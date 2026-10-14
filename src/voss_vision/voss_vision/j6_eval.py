"""J6 회전 시 핸드아이 오차·박스 yaw 측정 (S2-T16, BRD v1.5 R-28·TR-SERVO-06) — ROS 없음, pytest 대상.

박스를 벨트 위에 세워 두고(벨트 정지) 관측 자세에서 J6 만 돌려 각도마다 약 3 s 멈춘 녹화를 쓴다.
박스는 그대로라 J6 각마다 낸 박스 베이스 좌표·yaw 는 같아야 한다 — 기준 구간(J6 각이 가장 작은 정지 구간)
대비 차이가 J6 회전 때의 핸드아이 오차다. 기준 구간이 관측 자세면 호모그래피(독립 캘리브레이션) 값과도 비교한다.

- 정지 판정은 병진·회전 둘 다 본다. J6 만 돌리면 TCP 점은 그대로라 병진 속도만으로는 회전 중 프레임이 정지로 잡힌다.
- 계산은 box_tracker 와 같다: 촬영 시각 + lag 의 TCP pose 보간 → T_tcp_camera → 박스 윗면 평면 교점,
  yaw 는 송장 긴 변 양 끝(Detection.half_axis)을 같은 변환으로 옮긴 각(tracker_logic.yaw_from_ends).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from voss_vision.belt_plane import pixel_to_base_xy
from voss_vision.hand_eye import interpolate_pose, pixel_to_plane
from voss_vision.tracker_logic import fold_yaw, yaw_from_ends

POS_MAX_MM = 5.0  # 핸드아이 검증점 기준(제안값, calibration.md) — J6 각마다 기준 구간 대비
YAW_MAX_DEG = (
    2.0  # belt_servo J6 데드밴드(TR-SERVO-05 2°) — 이보다 크면 회전량을 믿기 어렵다 (제안값)
)


@dataclass(frozen=True)
class YawFrame:
    t: float  # 촬영 시각(s)
    u: float  # 송장 중심 픽셀 (box_tracker 와 같은 검출·트래커)
    v: float
    half_axis: tuple[float, float] | None  # 중심 → 송장 긴 변 끝 (Detection.half_axis)


@dataclass(frozen=True)
class Hold:
    j6_deg: float  # 녹화 첫 pose 대비 공구축(z) 둘레 회전(deg) — 구간 중앙값
    idx: tuple[int, ...]  # 이 구간 프레임 번호


@dataclass(frozen=True)
class HoldResult:
    j6_deg: float
    n: int  # 구간 프레임
    n_valid: int  # 좌표·yaw 를 모두 낸 프레임
    x: float  # mm, 구간 중앙값
    y: float
    yaw_deg: float
    spread_mm: float  # 구간 안 흔들림(중앙값에서 최대 거리) — 검출 잡음 수준
    spread_deg: float
    dpos_mm: float  # 기준 구간 대비
    dyaw_deg: float


def tool_z_angle_deg(t_ref: np.ndarray, t: np.ndarray) -> float:
    """t 가 t_ref 에서 공구축(z) 둘레로 돈 각(deg, (−180, 180]). J6 만 돌릴 때의 J6 각."""
    r = t_ref[:3, :3].T @ t[:3, :3]
    return math.degrees(math.atan2(r[1, 0], r[0, 0]))


def yaw_diff_deg(a_rad: float, b_rad: float) -> float:
    """두 yaw 의 차(deg, (−90, 90]) — 180° 대칭이라 접어서 뺀다."""
    return math.degrees(fold_yaw(a_rad - b_rad))


def pose_rates(t: float, stamps, poses, half_s: float = 0.15) -> tuple[float, float] | None:
    """시각 t 앞뒤 half_s 의 (TCP 병진 mm/s, 회전 deg/s). 이력이 모자라면 None."""
    a = interpolate_pose(t - half_s, stamps, poses, max_gap_s=half_s, max_extrap_s=0.0)
    b = interpolate_pose(t + half_s, stamps, poses, max_gap_s=half_s, max_extrap_s=0.0)
    if a is None or b is None:
        return None
    lin = float(np.linalg.norm(b[:3, 3] - a[:3, 3])) / (2 * half_s)
    c = float(np.clip((np.trace(a[:3, :3].T @ b[:3, :3]) - 1.0) / 2.0, -1.0, 1.0))
    return lin, math.degrees(math.acos(c)) / (2 * half_s)


def find_holds(frames, stamps, poses, still_mm_s: float = 2.0, still_deg_s: float = 1.0,
               min_s: float = 1.0, same_deg: float = 1.0) -> list[Hold]:  # fmt: skip
    """병진·회전이 모두 느린 프레임이 min_s 넘게 이어지고 J6 각이 same_deg 안인 구간들(시간순)."""
    if not frames or not poses:
        return []
    t0 = poses[0]
    holds: list[Hold] = []
    run: list[tuple[int, float]] = []

    def close() -> None:
        if run and frames[run[-1][0]].t - frames[run[0][0]].t >= min_s:
            holds.append(Hold(float(np.median([a for _, a in run])), tuple(i for i, _ in run)))
        run.clear()

    for i, f in enumerate(frames):
        r = pose_rates(f.t, stamps, poses)
        p = interpolate_pose(f.t, stamps, poses, max_gap_s=0.15, max_extrap_s=0.0)
        if r is None or p is None or r[0] >= still_mm_s or r[1] >= still_deg_s:
            close()
            continue
        ang = tool_z_angle_deg(t0, p)
        if run and abs(ang - run[0][1]) > same_deg:
            close()
        run.append((i, ang))
    close()
    return holds


def measure(frames, stamps, poses, t_tcp_camera, k, d, plane_z_mm, lag_s,
            max_gap_s=0.04, max_extrap_s=0.08) -> np.ndarray:  # fmt: skip
    """프레임마다 (x mm, y mm, yaw rad) — box_tracker._pose_at + _fill_position 과 같은 계산. 못 내면 nan
    (각도 없는 검출·끝점 무효면 yaw 만 nan)."""
    out = np.full((len(frames), 3), np.nan)
    for i, f in enumerate(frames):
        t = interpolate_pose(f.t + lag_s, stamps, poses, max_gap_s, max_extrap_s)
        if t is None:
            continue
        px = [[f.u, f.v]]
        if f.half_axis is not None:
            hx, hy = f.half_axis
            px += [[f.u - hx, f.v - hy], [f.u + hx, f.v + hy]]
        p, ok = pixel_to_plane(t @ t_tcp_camera, k, d, px, plane_z_mm)
        if not ok[0]:
            continue
        out[i, :2] = p[0, :2]
        if len(px) == 3 and ok[1] and ok[2]:
            yaw = yaw_from_ends(p[1], p[2])
            out[i, 2] = np.nan if yaw is None else yaw
    return out


def measure_homography(frames, calib: dict) -> np.ndarray:
    """관측 자세 프레임의 호모그래피 (x, y, yaw) — 비교용. 유효 영역 밖은 nan."""
    out = np.full((len(frames), 3), np.nan)
    for i, f in enumerate(frames):
        px = [[f.u, f.v]]
        if f.half_axis is not None:
            hx, hy = f.half_axis
            px += [[f.u - hx, f.v - hy], [f.u + hx, f.v + hy]]
        xy, ok = pixel_to_base_xy(calib, np.array(px, float))
        if not ok[0]:
            continue
        out[i, :2] = xy[0]
        if len(px) == 3 and ok[1] and ok[2]:
            yaw = yaw_from_ends(xy[1], xy[2])
            out[i, 2] = np.nan if yaw is None else yaw
    return out


def median_xy_yaw(values: np.ndarray) -> tuple[float, float, float, float, float, int]:
    """(N, 3) → (x, y, yaw rad, 흔들림 mm, 흔들림 deg, 유효 수). yaw 는 첫 유효값 기준 차로 접어 중앙값(±90° 경계)."""
    ok = np.isfinite(values).all(axis=1)
    v = values[ok]
    if len(v) == 0:
        return (math.nan,) * 5 + (0,)
    x, y = float(np.median(v[:, 0])), float(np.median(v[:, 1]))
    rel = np.array([fold_yaw(a - v[0, 2]) for a in v[:, 2]])
    yaw = fold_yaw(v[0, 2] + float(np.median(rel)))
    spread_mm = float(np.max(np.hypot(v[:, 0] - x, v[:, 1] - y)))
    spread_deg = float(max(abs(yaw_diff_deg(a, yaw)) for a in v[:, 2]))
    return x, y, yaw, spread_mm, spread_deg, int(ok.sum())


def summarize(holds: list[Hold], values: np.ndarray, ref: int | None = None) -> list[HoldResult]:
    """구간마다 중앙값과 기준 구간 대비 차. 기준 = ref(관측 자세 구간), 없으면 |J6| 가장 작은 유효 구간.
    J6 각도 기준 구간 대비로 고쳐 낸다. 유효 프레임이 없는 구간은 nan."""
    stats = [median_xy_yaw(values[list(h.idx)]) for h in holds]
    usable = [i for i, s in enumerate(stats) if s[5] > 0]
    if not usable:
        return []
    r = ref if ref in usable else min(usable, key=lambda i: abs(holds[i].j6_deg))
    rx, ry, ryaw = stats[r][:3]
    rj6 = holds[r].j6_deg
    out = []
    for h, (x, y, yaw, smm, sdeg, n_ok) in zip(holds, stats, strict=True):
        dpos = math.hypot(x - rx, y - ry) if n_ok else math.nan
        dyaw = yaw_diff_deg(yaw, ryaw) if n_ok else math.nan
        out.append(HoldResult(h.j6_deg - rj6, len(h.idx), n_ok, x, y, math.degrees(yaw) if n_ok else math.nan,
                              smm, sdeg, dpos, dyaw))  # fmt: skip
    return out


def passed(results: list[HoldResult]) -> bool:
    """유효 구간이 둘 이상이고 모두 Δ위치 ≤ POS_MAX_MM·|Δyaw| ≤ YAW_MAX_DEG."""
    ok = [r for r in results if r.n_valid > 0]
    return len(ok) >= 2 and all(
        r.dpos_mm <= POS_MAX_MM and abs(r.dyaw_deg) <= YAW_MAX_DEG for r in ok
    )
