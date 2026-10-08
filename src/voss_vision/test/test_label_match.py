"""label_match 순수 함수 시험 — 10/06 정지 송장 OCR 에서 실제로 나온 문자열을 쓴다."""

import pytest
from voss_vision.label_match import (
    CONFLICT,
    Candidate,
    candidates_from_config,
    code_numbers,
    levenshtein,
    match_label,
    name_similarity,
    to_jamo,
)

CANDS = [
    Candidate("역삼동", "S07-01", ("역삼", "역삼동")),
    Candidate("대치동", "S07-02", ("대치", "대치동")),
    Candidate("청담동", "S07-03", ("청담", "청담동")),
]
CONF_MIN = 0.6  # voss_config ocr.confidence_min


def test_levenshtein_and_jamo() -> None:
    assert levenshtein("역삼동", "역심동") == 1
    assert to_jamo("역삼") == "ㅇㅕㄱㅅㅏㅁ"
    # 자모로 보면 흐린 오독(삼→심)이 가깝다
    assert name_similarity("역심동", "역삼동") == pytest.approx(1 - 1 / 9)


@pytest.mark.parametrize(
    ("text", "nums"),
    [
        ("S07-01", ["0701"]),
        ("507-02", ["0702"]),  # S 를 5 로 읽어도 끝 4자리
        ("SO7-O3", ["0703"]),  # O/0 혼동
        ("S07 - 01", ["0701"]),
        ("받는분 박병후", []),
    ],
)
def test_code_numbers(text: str, nums: list[str]) -> None:
    assert code_numbers(text)[-1:] == nums[-1:]


def test_clean_label_agrees() -> None:
    m = match_label([("S07-01", 0.997), ("역삼동", 0.998), ("받는분 박병후", 0.84)], CANDS)
    assert (m.code, m.dong, m.reason) == ("S07-01", "역삼동", "AGREE")
    assert m.confidence > 0.99
    assert m.raw_text.splitlines()[0] == "S07-01"


def test_blurred_dong_still_agrees() -> None:
    # 10/06 BLUR_S0701_03 실제 출력
    m = match_label([("S07-01", 0.987), ("역심동", 0.834), ("UN", 0.238)], CANDS)
    assert (m.dong, m.reason) == ("역삼동", "AGREE")
    assert m.confidence >= CONF_MIN


def test_conflict_prefers_code_but_goes_to_recheck() -> None:
    m = match_label([("S07-02", 0.99), ("역삼동", 0.99)], CANDS)
    assert (m.code, m.dong, m.reason) == ("S07-02", "대치동", "CONFLICT")
    assert m.confidence < CONF_MIN  # 재확인 구역 (TR-OCR-06)
    assert (m.dong_alt, m.confidence_alt) == ("역삼동", pytest.approx(CONFLICT * 0.99))


def test_code_only_passes_dong_only_weaker() -> None:
    m = match_label([("S07-03", 0.99), ("받는분 남현지", 0.9)], CANDS)
    assert (m.dong, m.reason) == ("청담동", "CODE_ONLY") and m.confidence >= CONF_MIN
    d = match_label([("대치동", 0.95)], CANDS)
    assert (d.dong, d.reason) == ("대치동", "DONG_ONLY") and d.confidence < 0.7


def test_nothing_readable() -> None:
    m = match_label([("UN", 0.2)], CANDS)
    assert (m.code, m.dong, m.confidence, m.reason) == ("", "", 0.0, "NONE")


def test_receiver_name_is_not_a_dong() -> None:
    # 받는 사람 이름이 동 이름으로 잡히면 안 된다
    for name in ("박병후", "남현지", "받는분"):
        assert all(name_similarity(name, c.dong) < 0.6 for c in CANDS)


def test_candidates_from_config() -> None:
    cfg = {
        "aliases": {"역삼동": ["역삼", "역삼동"]},
        "ocr": {"codes": {"S07-01": "역삼동", "S07-02": "대치동"}},
    }
    got = candidates_from_config(cfg)
    assert [(c.dong, c.number, c.aliases) for c in got] == [
        ("역삼동", "01", ("역삼", "역삼동")),
        ("대치동", "02", ()),
    ]


def test_code_survives_s_as_5_without_hyphen() -> None:
    """S→5 오독 + 하이픈 누락에도 동 번호(02)를 잃지 않는다 — 동 이름과 엇갈리면 재확인행 (#75 리뷰)."""
    assert "0702" in code_numbers("50702")
    m = match_label([("50702", 0.9), ("역삼동", 0.9)], CANDS)
    assert m.reason == "CONFLICT" and m.confidence < CONF_MIN
