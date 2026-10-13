"""팔레타이징 검증 (verify/palletizing, BRD v1.5) — 검증 프롬프트 v2 의 명세를 구현(pallet_plan·pallet_fsm)에 대조한다.

구현 쪽 시험(test_pallet_plan·test_pallet_fsm)과 따로, 정답 생성기(프롬프트 2.3 원본)와 명세 표·불변식으로 판정한다.
- 줄 순서(같은 층 1줄·2줄)는 명세 미정(D6) — 줄을 바꾼 결과도 정답으로 본다.
- 명세 미정 동작(FAILED 칸, 대상 0개 등)은 "기록" 시험으로 남긴다 — 동작이 바뀌면 보고서와 함께 고친다.
보고서: docs/verification/palletizing_report.md
"""

import itertools
import os
import random
from dataclasses import replace

import pytest
import yaml

from voss_manager import pallet_fsm as pf
from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

REPO_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "voss_config.yaml"
)
Y, D, C = "역삼동", "대치동", "청담동"
ZONE_OF = {Y: "A", D: "B", C: "C"}
SID = "20261013T090000-v15a"
MS = 1_000_000
CAP = 16


# ---------------------------------------------------------------- 정답 생성기 (검증 프롬프트 v2 2.3 원본)


def ref_plan(route, counts):
    excluded = {z: n for z, n in counts.items() if z not in route and n > 0}
    total = sum(counts.get(z, 0) for z in route)
    if total <= CAP:
        load = {z: counts.get(z, 0) for z in route}
    else:
        visit = {z: i for i, z in enumerate(route)}
        prio = sorted(route, key=lambda z: (-counts.get(z, 0), -visit[z]))
        left, load = CAP, {}
        for z in prio:
            load[z] = min(counts.get(z, 0), left)
            left -= load[z]
    remain = {z: counts.get(z, 0) - load[z] for z in route}
    slots, s = [], 0
    for z in reversed(route):
        for _ in range(load[z]):
            col, w = divmod(s, 4)
            layer, lane = divmod(w, 2)
            slots.append(
                {
                    "order": s + 1,
                    "slot": s,
                    "col": col + 1,
                    "layer": layer + 1,
                    "lane": lane + 1,
                    "zone": z,
                }
            )
            s += 1
    return {"total": total, "overflow": max(0, total - CAP), "load": load,
            "remain_overflow": remain, "excluded": excluded, "slots": slots}  # fmt: skip


# 명세 2.4 표 (행 = 2층1줄, 2층2줄, 1층1줄, 1층2줄 / 열 = 1~4열, 역·대·청·-)
SCENARIOS = {
    "S1": ((Y, D, C), {Y: 7, D: 6, C: 6}, ["청대역역", "청대역역", "청청대역", "청청역역"]),
    "S2": ((C, Y, D), {Y: 7, D: 6, C: 6}, ["대역역청", "대역역청", "대대역역", "대대역청"]),
    "S3": ((Y, C), {Y: 7, D: 6, C: 6}, ["청역역-", "청역역-", "청청역역", "청청역-"]),
    "S4": ((Y, D, C), {Y: 6, D: 5, C: 5}, ["청대역역", "청대역역", "청청대역", "청대대역"]),
    "S5": ((Y, D, C), {Y: 8, D: 6, C: 5}, ["대대역역", "대대역역", "청대역역", "청대역역"]),
    "S6": ((Y, D, C), {Y: 6, D: 6, C: 6}, ["청대대역", "청대대역", "청청대역", "청청대역"]),
    "S7": ((D, Y, C), {Y: 4, D: 3, C: 5}, ["청역대-", "청역대-", "청청역-", "청역대-"]),
    "S8": ((D, Y, C), {Y: 7, D: 6, C: 6}, ["청역역대", "청역역대", "청청역역", "청청역대"]),
}
ROWS = ((2, 1), (2, 2), (1, 1), (1, 2))  # (층, 줄)
ABBR = {Y: "역", D: "대", C: "청"}


