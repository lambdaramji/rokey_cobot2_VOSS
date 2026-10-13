"""fake_gripper.py 순수 판정 시험 (ROS 노드 없이). design/U9b-dd.md 6.1, 7.1 G1."""

import pytest
from voss_servo.fake_gripper import (
    CLOSE,
    OPEN,
    VERIFY,
    FakeGripState,
    fake_reply,
    parse_plan,
)

PRE_OPEN = 90.0  # 사전 개방 폭 mm


def test_open_resets_closed_state() -> None:
    s, r, kind = fake_reply(FakeGripState(1, "held"), ("held",), 90.0, PRE_OPEN)
    assert kind == OPEN and s == FakeGripState(1, None)
    assert (r.ok, r.width_mm, r.grip_detected, r.message) == (True, 90.0, False, "OK")


def test_plan_in_order_then_last_repeats() -> None:
    plan = ("empty", "held")
    s = FakeGripState()
    s, r, kind = fake_reply(s, plan, 39.0, PRE_OPEN)  # 1차 닫기
    assert kind == CLOSE and (r.width_mm, r.grip_detected) == (38.4, False)
    s, _, _ = fake_reply(s, plan, 90.0, PRE_OPEN)  # 재시도 개방
    s, r, kind = fake_reply(s, plan, 39.0, PRE_OPEN)  # 2차 닫기
    assert kind == CLOSE and (r.width_mm, r.grip_detected) == (41.0, True)
    s, _, _ = fake_reply(s, plan, 90.0, PRE_OPEN)
    s, r, _ = fake_reply(s, plan, 39.0, PRE_OPEN)  # 계획 소진 → 마지막(held) 반복
    assert r.grip_detected and s.n_close == 3


def test_close_again_while_closed_is_verify() -> None:
    plan = ("held", "empty")
    s, _, _ = fake_reply(FakeGripState(), plan, 39.0, PRE_OPEN)
    s2, r, kind = fake_reply(s, plan, 39.0, PRE_OPEN)  # VERIFY = 닫기 재전송
    assert kind == VERIFY and r.grip_detected and s2 == s  # 결과 유지, 계획 소비 안 함


def test_wide_is_detected_but_out_of_hold_range() -> None:
    _, r, _ = fake_reply(FakeGripState(), ("wide",), 39.0, PRE_OPEN)
    assert r.grip_detected and r.width_mm > 44.0  # hold_width_max 44.0 밖 → WIDTH_OUT


def test_parse_plan() -> None:
    assert parse_plan(" Empty, held ,") == ("empty", "held")
    with pytest.raises(ValueError):
        parse_plan("")
    with pytest.raises(ValueError):
        parse_plan("empty,grab")
