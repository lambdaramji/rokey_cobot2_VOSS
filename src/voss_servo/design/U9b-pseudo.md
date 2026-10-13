# U9-b 재시도 재접근 + 안전 후퇴 — Pseudo code

[U9b-dd.md](U9b-dd.md)(r1)의 함수별 의사코드. 베이스 f01750c(U9-a). `fsm.py`·`control.py`·`params.py`·`log_schema.py` 는
ROS·시계·파일을 쓰지 않는다. 시각은 노드 시계 초, 높이 설정값 mm, 내부 길이 m. 최종은 코드가 기준이다.

- 상태: **pseudo 승인(박병후, 10/12) — 재검 r1 반영본** (r1 변경은 DD 9절 처리표)
- "재시도 여유 판단값"과 "후퇴를 끝까지 했나"는 노드가 다시 추론하지 않고 **Transition 에 담아** 넘긴다
  (`Transition.retry_room_ok`·`retreat_done`) — fsm 이 판단한 그 값을 로그에 남긴다.

## 1. params.py — 상수

```text
RETREAT_CLEAR_MM = 10.0  # 후퇴 중 보정 TCP z 가 박스 윗면 + 이 값을 넘으면 xy 0
                         # (판단값. 보정 TCP 는 외삽으로 몇 mm 앞설 수 있어 5 가 아니라 10, U9b-dd 1절)
# BLIND_DWELL_MARGIN_S = 1.0 (U9-a) 주석에 한 줄: "후퇴 체류 상한 여유에도 같은 값 (U9b-dd 1절)"
```

## 2. fsm.py

### 2.1 상수·필드

```text
RETREAT_TIMEOUT = "RETREAT_TIMEOUT"    # 후퇴 상승이 상한보다 오래 감 (U9b)

FsmState (frozen) 끝에 기본값 필드 — 기존 FsmState(phase, attempts, stopping) 생성은 그대로 동작:
    exit_reason: str | None = None     # 후퇴 중이면 끝에 보낼 reason (GRASP_FAILED | DEVICE_ERROR)
    exit_cause: str = ""               # 그때의 cause (후퇴 끝 틱까지 기억)
    hold_z: bool = False               # 개방 응답 전까지 높이 유지 (폭 밖 후퇴)

TickEvent 끝에:
    retry_room: bool = False           # 재시도 1회를 끝낼 x 여유 — 모르면 없음(안전 쪽)
    hold_expired: bool = False         # 개방 대기가 상한을 넘었거나 x_max 에 닿았나
    lift_overstay: bool = False        # LIFT 상승 체류가 상한을 넘었나

Transition 끝에:
    retry_room_ok: bool | None = None  # GRASP NOT_HELD 를 판단한 틱에만 값 (로그용)
    retreat_done: bool = False         # 후퇴가 들기 높이 도달로 끝난 틱이면 참 (로그용)
```

### 2.2 작은 판정 함수

```text
함수 is_retreat(state):
    """지금 후퇴 중인가 = LIFT 인데 끝에 보낼 reason 이 정해져 있다."""
    반환 state.phase == LIFT 이고 state.exit_reason 이 None 아님

함수 is_low(state):
    """그리퍼 오류 때 그 자리에 멈추면 위험한가 (파지 높이 근처)."""
    만약 state.phase == GRASP: 반환 참                            # 핑거가 벨트 위 약 8 mm
    만약 state.phase == PREPARE 이고 state.attempts ≥ 1: 반환 참  # 재시도로 올라가는 중
    반환 is_retreat(state)                                       # 후퇴 중 (아직 낮을 수 있다)

함수 lift_since_next(prev, state, now):
    """LIFT 상승이 시작된 시각을 이어 간다. 상승 중이 아니면 None. (blind_since_next 와 같은 꼴)"""
    만약 state.phase != LIFT 또는 state.hold_z: 반환 None   # 들기 아님 · 개방 기다리는 중
    만약 prev 가 None: 반환 now                              # 이번 틱에 상승 시작
    반환 prev

함수 lift_overstay(lift_since, now, limit_s):
    """상승 체류가 상한을 넘었나. 같으면 아직 아님."""
    만약 lift_since 가 None 또는 limit_s 가 None: 반환 거짓
    반환 (now − lift_since) > limit_s

함수 _retreat(state, reason, cause, open_first, room_ok=None):
    """후퇴 시작 (끝이 아니다). 폭 밖이면 먼저 연다."""
    nxt = replace(state, phase=LIFT, exit_reason=reason, exit_cause=cause, hold_z=open_first)
    행동 = (GRIPPER_OPEN,) 만약 open_first 아니면 ()
    반환 Transition(state=nxt, cause=cause, actions=행동, retry_room_ok=room_ok)
```

