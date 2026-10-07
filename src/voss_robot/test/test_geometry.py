"""geometry.py 순수 함수 시험. 값은 measurements-1006 #6·config/voss_config.yaml (10/06 실측)."""

import math

import pytest

from voss_robot import geometry as g

TCP = [1.382, 2.684, 246.642]  # robot.tcp_offset_mm (펜던트 등록값)
OBSERVE_FLANGE = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]  # observe_pose (플랜지)
OBSERVE_TCP_PENDANT = [-14.49, -276.54, 203.58]  # 같은 자세를 펜던트(TCP)로 읽은 값, 10/06


def test_grid_three_by_one():
    # A·B·C 3×1, pitch 60 → X −60 / 0 / +60
    assert [g.grid_slot_offset_mm(3, 1, 60, s) for s in range(3)] == [
        (-60.0, 0.0),
        (0.0, 0.0),
        (60.0, 0.0),
    ]


def test_grid_two_by_one():
    # 재확인·보류 2×1 → X ±30
    assert [g.grid_slot_offset_mm(2, 1, 60, s) for s in range(2)] == [(-30.0, 0.0), (30.0, 0.0)]


@pytest.mark.parametrize("slot", [-1, 3, 99])
def test_grid_slot_out_of_range(slot):
    # 없는 칸은 만들지 않는다 (#51 MC-017)
    with pytest.raises(ValueError):
        g.grid_slot_offset_mm(3, 1, 60, slot)


def test_slot_pose_moves_only_x():
    zone_b = [446.08, 160.78, 258.94, 14.28, 180.0, -75.33]
    p = g.slot_pose(zone_b, 3, 1, 60, 2)
    assert p[0] == pytest.approx(506.08)
    assert p[1:] == pytest.approx(zone_b[1:])


def test_normalize_down_pose_same_rotation():
    # 구역마다 rx/rz 가 달라도 rx − rz 가 같으면 같은 자세다 (measurements #6 자세 표기 주의)
    raw = [213.49, 165.23, 258.27, 35.36, -180.0, -54.64]
    norm = g.normalize_down_pose(raw)
    assert norm[3:] == pytest.approx([90.0, 180.0, 0.0])
    a, b = g.zyz_to_matrix(*raw[3:]), g.zyz_to_matrix(*norm[3:])
    for i in range(3):
        assert a[i] == pytest.approx(b[i], abs=1e-9)


def test_normalize_keeps_tilted_pose():
    p = [0, 0, 0, 10.0, 170.0, 5.0]  # 수직이 아니면 그대로
    assert g.normalize_down_pose(p) == p


def test_flange_to_tcp_matches_pendant():
    # 플랜지로 적은 관측 자세를 TCP 로 바꾸면 펜던트(TCP 등록) 값과 0.2 mm 안에서 같아야 한다
    tcp = g.flange_to_tcp(OBSERVE_FLANGE, TCP)
    assert tcp[:3] == pytest.approx(OBSERVE_TCP_PENDANT, abs=0.2)


def test_flange_tcp_round_trip():
    tcp = g.flange_to_tcp(OBSERVE_FLANGE, TCP)
    assert g.tcp_to_flange(tcp, TCP) == pytest.approx(OBSERVE_FLANGE, abs=1e-9)


def test_quaternion_down_pose():
    # (0, 180, 0) = x 축으로 180° 뒤집힌 자세 → 쿼터니언 크기 1, z 축이 아래(-z)를 본다
    q = g.zyz_to_quaternion(0.0, 180.0, 0.0)
    assert math.sqrt(sum(c * c for c in q)) == pytest.approx(1.0)
    m = g.zyz_to_matrix(0.0, 180.0, 0.0)
    assert [m[0][2], m[1][2], m[2][2]] == pytest.approx([0.0, 0.0, -1.0], abs=1e-12)


def test_quaternion_identity():
    assert g.zyz_to_quaternion(0.0, 0.0, 0.0) == pytest.approx((0.0, 0.0, 0.0, 1.0))


def test_clamp_speed():
    assert g.clamp_speed([0.03, 0.04, 0.0], 0.1) == pytest.approx([0.03, 0.04, 0.0])
    v = g.clamp_speed([0.3, 0.4, 0.0], 0.1)  # 크기 0.5 → 0.1, 방향 유지
    assert v == pytest.approx([0.06, 0.08, 0.0])


def test_in_box():
    assert g.in_box([0, 0, 0], [-1, -1, -1], [1, 1, 1])
    assert not g.in_box([0, 0, 2], [-1, -1, -1], [1, 1, 1])


def test_flange_to_ros_pose_units():
    # /voss/robot/pose = TCP 위치 m. 관측 자세 TCP z ≈ 203.58 mm → 0.2036 m (펜던트 값)
    (x, y, z), q = g.flange_to_ros_pose(OBSERVE_FLANGE, TCP)
    assert [x, y, z] == pytest.approx([v / 1000.0 for v in OBSERVE_TCP_PENDANT], abs=2e-4)
    assert math.sqrt(sum(c * c for c in q)) == pytest.approx(1.0)
