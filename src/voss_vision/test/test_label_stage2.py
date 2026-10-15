"""label_stage2 — 2단계(추종 중) 크롭 고르기: 끔·1단계 확실하면 건너뜀·가장 선명한 한 장·트랙당 상한·잊기."""

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