### 2.3 `_not_held` 재작성

```text
함수 _not_held(state, cause, max_attempts, ev):
    """파지 실패 처리 (U9b-dd 2.3)."""
    만약 state.phase == VERIFY:                               # a: 들다 놓침 — 이미 들기 높이
        반환 _end(state, GRASP_FAILED, cause)                 #    재시도 없음
    만약 cause == "WIDTH_OUT":                                # b: 무언가 끼었다 → 먼저 열고 후퇴
        반환 _retreat(state, GRASP_FAILED, cause, open_first=참, room_ok=ev.retry_room)
                                                              #    (재시도는 실패 x ≤ 115 라 도달 불가 — 분기 없음)
    limit = min(max_attempts, MAX_ATTEMPTS)                   # 계약 상한 3
    만약 state.attempts < limit 이고 ev.retry_room:            # c: 재시도 (지금과 같음)
        반환 Transition(state=replace(state, phase=PREPARE), cause=cause,
                         actions=(GRIPPER_OPEN,), attempt_ended=참, retry_room_ok=참)
    # d: 시도 다 씀 또는 여유 없음 → 닫힌 채 안전 후퇴 뒤 GRASP_FAILED
    반환 _retreat(state, GRASP_FAILED, cause, open_first=거짓, room_ok=ev.retry_room)
```

### 2.4 `step()` — 바뀌는 곳만

```text
함수 step(state, ev, w_min, w_max, max_attempts):
    1~3 stopping → _stop_outcome (그대로)                      # 후퇴 중 취소도 여기서 CANCELED
    4 취소 → stopping + REQUEST_STOP (그대로)
    5 그리퍼 응답이 있으면 verdict, grip_cause = judge_grip(...)
      만약 verdict == DEVICE_ERROR:
          만약 is_low(state):                                   # 낮은 자리 → 닫힌 채 후퇴 (Q2·주관 4)
              반환 _retreat(state, DEVICE_ERROR, grip_cause, open_first=거짓)
              #   후퇴 중(개방 대기 포함)이었으면 exit 를 DEVICE_ERROR 로 덮고 hold_z 해제 → 바로 상승
          반환 _end(state, DEVICE_ERROR, grip_cause)           # 처음 PREPARE·VERIFY 등 (그대로)
    6 pose_stale → _end(STALE_INPUT, POSE_MISSING) (그대로, 후퇴 중 포함)
    7·8 비전 단계 ∧ 사각 아님 → STALE_INPUT / LOST (그대로)
    9 REACH_PHASES ∧ reach → OUT_OF_REACH (그대로 — LIFT 는 대상 아님)
    9b DESCEND ∧ blind_overstay → DEVICE_ERROR/DESCEND_BLIND_TIMEOUT (U9-a, 그대로)
    9c 만약 is_retreat(state) 이고 ev.lift_overstay:              # 새 — 후퇴에만 (정상 LIFT 는 노드가 경고만)
          반환 _end(state, DEVICE_ERROR, RETREAT_TIMEOUT)
    반환 _advance(state, ev, verdict, grip_cause, max_attempts)
```

### 2.5 `_advance()` — 바뀌는 줄만 (위에서부터 처음 맞는 줄)

