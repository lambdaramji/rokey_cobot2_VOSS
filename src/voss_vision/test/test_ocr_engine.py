"""ocr_engine.read_label — 판정이 없을 때만 180° 돌려 다시 읽는다 (거꾸로 올린 박스)."""

import numpy as np
from voss_vision.label_match import Candidate
from voss_vision.ocr_engine import read_label

CANDS = [Candidate("역삼동", "S07-01", ("역삼",)), Candidate("대치동", "S07-02", ("대치",))]
LINES = [("S07-02", 0.99), ("대치동", 0.95)]


class Fake:
    """왼쪽 절반이 밝을 때만 글자를 읽는 가짜 엔진 (= 바로 선 송장만 읽힘)."""

    def __init__(self, always: bool = False, never: bool = False) -> None:
        self.calls, self.always, self.never = 0, always, never

    def read(self, img: np.ndarray) -> list[tuple[str, float]]:
        self.calls += 1
        upright = img[:, : img.shape[1] // 2].mean() > 128
        return [] if self.never else LINES if (self.always or upright) else []


def half(bright_left: bool) -> np.ndarray:
    img = np.zeros((60, 200, 3), np.uint8)
    img[:, :100] = 255 if bright_left else 0
    img[:, 100:] = 0 if bright_left else 255
    return img


def test_upright_reads_once() -> None:
    eng = Fake()
    m, _, flipped = read_label(eng, half(True), CANDS)
    assert (m.code, m.dong, flipped, eng.calls) == ("S07-02", "대치동", False, 1)


def test_upside_down_is_read_after_180_turn() -> None:
    eng = Fake()
    m, _, flipped = read_label(eng, half(False), CANDS)
    assert (m.code, m.dong, flipped, eng.calls) == ("S07-02", "대치동", True, 2)


def test_unreadable_stays_none() -> None:
    eng = Fake(never=True)
    m, _, flipped = read_label(eng, half(True), CANDS)
    assert (m.dong, m.reason, flipped, eng.calls) == ("", "NONE", False, 2)
