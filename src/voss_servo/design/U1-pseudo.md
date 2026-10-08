# U1 belt_servo 뼈대 — Pseudo code

[U1-dd.md](U1-dd.md) 의 함수별 의사코드. 순수 모듈(params·fsm·log_schema)은 ROS 를 import 하지 않는다.

## 1. params.py

```text
ParamSpec = (이름, 종류[float|float3|str], 단위, 필수 여부, 검사 함수 또는 없음)
PARAM_SPECS = DD 1절 표 전체

함수 vector_norm(v):
    반환 √(v[0]² + v[1]² + v[2]²)

함수 check_params(values):            # values = {이름: 값 또는 None}
    missing = [], invalid = []
    PARAM_SPECS 의 각 spec 에 대해:
        값 = values.get(spec.이름)
        값이 None 이면:
            spec 이 필수면 missing 에 이름 추가
            다음 spec 으로
        종류가 float 인데 숫자가 아니면 → invalid (이름, "숫자 아님")
        종류가 float3 인데 길이 3 숫자 목록이 아니면 → invalid (이름, "길이 3 목록 아님")
        spec 의 자기 검사(> 0 등)가 실패면 → invalid (이름, 이유)
    # 두 값을 함께 보는 검사 (둘 다 있을 때만)
    direction 노름이 1 ± 0.01 밖이면 → invalid ("belt.direction_base", "norm 0.500")
    grasp_width ≥ pre_open 이면 → invalid
    hold_width_min ≥ hold_width_max 이면 → invalid
    reach.x_min ≥ reach.x_max 이면 → invalid
    approach_height ≤ vision_cutoff 이면 → invalid
    반환 ReadyReport(ready = missing·invalid 모두 비었나, missing, invalid)

함수 params_digest(values):
    None 이 아닌 값만 이름순으로 정렬해 JSON 문자열로 만든다
    반환 sha256(그 문자열) 의 16진수 64자

함수 ready_log_line(report):
    ready 면 "READY"
    아니면 "READY 거부: missing=[…] invalid=[이름: 이유, …]"
```

## 2. fsm.py

```text
PHASES = PREPARE, TRACK, DESCEND, GRASP, LIFT, VERIFY
VISION_PHASES = PREPARE, TRACK, DESCEND          # 박스를 봐야 하는 단계
MAX_ATTEMPTS = 3                                  # 계약값(상수)

함수 start():
    반환 FsmState(PREPARE, attempts 0, stopping 거짓), 행동 [GRIPPER_OPEN]

함수 judge_grip(reply, w_min, w_max):
    reply.ok 가 거짓이거나 reply.message ≠ "OK" 이면
        반환 DEVICE_ERROR, cause = "GRIPPER_" + message (message 가 OK 인데 ok 거짓이면 "GRIPPER_NOT_OK")
    grip_detected 가 거짓이면 반환 NOT_HELD, "NOT_DETECTED"
    폭이 [w_min, w_max] 밖이면 반환 NOT_HELD, "WIDTH_OUT"
    반환 HELD, ""

함수 is_vision_blind(phase, tcp_z_m, box_top_z_m, cutoff_mm):
    phase 가 GRASP·LIFT·VERIFY 면 참
    phase 가 DESCEND 이고 tcp_z·box_top_z 둘 다 알면:
        반환 tcp_z ≤ box_top_z + cutoff_mm/1000
    반환 거짓                                     # 모르면 보수적으로 "보인다"로 보고 검사를 계속한다

함수 input_flags(now, last_box_rx, last_valid_rx, latest_invalid, last_pose_rx,
                 goal_start, vision_since, blind, lost_timeout, stale_timeout):
    # 수신 시각 기준. 기준 시각은 "마지막 수신"과 "비전 필요 구간 시작" 중 늦은 쪽
    pose_ref = max(last_pose_rx 또는 −∞, goal_start)
    pose_stale = now − pose_ref > stale_timeout
    blind 이면 반환 (box_lost 거짓, box_stale 거짓, pose_stale)
    box_ref = max(last_box_rx 또는 −∞, vision_since)
    box_lost = now − box_ref > lost_timeout
    valid_ref = max(last_valid_rx 또는 −∞, vision_since)
    box_stale = latest_invalid 이고 (now − valid_ref > stale_timeout)   # 메시지는 오는데 계속 invalid
    반환 (box_lost, box_stale, pose_stale)

함수 step(state, ev, w_min, w_max):
    # 1~3: 취소 후 stop 응답 대기
    state.stopping 이면:
        ev.stop_result 가 OK            → 끝(CANCELED, "STOP_OK")
        ev.stop_result 가 다른 값        → 끝(DEVICE_ERROR, "STOP_" + 값)
        아니면                           → 그대로
    # 4: 취소
    ev.cancel_requested 이면 → stopping 참으로, 행동 [REQUEST_STOP]
    # 5: 그리퍼 통신 실패
    ev.gripper 가 있으면 (판정, cause) = judge_grip(ev.gripper, w_min, w_max)
    판정이 DEVICE_ERROR 이면 → 끝(DEVICE_ERROR, cause)
    # 6~9: 입력·영역
    ev.pose_stale                                       → 끝(STALE_INPUT, "POSE_MISSING")
    phase ∈ VISION_PHASES 이고 not ev.vision_blind 이면:
        ev.box_stale                                    → 끝(STALE_INPUT, "BOX_INVALID")
        ev.box_lost                                     → 끝(LOST, "BOX_MISSING")
    phase ∈ (VISION_PHASES + GRASP) 이고 ev.reach 있음 → 끝(OUT_OF_REACH, "REACH_" + reach)
    # 10~17: 정상 진행
    PREPARE 이고 ev.gripper 응답이 ok       → TRACK
    TRACK 이고 ev.aligned                    → DESCEND
    DESCEND 이고 ev.at_grasp_height          → GRASP, attempts+1, 행동 [GRIPPER_CLOSE]
    GRASP 이고 판정 HELD                     → LIFT
    LIFT 이고 ev.at_lift_height              → VERIFY, 행동 [GRIPPER_VERIFY]
    VERIFY 이고 판정 HELD                    → 끝(OK, "", grasped 참)
    (GRASP 또는 VERIFY) 이고 판정 NOT_HELD:
        cause = VERIFY 면 "DROPPED", 아니면 judge_grip 의 cause
        attempts < 3 → PREPARE, 행동 [GRIPPER_OPEN], attempt_ended 참, cause
        attempts = 3 → 끝(GRASP_FAILED, cause), attempt_ended 참
    그 밖 → 그대로
    # "끝(...)" 은 Transition(terminal 참, reason, cause, grasped). 노드는 terminal 이면 시도 로그도 한 줄 쓴다
```