def table_of(cells: dict) -> list[str]:
    """{(열, 층, 줄): 동} → 명세 표 4줄."""
    return [
        "".join(ABBR.get(cells.get((c, la, ln), ""), "-") for c in range(1, 5)) for la, ln in ROWS
    ]


def same_table(got: list[str], want: list[str]) -> bool:
    return got == want or [got[1], got[0], got[3], got[2]] == want  # 줄 대칭 허용 (D6)


def placements(counts):
    out, k = [], 0
    for dong, n in counts.items():
        for s in range(n):
            k += 1
            out.append(
                pp.Placement(f"{SID}-{k:03d}", dong, ZONE_OF[dong], s, "PLACED", k * 1000 * MS)
            )
    return out


def impl(route, counts) -> dict:
    """구현 → 정답 생성기와 같은 모양."""
    plan = pp.plan_pallet(route, placements(counts))
    rows = {d: (n, o, e) for d, n, o, e in plan.counts()}
    return {
        "load": {d: rows[d][0] for d in route},
        "overflow": plan.overflow,
        "remain_overflow": {d: rows[d][1] for d in route},
        "excluded": {d: e for d, (_, _, e) in rows.items() if e},
        "cells": {m.cell: m.dong for m in plan.moves},
        "order": [m.dong for m in plan.moves],
        "plan": plan,
    }


def diff(route, counts) -> list[str]:
    ref = ref_plan(route, counts)
    try:
        got = impl(route, counts)
    except pp.PlanError as e:
        return [f"PlanError: {e}"]
    out = []
    for key in ("load", "overflow", "remain_overflow", "excluded"):
        if got[key] != ref[key]:
            out.append(f"{key} 기대 {ref[key]} 실제 {got[key]}")
    ref_cells = {(x["col"], x["layer"], x["lane"]): x["zone"] for x in ref["slots"]}
    if not same_table(table_of(got["cells"]), table_of(ref_cells)):
        out.append(f"칸 배치 기대 {table_of(ref_cells)} 실제 {table_of(got['cells'])}")
    if got["order"] != [x["zone"] for x in ref["slots"]]:
        out.append("적재 순서(동) 다름")
    return out


# ---------------------------------------------------------------- 3단계: 계획


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_reference_reproduces_spec_table(name) -> None:
    route, counts, table = SCENARIOS[name]
    ref = ref_plan(route, counts)
    assert same_table(
        table_of({(x["col"], x["layer"], x["lane"]): x["zone"] for x in ref["slots"]}), table
    )


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_matches_spec(name) -> None:
    route, counts, table = SCENARIOS[name]
    assert diff(route, counts) == []
    assert same_table(table_of(impl(route, counts)["cells"]), table)


def test_lane_order_is_lane1_first() -> None:
    """D6(명세 미정) 기록: 구현은 같은 층에서 1줄 → 2줄 — 명세 표와 줄 대칭 없이 그대로 같다."""
    route, counts, table = SCENARIOS["S1"]
    assert table_of(impl(route, counts)["cells"]) == table


def random_inputs(n: int = 500, seed: int = 20261013):
    rng = random.Random(seed)
    routes = [p for k in (1, 2, 3) for p in itertools.permutations((Y, D, C), k)]
    for _ in range(n):
        yield (
            rng.choice(routes),
            {Y: rng.randint(0, 10), D: rng.randint(0, 10), C: rng.randint(0, 10)},
        )


