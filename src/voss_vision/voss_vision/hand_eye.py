"""핸드아이(Eye-in-Hand): TCP → 카메라 변환 풀이와 픽셀 → 박스 윗면 좌표 (docs/interfaces/calibration.md).

ROS 없는 순수 함수. 길이는 mm, 변환은 4×4 동차 행렬. `T_a_b` 는 b 좌표의 점을 a 좌표로 바꾼다
(p_a = T_a_b · p_b). 깊이는 쓰지 않는다 — 광선과 알려진 박스 윗면 평면의 교점으로 위치를 구한다.
"""

import cv2
import numpy as np

from voss_vision.belt_plane import rot_zyz_deg

# PARK 채택(강의와 같음). 비교는 PARK·HORAUD·ANDREFF — TSAI·DANIILIDIS 는 자세 사이 회전이 크면
# (공구축 ±60°) 노이즈 없는 합성 데이터에서도 1~2 mm 어긋난다(test_hand_eye).
COMPARE = ("PARK", "HORAUD", "ANDREFF")
METHODS = {
    "TSAI": cv2.CALIB_HAND_EYE_TSAI,
    "PARK": cv2.CALIB_HAND_EYE_PARK,
    "HORAUD": cv2.CALIB_HAND_EYE_HORAUD,
    "ANDREFF": cv2.CALIB_HAND_EYE_ANDREFF,
    "DANIILIDIS": cv2.CALIB_HAND_EYE_DANIILIDIS,
}


