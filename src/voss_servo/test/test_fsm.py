"""fsm.py 전이 시험 (ROS 없이). 전이표 번호는 design/U1-dd.md 2절."""

import pytest
from voss_servo.fsm import FsmState, GripperReply, StopResult, TickEvent

from voss_servo import fsm

W_MIN, W_MAX = 39.5, 41.5  # 쥔 폭 범위 (measurements #8 제안값)
OPENED = GripperReply(ok=True, width_mm=90.0, grip_detected=False, message="OK")  # 개방 완료
HELD = GripperReply(ok=True, width_mm=40.2, grip_detected=True, message="OK")  # 잘 잡음
EMPTY = GripperReply(ok=True, width_mm=38.7, grip_detected=False, message="OK")  # 빈손
WIDE = GripperReply(ok=True, width_mm=45.0, grip_detected=True, message="OK")  # 감지됐지만 폭 밖


def step(state, ev=None, max_attempts=3):
    """시험용 짧은 호출."""
    return fsm.step(state, ev or TickEvent(), W_MIN, W_MAX, max_attempts)


def at(phase, attempts=0):
    """주어진 단계의 상태."""
    return FsmState(phase, attempts, False)


def _retreating(reason, cause, hold_z=False, attempts=1):
    """안전 후퇴 중 상태 (U9b)."""
    return FsmState(fsm.LIFT, attempts, False, reason, cause, hold_z)


def run_to_grasp(max_attempts=3):
    """PREPARE → TRACK → DESCEND → GRASP 까지 진행한 상태."""
    s, actions = fsm.start()
    assert s.phase == fsm.PREPARE and actions == (fsm.GRIPPER_OPEN,)
    s = step(s, TickEvent(gripper=OPENED), max_attempts).state
    s = step(s, TickEvent(aligned=True), max_attempts).state
    tr = step(s, TickEvent(at_grasp_height=True), max_attempts)
    assert tr.actions == (fsm.GRIPPER_CLOSE,)
    return tr.state


# --- 정상 흐름 ---


def test_normal_six_phases_end_ok() -> None:
    s = run_to_grasp()
    assert (s.phase, s.attempts) == (fsm.GRASP, 1)
    s = step(s, TickEvent(gripper=HELD, vision_blind=True)).state
    assert s.phase == fsm.LIFT
    tr = step(s, TickEvent(at_lift_height=True, vision_blind=True))
    assert tr.state.phase == fsm.VERIFY and tr.actions == (fsm.GRIPPER_VERIFY,)
    tr = step(tr.state, TickEvent(gripper=HELD, vision_blind=True))
    assert tr.terminal and tr.reason == fsm.OK and tr.grasped
    assert tr.state.attempts == 1


def test_close_done_without_detection_does_not_lift() -> None:
    # U9b: 재시도는 x 여유가 있을 때만 (retry_room 기본 False)
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=3)
    assert tr.state.phase == fsm.PREPARE  # LIFT 가 아니라 재시도
    assert tr.attempt_ended and tr.cause == "NOT_DETECTED"
    assert tr.actions == (fsm.GRIPPER_OPEN,)


def test_width_out_of_range_retreats_opening_first() -> None:
    # U9b r1: 폭 밖은 여유·시도가 남아도 항상 후퇴 (먼저 연다)
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=WIDE, retry_room=True), max_attempts=3)
    assert tr.state.phase == fsm.LIFT and fsm.is_retreat(tr.state) and not tr.terminal
    assert tr.state.hold_z and tr.actions == (fsm.GRIPPER_OPEN,) and tr.cause == "WIDTH_OUT"


def test_drop_in_verify_ends_without_retry() -> None:
    # U9b: 들다 놓침은 재시도 없이 바로 끝 (이미 들기 높이, 재정렬까지 x 363 mm 필요)
    tr = step(at(fsm.VERIFY, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=3)
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.GRASP_FAILED, "DROPPED")
    assert tr.actions == ()


def test_max_attempts_one_retreats_on_first_miss() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=1)
    assert not tr.terminal and fsm.is_retreat(tr.state)  # U9b: 끝내기 전에 안전 후퇴
    assert tr.state.exit_reason == fsm.GRASP_FAILED and tr.actions == ()  # 닫힌 채