## 3. log_schema.py

```text
TICK_FIELDS    = DD 3절 틱 키 (순서 고정)
ATTEMPT_FIELDS = DD 3절 시도 키 (TICK_FIELDS 의 부분집합, 모듈 로드 때 assert)

함수 make_tick(**values):
    values 의 키 집합 ≠ TICK_FIELDS − {"kind"} 이면 ValueError(빠진 키·남는 키 이름)
    float 값 중 NaN·무한대가 있으면 None 으로 바꾼다
    반환 {"kind": "tick", **values}  (TICK_FIELDS 순서)

함수 to_attempt(tick):
    반환 {"kind": "attempt", ATTEMPT_FIELDS 의 나머지 키는 tick 에서 복사}

함수 to_json_line(record):
    반환 json.dumps(record, ensure_ascii=False, allow_nan=False, 구분자 짧게)    # NaN 이 있으면 예외

클래스 JsonlWriter(path):
    write(record): 처음 쓸 때 폴더를 만들고 파일을 연다 → to_json_line + 줄바꿈 → 바로 flush
    close(): 열려 있으면 닫는다

함수 log_paths(log_dir, started):                # started = 노드 기동 시각
    반환 (log_dir/ticks/servo_ticks_YYYYMMDD_HHMMSS.jsonl,
          log_dir/attempts/servo_attempts_YYYYMMDD_HHMMSS.jsonl)
```

## 4. belt_servo.py

