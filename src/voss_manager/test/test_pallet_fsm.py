"""pallet_fsm (S2-T05, BRD v1.5) — 가짜 gateway·가짜 ListPlacements 로 PALLETIZING 전이를 시험한다.

시작 조건·거부, S1(19개 → 16칸 + 초과 3) 완주(순서·칸·관측 복귀·칸 카운터·결과 19건·안내), S3 경로 제외,
계획 직후 발행 순서(PalletResult 미적재 → PalletState → 첫 PICK), GRIP_FAIL 재시도, stop·resume(파지 확인·놓침·
놓은 뒤 정지), 장비 실패, 대상 조회 실패·계획 거부, reset_zone PALLET, PalletState, SortResult.slot.
"""

import os
from dataclasses import replace

import pytest
import yaml

from voss_manager import pallet_fsm as pf
from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

# 로직 시험은 고정 설정(3×1)을 읽는다 — 레포 config 의 현장 값이 바뀌어도 기대값이 그대로다(S2-T21)
TEST_CONFIG = os.path.join(os.path.dirname(__file__), "fixtures", "voss_config_3x1.yaml")
SID = "20261012T090000-a1b2"
RUN = "20261012T150000-c3d4"
MS = 1_000_000
Y, D, C = "역삼동", "대치동", "청담동"
ZONE_OF = {Y: "A", D: "B", C: "C"}
ALL3 = "역삼동,대치동,청담동"
S1 = {Y: 7, D: 6, C: 6}
HOLDING, EMPTY = 41.0, 28.0  # RG2 보고 폭: 박스를 쥠 / 빈손 (범위 39.5~44.0)


@pytest.fixture
def cfg() -> f.Config:
    with open(TEST_CONFIG, encoding="utf-8") as fh:
        return replace(f.load_config(yaml.safe_load(fh)), pallet_ready=True)


def running(cfg: f.Config) -> f.Ctx:
    """start → OBSERVE 도착까지 마친 RUNNING (처리 중 박스 없음)."""
    ctx = f.new_ctx(cfg)
    ctx = pf.step(ctx, f.Command("start", "", 0, (), SID)).ctx
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 1000 * MS)).ctx
    assert ctx.state == f.RUNNING and ctx.phase == f.PH_NONE
    return ctx


def cmd(
    c: str, arg: str = "", t: int = 2000 * MS, nr: tuple = (), sid: str = "", grip: float = -1.0
):
    return f.Command(c, arg, t, nr, sid, grip_mm=grip)


def palletize(arg: str = ALL3, **kw) -> f.Command:
    return cmd("palletize", arg, sid=RUN, **kw)


def placements(counts: dict) -> tuple[pp.Placement, ...]:
    out, n = [], 0
    for d, k in counts.items():
        for s in range(k):
            n += 1
            out.append(pp.Placement(f"{SID}-{n:03d}", d, ZONE_OF[d], s, "PLACED", n * 1000 * MS))
    return tuple(out)


def of(acts, kind) -> list:
    return [a for a in acts if isinstance(a, kind)]


GRID_TO_SLOT = {pp.grid_cell(s): s for s in range(pp.CAPACITY)}


def moves(acts) -> list[tuple]:
    """(구역, 칸, mode). PALLET 칸은 gateway 격자 번호로 보내므로 적재 순서 slot(D2)으로 되돌려 비교한다."""
    return [
        (a.zone, GRID_TO_SLOT[a.slot] if a.zone == "PALLET" else a.slot, a.mode)
        for a in of(acts, f.CallMove)
    ]


def says(acts) -> list[str]:
    return [a.text for a in of(acts, f.Say)]


def started(cfg: f.Config, arg: str = ALL3, counts=None) -> tuple[f.Ctx, list]:
    """palletize 접수 → 대상 조회 응답까지 (첫 PICK 을 보냈다)."""
    out = pf.step(running(cfg), palletize(arg))
    assert (
        out.reply == (True, "palletize 접수") and of(out.actions, pf.CallList)[0].session_id == SID
    )
    out2 = pf.step(out.ctx, pf.ListDone(True, "", placements(counts or S1), 3000 * MS))
    return out2.ctx, list(out.actions) + list(out2.actions)