def test_three_misses_retreat_then_grasp_failed() -> None:
    tr = step(at(fsm.GRASP, 3), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=3)
    assert fsm.is_retreat(tr.state) and tr.state.attempts == 3
    tr = step(tr.state, TickEvent(at_lift_height=True, vision_blind=True))
    assert tr.terminal and tr.reason == fsm.GRASP_FAILED and tr.cause == "NOT_DETECTED"
    assert tr.retreat_done and tr.state.attempts == 3


def test_max_attempts_capped_by_contract() -> None:
    tr = step(at(fsm.GRASP, 3), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=9)
    assert tr.state.exit_reason == fsm.GRASP_FAILED  # 계약 상한 3 을 넘지 않는다 → 후퇴


# --- 입력·영역 ---


def test_lost_in_track() -> None:
    tr = step(at(fsm.TRACK), TickEvent(box_lost=True))
    assert tr.terminal and tr.reason == fsm.LOST and tr.cause == "BOX_MISSING"


def test_lost_ignored_in_descend_blind_zone() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(box_lost=True, vision_blind=True))
    assert not tr.terminal


def test_lost_in_descend_above_blind_zone() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(box_lost=True, vision_blind=False))
    assert tr.reason == fsm.LOST


def test_lost_ignored_in_grasp() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(box_lost=True, box_stale=True))
    assert not tr.terminal


def test_box_invalid_is_stale_input() -> None:
    tr = step(at(fsm.TRACK), TickEvent(box_stale=True))
    assert tr.reason == fsm.STALE_INPUT and tr.cause == "BOX_INVALID"


def test_pose_missing_is_stale_even_in_blind() -> None:
    tr = step(at(fsm.LIFT, 1), TickEvent(pose_stale=True, vision_blind=True))
    assert tr.reason == fsm.STALE_INPUT and tr.cause == "POSE_MISSING"


def test_out_of_reach() -> None:
    tr = step(at(fsm.TRACK), TickEvent(reach="X_MAX"))
    assert tr.reason == fsm.OUT_OF_REACH and tr.cause == "REACH_X_MAX"


def test_gripper_comm_error_is_device_error() -> None:
    bad = GripperReply(ok=False, width_mm=0.0, grip_detected=False, message="COMM_ERROR")
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=bad))  # GRASP = 낮은 자리 → 후퇴 (U9b)
    assert tr.state.exit_reason == fsm.DEVICE_ERROR and tr.cause == "GRIPPER_COMM_ERROR"
    tr = step(at(fsm.PREPARE, 0), TickEvent(gripper=bad))  # 처음 개방 = 높은 자리 → 바로 끝
    assert tr.reason == fsm.DEVICE_ERROR and tr.cause == "GRIPPER_COMM_ERROR"


# --- 취소 ---


def test_cancel_then_stop_ok_is_canceled() -> None:
    tr = step(at(fsm.TRACK), TickEvent(cancel_requested=True))
    assert tr.state.stopping and tr.actions == (fsm.REQUEST_STOP,) and not tr.terminal
    tr = step(tr.state, TickEvent(stop_result=StopResult(fsm.STOP_OK)))
    assert tr.terminal and tr.reason == fsm.CANCELED and tr.cause == "STOP_OK"


def test_cancel_then_stop_failures_are_device_error() -> None:
    cases = {
        StopResult(fsm.STOP_FAILED, "TIMEOUT"): "STOP_FAILED_TIMEOUT",
        StopResult(fsm.STOP_TIMEOUT): "STOP_TIMEOUT",
        StopResult(fsm.STOP_UNAVAILABLE): "STOP_UNAVAILABLE",
    }
    stopping = FsmState(fsm.DESCEND, 0, True)
    for result, cause in cases.items():
        tr = step(stopping, TickEvent(stop_result=result))
        assert tr.reason == fsm.DEVICE_ERROR and tr.cause == cause


def test_stopping_ignores_other_events() -> None:
    stopping = FsmState(fsm.GRASP, 1, True)
    tr = step(stopping, TickEvent(pose_stale=True, gripper=HELD, box_lost=True))
    assert not tr.terminal and tr.state == stopping  # stop 응답만 기다린다


def test_cancel_wins_over_lost_same_tick() -> None:
    tr = step(at(fsm.TRACK), TickEvent(cancel_requested=True, box_lost=True))
    assert tr.state.stopping and not tr.terminal


# --- 비전 사각 판정 ---


