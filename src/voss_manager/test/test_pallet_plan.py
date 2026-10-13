"""pallet_plan (S2-T04, BRD v1.5) — 정답 생성기(검증 프롬프트 v2 2.3)와 S1~S8·불변식 500회, 대상 선정, 같은 칸 재사용,
입력 순서와 무관한 결과, 재개 시 남은 목록, 경로 문자열 검사(별칭), 다 빈 구역."""

import itertools
import os
import random

import pytest
import yaml

from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

REPO_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "voss_config.yaml"
)
SID = "20261012T090000-a1b2"
Y, D, C = "역삼동", "대치동", "청담동"
ZONE_OF = {Y: "A", D: "B", C: "C"}
ALL3 = (Y, D, C)


def box(
    n: int, dong: str, slot: int, zone: str = "", outcome: str = "PLACED", **kw
) -> pp.Placement:
    kw.setdefault("stamp_ns", n * 1_000_000_000)
    return pp.Placement(f"{SID}-{n:03d}", dong, zone or ZONE_OF[dong], slot, outcome, **kw)


def placements(counts: dict) -> list[pp.Placement]:
    """동별 n 개를 그 동 구역 칸 0..n−1 에 PLACED (트레이 칸 수는 결정 D1 — 여기서는 제한하지 않는다)."""
    out, k = [], 0
    for dong, n in counts.items():
        for s in range(n):
            k += 1
            out.append(box(k, dong, s))
    return out


# ---------------------------------------------------------------- 정답 생성기 (검증 프롬프트 v2 2.3 그대로)


def ref_plan(route, counts):
    cap = 16
    excluded = {z: n for z, n in counts.items() if z not in route and n > 0}
    total = sum(counts.get(z, 0) for z in route)
    if total <= cap:
        load = {z: counts.get(z, 0) for z in route}
    else:
        visit = {z: i for i, z in enumerate(route)}
        prio = sorted(route, key=lambda z: (-counts.get(z, 0), -visit[z]))
        left, load = cap, {}
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
    return {"total": total, "overflow": max(0, total - cap), "load": load,
            "remain_overflow": remain, "excluded": excluded, "slots": slots}  # fmt: skip


# BRD v1.5 10.4 · 검증 프롬프트 2.4 표 (행 = 2층1줄, 2층2줄, 1층1줄, 1층2줄 / 열 = 1~4열)
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


def table_of(plan: pp.Plan) -> list[str]:
    cells = {m.cell: m.dong for m in plan.moves}  # (열, 층, 줄)
    return [
        "".join(ABBR.get(cells.get((c, la, ln), ""), "-") for c in range(1, 5)) for la, ln in ROWS
    ]


def compare(route, counts) -> list[str]:
    """구현 ↔ 정답 생성기. 다른 점 목록 (같으면 [])."""
    ref = ref_plan(route, counts)
    plan = pp.plan_pallet(route, placements(counts))
    rows = {d: (n, o, e) for d, n, o, e in plan.counts()}
    bad = []
    if {d: rows[d][0] for d in route} != ref["load"]:
        bad.append(f"실은 수 {plan.counts()} ≠ {ref['load']}")
    if plan.overflow != ref["overflow"] or {d: rows[d][1] for d in route} != ref["remain_overflow"]:
        bad.append(f"초과 {plan.overflow} ≠ {ref['overflow']}")
    if {d: e for d, (_, _, e) in rows.items() if e} != ref["excluded"]:
        bad.append(f"경로 제외 ≠ {ref['excluded']}")
    want = [(x["slot"], x["zone"], (x["col"], x["layer"], x["lane"])) for x in ref["slots"]]
    got = [(m.pallet_slot, m.dong, m.cell) for m in plan.moves]
    if got != want:
        bad.append(f"칸·순서 {got} ≠ {want}")
    return bad


# ---------------------------------------------------------------- S1~S8 · 불변식


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenarios_match_reference_and_brd_tables(name) -> None:
    route, counts, table = SCENARIOS[name]
    assert compare(route, counts) == []
    assert (
        table_of(pp.plan_pallet(route, placements(counts))) == table
    )  # 같은 층 1줄 → 2줄 (결정 D6 제안)


