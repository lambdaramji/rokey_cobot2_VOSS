# U5 파지 시퀀스·판정·reason — Pseudo code

[U5-dd.md](U5-dd.md)(승인 10/09, 재검 r1 반영)의 함수별 의사코드. `grip.py`·`fsm.py`·`params.py` 는 ROS·시계·파일을 쓰지 않는다. 시각은 노드 시계 초(float), 폭 mm, 내부 길이 m. 최종은 코드가 기준이다.

- 상태: **pseudo 승인(박병후, 10/09)** — 재검 r1 반영본

## 1. grip.py — 상수·데이터

```text
OPEN = "OPEN"   CLOSE = "CLOSE"   VERIFY = "VERIFY"          # 호출 종류
ACTION_KIND = {GRIPPER_OPEN: OPEN, GRIPPER_CLOSE: CLOSE, GRIPPER_VERIFY: VERIFY}   # FSM 행동 → 종류
CODES = ("OK", "TIMEOUT", "INVALID", "BUSY", "COMM_ERROR")    # Gripper.srv message 계약
UNKNOWN = "UNKNOWN"   UNAVAILABLE = "UNAVAILABLE"              # belt_servo 가 만드는 코드
BUSY_RETRY_MAX = 1                                             # BUSY 재요청 횟수 (D3)
BUSY_RETRY_DELAY_S = 0.5                                       # BUSY 뒤 재요청까지 기다림 (E1, 판단값)
PENDING  REPLY  BUSY_WAIT  RETRY  TIMED_OUT                    # poll 결과 (문자열 상수)
# 로그 state 에만 쓰는 값: UNAVAILABLE (요청 순간 서비스 없음)

frozen GripCall(goal_id, attempt, kind, seq, width_mm, force_n, sent_s,
                busy_retries = 0, busy_at = None)              # 호출 한 건 = 이름표 + 보낸 값
frozen RawReply(ok, width_mm, grip_detected, message)          # srv 응답을 ROS 없이
frozen PollResult(status, reply = None, code = "", raw_message = "")
```

## 2. grip.py — 함수

```text
함수 request_for(action, pre_open_mm, grasp_width_mm):
    kind = ACTION_KIND 에서 action 찾기,  없으면 ValueError("모르는 그리퍼 행동")
    폭 = pre_open_mm  (kind 가 OPEN 이면)  아니면 grasp_width_mm    # VERIFY 도 닫기 폭 (D1)
    반환 (kind, 폭)

함수 message_code(message):
    머리 = message 를 첫 ":" 앞까지 자르고 앞뒤 공백 제거, 대문자로        # "INVALID: width" → "INVALID"
    반환 머리  (CODES 안에 있으면)  아니면 UNKNOWN                        # "" 도 UNKNOWN

함수 new_call(goal_id, attempt, kind, width_mm, force_n, seq, now):
    반환 GripCall(goal_id, attempt, kind, seq, width_mm, force_n, sent_s = now)

함수 busy_marked(call, now):                                   # BUSY 받음 → 재요청 대기 시작
    반환 call 에서 busy_at = now 로 바꾼 것

함수 retried(call, now):                                       # BUSY 재요청 = 새 요청 (E1)
    반환 call 에서 seq + 1, busy_retries + 1, sent_s = now, busy_at = None 으로 바꾼 것

함수 poll(call, done, raw, failed, now, timeout_s):
    만약 call.busy_at 있음:                                     # ⓪ 재요청 기다리는 중 (future 는 이미 소비)
        만약 now − call.busy_at ≥ BUSY_RETRY_DELAY_S:  반환 PollResult(RETRY)
        반환 PollResult(PENDING)
    만약 done:
        만약 failed:                                            # ① future 가 예외로 끝남 (E3)
            반환 PollResult(REPLY, GripperReply(False, 0.0, False, "COMM_ERROR"), "COMM_ERROR")
        code = message_code(raw.message)                        # ②
        만약 code == "BUSY" 그리고 call.busy_retries < BUSY_RETRY_MAX:
            반환 PollResult(BUSY_WAIT, None, code, raw.message)
        reply = GripperReply(raw.ok, raw.width_mm, raw.grip_detected, code)   # FSM 에는 코드만 (E4)
        반환 PollResult(REPLY, reply, code, raw.message)
    만약 now − call.sent_s > timeout_s:                          # ③ 같으면 아직 기다린다
        반환 PollResult(TIMED_OUT, GripperReply(False, 0.0, False, "TIMEOUT"), "TIMEOUT")
    반환 PollResult(PENDING)                                     # ④

함수 unavailable_reply():
    반환 GripperReply(False, 0.0, False, UNAVAILABLE)            # judge_grip → GRIPPER_UNAVAILABLE

함수 descend_time_s(dist_m, v, a, k, tol):                     # E5: U2 z 제어(kp_z·상한)를 따른 시간
    만약 v, a, k, tol 중 하나라도 ≤ 0:  ValueError                # 방어 (기동 검사가 먼저 막음)
    d_p = v / k                                                   # 이 거리부터 P 가 감속 (포화 끝)
    만약 dist_m ≤ d_p:                                            # 처음부터 감속 구간
        반환 max(ln(dist_m / tol) / k, 0)                         # 지수 접근으로 tol 까지
    반환 v / (2a)                                                 # 0 → v 가속하며 손해 보는 시간
         + (dist_m − d_p) / v                                     # 상한 속도로 가는 구간
         + ln(d_p / tol) / k                                      # 감속 꼬리 (d_p → tol)
    # 예: (0.059, 0.05, 0.1, 2, 0.002) → 0.25 + 0.68 + 1.26 = 2.19 s

함수 grasp_room_ok(tcp_x, x_max, belt_speed, need_s, margin_m):
    남은 길 = x_max − tcp_x
    필요한 길 = belt_speed × need_s + margin_m                    # 하강·닫힘 동안 벨트 따라 가는 거리 + 여유
    반환 남은 길 ≥ 필요한 길                                       # 같으면 여유 있음

함수 call_record(call, state, now, reply = None, code = None, raw = None, verdict = None):
    # 키는 항상 전부, 모르는 값은 None (E14)
    끝남 = state 가 REPLY·TIMED_OUT·UNAVAILABLE 중 하나
    반환 {kind, attempt, seq, width_cmd_mm, force_n, sent_s, busy_retries ← call,
          state,
          rx_s      = now                (끝남이면) 아니면 None,
          latency_s = now − call.sent_s  (끝남이면) 아니면 None,
          ok, width_actual_mm, grip_detected ← reply (없으면 None),
          message = raw, code = code, verdict = verdict}
```