```text
    PREPARE ∧ 그리퍼 응답 → TRACK (그대로)
    ... TRACK·DESCEND·GRASP(HELD) 줄 그대로 ...
    만약 is_retreat(state):                                       # 새: 후퇴 진행
        만약 state.hold_z:
            만약 ev.gripper 있음 또는 ev.hold_expired:             # 개방 응답(판정 안 봄) 또는 대기 상한·x 끝
                반환 Transition(replace(state, hold_z=거짓))       # 이제 올라간다
            반환 Transition(state)                                # 개방 기다림 (z 유지, xy FF)
        만약 ev.at_lift_height:
            반환 replace(_end(state, state.exit_reason, state.exit_cause), retreat_done=참)  # grasped 거짓
        반환 Transition(state)                                    # 올라가는 중
    만약 phase == LIFT 이고 ev.at_lift_height: VERIFY + GRIPPER_VERIFY (그대로 — 후퇴는 위에서 걸러짐)
    만약 phase == VERIFY 이고 verdict == HELD: OK (그대로)
    만약 phase ∈ (GRASP, VERIFY) 이고 verdict == NOT_HELD:
        cause = "DROPPED" 만약 phase == VERIFY 아니면 grip_cause
        반환 _not_held(state, cause, max_attempts, ev)             # ev 인자 추가
    반환 Transition(state)
```
- 순서: 후퇴 블록은 "LIFT ∧ at_lift → VERIFY" 줄보다 **앞**(후퇴가 VERIFY 로 새지 않게).
- hold_expired 로 풀린 뒤 늦게 온 개방 응답: 후퇴 블록은 hold_z 가 거짓이면 그리퍼 응답을 보지 않는다(무시). TIMEOUT 이면 5번이 exit 를 DEVICE_ERROR 로.
- docstring 머리말 설계 줄에 "U9b-dd 2절(후퇴·9c)" 추가.

## 3. control.py

```text
from voss_servo.params import BLIND_DWELL_MARGIN_S, RETREAT_CLEAR_MM

함수 z_plan(phase, top_z, cfg, hold_z=거짓):
    만약 hold_z: 반환 (None, 0.0, 0.0)                  # 개방 기다리는 동안 높이 유지 (GRASP 와 같음)
    ... 나머지 그대로 ...

함수 retreat_xy(tcp, top_z, cfg):
    """후퇴 중 xy 규칙: 윗면을 넘기 전엔 박스와 같이(FF), 넘었거나 x 끝이면 0 (수직)."""
    아래 = tcp[2] < top_z + RETREAT_CLEAR_MM / 1000       # 핑거 끝이 아직 박스 윗면 + 10 mm 아래
    x_안 = tcp[0] < cfg.x_max                              # x 끝 가드 (주관 1)
    반환 FF 만약 (아래 이고 x_안) 아니면 ZERO

함수 command(phase, stopping, terminal, geo, prev_v, dt, cfg, retreat=거짓, hold_z=거짓):
    만약 stopping 또는 terminal: 반환 0 (ZERO_STOP)        # 그대로 — 후퇴 중 취소도 즉시 0
    만약 geo 없음 / 관측 없음: 0 (그대로)
    rule = retreat_xy(geo.tcp, geo.top_z, cfg) 만약 retreat 아니면 xy_rule(phase, geo.visible)
    z_t, v_down, v_up = z_plan(phase, geo.top_z, cfg, hold_z)
    ... 나머지 그대로 ...

함수 retry_need_s(cfg, room_need_s):
    """GRASP 실패 순간부터 재시도 1회를 끝낼 시간 (s) = 재상승 + (하강 + 닫힘 상한)."""
    재상승 = grip.descend_time_s(cfg.approach_dz − cfg.grasp_dz, cfg.lift_speed,
                                 cfg.a_max, cfg.kp_z, cfg.height_tol_m)   # 59 mm → 2.66 s
    반환 재상승 + room_need_s                                             # + 4.94 = 7.60 s

함수 lift_max_s(cfg):
    """후퇴 상승 체류 상한 (s) = 파지→들기 높이 예상 + 여유. 정상 LIFT 는 이 값을 경고에만 쓴다."""
    예상 = grip.descend_time_s(cfg.lift_dz − cfg.grasp_dz, cfg.lift_speed,
                               cfg.a_max, cfg.kp_z, cfg.height_tol_m)     # 69 mm → 2.785 s
    반환 예상 + BLIND_DWELL_MARGIN_S                                       # 3.78 s

함수 retry_room_ok(tcp_x, need_s, belt_speed, cfg, margin_m):
    """지금 TCP x 에서 재시도 1회를 끝낼 x 여유가 있나. 모르면 거짓 (후퇴가 안전 쪽)."""
    만약 tcp_x 가 None 또는 need_s 가 None: 반환 거짓
    반환 grip.grasp_room_ok(tcp_x, cfg.x_max, belt_speed, need_s, margin_m)
```