def gateway(ctx: f.Ctx, acts: list, answer, limit: int = 200) -> tuple[f.Ctx, list]:
    """가짜 gateway: 보낸 CallMove 마다 answer(CallMove, i, t) → MoveDone 로 차례로 답한다."""
    seen = list(acts)
    t = 4000 * MS
    for i in range(limit):
        pending = of(seen, f.CallMove)
        if len(pending) <= i:
            return ctx, seen
        ev = answer(pending[i], i, t)
        if ev is None:
            return ctx, seen
        out = pf.step(ctx, ev)
        ctx, t = out.ctx, t + 1000 * MS
        seen += list(out.actions)
    raise AssertionError("끝나지 않음")


def ok_all(a: f.CallMove, i: int, t: int) -> f.MoveDone:
    return f.MoveDone(True, "OK", t if a.mode == "DROP" else 0, t)


# ---------------------------------------------------------------- 시작 조건


def test_palletize_rejected_until_conditions_hold(cfg) -> None:
    ctx = running(cfg)
    for arg, msg in [("역삼,역삼", "두 번"), ("", "1~3개"), ("신사", "등록되지 않은")]:
        assert pf.step(ctx, palletize(arg)).reply[1].count(msg) == 1
    assert "준비 안 됨: LOG" in pf.step(ctx, palletize(nr=("LOG", "VISION"))).reply[1]
    assert (
        "교시" in pf.step(replace(ctx, cfg=replace(cfg, pallet_ready=False)), palletize()).reply[1]
    )
    assert "reset_zone PALLET" in pf.step(replace(ctx, pallet_count=2), palletize()).reply[1]
    busy = replace(ctx, state=f.PICKING)
    assert pf.step(busy, palletize()).reply == (False, pf.BUSY_MSG)
    idle = f.new_ctx(cfg)
    assert "세션이 없음" in pf.step(idle, palletize()).reply[1]
    out = pf.step(replace(idle, session_id=SID), palletize())  # 세션이 있는 IDLE 은 받는다
    assert out.reply[0] and out.ctx.state == pf.PALLETIZING and out.ctx.phase == pf.PH_LIST


# ---------------------------------------------------------------- 계획 직후 (TR-PAL-10 ①·TR-PAL-09)


def test_plan_outputs_come_before_first_pick(cfg) -> None:
    _, acts = started(cfg)
    kinds = [type(a).__name__ for a in acts if not isinstance(a, f.Log)]
    first_pick = kinds.index("CallMove")
    assert kinds.index("PublishPalletState") < first_pick  # 배치도·집계·경고가 첫 PICK 보다 먼저
    over = of(acts, pf.PalletOut)
    assert [(r.dong, r.outcome, r.pallet_slot, r.pallet_col) for r in over] == [
        (D, "OVERFLOW", -1, 0)
    ] * 3
    assert all(acts.index(r) < acts.index(of(acts, f.CallMove)[0]) for r in over)
    assert says(acts)[0] == (
        "역삼동, 대치동, 청담동 순서로 싣겠습니다. 첫 배송지 역삼동은 오른쪽입니다. "
        "팔레트가 16칸이라 3개는 싣지 못하고 원래 구역에 둡니다."
    )


# ---------------------------------------------------------------- 완주


