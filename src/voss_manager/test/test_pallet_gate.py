"""pallet_gate (S2-T13) — 실제 pallet_fsm 을 가짜 gateway 로 돌려 만든 사건열로 게이트 기록표를 시험한다.

노드처럼 이벤트마다 바뀐 PalletState·PalletResult(PalletOut)·Say 를 '녹화'한다. D3 제안 회차(역삼 8개 = 1·2열, 2층 4칸).
"""

import os
from dataclasses import asdict, replace

import pytest
import yaml

from voss_manager import pallet_fsm as pf
from voss_manager import pallet_gate as pg
from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

# 로직 시험은 고정 설정(3×1)을 읽는다 — 레포 config 의 현장 값이 바뀌어도 기대값이 그대로다(S2-T21)
TEST_CONFIG = os.path.join(os.path.dirname(__file__), "fixtures", "voss_config_3x1.yaml")
SID, RUN = "20261013T170000-a1b2", "20261013T173000-c3d4"
MS = 1_000_000
T0 = 1_791_890_000.0  # 녹화 시각(epoch s) 기준
Y, D = "역삼동", "대치동"


@pytest.fixture
def cfg() -> f.Config:
    with open(TEST_CONFIG, encoding="utf-8") as fh:
        return replace(f.load_config(yaml.safe_load(fh)), pallet_ready=True)


def record(cfg: f.Config, counts: dict, route: str, answer, run_id: str = RUN, t0: float = T0):
    """palletize 한 회차를 돌려 (사건열, 최종 ctx). answer(CallMove) → MoveDone 인자 (ok, msg, placed)."""
    events, last, t = [], None, t0
    zone_of = {Y: "A", D: "B", "청담동": "C"}
    pl, n = [], 0
    for d, k in counts.items():
        for s in range(k):
            n += 1
            pl.append(pp.Placement(f"{SID}-{n:03d}", d, zone_of[d], s, "PLACED", n * 1000 * MS))

    def step(ctx, ev):
        nonlocal last, t
        out = pf.step(ctx, ev)
        for a in out.actions:
            if isinstance(a, pf.PalletOut):
                events.append(
                    pg.Ev(
                        t, pg.TOPIC_RESULT, {k: v for k, v in asdict(a).items() if k != "stamp_ns"}
                    )
                )
            elif isinstance(a, f.Say):
                events.append(pg.Ev(t, pg.TOPIC_SAY, {"data": a.text}))
        st = pf.pallet_state(out.ctx)
        if st != last:
            events.append(pg.Ev(t, pg.TOPIC_STATE, st))
            last = st
        return out

    ctx = f.new_ctx(cfg)
    ctx = pf.step(ctx, f.Command("start", "", 0, (), SID)).ctx
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 1000 * MS)).ctx
    out = step(ctx, f.Command("palletize", route, 2000 * MS, (), run_id))
    t += 1.0
    out = step(out.ctx, pf.ListDone(True, "", tuple(pl), 3000 * MS))
    seen, i = list(out.actions), 0
    while True:
        moves = [a for a in seen if isinstance(a, f.CallMove)]
        if len(moves) <= i:
            break
        t += 4.0 if moves[i].mode in ("PICK", "DROP") else 6.0  # PICK·DROP 4 s, OBSERVE 복귀 6 s
        ok, msg, placed = answer(moves[i])
        out = step(out.ctx, f.MoveDone(ok, msg, int(t * 1e9) if placed else 0, int(t * 1e9)))
        seen += list(out.actions)
        i += 1
        assert i < 200
    return events, out.ctx


def ok_all(a):
    return True, "OK", a.mode == "DROP"


def test_d3_run_all_done_is_a_candidate(cfg) -> None:
    events, _ = record(cfg, {Y: 8}, Y, ok_all)
    rows = [pg.summarize_run(rid, evs) for rid, evs in pg.split_runs(events).items()]
    assert len(rows) == 1
    r = rows[0]
    assert (r.route, r.total, r.done, r.failed, r.slots_ok, r.layer2, r.pulled) == (
        (Y,),
        8,
        8,
        (),
        8,
        4,
        0,
    )
    assert r.results == 8 and r.unloaded == 0
    assert r.max_s == pytest.approx(8.0)  # PICK 4 s + DROP 4 s, 박스마다 관측 복귀 없음
    assert r.finished and r.finish_said and r.candidate
    cells = pg.table_row(1, r)
    assert len(cells) == len(pg.COLUMNS) == 12
    assert cells[7] == "명령 8/8 (2층 4) · 실물 눈 확인" and cells[9] == "기대 8 · DB 확인"
    assert cells[11].startswith("완주 후보")