## 4. belt_servo.py (연결만)

```text
__init__ (READY 일 때, _room_need_s 다음):
    self._retry_need_s = control.retry_need_s(self._ctrl, self._room_need_s)
    self._lift_max_s = control.lift_max_s(self._ctrl)
    INFO: f"재시도 x 여유: 실패 때 x_max 까지 {need_mm:.0f} mm 이상 남아야 재시도 (실패 x ≤ {x_max_mm − need_mm:.0f})"
          need_mm = (벨트속도 × _retry_need_s + room_margin) × 1000
    INFO: f"후퇴 체류 상한 {lift_max:.2f} s (정상 들기는 넘으면 경고만)"
    READY 아니면 둘 다 None

GoalCtx 끝에:
    lift_since: float | None = None      # LIFT 상승 시작 시각 (후퇴 상한·정상 경고)
    hold_since: float | None = None      # 개방 대기(hold_z) 시작 시각
    retry_room_ok: bool | None = None    # 마지막 GRASP 실패 판단 때 재시도 여유 (로그)
    retreat_done: bool | None = None     # 후퇴로 끝났나 (끝 틱에 정함, 로그)
    lift_warned: bool = False            # 정상 LIFT 체류 경고를 냈나 (goal 당 1회)

_build_event (blind_since 줄 다음, 전이 전 상태 기준):
    ctx.lift_since = fsm.lift_since_next(ctx.lift_since, ctx.state, now)
    ctx.hold_since = (ctx.hold_since 또는 now) 만약 ctx.state.hold_z 아니면 None
    tcp_x = geo.tcp[0] 만약 geo 있음 아니면 None
    hold_expired = ctx.hold_since 있음 이고 (now − ctx.hold_since ≥ close_time_max_s
                                             또는 (tcp_x 있음 이고 tcp_x ≥ cfg.x_max))
    TickEvent(...,
        retry_room = control.retry_room_ok(tcp_x, self._retry_need_s, 벨트속도, cfg, room_margin_mm/1000),
        hold_expired = hold_expired,
        lift_overstay = fsm.lift_overstay(ctx.lift_since, now, self._lift_max_s))

_tick_goal (fsm.step → _diagnose 다음):
    was_retreat = fsm.is_retreat(ctx.state)                   # 전이 전
    만약 tr.retry_room_ok 가 None 아님: ctx.retry_room_ok = tr.retry_room_ok
    만약 tr.terminal:
        ctx.retreat_done = 참 만약 tr.retreat_done 아니면 (거짓 만약 was_retreat 아니면 None)
    # 정상 LIFT 가 상한을 넘음 → 경고만 (성공 경로는 바꾸지 않는다, 재검 r1 MAJOR-2)
    만약 ev.lift_overstay 이고 tr.state.phase == LIFT 이고 not fsm.is_retreat(tr.state) 이고 not ctx.lift_warned:
        WARN: f"들기 체류 {now − ctx.lift_since:.2f} s > 상한 {self._lift_max_s:.2f} s — 로봇 속도·펜던트 오버라이드 확인 (goal 은 계속)"
        ctx.lift_warned = 참
    ctx.state = tr.state
    ...
    ctx.cmd = control.command(..., retreat=fsm.is_retreat(tr.state), hold_z=tr.state.hold_z)

_tick_values 에 **self._retreat_values(ctx, tr.state)

함수 _retreat_values(ctx, state):
    단계 = None
    만약 fsm.is_retreat(state): 단계 = "OPENING" 만약 state.hold_z 아니면 "RISING"
    반환 {"retreat": 단계, "retreat_reason": state.exit_reason,
          "retreat_done": ctx.retreat_done, "retry_room_ok": ctx.retry_room_ok}

_finish: self._last_goal 에 _retreat_values(ctx, ctx.state) 저장 (스냅샷 행용)
_snapshot_values: **{4키: g.get(키)} (0 유지 틱·예외 경로 GOAL_END 도 키를 채운다)
```
- 재시도로 PREPARE 에 돌아갈 때 `blind_since`(U9-a)는 phase ≠ DESCEND 라 None, 다시 DESCEND 사각에서 새로 센다 — 손댈 것 없음.
- `lift_since` 는 개방 대기(hold_z) 동안 None → 상승 시작부터 센다. 개방 대기는 hold_expired(2.3 s)가 막는다.

