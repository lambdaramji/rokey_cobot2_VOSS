"""grip.py 순수 함수 시험 (ROS 없음). 설계: design/U5-dd.md 6.1."""

import math

import pytest

from voss_servo import fsm, grip

TIMEOUT = 3.0  # gripper_timeout_s


def call(**kw) -> grip.GripCall:
    """시험용 닫기 호출 (보낸 시각 10.0 s)."""
    base = dict(
        goal_id="g1", attempt=1, kind=grip.CLOSE, width_mm=39.0, force_n=14.0, seq=2, now=10.0
    )
    base.update(kw)
    return grip.new_call(**base)


def raw(ok=True, width=40.9, grip_detected=True, message="OK") -> grip.RawReply:
    return grip.RawReply(ok, width, grip_detected, message)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("OK", "OK"),
        ("INVALID: width 200", "INVALID"),  # gateway 가 이유를 붙인다
        ("COMM_ERROR: RG2 safety_err", "COMM_ERROR"),
        (" busy ", "BUSY"),  # 공백·소문자
        ("", grip.UNKNOWN),
        ("WHAT", grip.UNKNOWN),  # 계약 밖
    ],
)
def test_message_code(message, code) -> None:
    assert grip.message_code(message) == code


@pytest.mark.parametrize(
    ("action", "kind", "width"),
    [
        (fsm.GRIPPER_OPEN, grip.OPEN, 90.0),
        (fsm.GRIPPER_CLOSE, grip.CLOSE, 39.0),
        (fsm.GRIPPER_VERIFY, grip.VERIFY, 39.0),  # 확인도 닫기 폭 (HLD D1)
    ],
)
def test_request_for(action, kind, width) -> None:
    assert grip.request_for(action, 90.0, 39.0) == (kind, width)


def test_request_for_unknown_action() -> None:
    with pytest.raises(ValueError):
        grip.request_for(fsm.REQUEST_STOP, 90.0, 39.0)


def test_poll_pending_and_timeout_boundary() -> None:
    c = call()
    assert grip.poll(c, False, None, False, 11.0, TIMEOUT).status == grip.PENDING
    # 정확히 한계 = 아직 기다린다
    assert grip.poll(c, False, None, False, 10.0 + TIMEOUT, TIMEOUT).status == grip.PENDING


def test_poll_timed_out() -> None:
    res = grip.poll(call(), False, None, False, 13.01, TIMEOUT)
    assert res.status == grip.TIMED_OUT and res.code == "TIMEOUT"
    assert res.reply == fsm.GripperReply(False, 0.0, False, "TIMEOUT")


def test_poll_reply_passes_values_with_code() -> None:
    res = grip.poll(call(), True, raw(message="OK"), False, 11.8, TIMEOUT)
    assert res.status == grip.REPLY and res.reply == fsm.GripperReply(True, 40.9, True, "OK")


def test_poll_reply_message_becomes_code() -> None:
    res = grip.poll(call(), True, raw(ok=False, message="INVALID: width"), False, 11.0, TIMEOUT)
    assert res.reply.message == "INVALID"  # FSM 에는 코드 (DD E4)
    assert res.raw_message == "INVALID: width"  # 원문은 로그용으로 남는다


def test_poll_busy_waits_then_retries_after_delay() -> None:
    c = call()
    res = grip.poll(c, True, raw(ok=False, message="BUSY"), False, 10.25, TIMEOUT)
    assert res.status == grip.BUSY_WAIT
    waiting = grip.busy_marked(c, 10.25)  # 시각은 이진수로 정확한 값 (경계 비교가 흔들리지 않게)
    assert grip.poll(waiting, True, None, False, 10.6875, TIMEOUT).status == grip.PENDING
    assert grip.poll(waiting, True, None, False, 10.75, TIMEOUT).status == grip.RETRY  # 0.5 s 딱


def test_poll_busy_after_retry_is_reply() -> None:
    again = grip.retried(grip.busy_marked(call(), 10.1), 10.6)
    res = grip.poll(again, True, raw(ok=False, message="BUSY"), False, 10.7, TIMEOUT)
    # 두 번째 BUSY 는 응답으로 넘긴다 → FSM 이 DEVICE_ERROR
    assert res.status == grip.REPLY and res.reply.message == "BUSY"


def test_poll_exception_is_comm_error() -> None:
    res = grip.poll(call(), True, None, True, 10.5, TIMEOUT)
    assert res.status == grip.REPLY and res.reply == fsm.GripperReply(
        False, 0.0, False, "COMM_ERROR"
    )


def test_retried_and_busy_marked() -> None:
    c = call()
    waiting = grip.busy_marked(c, 10.1)
    assert waiting.busy_at == 10.1 and waiting.seq == c.seq
    again = grip.retried(waiting, 10.6)
    assert (again.seq, again.busy_retries, again.sent_s, again.busy_at) == (3, 1, 10.6, None)
    assert (again.goal_id, again.attempt, again.kind, again.width_mm) == ("g1", 1, grip.CLOSE, 39.0)


def test_unavailable_reply_judged_device_error() -> None:
    verdict, cause = fsm.judge_grip(grip.unavailable_reply(), 39.5, 43.5)
    assert (verdict, cause) == (fsm.DEVICE_ERROR, "GRIPPER_UNAVAILABLE")


def test_descend_time_matches_u2_simulation() -> None:
    # 접근 +40 → 파지 −19 mm, 상한 0.05 m/s, 가속 0.1, kp_z 2, 허용치 2 mm → U2 시뮬레이션 2.17 s
    t = grip.descend_time_s(0.059, 0.05, 0.1, 2.0, 0.002)
    assert t == pytest.approx(0.25 + 0.034 / 0.05 + math.log(12.5) / 2.0)
    assert 2.15 < t < 2.25


def test_descend_time_short_distance_is_tail_only() -> None:
    # 감속 시작 거리(0.05/2 = 25 mm)보다 짧으면 지수 접근만
    assert grip.descend_time_s(0.02, 0.05, 0.1, 2.0, 0.002) == pytest.approx(math.log(10) / 2.0)


def test_grasp_room_boundary() -> None:
    # 필요 = 0.0625 × 4.0 + 0.125 = 0.375 m (이진수로 정확한 값 — 경계 비교가 흔들리지 않게)
    assert grip.grasp_room_ok(0.125, 0.5, 0.0625, 4.0, 0.125)  # 남은 길 0.375 = 필요 → 여유 있음
    assert not grip.grasp_room_ok(0.126, 0.5, 0.0625, 4.0, 0.125)  # 1 mm 모자람


def test_call_record_keys_always_present() -> None:
    c = call()
    pending = grip.call_record(c, grip.PENDING, 10.0)
    done = grip.call_record(
        c, grip.REPLY, 11.8, fsm.GripperReply(True, 40.9, True, "OK"), "OK", "OK", fsm.HELD
    )
    assert set(pending) == set(done)  # 집계에서 키 유무 분기가 없게 (DD E14)
    assert pending["rx_s"] is None and pending["ok"] is None
    assert done["latency_s"] == pytest.approx(1.8) and done["verdict"] == fsm.HELD