def test_grip_fail_on_layer1_is_not_complete_and_shows_pull_down(cfg) -> None:
    """slot 0 박스 GRIP_FAIL 3회 → FAILED, 그 위 slot 2 박스를 slot 0 에 당겨 놓음(#37)."""

    def answer(a):
        if a.mode == "PICK" and (a.zone, a.slot) == ("A", 0):
            return False, "GRIP_FAIL: 집기 확인 실패", False
        return ok_all(a)

    events, _ = record(cfg, {Y: 8}, Y, answer)
    (r,) = [pg.summarize_run(rid, evs) for rid, evs in pg.split_runs(events).items()]
    assert r.done == 7 and r.failed == ((f"{SID}-001", "GRIP_FAIL"),) and r.pulled == 1
    assert r.slots_ok == 6 and not r.candidate
    cells = pg.table_row(1, r)
    assert cells[6] == "1 (001번 GRIP_FAIL)"
    assert "당겨 놓음 1" in cells[7]
    assert cells[11].startswith("미완주 — FAILED 1") and "칸이 계획과 다름" in cells[11]
    detail = pg.render([r])
    # slot 2(화면 칸 3) 박스를 slot 0(칸 1) 에 놓았다
    assert "| 역삼동 | 3 | 1 (당겨 놓음) | 1 | DONE |" in detail


def test_overflow_rows_are_expected_in_pallet_log(cfg) -> None:
    """S1(19개): 16개 싣고 초과 3 → 기대 pallet_log 19행, 싣지 않은 박스는 박스당 시간에 넣지 않는다."""
    events, _ = record(cfg, {Y: 7, D: 6, "청담동": 6}, "대치동,역삼동,청담동", ok_all)
    (r,) = [pg.summarize_run(rid, evs) for rid, evs in pg.split_runs(events).items()]
    assert (r.total, r.done, r.results, r.unloaded) == (16, 16, 19, 3)
    assert pg.table_row(1, r)[9] == "기대 19(미적재 3 포함) · DB 확인"
    assert r.candidate and r.max_s == pytest.approx(8.0)


def test_two_runs_in_one_recording_are_two_rows(cfg) -> None:
    ev1, _ = record(cfg, {Y: 2}, Y, ok_all, run_id="20261013T173000-aaaa", t0=T0)
    ev2, _ = record(cfg, {Y: 2}, Y, ok_all, run_id="20261013T175000-bbbb", t0=T0 + 1200)
    runs = pg.split_runs(ev2 + ev1)  # 순서가 섞여도 시각순
    assert list(runs) == ["20261013T173000-aaaa", "20261013T175000-bbbb"]
    text = pg.render([pg.summarize_run(k, v) for k, v in runs.items()])
    assert text.count("완주 후보") == 2
    assert text.splitlines()[0] == "| " + " | ".join(pg.COLUMNS) + " |"


def test_slow_box_is_flagged_against_nfr15(cfg) -> None:
    events, _ = record(cfg, {Y: 2}, Y, ok_all)
    late = [pg.Ev(e.t + (40.0 if e.topic == pg.TOPIC_RESULT and e.data["box_id"].endswith("002") else 0.0),
                  e.topic, e.data) for e in events]  # fmt: skip
    (r,) = [pg.summarize_run(k, v) for k, v in pg.split_runs(late).items()]
    assert r.max_s > pg.NFR15_S and pg.table_row(1, r)[10].endswith("⚠")


def test_no_finish_sentence_is_not_a_candidate(cfg) -> None:
    events, _ = record(cfg, {Y: 2}, Y, ok_all)
    quiet = [e for e in events if e.topic != pg.TOPIC_SAY]
    (r,) = [pg.summarize_run(k, v) for k, v in pg.split_runs(quiet).items()]
    assert not r.finish_said and not r.candidate and "끝 안내 없음" in pg.table_row(1, r)[11]