## 3. fsm.py — 바뀌는 곳

```text
REACH_GRASP_ROOM = "REACH_GRASP_ROOM"

TickEvent 에 필드 추가:
    grasp_room: bool = True        # x 여유 있음. 기본 True → 기존 시험 그대로

_advance 의 TRACK 줄을 바꾼다:
    만약 phase == TRACK 그리고 ev.aligned:
        만약 ev.grasp_room 이 아님:
            반환 _end(state, OUT_OF_REACH, REACH_GRASP_ROOM)    # DESCEND 에 들어가지 않는다 (D6)
        반환 Transition(state 의 phase = DESCEND)
(나머지 줄·step 의 1~9 순서는 그대로. judge_grip 그대로)
```

## 4. params.py — 바뀌는 곳

```text
PARAM_SPECS 에 추가 (grasp.* 묶음 뒤, stop_timeout_s 옆):
    ParamSpec("grasp.close_time_max_s", "float", "s",  필수, > 0)
    ParamSpec("grasp.room_margin_mm",   "float", "mm", 필수, ≥ 0)
    ParamSpec("gripper_timeout_s",      "float", "s",  필수, > 0)

_cross_checks 에 추가 (have() 로 둘 다 있을 때만):
    timeout ≤ close_time_max        → ("gripper_timeout_s", "grasp.close_time_max_s 보다 커야 함")
    hold_max ≥ pre_open             → ("grasp.hold_width_max_mm", "gripper.pre_open_mm 보다 작아야 함")
    hold_min ≤ grasp_width          → ("grasp.hold_width_min_mm", "gripper.grasp_width_mm 보다 커야 함 (빈손 보고 폭은 명령 폭 아래)")
```

`config/belt_servo.yaml`: `hold_width_min_mm: 39.5`, `hold_width_max_mm: 43.5`, `close_time_max_s: 2.1`, `room_margin_mm: 10.0`(제안), `gripper_timeout_s: 3.0`(제안, gateway `rg2_timeout_s` 6.0 주석) + 근거 주석(DD 5절).

## 5. belt_servo.py — GoalCtx·노드 필드