def test_blind_by_height_with_hysteresis() -> None:
    top, cut = 0.100, 10.0  # 박스 윗면 z 0.100 m, cutoff 10 mm → 진입 0.110, 이탈 0.115
    assert not fsm.is_vision_blind(fsm.DESCEND, 0.111, top, cut, was_blind=False)
    assert fsm.is_vision_blind(fsm.DESCEND, 0.110, top, cut, was_blind=False)  # 진입
    assert fsm.is_vision_blind(fsm.DESCEND, 0.114, top, cut, was_blind=True)  # 아직 안 나옴
    assert not fsm.is_vision_blind(fsm.DESCEND, 0.116, top, cut, was_blind=True)  # 이탈


def test_blind_after_retry_at_grasp_height() -> None:
    # 재시도로 PREPARE 에 돌아온 직후 TCP 는 아직 파지 높이(윗면 −19 mm)
    assert fsm.is_vision_blind(fsm.PREPARE, 0.081, 0.100, 10.0, was_blind=True)


def test_blind_phases_and_unknown_height() -> None:
    assert fsm.is_vision_blind(fsm.LIFT, None, None, 10.0, was_blind=False)
    assert not fsm.is_vision_blind(fsm.TRACK, None, 0.1, 10.0, was_blind=False)  # 모르면 유지


