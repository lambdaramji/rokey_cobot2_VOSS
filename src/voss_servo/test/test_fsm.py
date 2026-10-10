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
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY), max_attempts=3)
    assert tr.state.phase == fsm.PREPARE  # LIFT 가 아니라 재시도
    assert tr.attempt_ended and tr.cause == "NOT_DETECTED"
    assert tr.actions == (fsm.GRIPPER_OPEN,)


def test_width_out_of_range_retries() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=WIDE), max_attempts=3)
    assert tr.state.phase == fsm.PREPARE and tr.cause == "WIDTH_OUT"


def test_drop_in_verify_retries() -> None:
    tr = step(at(fsm.VERIFY, 1), TickEvent(gripper=EMPTY), max_attempts=3)
    assert tr.state.phase == fsm.PREPARE and tr.cause == "DROPPED"


def test_max_attempts_one_fails_on_first_miss() -> None:
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=EMPTY), max_attempts=1)
    assert tr.terminal and tr.reason == fsm.GRASP_FAILED  # U9 전 기본값 1


def test_three_misses_end_grasp_failed() -> None:
    tr = step(at(fsm.GRASP, 3), TickEvent(gripper=EMPTY), max_attempts=3)
    assert tr.terminal and tr.reason == fsm.GRASP_FAILED and tr.state.attempts == 3


def test_max_attempts_capped_by_contract() -> None:
    tr = step(at(fsm.GRASP, 3), TickEvent(gripper=EMPTY), max_attempts=9)
    assert tr.reason == fsm.GRASP_FAILED  # 계약 상한 3 을 넘지 않는다


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
    tr = step(at(fsm.GRASP, 1), TickEvent(gripper=bad))
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
    assert (tr.reason, tr.cause) == (fsm.DEVICE_ERROR, f"GRIPPER_{code}")
    assert tr.actions == ()


# --- U5: 끝나는 전이에는 행동이 없다 ("grasped=false 면 개방 없음"의 FSM 쪽 보장) ---

_TERMINAL_CASES = [
    (at(fsm.VERIFY, 1), TickEvent(gripper=HELD), 3, fsm.OK),
    (at(fsm.GRASP, 1), TickEvent(gripper=EMPTY), 1, fsm.GRASP_FAILED),
    (at(fsm.VERIFY, 1), TickEvent(gripper=EMPTY), 1, fsm.GRASP_FAILED),  # 떨어뜨림
    (at(fsm.GRASP, 3), TickEvent(gripper=WIDE), 3, fsm.GRASP_FAILED),
    (
        at(fsm.GRASP, 1),
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