def test_s1_run_completes(cfg) -> None:
    ctx, acts = started(cfg)
    ctx = replace(ctx, slots={**ctx.slots, "A": 7, "B": 6, "C": 6})
    ctx, acts = gateway(ctx, acts, ok_all)
    mv = moves(acts)
    # 칸 순서대로: 청담 6(1열 4칸 + 2열 1층) → 대치 3 → 역삼 7, 칸마다 PICK → DROP
    assert mv[:4] == [
        ("C", 0, "PICK"),
        ("PALLET", 0, "DROP"),
        ("C", 1, "PICK"),
        ("PALLET", 1, "DROP"),
    ]
    assert mv[12:14] == [("B", 0, "PICK"), ("PALLET", 6, "DROP")] and mv[18:20] == [
        ("A", 0, "PICK"),
        ("PALLET", 9, "DROP"),
    ]
    assert mv[-1] == ("OBSERVE", 0, "") and len(mv) == 16 * 2 + 1
    res = of(acts, pf.PalletOut)
    assert (
        len(res) == 19 and [r.outcome for r in res].count("DONE") == 16
    )  # pallet_log 19행 (S2-T07)
    last = [r for r in res if r.outcome == "DONE"][-1]
    assert (last.dong, last.pallet_slot, last.pallet_col, last.pallet_layer, last.pallet_lane) == (
        Y,
        15,
        4,
        2,
        2,
    )
    assert says(acts)[-1] == (
        "팔레트 적재를 마쳤습니다. 역삼동 7개, 대치동 3개, 청담동 6개를 실었습니다. 초과로 못 실은 박스는 대치동 3개입니다."
    )
    # 시작 전 RUNNING 으로, 다 비운 구역만 칸 0 (대치는 초과 3개가 남아 그대로), 팔레트 16개
    assert ctx.state == f.RUNNING and ctx.phase == f.PH_NONE and ctx.stage_start_ns > 0
    assert (ctx.slots["A"], ctx.slots["B"], ctx.slots["C"], ctx.pallet_count) == (0, 6, 0, 16)
    st = pf.pallet_state(ctx)
    assert st["state"] == "DONE" and st["done"] == 16 and st["slot_state"] == ["DONE"] * 16


def test_s3_route_excludes_a_dong(cfg) -> None:
    ctx, acts = started(cfg, "역삼,청담")
    ctx = replace(ctx, slots={**ctx.slots, "A": 7, "B": 6, "C": 6})
    excl = of(acts, pf.PalletOut)
    assert [(r.dong, r.outcome, r.route_index) for r in excl] == [(D, "EXCLUDED", -1)] * 6
    st = pf.pallet_state(ctx)
    assert (st["dongs"], st["load"], st["overflow"], st["excluded"]) == (
        [Y, C, D],
        [7, 6, 0],
        [0, 0, 0],
        [0, 0, 6],
    )
    assert st["overflow_warning"] is False  # 경로 제외는 초과 경고가 아니다
    ctx, acts = gateway(ctx, acts, ok_all)
    assert [m[1] for m in moves(acts) if m[0] == "PALLET"] == list(range(13))
    assert (ctx.slots["A"], ctx.slots["B"], ctx.slots["C"]) == (
        0,
        6,
        0,
    )  # 대치는 트레이에 그대로 (TR-PAL-11)
    assert says(acts)[-1].endswith("경로에 없는 대치동 6개는 그대로 두었습니다.")


# ---------------------------------------------------------------- 집기 실패


def test_grip_fail_retries_twice_then_next_box(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 3})

    def answer(a, i, t):
        if a.mode == "PICK" and a.slot == 0:
            return f.MoveDone(False, "GRIP_FAIL: 집기 확인 실패", 0, t)  # 칸 0 박스는 3번 다 실패
        if a.mode == "PICK" and a.slot == 1 and i == 3:
            return f.MoveDone(
                False, "GRIP_FAIL: 집기 확인 실패", 0, t
            )  # 칸 1 은 한 번 실패 뒤 성공
        return ok_all(a, i, t)

    ctx, acts = gateway(ctx, acts, answer)
    assert moves(acts)[:6] == [("C", 0, "PICK")] * 3 + [("C", 1, "PICK")] * 2 + [
        ("PALLET", 1, "DROP")
    ]
    res = of(acts, pf.PalletOut)
    assert [(r.outcome, r.reason, r.attempts, r.pallet_slot) for r in res] == [
        ("FAILED", "GRIP_FAIL", 3, 0),
        ("DONE", "", 2, 1),
        ("DONE", "", 1, 0),
    ]  # fmt: skip — 칸 2(2층) 박스는 비어 있는 아래 칸 0 에 당겨 놓는다 (pending #37 결정)
    assert pf.pallet_state(ctx)["slot_state"][:3] == ["DONE", "DONE", "EMPTY"]
    assert "옮기지 못한 박스는 001번" in says(acts)[-1]