def test_s1_counts_and_unloaded_boxes() -> None:
    plan = pp.plan_pallet((Y, D, C), placements({Y: 7, D: 6, C: 6}))
    assert plan.counts() == ((Y, 7, 0, 0), (D, 3, 3, 0), (C, 6, 0, 0))
    assert plan.overflow == 3 and plan.excluded == 0
    assert [(u.dong, u.reason, u.route_index) for u in plan.unloaded] == [(D, "OVERFLOW", 1)] * 3
    assert [u.slot for u in plan.unloaded] == [
        3,
        4,
        5,
    ]  # 대치 칸 0·1·2 를 싣고 3·4·5 는 트레이에 남는다
    assert [m.dong for m in plan.moves] == [C] * 6 + [D] * 3 + [Y] * 7  # 칸 순서 = 옮기는 순서


def test_s3_excluded_is_counted_apart_from_overflow() -> None:
    plan = pp.plan_pallet((Y, C), placements({Y: 7, D: 6, C: 6}))
    assert plan.overflow == 0 and plan.excluded == 6
    assert plan.counts() == ((Y, 7, 0, 0), (C, 6, 0, 0), (D, 0, 0, 6))
    assert {(u.dong, u.reason, u.route_index) for u in plan.unloaded} == {(D, "EXCLUDED", -1)}


def test_exactly_16_has_no_overflow() -> None:
    plan = pp.plan_pallet((Y, D, C), placements({Y: 6, D: 5, C: 5}))
    assert len(plan.moves) == 16 and plan.overflow == 0 and not plan.unloaded


def random_inputs(n: int = 500, seed: int = 20261012):
    rng = random.Random(seed)
    routes = [p for k in (1, 2, 3) for p in itertools.permutations(ALL3, k)]
    for _ in range(n):
        yield (
            rng.choice(routes),
            {Y: rng.randint(0, 10), D: rng.randint(0, 10), C: rng.randint(0, 10)},
        )


def test_invariants_random_500() -> None:
    """검증 프롬프트 2.5 불변식 1~6 + 정답 생성기와 같음 (대상 0개는 시작 거부라 따로)."""
    checked = 0
    for route, counts in random_inputs():
        if sum(counts[d] for d in route) == 0:
            with pytest.raises(pp.PlanError, match="옮길 박스가 없음"):
                pp.plan_pallet(route, placements(counts))
            continue
        plan = pp.plan_pallet(route, placements(counts))
        assert compare(route, counts) == [], (route, counts)
        rows = {d: (n, o, e) for d, n, o, e in plan.counts()}
        total = sum(counts[d] for d in route)
        assert len(plan.moves) == min(total, 16)  # 1
        assert all(rows[d][0] + rows[d][1] == counts[d] for d in route)  # 1
        assert [m.pallet_slot for m in plan.moves] == list(
            range(len(plan.moves))
        )  # 2 중복·빈틈 없음
        filled = {m.cell for m in plan.moves}
        assert all((c, 1, ln) in filled for (c, la, ln) in filled if la == 2)  # 3 2층 아래 1층
        visit = {d: i for i, d in enumerate(route)}
        for a in plan.moves:  # 4 나중에 방문하는 동이 안쪽(왼쪽)·아래
            for b in plan.moves:
                if visit[a.dong] > visit[b.dong]:
                    assert a.cell[0] <= b.cell[0]
                    if a.cell[0] == b.cell[0]:
                        assert a.cell[1] <= b.cell[1]
        assert all(m.dong in route for m in plan.moves)  # 5
        for x in route:  # 6 X 가 남았으면 X 보다 후순위인 동은 하나도 안 실린다
            if rows[x][1]:
                for y in route:
                    lower = counts[y] < counts[x] or (
                        counts[y] == counts[x] and visit[y] < visit[x]
                    )
                    if lower:
                        assert rows[y][0] == 0, (route, counts, x, y)
        checked += 1
    assert checked > 450


# ---------------------------------------------------------------- 대상 선정 (TR-PAL-03)


def test_only_placed_in_sort_zones_operator_box_included() -> None:
    recs = [
        box(1, Y, 0),
        box(2, Y, 0, zone="HOLD", outcome="HELD"),  # 판별 불가 → 보류, 대상 아님
        box(3, Y, 1, zone="RECHECK", outcome="HELD"),
        box(4, Y, -1, zone="", outcome="FAILED"),
        box(5, Y, -1, zone="", outcome="PASSED"),
        box(6, Y, 1),  # 흐린 송장 — 작업자가 "역삼" 이라고 답해 A 칸 1 에 PLACED
    ]
    plan = pp.plan_pallet((Y,), recs)
    assert [m.box_id[-3:] for m in plan.moves] == ["001", "006"]
    assert len(plan.skipped) == 4 and any("FAILED" in s for s in plan.skipped)