def invariant_failures(route, counts) -> list[str]:
    """명세 2.5 불변식 1~6 + 정답 생성기 비교."""
    ref = ref_plan(route, counts)
    if ref["total"] == 0:
        return []  # 대상 0개 — 명세 미정, 따로 시험
    try:
        got = impl(route, counts)
    except pp.PlanError as e:
        return [f"PlanError: {e}"]
    bad = list(diff(route, counts))
    moves = got["plan"].moves
    if len(moves) != min(ref["total"], CAP):
        bad.append("inv1 실은 수")
    if any(got["load"][d] + got["remain_overflow"][d] != counts[d] for d in route):
        bad.append("inv1 실은 수 + 못 실은 수 ≠ 물량")
    if [m.pallet_slot for m in moves] != list(range(len(moves))):
        bad.append("inv2 칸 번호 중복·빈틈")
    cells = {m.cell for m in moves}
    if any((c, 1, ln) not in cells for (c, la, ln) in cells if la == 2):
        bad.append("inv3 2층 아래 1층 빔")
    visit = {d: i for i, d in enumerate(route)}
    for a in moves:
        for b in moves:
            if visit[a.dong] > visit[b.dong] and (
                a.cell[0] > b.cell[0] or (a.cell[0] == b.cell[0] and a.cell[1] > b.cell[1])
            ):
                bad.append("inv4 나중에 내릴 박스가 위·바깥")
    if any(m.dong not in route for m in moves):
        bad.append("inv5 경로 밖 동 적재")
    for x in route:
        if got["remain_overflow"][x]:
            for y in route:
                if (
                    counts[y] < counts[x] or (counts[y] == counts[x] and visit[y] < visit[x])
                ) and got["load"][y]:
                    bad.append(f"inv6 {x} 가 남았는데 후순위 {y} 적재")
    return bad


def test_invariants_random_500() -> None:
    fails = [(r, c, x) for r, c in random_inputs() if (x := invariant_failures(r, c))]
    assert not fails, f"{len(fails)}/500 실패, 예: {fails[:3]}"


def test_no_v14_residue() -> None:
    """v1.4 잔재 없음: 동별 3개 상한 없음(7개도 계획), 열 수 = 동 수가 아님(16칸 고정), 층 있음."""
    got = impl((Y,), {Y: 7})
    assert len(got["plan"].moves) == 7 and {c[1] for c in got["cells"]} == {1, 2}
    assert not hasattr(got["plan"], "cols") and not hasattr(f.CallMove("PALLET", 0, "DROP"), "cols")


def test_target_selection_hold_excluded_operator_box_included() -> None:
    hold = pp.Placement(f"{SID}-900", Y, "HOLD", 0, "HELD", 1)
    blurry = pp.Placement(
        f"{SID}-901", Y, "A", 6, "PLACED", 99_000 * MS
    )  # 작업자가 "역삼" 이라고 답해 적재
    plan = pp.plan_pallet((Y,), placements({Y: 6}) + [hold, blurry])
    ids = [m.box_id for m in plan.moves]
    assert f"{SID}-901" in ids and f"{SID}-900" not in ids and len(ids) == 7


def test_route_input_validation() -> None:
    cfg = f.load_config(yaml.safe_load(open(REPO_CONFIG, encoding="utf-8")))
    for arg, msg in [
        ("", "1~3개"),
        ("역삼,역삼동", "두 번"),
        ("삼성동,역삼", "등록되지 않은"),
        ("역삼,대치,청담,역삼", "1~3개"),
    ]:
        with pytest.raises(pp.PlanError, match=msg):
            pp.parse_route(arg, cfg.dong_of)
    assert pp.parse_route("역삼, 대치동,청담", cfg.dong_of) == (Y, D, C)
    plan = pp.plan_pallet((Y, C), placements({Y: 2, C: 0}))  # 물량 0 인 동
    assert plan.empty == (C,) and plan.counts()[1] == (C, 0, 0, 0)
    with pytest.raises(
        pp.PlanError, match="옮길 박스가 없음"
    ):  # 대상 0개: 시작 거부 (명세 미정 기록)
        pp.plan_pallet((C,), placements({Y: 2}))


def test_plan_is_pure_and_deterministic() -> None:
    recs = placements({Y: 7, D: 6, C: 6})
    a = pp.plan_pallet((D, Y, C), recs)
    for k in range(10):
        shuffled = recs[:]
        random.Random(k).shuffle(shuffled)
        assert pp.plan_pallet((D, Y, C), shuffled) == a