```text
GoalCtx 에 추가:
    grip_call = None            # 지금 기다리는 호출 (BUSY 재요청 대기 중에도 남음)
    grip_future = None          # 그 호출의 future (진동벨). 응답을 소비했으면 None
    grip_seq = 0                # 이 goal 의 그리퍼 요청 수
    grip_ready_reply = None     # 요청 순간 정해진 응답 (서비스 없음)
    grip_log = None             # 로그 gripper 칸

__init__ 에 추가:
    self.grip_late_discarded = 0                       # 버린 늦은 응답 수 (E8)
    self._room_need_s = None
    READY 이면:
        t_desc = grip.descend_time_s(cfg.approach_dz − cfg.grasp_dz, cfg.descend_speed,
                                     cfg.a_max, cfg.kp_z, cfg.height_tol_m)
        self._room_need_s = t_desc + values["grasp.close_time_max_s"]
        INFO "x 여유: 하강 예상 <t_desc> s + 닫힘 <close> s → 필요 <belt × need + margin> m"
```

## 6. belt_servo.py — 행동·poll·고아

```text
함수 _handle_actions(ctx, actions, now):
    각 action 에 대해:
        만약 action == REQUEST_STOP:  _request_stop(ctx, now)              # U1 그대로
        아니면 만약 action 이 GRIPPER_OPEN/CLOSE/VERIFY:  _request_gripper(ctx, action, now)
        아니면:  WARN "모르는 행동 <action>"

함수 _request_gripper(ctx, action, now):
    kind, 폭 = grip.request_for(action, gripper.pre_open_mm, gripper.grasp_width_mm)
    call = grip.new_call(ctx.goal_id, ctx.state.attempts, kind, 폭, gripper.force_n,
                         ctx.grip_seq + 1, now)                          # attempts = 전이 후 값
    _send_gripper(ctx, call, now)

함수 _send_gripper(ctx, call, now):                                    # 처음 보낼 때·BUSY 재요청 공통
    ctx.grip_seq = call.seq                                              # 재요청 순번도 반영 (r2)
    만약 그리퍼 서비스가 준비 안 됨:                                    # D5: 기다리지 않는다 (재요청 때도, r2)
        ctx.grip_call = None;  ctx.grip_future = None
        ctx.grip_ready_reply = grip.unavailable_reply()
        ctx.grip_log = grip.call_record(call, UNAVAILABLE, now, code = UNAVAILABLE)
        ERROR "gripper 서비스 없음 — <kind> seq=<seq>"
        반환
    fut = 그리퍼 클라이언트.call_async(Gripper.Request(width = call.width_mm, force = call.force_n))
    ctx.grip_call = call;  ctx.grip_future = fut                         # 콜백은 달지 않는다 (E8)
    ctx.grip_log = grip.call_record(call, PENDING, call.sent_s)
    INFO "gripper 요청 <kind> <폭> mm <힘> N seq=<seq> attempt=<attempt>"

함수 _raw_of(fut) → (done, raw, failed, 예외글):
    만약 fut 가 None 또는 아직 안 끝남:  반환 (False, None, False, "")
    시도:
        resp = fut.result()
        반환 (True, RawReply(resp.ok, resp.width_actual, resp.grip_detected, resp.message), False, "")
    예외 e:
        반환 (True, None, True, repr(e))                                  # E3

함수 _poll_gripper(ctx, now) → GripperReply 또는 None:
    만약 ctx.grip_ready_reply 있음:                                     # 서비스 없음 응답을 한 번 넘긴다
        r = ctx.grip_ready_reply;  ctx.grip_ready_reply = None;  반환 r
    call = ctx.grip_call
    만약 call 없음:  반환 None
    done, raw, failed, 예외글 = _raw_of(ctx.grip_future)
    res = grip.poll(call, done, raw, failed, now, gripper_timeout_s)
    만약 res.status == PENDING:  반환 None
    만약 res.status == BUSY_WAIT:                                       # BUSY 첫 번째: 0.5 s 기다린다
        WARN "gripper BUSY — <BUSY_RETRY_DELAY_S> s 뒤 한 번 더 <kind> seq=<seq>"
        ctx.grip_call = grip.busy_marked(call, now);  ctx.grip_future = None   # 응답은 소비함
        ctx.grip_log = grip.call_record(ctx.grip_call, BUSY_WAIT, now, code = "BUSY", raw = res.raw_message)
        반환 None
    만약 res.status == RETRY:
        _send_gripper(ctx, grip.retried(call, now), now)
        반환 None
    # 여기부터 REPLY 또는 TIMED_OUT: 이 호출은 끝
    만약 res.status == TIMED_OUT:  _orphan_gripper(ctx)                  # 나중에 오는 응답은 버림으로 센다
    ctx.grip_call = None;  ctx.grip_future = None
    verdict = fsm.judge_grip(res.reply, hold_min, hold_max)[0]  (call.kind 가 CLOSE·VERIFY 이면)  아니면 None
    ctx.grip_log = grip.call_record(call, res.status, now, res.reply, res.code,
                                    res.raw_message 또는 예외글, verdict)
    만약 res.code == "INVALID":   ERROR "gripper 설정 오류(폭·힘) — message=<원문>"
    아니면 만약 res.reply.ok 아님 또는 res.code != "OK":  WARN "gripper 실패 <code> <원문>"
    반환 res.reply

함수 _orphan_gripper(ctx):                                            # 기다리던 호출을 내려놓는다 (D7·E8)
    fut = ctx.grip_future;  call = ctx.grip_call
    ctx.grip_call = None;  ctx.grip_future = None
    만약 fut 있음:
        fut.add_done_callback( (끝나면) _on_grip_late(call, fut) )     # 이미 끝났으면 곧바로 불린다

함수 _on_grip_late(call, fut):                                        # 고아 호출의 응답 = 무조건 버림
    시도:
        self.grip_late_discarded += 1
        done, raw, failed, 예외글 = _raw_of(fut)
        code = "COMM_ERROR" (failed 이면)  아니면 grip.message_code(raw.message)
        INFO "gripper_late_discarded goal=<goal_id> attempt=<attempt> kind=<kind> seq=<seq>
              code=<code> message=<raw.message 또는 예외글>"
    예외 e:  ERROR "_on_grip_late 예외 <e>"                              # 콜백이 노드를 죽이지 않게
```