def test_already_palletized_excluded_and_no_per_dong_cap() -> None:
    recs = placements({Y: 7})
    recs[0] = box(1, Y, 0, palletized=True)
    plan = pp.plan_pallet((Y,), recs)
    assert (
        len(plan.moves) == 6 and f"{SID}-001 {Y} 이미 팔레트" in plan.skipped
    )  # 동별 상한 없음 (v1.5)


def test_reset_zone_reused_slot_latest_wins() -> None:
    recs = [box(1, Y, 0), box(2, Y, 1), box(7, Y, 0)]
    plan = pp.plan_pallet((Y,), recs)
    assert [m.box_id[-3:] for m in plan.moves] == ["007", "002"]
    assert any(s.startswith(f"{SID}-001") and "나중 박스" in s for s in plan.skipped)


def test_same_result_regardless_of_input_order() -> None:
    recs = placements({Y: 7, D: 6, C: 6}) + [box(30, Y, 0, zone="HOLD", outcome="HELD")]
    want = pp.plan_pallet(ALL3, recs)
    rng = random.Random(7)
    for _ in range(20):
        shuffled = recs[:]
        rng.shuffle(shuffled)
        assert pp.plan_pallet(ALL3, shuffled) == want


def test_resume_keeps_planned_slots() -> None:
    plan = pp.plan_pallet(ALL3, placements({Y: 7, D: 6, C: 6}))
    finished = [m.box_id for m in plan.moves[:8]]
    rest = pp.remaining(plan, finished)
    assert rest == plan.moves[8:] and rest[0].pallet_slot == 8  # 9번 칸부터 (TR-PAL-08)
    assert (
        pp.remaining(plan, []) == plan.moves
        and pp.remaining(plan, [m.box_id for m in plan.moves]) == ()
    )


def test_missing_slot_or_nothing_to_move_rejected() -> None:
    with pytest.raises(pp.PlanError, match="칸 기록"):
        pp.plan_pallet((Y,), [box(1, Y, -1)])
    with pytest.raises(pp.PlanError, match="옮길 박스가 없음"):
        pp.plan_pallet((C,), placements({Y: 3}))


def test_route_dong_without_boxes_is_reported() -> None:
    plan = pp.plan_pallet((Y, C), placements({Y: 3}))
    assert plan.empty == (C,) and plan.counts() == ((Y, 3, 0, 0), (C, 0, 0, 0))


def test_emptied_zones_only_when_tray_fully_moved() -> None:
    plan = pp.plan_pallet((Y, D, C), placements({Y: 7, D: 6, C: 6}))
    done = [m.box_id for m in plan.moves]
    assert pp.emptied_zones(plan, done) == (
        "A",
        "C",
    )  # 대치(B)는 초과 3개가 남아 칸 카운터를 그대로 둔다
    assert pp.emptied_zones(plan, done[1:]) == ("A",)  # 청담 하나를 못 옮기면 C 는 그대로


def test_slot_cell_formula() -> None:
    # (열, 층, 줄), slot = (열−1)×4 + (층−1)×2 + (줄−1)
    assert [pp.slot_cell(s) for s in (0, 1, 2, 3, 4, 15)] == [
        (1, 1, 1), (1, 1, 2), (1, 2, 1), (1, 2, 2), (2, 1, 1), (4, 2, 2)
    ]  # fmt: skip
    with pytest.raises(ValueError):
        pp.slot_cell(16)


def test_parse_route_with_aliases_and_errors() -> None:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        cfg = f.load_config(yaml.safe_load(fh))
    assert pp.parse_route("역삼, 대치동,청담", cfg.dong_of) == ALL3
    for arg, msg in [
        ("", "1~3개"),
        ("역삼,대치,청담,역삼", "1~3개"),
        ("역삼,역삼동", "두 번"),
        ("역삼,신사", "등록되지 않은 동: 신사"),
    ]:
        with pytest.raises(pp.PlanError, match=msg):
            pp.parse_route(arg, cfg.dong_of)
    with pytest.raises(pp.PlanError, match="두 번"):
        pp.plan_pallet((Y, Y), placements({Y: 1}))


def test_sort_zones_match_fsm() -> None:
    assert pp.SORT_ZONES == f.SORT_ZONES
