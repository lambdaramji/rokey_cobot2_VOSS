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
    # 해가 유일하려면 두 번째로 작은 특이값이 0 이 아니어야 한다 (일직선 배치 검출)
    if sv[-2] < 1e-6 * sv[0]:
        raise ValueError("대응점이 한 직선 위에 있다 — 벨트 폭 양끝으로 점을 벌려라")
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
