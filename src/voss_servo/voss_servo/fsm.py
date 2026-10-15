"""belt_servo 픽업 단계 상태기계 (순수 모듈 — ROS 를 import 하지 않는다).

- phase 이름·reason 7종·grasped 의미: src/voss_msgs/action/TrackAndGrasp.action, docs/interfaces/voss_msgs.md
- GRASP → LIFT = 닫힘 완료 응답 + grip_detected + 보고폭 범위. 닫힘만으로는 LIFT 하지 않는다.
- 비전 사각 구간: 카메라가 공구축 옆이라 낮은 높이·GRASP·LIFT·VERIFY 에서는 박스가 안 보인다.
- 설계: src/voss_servo/design/U1-dd.md 2절 (전이표 1~17), U5-dd.md 2절 (11b x 여유),
  U9a-dd.md 2.4 (9b 사각 체류 상한), U9b-dd.md 2절 (안전 후퇴·9c 후퇴 체류 상한).
- 안전 후퇴(U9b): 실패로 끝날 때 파지 높이(핑거 끝이 벨트 위 약 8 mm)에 멈추지 않고 들기 높이까지 올라간 뒤
  결과를 보낸다. 후퇴는 phase LIFT + exit_reason 으로 나타낸다(계약 phase 6종 안).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from voss_servo.params import BLIND_EXIT_MARGIN_MM, MAX_ATTEMPTS

# --- phase 이름 (TrackAndGrasp feedback.phase) ---
PREPARE = "PREPARE"
TRACK = "TRACK"
DESCEND = "DESCEND"
GRASP = "GRASP"
LIFT = "LIFT"
VERIFY = "VERIFY"
VISION_PHASES = (PREPARE, TRACK, DESCEND)  # 박스를 봐야 하는 단계
BLIND_PHASES = (GRASP, LIFT, VERIFY)  # 높이와 무관하게 박스가 안 보이는 단계
REACH_PHASES = (PREPARE, TRACK, DESCEND, GRASP)  # 추종 구간 끝을 보는 단계

# --- reason (TrackAndGrasp result.reason, 계약 7종) ---
OK = "OK"
GRASP_FAILED = "GRASP_FAILED"
LOST = "LOST"
OUT_OF_REACH = "OUT_OF_REACH"
STALE_INPUT = "STALE_INPUT"
DEVICE_ERROR = "DEVICE_ERROR"
CANCELED = "CANCELED"

# --- cause (로그용 세부 원인) ---
REACH_GRASP_ROOM = "REACH_GRASP_ROOM"  # 정렬됐지만 하강·닫힘 동안 x 끝에 닿는다 (U5 HLD D6)
# DESCEND 사각이 상한보다 오래 감 = 로봇이 안 내려감 (U9a-dd 2.4)
DESCEND_BLIND_TIMEOUT = "DESCEND_BLIND_TIMEOUT"
# 안전 후퇴 상승이 상한보다 오래 감 = 로봇이 안 올라감 (U9b-dd 2.4 9c)
RETREAT_TIMEOUT = "RETREAT_TIMEOUT"

# --- 노드에게 시키는 행동 ---
GRIPPER_OPEN = "GRIPPER_OPEN"
GRIPPER_CLOSE = "GRIPPER_CLOSE"
GRIPPER_VERIFY = "GRIPPER_VERIFY"
REQUEST_STOP = "REQUEST_STOP"

# --- 그리퍼 판정 ---
HELD = "HELD"
NOT_HELD = "NOT_HELD"

# --- stop 결과 상태 ---
STOP_OK = "OK"
STOP_FAILED = "FAILED"
STOP_TIMEOUT = "TIMEOUT"
STOP_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class FsmState:
    """픽업 상태 한 장."""

    phase: str  # 지금 단계
    attempts: int  # GRASP 에 들어간 횟수 (파지 시도 수)
    stopping: bool  # 취소 후 stop 응답을 기다리는 중
    # --- 안전 후퇴 (U9b-dd 2.1). 기본값 = 후퇴 아님 ---
    exit_reason: str | None = None  # 후퇴 중이면 끝에 보낼 reason (GRASP_FAILED | DEVICE_ERROR)
    exit_cause: str = ""  # 그때의 cause (후퇴가 끝나는 틱까지 기억한다)
    hold_z: bool = False  # 개방 응답 전까지 높이 유지 (폭 밖 후퇴)


@dataclass(frozen=True)
class GripperReply:
    """voss_msgs/srv/Gripper 응답에서 판정에 쓰는 값."""

    ok: bool
    width_mm: float  # RG2 보고 폭
    grip_detected: bool  # RG2 물체 감지 비트
    message: str  # OK | TIMEOUT | INVALID | BUSY | COMM_ERROR


@dataclass(frozen=True)
class StopResult:
    """/voss/robot/stop 호출 결과."""

    status: str  # STOP_OK | STOP_FAILED | STOP_TIMEOUT | STOP_UNAVAILABLE
    message: str = ""  # gateway 가 준 message (TIMEOUT·DEVICE_ERROR 등)


@dataclass(frozen=True)
class TickEvent:
    """노드가 매 틱 모아서 넘기는 사실들. 기본값 = 아무 일도 없음."""

    cancel_requested: bool = False
    stop_result: StopResult | None = None  # 아직 응답 없음 = None
    box_lost: bool = False
    box_stale: bool = False
    pose_stale: bool = False
    vision_blind: bool = False
    reach: str | None = None  # None | "X_MIN" | "X_MAX" | "Z_MIN" (U2)
    aligned: bool = False  # U2 가 채움
    at_grasp_height: bool = False  # U2 가 채움
    at_lift_height: bool = False  # U2 가 채움
    gripper: GripperReply | None = None  # 지금 기다리던 호출의 응답 (U5, message = 코드)
    grasp_room: bool = True  # 정렬 순간 하강·닫힘을 끝낼 x 여유가 있나 (U5). 기본 = 있음
    blind_overstay: bool = False  # DESCEND 사각이 상한을 넘었나 (U9a). 기본 = 아니오
    # 재시도 1회(재상승+하강+닫힘)를 끝낼 x 여유 (U9b). 기본 = 없음 — 모르면 재시도하지 않는다(안전 쪽)
    retry_room: bool = False
    hold_expired: bool = False  # 개방 대기가 상한을 넘었거나 TCP x 가 x_max 에 닿았나 (U9b)
    lift_overstay: bool = False  # LIFT 상승 체류가 상한을 넘었나 (U9b)
    rot_ready: bool = True  # J6 회전이 끝났거나 안 돌리나 (S2-T18). 기본 = 회전 없음과 같다


@dataclass(frozen=True)
class Transition:
    """step() 의 결과."""

    state: FsmState
    terminal: bool = False  # goal 끝
    reason: str | None = None  # 끝일 때만
    cause: str = ""  # 로그용 세부 원인
    grasped: bool = False
    actions: tuple[str, ...] = ()
    attempt_ended: bool = False  # 재시도로 이어지는 시도 끝
    retry_room_ok: bool | None = (
        None  # GRASP 실패를 판단한 틱에만: 재시도 x 여유가 있었나 (로그용, U9b)
    )
    retreat_done: bool = False  # 후퇴가 들기 높이 도달로 끝난 틱 (로그용, U9b)


def start() -> tuple[FsmState, tuple[str, ...]]:
    """goal 시작 상태와 첫 행동(사전 개방)."""
    return FsmState(PREPARE, 0, False), (GRIPPER_OPEN,)


def judge_grip(reply: GripperReply, w_min: float, w_max: float) -> tuple[str, str]:
    """그리퍼 응답 → (HELD | NOT_HELD | DEVICE_ERROR, cause)."""
    if not reply.ok:
        # message 가 OK 인데 ok 가 거짓이면 이유를 따로 표시한다
        cause = "GRIPPER_NOT_OK" if reply.message == "OK" else f"GRIPPER_{reply.message}"
        return DEVICE_ERROR, cause
    if reply.message != "OK":
        return DEVICE_ERROR, f"GRIPPER_{reply.message}"  # ok 인데 message 가 이상한 경우
    if not reply.grip_detected:
        return NOT_HELD, "NOT_DETECTED"  # 닫혔지만 물체 감지 없음
    if not (w_min <= reply.width_mm <= w_max):
        return NOT_HELD, "WIDTH_OUT"  # 감지는 됐지만 폭이 쥔 폭 범위 밖
    return HELD, ""


def is_vision_blind(
    phase: str,
    tcp_z_m: float | None,
    box_top_z_m: float | None,
    cutoff_mm: float,
    was_blind: bool,
) -> bool:
    """지금 박스가 카메라에 안 보이는 구간인가 (높이 기준 + 히스테리시스)."""
    if phase in BLIND_PHASES:
        return True  # 닫힘·들기·확인 중에는 항상 안 보인다
    if tcp_z_m is None or box_top_z_m is None:
        return was_blind  # 높이를 모르면 바꾸지 않는다
    enter_z = box_top_z_m + cutoff_mm / 1000.0  # 이 아래로 내려가면 사각
    exit_z = enter_z + BLIND_EXIT_MARGIN_MM / 1000.0  # 이 위로 올라가야 사각에서 나옴
    if was_blind:
        return tcp_z_m <= exit_z
    return tcp_z_m <= enter_z


def blind_since_next(prev: float | None, phase: str, blind: bool, now: float) -> float | None:
    """DESCEND 안에서 사각이 시작된 시각을 이어 간다. DESCEND 사각이 아니면 None (U9a-dd 2.3)."""
    if phase != DESCEND or not blind:
        return None  # 지운다 — GRASP·재시도 PREPARE 를 지나 다시 DESCEND 에 오면 새로 센다
    if prev is None:
        return now  # 이번 틱에 DESCEND 사각이 시작됐다
    return prev  # 계속 사각: 처음 시각 유지


def blind_overstay(blind_since: float | None, now: float, limit_s: float | None) -> bool:
    """DESCEND 사각 체류가 상한을 넘었나. 같으면 아직 아니다."""
    if blind_since is None or limit_s is None:
        return False  # 사각 아님 · 상한 모름 (READY 가 아니면 goal 이 없다 — 방어)
    return now - blind_since > limit_s


def is_retreat(state: FsmState) -> bool:
    """지금 안전 후퇴 중인가 = LIFT 인데 끝에 보낼 reason 이 정해져 있다 (U9b)."""
    return state.phase == LIFT and state.exit_reason is not None


def is_low(state: FsmState) -> bool:
    """그리퍼 오류 때 그 자리에 멈추면 위험한가 = 파지 높이 근처 (U9b-dd 2.2)."""
    if state.phase == GRASP:
        return True  # 핑거 끝이 벨트 위 약 8 mm
    if state.phase == PREPARE and state.attempts >= 1:
        return True  # 재시도로 파지 높이에서 올라가는 중
    return is_retreat(state)  # 후퇴 중 (아직 낮을 수 있다)


def lift_since_next(prev: float | None, state: FsmState, now: float) -> float | None:
    """LIFT 상승이 시작된 시각을 이어 간다. 상승 중이 아니면 None (blind_since_next 와 같은 꼴)."""
    if state.phase != LIFT or state.hold_z:
        return None  # 들기 아님 · 개방 기다리는 중 (아직 안 올라간다)
    if prev is None:
        return now  # 이번 틱에 상승 시작
    return prev  # 계속 상승 중: 처음 시각 유지


def lift_overstay(lift_since: float | None, now: float, limit_s: float | None) -> bool:
    """LIFT 상승 체류가 상한을 넘었나. 같으면 아직 아니다."""
    if lift_since is None or limit_s is None:
        return False  # 상승 중 아님 · 상한 모름
    return now - lift_since > limit_s


def _ref(t: float | None, since: float) -> float:
    """시계 기준 시각 = 마지막 수신과 구간 시작 중 늦은 쪽."""
    return since if t is None else max(t, since)


def input_flags(
    now: float,
    last_box_rx: float | None,
    last_valid_rx: float | None,
    latest_invalid: bool,
    last_pose_rx: float | None,
    goal_start: float,
    vision_since: float,
    blind: bool,
    lost_timeout: float,
    stale_timeout: float,
) -> tuple[bool, bool, bool]:
    """입력 끊김 판정 → (box_lost, box_stale, pose_stale). 모두 수신 시각 기준(MC-031)."""
    pose_stale = now - _ref(last_pose_rx, goal_start) > stale_timeout  # pose 는 사각과 무관
    if blind:
        return False, False, pose_stale  # 사각 구간에서는 박스가 안 보이는 게 정상
    box_lost = now - _ref(last_box_rx, vision_since) > lost_timeout  # 내 트랙이 안 옴
    valid_late = now - _ref(last_valid_rx, vision_since) > stale_timeout
    receiving = now - _ref(last_box_rx, vision_since) <= stale_timeout  # 메시지가 아직 오는 중
    # 메시지는 오는데 계속 invalid 일 때만 STALE. 수신이 끊긴 것은 LOST 로 간다
    box_stale = latest_invalid and valid_late and receiving
    return box_lost, box_stale, pose_stale


def _end(state: FsmState, reason: str, cause: str, grasped: bool = False) -> Transition:
    """goal 끝 Transition."""
    return Transition(state=state, terminal=True, reason=reason, cause=cause, grasped=grasped)


def _stop_outcome(state: FsmState, result: StopResult | None) -> Transition:
    """stopping 중: stop 응답에 따라 끝내거나 기다린다 (전이표 1~3)."""
    if result is None:
        return Transition(state=state)  # 응답 대기, 다른 이벤트는 보지 않는다
    if result.status == STOP_OK:
        return _end(state, CANCELED, "STOP_OK")
    if result.status == STOP_FAILED:
        return _end(state, DEVICE_ERROR, f"STOP_FAILED_{result.message or 'UNKNOWN'}")
    return _end(state, DEVICE_ERROR, f"STOP_{result.status}")  # TIMEOUT·UNAVAILABLE


def _retreat(
    state: FsmState, reason: str, cause: str, open_first: bool, room_ok: bool | None = None
) -> Transition:
    """안전 후퇴 시작 (goal 끝이 아니다). 폭 밖이면 먼저 연다 (U9b-dd 2.2)."""
    nxt = replace(state, phase=LIFT, exit_reason=reason, exit_cause=cause, hold_z=open_first)
    actions = (GRIPPER_OPEN,) if open_first else ()  # 끼인 것을 풀고 올라간다
    return Transition(state=nxt, cause=cause, actions=actions, retry_room_ok=room_ok)


def _not_held(state: FsmState, cause: str, max_attempts: int, ev: TickEvent) -> Transition:
    """파지 실패: 들다 놓침은 끝, 폭 밖은 후퇴, 여유 있으면 재시도, 아니면 후퇴 (U9b-dd 2.3)."""
    if state.phase == VERIFY:
        # 이미 들기 높이 — 재정렬까지 x 363 mm 가 필요해 재시도 불가 (U9b-hld 1.2)
        return _end(state, GRASP_FAILED, cause)
    if cause == "WIDTH_OUT":
        # 무언가 끼었다 → 먼저 열고 후퇴. 재시도하려면 실패 x ≤ 115 mm 라 분기를 두지 않는다 (r1)
        return _retreat(state, GRASP_FAILED, cause, open_first=True, room_ok=ev.retry_room)
    limit = min(max_attempts, MAX_ATTEMPTS)  # 계약 상한 3 을 넘지 않는다
    if state.attempts < limit and ev.retry_room:
        nxt = replace(state, phase=PREPARE)  # 다시 벌리고 대기 높이로
        return Transition(
            state=nxt,
            cause=cause,
            actions=(GRIPPER_OPEN,),
            attempt_ended=True,
            retry_room_ok=True,
        )
    # 시도를 다 썼거나 x 여유가 없다 → 닫힌 채 들기 높이로 후퇴한 뒤 GRASP_FAILED
    return _retreat(state, GRASP_FAILED, cause, open_first=False, room_ok=ev.retry_room)


def step(
    state: FsmState, ev: TickEvent, w_min: float, w_max: float, max_attempts: int
) -> Transition:
    """한 틱의 전이. 전이표 위에서부터 처음 맞는 한 줄만 적용한다."""
    # 1~3: 취소 후 stop 응답 대기
    if state.stopping:
        return _stop_outcome(state, ev.stop_result)
    # 4: 취소
    if ev.cancel_requested:
        return Transition(state=replace(state, stopping=True), actions=(REQUEST_STOP,))
    # 5: 그리퍼 통신 실패 — 낮은 자리면 닫힌 채 후퇴한 뒤 DEVICE_ERROR (U9b-dd 2.4)
    verdict, grip_cause = (None, "")
    if ev.gripper is not None:
        verdict, grip_cause = judge_grip(ev.gripper, w_min, w_max)
        if verdict == DEVICE_ERROR:
            if is_low(state):  # 후퇴 중이었으면 exit 를 덮고 개방 대기를 풀어 바로 올라간다
                return _retreat(state, DEVICE_ERROR, grip_cause, open_first=False)
            return _end(state, DEVICE_ERROR, grip_cause)
    # 6~9: 입력·영역
    if ev.pose_stale:
        return _end(state, STALE_INPUT, "POSE_MISSING")
    if state.phase in VISION_PHASES and not ev.vision_blind:
        if ev.box_stale:
            return _end(state, STALE_INPUT, "BOX_INVALID")
        if ev.box_lost:
            return _end(state, LOST, "BOX_MISSING")
    if state.phase in REACH_PHASES and ev.reach is not None:
        return _end(state, OUT_OF_REACH, f"REACH_{ev.reach}")
    # 9b: 사각에서 로봇이 예상보다 오래 안 내려온다 → 로봇·gateway 이상 (U9a-dd 2.4)
    if state.phase == DESCEND and ev.blind_overstay:
        return _end(state, DEVICE_ERROR, DESCEND_BLIND_TIMEOUT)
    # 9c: 후퇴 상승이 예상보다 오래 걸린다 → 로봇 이상 (U9b). 정상 LIFT 는 노드가 경고만 (r1)
    if is_retreat(state) and ev.lift_overstay:
        return _end(state, DEVICE_ERROR, RETREAT_TIMEOUT)
    # 10~17: 정상 진행
    return _advance(state, ev, verdict, grip_cause, max_attempts)


def _advance(
    state: FsmState, ev: TickEvent, verdict: str | None, grip_cause: str, max_attempts: int
) -> Transition:
    """정상 진행 전이 (전이표 10~17)."""
    phase = state.phase
    if phase == PREPARE and ev.gripper is not None:
        return Transition(state=replace(state, phase=TRACK))  # 개방 완료 (실패는 5번에서 끝남)
    if phase == TRACK and ev.aligned and ev.rot_ready:  # 회전 중이면 정렬돼도 기다린다 (S2-T18)
        if not ev.grasp_room:  # 내려가 닫는 동안 x 끝에 닿는다 → 들어가지 않는다 (11b)
            return _end(state, OUT_OF_REACH, REACH_GRASP_ROOM)
        return Transition(state=replace(state, phase=DESCEND))
    if phase == DESCEND and ev.at_grasp_height:
        nxt = replace(state, phase=GRASP, attempts=state.attempts + 1)  # 시도 1회 시작
        return Transition(state=nxt, actions=(GRIPPER_CLOSE,))
    if phase == GRASP and verdict == HELD:
        return Transition(state=replace(state, phase=LIFT))
    if is_retreat(state):  # 안전 후퇴 진행 — "LIFT → VERIFY" 줄보다 먼저 본다 (VERIFY 로 새지 않게)
        return _advance_retreat(state, ev)
    if phase == LIFT and ev.at_lift_height:
        return Transition(state=replace(state, phase=VERIFY), actions=(GRIPPER_VERIFY,))
    if phase == VERIFY and verdict == HELD:
        return _end(state, OK, "", grasped=True)  # 들고 확인까지 끝 = 인계
    if phase in (GRASP, VERIFY) and verdict == NOT_HELD:
        cause = "DROPPED" if phase == VERIFY else grip_cause  # 들다 놓침 vs 못 잡음
        return _not_held(state, cause, max_attempts, ev)
    return Transition(state=state)  # 변화 없음


def _advance_retreat(state: FsmState, ev: TickEvent) -> Transition:
    """안전 후퇴 한 틱: 개방 기다림 → 상승 → 들기 높이에서 끝 (U9b-dd 2.4)."""
    if state.hold_z:
        # 개방 응답(판정은 안 본다)이 왔거나, 기다림 상한·x 끝 → 열렸든 아니든 올라간다 (r1)
        if ev.gripper is not None or ev.hold_expired:
            return Transition(state=replace(state, hold_z=False))
        return Transition(state=state)  # 개방 기다림 (z 유지, xy 는 박스를 따라감)
    if ev.at_lift_height:
        reason = state.exit_reason or GRASP_FAILED  # is_retreat 이면 None 이 아니다 (타입 방어)
        return replace(_end(state, reason, state.exit_cause), retreat_done=True)
    return Transition(state=state)  # 올라가는 중
