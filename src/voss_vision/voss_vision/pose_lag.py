"""영상-pose 지연(`pose_lag_ms`) 측정 — ROS 없음, pytest 대상. T21(#30), calibration.md 이동 중 검증.

정지한 박스를 카메라(로봇)가 움직이며 볼 때 프레임마다 낸 박스 베이스 좌표는 원래 한 점이어야 한다.
box_tracker 와 같은 계산(촬영 시각 + lag 의 TCP pose 보간 → T_tcp_camera → 박스 윗면 평면 교점)으로 좌표를 낸 뒤
- 기준점 = 로봇이 서 있는 프레임 좌표의 중앙값. 서 있을 때는 pose 가 그대로라 lag 와 무관하다.
- 움직이는 프레임이 기준점에서 벗어난 정도(RMS·최대)를 lag 마다 재서 가장 작은 lag 를 고른다.
- 진행 방향 오차 ≈ 속도 × (lag − 실제 지연) 이라, 진행 방향 오차를 속도에 대해 맞춘 기울기로 남은 지연도
  바로 추정한다(`residual_ms`, sweep 결과 확인용 — 맞는 lag 에서 0 에 가깝다).
한 방향 이동만 있어도 된다 — 서 있는 프레임이 핸드아이 고정 오차를 잡고, 속도에 비례하는 부분만 지연이다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from voss_vision.hand_eye import interpolate_pose, pixel_to_plane

MOVING_MAX_MM = 5.0  # calibration.md 이동 중 검증 기준(제안값) — moving_verified 와 같은 값


@dataclass(frozen=True)
class Frame:
    t: float  # 촬영 시각(s, 영상 header.stamp)
    u: float  # 박스 윗면 중심 픽셀 (box_tracker 와 같은 검출·트래커)
    v: float


@dataclass(frozen=True)
class LagResult:
    lag_ms: float
    n_still: int  # 기준점을 만든 정지 프레임 수
    n_moving: int  # 평가한 이동 프레임 수
    ref_xy: tuple[float, float] | None  # 기준점(mm)
    still_max_mm: float  # 정지 프레임의 기준점 대비 최대(검출 잡음 수준)
    moving_rms_mm: float
    moving_max_mm: float
    residual_ms: float  # 이 lag 에 더하면 진행 방향 오차가 0 이 되는 지연(추정)


def tcp_speed(t: float, stamps, poses, half_s: float = 0.15) -> np.ndarray | None:
    """시각 t 앞뒤 half_s 의 TCP 위치 차이로 낸 속도(mm/s, xyz). 이력이 모자라면 None."""
    a = interpolate_pose(t - half_s, stamps, poses, max_gap_s=half_s, max_extrap_s=0.0)
    b = interpolate_pose(t + half_s, stamps, poses, max_gap_s=half_s, max_extrap_s=0.0)
    if a is None or b is None:
        return None
    return (b[:3, 3] - a[:3, 3]) / (2 * half_s)


def classify(frames, stamps, poses, still_mm_s: float = 2.0, moving_mm_s: float = 5.0):
    """프레임마다 (속도 벡터 또는 None, 'still'|'moving'|''). 촬영 시각 기준이라 lag 와 무관하다."""
    out = []
    for f in frames:
        vel = tcp_speed(f.t, stamps, poses)
        if vel is None:
            out.append((None, ""))
            continue
        s = float(np.linalg.norm(vel[:2]))
        out.append((vel, "still" if s < still_mm_s else "moving" if s >= moving_mm_s else ""))
    return out


def positions(frames, stamps, poses, t_tcp_camera, k, d, plane_z_mm, lag_s,
              max_gap_s=0.04, max_extrap_s=0.08) -> np.ndarray:  # fmt: skip
    """box_tracker._pose_at + _fill_position 과 같은 계산. (N, 2) mm, 못 낸 프레임은 nan."""
    xy = np.full((len(frames), 2), np.nan)
    for i, f in enumerate(frames):
        t = interpolate_pose(f.t + lag_s, stamps, poses, max_gap_s, max_extrap_s)
        if t is None:
            continue
        p, ok = pixel_to_plane(t @ t_tcp_camera, k, d, [[f.u, f.v]], plane_z_mm)
        if ok[0]:
            xy[i] = p[0, :2]
    return xy


def evaluate(frames, labels, stamps, poses, t_tcp_camera, k, d, plane_z_mm, lag_s,
             max_gap_s=0.04, max_extrap_s=0.08) -> LagResult:  # fmt: skip
    """한 lag 의 결과. labels = classify() 결과(모든 lag 에 같은 것을 쓴다)."""
    xy = positions(frames, stamps, poses, t_tcp_camera, k, d, plane_z_mm, lag_s, max_gap_s,
                   max_extrap_s)  # fmt: skip
    still = np.array([lab == "still" for _, lab in labels]) & ~np.isnan(xy[:, 0])
    moving = np.array([lab == "moving" for _, lab in labels]) & ~np.isnan(xy[:, 0])
    lag_ms = lag_s * 1000.0
    if not still.any():
        return LagResult(lag_ms, 0, int(moving.sum()), None, np.nan, np.nan, np.nan, np.nan)
    ref = np.median(xy[still], axis=0)
    still_err = np.linalg.norm(xy[still] - ref, axis=1)
    if not moving.any():
        return LagResult(lag_ms, int(still.sum()), 0, (float(ref[0]), float(ref[1])),
                         float(still_err.max()), np.nan, np.nan, np.nan)  # fmt: skip
    err = xy[moving] - ref
    dist = np.linalg.norm(err, axis=1)
    vel = np.array([labels[i][0][:2] for i in np.flatnonzero(moving)])
    speed = np.linalg.norm(vel, axis=1)
    along = np.einsum("ij,ij->i", err, vel / speed[:, None])  # 진행 방향 성분(mm)
    # along ≈ speed × (lag − 실제 지연) → 실제 지연 − lag = −Σ(along·speed)/Σ(speed²)
    residual_s = -float(np.sum(along * speed) / np.sum(speed**2))
    return LagResult(
        lag_ms,
        int(still.sum()),
        int(moving.sum()),
        (float(ref[0]), float(ref[1])),
        float(still_err.max()),
        float(np.sqrt(np.mean(dist**2))),
        float(dist.max()),
        residual_s * 1000.0,
    )


def sweep(frames, stamps, poses, t_tcp_camera, k, d, plane_z_mm, lags_ms,
          max_gap_s=0.04, max_extrap_s=0.08) -> list[LagResult]:  # fmt: skip
    labels = classify(frames, stamps, poses)
    return [
        evaluate(
            frames,
            labels,
            stamps,
            poses,
            t_tcp_camera,
            k,
            d,
            plane_z_mm,
            lag / 1000.0,
            max_gap_s,
            max_extrap_s,
        )  # fmt: skip
        for lag in lags_ms
    ]


def best(results: list[LagResult]) -> LagResult | None:
    """이동 프레임 RMS 가 가장 작은 lag. 이동 프레임이 없으면 None."""
    ok = [r for r in results if r.n_moving and not np.isnan(r.moving_rms_mm)]
    return min(ok, key=lambda r: r.moving_rms_mm) if ok else None


def value_update_interval_s(stamps, poses, eps_mm: float = 0.01) -> float | None:
    """pose 값이 실제로 바뀌는 간격의 중앙값(s). 메시지는 50 Hz 여도 값이 0.1 s 마다만 바뀌면 0.1 (#118)."""
    t_change = [stamps[i] for i in range(1, len(stamps))
                if np.linalg.norm(poses[i][:3, 3] - poses[i - 1][:3, 3]) > eps_mm]  # fmt: skip
    if len(t_change) < 3:
        return None
    return float(np.median(np.diff(t_change)))
