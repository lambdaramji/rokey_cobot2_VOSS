"""pallet_fsm (S2-T05) — 가짜 gateway·가짜 ListPlacements 로 PALLETIZING 전이를 시험한다.

시작 조건·거부, 3개 동 9개 완주(순서·칸·관측 복귀·칸 카운터), GRIP_FAIL 재시도, stop·resume(파지 확인·놓침·
놓은 뒤 정지), 장비 실패, 대상 조회 실패·계획 거부, reset_zone PALLET, PalletState, SortResult.slot.
"""

import os
from dataclasses import replace

import pytest
import yaml

from voss_manager import pallet_fsm as pf
from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

REPO_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "voss_config.yaml"
)
SID = "20261012T090000-a1b2"
RUN = "20261012T150000-c3d4"
MS = 1_000_000
ZONE_OF = {"역삼동": "A", "대치동": "B", "청담동": "C"}
ALL3 = "역삼동,대치동,청담동"
HOLDING, EMPTY = 41.0, 28.0  # RG2 보고 폭: 박스를 쥠 / 빈손 (범위 39.5~44.0)


@pytest.fixture
def cfg() -> f.Config:
    with open(REPO_CONFIG, encoding="utf-8") as fh:
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


def placements(per_dong: int = 3, dongs=("역삼동", "대치동", "청담동")) -> tuple[pp.Placement, ...]:
    out, n = [], 0
    for d in dongs:
        for s in range(per_dong):
            n += 1
            out.append(pp.Placement(f"{SID}-{n:03d}", d, ZONE_OF[d], s, "PLACED", n * 1000 * MS))
    return tuple(out)


def of(acts, kind) -> list:
    return [a for a in acts if isinstance(a, kind)]


def moves(acts) -> list[tuple]:
    return [(a.zone, a.slot, a.mode, a.cols) for a in of(acts, f.CallMove)]


def says(acts) -> list[str]:
    return [a.text for a in of(acts, f.Say)]


def started(cfg: f.Config, arg: str = ALL3, places=None) -> tuple[f.Ctx, list]:
    """palletize 접수 → 대상 조회 응답까지 (첫 PICK 을 보냈다)."""
    out = pf.step(running(cfg), palletize(arg))
    assert (
        out.reply == (True, "palletize 접수") and of(out.actions, pf.CallList)[0].session_id == SID
    )
    out2 = pf.step(
        out.ctx, pf.ListDone(True, "", placements() if places is None else places, 3000 * MS)
    )
    return out2.ctx, list(out.actions) + list(out2.actions)


def gateway(ctx: f.Ctx, acts: list, answer, limit: int = 100) -> tuple[f.Ctx, list]:
    """가짜 gateway: 마지막 CallMove 에 answer(CallMove, i) → MoveDone 로 답하기를 더 부를 것이 없을 때까지."""
    seen = list(acts)
    t = 4000 * MS
    for i in range(limit):
        pending = [a for a in seen if isinstance(a, f.CallMove)]
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


# ---------------------------------------------------------------- 완주


def test_three_dong_run_completes(cfg) -> None:
    ctx, acts = started(cfg)
    assert (
        says(acts)[0]
        == "역삼동, 대치동, 청담동 순서로 싣겠습니다. 첫 배송지 역삼동은 오른쪽 열입니다."
    )
    ctx = replace(ctx, slots={**ctx.slots, "A": 3, "B": 3, "C": 3})  # 트레이 세 곳 가득
    ctx, acts = gateway(ctx, acts, ok_all)
    mv = moves(acts)
    # 마지막 배송지(청담, C) 부터: 칸에서 집기 → 팔레트 열 0 의 칸 0·1·2 에 놓기 (cols 3)
    assert mv[:4] == [
        ("C", 0, "PICK", 0),
        ("PALLET", 0, "DROP", 3),
        ("C", 1, "PICK", 0),
        ("PALLET", 1, "DROP", 3),
    ]
    assert mv[12:14] == [
        ("A", 0, "PICK", 0),
        ("PALLET", 6, "DROP", 3),
    ]  # 첫 배송지 역삼 = 오른쪽 열 2
    assert mv[-1] == ("OBSERVE", 0, "", 0) and len(mv) == 19
    res = of(acts, pf.PalletOut)
    assert (
        [r.outcome for r in res] == ["DONE"] * 9
        and res[0].run_id == RUN
        and res[0].session_id == SID
    )
    assert (res[0].zone, res[0].slot, res[0].pallet_col, res[0].pallet_row, res[0].route_index) == (
        "C",
        0,
        0,
        0,
        2,
    )
    assert says(acts)[-1] == "팔레트 적재를 마쳤습니다. 9개 중 9개를 실었습니다."
    # 시작 전 RUNNING 으로, 관측 자세 도착부터 판독, 다 비운 구역 칸 0, 팔레트 9개
    assert ctx.state == f.RUNNING and ctx.phase == f.PH_NONE and ctx.stage_start_ns > 0
    assert (ctx.slots["A"], ctx.slots["B"], ctx.slots["C"], ctx.pallet_count) == (0, 0, 0, 9)
    st = pf.pallet_state(ctx)
    assert st["state"] == "DONE" and st["done"] == 9 and st["slot_state"] == ["DONE"] * 9


