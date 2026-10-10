"""fake_box.py 순수 함수 시험 (ROS 없이) — design/U3-dd.md 8절 T-F1~T-F7."""

import math

import numpy as np
import pytest
from voss_servo.fake_box import belt_velocity, make_config, position_at, samples_at

DIRECTION = [0.99992, -0.01292, 0.0]  # 레포 voss_config belt.direction_base (시험 입력)
START = (-0.100, -0.271, 0.1008)


def cfg(scenario: str = "normal", **kw):
    """시험용 FakeBoxConfig (T = 2 s)."""
    args = {
        "scenario": scenario,
        "track_id": 1,
        "start": START,
        "speed_cmps": 4.8,
        "direction": DIRECTION,
        "invalid_after_s": 2.0,
        "lost_after_s": 2.0,
        "second_track_id": 2,
        "second_offset": (0.060, 0.040, 0.0),
    }
    args.update(kw)
    return make_config(**args)


def line_distance(p, start, d) -> float:
    """점 p 와 (start, 방향 d) 직선 사이 거리."""
    w = np.subtract(p, start)
    u = np.asarray(d, float) / np.linalg.norm(d)
    return float(np.linalg.norm(w - np.dot(w, u) * u))


def test_belt_velocity_units_and_direction() -> None:
    """T-F1: 4.8 cm/s → ‖v‖ = 0.048 m/s, 방향 유지 (길이 1 이 아닌 방향도 방향만 쓴다)."""
    v = belt_velocity(4.8, DIRECTION)
    assert math.isclose(math.hypot(*v), 0.048, rel_tol=1e-9)
    assert v[0] > 0 and v[1] < 0 and v[2] == 0.0
    assert np.allclose(belt_velocity(4.8, [2.0, 0, 0]), (0.048, 0.0, 0.0))


def test_position_at_moves_along_belt() -> None:
    """T-F2: t=0 시작점, t=10 s → 벨트 방향으로 0.48 m."""
    v = belt_velocity(4.8, DIRECTION)
    assert position_at(START, v, 0.0) == START
    p = position_at(START, v, 10.0)
    assert math.isclose(math.dist(p, START), 0.48, rel_tol=1e-9)
    assert p[2] == START[2]  # 높이는 그대로


def test_normal_always_one_valid() -> None:
    """T-F3: normal 은 언제나 첫째 박스 valid 1개."""
    c = cfg("normal")
    for t in (0.0, 1.0, 5.0, 100.0):
        s = samples_at(c, t)
        assert len(s) == 1 and s[0].track_id == 1 and s[0].valid


def test_invalid_after_keeps_moving_but_invalid() -> None:
    """T-F4: T 전 valid, T 뒤 invalid, 위치는 계속 움직인다."""
    c = cfg("invalid_after_s")
    before, after = samples_at(c, 1.9)[0], samples_at(c, 2.1)[0]
    assert before.valid and not after.valid
    assert after.xyz[0] > before.xyz[0]  # 벨트 방향(+x)으로 계속 감


def test_lost_after_sends_nothing() -> None:
    """T-F5: T 뒤에는 빈 목록 (미검출 = 발행 안 함)."""
    c = cfg("lost_after_s")
    assert len(samples_at(c, 1.9)) == 1
    assert samples_at(c, 2.0) == [] and samples_at(c, 30.0) == []


def test_two_boxes_offset_and_separate_line() -> None:
    """T-F6: 두 개, track_id 다름, 둘째 = 첫째 + offset, 첫째 궤적 선에서 약 40 mm."""
    c = cfg("two_boxes")
    first, second = samples_at(c, 3.0)
    assert (first.track_id, second.track_id) == (1, 2) and first.valid and second.valid
    assert np.allclose(np.subtract(second.xyz, first.xyz), (0.060, 0.040, 0.0))
    assert line_distance(first.xyz, START, DIRECTION) < 1e-9
    assert 0.035 < line_distance(second.xyz, START, DIRECTION) < 0.045


@pytest.mark.parametrize(
    "kw", [{"scenario": "teleport"}, {"direction": [0, 0, 0]}, {"direction": [1, 0]}]
)
def test_bad_config_raises(kw: dict) -> None:
    """T-F7: 모르는 시나리오·길이 0 방향·길이 3 아님 → ValueError."""
    with pytest.raises(ValueError):
        cfg(**kw)
