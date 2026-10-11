"""pose_lag — 지연을 넣은 합성 이동(정지 → +x 20 mm/s → 정지 → +x 48 mm/s → 정지)에서 그 지연을 되찾는지."""

import numpy as np
import pytest
from voss_vision.hand_eye import make_t, pixel_to_plane, posx_to_t
from voss_vision.pose_lag import Frame, best, classify, sweep, value_update_interval_s

K = np.array([[1367.46, 0.0, 978.51], [0.0, 1367.72, 552.04], [0.0, 0.0, 1.0]])
T_TCP_CAM = make_t(np.eye(3), np.array([30.22, 75.90, -210.67]))  # 10/08 위치, 회전은 단순화
OBSERVE = [-14.49, -276.54, 203.58, 85.25, -179.07, -6.03]  # 관측 자세 TCP posx
PLANE_Z = 100.8
SEGMENTS = [(1.0, 0.0), (2.0, 20.0), (1.0, 0.0), (0.8, 48.0), (1.2, 0.0)]  # (s, +x mm/s)


def x_offset(t: float) -> float:
    x, t0 = 0.0, 0.0
    for dur, v in SEGMENTS:
        x += v * min(max(t - t0, 0.0), dur)
        t0 += dur
    return x


def tcp_true(t: float) -> np.ndarray:
    p = list(OBSERVE)
    p[0] += x_offset(t)
    return posx_to_t(p)


def make_data(delay_s: float, hold_s: float = 0.0, noise_px: float = 0.3, seed: int = 0):
    """박스 한 점(관측 자세에서 화면 (1135, 518))을 30 Hz 로 찍고, pose 는 50 Hz 에 stamp 가 delay_s 늦다.
    hold_s > 0 이면 pose 값이 그 간격으로만 바뀐다(service 0.1 s 계단, #118)."""
    p_box, _ = pixel_to_plane(tcp_true(0.0) @ T_TCP_CAM, K, None, [[1135.0, 518.0]], PLANE_Z)
    p_box = np.append(p_box[0], 1.0)
    end = sum(d for d, _ in SEGMENTS)
    rng = np.random.default_rng(seed)
    frames = []
    for t in np.arange(0.0, end, 1 / 30):
        pc = np.linalg.inv(tcp_true(t) @ T_TCP_CAM) @ p_box
        u = K[0, 0] * pc[0] / pc[2] + K[0, 2] + rng.normal(0, noise_px)
        v = K[1, 1] * pc[1] / pc[2] + K[1, 2] + rng.normal(0, noise_px)
        frames.append(Frame(float(t), float(u), float(v)))
    stamps, poses = [], []
    for tau in np.arange(-0.5, end + 0.5, 0.02):
        actual = tau - delay_s
        if hold_s:
            actual = np.floor(actual / hold_s) * hold_s
        stamps.append(float(tau))
        poses.append(tcp_true(actual))
    return frames, stamps, poses, p_box[:2]


def run(frames, stamps, poses, lags=range(0, 125, 5)):
    return sweep(frames, stamps, poses, T_TCP_CAM, K, None, PLANE_Z, list(lags))


def test_finds_the_injected_lag() -> None:
    frames, stamps, poses, truth = make_data(delay_s=0.060)
    res = run(frames, stamps, poses)
    b = best(res)
    assert b is not None and abs(b.lag_ms - 60) <= 5
    assert b.moving_max_mm < 1.0 and b.still_max_mm < 0.5
    assert np.hypot(b.ref_xy[0] - truth[0], b.ref_xy[1] - truth[1]) < 0.3  # 정지 기준점 = 실제 위치
    lag0 = next(r for r in res if r.lag_ms == 0)
    assert lag0.moving_max_mm > 2.0  # 보정 없으면 48 mm/s × 60 ms ≈ 2.9 mm 어긋난다
    assert lag0.residual_ms == pytest.approx(60, abs=5)  # 기울기로도 같은 지연


def test_zero_lag_source_gives_zero() -> None:
    """joint_states 처럼 stamp 가 측정 시각이면 0 근처가 나와야 한다."""
    b = best(run(*make_data(delay_s=0.0)[:3], lags=range(-20, 65, 5)))
    assert b is not None and abs(b.lag_ms) <= 5


def test_classify_one_way_motion() -> None:
    frames, stamps, poses, _ = make_data(delay_s=0.060)
    labels = [lab for _, lab in classify(frames, stamps, poses)]
    assert labels.count("still") > 60 and labels.count("moving") > 60


def test_staircase_pose_is_reported_and_worse() -> None:
    """값이 0.1 s 마다만 바뀌면(#118 service) 갱신 간격이 0.1 로 나오고 이동 중 오차가 커진다."""
    frames, stamps, poses, _ = make_data(delay_s=0.060, hold_s=0.1)
    assert value_update_interval_s(stamps, poses) == pytest.approx(0.1, abs=0.01)
    smooth = best(run(*make_data(delay_s=0.060)[:3]))
    stair = best(run(frames, stamps, poses))
    assert stair.moving_max_mm > smooth.moving_max_mm + 1.0