```text
QOS_BOX  = best_effort, volatile, depth 5    # 구독 depth 는 소비자 재량 (DD 0절)
QOS_POSE = best_effort, volatile, depth 1
QOS_CMD  = best_effort, volatile, depth 1    # topics.md

클래스 BeltServoNode:
  __init__():
    PARAM_SPECS 의 각 이름을 "기본값 없음·타입 자유"로 선언 → 값 읽기(안 왔으면 None)
    report = check_params(values), sha = params_digest(values)
    로그 "config_version=… config_sha256=… params_sha256=sha" (version 없으면 경고)
    report.ready 면 info "READY", 아니면 error ready_log_line(report)
    self.ready = report.ready
    로그 writer 2개 준비(파일은 처음 쓸 때 생김)
    구독 box(QOS_BOX) → _on_box, pose(QOS_POSE) → _on_pose
    발행 servo_cmd(QOS_CMD)
    클라이언트 gripper(U5 에서 사용), stop
    액션 서버 track_and_grasp(goal → _on_goal, cancel → _on_cancel, execute → _execute)
    타이머 1/rate_hz (rate 가 없으면 30) → _on_tick
    상태: ctx = None, busy = 거짓, hold_until = None, boxes = {}, pose = None

  _on_box(msg):
    now = 지금, 이전 = boxes.get(msg.track_id)
    이전이 있고 msg.stamp < 이전.stamp 이면 버린다          # 같은 트랙 역행
    boxes[track_id] = (msg, 수신 now, valid 면 now 아니면 이전.last_valid_rx)
    lost_timeout × 4 넘게 갱신 안 된 다른 트랙 항목은 지운다(현재 goal 트랙 제외)

  _on_pose(msg):
    pose = (msg, 수신 now)

  _on_goal(req):
    READY 아님   → 로그 "goal 거부: READY 아님", REJECT
    busy         → 로그 "goal 거부: 진행 중 또는 0 유지 중", REJECT
    track_id ≤ 0 → 로그, REJECT
    busy = 참, ACCEPT

  _on_cancel(handle):
    ACCEPT (실제 처리는 타이머가 handle.is_cancel_requested 를 보고)

  async _execute(handle):
    state, actions = fsm.start()
    ctx = GoalCtx(handle, goal_id, track_id, state, 시작 now, vision_since = now,
                  done = 빈 봉투(Future), stop_future 없음, 마지막 phase 없음)
    _handle_actions(actions)
    feedback(phase) 1회
    result = await ctx.done                     # 타이머가 채울 때까지 기다림
    reason 이 OK → handle.succeed(), CANCELED → handle.canceled(), 그 밖 → handle.abort()
    반환 Result(grasped, reason, attempts)

  _on_tick():
    now = 지금
    hold 중이면(hold_until 있음):
        _publish_zero(now), 틱 로그(종료된 goal 정보)
        now ≥ hold_until 이면 hold 끝, busy = 거짓
        반환
    ctx 가 없으면 반환                              # IDLE: 발행·로그 없음
    시도:
        ev = _build_event(ctx, now)
        tr = fsm.step(ctx.state, ev, w_min, w_max)
        ctx.state = tr.state
        _handle_actions(tr.actions)
        vel = 0 벡터                                 # U2 에서 control.py 로 교체
        _publish(vel, now)
        phase 가 바뀌었으면 feedback(phase)
        틱 기록 = make_tick(…) → ticks writer
        tr.attempt_ended 또는 tr.terminal 이면 to_attempt(틱 기록) → attempts writer
        tr.terminal 이면 _finish(ctx, tr.reason, tr.cause, tr.grasped, now)
    예외가 나면:
        error 로그(예외 내용), _publish_zero(now)
        _finish(ctx, "DEVICE_ERROR", "INTERNAL_EXCEPTION", 거짓, now)

  _build_event(ctx, now):
    entry = boxes.get(ctx.track_id), pose = 최신 pose
    box_top_z = entry 의 마지막 유효 position_base.z (없으면 None)
    blind = is_vision_blind(ctx.state.phase, pose 의 z, box_top_z, cutoff)
    blind 가 참 → 거짓으로 바뀌었으면 ctx.vision_since = now      # 재시도 PREPARE 등
    (box_lost, box_stale, pose_stale) = input_flags(…)
    stop_result = _poll_stop(ctx, now)
    반환 TickEvent(cancel_requested = handle.is_cancel_requested, stop_result,
                   box_lost, box_stale, pose_stale, vision_blind = blind,
                   reach = None, aligned = 거짓, at_grasp_height = 거짓,
                   at_lift_height = 거짓, gripper = None)        # U2·U5 에서 채움

  _handle_actions(actions):
    REQUEST_STOP → stop 서비스가 준비 안 됐으면 ctx.stop_result = UNAVAILABLE
                   아니면 ctx.stop_future = call_async(Trigger), ctx.stop_sent = now
    GRIPPER_*    → debug 로그 "U5 에서 구현"

  _poll_stop(ctx, now):
    ctx.stop_result 가 이미 정해졌으면 그것
    stop_future 가 끝났으면: 응답 success 면 OK, 아니면 FAILED (예외도 FAILED)
    stop_sent + stop_timeout_s < now 이면 TIMEOUT
    아니면 None

  _finish(ctx, reason, cause, grasped, now):
    reason 이 OK 가 아니면 warn 로그 "goal 종료 reason=… cause=…"
    ctx.done 에 (grasped, reason, attempts) 채움
    hold_until = now + zero_hold_s, ctx = None        # busy 는 hold 가 끝날 때 해제

  _publish(vel, now) / _publish_zero(now):
    TwistStamped(stamp = now, frame_id "base_link", linear = vel, angular = 0) 발행

  destroy_node():
    _publish_zero 한 번, writer 닫기, 부모 destroy

함수 main(): rclpy.init → 노드 → spin(단일 executor) → 종료 시 destroy·shutdown
```
