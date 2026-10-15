"""label_stage2 — 2단계(추종 중) 크롭 고르기: 끔·1단계 확실하면 건너뜀·가장 선명한 한 장·트랙당 상한·잊기."""

from voss_vision.label_match import Match
from voss_vision.label_vote import Read, Vote, vote

from voss_vision import label_stage2 as s2


def picker(**kw) -> s2.Stage2Picker:
    return s2.Stage2Picker(s2.Stage2Params(**{"enable": True, **kw}))


def test_off_reads_nothing() -> None:
    p = s2.Stage2Picker(s2.Stage2Params())
    assert p.offer(1, 50.0, "a", 0.0) == s2.OFF and p.take() is None


def test_skips_track_whose_stage1_was_always_confident() -> None:
    # sort_manager 는 재확인행 박스에만 2단계를 쓴다 → 1단계가 모두 확실했으면 CPU 를 쓰지 않는다
    p = picker()
    p.note_stage1(1, "대치동", 0.9, 0.6, 0.0)
    p.note_stage1(1, "대치동", 0.95, 0.6, 0.1)
    assert p.offer(1, 50.0, "a", 0.2) == s2.SKIP_CONFIDENT and p.take() is None


def test_reads_when_any_stage1_was_unsure_or_none_seen() -> None:
    p = picker()
    p.note_stage1(
        1, "대치동", 0.4, 0.6, 0.0
    )  # 첫 발행이 불확실 → sort_manager 가 재확인으로 보냈을 수 있다
    p.note_stage1(1, "대치동", 0.9, 0.6, 0.1)  # 뒤에 확실해져도 읽는다
    p.note_stage1(2, "", 0.0, 0.6, 0.0)  # 글자 못 읽음
    assert p.offer(1, 50.0, "a", 0.2) == s2.KEPT
    assert p.offer(2, 50.0, "b", 0.2) == s2.KEPT
    assert p.offer(3, 50.0, "c", 0.2) == s2.KEPT  # 1단계 발행을 못 봄 → 읽는다
    q = picker(skip_confident_stage1=False)
    q.note_stage1(4, "대치동", 0.9, 0.6, 0.0)
    assert q.offer(4, 50.0, "d", 0.1) == s2.KEPT


def test_keeps_the_sharpest_crop_until_taken() -> None:
    p = picker()
    assert p.offer(1, 30.0, "a", 0.0) == s2.KEPT
    assert p.offer(1, 80.0, "b", 0.1) == s2.REPLACED
    assert p.offer(1, 40.0, "c", 0.2) == s2.DULLER
    assert p.take() == (1, "b") and p.take() is None
    assert p.offer(1, 10.0, "d", 0.3) == s2.KEPT  # 넘긴 뒤에는 새로 고른다


def test_caps_ocr_per_track_and_drops_when_sure() -> None:
    p = picker(max_ocr=2)
    for i in range(2):
        assert p.offer(1, 50.0, i, i) == s2.KEPT
        assert p.take() == (1, i)
    assert p.offer(1, 99.0, "late", 3.0) == s2.CAP
    assert p.offer(2, 50.0, "x", 3.0) == s2.KEPT
    p.drop(2)
    assert p.take() is None


def test_min_sharpness_and_sharpest_track_first() -> None:
    p = picker(min_sharpness=20.0)
    assert p.offer(1, 10.0, "blur", 0.0) == s2.BLURRY
    p.offer(1, 30.0, "a", 0.0)
    p.offer(2, 90.0, "b", 0.0)
    assert p.take() == (2, "b") and p.take() == (1, "a")


def test_forget_clears_old_tracks() -> None:
    p = picker(max_ocr=1)
    p.note_stage1(1, "대치동", 0.4, 0.6, 0.0)
    p.offer(1, 50.0, "a", 0.0)
    p.take()
    assert p.forget(31.0, 30.0) == 1
    assert p.offer(1, 50.0, "again", 31.0) == s2.KEPT  # 기록이 지워져 상한도 처음부터


def votes(*reads: tuple[str, float, float]) -> Vote:
    """(동, 신뢰도, 선명도) 크롭들 → 2단계 투표(선명도 가중)."""
    codes = {"역삼동": "S07-01", "대치동": "S07-02", "청담동": "S07-03"}
    rs = [
        Read(Match(codes.get(d, ""), d, c, reason="AGREE" if d else "NONE"), i, sh)
        for i, (d, c, sh) in enumerate(reads)
    ]
    return vote(rs, weighted=True)


def test_publish_only_when_enough_agree() -> None:
    # #171 리뷰: sort_manager 는 확실한 2단계 한 번에 구역을 바꾼다 → 1장(같은 동 1) 은 내지 않는다
    assert not s2.publishable(votes(("대치동", 1.0, 50)), 0.6, 2)
    assert s2.publishable(votes(("대치동", 0.9, 50), ("대치동", 0.8, 60)), 0.6, 2)
    assert not s2.publishable(
        votes(("대치동", 0.5, 50), ("대치동", 0.5, 50)), 0.6, 2
    )  # 신뢰도 미달
    assert not s2.publishable(votes(("", 0.0, 50)), 0.6, 2)
    assert s2.publishable(votes(("대치동", 0.7, 50)), 0.6, 1)  # min_agree 1 이면 1장으로도


def test_dissent_is_never_published() -> None:
    # #171 리뷰(김학민·정의석): 2:1 로 갈리면 신뢰도가 0.6 을 넘어도 내지 않는다 — 재확인으로
    flat = votes(("대치동", 1.0, 50), ("대치동", 1.0, 50), ("역삼동", 1.0, 50))
    sharp = votes(("역삼동", 1.0, 30), ("대치동", 1.0, 100), ("대치동", 1.0, 100))
    for v in (flat, sharp):
        assert v.match.dong == "대치동" and v.match.confidence >= 0.6 and v.agree == 2
        assert not s2.publishable(v, 0.6, 2)


def test_unreadable_crop_is_not_dissent() -> None:
    # 글자를 못 읽은 크롭(NONE)은 반대표가 아니다
    v = votes(("대치동", 0.9, 50), ("", 0.0, 80), ("대치동", 0.9, 60))
    assert (v.agree, v.picked, v.total) == (2, 2, 3) and s2.publishable(v, 0.6, 2)