# ---------------------------------------------------------------- stop·resume


def test_stop_while_picking_then_resume_checks_grip(cfg) -> None:
    ctx, _ = started(cfg, "청담동", {C: 3})
    ctx = pf.step(ctx, cmd("stop")).ctx
    assert ctx.state == f.PAUSED and ctx.phase == pf.PH_PICK  # 응답은 PAUSED 에서 받는다
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx  # 정지 전에 집기는 끝났다
    assert ctx.phase == f.PH_NONE and pf.current_box_id(ctx) == f"{SID}-001"
    assert pf.pallet_state(ctx)["state"] == "PAUSED"
    assert "보고 폭을 모름" in pf.step(ctx, cmd("resume")).reply[1]
    out = pf.step(ctx, cmd("resume", grip=HOLDING))  # 쥐고 있으면 그 칸에 놓는다
    assert (
        out.reply[0]
        and out.ctx.state == pf.PALLETIZING
        and moves(out.actions) == [("PALLET", 0, "DROP")]
    )
    out = pf.step(ctx, cmd("resume", grip=EMPTY))  # 놓쳤으면 FAILED·DROPPED, 알리고 다음 박스
    res = of(out.actions, pf.PalletOut)
    assert [(r.box_id[-3:], r.outcome, r.reason) for r in res] == [("001", "FAILED", "DROPPED")]
    assert "001번 박스를 놓쳤습니다" in says(out.actions)[0] and moves(out.actions) == [
        ("C", 1, "PICK")
    ]


def test_stop_after_open_counts_done_and_keeps_slots(cfg) -> None:
    ctx, _ = started(cfg, "청담동", {C: 3})
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx  # 칸 0 집음 → DROP 중
    assert ctx.phase == pf.PH_DROP
    ctx = pf.step(ctx, cmd("stop")).ctx
    out = pf.step(ctx, f.MoveDone(False, "STOPPED: 정지", 6000 * MS, 6000 * MS))  # 연 뒤 끊김
    res = of(out.actions, pf.PalletOut)
    assert [(r.outcome, r.reason) for r in res] == [
        ("DONE", "STOPPED")
    ] and out.ctx.pallet_count == 1
    assert out.ctx.state == f.PAUSED and not says(out.actions)  # 사람이 멈춘 것 — 문제 안내 없음
    out = pf.step(out.ctx, cmd("resume", grip=EMPTY))
    assert moves(out.actions) == [("C", 1, "PICK")]
    out = pf.step(out.ctx, f.MoveDone(True, "OK", 0, 8000 * MS))
    assert moves(out.actions) == [("PALLET", 1, "DROP")]  # 다음 칸 — 당겨지지 않는다 (TR-PAL-08)


def test_device_failure_mid_pick_pauses_then_repicks(cfg) -> None:
    ctx, _ = started(cfg, "청담동", {C: 3})
    out = pf.step(ctx, f.MoveDone(False, "LIMIT: 1206 NOT REACHABLE", 0, 5000 * MS))
    assert out.ctx.state == f.PAUSED and says(out.actions) == [
        "팔레트 적재 중 문제가 생겨 일시정지했습니다."
    ]
    assert not of(out.actions, pf.PalletOut)
    out = pf.step(out.ctx, cmd("resume", grip=EMPTY))  # 쥐고 있지 않다 → 박스는 칸에 있다
    assert moves(out.actions) == [("C", 0, "PICK")] and pf.run_of(out.ctx).attempts == 2


def test_drop_failure_before_open_keeps_box_in_gripper(cfg) -> None:
    ctx, _ = started(cfg, "청담동", {C: 3})
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx
    out = pf.step(ctx, f.MoveDone(False, "TIMEOUT", 0, 9000 * MS))
    assert out.ctx.state == f.PAUSED and not of(out.actions, pf.PalletOut)
    out = pf.step(out.ctx, cmd("resume", grip=HOLDING))
    assert moves(out.actions) == [("PALLET", 0, "DROP")]