def test_input_flags_clock_restarts_after_blind() -> None:
    # 마지막 박스 수신 t=1.0, 사각에서 t=3.0 에 나옴 → t=3.2 는 아직 LOST 아님
    lost, stale, _ = fsm.input_flags(
        3.2, 1.0, 1.0, False, 3.19, 0.0, vision_since=3.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert not lost and not stale
    lost, _, _ = fsm.input_flags(
        3.6, 1.0, 1.0, False, 3.59, 0.0, vision_since=3.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert lost  # 다시 센 시계로 0.6 s 경과


def test_input_flags_no_messages_is_lost_not_stale() -> None:
    lost, stale, pose_stale = fsm.input_flags(
        1.0, None, None, False, 0.99, 0.0, vision_since=0.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert lost and not stale and not pose_stale


def test_input_flags_invalid_stream_is_stale() -> None:
    _, stale, _ = fsm.input_flags(
        1.0, 0.99, 0.5, True, 0.99, 0.0, vision_since=0.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert stale  # 메시지는 오는데 0.5 s 째 invalid


def test_input_flags_pose_missing_from_goal_start() -> None:
    *_, pose_stale = fsm.input_flags(
        10.2, None, None, False, None, 10.0, vision_since=10.0, blind=True,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert not pose_stale  # goal 시작 0.2 s 뒤라 아직 아님


def test_input_flags_invalid_then_silence_is_lost_not_stale() -> None:
    # 마지막 valid t=0.0, 마지막 수신(invalid) t=0.1, 그 뒤 수신 끊김 → t=0.45 는 STALE 이 아니다
    lost, stale, _ = fsm.input_flags(
        0.45, 0.1, 0.0, True, 0.44, 0.0, vision_since=0.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert not stale and not lost
    lost, stale, _ = fsm.input_flags(
        0.65, 0.1, 0.0, True, 0.64, 0.0, vision_since=0.0, blind=False,
        lost_timeout=0.5, stale_timeout=0.3,
    )  # fmt: skip
    assert lost and not stale  # 끊김은 LOST 로 분류된다


# --- U5: x 여유 사전 검사 (design/U5-dd.md 2절, 전이 11b) ---


def test_aligned_without_room_ends_out_of_reach() -> None:
    tr = step(at(fsm.TRACK), TickEvent(aligned=True, grasp_room=False))
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.OUT_OF_REACH, fsm.REACH_GRASP_ROOM)
    assert tr.actions == ()  # 하강도 그리퍼도 없다


def test_aligned_with_room_descends() -> None:
    assert (
        step(at(fsm.TRACK), TickEvent(aligned=True)).state.phase == fsm.DESCEND
    )  # 기본 = 여유 있음
    tr = step(at(fsm.TRACK), TickEvent(aligned=True, grasp_room=True))
    assert tr.state.phase == fsm.DESCEND and not tr.terminal


def test_no_room_ignored_outside_track() -> None:
    # 여유 검사는 TRACK → DESCEND 들어갈 때 한 번만. 이미 내려가는 중이면 보지 않는다
    assert (
        step(at(fsm.PREPARE), TickEvent(gripper=OPENED, grasp_room=False)).state.phase == fsm.TRACK
    )
    tr = step(at(fsm.DESCEND, 0), TickEvent(at_grasp_height=True, grasp_room=False))
    assert tr.state.phase == fsm.GRASP
    assert not step(at(fsm.GRASP, 1), TickEvent(grasp_room=False)).terminal


# --- U5: 코드로 들어온 그리퍼 실패 (grip.py 가 message 를 코드로 바꿔 넘긴다) ---


@pytest.mark.parametrize("code", ["BUSY", "UNAVAILABLE", "TIMEOUT", "INVALID", "UNKNOWN"])
def test_gripper_failure_codes_are_device_error(code) -> None:
    reply = GripperReply(ok=False, width_mm=0.0, grip_detected=False, message=code)
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=reply))
    # U9b: GRASP 중 그리퍼 오류는 닫힌 채 후퇴한 뒤 DEVICE_ERROR (개방 행동 없음)
    assert (tr.state.exit_reason, tr.cause) == (fsm.DEVICE_ERROR, f"GRIPPER_{code}")
    assert tr.actions == () and not tr.state.hold_z


# --- U5: 끝나는 전이에는 행동이 없다 ("grasped=false 면 개방 없음"의 FSM 쪽 보장) ---

_TERMINAL_CASES = [
    (at(fsm.VERIFY, 1), TickEvent(gripper=HELD), 3, fsm.OK),
    (at(fsm.VERIFY, 1), TickEvent(gripper=EMPTY), 1, fsm.GRASP_FAILED),  # 떨어뜨림
    # U9b: GRASP 실패는 후퇴 끝(들기 높이 도달)에서 끝난다 — 그 끝 전이에도 행동이 없다
    (
        _retreating(fsm.GRASP_FAILED, "NOT_DETECTED"),
        TickEvent(at_lift_height=True),
        1,
        fsm.GRASP_FAILED,
    ),
    (
        _retreating(fsm.GRASP_FAILED, "WIDTH_OUT"),
        TickEvent(at_lift_height=True),
        3,
        fsm.GRASP_FAILED,
    ),
    (
        _retreating(fsm.DEVICE_ERROR, "GRIPPER_TIMEOUT"),
        TickEvent(at_lift_height=True),
        3,
        fsm.DEVICE_ERROR,
    ),
    (
        at(fsm.VERIFY, 1),
        TickEvent(gripper=GripperReply(False, 0.0, False, "TIMEOUT")),
        3,
        fsm.DEVICE_ERROR,
    ),
    (at(fsm.TRACK), TickEvent(aligned=True, grasp_room=False), 3, fsm.OUT_OF_REACH),
    (at(fsm.TRACK), TickEvent(reach="X_MAX"), 3, fsm.OUT_OF_REACH),
    (at(fsm.TRACK), TickEvent(box_lost=True), 3, fsm.LOST),
    (at(fsm.TRACK), TickEvent(box_stale=True), 3, fsm.STALE_INPUT),
    (FsmState(fsm.GRASP, 1, True), TickEvent(stop_result=StopResult(fsm.STOP_OK)), 3, fsm.CANCELED),
    (
        FsmState(fsm.GRASP, 1, True),
        TickEvent(stop_result=StopResult(fsm.STOP_FAILED, "TIMEOUT")),
        3,
        fsm.DEVICE_ERROR,
    ),
]


@pytest.mark.parametrize(("state", "ev", "max_attempts", "reason"), _TERMINAL_CASES)
def test_terminal_transitions_have_no_actions(state, ev, max_attempts, reason) -> None:
    tr = step(state, ev, max_attempts)
    assert tr.terminal and tr.reason == reason
    assert tr.actions == ()  # 끝난 뒤 개방·닫기 요청이 나갈 길이 없다


# --- U9a: cutoff 30 히스테리시스 · DESCEND 사각 체류 상한 (design/U9a-dd.md 2.3·2.4·6절) ---

CUT30 = 30.0  # 시연 cutoff (윗면 +30 mm 진입, +35 mm 이탈)


@pytest.mark.parametrize("was_blind", [False, True])
def test_cutoff30_track_band_visible(was_blind) -> None:
    # TRACK 접근 높이 띠 38~42 mm 에 x≥600 처짐 1.3 mm 가 겹쳐도(38.7) 사각이 아니다
    top = 0.100
    assert not fsm.is_vision_blind(fsm.TRACK, top + 0.0387, top, CUT30, was_blind)
    assert not fsm.is_vision_blind(fsm.TRACK, top + 0.042, top, CUT30, was_blind)


def test_cutoff30_exit_needs_above_35() -> None:
    top = 0.100
    assert fsm.is_vision_blind(fsm.PREPARE, top + 0.0349, top, CUT30, was_blind=True)  # 아직 안에
    assert not fsm.is_vision_blind(fsm.PREPARE, top + 0.0351, top, CUT30, was_blind=True)  # 나옴


def test_retry_rise_exits_above_35() -> None:
    # 재시도 PREPARE: 파지 높이(−17)에서 접근 높이(+40)로 1 mm 씩 올라가며 사각이 언제 풀리나
    top, blind, exit_mm = 0.100, True, None
    for mm in range(-17, 41):
        blind = fsm.is_vision_blind(fsm.PREPARE, top + mm / 1000.0, top, CUT30, blind)
        if not blind and exit_mm is None:
            exit_mm = mm  # 처음 사각에서 나온 높이
    assert exit_mm == 36  # +35 초과에서 처음 풀린다 (정수 mm 걸음)
    assert not blind  # 접근 높이에서는 보인다


def test_blind_since_starts_in_descend_blind() -> None:
    assert fsm.blind_since_next(None, fsm.DESCEND, True, 5.0) == 5.0


def test_blind_since_keeps_first_time() -> None:
    assert fsm.blind_since_next(5.0, fsm.DESCEND, True, 6.0) == 5.0


@pytest.mark.parametrize(
    "phase, blind",
    [(fsm.DESCEND, False), (fsm.GRASP, True), (fsm.TRACK, True), (fsm.PREPARE, True)],
)
def test_blind_since_clears_when_visible_or_other_phase(phase, blind) -> None:
    assert fsm.blind_since_next(5.0, phase, blind, 6.0) is None


def test_blind_since_retry_sequence() -> None:
    # DESCEND 사각 → GRASP → 재시도 PREPARE(사각) → 다시 DESCEND 사각: 두 번째는 새 시각
    s = fsm.blind_since_next(None, fsm.DESCEND, True, 1.0)
    s = fsm.blind_since_next(s, fsm.GRASP, True, 3.0)
    assert s is None
    s = fsm.blind_since_next(s, fsm.PREPARE, True, 5.0)
    assert s is None
    assert fsm.blind_since_next(s, fsm.DESCEND, True, 9.0) == 9.0


def test_blind_overstay_boundary() -> None:
    limit, dt = 3.44, 1.0 / 30.0
    assert not fsm.blind_overstay(10.0, 10.0 + limit, limit)  # 같으면 아직 아님
    assert not fsm.blind_overstay(10.0, 10.0 + limit - dt, limit)  # 1틱 전
    assert fsm.blind_overstay(10.0, 10.0 + limit + dt, limit)  # 1틱 뒤
    assert not fsm.blind_overstay(None, 99.0, limit)  # 사각 아님
    assert not fsm.blind_overstay(10.0, 99.0, None)  # 상한 모름 (방어)


def test_step_descend_overstay_device_error() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(vision_blind=True, blind_overstay=True))
    assert tr.terminal and tr.reason == fsm.DEVICE_ERROR and tr.cause == fsm.DESCEND_BLIND_TIMEOUT


@pytest.mark.parametrize("phase", [fsm.TRACK, fsm.GRASP, fsm.LIFT])
def test_step_overstay_ignored_outside_descend(phase) -> None:
    tr = step(at(phase, attempts=1), TickEvent(vision_blind=True, blind_overstay=True))
    assert not tr.terminal


def test_step_overstay_pose_stale_first() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(pose_stale=True, blind_overstay=True))
    assert tr.reason == fsm.STALE_INPUT and tr.cause == "POSE_MISSING"


def test_step_overstay_reach_first() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(reach="X_MAX", blind_overstay=True))
    assert tr.reason == fsm.OUT_OF_REACH and tr.cause == "REACH_X_MAX"


