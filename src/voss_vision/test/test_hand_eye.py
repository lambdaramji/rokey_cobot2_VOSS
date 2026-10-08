"""hand_eye — 합성 데이터: 알려진 T_tcp_camera 를 풀이로 되찾는지, 픽셀 → 평면, pose 보간."""

import numpy as np
import pytest
from voss_vision.belt_plane import rot_zyz_deg
from voss_vision.hand_eye import (
    board_in_base,
    board_object_points,
    board_pose,
    correct_translation,
    interpolate_pose,
    make_t,
    pixel_to_plane,
    plane_errors,
    pose_msg_to_t,
    posx_to_t,
    rot_angle_deg,
    rot_to_quat,
    solve,
    spread,
)

K = np.array([[1367.5, 0, 978.5], [0, 1367.7, 552.0], [0, 0, 1]])
# 10/07 호모그래피에서 유도한 값과 비슷한 실제적 배치: 카메라가 TCP 위 약 208 mm, 22° 기울어짐
T_TCP_CAM = make_t(rot_zyz_deg(30, 22, -100), [-16.0, -44.0, -208.0])
T_BASE_BOARD = make_t(rot_zyz_deg(5, 0, 0), [-120.0, -380.0, 101.0])


def capture_poses(n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """보드 위 35~50 cm 에서 공구를 15~25° 기울이고 축 둘레로 돌린 TCP 자세들."""
    out = []
    for _ in range(n):
        tilt, az, spin = rng.uniform(15, 25), rng.uniform(-180, 180), rng.uniform(-60, 60)
        r = rot_zyz_deg(az, 180 - tilt, spin - az)  # ry≈180 = 공구가 아래를 봄
        p = T_BASE_BOARD[:3, 3] + [
            rng.uniform(-60, 60),
            rng.uniform(-60, 60),
            rng.uniform(150, 300),
        ]
        out.append(make_t(r, p))
    return out


def cam_board(t_base_tcp: np.ndarray) -> np.ndarray:
    return np.linalg.inv(T_TCP_CAM) @ np.linalg.inv(t_base_tcp) @ T_BASE_BOARD


def jitter(t: np.ndarray, rng: np.random.Generator, mm: float, deg: float) -> np.ndarray:
    a, b, c = rng.normal(0, deg, 3)
    return make_t(t[:3, :3] @ rot_zyz_deg(a, b, -a + c), t[:3, 3] + rng.normal(0, mm, 3))


# TSAI·DANIILIDIS 는 자세 사이 회전이 크면(공구축 ±60°) 노이즈 없이도 1~2 mm 어긋나서 비교에서 뺀다
@pytest.mark.parametrize("method", ["PARK", "HORAUD", "ANDREFF"])
def test_solve_recovers_known_transform(method: str) -> None:
    rng = np.random.default_rng(0)
    poses = capture_poses(20, rng)
    boards = [cam_board(p) for p in poses]
    t = solve(poses, boards, method)
    assert np.linalg.norm(t[:3, 3] - T_TCP_CAM[:3, 3]) < 0.1
    assert rot_angle_deg(t[:3, :3], T_TCP_CAM[:3, :3]) < 0.01
    d, ang = spread(board_in_base(poses, t, boards))
    assert d < 0.1 and ang < 0.01


def test_solve_with_noise_stays_within_board_spread() -> None:
    rng = np.random.default_rng(1)
    poses = capture_poses(22, rng)
    boards = [jitter(cam_board(p), rng, 0.3, 0.05) for p in poses]  # PnP 오차 수준
    t = solve(poses, boards, "PARK")
    assert np.linalg.norm(t[:3, 3] - T_TCP_CAM[:3, 3]) < 2.0
    assert rot_angle_deg(t[:3, :3], T_TCP_CAM[:3, :3]) < 0.3


def test_solve_needs_three_poses() -> None:
    with pytest.raises(ValueError):
        solve([np.eye(4)] * 2, [np.eye(4)] * 2)


def test_board_pose_from_projected_corners() -> None:
    import cv2

    t_cam_board = cam_board(capture_poses(1, np.random.default_rng(2))[0])
    obj = board_object_points((10, 7), 25.0)
    rvec = cv2.Rodrigues(t_cam_board[:3, :3])[0]
    px, _ = cv2.projectPoints(obj, rvec, t_cam_board[:3, 3], K, np.zeros(5))
    t, err = board_pose(px.reshape(-1, 2), (10, 7), 25.0, K, None)
    assert err < 0.01
    assert np.linalg.norm(t[:3, 3] - t_cam_board[:3, 3]) < 0.01


def test_pixel_to_plane_roundtrip_and_invalid_rays() -> None:
    t_base_cam = capture_poses(1, np.random.default_rng(3))[0] @ T_TCP_CAM
    pts = np.array([[-130.0, -390.0, 101.0], [-90.0, -350.0, 101.0]])
    pc = (np.linalg.inv(t_base_cam) @ np.hstack([pts, np.ones((2, 1))]).T).T[:, :3]
    px = (K @ (pc / pc[:, 2:3]).T).T[:, :2]
    xyz, valid = pixel_to_plane(t_base_cam, K, None, px, 101.0)
    assert valid.all() and np.allclose(xyz, pts, atol=1e-6)
    # 카메라보다 높은 평면 → 광선이 뒤에서 만난다
    _, valid = pixel_to_plane(t_base_cam, K, None, px, t_base_cam[2, 3] + 50)
    assert not valid.any()


def test_interpolate_pose_midpoint_and_no_extrapolation() -> None:
    a = make_t(rot_zyz_deg(0, 180, 0), [0, 0, 300])
    b = make_t(rot_zyz_deg(0, 180, 20), [10, 0, 280])
    m = interpolate_pose(0.01, [0.0, 0.02], [a, b])
    assert np.allclose(m[:3, 3], [5, 0, 290])
    assert abs(rot_angle_deg(a[:3, :3], m[:3, :3]) - 10) < 1e-6
    assert interpolate_pose(0.03, [0.0, 0.02], [a, b]) is None  # 외삽 안 함
    assert interpolate_pose(0.05, [0.0, 0.1], [a, b]) is None  # 가까운 pose 가 50 ms 밖


def test_pose_msg_and_posx_agree() -> None:
    posx = [-14.49, -276.54, 203.58, 85.25, -179.07, -6.03]
    t = posx_to_t(posx)
    q = rot_to_quat(t[:3, :3])
    m = pose_msg_to_t(np.asarray(posx[:3]) / 1000.0, q)
    assert np.allclose(m, t, atol=1e-9)


def test_interpolate_pose_bounded_forward_extrapolation() -> None:
    """pose_lag 때문에 촬영 시각 + 지연의 pose 가 아직 없으면 최근 속도로 max_extrap_s 까지만 앞으로."""
    st = [i * 0.02 for i in range(6)]  # 50 Hz, 0~100 ms
    poses = [make_t(rot_zyz_deg(0, 180, 0), [48.0 * t, 0.0, 300.0]) for t in st]  # 48 mm/s
    m = interpolate_pose(0.16, st, poses, max_gap_s=0.04, max_extrap_s=0.08)
    assert np.allclose(m[:3, 3], [48.0 * 0.16, 0, 300], atol=1e-9)  # 60 ms 앞, 등속이면 정확
    assert rot_angle_deg(m[:3, :3], poses[-1][:3, :3]) < 1e-6
    assert interpolate_pose(0.19, st, poses, max_extrap_s=0.08) is None  # 90 ms > 80 ms
    assert interpolate_pose(0.12, st, poses) is None  # 기본은 외삽 안 함
    assert interpolate_pose(-0.01, st, poses, max_extrap_s=0.08) is None  # 뒤로는 안 함
    gap = st[:3] + [0.1, 0.12]  # 이력이 끊겼으면 속도를 믿지 않는다
    assert interpolate_pose(0.15, gap, poses[:5], max_extrap_s=0.08) is None


def test_correct_translation_recovers_optical_axis_offset() -> None:
    """보드 풀이가 광축 방향으로 10 mm 틀린 경우: 위치를 아는 점(터치) 몇 개로 되찾는다."""
    rng = np.random.default_rng(7)
    shift = np.array([0.5, -1.5, 10.0])  # 카메라 좌표 mm (광축 = z)
    wrong = T_TCP_CAM @ make_t(np.eye(3), -shift)
    obs = []
    for t_base_tcp in capture_poses(4, rng):
        t_base_cam = t_base_tcp @ T_TCP_CAM
        for _ in range(3):
            p = T_BASE_BOARD[:3, 3] + [rng.uniform(-40, 40), rng.uniform(-40, 40), 0.0]
            pc = np.linalg.inv(t_base_cam) @ np.append(p, 1.0)
            u, v = (K @ (pc[:3] / pc[2]))[:2]
            obs.append((t_base_tcp, (u, v), (p[0], p[1]), p[2]))
    assert plane_errors(wrong, K, None, obs).max() > 1.0
    x = correct_translation(wrong, K, None, obs)
    assert np.allclose(x, shift, atol=0.01)
    assert plane_errors(wrong @ make_t(np.eye(3), x), K, None, obs).max() < 1e-3
