"""label_vote — 트랙별 다수결: 같은 동이면 평균, 엇갈리면 낮아짐, NONE 은 분모 제외, 확실하면 그만 읽기."""

import pytest
from voss_vision.label_match import Match
from voss_vision.label_vote import Read, TrackReads, vote

MS = 1_000_000


def m(dong: str, conf: float, code: str = "", alt: str = "", alt_conf: float = 0.0) -> Match:
    codes = {"역삼동": "S07-01", "대치동": "S07-02", "청담동": "S07-03"}
    return Match(
        code or codes.get(dong, ""),
        dong,
        conf,
        alt,
        alt_conf,
        raw_text=f"{dong}?",
        reason="AGREE" if dong else "NONE",
    )


def r(dong: str, conf: float, t: int, **kw) -> Read:
    return Read(m(dong, conf, **kw), t * MS)


def test_single_read_passes_through() -> None:
    v = vote([r("대치동", 0.93, 10, alt="청담동", alt_conf=0.2)])
    assert (v.match.code, v.match.dong, v.match.confidence) == ("S07-02", "대치동", 0.93)
    assert (v.match.dong_alt, v.match.confidence_alt) == ("청담동", 0.2)
    assert (v.agree, v.picked, v.total, v.stamp_ns) == (1, 1, 1, 10 * MS)


def test_agreeing_reads_average_and_latest_stamp() -> None:
    v = vote([r("대치동", 0.9, 10), r("대치동", 0.7, 30), r("대치동", 0.8, 20)])
    assert v.match.dong == "대치동" and v.match.confidence == pytest.approx(0.8)
    assert v.stamp_ns == 30 * MS and v.agree == 3 and v.match.raw_text == "대치동?"


def test_disagreement_lowers_confidence_and_names_runner_up() -> None:
    v = vote([r("대치동", 0.9, 10), r("청담동", 0.9, 20), r("대치동", 0.9, 30)])
    assert v.match.dong == "대치동" and v.match.confidence == pytest.approx(0.6)
    assert v.match.dong_alt == "청담동" and v.match.confidence_alt == pytest.approx(0.3)
    tie = vote([r("대치동", 0.9, 10), r("청담동", 0.9, 20)])
    assert tie.match.confidence == pytest.approx(0.45)  # 반반 → 재확인 쪽(0.6 미만)


def test_none_reads_are_not_counter_evidence() -> None:
    v = vote([r("", 0.0, 10), r("대치동", 0.95, 20), r("", 0.0, 30)])
    assert v.match.confidence == pytest.approx(0.95) and (v.picked, v.total) == (1, 3)
    assert v.stamp_ns == 20 * MS  # 판정에 쓴 크롭의 촬영 시각
    empty = vote([r("", 0.0, 10), r("", 0.0, 40)])
    assert empty.match.dong == "" and empty.match.confidence == 0.0 and empty.stamp_ns == 40 * MS


def test_track_reads_enough_and_forget() -> None:
    tr = TrackReads()
    tr.add(5, 1, r("대치동", 0.9, 10), now=0.0)
    assert not tr.enough(5, 1, conf_min=0.6, min_agree=2)  # 한 장으로는 아직
    tr.add(5, 1, r("대치동", 0.8, 20), now=1.0)
    assert tr.enough(5, 1, 0.6, 2)
    assert not tr.enough(5, 2, 0.6, 2)  # 단계가 다르면 따로
    tr.add(6, 1, r("대치동", 0.9, 10), now=1.0)
    tr.add(6, 1, r("청담동", 0.9, 20), now=1.0)
    assert not tr.enough(6, 1, 0.6, 2)  # 엇갈리면 더 읽는다
    assert tr.forget(now=40.0, older_than_s=30.0) == 2 and not tr.reads
