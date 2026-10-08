"""벨트 평면 호모그래피 — 픽셀 ↔ 로봇 베이스 (x, y) mm. ADR-0003.

관측 자세에서 찍은 박스 윗면 중앙 픽셀과, 같은 자리를 TCP 로 터치한 posx(x, y)의 대응점으로
3×3 행렬 H 를 구한다. 박스 윗면(벨트 + 27 mm)이 한 평면이라는 가정이라 관측 자세에서만 유효.

순수 함수(numpy 만 사용) — 노드·계산 스크립트·pytest 가 같이 쓴다. ROS 의존 없음.
"""

from __future__ import annotations

import numpy as np

MIN_POINTS = 4


def _normalize(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """하틀리 정규화: 중심을 원점, 평균 거리를 √2 로. 픽셀(~1000)과 mm(~500) 스케일 차이로
    생기는 수치 불안정을 막는다. (정규화된 점, 3×3 변환) 반환."""
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
    return apply_homography(t, pts), t


def fit_homography(px: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """픽셀 (N,2) → 베이스 xy mm (N,2) 호모그래피를 최소제곱(DLT)으로 구한다. N ≥ 4.

    점이 한 직선 위에 몰리면(벨트 폭 방향으로 안 벌림) 풀 수 없다 → ValueError.
    """
    px = np.asarray(px, dtype=float)
    xy = np.asarray(xy, dtype=float)
    if px.shape != xy.shape or px.ndim != 2 or px.shape[1] != 2:
        raise ValueError("px, xy 는 같은 (N, 2) 배열이어야 한다")
    if len(px) < MIN_POINTS:
        raise ValueError(f"대응점이 {MIN_POINTS}개 이상 필요하다 (현재 {len(px)}개)")

    p, tp = _normalize(px)
    q, tq = _normalize(xy)
    rows = []
    for (u, v), (x, y) in zip(p, q, strict=True):
        rows.append([-u, -v, -1, 0, 0, 0, u * x, v * x, x])
        rows.append([0, 0, 0, -u, -v, -1, u * y, v * y, y])
    a = np.asarray(rows)
    _, sv, vt = np.linalg.svd(a)
    # 해가 유일하려면 rank(A) = 8. N=4 면 A 가 8×9 라 특이값이 8개뿐이므로 항상 8번째(sv[7])를 본다.
    # (sv[-2] 로 보면 N=4 에서 "세 점 일직선 + 1점"(rank 7)을 통과시킨다 — #48 리뷰 P2)
    if sv[7] < 1e-6 * sv[0]:
        raise ValueError("대응점 배치가 퇴화(일직선·세 점 일직선)다 — 벨트 폭 양끝으로 점을 벌려라")
    hn = vt[-1].reshape(3, 3)
    h = np.linalg.inv(tq) @ hn @ tp
    return h / h[2, 2]


def apply_homography(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """(N,2) 점에 H 적용. 픽셀 → mm (또는 inv(H) 로 mm → 픽셀)."""
    pts = np.asarray(pts, dtype=float)
    ph = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(h).T
    return ph[:, :2] / ph[:, 2:3]


def point_errors_mm(h: np.ndarray, px: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """점마다 |H(px) − xy| (mm). 검증점 오차 판정(SR-FN-02, ≤ 5 mm 제안값)에 쓴다."""
    return np.linalg.norm(apply_homography(h, px) - np.asarray(xy, dtype=float), axis=1)


# ---- 두산 posx 보조 함수 (ZYZ, deg) -------------------------------------------------


def rot_zyz_deg(rx: float, ry: float, rz: float) -> np.ndarray:
    """두산 posx 자세(ZYZ 오일러, deg) → 3×3 회전행렬. R = Rz(rx)·Ry(ry)·Rz(rz)."""
    a, b, c = np.radians([rx, ry, rz])

    def rz_(t: float) -> np.ndarray:
        return np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])

    rb = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    return rz_(a) @ rb @ rz_(c)


def flange_to_tcp(posx: np.ndarray, tcp_offset_mm: np.ndarray) -> np.ndarray:
    """플랜지 posx (x,y,z,rx,ry,rz) → TCP(접촉점) 위치 (x,y,z). p_tcp = p_flange + R·t."""
    posx = np.asarray(posx, dtype=float)
    return posx[:3] + rot_zyz_deg(*posx[3:6]) @ np.asarray(tcp_offset_mm, dtype=float)


def tool_axis_angle_deg(posx_a: np.ndarray, posx_b: np.ndarray) -> float:
    """두 자세의 툴 z축 사이 각도(deg). ZYZ 각을 직접 빼면 ry≈±180 근처에서 틀리므로 축으로 비교."""
    za = rot_zyz_deg(*np.asarray(posx_a, dtype=float)[3:6])[:, 2]
    zb = rot_zyz_deg(*np.asarray(posx_b, dtype=float)[3:6])[:, 2]
    return float(np.degrees(np.arccos(np.clip(za @ zb, -1.0, 1.0))))


# ---- 결과 파일로 픽셀 → 베이스 ------------------------------------------------------


def undistort_pixels(px: np.ndarray, k: np.ndarray | None, d: np.ndarray | None) -> np.ndarray:
    """왜곡 보정한 픽셀 (N,2). d 가 없거나 0 이면 그대로 (cv2 는 필요할 때만 불러온다)."""
    px = np.asarray(px, dtype=float).reshape(-1, 2)
    if k is None or d is None or not np.any(d):
        return px
    import cv2  # noqa: PLC0415 — 비전 컨테이너·도구에서만 필요

    k = np.asarray(k, dtype=float).reshape(3, 3)
    return cv2.undistortPoints(px.reshape(-1, 1, 2), k, np.asarray(d, dtype=float), P=k).reshape(
        -1, 2
    )


def inside_hull(hull_px: np.ndarray, px: np.ndarray) -> np.ndarray:
    """볼록 다각형(반시계 또는 시계 순서) 안에 있는지 (N,) bool. 경계 포함."""
    hull = np.asarray(hull_px, dtype=float)
    p = np.asarray(px, dtype=float).reshape(-1, 2)
    edges = np.roll(hull, -1, axis=0) - hull
    rel = p[:, None, :] - hull[None, :, :]
    cross = edges[None, :, 0] * rel[:, :, 1] - edges[None, :, 1] * rel[:, :, 0]
    return np.all(cross >= -1e-9, axis=1) | np.all(cross <= 1e-9, axis=1)


def convex_hull(px: np.ndarray) -> np.ndarray:
    """2D 볼록 껍질(반시계, Andrew monotone chain)."""
    pts = sorted(map(tuple, np.asarray(px, dtype=float)))

    def half(seq: list) -> list:
        out: list = []
        for q in seq:
            while len(out) >= 2:
                o, a = out[-2], out[-1]
                if (a[0] - o[0]) * (q[1] - o[1]) - (a[1] - o[1]) * (q[0] - o[0]) > 0:
                    break
                out.pop()
            out.append(q)
        return out

    lower, upper = half(pts), half(pts[::-1])
    return np.array(lower[:-1] + upper[:-1])


def pixel_to_base_xy(calib: dict, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """belt_homography.yaml 내용(dict)으로 원본 픽셀 → 베이스 (x, y) mm 와 유효 여부.

    순서: 왜곡 보정 → H. 유효 = 캘리브레이션 대응점 볼록 껍질(`calib_hull_px`, 보정 후 픽셀) 안.
    관측 자세에서만 쓴다(이동 중 좌표는 핸드아이 단계). box_tracker 와 도구가 같은 함수를 쓴다.
    """
    und = calib.get("undistort") or {}
    p = undistort_pixels(px, und.get("k"), und.get("d"))
    xy = apply_homography(np.asarray(calib["H_px_to_base_xy"]), p)
    hull = calib.get("calib_hull_px")
    valid = inside_hull(np.asarray(hull), p) if hull else np.ones(len(p), dtype=bool)
    return xy, valid
