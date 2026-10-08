"""MoveToZone 경로 — 격자 칸(measurements #6), 수직 상승 → 수평 → 수직 하강(T35)."""

import pytest
from voss_robot.zone_motion import SAFE_Z_MM, plan_move, slot_offset, slot_pose

A = [213.49, 165.23, 258.27, 35.36, -180.0, -54.64]  # voss_config zones.A (플랜지)
OBS = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]


def test_slot_offsets_match_measurements():
    assert [slot_offset([3, 1, 60], s)[0] for s in range(3)] == [-60.0, 0.0, 60.0]
    assert [slot_offset([2, 1, 60], s)[0] for s in range(2)] == [-30.0, 30.0]
    assert slot_offset([3, 1, 60], 1)[1] == 0.0


def test_slot_out_of_range():
    with pytest.raises(ValueError):
        slot_offset([3, 1, 60], 3)
    with pytest.raises(ValueError):
        slot_offset([2, 1, 60], -1)


def test_slot_pose_shifts_x_only():
    assert slot_pose(A, [3, 1, 60], 0) == pytest.approx([153.49, *A[1:]])


def test_observe_to_zone_rises_then_over_then_descends():
    steps = plan_move(OBS, slot_pose(A, [3, 1, 60], 2))
    assert [n for n, _ in steps] == ["over", "descend"]  # 관측 자세는 이미 safe z(450.2) 이상
    over, down = steps[0][1], steps[1][1]
    assert over[2] == pytest.approx(SAFE_Z_MM) and over[:2] == pytest.approx([273.49, 165.23])
    assert down == pytest.approx([273.49, *A[1:]])


def test_zone_back_to_observe_rises_vertically_first():
    steps = plan_move(A, OBS)
    assert [n for n, _ in steps] == ["rise", "over"]
    rise = steps[0][1]
    assert rise[:2] == pytest.approx(A[:2]) and rise[2] == pytest.approx(SAFE_Z_MM)
    assert rise[3:] == pytest.approx(A[3:])  # 상승 중엔 자세 그대로
    assert steps[1][1] == pytest.approx(OBS)


def test_low_target_uses_safe_z_for_travel():
    low = [0.0, -276.0, 260.0, 85.0, -179.0, -6.0]
    cur = [100.0, -276.0, 300.0, 85.0, -179.0, -6.0]
    names_z = [(n, p[2]) for n, p in plan_move(cur, low)]
    assert names_z == [("rise", SAFE_Z_MM), ("over", SAFE_Z_MM), ("descend", 260.0)]


def test_already_there_no_steps():
    assert plan_move(OBS, OBS) == []


def test_far_zone_lower_travel_height_and_no_overshoot_rise():
    c = [675.14, 158.69, 260.94, 159.7, -180.0, 70.28]
    steps = plan_move(OBS, c, safe_z=400.0)  # gateway 가 ikin 으로 낮춘 높이
    assert [(n, round(p[2], 1)) for n, p in steps] == [("over", 400.0), ("descend", 260.9)]
    back = plan_move(c, OBS, safe_z=400.0)
    assert [(n, round(p[2], 2)) for n, p in back] == [("rise", 400.0), ("over", 450.16)]
