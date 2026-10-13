"""팔레타이징 상태 PALLETIZING (S2-T05, BRD v1.5 10.4·TR-PAL-02·05·06·08·09·10·11). ROS 없음, pytest 대상.

노드는 이 모듈의 step 을 부른다. 팔레타이징 이벤트(palletize·reset_zone PALLET·멈춘 실행의 resume·대상 조회 응답·
팔레타이징 이동 응답)만 여기서 처리하고, 나머지는 sort_fsm.step 으로 넘긴다(stop 도 sort_fsm 이 → PAUSED).

  palletize(경로) → 대상 조회(ListPlacements) → pallet_plan → 박스마다 MoveToZone(구역, 칸, PICK)
  → MoveToZone(PALLET, slot 0~15, DROP) → PalletResult → … → 끝나면 MoveToZone(OBSERVE) → 원래 상태
- 계획 직후(첫 PICK 전): 시작 안내, 싣지 않는 박스의 PalletResult(OVERFLOW·EXCLUDED), PalletState 발행(TR-PAL-10 ①).
- 시작 조건: 처리 중 박스가 없는 RUNNING·PAUSED 또는 세션이 있는 IDLE, ROBOT·LOG 준비, 팔레트 교시됨, 팔레트 비어 있음.
- PICK 이 GRIP_FAIL 이면 2회 더(최대 3회) → 그래도 실패면 FAILED·GRIP_FAIL 로 두고 다음 박스(박스는 원래 칸에 남는다).
- 그 밖의 실패·stop 은 PAUSED. resume 은 남은 박스부터 — 박스를 든 채 멈췄으면 RobotState 보고 폭으로 파지를 확인해
  쥐고 있으면 놓고, 놓쳤으면 FAILED·DROPPED 로 두고 작업자에게 알린다. 계획은 다시 세우지 않는다(칸이 당겨지지 않게).
- 1층 칸 박스가 FAILED 면 그 바로 위 2층 칸 박스를 빈 1층 칸에 당겨 놓고 위층 칸은 비운다(pending #37 결정) — 빈칸 위에
  박스를 올리지 않는다(기울거나 떨어짐).
- 2층 트레이 위층 박스가 3회 다 GRIP_FAIL 이면 FAILED 로 기록하고 PAUSED + "○ 구역 2층 박스를 집지 못했습니다. 박스를
  치운 뒤 재개해 주세요"(10/13 PL 결정 Q5/K5) — 그 박스가 아래 칸 위에 남아 있어 바로 아래 칸을 집으면 부딪친다.
  작업자가 치운 뒤 resume 하면 다음 박스(위층부터 집으므로 그 아래 칸)부터 이어 간다.
- 다 옮기면 관측 자세로 → 트레이가 다 빈 구역은 칸 카운터 0 → 구역별 실은 수·초과·경로 제외·실패 안내 → 시작 전 상태로.
여기서 정한 규칙은 src/voss_manager/CLAUDE.md 에 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from voss_manager import pallet_plan as pp
from voss_manager import sort_fsm as f

PALLETIZING = f.PALLETIZING
PH_LIST, PH_PICK, PH_DROP, PH_HOME = "PALLET_LIST", "PALLET_PICK", "PALLET_DROP", "PALLET_HOME"
MAX_PICK = 3  # 처음 + 재시도 2 (TR-PAL-05)
NO, YES, MAYBE = "NO", "YES", "MAYBE"  # 지금 박스를 쥐고 있나: 아니오 / 집음 / 집다가 멈춤(모름)
BUSY_MSG = "분류 중인 박스를 마친 뒤 다시 말씀해 주세요"


@dataclass(frozen=True)
class Run:
    """palletize 실행 하나."""

    run_id: str
    route: tuple[str, ...]
    back_to: str  # 끝나면 돌아갈 상태: IDLE | RUNNING | PAUSED
    plan: pp.Plan | None = None  # 대상 조회 응답 전 None
    results: tuple[tuple[str, str], ...] = ()  # (box_id, DONE | FAILED) 끝낸 차례대로
    attempts: int = 0  # 지금 박스의 PICK 호출 수
    holding: str = NO
    stage: str = ""  # 멈췄을 때 resume 이 이어 갈 단계: PICK | DROP | NEXT | HOME
    finished: bool = False
    # (box_id, 실제 놓는 칸) — 바로 아래 1층 칸이 FAILED 로 비어 그 칸에 당겨 놓는 2층 박스 (pending #37 결정 10/13).
    # DROP 을 보낼 때 한 번 정해 두고, 재개해도 같은 칸에 놓는다
    moved: tuple[tuple[str, int], ...] = ()


# ---------------------------------------------------------------- 이벤트·액션


@dataclass(frozen=True)
class ListDone:
    """/voss/log/list_placements 응답 (시간 초과·서비스 없음은 ok=false)."""

    ok: bool
    message: str
    placements: tuple[pp.Placement, ...]
    now_ns: int


@dataclass(frozen=True)
class CallList:
    session_id: str


@dataclass(frozen=True)
class PublishPalletState:
    """지금 PalletState 를 바로 발행 — 계획 직후·첫 PICK 전 (TR-PAL-10 ①)."""


@dataclass(frozen=True)
class PalletOut:
    """PalletResult 한 건 (필드 이름·값은 PalletResult.msg 그대로)."""

    run_id: str
    session_id: str
    box_id: str
    dong: str
    route_index: int
    zone: str
    slot: int
    pallet_slot: int  # 0~15, 싣지 않으면 -1
    pallet_col: int  # 1~4, 싣지 않으면 0
    pallet_lane: int
    pallet_layer: int
    outcome: str
    reason: str
    attempts: int
    stamp_ns: int


# ---------------------------------------------------------------- 조회 (노드 발행용)


def run_of(ctx: f.Ctx) -> Run | None:
    return ctx.pallet if isinstance(ctx.pallet, Run) else None


def _paused_run(ctx: f.Ctx) -> bool:
    run = run_of(ctx)
    return run is not None and not run.finished and ctx.state == f.PAUSED


def _finished_ids(run: Run) -> list[str]:
    return [b for b, _ in run.results]


def current(run: Run | None) -> pp.Move | None:
    """지금(또는 다음에) 옮길 박스."""
    if run is None or run.plan is None:
        return None
    rest = pp.remaining(run.plan, _finished_ids(run))
    return rest[0] if rest else None


def current_box_id(ctx: f.Ctx) -> str:
    """SortState.box_id — 팔레타이징 중·멈춤이면 지금 옮기는 박스."""
    run = run_of(ctx)
    if run is None or run.finished or ctx.state not in (PALLETIZING, f.PAUSED):
        return ""
    if run.stage in ("NEXT", "HOME"):
        return ""
    m = current(run)
    return m.box_id if m else ""


def pallet_state(ctx: f.Ctx) -> dict:
    """PalletState 필드 (voss_msgs.md, BRD v1.5). 실행이 없으면 state "", 칸 배열은 늘 16."""
    run = run_of(ctx)
    st = dict(run_id="", state="", route=[], dongs=[], load=[], overflow=[], excluded=[],
              overflow_warning=False, total=0, done=0, failed=0, box_id="",
              slot_state=["EMPTY"] * pp.CAPACITY, slot_box_id=[""] * pp.CAPACITY,
              slot_dong=[""] * pp.CAPACITY)  # fmt: skip
    if run is None:
        return st
    st.update(run_id=run.run_id, route=list(run.route), box_id=current_box_id(ctx))
    st["state"] = "DONE" if run.finished else ("RUNNING" if ctx.state == PALLETIZING else "PAUSED")
    st["done"] = sum(1 for _, o in run.results if o == "DONE")
    st["failed"] = sum(1 for _, o in run.results if o == "FAILED")
    if run.plan is None:
        return st
    rows = run.plan.counts()
    st.update(dongs=[r[0] for r in rows], load=[r[1] for r in rows], overflow=[r[2] for r in rows],
              excluded=[r[3] for r in rows], overflow_warning=run.plan.overflow > 0,
              total=len(run.plan.moves))  # fmt: skip
    outcome = dict(run.results)
    moved = dict(run.moved)
    # 당겨 놓은 박스는 실제 칸에 나중에 써서 아래 칸의 FAILED 박스를 덮고, 비운 위층 칸은 EMPTY 로 둔다 (pending #37)
    for m in sorted(run.plan.moves, key=lambda m: m.box_id in moved):
        slot = moved.get(m.box_id, m.pallet_slot)
        st["slot_box_id"][slot] = m.box_id
        st["slot_dong"][slot] = m.dong
        st["slot_state"][slot] = outcome.get(m.box_id) or (
            "MOVING" if m.box_id == st["box_id"] else "PLANNED"
        )
    return st


def start_sentence(plan: pp.Plan) -> str:
    """시작 안내 (BRD v1.5 10.4): 순서 되읽기 + 첫 배송지 위치. 초과가 있으면 남는 수도 말한다."""
    names = ", ".join(plan.route)
    if len(plan.route) == 1:
        text = f"{names} 박스를 팔레트에 싣겠습니다."
    else:
        text = f"{names} 순서로 싣겠습니다. 첫 배송지 {plan.route[0]}은 오른쪽입니다."
    if plan.empty:
        text += f" {', '.join(plan.empty)} 박스는 없습니다."
    if plan.overflow:
        text += (
            f" 팔레트가 {plan.capacity}칸이라 {plan.overflow}개는 싣지 못하고 원래 구역에 둡니다."
        )
    return text


def finish_sentence(plan: pp.Plan, results: tuple[tuple[str, str], ...], moved: int = 0) -> str:
    """끝 안내 (TR-PAL-10 ③): 구역별 실은 수, 초과로 못 실은 수, 경로 제외 수, 실패 박스."""
    outcome = dict(results)
    done = {d: 0 for d in plan.route}
    for m in plan.moves:
        if outcome.get(m.box_id) == "DONE":
            done[m.dong] += 1
    loaded = [f"{d} {n}개" for d, n in done.items() if n]
    text = "팔레트 적재를 마쳤습니다. "
    text += (", ".join(loaded) + "를 실었습니다.") if loaded else "실은 박스가 없습니다."
    rows = plan.counts()
    over = [f"{d} {o}개" for d, _, o, _ in rows if o]
    excl = [f"{d} {e}개" for d, _, _, e in rows if e]
    if over:
        text += f" 초과로 못 실은 박스는 {', '.join(over)}입니다."
    if excl:
        text += f" 경로에 없는 {', '.join(excl)}는 그대로 두었습니다."
    failed = [b for b, o in results if o == "FAILED"]
    if failed:
        text += f" 옮기지 못한 박스는 {', '.join(b[-3:] + '번' for b in failed)}입니다. 원래 칸을 확인해 주세요."
    if moved:
        text += f" 아래 칸이 비어 위층 박스 {moved}개를 아래 칸에 놓았습니다."
    return text


# ---------------------------------------------------------------- 전이


def step(ctx: f.Ctx, ev) -> f.Out:
    if isinstance(ev, f.Command):
        cmd = ev.command.strip().lower()
        if cmd == "palletize":
            return _on_palletize(ctx, ev)
        if cmd == "reset_zone" and ev.arg.strip().upper() == "PALLET":
            return _on_reset_pallet(ctx)
        if cmd == "reset_zone" and _paused_run(ctx):
            return _reject(
                ctx,
                "멈춘 팔레타이징이 있음 — 옮길 박스가 트레이에 남아 있어 비울 수 없다, resume 으로 끝낸 뒤",
            )
        if cmd == "resume" and _paused_run(ctx):
            return _on_resume(ctx, ev)
        if (
            cmd in ("start", "priority", "answer", "reset_zone", "recheck")
            and ctx.state == PALLETIZING
        ):
            return _reject(ctx, f"팔레타이징 중에는 {cmd} 를 받지 않음 — 끝나거나 stop 뒤")
        return f.step(ctx, ev)
    if isinstance(ev, ListDone):
        return _on_list(ctx, ev)
    if isinstance(ev, f.MoveDone) and ctx.phase in (PH_PICK, PH_DROP, PH_HOME):
        return _on_move(ctx, ev)
    return f.step(ctx, ev)


def _reject(ctx: f.Ctx, msg: str) -> f.Out:
    return f.Out(ctx, (f.Log("warn", f"명령 거부: {msg}"),), (False, msg))


def _on_palletize(ctx: f.Ctx, ev: f.Command) -> f.Out:
    try:
        route = pp.parse_route(ev.arg, ctx.cfg.dong_of)
    except pp.PlanError as e:
        return _reject(ctx, str(e))
    if ctx.state == PALLETIZING:
        return _reject(ctx, "이미 팔레타이징 중")
    if _paused_run(ctx):
        return _reject(ctx, "멈춘 팔레타이징이 있음 — resume 으로 이어 간다")
    if (
        ctx.state not in (f.IDLE, f.RUNNING, f.PAUSED)
        or ctx.box is not None
        or ctx.phase != f.PH_NONE
    ):
        return _reject(ctx, BUSY_MSG)
    if ctx.state == f.IDLE and not ctx.session_id:
        return _reject(ctx, "분류 세션이 없음 — 분류를 먼저 한다")
    if ctx.stop_failed:
        return _reject(ctx, "정지 응답 미확인 — 로봇 확인 후 stop 을 다시 보내 성공을 받은 뒤")
    missing = [k for k in ("ROBOT", "LOG") if k in f.not_ready_items(ctx, ev.not_ready)]
    if missing:
        return _reject(ctx, "준비 안 됨: " + ", ".join(missing))
    if not ctx.cfg.pallet_ready:
        return _reject(ctx, "팔레트 구역 좌표가 교시되지 않음 (zones.pallet.pose)")
    if ctx.pallet_count:
        return _reject(
            ctx, f"팔레트에 박스 {ctx.pallet_count}개가 남아 있음 — 비운 뒤 reset_zone PALLET"
        )
    if not ev.new_session_id:
        return _reject(ctx, "실행 ID 없음")
    run = Run(run_id=ev.new_session_id, route=route, back_to=ctx.state)
    return f.Out(
        replace(ctx, state=PALLETIZING, phase=PH_LIST, pallet=run, stop_requested=False),
        (
            CallList(ctx.session_id),
            f.Log("info", f"팔레타이징 {run.run_id} 접수: {' → '.join(route)}, 대상 조회"),
        ),
        (True, "palletize 접수"),
    )


def _on_reset_pallet(ctx: f.Ctx) -> f.Out:
    if ctx.state not in (f.IDLE, f.PAUSED):
        return _reject(ctx, "reset_zone PALLET 은 IDLE·PAUSED 에서만")
    if _paused_run(ctx):
        return _reject(ctx, "멈춘 팔레타이징이 있음 — resume 으로 끝낸 뒤 비운다")
    return f.Out(
        replace(ctx, pallet_count=0, pallet=None),
        (f.Log("info", f"팔레트 비움 확인 (박스 {ctx.pallet_count}개), 칸 0"),),
        (True, "PALLET 비움"),
    )


def _on_list(ctx: f.Ctx, ev: ListDone) -> f.Out:
    run = run_of(ctx)
    if ctx.phase != PH_LIST or run is None:
        return f.Out(ctx, (f.Log("warn", f"기다리지 않던 ListPlacements 응답 무시: {ev.message}"),))
    if ctx.state == f.PAUSED:
        # 조회 중 stop — 아무것도 옮기지 않았으니 실행을 접는다. 분류를 저절로 다시 시작하지는 않는다
        back = f.IDLE if run.back_to == f.IDLE else f.PAUSED
        return f.Out(
            replace(ctx, state=back, phase=f.PH_NONE, pallet=None),
            (f.Log("info", f"팔레타이징 {run.run_id} 취소: 대상 조회 중 정지"),),
        )
    if not ev.ok:
        return _abort(ctx, run, f"작업 기록 조회 실패 {ev.message}", "작업 기록을 읽지 못해")
    try:
        plan = pp.plan_pallet(
            run.route, ev.placements, layers=ctx.pallet_layers, tray_layer_cells=ctx.cfg.layer_cells
        )
    except pp.PlanError as e:
        return _abort(ctx, run, str(e), str(e) + " —")
    acts: list = [
        f.Say(start_sentence(plan)),
        f.Log(
            "info",
            f"팔레타이징 계획: 실음 {len(plan.moves)}, 초과 {plan.overflow}, 경로 제외 {plan.excluded}, "
            f"빈 동 {plan.empty or '-'} — {plan.counts()}",
        ),
    ]
    acts += [f.Log("info", f"팔레타이징 제외: {s}") for s in plan.skipped]
    # 싣지 않는 박스도 한 건씩 남긴다(TR-PAL-09 v1.5) — 원래 구역에 그대로 둔다(TR-PAL-11)
    acts += [PalletOut(run.run_id, ctx.session_id, u.box_id, u.dong, u.route_index, u.zone, u.slot,
                       -1, 0, 0, 0, u.reason, "", 0, ev.now_ns) for u in plan.unloaded]  # fmt: skip
    acts.append(PublishPalletState())  # 배치도·집계·경고를 첫 PICK 보다 먼저 (TR-PAL-10 ①)
    return _next(replace(ctx, pallet=replace(run, plan=plan)), acts)


def _abort(ctx: f.Ctx, run: Run, why: str, spoken: str) -> f.Out:
    """시작하지 않고 원래 상태로 (아무것도 옮기지 않았다)."""
    return f.Out(
        replace(ctx, state=run.back_to, phase=f.PH_NONE, pallet=None),
        (
            f.Log("warn", f"팔레타이징 {run.run_id} 시작 안 함: {why}"),
            f.Say(f"{spoken} 팔레트 적재를 시작하지 않습니다."),
        ),
    )


def _pick(ctx: f.Ctx, m: pp.Move, acts: list) -> f.Out:
    run = run_of(ctx)
    run = replace(run, attempts=run.attempts + 1, stage="PICK")
    return f.Out(
        replace(ctx, phase=PH_PICK, pallet=run),
        (
            *acts,
            f.CallMove(m.zone, m.slot, "PICK"),
            f.Log("info", f"{m.box_id} {m.dong} {m.zone} 칸 {m.slot} 집기 ({run.attempts}/{MAX_PICK}) → 팔레트 칸 {m.pallet_slot} (열·층·줄 {m.cell})"),
        ),
    )  # fmt: skip


def _next(ctx: f.Ctx, acts: list) -> f.Out:
    """다음 박스 집기, 없으면 관측 자세로."""
    run = replace(run_of(ctx), attempts=0, holding=NO)
    m = current(run)
    if m is None:
        return f.Out(
            replace(ctx, phase=PH_HOME, pallet=replace(run, stage="HOME")),
            (*acts, f.CallMove("OBSERVE", 0, ""), f.Log("info", "팔레트 적재 끝 → 관측 자세")),
        )
    return _pick(replace(ctx, pallet=run), m, acts)


def tray_layer(cfg: f.Config, m: pp.Move) -> int:
    """m 이 놓여 있던 트레이 칸의 층(1부터). 1층뿐인 구역은 1 (Config.layer_cells, cc1d0fe)."""
    n = cfg.layer_cells.get(m.zone.upper(), 0)
    return m.slot // n + 1 if n else 1


def planned_box(plan: pp.Plan, slot: int) -> str:
    """그 칸에 계획된 box_id (없으면 ""). 1층만 쓰면 옮기는 차례 ≠ 칸 번호라 칸으로 찾는다."""
    return next((m.box_id for m in plan.moves if m.pallet_slot == slot), "")


def placed_slot(run: Run, m: pp.Move) -> int:
    """이 박스를 실제로 놓을 칸. 계획 칸이 2층이고 바로 아래 1층 칸 박스가 FAILED(빈칸)면 그 아래 칸 (pending #37)."""
    moved = dict(run.moved)
    if m.box_id in moved:
        return moved[m.box_id]
    _, layer, _ = m.cell
    below = m.pallet_slot - pp.LANES  # 같은 열·같은 줄의 1층 = slot − 2
    if (
        layer == 2
        and below not in moved.values()
        and dict(run.results).get(planned_box(run.plan, below)) == "FAILED"
    ):
        return below
    return m.pallet_slot


def _drop(ctx: f.Ctx, m: pp.Move, acts: list) -> f.Out:
    run = replace(run_of(ctx), holding=YES, stage="DROP")
    target = placed_slot(run, m)
    note = ""
    if target != m.pallet_slot and m.box_id not in dict(run.moved):
        run = replace(run, moved=(*run.moved, (m.box_id, target)))
        note = f" — 아래 칸 {target} 이 비어(FAILED) 2층 칸 {m.pallet_slot} 대신 당겨 놓는다"
    return f.Out(
        replace(ctx, phase=PH_DROP, pallet=run),
        (
            *acts,
            f.CallMove(
                "PALLET", pp.grid_cell(target), "DROP"
            ),  # gateway 는 격자 칸 번호(voss_msgs.md)
            f.Log(
                "info",
                f"{m.box_id} 팔레트 칸 {target}(열·층·줄 {pp.slot_cell(target)}, 격자 {pp.grid_cell(target)}) "
                f"에 놓기{note}",
            ),
        ),
    )


def _finish_box(
    ctx: f.Ctx, m: pp.Move, outcome: str, reason: str, stamp_ns: int
) -> tuple[f.Ctx, list]:
    """박스 하나 끝 — PalletResult 를 내고 실행 기록에 넣는다."""
    run = run_of(ctx)
    slot = dict(run.moved).get(m.box_id, m.pallet_slot)  # 실제로 놓은(놓으려던) 칸
    col, layer, lane = pp.slot_cell(slot)
    res = PalletOut(run.run_id, ctx.session_id, m.box_id, m.dong, m.route_index, m.zone, m.slot,
                    slot, col, lane, layer, outcome, reason, run.attempts, stamp_ns)  # fmt: skip
    run = replace(run, results=(*run.results, (m.box_id, outcome)), holding=NO, stage="NEXT")
    count = ctx.pallet_count + (1 if outcome == "DONE" else 0)
    level = "info" if outcome == "DONE" else "warn"
    log = f.Log(level, f"{m.box_id} 팔레트 {outcome} {reason or ''} (시도 {res.attempts})".rstrip())
    return replace(ctx, pallet=run, pallet_count=count), [res, log]


def _pause(ctx: f.Ctx, run: Run, text: str, acts: list | None = None) -> f.Out:
    """PAUSED 로. 이미 멈춘 뒤(사람이 stop) 온 응답이면 안내 문장을 다시 말하지 않는다."""
    out = list(acts or [])
    out.append(f.Log("error" if ctx.state != f.PAUSED else "info", text))
    if ctx.state != f.PAUSED:
        out.append(f.Say("팔레트 적재 중 문제가 생겨 일시정지했습니다."))
    return f.Out(replace(ctx, state=f.PAUSED, phase=f.PH_NONE, pallet=run), tuple(out))


def _fail_reason(ctx: f.Ctx, ev: f.MoveDone) -> str:
    if ev.ok:
        return ""
    if ctx.state == f.PAUSED or ev.message.strip().upper().startswith("STOPPED"):
        return "STOPPED"
    return "DEVICE_ERROR"


def _on_move(ctx: f.Ctx, ev: f.MoveDone) -> f.Out:
    run = run_of(ctx)
    if run is None or run.plan is None:
        return f.Out(ctx, (f.Log("warn", f"기다리지 않던 MoveToZone 응답 무시: {ev.message}"),))
    if ctx.phase == PH_HOME:
        return _on_home(ctx, run, ev)
    m = current(run)
    if ctx.phase == PH_PICK:
        return _on_pick(ctx, run, m, ev)
    return _on_drop(ctx, run, m, ev)


def _on_pick(ctx: f.Ctx, run: Run, m: pp.Move, ev: f.MoveDone) -> f.Out:
    paused = ctx.state == f.PAUSED
    if ev.ok:
        if paused:
            run = replace(run, holding=YES, stage="DROP")
            return f.Out(
                replace(ctx, phase=f.PH_NONE, pallet=run),
                (f.Log("info", f"{m.box_id} 집은 채 멈춤 — resume 때 파지 확인 후 놓는다"),),
            )
        return _drop(ctx, m, [])
    if ev.message.strip().upper().startswith("GRIP_FAIL"):
        # 집기 확인 실패 — gateway 가 열고 올라왔다, 박스는 원래 칸에 있다
        if run.attempts < MAX_PICK:
            if paused:
                return f.Out(
                    replace(ctx, phase=f.PH_NONE, pallet=replace(run, holding=NO, stage="PICK"))
                )
            return _pick(ctx, m, [f.Log("warn", f"{m.box_id} 집기 실패 {ev.message} → 다시")])
        nctx, acts = _finish_box(ctx, m, "FAILED", "GRIP_FAIL", ev.now_ns)
        if paused:
            return f.Out(replace(nctx, phase=f.PH_NONE), tuple(acts))
        layer = tray_layer(ctx.cfg, m)
        if layer > 1:  # 위층 박스가 아래 칸 위에 남았다 — 사람이 치울 때까지 멈춘다 (Q5/K5)
            text = f"{m.zone} 구역 {layer}층 박스를 집지 못했습니다. 박스를 치운 뒤 재개해 주세요."
            log = f"{m.box_id} {m.zone} 칸 {m.slot}({layer}층) 집기 실패 — 아래 칸을 집기 전에 PAUSED (K5)"
            return f.Out(
                replace(nctx, state=f.PAUSED, phase=f.PH_NONE),
                (*acts, f.Log("warn", log), f.Say(text)),
            )
        return _next(nctx, acts)
    # 정지·장비 실패 — 박스가 그리퍼에 있을 수도 있다(상승 중 실패는 쥔 채 멈춘다). resume 때 파지 확인
    run = replace(run, holding=MAYBE, stage="PICK")
    return _pause(ctx, run, f"{m.box_id} 집기 중 {ev.message} → PAUSED")


def _on_drop(ctx: f.Ctx, run: Run, m: pp.Move, ev: f.MoveDone) -> f.Out:
    if ev.placed_stamp_ns:
        nctx, acts = _finish_box(ctx, m, "DONE", _fail_reason(ctx, ev), ev.placed_stamp_ns)
        if ev.ok and ctx.state == PALLETIZING:
            return _next(nctx, acts)
        if ctx.state == f.PAUSED:
            return f.Out(replace(nctx, phase=f.PH_NONE), tuple(acts))
        return _pause(nctx, run_of(nctx), f"{m.box_id} 놓았으나 {ev.message} → PAUSED", acts)
    # 개방 전 실패 — 박스는 그리퍼에 있다
    return _pause(
        ctx, replace(run, holding=YES, stage="DROP"), f"{m.box_id} 놓기 전 {ev.message} → PAUSED"
    )


def _on_home(ctx: f.Ctx, run: Run, ev: f.MoveDone) -> f.Out:
    if not ev.ok:
        return _pause(
            ctx,
            replace(run, stage="HOME"),
            f"팔레트 적재 뒤 관측 자세 이동 실패 {ev.message} → PAUSED",
        )
    return _complete(ctx, run, ev.now_ns)


def _complete(ctx: f.Ctx, run: Run, now_ns: int) -> f.Out:
    """다 옮기고 관측 자세 도착 — 빈 구역 칸 0, 결과 안내, 시작 전 상태로."""
    done = [b for b, o in run.results if o == "DONE"]
    failed = [b for b, o in run.results if o == "FAILED"]
    freed = pp.emptied_zones(run.plan, done)
    slots = {**ctx.slots, **{z: 0 for z in freed}}
    full = "" if ctx.full_zone in freed else ctx.full_zone
    text = finish_sentence(run.plan, run.results, len(run.moved))
    back = f.PAUSED if ctx.state == f.PAUSED else run.back_to  # 도착 뒤 stop 이 왔으면 멈춘 채로
    nctx = replace(ctx, state=back, phase=f.PH_NONE, slots=slots, full_zone=full,
                   pallet=replace(run, finished=True, stage=""))  # fmt: skip
    if back == f.RUNNING:
        nctx = replace(nctx, stage_start_ns=now_ns)  # 관측 자세 도착부터의 판독만 쓴다
    log = f"팔레타이징 {run.run_id} 끝: {len(done)}/{len(run.plan.moves)}, 실패 {failed or '-'}, 칸 0 구역 {freed or '-'} → {back}"
    return f.Out(nctx, (f.Say(text), f.Log("info", log)))


def _on_resume(ctx: f.Ctx, ev: f.Command) -> f.Out:
    if ctx.phase != f.PH_NONE:
        return _reject(ctx, f"이전 동작({ctx.phase}) 응답 대기 중")
    if ctx.stop_failed:
        return _reject(
            ctx, "정지 응답 미확인 — 로봇 확인 후 stop 을 다시 보내 성공을 받은 뒤 resume"
        )
    missing = [k for k in ("ROBOT",) if k in f.not_ready_items(ctx, ev.not_ready)]
    if missing:
        return _reject(ctx, "준비 안 됨: " + ", ".join(missing))
    run = run_of(ctx)
    base = replace(ctx, state=PALLETIZING, stop_requested=False)
    m = current(run)
    ok = (True, "resume 접수 (팔레타이징)")
    if run.stage == "HOME" or m is None:
        out = _next(base, [f.Log("info", "resume — 관측 자세로")])
        return f.Out(out.ctx, out.actions, ok)
    if run.stage == "NEXT":
        out = _next(base, [f.Log("info", "resume — 다음 박스")])
        return f.Out(out.ctx, out.actions, ok)
    if run.holding in (YES, MAYBE):
        if ev.grip_mm < 0:
            return _reject(ctx, "그리퍼 보고 폭을 모름 — /voss/robot/state 확인 후 resume")
        lo, hi = ctx.hold_width_mm
        gripping = lo <= ev.grip_mm <= hi
        if gripping:
            out = _drop(
                base,
                m,
                [f.Log("info", f"resume — {m.box_id} 파지 확인({ev.grip_mm:.1f} mm), 놓기")],
            )
            return f.Out(out.ctx, out.actions, ok)
        if run.holding == YES:
            # 든 박스를 놓쳤다 (TR-PAL-08) — 어디 있는지 모르니 FAILED 로 두고 작업자에게 알린다
            nctx, acts = _finish_box(base, m, "FAILED", "DROPPED", ev.now_ns)
            acts.append(f.Say(f"{m.box_id[-3:]}번 박스를 놓쳤습니다. 작업자가 확인해 주세요."))
            out = _next(nctx, acts)
            return f.Out(out.ctx, out.actions, ok)
        # 집다가 멈췄는데 쥐고 있지 않다 → 박스는 원래 칸에 있다, 다시 집는다
    out = _pick(
        replace(base, pallet=replace(run, holding=NO)),
        m,
        [f.Log("info", f"resume — {m.box_id} 다시 집기")],
    )
    return f.Out(out.ctx, out.actions, ok)