def test_home_failure_then_resume_finishes(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 1})
    ctx, acts = gateway(
        ctx,
        acts,
        lambda a, i, t: (
            f.MoveDone(False, "TIMEOUT", 0, t) if a.zone == "OBSERVE" else ok_all(a, i, t)
        ),
    )
    assert ctx.state == f.PAUSED and pf.run_of(ctx).stage == "HOME"
    out = pf.step(ctx, cmd("resume"))
    assert moves(out.actions) == [("OBSERVE", 0, "")]
    out = pf.step(out.ctx, f.MoveDone(True, "OK", 0, 20000 * MS))
    assert out.ctx.state == f.RUNNING and pf.pallet_state(out.ctx)["state"] == "DONE"


# ---------------------------------------------------------------- 대상 조회


def test_list_failure_or_plan_error_returns_to_previous_state(cfg) -> None:
    out = pf.step(running(cfg), palletize())
    back = pf.step(out.ctx, pf.ListDone(False, "DB_ERROR", (), 3000 * MS))
    assert back.ctx.state == f.RUNNING and back.ctx.pallet is None and not moves(back.actions)
    assert says(back.actions) == ["작업 기록을 읽지 못해 팔레트 적재를 시작하지 않습니다."]
    no_slot = placements(S1) + (pp.Placement(f"{SID}-020", C, "C", -1, "PLACED", 50000 * MS),)
    back = pf.step(out.ctx, pf.ListDone(True, "", no_slot, 3000 * MS))
    assert back.ctx.state == f.RUNNING and "칸 기록이 없어" in says(back.actions)[0]


def test_stop_during_list_cancels_run(cfg) -> None:
    ctx = pf.step(running(cfg), palletize()).ctx
    ctx = pf.step(ctx, cmd("stop")).ctx
    out = pf.step(ctx, pf.ListDone(True, "", placements(S1), 3000 * MS))
    assert out.ctx.state == f.PAUSED and out.ctx.pallet is None and not moves(out.actions)


# ---------------------------------------------------------------- 다른 명령·비움


def test_other_commands_while_palletizing(cfg) -> None:
    ctx, _ = started(cfg)
    for c in ("start", "priority", "answer"):
        assert not pf.step(ctx, cmd(c, "대치동")).reply[0]
    out = pf.step(ctx, cmd("stop"))
    assert out.ctx.state == f.PAUSED and of(out.actions, f.CallStop)
    ctx = pf.step(out.ctx, f.MoveDone(False, "STOPPED", 0, 5000 * MS)).ctx
    assert "멈춘 팔레타이징" in pf.step(ctx, cmd("reset_zone", "PALLET")).reply[1]
    assert "멈춘 팔레타이징" in pf.step(ctx, cmd("reset_zone", "C")).reply[1]
    assert "resume" in pf.step(ctx, palletize()).reply[1]


def test_reset_pallet_before_next_run(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 1})
    ctx, _ = gateway(ctx, acts, ok_all)
    assert ctx.state == f.RUNNING and ctx.pallet_count == 1
    assert "박스 1개가 남아" in pf.step(ctx, palletize("청담동")).reply[1]
    # PL 안전 결정: 분류 RUNNING 중에는 작업자가 팔레트에 손대는 절차를 허용하지 않는다.
    denied = pf.step(ctx, cmd("reset_zone", "PALLET"))
    assert not denied.reply[0] and "IDLE·PAUSED" in denied.reply[1]
    assert denied.ctx.pallet_count == 1
    stopped = pf.step(ctx, cmd("stop"))
    assert stopped.ctx.state == f.PAUSED and of(stopped.actions, f.CallStop)
    # 현장에서는 로봇 안전 정지·실물 비움을 확인한 뒤 비움 버튼을 누른다.
    out = pf.step(stopped.ctx, cmd("reset_zone", "PALLET"))
    assert out.reply == (True, "PALLET 비움") and out.ctx.pallet_count == 0
    assert out.ctx.state == f.PAUSED and pf.pallet_state(out.ctx)["state"] == ""
    resumed = pf.step(out.ctx, cmd("resume"))
    assert resumed.reply[0] and resumed.ctx.state == f.RUNNING
    assert pf.step(resumed.ctx, palletize("청담동")).reply[0]


