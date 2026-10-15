"""ocr_engine.read_label — 판정이 없을 때만 반대 방향으로 다시 읽는다 (거꾸로 올린 박스), 180° 먼저 읽기."""

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


def test_no_flip_retry_returns_after_one_read() -> None:
    """1단계: 못 읽어도 180° 다시 읽지 않는다 (판독 실패를 빨리 내서 재확인으로)."""
    eng = Fake()
    m, _, flipped = read_label(eng, half(False), CANDS, flip_retry=False)
    assert (m.dong, flipped, eng.calls) == ("", False, 1)


def test_flip_first_reads_upside_down_once() -> None:
    """2단계: 1단계가 글자를 못 읽은 트랙은 180° 먼저 — 거꾸로 올린 송장이 한 번에 읽힌다(10/15 실기 5.5 → 2.3 s)."""
    eng = Fake()
    m, _, flipped = read_label(eng, half(False), CANDS, flip_first=True)
    assert (m.dong, flipped, eng.calls) == ("대치동", True, 1)


def test_flip_first_falls_back_to_upright() -> None:
    """추측이 틀려도(바로 선 송장) 바로 선 쪽을 다시 읽어 판정한다 — 지금과 같은 두 번."""
    eng = Fake()
    m, _, flipped = read_label(eng, half(True), CANDS, flip_first=True)
    assert (m.dong, flipped, eng.calls) == ("대치동", False, 2)


def test_flip_first_unreadable_returns_upright_result() -> None:
    eng = Fake(never=True)
    m, _, flipped = read_label(eng, half(True), CANDS, flip_first=True)
    assert (m.dong, m.reason, flipped, eng.calls) == ("", "NONE", False, 2)
    eng = Fake()
    m, _, flipped = read_label(eng, half(True), CANDS, flip_retry=False, flip_first=True)
    assert (m.dong, flipped, eng.calls) == ("", False, 1)
