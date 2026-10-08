"""송장 크롭 전처리 (TR-OCR-03): 원근 보정 → 고정 회전 → 2~3배 업스케일 → (선택) 대비 강화.

`find_label_rect` 는 관측 자세 정지 사진용 휴리스틱이다(T16·T18). 흰 송장은 V≈250 으로
벨트 위 위치 테이프(≈130)·레일(≈170)보다 훨씬 밝다. 운용 중에는 box_tracker 의 박스 영역이
LabelCrop 으로 오므로 label_reader 는 `crop_upright` 부터 쓴다.
"""

from __future__ import annotations

import cv2
import numpy as np

Rect = tuple[tuple[float, float], tuple[float, float], float]  # cv2.minAreaRect 형식


def find_label_rect(image: np.ndarray) -> Rect | None:
    """초록 벨트 열 안에서 가장 큰 밝은 덩어리(송장)의 회전 사각형. 없으면 None."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (40, 60, 20), (95, 255, 200))
    cols = np.where(green.sum(axis=0) > 255 * 200)[0]
    if cols.size == 0:
        return None
    m = cv2.inRange(hsv, (0, 0, 215), (180, 90, 255))
    m[:, : cols.min()] = 0
    m[:, cols.max() :] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))  # 글자 구멍 메움
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    i = max(range(1, n), key=lambda j: st[j, cv2.CC_STAT_AREA])
    pts = np.column_stack(np.where(lab == i))[:, ::-1].astype(np.float32)
    return cv2.minAreaRect(pts)


# 관측 자세 화면에서 송장 글자가 나아가는 방향(이미지 좌표, y 아래). 송장은 박스 윗면에 늘 같은
# 방향으로 붙고 박스 긴 변이 벨트 방향이라 고정이다(TR-OCR-03). 카메라 장착이 바뀌면 다시 정한다.
BASELINE_DIR = (0.0, 1.0)


def crop_upright(
    image: np.ndarray,
    rect: Rect,
    scale: float = 3.0,
    pad_px: float = 4.0,
    baseline_dir: tuple[float, float] = BASELINE_DIR,
    clahe: bool = False,
) -> np.ndarray:
    """회전 사각형(송장)을 글자가 바로 읽히는 가로 사각형으로 편다(원근 보정 + 확대).

    긴 축 두 방향 중 `baseline_dir` 에 가까운 쪽을 글자 진행 방향으로 고른다 → 박스가
    기본 방향에서 ±90° 안으로 돌아가 있으면 몇 도든 바로 선다(10/06: 최대 약 40°).
    """
    (cx, cy), (w, h), ang = rect
    t = np.radians(ang)
    a1 = np.array([np.cos(t), np.sin(t)])  # minAreaRect 의 w 축
    a2 = np.array([-np.sin(t), np.cos(t)])  # h 축
    u, long_, short = (a1, w, h) if w >= h else (a2, h, w)
    if u @ np.asarray(baseline_dir, dtype=float) < 0:
        u = -u
    up = np.array([u[1], -u[0]])  # 글자 위쪽 (y 아래 좌표계에서 진행 방향을 반시계 90°)
    c = np.array([cx, cy])
    hl, hs = long_ / 2 + pad_px, short / 2 + pad_px
    src = np.float32(
        [c - u * hl + up * hs, c + u * hl + up * hs, c + u * hl - up * hs, c - u * hl - up * hs]
    )
    W, H = int(round(2 * hl * scale)), int(round(2 * hs * scale))
    M = cv2.getPerspectiveTransform(src, np.float32([[0, 0], [W, 0], [W, H], [0, H]]))
    out = cv2.warpPerspective(image, M, (W, H), flags=cv2.INTER_CUBIC)
    if clahe:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(lab[..., 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return out