def test_pallet_state_during_run(cfg) -> None:
    st = pf.pallet_state(running(cfg))
    assert st["state"] == "" and len(st["slot_state"]) == 16 and st["slot_state"] == ["EMPTY"] * 16
    ctx, _ = started(cfg)
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 6000 * MS, 6000 * MS)).ctx  # 첫 박스 끝, 둘째 집는 중
    st = pf.pallet_state(ctx)
    assert (st["state"], st["total"], st["done"], st["failed"]) == ("RUNNING", 16, 1, 0)
    assert (st["dongs"], st["load"], st["overflow"], st["excluded"]) == (
        [Y, D, C],
        [7, 3, 6],
        [0, 3, 0],
        [0, 0, 0],
    )
    assert st["overflow_warning"] is True and st["box_id"] == f"{SID}-015"  # 청담 둘째 박스
    assert (
        st["slot_state"][:3] == ["DONE", "MOVING", "PLANNED"]
        and st["slot_dong"][6] == D
        and st["slot_dong"][15] == Y
    )


# ---------------------------------------------------------------- 분류 쪽 (S2-T07 sort_manager 몫)


def test_sort_result_carries_slot(cfg) -> None:
    ctx = running(cfg)
    slots = []
    for k, track in enumerate((1, 2)):
        t = (2000 + k * 20000) * MS
        ev = f.LabelSeen(track, "S07-02", "대치동", 0.9, 1, t, "", "", t + 50 * MS, t - 300 * MS)
        for e in (
            ev,
            f.GoalDone(True, True, "OK", 1, t + 5000 * MS),
            f.MoveDone(True, "OK", t + 9000 * MS, t + 12000 * MS),
        ):
            out = pf.step(ctx, e)
            ctx = out.ctx
            slots += [(r.zone, r.slot) for r in of(out.actions, f.Result)]
    assert slots == [("B", 0), ("B", 1)]


def test_intent_and_config_hooks(cfg) -> None:
    assert f.intent_to_command("palletize", "", "", "", ("역삼동", "대치동")) == (
        "palletize",
        "역삼동,대치동",
    )
    with open(TEST_CONFIG, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    assert f.load_config(raw).pallet_ready is False  # 교시 전 — 고정 설정에 zones.pallet 없음
    raw["zones"]["pallet"] = {"pose": [100.0, 200.0, 260.0, 0.0, 180.0, 0.0]}
    assert f.load_config(raw).pallet_ready is True
    raw["zones"]["pallet"] = {"pose": None}
    assert f.load_config(raw).pallet_ready is False


# ---------------------------------------------------------------- pending #37 결정: FAILED 1층 위 2층 박스는 아래로


def test_layer2_box_is_pulled_down_onto_failed_slot(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 4})  # 1열: 칸 0·1 = 1층, 칸 2·3 = 2층

    def answer(a, i, t):
        if a.mode == "PICK" and a.slot == 0:
            return f.MoveDone(False, "GRIP_FAIL", 0, t)  # 칸 0 박스는 3번 다 실패 → FAILED
        return ok_all(a, i, t)

    ctx, acts = gateway(ctx, acts, answer)
    drops = [m for m in moves(acts) if m[2] == "DROP"]
    assert drops == [
        ("PALLET", 1, "DROP"),
        ("PALLET", 0, "DROP"),
        ("PALLET", 3, "DROP"),
    ]  # 칸 2 박스 → 칸 0
    res = {
        r.box_id[-3:]: (r.outcome, r.pallet_slot, r.pallet_layer) for r in of(acts, pf.PalletOut)
    }
    assert res == {
        "001": ("FAILED", 0, 1),
        "002": ("DONE", 1, 1),
        "003": ("DONE", 0, 1),
        "004": ("DONE", 3, 2),
    }
    st = pf.pallet_state(ctx)
    assert (
        st["slot_state"][:4] == ["DONE", "DONE", "EMPTY", "DONE"]
        and st["slot_box_id"][0] == f"{SID}-003"
    )
    assert "아래 칸이 비어 위층 박스 1개를 아래 칸에 놓았습니다" in says(acts)[-1]


