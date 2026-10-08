"""pose_source.py — joint_states 관절 매핑·나이·기동 교차 검사 (#118)."""

import math

from voss_robot.pose_source import StartupCheck, fresh, joints_deg

NAMES = [f"joint_{i}" for i in range(1, 7)]


def test_joints_deg_orders_by_name():
    rad = [math.radians(v) for v in (10, 20, 30, 40, 50, 60)]
    shuffled = list(zip(NAMES, rad, strict=True))[::-1]
    out = joints_deg([n for n, _ in shuffled], [r for _, r in shuffled])
    assert [round(v, 6) for v in out] == [10, 20, 30, 40, 50, 60]


def test_joints_deg_missing_name_is_none():
    assert joints_deg(NAMES[:5], [0.0] * 5) is None
    assert joints_deg(["j1", "j2", "j3", "j4", "j5", "j6"], [0.0] * 6) is None


def test_fresh():
    now = 10_000_000_000
    assert fresh(now, now - 50_000_000, 0.1)
    assert not fresh(now, now - 150_000_000, 0.1)
    assert fresh(now, now + 10_000_000, 0.1)  # 시계 차이 조금
    assert not fresh(now, now + 100_000_000, 0.1)


def test_startup_check_pass_and_fail():
    srv = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]
    ok = StartupCheck()
    assert ok.feed([-11.51, -271.11, 450.5, 0, 0, 0], srv) == "pass"
    # 등록 TCP 가 다르면 늘 크게 다르다 → fails 번 연속이면 실패
    bad = StartupCheck(fails=3)
    wrong = [-11.51, -271.11, 450.16 - 246.6, 0, 0, 0]
    assert [bad.feed(wrong, srv) for _ in range(3)] == ["", "", "fail"]
    assert bad.last_diff_mm > 200
