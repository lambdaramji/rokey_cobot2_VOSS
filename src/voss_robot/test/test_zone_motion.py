"""MoveToZone 경로 — 격자 칸(measurements #6), 수직 상승 → 수평 → 수직 하강(T35)."""

import pytest
from voss_robot.zone_motion import (
    SAFE_Z_MM,
    TravelCache,
    crosses_back,
    pick_grip_ok,
    pick_pose,
    plan_move,
    row_stage_slot,
    search_travel_z,
    slot_offset,
    slot_pose,
    slot_route,
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


def test_pallet_4x2_two_layers_slots():
    grid = [4, 2, 50, 0, 2, 27, 60]
    assert [slot_offset(grid, k) for k in range(8)] == [
        (-75.0, 30.0),
        (-25.0, 30.0),
        (25.0, 30.0),
        (75.0, 30.0),
        (-75.0, -30.0),
        (-25.0, -30.0),
        (25.0, -30.0),
        (75.0, -30.0),
    ]
    z0, z8 = slot_pose([0] * 6, grid, 0)[2], slot_pose([0] * 6, grid, 8)[2]
    assert slot_offset(grid, 15) == (75.0, -30.0) and z8 - z0 == 27.0


def test_row_stage_slot_is_minus_x_end_of_same_row():
    grid = [3, 2, 50, -30, 2, 27, 60]
    assert [row_stage_slot(grid, k) for k in range(12)] == [0, 0, 0, 3, 3, 3, 0, 0, 0, 3, 3, 3]
    assert row_stage_slot([2, 1, 60], 1) == 0  # 재확인·보류 1줄은 칸 0 그대로


def test_layers_reuse_first_layer_slots_and_raise_z():
    g = [3, 2, 60, 0, 2, 27]  # 3칸 × 2줄 × 2층 = 12칸, 층 간격 27 mm (박스 높이)
    # row 0 = +Y(위 줄): 왼쪽 위 0·1·2, 왼쪽 아래 3·4·5 (10/12 실기 요청)
    assert [slot_offset(g, s) for s in (0, 5)] == [(-60.0, 30.0), (60.0, -30.0)]
    assert slot_offset(g, 6) == slot_offset(g, 0)  # 7번째 = 칸 0 위 2층
    assert slot_pose(A, g, 6) == pytest.approx([153.49, 195.23, A[2] + 27.0, *A[3:]])
    assert slot_pose(A, g, 5)[2] == pytest.approx(A[2])
    with pytest.raises(ValueError):
        slot_offset(g, 12)


def test_pitch_y_separate_from_x():
    g = [3, 2, 50, -30, 1, 27, 44]  # C: X 50·offset −30, Y 줄 간격 44
    assert [slot_offset(g, s) for s in (0, 2, 3)] == [(-80.0, 22.0), (20.0, 22.0), (-80.0, -22.0)]


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


def test_observe_to_pallet_goes_round_the_front_not_behind_the_base():
    # 10/12 실기: OBSERVE → 팔레트 직선이 베이스 뒤(−X)를 지나 팔이 반대로 돌고 축 가까이서 느려져 TIMEOUT
    pallet0 = slot_pose(
        [-163.76, 170.18, 258.27, 35.36, -180.0, -54.64], [4, 2, 50, 0, 2, 27, 60], 0
    )
    steps = plan_move(OBS, pallet0)
    names = [n for n, _ in steps]
    assert names[0].startswith("arc") and names[-2:] == [
        "over",
        "descend",
    ]  # OBSERVE 는 safe_z 위라 상승 없음
    pts = [OBS] + [p for _, p in steps]
    for a, b in zip(pts, pts[1:], strict=False):
        assert not crosses_back(a, b)
    import math

    assert min(math.hypot(p[0], p[1]) for n, p in steps if n.startswith("arc")) > 250
    back = plan_move(pallet0, OBS)
    assert back[0][0] == "rise" and back[1][0].startswith("arc") and back[-1][0] == "over"


def test_tray_paths_do_not_get_arcs():
    for z in (A, slot_pose(A, [3, 2, 60, 0, 2, 27, 60], 0)):
        assert not any(n.startswith("arc") for n, _ in plan_move(OBS, z) + plan_move(z, OBS))


def test_col_dy_shifts_one_column_in_both_rows_and_layers():
    grid = [4, 2, 50, 0, 2, 27, 60, 0, 0, 0, 10]
    assert slot_offset(grid, 3) == (75.0, 40.0) and slot_offset(grid, 7) == (75.0, -20.0)
    assert slot_offset(grid, 11) == (75.0, 40.0) and slot_offset(grid, 2) == (25.0, 30.0)


C2 = [655.3, -101.4, 260.5, 35.0, 180.0, -54.0]  # 플랜지, 자세 표기는 ZYZ (rx − rz = 89)
OFF = [1.382, 2.684, 246.642]


def test_travel_cache_hits_same_slot_within_tolerance():
    """#147: 같은 칸(x·y 1 mm 안, 같은 자세·관절 배치·하한·오프셋)이면 저장한 높이를 돌려준다."""
    c = TravelCache()
    assert c.get(C2, 2, 120.0, OFF) == (False, None)
    c.put(C2, 2, 120.0, OFF, None)  # 닿지 않음도 저장한다(가장 비싼 경우)
    c.put(C2, 2, 60.0, OFF, 306.6)
    near = [C2[0] + 0.4, C2[1] - 0.6, 14.4, *C2[3:]]  # 놓은 뒤 잰 현재 위치(z 는 상관없음)
    assert c.get(near, 2, 120.0, OFF) == (True, None)
    assert c.get(near, 2, 60.0, OFF) == (True, 306.6)
    assert len(c) == 2


def test_travel_cache_same_rotation_other_zyz_notation():
    """ry = 180 이면 rx − rz 만 의미가 있다 — 표기가 달라도 같은 자세면 같은 칸."""
    c = TravelCache()
    c.put(C2, 2, 120.0, OFF, 396.6)
    other = [*C2[:3], 159.0, 180.0, 70.0]  # 159 − 70 = 89
    assert c.get(other, 2, 120.0, OFF) == (True, 396.6)


def test_travel_cache_misses_other_slot_sol_floor_offset():
    c = TravelCache()
    c.put(C2, 2, 120.0, OFF, 396.6)
    assert not c.get([C2[0] + 50.0, *C2[1:]], 2, 120.0, OFF)[0]  # 옆 칸
    assert not c.get([*C2[:3], 35.0, 180.0, -40.0], 2, 120.0, OFF)[0]  # 14° 돈 자세
    assert not c.get(C2, 3, 120.0, OFF)[0]  # 관절 배치
    assert not c.get(C2, 2, 60.0, OFF)[0]  # 하한(트레이 안)
    assert not c.get(C2, 2, 120.0, [0.0, 0.0, 0.0])[0]  # 컨트롤러 TCP 등록 없음(플랜지 모드)


def test_travel_cache_put_replaces_and_caps():
    c = TravelCache(max_items=2)
    c.put(C2, 2, 120.0, OFF, 396.6)
    c.put(C2, 2, 120.0, OFF, 386.6)
    assert c.get(C2, 2, 120.0, OFF) == (True, 386.6) and len(c) == 1
    c.put([100.0, *C2[1:]], 2, 120.0, OFF, 446.6)
    c.put([200.0, *C2[1:]], 2, 120.0, OFF, 446.6)
    assert len(c) == 2 and not c.get(C2, 2, 120.0, OFF)[0]  # 가장 오래된 것부터 버림


LADDER = [446.6, 436.6, 426.6, 416.6, 406.6, 396.6]  # safe_z 부터 하한까지 10 mm 씩


class FakeIk:
    """ik_ok(z) 대역: reach 이하 높이만 풀림, error 높이는 호출 실패(None). 부른 높이를 남긴다."""

    def __init__(self, reach=None, error=()):
        self.reach, self.error, self.calls = reach, set(error), []

    def __call__(self, z):
        self.calls.append(z)
        if z in self.error:
            return None
        return self.reach is not None and z <= self.reach + 1e-6


def test_search_finds_highest_reachable_and_keeps():
    ik = FakeIk(reach=416.6)
    assert search_travel_z(LADDER, ik) == (416.6, True)
    assert search_travel_z(LADDER, FakeIk()) == (None, True)  # 닿지 않음도 저장한다


def test_search_cached_height_one_ikin():
    ik = FakeIk(reach=416.6)
    assert search_travel_z(LADDER, ik, (True, 416.6)) == (416.6, False)
    assert ik.calls == [416.6]


def test_search_cached_none_probes_floor_once():
    """#153: 저장한 "닿지 않음"은 하한 높이 ikin 1회로만 다시 본다."""
    ik = FakeIk()
    assert search_travel_z(LADDER, ik, (True, None)) == (None, False)
    assert ik.calls == [396.6]


def test_search_cached_none_but_reachable_now_researches():
    """#153: 미리 계산(관측 자세 씨앗) 때 None → 파지 끝 위치에서는 풀림 → 처음부터 찾아 새 값을 저장."""
    ik = FakeIk(reach=406.6)
    assert search_travel_z(LADDER, ik, (True, None)) == (406.6, True)
    assert ik.calls[0] == 396.6 and ik.calls[1:] == LADDER[:5]


def test_search_call_error_is_not_kept():
    """#153: 두산 호출 실패(타임아웃 등)가 섞이면 "닿지 않음"·낮은 높이로 굳지 않게 저장하지 않는다."""
    assert search_travel_z(LADDER, FakeIk(error={436.6})) == (None, False)
    assert search_travel_z(LADDER, FakeIk(reach=416.6, error={446.6})) == (416.6, False)
    # 저장한 None 을 확인하다 호출 실패 → 처음부터
    ik = FakeIk(reach=426.6, error={396.6})
    assert search_travel_z(LADDER, ik, (True, None)) == (426.6, True)


# voss_config zones.C (10/13~): 3×2 × 2층, offset −30, 트레이 안 TCP 40 — gateway self.zones 형태
C_ZONE = {
    "pose": [675.14, 158.69, 260.94, 159.7, -180.0, 70.28],
    "grid": [3, 2, 50, -30, 2, 27, 60],
    "in_tray": 40.0,
}
HOLD_ZONE = {
    "pose": [674.12, -71.37, 262.65, 168.88, -180.0, 78.38],
    "grid": [2, 1, 60],
    "in_tray": None,
}


def test_slot_route_gate_is_row_minus_x_end_and_zone_floor():
    """MoveToZone 의 출입구 칸·하한(C 칸 2 → 0, 칸 5 → 3, 트레이 안 TCP 40)."""
    r = slot_route(C_ZONE, 2)
    assert r.target == slot_pose(C_ZONE["pose"], C_ZONE["grid"], 2)
    assert (r.via, r.in_tray_z) == (0, 40.0)
    assert r.stage == slot_pose(C_ZONE["pose"], C_ZONE["grid"], 0)
    assert slot_route(C_ZONE, 5)[1:3] == (3, slot_pose(C_ZONE["pose"], C_ZONE["grid"], 3))
    assert slot_route(HOLD_ZONE, 1)[1:] == (0, slot_pose(HOLD_ZONE["pose"], [2, 1, 60], 0), None)
    with pytest.raises(ValueError):
        slot_route(C_ZONE, 12)


def test_prewarm_first_layer_routes_hit_cache_for_every_slot():
    """#147 회귀(10/13~ C 칸 2 경로 계산 ikin 32회): 미리 계산이 칸 0·공통 하한 60 으로 저장해 C 칸 2·5
    (하한 40, 칸 5 출입구 = 칸 3)가 캐시에 안 맞았다. 1층 칸을 slot_route 로 저장하면 2층까지 모두 맞는다."""
    common = 60.0  # zone_min_in_tray_tcp_z_mm

    def floor(r):
        return common if r.in_tray_z is None else r.in_tray_z

    per = 6
    c = TravelCache()
    for k in range(per):  # gateway _prewarm_travel 과 같이 1층만
        r = slot_route(C_ZONE, k)
        c.put(r.target, 2, floor(r), OFF, 300.0)  # 칸 위 트레이 안 높이
        c.put(r.stage, 2, 120.0, OFF, 400.0)  # 출입구 칸 위 이동 높이
    for k in range(per * 2):
        r = slot_route(C_ZONE, k)
        assert c.get(r.target, 2, floor(r), OFF) == (True, 300.0), k
        assert c.get(r.stage, 2, 120.0, OFF) == (True, 400.0), k
    # 예전 미리 계산(하한 60)으로는 C 칸 2 의 하한 40 이 맞지 않았다
    old = TravelCache()
    old.put(slot_route(C_ZONE, 2).target, 2, common, OFF, 300.0)
    assert not old.get(slot_route(C_ZONE, 2).target, 2, 40.0, OFF)[0]