## 7. belt_servo.py — 이벤트·로그·종료

```text
함수 _build_event(ctx, now):     (U2 본문 그대로 + 두 칸)
    ...
    gripper = None
    만약 ctx.state.stopping 아님:                                       # E2: 취소 뒤에는 보지도, 재요청하지도 않는다
        gripper = _poll_gripper(ctx, now)
    grasp_room = True
    만약 geo 있음:
        grasp_room = grip.grasp_room_ok(geo.tcp[0], cfg.x_max, ‖cfg.belt_v‖,
                                        self._room_need_s, grasp.room_margin_mm / 1000)
    반환 TickEvent(..., gripper = gripper, grasp_room = grasp_room)

함수 _tick_values(...):    "gripper": ctx.grip_log                       # E7 (진행 중 또는 마지막 끝난 호출)
함수 _snapshot_values(...): "gripper": last.get("gripper")               # 0 유지·예외 스냅샷
함수 _finish(...):          _last_goal 에 "gripper": ctx.grip_log 추가
                            _orphan_gripper(ctx)                          # 진행 중 호출은 취소하지 않고, 응답이 오면 버림 (D7)
(main·destroy_node·_finish_on_shutdown 은 PR #130 소관 — 고치지 않음. #130 의 종료 경로도 _finish 를 거치므로 같이 적용)
```

## 8. 시험 도구 (test_action_e2e.py)

```text
클래스 FakeGripper(Node):                       # 별도 스레드 executor 에서 돈다 (E11)
    __init__(script):                             # script = {OPEN: [응답...], CLOSE: [...], VERIFY: [...]}
        서비스 /voss/robot/gripper 생성 (ReentrantCallbackGroup)
        self.requests = []                        # 받은 (폭, 힘, 받은 시각)
        self._closes = 0                          # 닫기 폭 요청 수 (1번째 CLOSE, 2번째 VERIFY)
    _on_gripper(req, res):
        self.requests 에 (req.width, req.force, 지금) 추가
        만약 req.width ≥ 60:  kind = OPEN
        아니면:  self._closes += 1;  kind = CLOSE (첫 번째) 아니면 VERIFY     # U9 재시도 때는 바꿔야 함
        응답 하나 꺼냄 (목록 끝이면 마지막 것 반복) = (지연, ok, 폭, grip, message)
        time.sleep(지연)                           # 이 스레드만 잔다
        res 채워 반환

함수 start_gripper(script) → (노드, executor, 스레드):
    executor = MultiThreadedExecutor();  노드 추가;  daemon 스레드로 executor.spin()

FakeClient 확장:
    pose 적분 옵션: 50 Hz 마다 tcp += 마지막으로 받은 servo_cmd 선속도 × 0.02, 그 값을 pose 로 발행
    박스 옵션 "moving" | "still" | 없음:
        30 Hz 로 track 7, stamp = 지금, 위치 = 시작점 (+ belt_v × 경과시간, moving 일 때), 윗면 z 0.16, HAND_EYE

env 픽스처: request.param = dict(stop_ok, gripper = 스크립트 또는 "none", 덮어쓸 파라미터, box, integrate_pose)
    기본: stop 없음, 가짜 그리퍼 = 모두 즉시 OK(OPEN 폭 90, CLOSE·VERIFY 폭 40.9 grip), 박스 없음, 고정 pose
    moving 이면 파라미터에 control.kp_per_s:=1.5 추가 (E12)
    그리퍼가 있으면: assert node._gripper_cli.wait_for_service(timeout_sec = 2.0)   (E12)
    정리 순서: 그리퍼 executor.shutdown(2) → 스레드 join(2) → 그리퍼 노드 destroy
               → ex.shutdown → node·client destroy → rclpy.try_shutdown()      (E11)
```