# ---------------------------------------------------------------- 4단계: 시작·안내·기록·재개 (가짜 장비)


@pytest.fixture
def cfg() -> f.Config:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        return replace(f.load_config(yaml.safe_load(fh)), pallet_ready=True)


def running(cfg):
    ctx = f.new_ctx(cfg)
    ctx = pf.step(ctx, f.Command("start", "", 0, (), SID)).ctx
    return pf.step(ctx, f.MoveDone(True, "OK", 0, 1000 * MS)).ctx


def started(cfg, arg, counts):
    out = pf.step(running(cfg), f.Command("palletize", arg, 2000 * MS, (), "RUN"))
    return pf.step(out.ctx, pf.ListDone(True, "", tuple(placements(counts)), 3000 * MS))


def drive(ctx, acts, limit=200):
    """가짜 gateway: 보낸 CallMove 에 차례로 성공 응답."""
    seen, i = list(acts), 0
    while i < limit:
        mv = [a for a in seen if isinstance(a, f.CallMove)]
        if len(mv) <= i:
            return ctx, seen
        a = mv[i]
        out = pf.step(
            ctx, f.MoveDone(True, "OK", (5 + i) * MS if a.mode == "DROP" else 0, (5 + i) * MS)
        )
        ctx, i = out.ctx, i + 1
        seen += list(out.actions)
    raise AssertionError("끝나지 않음")


def test_start_conditions(cfg) -> None:
    busy = replace(running(cfg), state=f.PICKING)
    assert pf.step(busy, f.Command("palletize", "역삼,대치,청담", 0, (), "R")).reply == (
        False, "분류 중인 박스를 마친 뒤 다시 말씀해 주세요")  # fmt: skip
    full = replace(running(cfg), pallet_count=1)
    assert "reset_zone PALLET" in pf.step(full, f.Command("palletize", "역삼", 0, (), "R")).reply[1]
    out = pf.step(running(cfg), f.Command("palletize", "역삼", 0, (), "R"))
    back = pf.step(out.ctx, pf.ListDone(False, "DB_ERROR", (), 1))
    assert back.ctx.state == f.RUNNING and not [
        a for a in back.actions if isinstance(a, f.CallMove)
    ]


def test_s8_start_sentence_and_plan_before_first_pick(cfg) -> None:
    out = started(cfg, "대치,역삼,청담", {Y: 7, D: 6, C: 6})
    acts = [a for a in out.actions if not isinstance(a, f.Log)]
    names = [type(a).__name__ for a in acts]
    says = [a.text for a in acts if isinstance(a, f.Say)]
    assert "첫 배송지 대치동은 오른쪽" in says[0]  # TR-PAL-10 ②
    assert names.index("PublishPalletState") < names.index("CallMove")  # TR-PAL-10 ① 첫 PICK 전
    st = pf.pallet_state(out.ctx)
    assert (st["dongs"], st["load"], st["overflow"], st["excluded"]) == (
        [D, Y, C],
        [3, 7, 6],
        [3, 0, 0],
        [0, 0, 0],
    )
    assert st["overflow_warning"] is True and len(st["slot_state"]) == 16


def test_s3_excluded_has_no_overflow_warning(cfg) -> None:
    st = pf.pallet_state(started(cfg, "역삼,청담", {Y: 7, D: 6, C: 6}).ctx)
    assert st["overflow_warning"] is False and st["excluded"][st["dongs"].index(D)] == 6


