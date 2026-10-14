"""박스 검출 — 분할 방식(`detector: seg`, ADR-0004 1단계). OpenCV 만 쓴다(학습 없음).

골판지 박스 색은 손 피부색과 거의 같아서(10/06 B bag) 박스 색으로 나누면 손을 잡는다.
그래서 **흰 송장**을 찾는다: 송장은 박스 윗면 중앙의 40×25 mm 흰 사각형이라 밝기·모양이
뚜렷하다. 송장 사각형을 박스 크기(46×31 mm)로 넓혀 bbox 를 만들고, 중심은 송장 중심
(= 박스 윗면 중심)을 쓴다. 화면 가장자리에 걸린 송장은 중심이 치우치므로 내지 않는다.
버린 성분과 이유(면적·가장자리·비율·채움)는 `detect_candidates` 로 본다(진단·시각화용, 같은 판정).

벨트 영역(`belt_roi`): `columns`(이전) = 초록 비율이 높은 열 범위 — 벨트가 화면 세로일 때만 맞고, 카메라가 J6 로
돌아 벨트가 기울면 영역 경계가 송장을 자른다. `hull`(기본, S2-T16) = 그 열 범위 ∪ 초록 성분들의 볼록 껍질 + 여유 —
이전 영역을 넓히기만 하므로 세로 벨트에서는 이전 검출이 그대로고(10/06 실제 프레임 1593장 같음), 기울면 껍질이 메운다. 어느 쪽이든 **영역 경계에 걸린 송장은 내지 않는다**(잘린 송장은 중심·각이 틀린다).
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
    belt_green_frac: float = 0.25  # columns: 열마다 초록 비율이 이 이상이면 벨트
    belt_margin_px: int = 60  # 벨트 영역 바깥 여유 (원본 px)
    belt_roi: str = "hull"  # hull = columns ∪ 볼록 껍질(방향 무관, S2-T16) | columns(이전 — 벨트가 화면 세로일 때만)
    belt_min_area_frac: float = 0.02  # hull: 초록 성분 합이 화면의 이 비율 미만이면 벨트 없음
    box_scale: tuple[float, float] = (46 / 40, 31 / 25)  # 송장 → 박스 (긴 변, 짧은 변)


def belt_columns(hsv: np.ndarray, p: SegParams) -> tuple[int, int] | None:
    """초록 벨트가 차지하는 열 범위(계산 해상도). 손이 반쯤 가려도 잡히게 비율을 낮게 둔다."""
    green = cv2.inRange(hsv, (40, 60, 20), (95, 255, 200))
    cols = np.where(green.mean(axis=0) / 255 >= p.belt_green_frac)[0]
    if cols.size == 0:
        return None
    m = p.belt_margin_px // p.downscale
    return max(int(cols.min()) - m, 0), min(int(cols.max()) + m, hsv.shape[1] - 1)


def belt_region(hsv: np.ndarray, p: SegParams) -> tuple[np.ndarray, tuple[int, int]] | None:
    """벨트 영역 마스크(계산 해상도, 0/255)와 그 열 범위. 벨트가 안 보이면 None.

    columns: 열 범위. hull: 열 범위(있으면) ∪ 면적이 가장 큰 초록 성분의 20 % 이상인 성분들(손이 가로질러 나뉜 벨트
    포함)의 볼록 껍질 + 여유. 벨트 위 박스는 초록을 가리지만 껍질 안이라 영역에 든다."""
    if p.belt_roi not in ("hull", "columns"):
        raise ValueError(f"belt_roi={p.belt_roi} — hull | columns")
    h, w = hsv.shape[:2]
    roi = np.zeros((h, w), np.uint8)
    cols = belt_columns(hsv, p)
    if cols is not None:
        roi[:, cols[0] : cols[1] + 1] = 255
    if p.belt_roi == "hull":
        green = cv2.inRange(hsv, (40, 60, 20), (95, 255, 200))
        n, lab, st, _ = cv2.connectedComponentsWithStats(green)
        areas = st[1:, cv2.CC_STAT_AREA]
        keep = 1 + np.where(areas >= 0.2 * areas.max())[0] if n > 1 else np.array([], int)
        if len(keep) and areas[keep - 1].sum() >= p.belt_min_area_frac * h * w:
            pts = np.column_stack(np.where(np.isin(lab, keep)))[:, ::-1].astype(np.int32)
            hull = np.zeros((h, w), np.uint8)
            cv2.fillConvexPoly(hull, cv2.convexHull(pts), 255)
            m = p.belt_margin_px // p.downscale
            if m > 0:
                ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * m + 1, 2 * m + 1))
                hull = cv2.dilate(hull, ker)
            roi |= hull
    xs = np.where(roi.any(axis=0))[0]
    if xs.size == 0:
        return None
    return roi, (int(xs.min()), int(xs.max()))


DEFAULT_PARAMS = SegParams()

REASONS = ("", "area", "border", "aspect", "fill")  # "" = 통과. 판정 순서와 같다


@dataclass(frozen=True)
class Candidate:
    """흰 연결 성분 하나와 판정 — 진단·시각화용(tools/vision/box_overlay.py). 좌표는 원본 px."""

    rect: tuple[int, int, int, int]  # 성분의 축정렬 bbox x, y, w, h
    area: float  # px²
    reason: str  # REASONS 중 하나. "area"·"border" 는 회전 사각형을 계산하기 전에 버린 것
    rot: tuple[tuple[float, float], tuple[float, float], float] | None = None  # minAreaRect
    aspect: float = float("nan")  # 긴 변 / 짧은 변
    fill: float = float("nan")  # 회전 사각형 대비 채움
    det: Detection | None = None  # 통과했을 때만


def half_long_axis(rot) -> tuple[float, float]:
    """minAreaRect ((cx, cy), (w, h), 각) → 중심에서 긴 변 끝까지의 픽셀 벡터 (S2-T16 yaw).
    OpenCV 각도 규칙에 기대지 않고 꼭짓점에서 긴 변을 고른다. 방향 부호(±)는 yaw 를 180° 접어 상관없다."""
    c = cv2.boxPoints(rot)
    e1, e2 = c[1] - c[0], c[2] - c[1]
    e = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    return float(e[0] / 2), float(e[1] / 2)


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
    region = belt_region(hsv, p)
    if region is None:
        return None, []
    roi_mask, roi = region
    m = cv2.inRange(hsv, (0, 0, p.v_min), (180, p.s_max, 255))
    m &= roi_mask
    ck = max(3, (p.close_px // k) | 1)
    # 화면 밖을 배경(0)으로 덧대고 닫는다. 그냥 닫으면 OpenCV 기본 테두리가 화면 밖을 흰색처럼 다뤄
    # 끝에서 ck/2 안쪽 송장이 화면 끝과 붙고 border_px 판정에서 버려진다(실효 여유 ≈ 10 px, #76).
    r = ck // 2 + 1
    m = cv2.copyMakeBorder(m, r, r, r, r, cv2.BORDER_CONSTANT, value=0)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((ck, ck), np.uint8))[r:-r, r:-r]
    m &= roi_mask  # 닫기가 영역 밖으로 번진 것은 지운다
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    H, W = small.shape[:2]
    b = p.border_px / k
    # 벨트 영역 안쪽 경계 띠 — 여기 닿은 성분은 영역 경계에 잘린 것이다 (화면 밖은 깎지 않는다: erode 기본 테두리)
    bi = max(1, int(round(b)))
    roi_edge = roi_mask & ~cv2.erode(roi_mask, np.ones((2 * bi + 1, 2 * bi + 1), np.uint8))
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
        if np.any(roi_edge[y : y + h, x : x + w][lab[y : y + h, x : x + w] == i]):
            if keep_rejected:  # 벨트 영역 경계에 잘림 → 중심·각이 틀린다 (S2-T16)
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
            float(cx * k),
            float(cy * k),
            (int(x0), int(y0), int(x1 - x0), int(y1 - y0)),
            score,
            half_long_axis(rot),
        )
        out.append(Candidate(rect, float(area), "", rot, float(long_ / short), float(fill), det))
    return (roi[0] * k, roi[1] * k), out
