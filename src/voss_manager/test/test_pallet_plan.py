"""pallet_plan (S2-T04) — 경로 3/2/1개, BRD 10.4 열 배치 예시, 경로 밖·보류·실패·이미 옮김 제외, 동별 3개 초과 거부,
reset_zone 으로 다시 쓴 칸, 입력 순서와 무관한 결과, 재개 시 남은 목록, 경로 문자열 검사(별칭)."""

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
ZONE_OF = {"역삼동": "A", "대치동": "B", "청담동": "C"}
ALL3 = ("역삼동", "대치동", "청담동")


def box(
    n: int, dong: str, slot: int, zone: str = "", outcome: str = "PLACED", **kw
) -> pp.Placement:
    """n = box_id 순번. 기본 시각은 순번 순서(놓은 차례)."""
    kw.setdefault("stamp_ns", n * 1_000_000_000)
    return pp.Placement(f"{SID}-{n:03d}", dong, zone or ZONE_OF[dong], slot, outcome, **kw)


def nine() -> list[pp.Placement]:
    """동별 3개씩 9개 — 시연 박스 구성 제안(pending #19)."""
    return [box(i * 3 + s + 1, d, s) for i, d in enumerate(ALL3) for s in range(3)]


def layout(plan: pp.Plan) -> list[tuple[str, int, int]]:
    return [(m.dong, m.col, m.row) for m in plan.moves]


def test_three_dong_route_last_delivery_first() -> None:
    plan = pp.plan_pallet(ALL3, nine())
    assert plan.cols == 3 and plan.empty == () and plan.skipped == ()
    # 마지막 배송지(청담) → 가장 왼쪽 열 0 부터, 첫 배송지(역삼) = 오른쪽 열 2 (트럭 문 쪽)
    assert layout(plan) == [
        ("청담동", 0, 0), ("청담동", 0, 1), ("청담동", 0, 2),
        ("대치동", 1, 0), ("대치동", 1, 1), ("대치동", 1, 2),
        ("역삼동", 2, 0), ("역삼동", 2, 1), ("역삼동", 2, 2),
    ]  # fmt: skip
    assert [m.pallet_slot for m in plan.moves] == list(range(9))  # 열 × 3 + 칸
    first = plan.moves[0]
    assert (first.zone, first.slot, first.route_index) == ("C", 0, 2)  # 집을 곳 = 기록된 구역·칸


@pytest.mark.parametrize(
    "route,cols",
    [
        (("역삼동", "대치동", "청담동"), ["청담동", "대치동", "역삼동"]),
        (("대치동", "역삼동", "청담동"), ["청담동", "역삼동", "대치동"]),
        (("청담동", "역삼동"), ["역삼동", "청담동"]),
    ],
)
def test_brd_column_examples(route, cols) -> None:
    """BRD v1.4 10.4 열 배치 예시 표 (왼쪽 열 → 오른쪽 열)."""
    plan = pp.plan_pallet(route, nine())
    assert plan.cols == len(route)
    assert [next(m.dong for m in plan.moves if m.col == c) for c in range(plan.cols)] == cols


def test_one_dong_route_and_out_of_route_stays() -> None:
    plan = pp.plan_pallet(("대치동",), nine())
    assert plan.cols == 1 and layout(plan) == [("대치동", 0, r) for r in range(3)]
    out = [s for s in plan.skipped if s.endswith("경로 밖")]
    assert len(out) == 6 and all("역삼동" in s or "청담동" in s for s in out)  # 트레이에 그대로


def test_two_dong_route_columns() -> None:
    plan = pp.plan_pallet(("청담동", "역삼동"), nine())
    assert {(m.dong, m.col) for m in plan.moves} == {("역삼동", 0), ("청담동", 1)}
    assert [m.dong for m in plan.moves[:3]] == ["역삼동"] * 3  # 마지막 배송지 역삼부터
    assert {m.pallet_slot for m in plan.moves} == {0, 1, 2, 3, 4, 5}


def test_only_placed_in_sort_zones() -> None:
    recs = [
        box(1, "역삼동", 0),
        box(2, "역삼동", 0, zone="HOLD", outcome="HELD"),
        box(3, "역삼동", 1, zone="RECHECK", outcome="HELD"),
        box(4, "역삼동", -1, zone="", outcome="FAILED"),
        box(5, "역삼동", -1, zone="", outcome="PASSED"),
        box(6, "역삼동", 1),
    ]
    plan = pp.plan_pallet(("역삼동",), recs)
    assert [m.box_id[-3:] for m in plan.moves] == ["001", "006"]
    assert len(plan.skipped) == 4 and any("FAILED" in s for s in plan.skipped)


