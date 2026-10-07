"""box_track — BoxTrack.track_id 규칙 시험 (voss_msgs.md)."""

from voss_vision.box_track import Detection, Tracker


def det(u: float, v: float) -> Detection:
    return Detection(u, v, (int(u) - 60, int(v) - 90, 120, 180))


def test_ids_start_at_one_and_follow_motion() -> None:
    tr = Tracker()
    ids = [tr.update([det(1100, 100 + 5 * i)])[0].id for i in range(30)]  # 벨트 따라 아래로
    assert set(ids) == {1}


def test_keeps_id_through_short_gap_and_drops_after_15() -> None:
    tr = Tracker(max_missed=15)
    for i in range(5):
        tr.update([det(1100, 300 + 4 * i)])
    for _ in range(15):  # 15 프레임 가림 → 유지
        assert tr.update([]) == []  # 미검출 프레임은 발행 안 함
    assert tr.update([det(1100, 300 + 4 * 20)])[0].id == 1  # 등속 예측 위치 근처에서 재등장
    for _ in range(16):  # 16 프레임 → 폐기
        tr.update([])
    assert tr.update([det(1100, 500)])[0].id == 2  # 새 ID, 1 은 재사용 안 함


def test_hold_id_is_not_dropped_while_picking() -> None:
    tr = Tracker(max_missed=15)
    tr.update([det(1100, 600)])
    for _ in range(60):  # 파지 중 2 s 가림
        tr.update([], hold_id=1)
    assert tr.update([det(1105, 610)], hold_id=1)[0].id == 1


def test_two_boxes_get_two_ids() -> None:
    tr = Tracker()
    out = tr.update([det(1050, 200), det(1200, 700)])
    assert [t.id for t in out] == [1, 2]
    out = tr.update([det(1052, 210), det(1201, 712)])
    assert [t.id for t in out] == [1, 2]


def test_min_hits_hides_transient_tracks() -> None:
    tr = Tracker(min_hits=5)
    assert tr.update([det(1125, 100)]) == []  # 손으로 올리는 중 잠깐 보임
    assert tr.update([det(1124, 104)]) == []
    for _ in range(20):  # 손에 가려 폐기
        tr.update([])
    out = []
    for i in range(6):
        out = tr.update([det(1142, 100 + 3 * i)])
    assert [t.id for t in out] == [2]  # 다섯 번째 검출부터 발행, ID 1 은 건너뜀


def test_restart_counts_from_one() -> None:
    tr = Tracker()
    tr.update([det(1100, 100)])
    tr.update([det(1100, 900)])  # 멀리 떨어진 새 박스
    assert Tracker().update([det(1100, 100)])[0].id == 1
