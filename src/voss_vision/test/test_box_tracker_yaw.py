"""box_tracker._fill_position — BoxTrack yaw_base·yaw_valid (S2-T16, voss_msgs.md BoxTrack).

rclpy 없이 노드 메서드만 부른다(입출력이 없는 계산). 핸드아이 합성 배치는 test_hand_eye 와 같다.
"""

import threading

import numpy as np
import pytest
from voss_vision.belt_plane import rot_zyz_deg
from voss_vision.box_tracker import BoxTrackerNode
from voss_vision.hand_eye import make_t
from voss_vision.tracker_logic import LoopStats

from voss_msgs.msg import BoxTrack

K = np.array([[1367.5, 0, 978.5], [0, 1367.7, 552.0], [0, 0, 1]])
T_TCP_CAM = make_t(rot_zyz_deg(30, 22, -100), [-16.0, -44.0, -208.0])
PLANE_Z = 101.0


def node() -> BoxTrackerNode:
    n = BoxTrackerNode.__new__(
        BoxTrackerNode
    )  # Node.__init__ 를 건너뛴다 — _fill_position 이 쓰는 값만 채운다
    n.he, n.he_T, n.he_k, n.he_d = {"moving_verified": True}, T_TCP_CAM, K, np.zeros(5)
    n.plane_z, n.he_ok, n.he_verified, n.he_label = PLANE_Z, True, True, "hand_eye test"
    n.homo, n.homo_ok, n.homo_label, n.observe_source = None, False, "", "hand_eye"
    n.stats, n._stats_lock = LoopStats(), threading.Lock()
    return n


def label_pixels(t_base_cam: np.ndarray, box_yaw_deg: float) -> tuple[float, float, tuple]:
    """박스 윗면의 송장 긴 변 양 끝(±20 mm) → 화면 중심 픽셀과 half_axis (검출기가 주는 값)."""
    c, a = np.array([-110.0, -385.0, PLANE_Z]), np.radians(box_yaw_deg)
    d = 20 * np.array([np.cos(a), np.sin(a), 0.0])
    ends = np.array([c - d, c + d])
    pc = (np.linalg.inv(t_base_cam) @ np.hstack([ends, np.ones((2, 1))]).T).T[:, :3]
    px = (K @ (pc / pc[:, 2:3]).T).T[:, :2]
    (u, v), half = px.mean(0), (px[1] - px[0]) / 2
    return float(u), float(v), (float(half[0]), float(half[1]))


@pytest.mark.parametrize("j6", [0, 15, 30, 45])
@pytest.mark.parametrize("box_yaw", [0, 30, -60, 90])
def test_hand_eye_yaw_matches_box_for_any_j6(j6: float, box_yaw: float) -> None:
    t_tcp = make_t(rot_zyz_deg(0, 180, 0), [-110.0, -380.0, 351.0]) @ make_t(
        rot_zyz_deg(j6, 0, 0), [0, 0, 0]
    )
    u, v, half = label_pixels(t_tcp @ T_TCP_CAM, box_yaw)
    m = BoxTrack()
    node()._fill_position(m, u, v, t_tcp, False, half)
    assert m.position_source == BoxTrack.SOURCE_HAND_EYE and m.position_valid
    assert m.yaw_valid
    # ±90° 는 같은 방향이라 π 로 접어 비교한다 (부동소수에서 π/2 가 −π/2 로 접힐 수 있다)
    diff = (m.yaw_base - np.radians(box_yaw) + np.pi / 2) % np.pi - np.pi / 2
    assert abs(diff) < 1e-4
    assert -np.pi / 2 < m.yaw_base <= np.pi / 2


def test_no_angle_from_detector_keeps_position_but_not_yaw() -> None:
    t_tcp = make_t(rot_zyz_deg(0, 180, 0), [-110.0, -380.0, 351.0])
    u, v, _ = label_pixels(t_tcp @ T_TCP_CAM, 30)
    m = BoxTrack()
    node()._fill_position(m, u, v, t_tcp, False, None)  # yolo 축정렬 bbox 처럼 각도 없음
    assert m.position_valid and not m.yaw_valid and m.yaw_base == 0.0


def test_invalid_position_gives_invalid_yaw() -> None:
    n = node()
    n.he_verified = False  # 동적 검증 전 → position_valid=false
    t_tcp = make_t(rot_zyz_deg(0, 180, 0), [-110.0, -380.0, 351.0])
    u, v, half = label_pixels(t_tcp @ T_TCP_CAM, 30)
    m = BoxTrack()
    n._fill_position(m, u, v, t_tcp, False, half)
    assert not m.position_valid and not m.yaw_valid