def test_already_palletized_excluded() -> None:
    recs = nine()
    recs[0] = box(1, "역삼동", 0, palletized=True)
    plan = pp.plan_pallet(ALL3, recs)
    assert len(plan.moves) == 8 and f"{SID}-001 역삼동 이미 팔레트" in plan.skipped
    # 남은 역삼 박스 2개가 열 2 의 칸 0·1 (팔레트는 시작 때 비어 있다 — TR-PAL-02)
    assert [(m.slot, m.row) for m in plan.moves if m.dong == "역삼동"] == [(1, 0), (2, 1)]


def test_more_than_three_per_dong_rejected() -> None:
    # 세션 중 zone_map 이 바뀌어 청담동 박스가 C 3개 + B 1개
    recs = nine()[6:] + [box(20, "청담동", 0, zone="B")]
    with pytest.raises(pp.PlanError, match="청담동 4개"):
        pp.plan_pallet(ALL3, recs)


def test_reset_zone_reused_slot_latest_wins() -> None:
    # A 칸 0 에 놓은 뒤 사람이 비우고(reset_zone A) 다시 칸 0 에 놓았다 → 트레이에는 나중 박스만
    recs = [box(1, "역삼동", 0), box(2, "역삼동", 1), box(7, "역삼동", 0)]
    plan = pp.plan_pallet(("역삼동",), recs)
    assert [m.box_id[-3:] for m in plan.moves] == ["007", "002"]  # 칸 0 → 1 순서
    assert any(s.startswith(f"{SID}-001") and "나중 박스" in s for s in plan.skipped)


def test_same_result_regardless_of_input_order() -> None:
    recs = nine() + [box(30, "역삼동", 0, zone="HOLD", outcome="HELD")]
    want = pp.plan_pallet(ALL3, recs)
    rng = random.Random(7)
    for _ in range(20):
        shuffled = recs[:]
        rng.shuffle(shuffled)
        assert pp.plan_pallet(ALL3, shuffled) == want


def test_resume_keeps_planned_slots() -> None:
    plan = pp.plan_pallet(ALL3, nine())
    finished = [m.box_id for m in plan.moves[:4]]  # 청담 3개 + 대치 1개 끝(DONE 또는 FAILED)
    rest = pp.remaining(plan, finished)
    assert rest == plan.moves[4:]
    assert [(m.col, m.row) for m in rest][:2] == [(1, 1), (1, 2)]  # 대치 칸 0 을 다시 쓰지 않는다
    assert (
        pp.remaining(plan, []) == plan.moves
        and pp.remaining(plan, [m.box_id for m in plan.moves]) == ()
    )


def test_missing_slot_or_nothing_to_move_rejected() -> None:
    with pytest.raises(pp.PlanError, match="칸 기록"):
        pp.plan_pallet(("역삼동",), [box(1, "역삼동", -1)])
    with pytest.raises(pp.PlanError, match="옮길 박스가 없음"):
        pp.plan_pallet(("청담동",), nine()[:3])


def test_route_dong_without_boxes_is_reported() -> None:
    plan = pp.plan_pallet(("역삼동", "청담동"), nine()[:3])
    assert plan.empty == ("청담동",) and plan.cols == 2
    assert {m.col for m in plan.moves} == {1}  # 역삼 = 첫 배송지 = 오른쪽 열, 청담 열은 비워 둔다


def test_parse_route_with_aliases_and_errors() -> None:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        cfg = f.load_config(yaml.safe_load(fh))
    assert pp.parse_route("역삼, 대치동,청담", cfg.dong_of) == ALL3
    assert pp.parse_route("청담동", cfg.dong_of) == ("청담동",)
    for arg, msg in [
        ("", "1~3개"),
        ("역삼,대치,청담,역삼", "1~3개"),
        ("역삼,역삼동", "두 번"),
        ("역삼,신사", "등록되지 않은 동: 신사"),
    ]:
        with pytest.raises(pp.PlanError, match=msg):
            pp.parse_route(arg, cfg.dong_of)
    with pytest.raises(pp.PlanError, match="두 번"):
        pp.plan_pallet(("역삼동", "역삼동"), nine())


def test_sort_zones_match_fsm() -> None:
    assert pp.SORT_ZONES == f.SORT_ZONES


def test_occupied_and_emptied_zones() -> None:
    recs = nine() + [
        box(20, "역삼동", 0, palletized=True, stamp_ns=0)
    ]  # 칸 0 옛 기록(이미 옮김)은 나중 박스에 덮인다
    plan = pp.plan_pallet(("청담동", "역삼동"), recs)
    assert (
        len(plan.occupied) == 9 and ("B", 0, f"{SID}-004") in plan.occupied
    )  # 경로 밖 대치도 트레이에 있다
    moved = [m.box_id for m in plan.moves]
    assert pp.emptied_zones(plan, moved) == ("A", "C")  # 대치(B)는 남아 칸 카운터를 그대로 둔다
    assert moved[0].endswith("-001")  # 마지막 배송지 역삼부터 옮긴다
    assert pp.emptied_zones(plan, moved[1:]) == ("C",)  # 역삼 하나를 못 옮기면 A 는 그대로
