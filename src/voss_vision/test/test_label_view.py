"""label_view — 재확인 구역 정지 재판독: 전체 화면 송장 찾기, 선명한 순서·조기 종료 다수결, 실패 사유."""

import cv2
import numpy as np
import pytest
from voss_vision.label_match import Candidate
from voss_vision.label_view import find_labels_in_view, read_view, sharpness

CANDS = [
    Candidate("역삼동", "S07-01", ("역삼",)),
    Candidate("대치동", "S07-02", ("대치",)),
    Candidate("청담동", "S07-03", ("청담",)),
]
LONG, SHORT = 172, 106  # 관측 자세 송장 크기(px) — VIEW 자세는 사진으로 다시 정한다


def tray(*labels: tuple[float, float, float], size=(1080, 1920)) -> np.ndarray:
    """회색 트레이 위 송장들 (cx, cy, 각도°). 송장 안에 글자 대신 검은 줄."""
    img = np.full((*size, 3), (95, 105, 115), np.uint8)
    for cx, cy, ang in labels:
        box = cv2.boxPoints(((cx, cy), (SHORT, LONG), ang)).astype(np.int32)
        cv2.fillPoly(img, [box], (250, 250, 250))
        cv2.line(img, (int(cx) - 30, int(cy)), (int(cx) + 30, int(cy)), (20, 20, 20), 6)
    return img


def test_find_labels_nearest_centre_first() -> None:
    img = tray((900, 520, 15), (1600, 250, 0))
    rects = find_labels_in_view(img)
    assert len(rects) == 2
    (cx, cy), (w, h), _ = rects[0]
    assert abs(cx - 900) < 4 and abs(cy - 520) < 4
    assert max(w, h) == pytest.approx(LONG, rel=0.06)
    assert min(w, h) == pytest.approx(SHORT, rel=0.08)


def test_find_labels_roi_and_filters() -> None:
    img = tray((900, 520, 0), (1600, 250, 0))
    cv2.rectangle(img, (100, 900), (110, 910), (250, 250, 250), -1)  # 작은 흰 점 — 면적 미달
    cv2.rectangle(img, (200, 100), (500, 140), (250, 250, 250), -1)  # 가늘고 긴 흰 띠 — 비율 미달
    rects = find_labels_in_view(img, roi=(1300, 0, 1920, 600))
    # roi 안의 송장만, 좌표는 전체 화면 기준
    assert len(rects) == 1 and abs(rects[0][0][0] - 1600) < 4
    assert find_labels_in_view(tray()) == []


class Fake:
    """크롭을 받을 때마다 기록하고 정해 둔 줄을 돌려주는 엔진."""

    def __init__(self, lines: list[tuple[str, float]]) -> None:
        self.lines, self.calls = lines, []

    def read(self, img: np.ndarray) -> list[tuple[str, float]]:
        self.calls.append(sharpness(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))
        return self.lines


def frames(n: int, blur_first: bool = False) -> list[tuple[np.ndarray, int]]:
    out = []
    for i in range(n):
        img = tray((960, 540, 10))
        if blur_first and i == 0:
            img = cv2.GaussianBlur(img, (31, 31), 0)
        out.append((img, (i + 1) * 1_000_000))
    return out


def test_read_view_confident_stops_after_two_agreeing() -> None:
    eng = Fake([("S07-02", 0.99), ("대치동", 0.97)])
    r = read_view(eng, frames(5), CANDS)
    assert r.reason == "" and r.vote.match.dong == "대치동" and r.vote.match.code == "S07-02"
    assert r.ocr_runs == 2 and len(eng.calls) == 2  # 같은 동 2장이 확실하면 그만 읽는다


def test_read_view_reads_sharpest_first() -> None:
    eng = Fake([("S07-02", 0.99), ("대치동", 0.97)])
    r = read_view(eng, frames(3, blur_first=True), CANDS)
    assert r.ocr_runs == 2 and eng.calls[0] == eng.calls[1]  # 흐린 첫 프레임은 읽지 않았다
    blur = Fake([("S07-02", 0.99)])
    assert read_view(blur, frames(1, blur_first=True), CANDS).ocr_runs == 1  # 흐려도 송장은 찾는다
    assert blur.calls[0] < eng.calls[0] / 3


def test_read_view_failure_reasons() -> None:
    assert read_view(Fake([]), [], CANDS).reason == "timeout"
    assert read_view(Fake([]), [(tray(), 1)], CANDS).reason == "no_box"
    r = read_view(Fake([]), frames(3), CANDS, max_ocr=2)
    assert r.reason == "no_text" and r.ocr_runs == 2


def test_read_view_low_confidence_is_still_a_read() -> None:
    """확실하지 않아도 판독 결과는 돌려준다 — 질문으로 갈지는 sort_manager 가 confidence 로 정한다."""
    eng = Fake([("S07-0?", 0.4), ("대치", 0.5)])
    r = read_view(eng, frames(3), CANDS, max_ocr=3)
    assert r.reason == "" and r.vote.match.dong == "대치동" and r.vote.match.confidence < 0.6
    assert r.ocr_runs == 3
