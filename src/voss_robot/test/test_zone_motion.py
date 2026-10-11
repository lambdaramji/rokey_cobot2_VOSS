"""MoveToZone 경로 — 격자 칸(measurements #6), 수직 상승 → 수평 → 수직 하강(T35)."""

import pytest
from voss_robot.zone_motion import (
    SAFE_Z_MM,
    pick_grip_ok,
    pick_pose,
    plan_move,
    slot_offset,
    slot_pose,
)

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


def test_offset_moves_slots_toward_minus_x():
    # 10/08: 먼 트레이는 칸 줄을 −X 쪽에 둔다 (보류 −60/0, 재확인 1칸 −60)
    assert [slot_offset([2, 1, 60, -30], s)[0] for s in range(2)] == [-60.0, 0.0]
    assert slot_offset([1, 1, 60, -60], 0) == (-60.0, 0.0)
    assert slot_offset([3, 1, 60], 2) == (60.0, 0.0)  # offset 없으면 0


RECHECK = [446.17, -69.04, 260.65, 169.44, -180.0, 79.38]  # voss_config zones.recheck (플랜지)


def test_pick_pose_is_slot_pose_plus_dz():
    """PICK 파지 = 놓기 칸 자세 − 8 mm (10/11 실기, voss_msgs.md MoveToZone PICK)."""
    p = pick_pose(slot_pose(RECHECK, [2, 1, 60], 1), -8.0)
    assert p == pytest.approx([476.17, -69.04, 252.65, *RECHECK[3:]])


def test_pick_grip_ok_needs_detect_and_width_range():
    assert pick_grip_ok(True, True, 41.1, 39.5, 44.0) == ""  # 10/10 벨트 VERIFY 폭
    assert pick_grip_ok(True, True, 39.5, 39.5, 44.0) == ""  # 경계 포함
    assert "응답" in pick_grip_ok(False, True, 41.1, 39.5, 44.0)
    assert "grip 없음" in pick_grip_ok(True, False, 38.7, 39.5, 44.0)  # 빈손
    assert "밖" in pick_grip_ok(True, True, 45.2, 39.5, 44.0)  # 비스듬히 쥠
    assert "밖" in pick_grip_ok(True, True, 39.0, 39.5, 44.0)