def test_step_overstay_cancel_first() -> None:
    tr = step(at(fsm.DESCEND), TickEvent(cancel_requested=True, blind_overstay=True))
    assert tr.state.stopping and not tr.terminal


def test_step_overstay_wins_over_grasp_height_same_tick() -> None:
    # 같은 틱에 파지 높이 도달과 겹치면 시간 초과가 이긴다 (보수적, U9a-dd 2.4)
    tr = step(at(fsm.DESCEND), TickEvent(at_grasp_height=True, blind_overstay=True))
    assert tr.terminal and tr.cause == fsm.DESCEND_BLIND_TIMEOUT


# --- U9b: 재시도 여유 · 안전 후퇴 (design/U9b-dd.md 7.1) ---

TIMEOUT_REPLY = GripperReply(ok=False, width_mm=0.0, grip_detected=False, message="TIMEOUT")


def test_u9b_t1_retry_when_room() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=3)
    assert tr.state.phase == fsm.PREPARE and tr.attempt_ended and tr.retry_room_ok is True
    assert tr.actions == (fsm.GRIPPER_OPEN,) and not fsm.is_retreat(tr.state)


def test_u9b_t2_no_room_retreats_closed() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY, retry_room=False), max_attempts=3)
    assert not tr.terminal and not tr.attempt_ended
    assert (tr.state.phase, tr.state.exit_reason, tr.state.exit_cause) == (
        fsm.LIFT,
        fsm.GRASP_FAILED,
        "NOT_DETECTED",
    )
    assert tr.actions == () and not tr.state.hold_z and tr.retry_room_ok is False