def test_pulled_down_target_survives_resume(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 4})
    for _ in range(3):  # 칸 0 FAILED
        ctx = pf.step(ctx, f.MoveDone(False, "GRIP_FAIL", 0, 4000 * MS)).ctx
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx  # 칸 1 집음
    ctx = pf.step(
        ctx, f.MoveDone(True, "OK", 6000 * MS, 6000 * MS)
    ).ctx  # 칸 1 놓음 → 칸 2 박스 집기
    out = pf.step(ctx, f.MoveDone(True, "OK", 0, 7000 * MS))  # 집음 → 칸 0 에 놓기로 정함
    assert moves(out.actions) == [("PALLET", 0, "DROP")]
    ctx = pf.step(out.ctx, cmd("stop")).ctx
    ctx = pf.step(ctx, f.MoveDone(False, "STOPPED", 0, 8000 * MS)).ctx  # 열기 전에 끊김 → 든 채
    out = pf.step(ctx, cmd("resume", grip=HOLDING))
    assert moves(out.actions) == [("PALLET", 0, "DROP")]  # 재개해도 같은 아래 칸


def test_no_pull_down_when_lower_slot_is_done(cfg) -> None:
    ctx, acts = started(cfg, "청담동", {C: 4})
    ctx, acts = gateway(ctx, acts, ok_all)
    assert [m[1] for m in moves(acts) if m[2] == "DROP"] == [0, 1, 2, 3] and not pf.run_of(
        ctx
    ).moved


# ---------------------------------------------------------------- 1층만 (ADR-0014 B, sort_manager pallet_layers)


def test_layer1_only_drops_on_first_layer_and_says_8_slots(cfg) -> None:
    ctx = replace(running(cfg), pallet_layers=1)
    out = pf.step(ctx, palletize(ALL3))
    out2 = pf.step(out.ctx, pf.ListDone(True, "", placements(S1), 3000 * MS))
    acts = list(out.actions) + list(out2.actions)
    assert "팔레트가 8칸이라 11개는" in says(acts)[0]
    ctx, acts = gateway(out2.ctx, acts, ok_all)
    drops = [s for z, s, mode in moves(acts) if mode == "DROP"]
    assert drops == [0, 1, 4, 5, 8, 9, 12, 13]
    st = pf.pallet_state(ctx)
    assert all(st["slot_state"][s] == "EMPTY" for s in range(16) if pp.slot_cell(s)[1] == 2)
    assert st["state"] == "DONE" and st["done"] == 8 and st["total"] == 8
    res = of(acts, pf.PalletOut)
    assert {r.pallet_layer for r in res if r.outcome == "DONE"} == {1}
    assert sum(r.outcome == "OVERFLOW" for r in res) == 11


def test_new_ctx_rejects_unknown_layers(cfg) -> None:
    with pytest.raises(ValueError):
        f.new_ctx(cfg, pallet_layers=3)


# ---------------------------------------------------------------- gateway 격자 번호 (10/13 김학민 로봇 쪽 통합)


def test_grid_cell_matches_field_order_and_is_one_to_one() -> None:
    """적재 순서 slot(D2) → 격자 칸 = 10/12 실기 zones.pallet.grid.order 와 같다."""
    assert [pp.grid_cell(s) for s in range(16)] == [
        0,
        4,
        8,
        12,
        1,
        5,
        9,
        13,
        2,
        6,
        10,
        14,
        3,
        7,
        11,
        15,
    ]
    assert [pp.grid_cell(s) for s in pp.slot_order(1)] == [
        0,
        4,
        1,
        5,
        2,
        6,
        3,
        7,
    ]  # 1층만 = 격자 1층


def test_drop_calls_use_grid_cells(cfg) -> None:
    ctx, acts = started(cfg, ALL3)
    ctx, acts = gateway(ctx, acts, ok_all)
    raw = [a.slot for a in of(acts, f.CallMove) if a.zone == "PALLET"]
    assert raw == [pp.grid_cell(s) for s in range(16)]