def make_t(r: np.ndarray, t: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    out[:3, :3] = r
    out[:3, 3] = np.asarray(t, dtype=float).reshape(3)
    return out


def quat_to_rot(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    q = np.array([qw, qx, qy, qz], dtype=float)
    w, x, y, z = q / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def rot_to_quat(r: np.ndarray) -> np.ndarray:
    """회전 행렬 → (x, y, z, w), w ≥ 0."""
    m = np.asarray(r, dtype=float)
    k = np.array(
        [
            [m[0, 0] - m[1, 1] - m[2, 2], m[1, 0] + m[0, 1], m[2, 0] + m[0, 2], m[2, 1] - m[1, 2]],
            [m[1, 0] + m[0, 1], m[1, 1] - m[0, 0] - m[2, 2], m[2, 1] + m[1, 2], m[0, 2] - m[2, 0]],
            [m[2, 0] + m[0, 2], m[2, 1] + m[1, 2], m[2, 2] - m[0, 0] - m[1, 1], m[1, 0] - m[0, 1]],
            [m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1], m[0, 0] + m[1, 1] + m[2, 2]],
        ]
    )
    w, v = np.linalg.eigh(k / 3.0)
    q = v[:, np.argmax(w)]
    return q if q[3] >= 0 else -q


def pose_msg_to_t(position_m, quat_xyzw) -> np.ndarray:
    """geometry_msgs Pose(위치 m, 쿼터니언 x y z w) → T(mm)."""
    return make_t(quat_to_rot(*quat_xyzw), np.asarray(position_m, dtype=float) * 1000.0)


def posx_to_t(posx) -> np.ndarray:
    """두산 posx [x y z mm, rx ry rz deg, ZYZ] → T(mm)."""
    p = np.asarray(posx, dtype=float)
    return make_t(rot_zyz_deg(*p[3:6]), p[:3])


def rot_angle_deg(ra: np.ndarray, rb: np.ndarray) -> float:
    c = (np.trace(np.asarray(ra).T @ np.asarray(rb)) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def board_object_points(inner_corners: tuple[int, int], square_mm: float) -> np.ndarray:
    """보드 좌표의 내부 코너 (N, 3) mm. findChessboardCorners 와 같은 순서(행 우선, 가로 c개)."""
    c, r = inner_corners
    g = np.mgrid[0:c, 0:r].T.reshape(-1, 2) * float(square_mm)
    return np.hstack([g, np.zeros((len(g), 1))]).astype(np.float32)


def board_pose(
    corners_px: np.ndarray, inner_corners, square_mm: float, k: np.ndarray, d
) -> tuple[np.ndarray, float]:
    """검출된 코너 → T_cam_board(mm), 최대 재투영 오차(px)."""
    obj = board_object_points(inner_corners, square_mm)
    px = np.asarray(corners_px, dtype=np.float32).reshape(-1, 1, 2)
    dist = np.zeros(5) if d is None else np.asarray(d, dtype=float)
    ok, rvec, tvec = cv2.solvePnP(obj, px, k, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError("solvePnP 실패")
    proj, _ = cv2.projectPoints(obj, rvec, tvec, k, dist)
    err = float(np.max(np.linalg.norm(proj.reshape(-1, 2) - px.reshape(-1, 2), axis=1)))
    return make_t(cv2.Rodrigues(rvec)[0], tvec), err


def solve(t_base_tcp: list[np.ndarray], t_cam_board: list[np.ndarray], method: str = "PARK"):
    """AX = XB 풀이 → T_tcp_camera(mm). 입력은 자세마다 (베이스→TCP, 카메라→보드)."""
    if len(t_base_tcp) != len(t_cam_board) or len(t_base_tcp) < 3:
        raise ValueError("자세 3개 이상, 두 목록 길이가 같아야 한다")
    r, t = cv2.calibrateHandEye(
        [a[:3, :3] for a in t_base_tcp],
        [a[:3, 3] for a in t_base_tcp],
        [b[:3, :3] for b in t_cam_board],
        [b[:3, 3] for b in t_cam_board],
        method=METHODS[method],
    )
    return make_t(r, t)


def mean_pose(ts: list[np.ndarray]) -> np.ndarray:
    """위치 평균 + 회전 평균(SVD 투영)."""
    rs = sum(a[:3, :3] for a in ts)
    u, _, vt = np.linalg.svd(rs)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return make_t(r, np.mean([a[:3, 3] for a in ts], axis=0))


def spread(ts: list[np.ndarray]) -> tuple[float, float]:
    """평균 자세에서 가장 먼 위치(mm)·각(°). 같은 물체를 여러 번 잰 값이 얼마나 흩어지는지."""
    m = mean_pose(ts)
    d = max(float(np.linalg.norm(a[:3, 3] - m[:3, 3])) for a in ts)
    ang = max(rot_angle_deg(a[:3, :3], m[:3, :3]) for a in ts)
    return d, ang


def board_in_base(t_base_tcp, t_tcp_camera, t_cam_board) -> list[np.ndarray]:
    """자세마다 계산한 베이스→보드. 보드는 고정이라 핸드아이가 맞으면 모두 같아야 한다."""
    return [a @ t_tcp_camera @ b for a, b in zip(t_base_tcp, t_cam_board, strict=True)]


def pixel_to_plane(
    t_base_camera: np.ndarray, k: np.ndarray, d, px, plane_z_mm: float, max_angle_deg: float = 75.0
) -> tuple[np.ndarray, np.ndarray]:
    """픽셀 (N, 2) → 베이스 z = plane_z_mm 평면 위 점 (N, 3) mm, 유효 여부 (N,).

    광선이 평면과 거의 평행하거나(평면 법선과 max_angle_deg 초과) 카메라 뒤에서 만나면 무효.
    """
    px = np.asarray(px, dtype=float).reshape(-1, 1, 2)
    dist = np.zeros(5) if d is None else np.asarray(d, dtype=float)
    n = cv2.undistortPoints(px, np.asarray(k, dtype=float), dist).reshape(-1, 2)
    rays = (t_base_camera[:3, :3] @ np.hstack([n, np.ones((len(n), 1))]).T).T
    o = t_base_camera[:3, 3]
    dz = rays[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (plane_z_mm - o[2]) / dz
    cos = np.abs(dz) / np.linalg.norm(rays, axis=1)
    valid = (s > 0) & (cos >= np.cos(np.radians(max_angle_deg)))
    pts = o + rays * np.where(valid, s, 0.0)[:, None]
    pts[~valid] = np.nan
    return pts, valid


def _slerp(qa: np.ndarray, qb: np.ndarray, a: float) -> np.ndarray:
    if qa @ qb < 0:
        qb = -qb
    dot = float(np.clip(qa @ qb, -1.0, 1.0))
    if dot > 0.9995:
        q = qa + a * (qb - qa)
        return q / np.linalg.norm(q)
    th = np.arccos(dot)
    return (np.sin((1 - a) * th) * qa + np.sin(a * th) * qb) / np.sin(th)


def interpolate_pose(
    t: float, stamps, poses: list[np.ndarray], max_gap_s: float = 0.04, max_extrap_s: float = 0.0
):
    """시각 t 의 T_base_tcp — 위치 선형, 자세 slerp.

    stamps 는 오름차순(초). 범위 안이면 보간하되 가장 가까운 pose 가 max_gap_s 보다 멀거나 앞뒤 pose 사이가
    2·max_gap_s 보다 길면 None.
    t 가 마지막 pose 보다 뒤면 max_extrap_s 까지만 **앞으로 외삽**한다(최근 pose 몇 개의 속도, 끊김 없을 때만).
    마지막 pose 보다 max_extrap_s 넘게 뒤거나 첫 pose 보다 앞이면 None (calibration.md: pose_lag 때문에
    촬영 시각 + 지연의 pose 가 아직 안 왔을 때 기다리지 않으려고 쓴다).
    """
    st = np.asarray(stamps, dtype=float)
    if len(st) == 0 or t < st[0]:
        return None
    if t > st[-1]:
        return _extrapolate(t, st, poses, max_gap_s, max_extrap_s)
    i = int(np.searchsorted(st, t, side="right")) - 1
    i = min(i, len(st) - 2) if len(st) > 1 else 0
    if len(st) == 1:
        return poses[0] if abs(t - st[0]) <= max_gap_s else None
    t0, t1 = st[i], st[i + 1]
    if min(t - t0, t1 - t) > max_gap_s or t1 - t0 > 2 * max_gap_s:
        return None  # 가까운 pose 가 멀거나, pose 가 끊긴 긴 구간을 선형으로 메우지 않는다
    a = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
    pa, pb = poses[i], poses[i + 1]
    q = _slerp(rot_to_quat(pa[:3, :3]), rot_to_quat(pb[:3, :3]), a)
    return make_t(quat_to_rot(*q), (1 - a) * pa[:3, 3] + a * pb[:3, 3])


EXTRAP_SPAN = 5  # 외삽 속도를 재는 최근 pose 수 (50 Hz 면 80 ms)


def _extrapolate(t: float, st: np.ndarray, poses, max_gap_s: float, max_extrap_s: float):
    dt = t - st[-1]
    if dt > max_extrap_s:
        return None
    if dt <= 1e-9 or len(st) == 1:
        return poses[-1] if dt <= max_gap_s else None
    k = min(EXTRAP_SPAN, len(st))
    seg = st[-k:]
    if np.max(np.diff(seg)) > max_gap_s:  # 끊긴 이력으로는 속도를 믿지 않는다
        return None
    ta, pa, pb = seg[0], poses[-k], poses[-1]
    a = 1.0 + dt / (st[-1] - ta)  # pa→pb 를 같은 빠르기로 dt 만큼 더 간다
    q = _slerp(rot_to_quat(pa[:3, :3]), rot_to_quat(pb[:3, :3]), a)
    return make_t(quat_to_rot(*q), pb[:3, 3] + (pb[:3, 3] - pa[:3, 3]) * dt / (st[-1] - ta))


def plane_errors(t_tcp_camera: np.ndarray, k, d, obs) -> np.ndarray:
    """관측 [(T_base_tcp, (u, v), (x, y) 정답 mm, 평면 z mm)] 마다 픽셀→평면 점과 정답의 xy 거리(mm)."""
    out = []
    for t_base_tcp, px, xy, z in obs:
        p, ok = pixel_to_plane(t_base_tcp @ t_tcp_camera, k, d, [list(px)], z)
        out.append(float(np.hypot(p[0, 0] - xy[0], p[0, 1] - xy[1])) if ok[0] else np.inf)
    return np.asarray(out)


def correct_translation(t_tcp_camera: np.ndarray, k, d, obs, iters: int = 20) -> np.ndarray:
    """회전은 두고 카메라 위치만 고쳐 관측(터치·T16 대응점)에 맞춘다 → 보정량(카메라 좌표 mm, 3).

    보드 사진이 모두 아래를 보는 자세(≤ 25°)면 광축 방향 거리가 약하게 잡힌다(10/08: 약 10 mm).
    그 거리는 보드 흩어짐(①)에 드러나지 않으므로 위치를 아는 점으로 고친다. 가우스-뉴턴, 수치 미분.
    """

    def resid(x: np.ndarray) -> np.ndarray:
        t = t_tcp_camera @ make_t(np.eye(3), x)
        r = []
        for t_base_tcp, px, xy, z in obs:
            p, _ = pixel_to_plane(t_base_tcp @ t, k, d, [list(px)], z, max_angle_deg=89.0)
            r += [p[0, 0] - xy[0], p[0, 1] - xy[1]]
        return np.asarray(r)

    x = np.zeros(3)
    for _ in range(iters):
        r = resid(x)
        jac = np.column_stack([(resid(x + h) - r) / 1e-3 for h in np.eye(3) * 1e-3])
        step = np.linalg.lstsq(jac, -r, rcond=None)[0]
        x = x + step
        if np.linalg.norm(step) < 1e-4:
            break
    return x