def test_two_dong_route_leaves_other_zone(cfg) -> None:
    ctx, acts = started(cfg, "청담,역삼")
    ctx = replace(ctx, slots={**ctx.slots, "A": 3, "B": 3, "C": 3})
    ctx, acts = gateway(ctx, acts, ok_all)
    drops = [m for m in moves(acts) if m[0] == "PALLET"]
    assert [d[1] for d in drops] == [0, 1, 2, 3, 4, 5] and {d[3] for d in drops} == {2}
    assert (ctx.slots["A"], ctx.slots["B"], ctx.slots["C"]) == (
        0,
        3,
        0,
    )  # 대치(B) 박스는 트레이에 남았다
    assert says(acts)[-1].startswith("팔레트 적재를 마쳤습니다. 6개 중 6개")


# ---------------------------------------------------------------- 집기 실패


def test_grip_fail_retries_twice_then_next_box(cfg) -> None:
    ctx, acts = started(cfg, "청담동", placements(dongs=("청담동",)))

    def answer(a, i, t):
        if a.mode == "PICK" and a.slot == 0:
            return f.MoveDone(False, "GRIP_FAIL: 집기 확인 실패", 0, t)  # 칸 0 박스는 3번 다 실패
        if a.mode == "PICK" and a.slot == 1 and i == 3:
            return f.MoveDone(
                False, "GRIP_FAIL: 집기 확인 실패", 0, t
            )  # 칸 1 은 한 번 실패 뒤 성공
        return ok_all(a, i, t)

    ctx, acts = gateway(ctx, acts, answer)
    assert [m[:3] for m in moves(acts)[:6]] == [("C", 0, "PICK")] * 3 + [("C", 1, "PICK")] * 2 + [
        ("PALLET", 1, "DROP")
    ]
    res = of(acts, pf.PalletOut)
    assert [(r.outcome, r.reason, r.attempts) for r in res] == [
        ("FAILED", "GRIP_FAIL", 3), ("DONE", "", 2), ("DONE", "", 1)
    ]  # fmt: skip
    # 실패한 박스의 팔레트 칸(0)은 비워 두고 다음 박스는 계획대로 칸 1·2
    assert pf.pallet_state(ctx)["slot_state"][:3] == ["FAILED", "DONE", "DONE"]
    assert "옮기지 못한 박스는 001번" in says(acts)[-1]
    assert (
        pp.emptied_zones(pf.run_of(ctx).plan, [f"{SID}-002", f"{SID}-003"]) == ()
    )  # 001 이 C 트레이에 남았다


# ---------------------------------------------------------------- stop·resume


def test_stop_while_picking_then_resume_checks_grip(cfg) -> None:
    ctx, _ = started(cfg, "청담동", placements(dongs=("청담동",)))
    ctx = pf.step(ctx, cmd("stop")).ctx
    assert ctx.state == f.PAUSED and ctx.phase == pf.PH_PICK  # 응답은 PAUSED 에서 받는다
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx  # 정지 전에 집기는 끝났다
    assert ctx.phase == f.PH_NONE and pf.current_box_id(ctx) == f"{SID}-001"
    assert pf.pallet_state(ctx)["state"] == "PAUSED"
    assert "보고 폭을 모름" in pf.step(ctx, cmd("resume")).reply[1]
    # 쥐고 있으면 그 칸에 놓는다
    out = pf.step(ctx, cmd("resume", grip=HOLDING))
    assert (
        out.reply[0]
        and out.ctx.state == pf.PALLETIZING
        and moves(out.actions) == [("PALLET", 0, "DROP", 1)]
    )
    # 놓쳤으면 FAILED·DROPPED, 알리고 다음 박스
    out = pf.step(ctx, cmd("resume", grip=EMPTY))
    res = of(out.actions, pf.PalletOut)
    assert [(r.box_id[-3:], r.outcome, r.reason) for r in res] == [("001", "FAILED", "DROPPED")]
    assert "001번 박스를 놓쳤습니다" in says(out.actions)[0] and moves(out.actions) == [
        ("C", 1, "PICK", 0)
    ]


def test_stop_after_open_counts_done_and_keeps_slots(cfg) -> None:
    ctx, acts = started(cfg, "청담동", placements(dongs=("청담동",)))
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
    assert moves(out.actions) == [("C", 1, "PICK", 0)]
    out = pf.step(out.ctx, f.MoveDone(True, "OK", 0, 8000 * MS))
    assert moves(out.actions) == [("PALLET", 1, "DROP", 1)]  # 다음 박스 칸은 당겨지지 않는다


