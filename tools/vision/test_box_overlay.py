"""box_overlay 의 BOX 번호(BoxNumbers)·초록 글자 시험 — ROS 없이. `python3 -m pytest tools/vision`(colcon 패키지가 아니라 CI 밖)."""

from types import SimpleNamespace

import numpy as np
from box_overlay import TRACK, BoxNumbers, Painter
from voss_vision.box_detect import SegParams

S1 = "20261014T090000-abcd"
S2 = "20261014T100000-ef01"
MS = 1_000_000


def tr(tid: int, u: float = 500.0, v: float = 300.0) -> SimpleNamespace:
    return SimpleNamespace(track_id=tid, u=u, v=v)


def walk(b: BoxNumbers, tid: int, t0: int, t1: int, u0: float, du_per_s: float = 220.0) -> float:
    """벨트처럼 u 가 초당 du_per_s px 로 늘며 33 ms 마다 발행. 마지막 u 를 돌려준다."""
    u = u0
    for t in range(t0, t1 + 1, 33):
        u = u0 + du_per_s * (t - t0) / 1000
        b.tracks(t * MS, [tr(tid, u)])
    return u


def test_number_from_sort_manager_box_id() -> None:
    b = BoxNumbers()
    b.tracks(0, [tr(3)])
    assert b.label(3) == "BOX"  # 판독 전
    b.sort_msg(f"{S1}-001", 3, S1)
    assert b.label(3) == "BOX1"


def test_session_change_drops_numbers() -> None:
    b = BoxNumbers()
    b.tracks(0, [tr(3)])
    b.sort_msg(f"{S1}-001", 3, S1)
    b.sort_msg("", -1, S2)  # 새 start 의 첫 SortState
    assert b.label(3) == "BOX"


def test_old_build_session_from_box_id() -> None:
    b = BoxNumbers()
    b.sort_msg(f"{S1}-005", 2)
    b.sort_msg(f"{S2}-001", 9)
    assert b.label(2) == "BOX" and b.label(9) == "BOX1"


def test_tracker_restart_reuses_id_quickly() -> None:
    """의석 리뷰(#49): box_tracker 가 5 s 안에 다시 떠 같은 id 를 써도 앞 번호가 남지 않는다."""
    b = BoxNumbers()
    walk(b, 3, 0, 297, 600)
    b.sort_msg(f"{S1}-001", 3, S1)
    b.tracks(1000 * MS, [tr(3, 200)])  # 0.7 s 뒤 재시작한 tracker 의 새 track 3
    assert b.label(3) == "BOX"
    for t in (5000, 8000):  # 4~8 s 뒤 다시 써도 같다
        b.sort_msg(f"{S1}-001", 3, S1)
        b.tracks(t * MS, [tr(3, 200)])
        assert b.label(3) == "BOX"


def test_tracker_restart_within_0p6s_elsewhere() -> None:
    """의석 리뷰(#49 2차): 0.5 s 만에 다시 뜬 tracker 가 다른 자리의 새 박스에 같은 id 를 줘도 번호가 안 남는다(녹화 재생)."""
    b = BoxNumbers()
    u = walk(b, 3, 0, 297, 600)
    b.sort_msg(f"{S1}-001", 3, S1)
    # 벨트 입구 쪽 새 박스 — 예측 자리(u + 110 px)에서 수백 px
    b.tracks((297 + 500) * MS, [tr(3, 150)])
    assert b.label(3) == "BOX"
    assert u > 600


def test_restart_signal_drops_all() -> None:
    """실시간: /voss/vision/box 발행자 GID 가 바뀌면 restart() — 간격·자리와 상관없이 전부 버린다."""
    b = BoxNumbers()
    b.tracks(0, [tr(3), tr(4, 900)])
    b.sort_msg(f"{S1}-001", 3, S1)
    b.restart()
    b.tracks(50 * MS, [tr(3)])  # 0.05 s 뒤 같은 자리라도
    assert b.label(3) == "BOX"


def test_short_miss_keeps_number() -> None:
    """미검출 프레임은 발행이 없다 — max_missed(0.5 s) 안의 끊김은 같은 트랙."""
    b = BoxNumbers()
    u = walk(b, 3, 0, 297, 600)
    b.sort_msg(f"{S1}-001", 3, S1)
    # 0.5 s 미검출 뒤 벨트로 110 px 간 자리 — 같은 박스
    b.tracks((297 + 500) * MS, [tr(3, u + 110)])
    assert b.label(3) == "BOX1"


def test_camera_motion_short_gap_keeps_number() -> None:
    """그리퍼 카메라가 움직여 픽셀이 크게 뛰어도 끊김이 0.1 s 안이면 버리지 않는다."""
    b = BoxNumbers()
    b.tracks(0, [tr(3)])
    b.sort_msg(f"{S1}-001", 3, S1)
    b.tracks(66 * MS, [tr(3, 800, 600)])
    assert b.label(3) == "BOX1"


def test_occluded_picking_track_comes_back_via_sort_state() -> None:
    b = BoxNumbers()
    b.tracks(0, [tr(3)])
    b.sort_msg(f"{S1}-001", 3, S1)
    b.tracks(2000 * MS, [tr(3)])  # 그리퍼에 가려졌다 다시 — 일단 버리고
    assert b.label(3) == "BOX"
    b.sort_msg(f"{S1}-001", 3, S1)  # 0.4 s 안의 SortState 가 다시 붙인다
    assert b.label(3) == "BOX1"


def _green(**kw) -> str:
    got = []
    p = Painter(0.5)
    p._texts = lambda img, texts: got.extend(texts) or img
    t = SimpleNamespace(bbox=(100, 100, 80, 60), track_id=3, u=140.0, v=130.0, position_valid=True)
    p.render(np.zeros((480, 640, 3), np.uint8), [], SegParams(), [t], {}, [], score_cands=[], **kw)
    return next(x[2] for x in got if x[3] == TRACK)


def test_percent_off_vs_no_match() -> None:
    assert _green() == "BOX -%"  # 판정은 했고 짝 없음
    assert _green(score=False) == "BOX"  # --no-score