## 5. log_schema.py

```text
TICK_FIELDS 의 "grasped" 다음에:
    "retreat",         # null | "OPENING"(개방 기다림) | "RISING" — 안전 후퇴 중 (U9b)
    "retreat_reason",  # null | 후퇴 끝에 보낼 reason (GRASP_FAILED | DEVICE_ERROR)
    "retreat_done",    # null(후퇴 없음) | true(들기 높이 도달로 끝) | false(후퇴 중 다른 이유로 끝)
    "retry_room_ok",   # null | 마지막 GRASP 실패 때 재시도 x 여유 (true 재시도 / false 후퇴)
ATTEMPT_FIELDS 의 "grasped" 다음에 같은 4키 (부분집합 assert 그대로 통과)
```

## 6. fake_gripper.py (새, sim 전용)

```text
"""fake_gripper — sim 전용 가짜 RG2. 계획표대로 빈손·쥠·폭 밖을 응답한다 (U9b-dd 6.1)."""

OPEN_MIN_MM = 60.0                                   # 요청 폭이 이 이상이면 개방
WIDTH = {"empty": 38.4, "held": 41.0, "wide": 46.5}  # 보고 폭 (빈손 실측 38.0~38.7, 쥠 40.6~41.5, 폭 밖 > 44.0)
GRIP = {"empty": 거짓, "held": 참, "wide": 참}

@dataclass(frozen) FakeGripState: n_close: int = 0, closed: str | None = None   # 마지막 닫힘 결과 (열면 None)

함수 fake_reply(state, plan, width_req, pre_open_mm) -> (새 state, (ok, width, grip, message), 종류):
    """순수: 요청 하나 → 응답. 개방이면 열고, 닫힌 상태에서 또 닫으면 확인 재닫힘(결과 유지)."""
    만약 width_req ≥ OPEN_MIN_MM:
        반환 replace(state, closed=None), (참, pre_open_mm, 거짓, "OK"), "open"
    만약 state.closed 가 None 아님:                       # 이미 닫혀 있다 = VERIFY
        r = state.closed
        반환 state, (참, WIDTH[r], GRIP[r], "OK"), "verify"
    r = plan[min(state.n_close, len(plan) − 1)]          # 계획표 다음 (다 쓰면 마지막 반복)
    반환 FakeGripState(state.n_close + 1, r), (참, WIDTH[r], GRIP[r], "OK"), "close"

함수 parse_plan(text) -> tuple[str, ...]:
    값 = 쉼표로 나눈 소문자, 빈 값 제외. 비었거나 WIDTH 키가 아닌 값이 있으면 ValueError

class FakeGripperNode(Node):  이름 "fake_gripper"
    파라미터: plan "held", close_s 1.7, open_s 1.0, verify_s 0.2, pre_open_mm 90.0
    서비스 /voss/sim/gripper (voss_msgs/Gripper), 콜백:
        state, (ok, w, g, msg), 종류 = fake_reply(self.state, self.plan, req.width, pre_open_mm)
        time.sleep({open: open_s, close: close_s, verify: verify_s}[종류])
        self.state = state
        응답 (ok, width_actual=w, grip_detected=g, message=msg)
        INFO: f"fake_gripper {종류} 요청 {req.width:.1f} → 폭 {w} grip {g} (닫기 {state.n_close}번째)"
main: rclpy init → spin → 정리 (fake_box 와 같은 꼴)
setup.py console_scripts: "fake_gripper = voss_servo.fake_gripper:main",  # sim 전용 (U9b)
```

## 7. sim.launch.py

