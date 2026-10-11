"""박스 검출 — 분할 방식(`detector: seg`, ADR-0004 1단계). OpenCV 만 쓴다(학습 없음).

골판지 박스 색은 손 피부색과 거의 같아서(10/06 B bag) 박스 색으로 나누면 손을 잡는다.
그래서 **흰 송장**을 찾는다: 송장은 박스 윗면 중앙의 40×25 mm 흰 사각형이라 밝기·모양이
뚜렷하다. 송장 사각형을 박스 크기(46×31 mm)로 넓혀 bbox 를 만들고, 중심은 송장 중심
(= 박스 윗면 중심)을 쓴다. 화면 가장자리에 걸린 송장은 중심이 치우치므로 내지 않는다.
버린 성분과 이유(면적·가장자리·비율·채움)는 `detect_candidates` 로 본다(진단·시각화용, 같은 판정).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from voss_vision.box_track import Detection


@dataclass(frozen=True)
class SegParams:
    """voss_vision 파라미터 YAML 로 넘기는 값(ADR-0004: voss_config 아님). 기본값은 10/06 실측."""

    downscale: int = 2  # 계산 해상도 1/2 (중심 오차 ≈ 1 px ≈ 0.25 mm)
    v_min: int = 200  # 송장 밝기 하한 (HSV V)
    s_max: int = 90  # 송장 채도 상한
    close_px: int = 21  # 글자 구멍 메우기 (원본 px)
    area_min: int = 6000  # 송장 면적 (원본 px²). 관측 자세 ≈ 106×172 = 18k, 하강하면 커진다
    area_max: int = 400_000
    aspect: float = 40 / 25
    aspect_tol: float = 0.3
    fill_min: float = 0.8  # 회전 사각형 대비 채움
    border_px: int = 4  # 화면 가장자리에서 이만큼 안쪽이어야 낸다
    belt_green_frac: float = 0.25  # 열마다 초록 비율이 이 이상이면 벨트
    belt_margin_px: int = 60  # 벨트 열 범위 양옆 여유 (원본 px)
    box_scale: tuple[float, float] = (46 / 40, 31 / 25)  # 송장 → 박스 (긴 변, 짧은 변)


def belt_columns(hsv: np.ndarray, p: SegParams) -> tuple[int, int] | None:
    """초록 벨트가 차지하는 열 범위(계산 해상도). 손이 반쯤 가려도 잡히게 비율을 낮게 둔다."""
    green = cv2.inRange(hsv, (40, 60, 20), (95, 255, 200))
    cols = np.where(green.mean(axis=0) / 255 >= p.belt_green_frac)[0]
    if cols.size == 0:
        return None
    m = p.belt_margin_px // p.downscale
    return max(int(cols.min()) - m, 0), min(int(cols.max()) + m, hsv.shape[1] - 1)


DEFAULT_PARAMS = SegParams()

REASONS = ("", "area", "border", "aspect", "fill")  # "" = 통과. 판정 순서와 같다


@dataclass(frozen=True)
class Candidate:
    """흰 연결 성분 하나와 판정 — 진단·시각화용(tools/viz/box_overlay.py). 좌표는 원본 px."""

    rect: tuple[int, int, int, int]  # 성분의 축정렬 bbox x, y, w, h
    area: float  # px²
    reason: str  # REASONS 중 하나. "area"·"border" 는 회전 사각형을 계산하기 전에 버린 것
    rot: tuple[tuple[float, float], tuple[float, float], float] | None = None  # minAreaRect
    aspect: float = float("nan")  # 긴 변 / 짧은 변
    fill: float = float("nan")  # 회전 사각형 대비 채움
    det: Detection | None = None  # 통과했을 때만


def detect_boxes(bgr: np.ndarray, p: SegParams = DEFAULT_PARAMS) -> list[Detection]:
    """한 프레임 → 박스 검출 목록(원본 픽셀 좌표). 벨트가 안 보이면 빈 목록."""
    return [c.det for c in _judge(bgr, p, keep_rejected=False)[1] if c.det is not None]


def detect_candidates(
    bgr: np.ndarray, p: SegParams = DEFAULT_PARAMS
) -> tuple[tuple[int, int] | None, list[Candidate]]:
    """detect_boxes 와 같은 판정에 버린 성분까지 — (벨트 열 범위 원본 px 또는 None, 후보 목록).
    통과한 후보의 det 는 detect_boxes 결과와 같다(같은 함수를 지난다)."""
    return _judge(bgr, p, keep_rejected=True)


def _judge(bgr: np.ndarray, p: SegParams, keep_rejected: bool):
    k = p.downscale
    small = (
        cv2.resize(bgr, None, fx=1 / k, fy=1 / k, interpolation=cv2.INTER_AREA) if k > 1 else bgr
    )
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    roi = belt_columns(hsv, p)
    if roi is None:
        return None, []
    m = cv2.inRange(hsv, (0, 0, p.v_min), (180, p.s_max, 255))
    m[:, : roi[0]] = 0
    m[:, roi[1] + 1 :] = 0
    ck = max(3, (p.close_px // k) | 1)
    # 화면 밖을 배경(0)으로 덧대고 닫는다. 그냥 닫으면 OpenCV 기본 테두리가 화면 밖을 흰색처럼 다뤄
    # 끝에서 ck/2 안쪽 송장이 화면 끝과 붙고 border_px 판정에서 버려진다(실효 여유 ≈ 10 px, #76).
    r = ck // 2 + 1
    m = cv2.copyMakeBorder(m, r, r, r, r, cv2.BORDER_CONSTANT, value=0)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((ck, ck), np.uint8))[r:-r, r:-r]
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    H, W = small.shape[:2]
    b = p.border_px / k
    out: list[Candidate] = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA] * k * k
        x, y, w, h = st[i, :4]
        rect = (int(x * k), int(y * k), int(w * k), int(h * k))
        if not p.area_min <= area <= p.area_max:
            if keep_rejected:
                out.append(Candidate(rect, float(area), "area"))
            continue
        if x <= b or y <= b or x + w >= W - b or y + h >= H - b:
            if keep_rejected:  # 가장자리에 걸림 → 중심이 치우친다
                out.append(Candidate(rect, float(area), "border"))
            continue
        pts = np.column_stack(np.where(lab[y : y + h, x : x + w] == i))[:, ::-1].astype(np.float32)
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(pts + np.float32([x, y]))
        long_, short = max(rw, rh), min(rw, rh)
        rot = ((float(cx * k), float(cy * k)), (float(rw * k), float(rh * k)), float(ang))
        if short < 1 or abs(long_ / short - p.aspect) > p.aspect_tol:
            if keep_rejected:
                ratio = long_ / short if short >= 1 else float("inf")
                out.append(Candidate(rect, float(area), "aspect", rot, float(ratio)))
            continue
        fill = st[i, cv2.CC_STAT_AREA] / (rw * rh)
        if fill < p.fill_min:
            if keep_rejected:
                out.append(Candidate(rect, float(area), "fill", rot, float(long_ / short), fill))
            continue
        # 송장 → 박스 크기로 넓힌 회전 사각형의 축정렬 bbox (원본 좌표)
        sl, ss = p.box_scale
        bw, bh = (rw * sl, rh * ss) if rw >= rh else (rw * ss, rh * sl)
        corners = cv2.boxPoints(((cx * k, cy * k), (bw * k, bh * k), ang))
        x0, y0 = np.floor(corners.min(0)).astype(int)
        x1, y1 = np.ceil(corners.max(0)).astype(int)
        score = float(min(1.0, fill))
        det = Detection(
            float(cx * k), float(cy * k), (int(x0), int(y0), int(x1 - x0), int(y1 - y0)), score
        )
        out.append(Candidate(rect, float(area), "", rot, float(long_ / short), float(fill), det))
    return (roi[0] * k, roi[1] * k), out
