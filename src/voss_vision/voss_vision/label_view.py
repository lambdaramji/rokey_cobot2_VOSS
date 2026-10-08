"""재확인 구역 정지 재판독(3단계, `/voss/vision/read_label`) — ROS 없음, pytest 대상.

정지 화면 몇 장 → 장마다 송장 찾기(벨트 없이 전체 화면에서) → 펴기 → **선명한 순서로** OCR → 다수결.
box_tracker 의 박스 검출은 초록 벨트를 전제로 해서 재확인 트레이에서는 쓸 수 없다 → label_reader 가 카메라 영상을
직접 받아 여기서 송장을 찾는다. 송장 크기·찾는 영역은 재확인 VIEW 자세 사진으로 정한다(그 전엔 넓게).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from voss_vision.label_match import Candidate
from voss_vision.label_preprocess import Rect, crop_upright
from voss_vision.label_vote import Read, Vote, vote
from voss_vision.ocr_engine import read_label


def find_labels_in_view(
    img: np.ndarray,
    v_min: int = 200,
    s_max: int = 90,
    close_px: int = 5,
    area_min_px: int = 4000,
    area_max_px: int = 300_000,
    aspect: float = 40 / 25,
    aspect_tol: float = 0.5,
    fill_min: float = 0.75,
    roi: tuple[int, int, int, int] | None = None,
) -> list[Rect]:
    """전체 화면에서 송장 모양 흰 덩어리들의 회전 사각형 — roi(없으면 화면) 중심에 가까운 순.

    송장 모양 = 면적(px) 범위·가로세로비 40:25 ± tol·회전 사각형 대비 채움 ≥ fill_min. 글자 구멍은 윤곽을 채워 메운다.
    """
    h, w = img.shape[:2]
    x0, y0, x1, y1 = roi if roi else (0, 0, w, h)
    sub = img[y0:y1, x0:x1]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 0, v_min), (180, s_max, 255))
    if close_px > 1:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((close_px, close_px), np.uint8))
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c0 = np.array([(x1 - x0) / 2, (y1 - y0) / 2])
    found = []
    for c in contours:
        area = cv2.contourArea(c)
        if not area_min_px <= area <= area_max_px:
            continue
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        long_, short = max(rw, rh), min(rw, rh)
        if short < 1 or abs(long_ / short - aspect) > aspect_tol or area / (rw * rh) < fill_min:
            continue
        d = float(np.hypot(cx - c0[0], cy - c0[1]))
        found.append((d, ((cx + x0, cy + y0), (rw, rh), ang)))
    return [r for _, r in sorted(found, key=lambda t: t[0])]


def sharpness(gray: np.ndarray) -> float:
    """라플라시안 분산 — 흔들리거나 초점이 나가면 작다."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


@dataclass(frozen=True)
class ViewResult:
    vote: Vote | None
    reason: str  # "" 판독됨 | timeout(프레임 없음) | no_box(송장 못 찾음) | no_text(글자 없음) — ReadLabel.message
    ocr_runs: int


def read_view(
    engine,
    frames: list[tuple[np.ndarray, int]],
    cands: list[Candidate],
    finder: dict | None = None,
    scale: float = 3.0,
    max_ocr: int = 3,
    conf_min: float = 0.6,
    min_agree: int = 2,
) -> ViewResult:
    """프레임 [(BGR, 촬영 ns)] → 판정. OCR 은 선명한 크롭부터 max_ocr 장까지, 같은 동 min_agree 장이 확실하면 멈춘다."""
    if not frames:
        return ViewResult(None, "timeout", 0)
    crops = []
    for img, stamp in frames:
        rects = find_labels_in_view(img, **(finder or {}))
        if rects:
            up = crop_upright(img, rects[0], scale=scale)
            crops.append((sharpness(cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)), stamp, up))
    if not crops:
        return ViewResult(None, "no_box", 0)
    crops.sort(key=lambda c: -c[0])
    reads: list[Read] = []
    for sharp, stamp, up in crops[:max_ocr]:
        m, _, _ = read_label(engine, up, cands)
        reads.append(Read(m, stamp, sharp))
        v = vote(reads)
        if v.match.confidence >= conf_min and v.agree >= min_agree:
            break
    v = vote(reads)
    return ViewResult(v, "" if v.match.dong else "no_text", len(reads))