def test_device_failure_mid_pick_pauses_then_repicks(cfg) -> None:
    ctx, _ = started(cfg, "청담동", placements(dongs=("청담동",)))
    out = pf.step(ctx, f.MoveDone(False, "LIMIT: 1206 NOT REACHABLE", 0, 5000 * MS))
    assert out.ctx.state == f.PAUSED and says(out.actions) == [
        "팔레트 적재 중 문제가 생겨 일시정지했습니다."
    ]
    assert not of(out.actions, pf.PalletOut)
    out = pf.step(out.ctx, cmd("resume", grip=EMPTY))  # 쥐고 있지 않다 → 박스는 칸에 있다
    assert moves(out.actions) == [("C", 0, "PICK", 0)] and pf.run_of(out.ctx).attempts == 2


def test_drop_failure_before_open_keeps_box_in_gripper(cfg) -> None:
    ctx, _ = started(cfg, "청담동", placements(dongs=("청담동",)))
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx
    out = pf.step(ctx, f.MoveDone(False, "TIMEOUT", 0, 9000 * MS))
    assert out.ctx.state == f.PAUSED and not of(out.actions, pf.PalletOut)
    out = pf.step(out.ctx, cmd("resume", grip=HOLDING))
    assert moves(out.actions) == [("PALLET", 0, "DROP", 1)]


def test_home_failure_then_resume_finishes(cfg) -> None:
    ctx, acts = started(cfg, "청담동", placements(1, dongs=("청담동",)))
    ctx, acts = gateway(
        ctx,
        acts,
        lambda a, i, t: (
            f.MoveDone(False, "TIMEOUT", 0, t) if a.zone == "OBSERVE" else ok_all(a, i, t)
        ),
    )
    assert ctx.state == f.PAUSED and pf.run_of(ctx).stage == "HOME"
    out = pf.step(ctx, cmd("resume"))
    assert moves(out.actions) == [("OBSERVE", 0, "", 0)]
    out = pf.step(out.ctx, f.MoveDone(True, "OK", 0, 20000 * MS))
    assert out.ctx.state == f.RUNNING and pf.pallet_state(out.ctx)["state"] == "DONE"


# ---------------------------------------------------------------- 대상 조회


def test_list_failure_or_plan_error_returns_to_previous_state(cfg) -> None:
    out = pf.step(running(cfg), palletize())
    back = pf.step(out.ctx, pf.ListDone(False, "DB_ERROR", (), 3000 * MS))
    assert back.ctx.state == f.RUNNING and back.ctx.pallet is None and not moves(back.actions)
    assert says(back.actions) == ["작업 기록을 읽지 못해 팔레트 적재를 시작하지 않습니다."]
    four = placements() + (pp.Placement(f"{SID}-020", "청담동", "B", 0, "PLACED", 50000 * MS),)
    back = pf.step(out.ctx, pf.ListDone(True, "", four, 3000 * MS))
    assert back.ctx.state == f.RUNNING and "청담동 4개" in says(back.actions)[0]


def test_stop_during_list_cancels_run(cfg) -> None:
    ctx = pf.step(running(cfg), palletize()).ctx
    ctx = pf.step(ctx, cmd("stop")).ctx
    out = pf.step(ctx, pf.ListDone(True, "", placements(), 3000 * MS))
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
    ctx, acts = started(cfg, "청담동", placements(1, dongs=("청담동",)))
    ctx, _ = gateway(ctx, acts, ok_all)
    assert ctx.state == f.RUNNING and ctx.pallet_count == 1
    assert "박스 1개가 남아" in pf.step(ctx, palletize("청담동")).reply[1]
    assert (
        "IDLE·PAUSED" in pf.step(ctx, cmd("reset_zone", "PALLET")).reply[1]
    )  # 사람이 손을 넣기 전에 멈춘다
    ctx = pf.step(ctx, cmd("stop")).ctx
    out = pf.step(ctx, cmd("reset_zone", "PALLET"))
    assert out.reply == (True, "PALLET 비움") and out.ctx.pallet_count == 0
    assert (
        pf.pallet_state(out.ctx)["state"] == "" and pf.step(out.ctx, palletize("청담동")).reply[0]
    )


def test_pallet_state_during_run(cfg) -> None:
    assert pf.pallet_state(running(cfg))["state"] == ""
    ctx, _ = started(cfg)
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 0, 5000 * MS)).ctx
    ctx = pf.step(ctx, f.MoveDone(True, "OK", 6000 * MS, 6000 * MS)).ctx  # 첫 박스 끝, 둘째 집는 중
    st = pf.pallet_state(ctx)
    assert (st["state"], st["total"], st["done"], st["failed"]) == ("RUNNING", 9, 1, 0)
    assert st["route"] == ["역삼동", "대치동", "청담동"] and st["box_id"] == f"{SID}-008"
    assert (
        st["slot_state"][:3] == ["DONE", "MOVING", "PLANNED"]
        and st["slot_box_id"][0] == f"{SID}-007"
    )
    assert len(st["slot_state"]) == 9


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
    with open(REPO_CONFIG, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    assert f.load_config(raw).pallet_ready is False  # 교시 전 — 레포 설정에 zones.pallet 없음
    raw["zones"]["pallet"] = {"pose": [100.0, 200.0, 260.0, 0.0, 180.0, 0.0]}
    assert f.load_config(raw).pallet_ready is True
    raw["zones"]["pallet"] = {"pose": None}
    assert f.load_config(raw).pallet_ready is False
