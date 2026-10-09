"""belt_servo 픽업 단계 상태기계 (순수 모듈 — ROS 를 import 하지 않는다).

- phase 이름·reason 7종·grasped 의미: src/voss_msgs/action/TrackAndGrasp.action, docs/interfaces/voss_msgs.md
- GRASP → LIFT = 닫힘 완료 응답 + grip_detected + 보고폭 범위. 닫힘만으로는 LIFT 하지 않는다.
- 비전 사각 구간: 카메라가 공구축 옆이라 낮은 높이·GRASP·LIFT·VERIFY 에서는 박스가 안 보인다.
- 설계: src/voss_servo/design/U1-dd.md 2절 (전이표 1~17), U5-dd.md 2절 (11b x 여유).
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


def _not_held(state: FsmState, cause: str, max_attempts: int) -> Transition:
    """파지 실패: 남은 시도가 있으면 재시도, 없으면 GRASP_FAILED (전이표 14·15)."""
    limit = min(max_attempts, MAX_ATTEMPTS)  # 계약 상한 3 을 넘지 않는다
    if state.attempts < limit:
        nxt = replace(state, phase=PREPARE)  # 다시 벌리고 대기 높이로
        return Transition(state=nxt, cause=cause, actions=(GRIPPER_OPEN,), attempt_ended=True)
    return _end(state, GRASP_FAILED, cause)


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
    # 5: 그리퍼 통신 실패
    verdict, grip_cause = (None, "")
    if ev.gripper is not None:
        verdict, grip_cause = judge_grip(ev.gripper, w_min, w_max)
        if verdict == DEVICE_ERROR:
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
    # 10~17: 정상 진행
    return _advance(state, ev, verdict, grip_cause, max_attempts)


def _advance(
    state: FsmState, ev: TickEvent, verdict: str | None, grip_cause: str, max_attempts: int
) -> Transition:
    """정상 진행 전이 (전이표 10~17)."""
    phase = state.phase
    if phase == PREPARE and ev.gripper is not None:
        return Transition(state=replace(state, phase=TRACK))  # 개방 완료 (실패는 5번에서 끝남)
    if phase == TRACK and ev.aligned:
        if not ev.grasp_room:  # 내려가 닫는 동안 x 끝에 닿는다 → 들어가지 않는다 (11b)
            return _end(state, OUT_OF_REACH, REACH_GRASP_ROOM)
        return Transition(state=replace(state, phase=DESCEND))
    if phase == DESCEND and ev.at_grasp_height:
        nxt = replace(state, phase=GRASP, attempts=state.attempts + 1)  # 시도 1회 시작
        return Transition(state=nxt, actions=(GRIPPER_CLOSE,))
    if phase == GRASP and verdict == HELD:
        return Transition(state=replace(state, phase=LIFT))
    if phase == LIFT and ev.at_lift_height:
        return Transition(state=replace(state, phase=VERIFY), actions=(GRIPPER_VERIFY,))
    if phase == VERIFY and verdict == HELD:
        return _end(state, OK, "", grasped=True)  # 들고 확인까지 끝 = 인계
    if phase in (GRASP, VERIFY) and verdict == NOT_HELD:
        cause = "DROPPED" if phase == VERIFY else grip_cause  # 들다 놓침 vs 못 잡음
        return _not_held(state, cause, max_attempts)
    return Transition(state=state)  # 변화 없음