```text
새 인자 (기본이면 지금과 같음):
    gripper "gateway" | "fake",  grip_plan "held",  grip_close_s "1.7",
    max_attempts "" (비우면 sim yaml),  box_start_x_mm "-100"

_write_overrides(folder, kp, max_attempts) — 값이 있는 것만 YAML 에
    (control.kp_per_s / retry.max_attempts). 둘 다 비면 덮어쓰기 파일 없음

fake_box 파라미터에 start_xyz_m = [box_start_x_mm/1000, DEFAULT_START_M[1], DEFAULT_START_M[2]]
만약 gripper == "fake":
    fake_gripper Node(plan=grip_plan, close_s=float(grip_close_s)) 추가
    servo include 를 GroupAction([SetRemap("/voss/robot/gripper", "/voss/sim/gripper"), servo]) 로 감싼다
    # gateway 의 /voss/robot/gripper 는 떠 있지만 belt_servo 가 부르지 않는다
그 밖 "gateway" 가 아니면 RuntimeError
LogInfo 문구에 gripper·plan·close·max_attempts·start_x 추가
```

## 8. sim_check.py

```text
Case 필드 추가 (기본 None = 지금 동작):
    grip_plan: str | None · grip_close_s: float | None · max_attempts: int | None
    start_x_mm: float | None · kp: float | None · timeout_s: float | None

CASES 추가:
    "retry":        Case("retry", "normal", 40.5, grip_plan="empty,held", grip_close_s=1.2, max_attempts=3,
                         start_x_mm=-250.0, kp=3.0, timeout_s=60.0)
    "fail_retreat": Case("fail_retreat", "normal", 40.5, grip_plan="empty", grip_close_s=1.7,
                         max_attempts=3, timeout_s=45.0)
    "wide":         Case("wide", "normal", 40.5, grip_plan="wide", grip_close_s=1.7, max_attempts=3, timeout_s=45.0)

Expect 필드 추가: attempts: int | None = None, retreat: bool = 거짓
EXPECT (profile "grasp"):
    retry        → Expect(SUCCEEDED, "OK", "", 참, (PREPARE,TRACK,DESCEND,GRASP,PREPARE,TRACK,DESCEND,GRASP,LIFT,VERIFY), attempts=2)
    fail_retreat → Expect(ABORTED, "GRASP_FAILED", "NOT_DETECTED", 거짓, (PREPARE,TRACK,DESCEND,GRASP,LIFT), attempts=1, retreat=참)
    wide         → Expect(ABORTED, "GRASP_FAILED", "WIDTH_OUT", 거짓, (PREPARE,TRACK,DESCEND,GRASP,LIFT), attempts=1, retreat=참)
    empty (수정) → phases_last "GRASP" → "LIFT", retreat=참
PROFILE_CASES["grasp"] 끝에 "retry", "fail_retreat", "wide"

judge_result(exp, status, reason, grasped, attempts=None):
    기존 비교 + (exp.attempts 가 None 아니면 attempts == exp.attempts), want·got 에 attempts

함수 judge_retreat(terminal, lift_dz_m, tol_m):          # J-ret (순수)
    terminal 없음 → _unknown("J-ret", …)
    z = terminal["tcp_now_m"][2], top = terminal["position_base_m"][2]  (없으면 _unknown)
    ok = z ≥ top + lift_dz_m − tol_m 이고 terminal["retreat_done"] 이 참
    반환 _v("J-ret", "후퇴 끝 높이", ok, f"≥ 윗면 +{(lift−tol)×1000:.0f} mm · done", f"+{(z−top)×1000:.1f} mm · {done}")

sim_values() 에 z.lift_above_top_mm·z.height_tol_mm 추가
start_launch: case 값이 있으면 gripper:=fake grip_plan:=… grip_close_s:=… max_attempts:=… box_start_x_mm:=…,
              kp 는 args.kp 가 없을 때 case.kp
run_goal: 시간 한계 = max(case.timeout_s or 0, args.goal_timeout_s)
judge_case: judge_result 에 out.attempts · exp.retreat 이면 judge_retreat 추가
```

## 9. 시험 (DD 7절 → 파일)

| 파일 | 함수 |
|---|---|
| test_fsm.py | T1~T17 (DD 7.1) + 기존 52·59·64·69·74·79·277줄 수정. 보조: `retreat_state(reason, cause, hold_z)` |
| test_control.py | C1~C5 |
| test_log_schema.py | L1 |
| test_fake_gripper.py (새) | G1 `fake_reply`·`parse_plan` |
| test_sim_check.py | S1 새 EXPECT · J1 attempts · J-ret |
| test_action_e2e.py | DD 7.2 의 5개 실행 확인 (결과 대기 한계만 필요 시 늘림) |