def test_u9b_t3_attempts_used_retreats_even_with_room() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=1)
    assert fsm.is_retreat(tr.state) and tr.retry_room_ok is True  # 여유는 있었지만 시도 다 씀


def test_u9b_t4_dropped_ends_immediately() -> None:
    tr = step(at(fsm.VERIFY, 1), TickEvent(gripper=EMPTY, retry_room=True), max_attempts=3)
    assert tr.terminal and tr.cause == "DROPPED" and not tr.retreat_done


def test_u9b_t5_width_out_opens_then_rises_then_ends() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=WIDE, retry_room=True), max_attempts=3)
    assert tr.state.hold_z and tr.actions == (fsm.GRIPPER_OPEN,)
    tr = step(tr.state, TickEvent(vision_blind=True))  # 개방 기다림: 그대로
    assert tr.state.hold_z and not tr.terminal
    tr = step(tr.state, TickEvent(gripper=OPENED, vision_blind=True))  # 개방 응답
    assert not tr.state.hold_z and fsm.is_retreat(tr.state) and not tr.terminal
    tr = step(tr.state, TickEvent(at_lift_height=True, vision_blind=True))
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.GRASP_FAILED, "WIDTH_OUT")
    assert tr.retreat_done and not tr.grasped and tr.actions == ()


def test_u9b_t6_hold_expired_rises_without_reply() -> None:
    s = _retreating(fsm.GRASP_FAILED, "WIDTH_OUT", hold_z=True)
    tr = step(s, TickEvent(hold_expired=True, vision_blind=True))
    assert not tr.state.hold_z and tr.state.exit_reason == fsm.GRASP_FAILED  # exit 그대로
    # 상승 중 늦게 온 개방 OK 는 무시된다 (판정을 보지 않음)
    tr = step(tr.state, TickEvent(gripper=OPENED, vision_blind=True))
    assert fsm.is_retreat(tr.state) and not tr.terminal


def test_u9b_t7_grasp_close_error_retreats_then_device_error() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=TIMEOUT_REPLY))
    assert fsm.is_retreat(tr.state) and tr.state.exit_reason == fsm.DEVICE_ERROR
    tr = step(tr.state, TickEvent(at_lift_height=True, vision_blind=True))
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.DEVICE_ERROR, "GRIPPER_TIMEOUT")


def test_u9b_t8_open_no_reply_during_retreat_overrides_exit() -> None:
    s = _retreating(fsm.GRASP_FAILED, "WIDTH_OUT", hold_z=True)
    tr = step(s, TickEvent(gripper=TIMEOUT_REPLY, vision_blind=True))
    assert not tr.state.hold_z and not tr.terminal  # 닫힌 채 바로 상승
    assert (tr.state.exit_reason, tr.state.exit_cause) == (fsm.DEVICE_ERROR, "GRIPPER_TIMEOUT")


def test_u9b_t9_first_prepare_gripper_error_ends() -> None:
    tr = step(at(fsm.PREPARE, 0), TickEvent(gripper=TIMEOUT_REPLY))
    assert tr.terminal and tr.reason == fsm.DEVICE_ERROR  # 관측 자세 높이 = 위험 없음


