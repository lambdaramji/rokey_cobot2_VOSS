"""sort_manager 상태기계 (ROS 없음, pytest 대상). 노드는 입출력만 맡는다.

step(ctx, event) → Out(ctx', actions, reply). ctx 는 바꾸지 않고 새 값을 돌려준다.

6상태 (T20, docs/architecture.md):
  IDLE —start→ RUNNING(OBSERVE 이동 → 입구 관측) —stage 1 판독→ PICKING(TrackAndGrasp → MoveToZone PLACE)
  → SortResult → RUNNING. stop/resume/reset_zone, 구역 가득 → PAUSED.
  불확실(후보는 있는데 LOW_CONF·불일치)하면 PICKING 의 목적지가 재확인 구역 → RECHECK(VIEW → ReadLabel)
  → 확정이면 PICK → 목적 구역 PLACE, 아니면 ASKING(질문 30 s) → 답 → PICK → PLACE / 무응답 → HOLD.
  (SRD v1.0 §5.7 질문, voss_msgs.md MoveToZone 재확인 실패 분기·ReadLabel, #51 MC-017)
여기서 정한 규칙은 src/voss_manager/CLAUDE.md "운용 규칙" 에 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

IDLE, RUNNING, PICKING, RECHECK, ASKING, PAUSED = (
    "IDLE",
    "RUNNING",
    "PICKING",
    "RECHECK",
    "ASKING",
    "PAUSED",
)
ACTIVE = (RUNNING, PICKING, RECHECK, ASKING)  # start(ALL)·priority 를 받는 운전 상태
ZONES = ("A", "B", "C", "RECHECK", "HOLD")
SORT_ZONES = ("A", "B", "C")

# 진행 중인 장비 호출 (한 번에 하나)
PH_NONE, PH_HOME, PH_GOAL, PH_PLACE = "", "HOME", "GOAL", "PLACE"
PH_VIEW, PH_READ, PH_PICK = (
    "VIEW",
    "READ",
    "PICK",
)  # 재확인: 구역 보기 → 다시 읽기 → 재확인 칸에서 집기
HOLD_WORDS = ("HOLD", "보류")
ASK_TIMEOUT_NS = 30_000_000_000  # 질문 발화부터 30 s (SRD §5.7)


# ---------------------------------------------------------------- 설정


@dataclass(frozen=True)
class Config:
    """voss_config.yaml 중 sort_manager 가 쓰는 부분."""

    zone_map: dict[str, str]  # 동 → 구역(A/B/C)
    codes: dict[str, str]  # 분류코드 → 동
    aliases: dict[str, list[str]]  # 동 → 별칭
    capacity: dict[str, int]  # 구역(대문자) → 칸 수 = grid cols × rows
    confidence_min: float
    version: str  # ZoneMap.version = SortResult.rule_version (≤ 16자)

    def dong_of(self, name: str) -> str:
        """정식 동 이름 또는 별칭 → 정식 이름. 없으면 ""."""
        if name in self.zone_map:
            return name
        for dong, names in self.aliases.items():
            if name in names:
                return dong
        return ""


def load_config(raw: dict) -> Config:
    """YAML dict 검사 후 Config. 쓰는 값이 비었거나 어긋나면 ValueError(기동 거부)."""
    zone_map = raw.get("zone_map") or {}
    if not zone_map:
        raise ValueError("zone_map 비어 있음")
    for dong, zone in zone_map.items():
        if str(zone).upper() not in SORT_ZONES:
            raise ValueError(f"zone_map {dong}: {zone} 는 A/B/C 가 아님")
    zone_map = {str(d): str(z).upper() for d, z in zone_map.items()}

    ocr = raw.get("ocr") or {}
    codes = {str(c): str(d) for c, d in (ocr.get("codes") or {}).items()}
    if not codes:
        raise ValueError("ocr.codes 비어 있음")
    for code, dong in codes.items():
        if dong not in zone_map:
            raise ValueError(f"ocr.codes {code}: {dong} 가 zone_map 에 없음")
    conf = ocr.get("confidence_min")
    if conf is None or not 0.0 < float(conf) <= 1.0:
        raise ValueError(f"ocr.confidence_min 이 (0, 1] 밖: {conf}")

    aliases = {str(d): [str(a) for a in (v or [])] for d, v in (raw.get("aliases") or {}).items()}
    for dong in aliases:
        if dong not in zone_map:
            raise ValueError(f"aliases {dong} 가 zone_map 에 없음")

    zones = {str(k).upper(): v for k, v in (raw.get("zones") or {}).items()}
    capacity = {}
    for z in ZONES:
        grid = (zones.get(z) or {}).get("grid") or {}
        cols, rows = grid.get("cols"), grid.get("rows")
        if not cols or not rows or int(cols) < 1 or int(rows) < 1:
            raise ValueError(f"zones.{z.lower()}.grid 의 cols·rows 가 없음")
        capacity[z] = int(cols) * int(rows)

    version = str(raw.get("version", ""))
    if not version or len(version) > 16:
        raise ValueError(f"version 이 비었거나 16자 초과: {version!r}")
    return Config(zone_map, codes, aliases, capacity, float(conf), version)


def zone_map_entries(cfg: Config) -> list[tuple[str, str, str, list[str]]]:
    """ZoneMap entries: (dong, zone, code, aliases). code 는 ocr.codes 역참조, 별칭 없으면 []."""
    code_of = {d: c for c, d in cfg.codes.items()}
    return [
        (d, z, code_of.get(d, ""), list(cfg.aliases.get(d, []))) for d, z in cfg.zone_map.items()
    ]


def make_session_id(now: datetime, rand4: str) -> str:
    """YYYYMMDDTHHMMSS-xxxx (20자, SortResult.session_id)."""
    return f"{now:%Y%m%dT%H%M%S}-{rand4}"


def intent_to_command(kind: str, dong: str, zone: str, box_id: str) -> tuple[str, str] | None:
    """Intent → (command, arg) (intent_json.md). update_zone_map 은 C 범위라 None."""
    k = kind.strip().lower()
    if k in ("start", "stop", "resume"):
        return k, ""  # start 의 dong 비움 = 전체 분류
    if k == "priority":
        return "priority", dong
    if k == "answer":
        return "answer", f"{box_id}|{dong or zone}"
    return None


def make_box_id(session_id: str, seq: int) -> str:
    """<session_id>-NNN (24자, DB 유일키)."""
    return f"{session_id}-{seq:03d}"


def resolve_label(code: str, dong: str, confidence: float, cfg: Config) -> tuple[str, str, str]:
    """판독 → (정식 동, 구역, 불확실 사유). 사유가 "" 이면 바로 분류해도 된다.

    분류코드가 동 이름보다 우선이고, 둘 다 읽혔는데 서로 다르면 불확실로 본다.
    """
    by_code = cfg.codes.get(code, "") if code else ""
    by_name = cfg.dong_of(dong) if dong else ""
    if by_code and by_name and by_code != by_name:
        return "", "", "CODE_DONG_MISMATCH"
    d = by_code or by_name
    if not d:
        return "", "", "UNKNOWN"
    if confidence < cfg.confidence_min:
        return d, cfg.zone_map[d], "LOW_CONF"
    return d, cfg.zone_map[d], ""


def label_candidates(cfg: Config, *names: str, codes: tuple[str, ...] = ()) -> tuple[str, ...]:
    """질문 후보 정식 동(순서 유지, 중복 없음): 분류코드가 가리키는 동 → 읽은 동 이름·2위 후보."""
    out: list[str] = []
    for c in codes:
        d = cfg.codes.get(c, "") if c else ""
        if d and d not in out:
            out.append(d)
    for n in names:
        d = cfg.dong_of(n) if n else ""
        if d and d not in out:
            out.append(d)
    return tuple(out)


# ---------------------------------------------------------------- 상태


@dataclass(frozen=True)
class Box:
    """처리 중인 박스 하나."""

    box_id: str
    track_id: int
    started_at_ns: int
    code: str
    dong: str
    confidence: float
    raw_text: str
    dong_alt: str
    zone: str  # 지금 놓으러 가는 구역 (재확인 경로면 처음엔 RECHECK, 판정 뒤 목적 구역)
    slot: int
    attempts: int = 0
    decided_by: str = "OCR"  # OCR | RECHECK | OPERATOR | NONE
    reason: str = ""  # 정상 끝의 SortResult.reason (무응답 보류 = NO_ANSWER)
    recheck_slot: int = -1  # 재확인 구역에 놓인 칸, 없으면 -1
    candidates: tuple[str, ...] = ()  # 질문 후보 정식 동


@dataclass(frozen=True)
class Ctx:
    cfg: Config
    state: str = IDLE
    session_id: str = ""
    seq: int = 0  # 이 세션에서 발급한 box_id 수
    slots: dict[str, int] = field(default_factory=dict)  # 구역 → 다음 칸 번호 = 개방한 횟수
    priority: str = ""  # "" = 전체 분류
    stage_start_ns: int = 0  # 이 시각 이후 촬영된 판독만 채택 (OBSERVE 도착 시각)
    phase: str = PH_NONE
    box: Box | None = None
    stop_requested: bool = False  # 진행 중 박스에 stop 이 걸렸다
    stop_failed: bool = (
        False  # /voss/robot/stop 응답 없음·오류 → ROBOT 미준비, stop 재성공까지 resume 거부
    )
    full_zone: str = ""  # 가득 차서 멈춘 구역, reset_zone 전 resume 거부
    decided: frozenset[int] = frozenset()  # 이 세션에서 처리를 정한 track_id
    noted: frozenset[tuple[int, str]] = (
        frozenset()
    )  # 이미 로그로 남긴 (track_id, 무시·대기 사유) — 2 Hz 반복 로그 방지
    home_first: bool = True  # start·resume 때 OBSERVE 로 먼저 이동
    recheck_busy: frozenset[int] = frozenset()  # 재확인 구역에 박스가 있는 칸 (보류로 남은 것 포함)
    question: str = ""  # ASKING 중 질문 문장 (SortState.pending_question)
    ask_deadline_ns: int = 0  # 이 시각까지 답이 없으면 보류
    ask_reprompted: bool = False  # 무효 답 재안내는 1회
    ask_timeout_ns: int = ASK_TIMEOUT_NS
    resume_to: str = (
        ""  # PAUSED 에서 resume 할 때 이어 갈 재확인 단계: RECHECK | ASKING | PICK | PLACE
    )


def new_ctx(cfg: Config, home_first: bool = True, ask_timeout_s: float = 30.0) -> Ctx:
    return Ctx(
        cfg=cfg,
        slots={z: 0 for z in ZONES},
        home_first=home_first,
        ask_timeout_ns=int(ask_timeout_s * 1e9),
    )


# ---------------------------------------------------------------- 이벤트


@dataclass(frozen=True)
class Command:
    """/voss/sort/command 또는 Intent 에서 바꾼 명령."""

    command: str
    arg: str
    now_ns: int
    not_ready: tuple[str, ...] = ()  # 노드가 계산한 준비 안 된 항목
    new_session_id: str = ""  # start 로 새 세션을 열 때 쓸 값(노드가 시계·난수로 만든다)


@dataclass(frozen=True)
class LabelSeen:
    """/voss/vision/label 한 건 + 노드가 붙인 트랙 정보."""

    track_id: int
    code: str
    dong: str
    confidence: float
    stage: int
    stamp_ns: int
    raw_text: str
    dong_alt: str
    now_ns: int
    started_at_ns: int = 0  # 이 트랙의 첫 BoxTrack 촬영 시각, 모르면 0
    track_fresh: bool = True  # 이 트랙의 BoxTrack 을 최근에 받았다(박스가 아직 시야에 있다)
    not_ready: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalDone:
    """TrackAndGrasp 응답. accepted=false 면 goal 거부(결과 없음)."""

    accepted: bool
    grasped: bool
    reason: str
    attempts: int
    now_ns: int


@dataclass(frozen=True)
class MoveDone:
    """MoveToZone 응답(시간 초과는 ok=false, message TIMEOUT, placed_stamp 0)."""

    ok: bool
    message: str
    placed_stamp_ns: int
    now_ns: int


@dataclass(frozen=True)
class StopDone:
    success: bool
    message: str
    now_ns: int


@dataclass(frozen=True)
class ReadDone:
    """/voss/vision/read_label 응답 (3단계 정지 재판독). 실패·시간 초과는 ok=false."""

    ok: bool
    code: str
    dong: str
    confidence: float
    dong_alt: str
    raw_text: str
    message: str
    now_ns: int


@dataclass(frozen=True)
class Tick:
    """주기 시각 (질문 30 s 타이머)."""

    now_ns: int


# ---------------------------------------------------------------- 액션


@dataclass(frozen=True)
class SendGoal:
    track_id: int


@dataclass(frozen=True)
class CancelGoal:
    pass


@dataclass(frozen=True)
class CallStop:
    pass


@dataclass(frozen=True)
class CallMove:
    zone: str
    slot: int
    mode: str = ""  # "" = PLACE


@dataclass(frozen=True)
class CallReadLabel:
    track_id: int = -1  # -1 = 시야 안 박스 아무거나
    slot: int = (
        -1
    )  # 그 박스를 놓은 재확인 칸 (ReadLabel.slot) — 보류로 남은 다른 칸 박스를 읽지 않게


@dataclass(frozen=True)
class Result:
    """SortResult 한 건 (필드 이름·값은 SortResult.msg 그대로)."""

    box_id: str
    code: str
    dong: str
    confidence: float
    decided_by: str
    zone: str
    outcome: str
    stamp_ns: int
    session_id: str
    track_id: int
    started_at_ns: int
    raw_text: str
    dong_alt: str
    rule_version: str
    reason: str
    attempts: int


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Log:
    level: str  # info | warn | error
    text: str


@dataclass(frozen=True)
class Out:
    ctx: Ctx
    actions: tuple = ()
    reply: tuple[bool, str] | None = None  # Command 응답(접수 여부)


# ---------------------------------------------------------------- 전이


def step(ctx: Ctx, ev) -> Out:
    if isinstance(ev, Command):
        return _on_command(ctx, ev)
    if isinstance(ev, LabelSeen):
        return _on_label(ctx, ev)
    if isinstance(ev, GoalDone):
        return _on_goal(ctx, ev)
    if isinstance(ev, MoveDone):
        return _on_move(ctx, ev)
    if isinstance(ev, StopDone):
        return _on_stop_done(ctx, ev)
    if isinstance(ev, ReadDone):
        return _on_read(ctx, ev)
    if isinstance(ev, Tick):
        return _on_tick(ctx, ev)
    raise TypeError(f"모르는 이벤트 {type(ev).__name__}")


def _reject(ctx: Ctx, msg: str) -> Out:
    return Out(ctx, (Log("warn", f"명령 거부: {msg}"),), (False, msg))


def _enter_running(ctx: Ctx, now_ns: int, **kw) -> tuple[Ctx, tuple]:
    """RUNNING 으로. home_first 면 OBSERVE 이동이 끝날 때까지 판독을 받지 않는다."""
    if ctx.home_first:
        return replace(ctx, state=RUNNING, phase=PH_HOME, **kw), (CallMove("OBSERVE", 0, ""),)
    return replace(ctx, state=RUNNING, phase=PH_NONE, stage_start_ns=now_ns, **kw), ()


def _on_command(ctx: Ctx, ev: Command) -> Out:
    cmd, arg = ev.command.strip().lower(), ev.arg.strip()

    if cmd == "stop":
        # 모든 상태에서 장비 stop 을 먼저, 그다음 goal 취소 (topics.md sort_manager, F-04)
        acts: list = [CallStop()]
        if ctx.phase == PH_GOAL:
            acts.append(CancelGoal())
        nxt = replace(ctx, stop_requested=ctx.box is not None)
        if ctx.state == ASKING:
            # 질문은 멈추고 타이머를 끈다 — resume 때 다시 묻고 30 s 를 새로 잰다 (SRD §5.7)
            nxt = replace(nxt, resume_to="ASKING", ask_deadline_ns=0)
        if ctx.state == IDLE:
            # 세션이 없어 PAUSED 로 가면 resume 할 곳이 없다 → IDLE 유지 (G0 임시 규칙)
            return Out(nxt, tuple(acts), (True, "stop 접수 (IDLE 유지)"))
        # 진행 중인 goal·이동의 응답은 PAUSED 에서 받아 정리한다 (phase 유지)
        acts.append(Log("info", f"stop: {ctx.state} → PAUSED"))
        return Out(replace(nxt, state=PAUSED), tuple(acts), (True, "stop 접수"))

    if cmd == "start":
        if arg.upper() not in ("", "ALL"):
            return _reject(ctx, f"start 인자는 빈값 또는 ALL: {arg}")
        if ctx.state in ACTIVE:
            return Out(
                replace(ctx, priority=""),
                (Log("info", "전체 분류로 전환"),),
                (True, "전체 분류로 전환"),
            )
        if ctx.state == PAUSED:
            return _reject(ctx, "PAUSED 에서는 resume")
        nr = not_ready_items(ctx, ev.not_ready)
        if nr:
            return _reject(ctx, "준비 안 됨: " + ", ".join(nr))
        if not ev.new_session_id:
            return _reject(ctx, "세션 ID 없음")
        nxt, acts = _enter_running(
            ctx,
            ev.now_ns,
            session_id=ev.new_session_id,
            seq=0,
            slots={z: 0 for z in ZONES},  # 새 세션 = 시작 점검에서 구역을 비운다 (MC-018)
            full_zone="",
            decided=frozenset(),
            noted=frozenset(),
            box=None,
            stop_requested=False,
        )
        log = Log("info", f"세션 {ev.new_session_id} 시작, 우선 {ctx.priority or '전체'}")
        return Out(nxt, (*acts, log), (True, "start 접수"))

    if cmd == "priority":
        dong = ctx.cfg.dong_of(arg)
        if not dong:
            return _reject(ctx, f"zone_map 에 없는 동: {arg}")
        if ctx.state == PAUSED:
            return _reject(ctx, "PAUSED 에서는 priority 를 받지 않음")
        return Out(
            replace(ctx, priority=dong), (Log("info", f"우선 분류 {dong}"),), (True, f"우선 {dong}")
        )

    if cmd == "resume":
        if ctx.state != PAUSED:
            return _reject(ctx, f"{ctx.state} 에서는 resume 불가")
        if ctx.phase != PH_NONE:
            return _reject(ctx, f"이전 동작({ctx.phase}) 응답 대기 중")
        if ctx.stop_failed:
            return _reject(
                ctx, "정지 응답 미확인 — 로봇 확인 후 stop 을 다시 보내 성공을 받은 뒤 resume"
            )
        if ctx.full_zone:
            return _reject(ctx, f"{ctx.full_zone} 구역 가득 참 — reset_zone 먼저")
        nr = not_ready_items(ctx, ev.not_ready)
        if nr:
            return _reject(ctx, "준비 안 됨: " + ", ".join(nr))
        if ctx.box is not None and ctx.resume_to:
            return _resume_recheck(ctx, ev.now_ns)
        nxt, acts = _enter_running(ctx, ev.now_ns, stop_requested=False)
        return Out(nxt, (*acts, Log("info", "resume")), (True, "resume 접수"))

    if cmd == "reset_zone":
        zone = arg.upper()
        if zone not in ZONES:
            return _reject(ctx, f"모르는 구역: {arg}")
        if ctx.state != PAUSED:
            return _reject(ctx, "reset_zone 은 PAUSED 에서만")
        if zone == "RECHECK" and ctx.box is not None and ctx.box.recheck_slot >= 0:
            return _reject(
                ctx, f"{ctx.box.box_id} 가 재확인 구역에서 처리 중 — resume 으로 끝낸 뒤 비운다"
            )
        slots = {**ctx.slots, zone: 0}
        full = "" if ctx.full_zone == zone else ctx.full_zone
        busy = frozenset() if zone == "RECHECK" else ctx.recheck_busy
        return Out(
            replace(ctx, slots=slots, full_zone=full, recheck_busy=busy),
            (Log("info", f"{zone} 구역 비움 확인, 칸 0"),),
            (True, f"{zone} 비움"),
        )

    if cmd == "answer":
        return _on_answer(ctx, arg, ev.now_ns)

    return _reject(ctx, f"모르는 명령: {ev.command}")


def not_ready_items(ctx: Ctx, base: tuple[str, ...] | list[str]) -> list[str]:
    """노드의 판단에 FSM 이 아는 사유(정지 응답 미확인 = ROBOT)를 더한다."""
    nr = list(base)
    if ctx.stop_failed and "ROBOT" not in nr:
        nr.append("ROBOT")
    return nr


def _on_label(ctx: Ctx, ev: LabelSeen) -> Out:
    if ctx.state == PICKING and ev.stage == 2:
        return _on_label_tracking(ctx, ev)
    if ctx.state != RUNNING or ctx.phase != PH_NONE:
        return Out(ctx)  # 그 밖의 상태·단계 판독은 쓰지 않는다 (3단계는 ReadLabel 응답으로 받는다)
    if ev.stage != 1 or ev.track_id in ctx.decided:
        return Out(ctx)
    if not ev.track_fresh:
        return _note(ctx, ev.track_id, "GONE", "판독 무시: 박스가 시야에 없음")
    if ev.stamp_ns < ctx.stage_start_ns:
        return _note(ctx, ev.track_id, "STALE", "판독 무시: 관측 시작 전 촬영")

    dong, zone, why = resolve_label(ev.code, ev.dong, ev.confidence, ctx.cfg)
    cands = label_candidates(ctx.cfg, ev.dong, ev.dong_alt, codes=(ev.code,))
    if why == "UNKNOWN":
        # 후보가 하나도 없으면(글자를 못 읽음) 집지 않고 다음 판독을 기다린다
        return _note(ctx, ev.track_id, why, f"대기 UNKNOWN raw={ev.raw_text!r}")

    decided = ctx.decided | {ev.track_id}
    if not why and ctx.priority and dong != ctx.priority:
        seq = ctx.seq + 1
        box = _box(ctx, ev, seq, dong, "", -1)
        res = _result(ctx, box, "PASSED", "", "NON_TARGET", ev.now_ns, 0)
        return Out(
            replace(ctx, seq=seq, decided=decided),
            (res, Log("info", f"{box.box_id} 비대상 통과 ({dong})")),
        )

    if why:
        # 후보는 있는데 불확실(LOW_CONF·코드와 동 이름 불일치) → 집어서 재확인 구역으로 (SRD SYS-FR-012)
        zone, slot = "RECHECK", _free_recheck_slot(ctx)
        if slot < 0:
            return _zone_full(ctx, "RECHECK", decided)
    elif ctx.slots[zone] >= ctx.cfg.capacity[zone]:
        return _zone_full(ctx, zone, decided)
    else:
        slot = ctx.slots[zone]

    missing = [k for k in ("ROBOT", "SERVO") if k in not_ready_items(ctx, ev.not_ready)]
    if missing:
        return Out(
            ctx, (Log("warn", f"track {ev.track_id} 집지 않음: 준비 안 됨 {', '.join(missing)}"),)
        )

    seq = ctx.seq + 1
    box = replace(_box(ctx, ev, seq, dong, zone, slot), candidates=cands)
    note = f" ({why} → 재확인)" if why else ""
    return Out(
        replace(
            ctx,
            state=PICKING,
            phase=PH_GOAL,
            seq=seq,
            box=box,
            decided=decided,
            stop_requested=False,
        ),
        (
            SendGoal(ev.track_id),
            Log(
                "info",
                f"{box.box_id} track {ev.track_id} {dong or '?'}→{zone} 칸 {box.slot} 파지 시작{note}",
            ),
        ),
    )


def _on_label_tracking(ctx: Ctx, ev: LabelSeen) -> Out:
    """추종 중(stage 2) 판독: 재확인 구역으로 가려던 박스가 확실해지면 목적 구역으로 바로 바꾼다."""
    box = ctx.box
    if box is None or ctx.phase != PH_GOAL or ev.track_id != box.track_id or box.zone != "RECHECK":
        return Out(ctx)
    dong, zone, why = resolve_label(ev.code, ev.dong, ev.confidence, ctx.cfg)
    if why or ctx.slots[zone] >= ctx.cfg.capacity[zone]:
        return Out(ctx)
    nbox = replace(
        box,
        zone=zone,
        slot=ctx.slots[zone],
        code=ev.code,
        dong=dong,
        confidence=ev.confidence,
        raw_text=ev.raw_text,
        dong_alt=ev.dong_alt,
    )
    return Out(
        replace(ctx, box=nbox),
        (
            Log(
                "info", f"{box.box_id} 추종 중 판독 확정 {dong} → 재확인 대신 {zone} 칸 {nbox.slot}"
            ),
        ),
    )


def _free_recheck_slot(ctx: Ctx) -> int:
    for k in range(ctx.cfg.capacity["RECHECK"]):
        if k not in ctx.recheck_busy:
            return k
    return -1


def _zone_full(ctx: Ctx, zone: str, decided: frozenset[int]) -> Out:
    return Out(
        replace(ctx, state=PAUSED, full_zone=zone, decided=decided),
        (
            Log("warn", f"{zone} 구역 가득 참 ({ctx.cfg.capacity[zone]}칸) → PAUSED"),
            Say(f"{_zone_word(zone)} 구역이 가득 찼습니다. 비운 뒤 알려 주세요."),
        ),
    )


def _zone_word(zone: str) -> str:
    return {"RECHECK": "재확인", "HOLD": "보류"}.get(zone, zone)


def _note(ctx: Ctx, track_id: int, why: str, text: str) -> Out:
    """판독을 쓰지 않을 때. 같은 트랙·사유는 처음 한 번만 로그."""
    key = (track_id, why)
    if key in ctx.noted:
        return Out(ctx)
    return Out(replace(ctx, noted=ctx.noted | {key}), (Log("info", f"track {track_id} {text}"),))


def _box(ctx: Ctx, ev: LabelSeen, seq: int, dong: str, zone: str, slot: int) -> Box:
    return Box(
        box_id=make_box_id(ctx.session_id, seq),
        track_id=ev.track_id,
        started_at_ns=ev.started_at_ns,
        code=ev.code,
        dong=dong,
        confidence=ev.confidence,
        raw_text=ev.raw_text,
        dong_alt=ev.dong_alt,
        zone=zone,
        slot=slot,
    )


def _result(
    ctx: Ctx, box: Box, outcome: str, zone: str, reason: str, stamp_ns: int, attempts: int
) -> Result:
    return Result(
        box_id=box.box_id,
        code=box.code,
        dong=box.dong,
        confidence=box.confidence,
        decided_by=box.decided_by,
        zone=zone,
        outcome=outcome,
        stamp_ns=stamp_ns,
        session_id=ctx.session_id,
        track_id=box.track_id,
        started_at_ns=box.started_at_ns,
        raw_text=box.raw_text,
        dong_alt=box.dong_alt,
        rule_version=ctx.cfg.version,
        reason=reason,
        attempts=attempts,
    )


def _done(ctx: Ctx, **kw) -> Ctx:
    """박스 처리를 끝내고 장비 호출 없음으로."""
    return replace(ctx, box=None, phase=PH_NONE, stop_requested=False, **kw)


def _on_goal(ctx: Ctx, ev: GoalDone) -> Out:
    if ctx.phase != PH_GOAL or ctx.box is None:
        return Out(ctx, (Log("warn", f"기다리지 않던 TrackAndGrasp 응답 무시: {ev.reason}"),))
    box = ctx.box
    if not ev.accepted:
        res = _result(ctx, box, "FAILED", "", "DEVICE_ERROR", ev.now_ns, 0)
        return Out(
            _done(ctx, state=PAUSED),
            (
                res,
                Log("error", f"{box.box_id} goal 거부 (belt_servo 바쁨 또는 미준비) → PAUSED"),
                Say("로봇이 준비되지 않아 일시정지했습니다."),
            ),
        )
    if ev.reason == "OK" and ev.grasped and ctx.state == PICKING and not ctx.stop_requested:
        box = replace(box, attempts=ev.attempts)
        return Out(
            replace(ctx, phase=PH_PLACE, box=box),
            (
                CallMove(box.zone, box.slot, ""),
                Log(
                    "info",
                    f"{box.box_id} 파지 완료(시도 {ev.attempts}) → {box.zone} 칸 {box.slot} 적재",
                ),
            ),
        )

    stopped = ctx.stop_requested or ev.reason == "CANCELED"
    reason = "STOPPED" if stopped else (ev.reason or "DEVICE_ERROR")
    res = _result(ctx, box, "FAILED", "", reason, ev.now_ns, ev.attempts)
    acts: list = [res]
    if ev.grasped:
        acts.append(
            Log("warn", f"{box.box_id} 파지된 채 정지 — 자동 개방하지 않음, 사람이 박스를 꺼낸다")
        )
    if stopped:
        acts.append(Log("info", f"{box.box_id} 정지로 FAILED"))
        return Out(_done(ctx), tuple(acts))
    # G0 임시 규칙: 실패 뒤 자동 복귀하지 않고 PAUSED (사람 확인 → resume 이 OBSERVE 로 보낸다)
    acts += [
        Log("warn", f"{box.box_id} 파지 실패 {reason}(시도 {ev.attempts}) → PAUSED"),
        Say("박스를 집지 못해 일시정지했습니다."),
    ]
    return Out(_done(ctx, state=PAUSED), tuple(acts))


def _on_move(ctx: Ctx, ev: MoveDone) -> Out:
    if ctx.phase == PH_HOME:
        if not ev.ok:
            return Out(
                replace(ctx, state=PAUSED, phase=PH_NONE),
                (
                    Log("error", f"OBSERVE 이동 실패 {ev.message} → PAUSED"),
                    Say("관측 자세로 가지 못해 일시정지했습니다."),
                ),
            )
        if ctx.state == RUNNING:
            return Out(
                replace(ctx, phase=PH_NONE, stage_start_ns=ev.now_ns),
                (Log("info", "OBSERVE 도착, 관측 시작"),),
            )
        return Out(replace(ctx, phase=PH_NONE))  # 이동 중 stop → PAUSED 유지
    if ctx.box is None:
        return Out(ctx, (Log("warn", f"기다리지 않던 MoveToZone 응답 무시: {ev.message}"),))
    if ctx.phase == PH_PLACE:
        return (
            _on_place(ctx, ev)
            if ctx.box.zone != "RECHECK" or ctx.box.recheck_slot >= 0
            else _on_place_recheck(ctx, ev)
        )
    if ctx.phase == PH_VIEW:
        return _on_view(ctx, ev)
    if ctx.phase == PH_PICK:
        return _on_pick(ctx, ev)
    return Out(ctx, (Log("warn", f"기다리지 않던 MoveToZone 응답 무시: {ev.message}"),))


def _fail_reason(ctx: Ctx, ev: MoveDone) -> str:
    if ev.ok:
        return ""
    if ctx.stop_requested or ev.message.strip().upper().startswith("STOPPED"):
        # 게이트웨이가 stop 으로 끊었다(voss_msgs.md MoveToZone STOPPED, #100) — 누가 stop 을 불렀든 STOPPED
        return "STOPPED"
    return "DEVICE_ERROR"


def _on_place(ctx: Ctx, ev: MoveDone) -> Out:
    """목적 구역(A·B·C·HOLD)에 놓기 — 벨트에서 바로 또는 재확인 뒤."""
    box = ctx.box
    placed = ev.placed_stamp_ns != 0
    reason = box.reason if ev.ok else _fail_reason(ctx, ev)
    slots = dict(ctx.slots)
    if placed:
        # 그 칸에서 개방했으면(RETURN_FAILED 포함) 칸을 쓴 것 (MC-018)
        slots[box.zone] += 1
        outcome = "HELD" if box.zone == "HOLD" else "PLACED"
        res = _result(ctx, box, outcome, box.zone, reason, ev.placed_stamp_ns, box.attempts)
    else:
        res = _result(ctx, box, "FAILED", "", reason, ev.now_ns, box.attempts)

    if ev.ok and ctx.state in (PICKING, RECHECK):
        return Out(
            _done(ctx, state=RUNNING, slots=slots, stage_start_ns=ev.now_ns),
            (
                res,
                Log("info", f"{box.box_id} {box.zone} 칸 {box.slot} 적재 완료 ({box.decided_by})"),
            ),
        )
    acts: list = [
        res,
        Log(
            "error" if not ev.ok else "info",
            f"{box.box_id} 적재 응답 ok={ev.ok} {ev.message} placed={placed}",
        ),
    ]
    if ctx.state != PAUSED:
        # 응답 유실·실패는 상태 확인 없이 자동 재호출하지 않는다 (voss_msgs.md MoveToZone)
        acts.append(Say("적재 중 문제가 생겨 일시정지했습니다."))
    return Out(_done(ctx, state=PAUSED, slots=slots), tuple(acts))


def _on_place_recheck(ctx: Ctx, ev: MoveDone) -> Out:
    """벨트에서 집은 박스를 재확인 구역에 놓았다 → 구역을 보러 간다(VIEW)."""
    box = ctx.box
    if ev.placed_stamp_ns == 0:
        # 개방 전 실패 — 박스는 그리퍼(또는 모름). 결과를 남기고 사람 확인
        return _on_place(ctx, ev)
    slots = {**ctx.slots, "RECHECK": ctx.slots["RECHECK"] + 1}
    nbox = replace(box, recheck_slot=box.slot)
    nxt = replace(ctx, box=nbox, slots=slots, recheck_busy=ctx.recheck_busy | {box.slot})
    if ev.ok and ctx.state == PICKING:
        return Out(
            replace(nxt, state=RECHECK, phase=PH_VIEW),
            (
                CallMove("RECHECK", 0, "VIEW"),
                Log("info", f"{box.box_id} 재확인 칸 {box.slot} 에 놓음 → 다시 읽기"),
            ),
        )
    # 놓았지만 복귀 실패·정지 — 박스는 재확인 칸에 있다. resume 때 VIEW 부터 다시
    acts: list = [
        Log("warn", f"{box.box_id} 재확인 칸에 놓았으나 ok={ev.ok} {ev.message} → PAUSED")
    ]
    if ctx.state != PAUSED:
        acts.append(Say("재확인 구역에 놓는 중 문제가 생겨 일시정지했습니다."))
    return Out(replace(nxt, state=PAUSED, phase=PH_NONE, resume_to="RECHECK"), tuple(acts))


def _on_view(ctx: Ctx, ev: MoveDone) -> Out:
    box = ctx.box
    if ctx.state == PAUSED:
        return Out(replace(ctx, phase=PH_NONE, resume_to="RECHECK"))
    if not ev.ok:
        # VIEW 실패(view_pose 미교시 포함) → 질문 경로 (#51 MC-017)
        return _ask(replace(ctx, phase=PH_NONE), ev.now_ns, f"구역 보기 실패 {ev.message}")
    return Out(
        replace(ctx, phase=PH_READ),
        (
            CallReadLabel(-1, box.recheck_slot),
            Log("info", f"{box.box_id} 재확인 칸 {box.recheck_slot} 판독 요청"),
        ),
    )


def _on_read(ctx: Ctx, ev: ReadDone) -> Out:
    if ctx.phase != PH_READ or ctx.box is None:
        return Out(ctx, (Log("warn", f"기다리지 않던 ReadLabel 응답 무시: {ev.message}"),))
    box = ctx.box
    if ctx.state == PAUSED:
        return Out(replace(ctx, phase=PH_NONE, resume_to="RECHECK"))
    cands = label_candidates(ctx.cfg, ev.dong, ev.dong_alt, *box.candidates, codes=(ev.code,))
    nbox = replace(box, candidates=cands)
    if ev.ok:
        dong, zone, why = resolve_label(ev.code, ev.dong, ev.confidence, ctx.cfg)
        if not why:
            nbox = replace(
                nbox,
                code=ev.code,
                dong=dong,
                confidence=ev.confidence,
                raw_text=ev.raw_text,
                dong_alt=ev.dong_alt,
            )
            return _decide(replace(ctx, box=nbox, phase=PH_NONE), zone, "RECHECK", "", ev.now_ns)
        detail = f"{why} conf={ev.confidence:.2f}"
    else:
        detail = f"판독 실패 {ev.message}"
    return _ask(replace(ctx, box=nbox, phase=PH_NONE), ev.now_ns, detail)


def _ask(ctx: Ctx, now_ns: int, why: str) -> Out:
    """작업자에게 묻는다. 30 s 타이머는 이 발화부터 (SRD §5.7)."""
    box = ctx.box
    cands = box.candidates[:2] or tuple(ctx.cfg.zone_map)
    nbox = replace(box, candidates=cands)
    if len(cands) == 1:
        choice = f"{cands[0]}입니까?"
    else:
        choice = ", ".join(cands[:-1]) + f", {cands[-1]} 중 어디입니까?"
    q = f"{box.box_id[-3:]}번 박스 송장을 확인하지 못했습니다. {choice} 보류하려면 보류라고 말해 주세요."
    return Out(
        replace(
            ctx,
            box=nbox,
            state=ASKING,
            question=q,
            ask_deadline_ns=now_ns + ctx.ask_timeout_ns,
            ask_reprompted=False,
            resume_to="",
        ),
        (Say(q), Log("info", f"{box.box_id} 질문 ({why}): 후보 {', '.join(cands)}")),
    )


def _on_answer(ctx: Ctx, arg: str, now_ns: int) -> Out:
    if ctx.state != ASKING or ctx.box is None:
        return _reject(ctx, "ASKING 상태가 아님")
    box_id, _, value = arg.partition("|")
    if box_id.strip() != ctx.box.box_id:
        return _reject(
            ctx, f"지금 질문 중인 박스가 아님: {box_id.strip()} (질문 중 {ctx.box.box_id})"
        )
    value = value.strip()
    if value.upper() in HOLD_WORDS:
        out = _decide(ctx, "HOLD", "OPERATOR", "", now_ns)
        return Out(out.ctx, out.actions, (True, "보류 접수"))
    dong = ctx.cfg.dong_of(value)
    if dong and dong in ctx.box.candidates:
        code = ctx.box.code if ctx.cfg.codes.get(ctx.box.code) == dong else ""
        nbox = replace(ctx.box, dong=dong, code=code)
        out = _decide(replace(ctx, box=nbox), ctx.cfg.zone_map[dong], "OPERATOR", "", now_ns)
        return Out(out.ctx, out.actions, (True, f"{dong} 접수"))
    # 후보가 아닌 답: 1회만 다시 안내하고 타이머는 그대로 (SRD §5.7)
    msg = f"후보가 아닌 답: {value}"
    if ctx.ask_reprompted:
        return _reject(ctx, msg)
    again = f"다시 말씀해 주세요. {ctx.question}"
    return Out(
        replace(ctx, ask_reprompted=True),
        (Say(again), Log("warn", f"{ctx.box.box_id} {msg} — 재안내")),
        (False, msg + " — 재안내"),
    )


def _on_tick(ctx: Ctx, ev: Tick) -> Out:
    if ctx.state != ASKING or not ctx.ask_deadline_ns or ev.now_ns < ctx.ask_deadline_ns:
        return Out(ctx)
    out = _decide(ctx, "HOLD", "NONE", "NO_ANSWER", ev.now_ns)
    return Out(out.ctx, (Say("응답이 없어 보류 구역에 놓습니다."), *out.actions))


def _decide(ctx: Ctx, zone: str, decided_by: str, reason: str, now_ns: int) -> Out:
    """재확인·질문으로 목적 구역이 정해졌다 → 재확인 칸에서 집으러 간다(PICK)."""
    box = ctx.box
    nbox = replace(box, zone=zone, decided_by=decided_by, reason=reason)
    base = replace(ctx, box=nbox, question="", ask_deadline_ns=0, ask_reprompted=False)
    if ctx.slots[zone] >= ctx.cfg.capacity[zone]:
        # 박스는 재확인 칸에 둔 채 멈춘다 — reset_zone 뒤 resume 하면 PICK 부터
        out = _zone_full(base, zone, ctx.decided)
        return Out(replace(out.ctx, phase=PH_NONE, resume_to="PICK"), out.actions)
    nbox = replace(nbox, slot=ctx.slots[zone])
    return Out(
        replace(base, box=nbox, state=RECHECK, phase=PH_PICK, resume_to=""),
        (
            CallMove("RECHECK", box.recheck_slot, "PICK"),
            Log(
                "info",
                f"{box.box_id} {decided_by} 판정 → {zone} 칸 {nbox.slot}, 재확인 칸 {box.recheck_slot} 에서 집기",
            ),
        ),
    )


def _on_pick(ctx: Ctx, ev: MoveDone) -> Out:
    box = ctx.box
    if ev.ok:
        nbox = replace(box, recheck_slot=-1)
        nxt = replace(ctx, box=nbox, recheck_busy=ctx.recheck_busy - {box.recheck_slot})
        if ctx.state == PAUSED:
            # 집어 든 채 멈췄다 — resume 때 목적 구역에 놓는다
            return Out(replace(nxt, phase=PH_NONE, resume_to="PLACE"))
        return Out(
            replace(nxt, phase=PH_PLACE),
            (
                CallMove(box.zone, box.slot, ""),
                Log("info", f"{box.box_id} 재확인 칸에서 집음 → {box.zone} 칸 {box.slot}"),
            ),
        )
    # PICK 실패 → 박스는 재확인 칸에 둔 채 보류(HELD), 사람 확인 (#51 MC-017)
    reason = _fail_reason(ctx, ev)
    res = replace(
        _result(ctx, box, "HELD", "RECHECK", reason, ev.now_ns, box.attempts),
        decided_by=box.decided_by,
    )
    acts: list = [
        res,
        Log("error", f"{box.box_id} 재확인 칸에서 집기 실패 {ev.message} → 보류, PAUSED"),
    ]
    if ctx.state != PAUSED:
        acts.append(Say("재확인 구역의 박스를 집지 못해 일시정지했습니다."))
    return Out(_done(ctx, state=PAUSED, question=""), tuple(acts))


def _resume_recheck(ctx: Ctx, now_ns: int) -> Out:
    """재확인 흐름 중 멈췄던 박스를 이어 간다."""
    box, to = ctx.box, ctx.resume_to
    base = replace(ctx, stop_requested=False, resume_to="")
    if to == "ASKING":
        q = ctx.question
        return Out(
            replace(
                base,
                state=ASKING,
                ask_deadline_ns=now_ns + ctx.ask_timeout_ns,
                ask_reprompted=False,
            ),
            (Say(q), Log("info", f"{box.box_id} resume — 다시 질문")),
            (True, "resume 접수 (다시 질문)"),
        )
    if to == "PICK":
        out = _decide(base, box.zone, box.decided_by, box.reason, now_ns)
        return Out(out.ctx, out.actions, (True, "resume 접수 (재확인 칸에서 집기)"))
    if to == "PLACE":
        return Out(
            replace(base, state=RECHECK, phase=PH_PLACE),
            (
                CallMove(box.zone, box.slot, ""),
                Log("info", f"{box.box_id} resume — {box.zone} 에 놓기"),
            ),
            (True, "resume 접수 (적재)"),
        )
    return Out(
        replace(base, state=RECHECK, phase=PH_VIEW),
        (CallMove("RECHECK", 0, "VIEW"), Log("info", f"{box.box_id} resume — 재확인 다시")),
        (True, "resume 접수 (재확인 다시)"),
    )


def _on_stop_done(ctx: Ctx, ev: StopDone) -> Out:
    if ev.success:
        return Out(replace(ctx, stop_failed=False), (Log("info", "로봇 정지 요청 성공"),))
    return Out(
        replace(ctx, stop_failed=True),
        (Log("error", f"로봇 정지 요청 응답 없음/오류 {ev.message} — 사람이 로봇을 확인한다"),),
    )
