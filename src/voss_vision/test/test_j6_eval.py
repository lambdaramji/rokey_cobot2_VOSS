"""j6_eval (S2-T16) — 합성 녹화: 관측 자세에서 J6 만 0→15→30→45° 로 돌리며 3 s 씩 멈춘다, 박스는 그대로.

맞는 핸드아이면 J6 각마다 좌표·yaw 가 같고, 카메라 위치가 틀린 핸드아이면 J6 각이 커질수록 벌어진다.
"""

import math

import cv2
import numpy as np
import pytest
from voss_vision.belt_plane import rot_zyz_deg
from voss_vision.hand_eye import make_t
from voss_vision.j6_eval import (
    YawFrame,
    find_holds,
    measure,
    measure_homography,
    median_xy_yaw,
    passed,
    summarize,
    tool_z_angle_deg,
    yaw_diff_deg,
)

K = np.array([[1367.5, 0, 978.5], [0, 1367.7, 552.0], [0, 0, 1]])
T_TCP_CAM = make_t(rot_zyz_deg(30, 22, -100), [-16.0, -44.0, -208.0])
T_OBS = make_t(rot_zyz_deg(0, 180, 0), [-110.0, -380.0, 351.0])
PLANE_Z = 101.0
BOX_C, BOX_YAW = np.array([-110.0, -385.0, PLANE_Z]), 30.0
J6_STEPS = [0.0, 15.0, 30.0, 45.0]
HOLD_S, TURN_DEG_S = 3.0, 15.0


def j6_at(t: float) -> float:
    """시각 t 의 J6 각: 3 s 정지 → 15°/s 로 15° 회전(1 s) → 3 s 정지 …"""
    seg = HOLD_S + 15.0 / TURN_DEG_S
    i = int(t // seg)
    if i >= len(J6_STEPS) - 1:
        return J6_STEPS[-1]
    dt = t - i * seg
    return J6_STEPS[i] + max(0.0, dt - HOLD_S) * TURN_DEG_S


def tcp(t: float) -> np.ndarray:
    return T_OBS @ make_t(rot_zyz_deg(j6_at(t), 0, 0), [0, 0, 0])


def recording(duration: float = 15.5):
    stamps = list(np.arange(0.0, duration, 0.02))  # pose 50 Hz
    poses = [tcp(t) for t in stamps]
    a = math.radians(BOX_YAW)
    d = 20 * np.array([math.cos(a), math.sin(a), 0.0])
    ends = np.array([BOX_C - d, BOX_C + d])
    frames = []
    for t in np.arange(0.2, duration - 0.2, 1 / 30):  # 영상 30 Hz
        cam = tcp(t) @ T_TCP_CAM
        pc = (np.linalg.inv(cam) @ np.hstack([ends, np.ones((2, 1))]).T).T[:, :3]
        px = (K @ (pc / pc[:, 2:3]).T).T[:, :2]
        (u, v), half = px.mean(0), (px[1] - px[0]) / 2
        frames.append(YawFrame(float(t), float(u), float(v), (float(half[0]), float(half[1]))))
    return frames, stamps, poses


def run(t_tcp_cam: np.ndarray):
    frames, stamps, poses = recording()
    holds = find_holds(frames, stamps, poses)
    vals = measure(frames, stamps, poses, t_tcp_cam, K, None, PLANE_Z, 0.0)
    return holds, summarize(holds, vals)


def test_holds_are_the_four_j6_stops_and_skip_turning_frames() -> None:
    frames, stamps, poses = recording()
    holds = find_holds(frames, stamps, poses)
    assert [round(h.j6_deg) for h in holds] == [0, 15, 30, 45]
    for h in holds:
        assert all(abs(j6_at(frames[i].t) - h.j6_deg) < 0.01 for i in h.idx)  # 회전 중 프레임 없음


def test_true_hand_eye_gives_same_box_at_every_j6() -> None:
    _, res = run(T_TCP_CAM)
    assert [round(r.j6_deg) for r in res] == [0, 15, 30, 45]
    for r in res:
        assert r.n_valid == r.n > 60
        # 픽셀 중점은 원근 때문에 3D 중심의 투영과 조금 어긋나 J6 각마다 다르다(45° 에서 약 0.26 mm).
        # box_tracker 도 픽셀 중심을 쓰므로 그대로 두고 기준 5 mm 의 1/10 로 본다
        assert r.dpos_mm < 0.5 and abs(r.dyaw_deg) < 0.01
        assert r.yaw_deg == pytest.approx(BOX_YAW, abs=0.01)
    assert passed(res)


def test_wrong_camera_position_grows_with_j6() -> None:
    """핸드아이 카메라 위치가 공구축 옆으로 4 mm 틀리면 J6 θ 에서 약 2·4·sin(θ/2) mm 벌어진다."""
    wrong = T_TCP_CAM.copy()
    wrong[:3, 3] += [4.0, 0.0, 0.0]
    _, res = run(wrong)
    d = [r.dpos_mm for r in res]
    assert d[0] == 0.0 and d[1] < d[2] < d[3]
    assert d[3] == pytest.approx(2 * 4 * math.sin(math.radians(22.5)), rel=0.2)
    assert passed(res)  # 3 mm 정도는 기준(5 mm) 안
    far = T_TCP_CAM.copy()
    far[:3, 3] += [12.0, 0.0, 0.0]
    assert not passed(run(far)[1])


def test_yaw_median_across_the_90_degree_fold() -> None:
    v = np.array([[0.0, 0.0, math.radians(89.9)], [0.0, 0.0, math.radians(-89.9)]] * 5)
    _, _, yaw, _, spread_deg, n = median_xy_yaw(v)
    assert n == 10 and abs(yaw_diff_deg(yaw, math.radians(90))) < 0.2 and spread_deg < 0.3


def test_tool_z_angle_and_yaw_diff() -> None:
    assert tool_z_angle_deg(T_OBS, T_OBS @ make_t(rot_zyz_deg(30, 0, 0), [0, 0, 0])) == (
        pytest.approx(30.0)
    )
    assert yaw_diff_deg(math.radians(89), math.radians(-89)) == pytest.approx(-2.0)


def test_homography_at_observe_pose_agrees_with_hand_eye() -> None:
    """관측 자세 픽셀 → 평면 H 를 같은 카메라로 만들면 호모그래피 값과 핸드아이 값이 같다(비교 경로 확인)."""
    cam = T_OBS @ T_TCP_CAM
    grid = np.array(
        [[x, y, PLANE_Z] for x in (-160, -60) for y in (-430, -340)] + [[-110, -385, PLANE_Z]]
    )
    pc = (np.linalg.inv(cam) @ np.hstack([grid, np.ones((len(grid), 1))]).T).T[:, :3]
    px = (K @ (pc / pc[:, 2:3]).T).T[:, :2]
    h, _ = cv2.findHomography(px, grid[:, :2])
    calib = {"H_px_to_base_xy": h.tolist()}
    frames, stamps, poses = recording()
    first = find_holds(frames, stamps, poses)[0]
    sel = [frames[i] for i in first.idx]
    homo = median_xy_yaw(measure_homography(sel, calib))
    he = median_xy_yaw(measure(sel, stamps, poses, T_TCP_CAM, K, None, PLANE_Z, 0.0))
    assert math.hypot(homo[0] - he[0], homo[1] - he[1]) < 0.01
    assert abs(yaw_diff_deg(homo[2], he[2])) < 0.01