def test_s1_records_and_finish_sentence(cfg) -> None:
    out = started(cfg, "역삼,대치,청담", {Y: 7, D: 6, C: 6})
    ctx0 = replace(out.ctx, slots={**out.ctx.slots, "A": 7, "B": 6, "C": 6})  # 트레이에 놓인 수
    ctx, acts = drive(ctx0, list(out.actions))
    res = [a for a in acts if isinstance(a, pf.PalletOut)]
    assert len(res) == 19 and sorted({r.outcome for r in res}) == [
        "DONE",
        "OVERFLOW",
    ]  # TR-PAL-09: 16 + 초과 3
    over = [r for r in res if r.outcome == "OVERFLOW"]
    assert {(r.dong, r.zone, r.pallet_slot) for r in over} == {
        (D, "B", -1)
    }  # 원래 구역 B 에 남음 (TR-PAL-11)
    text = [a.text for a in acts if isinstance(a, f.Say)][-1]
    assert all(
        s in text
        for s in ("역삼동 7개", "대치동 3개", "청담동 6개", "초과로 못 실은 박스는 대치동 3개")
    )
    assert (ctx.slots["A"], ctx.slots["B"], ctx.slots["C"]) == (
        0,
        6,
        0,
    )  # 다 옮긴 트레이만 칸 0, 대치는 남은 3개 때문에 그대로


def test_resume_continues_at_next_slot(cfg) -> None:
    out = started(cfg, "청담", {C: 3})
    ctx = pf.step(out.ctx, f.Command("stop", "", 4 * MS)).ctx  # 집는 중 "멈춰"
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5 * MS)).ctx  # 든 채 PAUSED
    o = pf.step(ctx, f.Command("resume", "", 7 * MS, grip_mm=41.0))
    assert [(a.zone, a.slot, a.mode) for a in o.actions if isinstance(a, f.CallMove)] == [
        ("PALLET", 0, "DROP")
    ]
    o = pf.step(o.ctx, f.MoveDone(True, "OK", 8 * MS, 8 * MS))
    assert [(a.zone, a.slot) for a in o.actions if isinstance(a, f.CallMove)] == [("C", 1)]


def test_failed_box_slot_without_box_above(cfg) -> None:
    """1층 칸 2개뿐(위층 없음)이면 FAILED 칸은 비워 두고 다음 박스는 계획한 칸에 (위층이 있으면 아래 시험 — #37)."""
    ctx = started(cfg, "청담", {C: 2}).ctx
    for _ in range(3):
        o = pf.step(ctx, f.MoveDone(False, "GRIP_FAIL", 0, 4 * MS))
        ctx = o.ctx
    assert [(a.zone, a.slot, a.mode) for a in o.actions if isinstance(a, f.CallMove)] == [
        ("C", 1, "PICK")
    ]
    o = pf.step(ctx, f.MoveDone(True, "OK", 0, 5 * MS))
    # MoveToZone PALLET 은 gateway 격자 번호로 부른다(slot 1 = 1열 1층 2줄 → 격자 4, 10/13 통합)
    assert [(a.zone, a.slot) for a in o.actions if isinstance(a, f.CallMove)] == [
        ("PALLET", pp.grid_cell(1))
    ]


def test_layer2_box_pulled_down_onto_failed_slot(cfg) -> None:
    """pending #37 결정(10/13): 1층 FAILED 칸 위 2층 박스는 빈 1층 칸에 — 실기 불변식 3(빈칸 위에 올리지 않음)."""
    ctx = started(cfg, "청담", {C: 4}).ctx
    acts: list = []
    for _ in range(3):  # 칸 0 박스 FAILED
        o = pf.step(ctx, f.MoveDone(False, "GRIP_FAIL", 0, 4 * MS))
        ctx = o.ctx
    ctx, acts = drive(ctx, list(o.actions))
    drops = [a.slot for a in acts if isinstance(a, f.CallMove) and a.mode == "DROP"]
    # 칸 2 박스 → 칸 0, 칸 2 는 빈칸 (MoveToZone 은 gateway 격자 번호, 10/13 통합)
    assert drops == [pp.grid_cell(s) for s in (1, 0, 3)]
    st = pf.pallet_state(ctx)
    cells = {pp.slot_cell(i) for i, s in enumerate(st["slot_state"]) if s == "DONE"}
    assert all((c, 1, ln) in cells for (c, la, ln) in cells if la == 2)  # 2층 아래는 늘 1층