def test_u9b_t10_retry_prepare_gripper_error_retreats() -> None:
    tr = step(at(fsm.PREPARE, 1), TickEvent(gripper=TIMEOUT_REPLY))
    assert fsm.is_retreat(tr.state) and tr.state.exit_reason == fsm.DEVICE_ERROR


def test_u9b_t11_cancel_during_retreat() -> None:
    s = _retreating(fsm.GRASP_FAILED, "NOT_DETECTED")
    tr = step(s, TickEvent(cancel_requested=True))
    assert tr.state.stopping and tr.actions == (fsm.REQUEST_STOP,)
    tr = step(tr.state, TickEvent(stop_result=StopResult(fsm.STOP_OK), at_lift_height=True))
    assert tr.terminal and tr.reason == fsm.CANCELED and not tr.retreat_done


def test_u9b_t12_pose_stale_during_retreat() -> None:
    tr = step(_retreating(fsm.GRASP_FAILED, "NOT_DETECTED"), TickEvent(pose_stale=True))
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.STALE_INPUT, "POSE_MISSING")


def test_u9b_t13_overstay_only_for_retreat() -> None:
    tr = step(_retreating(fsm.GRASP_FAILED, "NOT_DETECTED"), TickEvent(lift_overstay=True))
    assert tr.terminal and (tr.reason, tr.cause) == (fsm.DEVICE_ERROR, fsm.RETREAT_TIMEOUT)
    tr = step(at(fsm.LIFT, 1), TickEvent(lift_overstay=True, vision_blind=True))
    assert (
        not tr.terminal and tr.state.phase == fsm.LIFT
    )  # 정상 들기(박스 쥔 채)는 끊지 않는다 (r1)


def test_u9b_t14_retreat_not_cut_by_x_end() -> None:
    tr = step(_retreating(fsm.GRASP_FAILED, "NOT_DETECTED"), TickEvent(reach="X_MAX"))
    assert not tr.terminal and fsm.is_retreat(tr.state)


def test_u9b_t15_lost_during_retry_prepare() -> None:
    tr = step(at(fsm.PREPARE, 1), TickEvent(box_lost=True, vision_blind=False))
    assert tr.terminal and tr.reason == fsm.LOST


def test_u9b_t16_lift_since_and_overstay_edges() -> None:
    lift, held = at(fsm.LIFT, 1), _retreating(fsm.GRASP_FAILED, "WIDTH_OUT", hold_z=True)
    assert fsm.lift_since_next(None, lift, 5.0) == 5.0  # 상승 시작
    assert fsm.lift_since_next(5.0, lift, 6.0) == 5.0  # 처음 시각 유지
    assert fsm.lift_since_next(5.0, held, 6.0) is None  # 개방 기다림은 세지 않는다
    assert fsm.lift_since_next(5.0, at(fsm.VERIFY, 1), 6.0) is None
    assert not fsm.lift_overstay(5.0, 8.79, 3.79)  # 같으면 아직
    assert fsm.lift_overstay(5.0, 8.80, 3.79)
    assert not fsm.lift_overstay(None, 99.0, 3.79) and not fsm.lift_overstay(5.0, 99.0, None)


def test_u9b_t17_default_event_has_no_retry_room() -> None:
    assert TickEvent().retry_room is False  # 모르면 재시도하지 않는다
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY), max_attempts=3)
    assert fsm.is_retreat(tr.state)


def test_u9b_retreat_never_leaks_into_verify() -> None:
    tr = step(_retreating(fsm.GRASP_FAILED, "NOT_DETECTED"), TickEvent(at_lift_height=True))
    assert tr.terminal and tr.state.phase == fsm.LIFT and fsm.GRIPPER_VERIFY not in tr.actions


def test_u9b_is_low() -> None:
    assert fsm.is_low(at(fsm.GRASP, 1)) and fsm.is_low(at(fsm.PREPARE, 1))
    assert fsm.is_low(_retreating(fsm.GRASP_FAILED, "NOT_DETECTED"))
    assert not fsm.is_low(at(fsm.PREPARE, 0)) and not fsm.is_low(at(fsm.VERIFY, 1))
    assert not fsm.is_low(at(fsm.LIFT, 1))  # 박스 쥔 정상 들기