def test_two_layer_tray_from_config_picks_upper_layer_first(cfg) -> None:
    """voss_config 트레이 grid layers 2(한 층 6칸) → A 칸 6(칸 0 위)을 칸 0 보다 먼저 집는다(10/13 게이트).
    레포 설정(1층)은 그대로 칸 순서."""
    with open(TEST_CONFIG, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    for z in ("A", "B", "C"):
        raw["zones"][z]["grid"].update(rows=2, layers=2)
    two = replace(f.load_config(raw), pallet_ready=True)
    assert two.layer_cells == {"A": 6, "B": 6, "C": 6} and cfg.layer_cells == {}
    ctx, acts = started(two, "대치동,역삼동,청담동", S1)
    ctx, acts = gateway(ctx, acts, ok_all)
    picks = [(z, s) for z, s, m in moves(acts) if m == "PICK"]
    assert [s for z, s in picks if z == "A"] == [6, 0, 1, 2, 3, 4, 5]
    assert [z for z, _ in picks] == ["C"] * 6 + ["A"] * 7 + ["B"] * 3


def two_layer() -> f.Config:
    """A·B·C 트레이를 2층(한 층 6칸)으로 바꾼 설정 — 10/13 게이트 실기와 같다."""
    with open(TEST_CONFIG, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    for z in ("A", "B", "C"):
        raw["zones"][z]["grid"].update(rows=2, layers=2)
    return replace(f.load_config(raw), pallet_ready=True)


def test_upper_tray_box_failed_pauses_until_cleared() -> None:
    """Q5/K5 (10/13 PL): 위층 칸 6 박스가 GRIP_FAIL 3회 → FAILED 기록 + PAUSED + 안내, 그 아래 칸 0 은 집지 않는다.
    작업자가 치운 뒤 resume 하면 칸 0 부터 이어 간다."""
    ctx, acts = started(two_layer(), Y, {Y: 7})

    def answer(a, i, t):
        if a.mode == "PICK" and a.zone == "A" and a.slot == 6:
            return f.MoveDone(False, "GRIP_FAIL: 집기 확인 실패", 0, t)
        return ok_all(a, i, t)

    ctx, acts = gateway(ctx, acts, answer)
    assert ctx.state == f.PAUSED and ctx.phase == f.PH_NONE
    assert [s for z, s, m in moves(acts) if m == "PICK"] == [6, 6, 6]  # 칸 0 을 집지 않고 멈춤
    res = [(r.box_id[-3:], r.outcome, r.reason, r.attempts) for r in of(acts, pf.PalletOut)]
    assert res == [("007", "FAILED", "GRIP_FAIL", 3)]
    assert says(acts)[-1] == "A 구역 2층 박스를 집지 못했습니다. 박스를 치운 뒤 재개해 주세요."
    assert pf.current_box_id(ctx) == ""  # 다음 박스로 넘어갈 차례(NEXT)

    out = pf.step(ctx, cmd("resume", t=60_000 * MS))
    assert out.reply == (True, "resume 접수 (팔레타이징)")
    ctx, acts = gateway(out.ctx, list(out.actions), ok_all)
    assert [s for z, s, m in moves(acts) if m == "PICK"] == [0, 1, 2, 3, 4, 5]
    assert [r.outcome for r in of(acts, pf.PalletOut)] == ["DONE"] * 6
    assert ctx.state == f.RUNNING and "옮기지 못한 박스는 007번" in says(acts)[-1]


def test_lower_tray_failure_goes_on_without_pause() -> None:
    """아래층(칸 0) 박스 실패는 위에 남는 박스가 없으니 멈추지 않고 다음 박스로 (기존 TR-PAL-05)."""
    ctx, acts = started(two_layer(), Y, {Y: 7})

    def answer(a, i, t):
        if a.mode == "PICK" and a.zone == "A" and a.slot == 0:
            return f.MoveDone(False, "GRIP_FAIL", 0, t)
        return ok_all(a, i, t)

    ctx, acts = gateway(ctx, acts, answer)
    assert [s for z, s, m in moves(acts) if m == "PICK"] == [6, 0, 0, 0, 1, 2, 3, 4, 5]
    assert ctx.state == f.RUNNING and not any("치운 뒤" in t for t in says(acts))