## 9. 시험 의사코드 (지시서 4 케이스)

```text
① 정상:  box moving, integrate_pose, 그리퍼 기본
    goal 7 보냄 → 결과 기다림(≤ 15 s)
    확인: SUCCEEDED · reason OK · grasped · attempts 1
          feedback == [PREPARE, TRACK, DESCEND, GRASP, LIFT, VERIFY]
          gripper 요청 폭 == [90, 39, 39]
          0.6 s 더 돌린 뒤: node.grip_late_discarded == 0 · 마지막 cmd == (0,0,0)

② 빈손:  box moving, integrate_pose, CLOSE = (0, ok, 38.4, grip=False, "OK")
    확인: ABORTED · GRASP_FAILED · cause NOT_DETECTED · attempts 1
          0.6 s 더 돌려도 요청 폭 == [90, 39]            # 개방 재요청 없음
          grip_late_discarded == 0 · 마지막 cmd 0

③ 늦은 응답:  box moving, integrate_pose, gripper_timeout_s 0.5 · close_time_max_s 0.4, CLOSE 지연 1.0 s
    확인: ABORTED · DEVICE_ERROR · cause GRIPPER_TIMEOUT
          1.2 s 더 돌린 뒤 grip_late_discarded == 1 · 요청 폭 == [90, 39] · 마지막 cmd 0

④ 정지 실패:  box moving, integrate_pose, stop_ok False, CLOSE 지연 1.0 s
    feedback 에 GRASP 가 보이면 cancel
    확인: ABORTED · DEVICE_ERROR · cause STOP_FAILED_TIMEOUT
          1.2 s 더 돌린 뒤 grip_late_discarded == 1 · 요청 폭 == [90, 39] · 마지막 cmd 0

⑤ BUSY 1회:  box still, stop 정상, OPEN = [(0, False, 0, False, "BUSY"), (0, ok, 90, False, "OK")]
    확인: 요청 폭 == [90, 90] · 두 요청 간격 ≥ 0.45 s · grip_log.busy_retries == 1 · seq == 2
    TRACK 이 feedback 에 나오면 cancel → CANCELED 까지 기다려 정리 (r2)
⑥ BUSY 2회:  box still, OPEN = BUSY 계속 → DEVICE_ERROR, cause GRIPPER_BUSY, 요청 폭 == [90, 90]
⑦ INVALID:   OPEN = (0, False, 0, False, "INVALID: width") → DEVICE_ERROR, cause GRIPPER_INVALID
⑧ 서비스 없음: gripper "none" → DEVICE_ERROR, cause GRIPPER_UNAVAILABLE
⑨ x 여유 부족 (r2): box moving, reach.x_max_mm 200 → OUT_OF_REACH / REACH_GRASP_ROOM, feedback [PREPARE, TRACK], 요청 [90], 마지막 cmd 0
```

## 10. 변경 기록
- 2026-10-09: 초안 (작업 세션 U5).
- 2026-10-10: 재검 r2 반영 — `_send_gripper` 가 순번 동기화·서비스 검사(재요청 포함), 시험 ⑤ 정리·⑨ 추가.
- 2026-10-09: 재검 r1 반영 — GripCall 하나로 합침, BUSY 0.5 s 대기 재요청(BUSY_WAIT), 고아 때만 done 콜백(`_orphan_gripper`·`_on_grip_late`, `is_current` 삭제), 하강 시간 식(P 꼬리), 로그 키 고정·OPEN verdict null, hold_min 교차 검사, 시험 픽스처(서비스 대기·kp 1.5·정지 박스·정리 순서).
