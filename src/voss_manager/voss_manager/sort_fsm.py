"""sort_manager 상태기계 (ROS 없음, pytest 대상). 노드는 입출력만 맡는다.

step(ctx, event) → Out(ctx', actions, reply). ctx 는 바꾸지 않고 새 값을 돌려준다.

G0 최소 경로(T20 1차, docs/plan.md G0 준비):
  IDLE —start→ RUNNING(OBSERVE 이동 → 입구 관측) —명확한 stage 1 판독→ PICKING(TrackAndGrasp → MoveToZone PLACE)
  → SortResult → RUNNING. stop/resume/reset_zone, 구역 가득 → PAUSED.
RECHECK·ASKING 은 이름만 있고 아직 들어가지 않는다(T23 에서 재확인·질문·보류 흐름을 붙인다).
여기서 정한 G0 임시 규칙은 src/voss_manager/CLAUDE.md "G0 임시 규칙" 에 적는다.
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
    zone: str
    slot: int
    attempts: int = 0


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


def new_ctx(cfg: Config, home_first: bool = True) -> Ctx:
    return Ctx(cfg=cfg, slots={z: 0 for z in ZONES}, home_first=home_first)


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
        nxt, acts = _enter_running(ctx, ev.now_ns, stop_requested=False)
        return Out(nxt, (*acts, Log("info", "resume")), (True, "resume 접수"))

    if cmd == "reset_zone":
        zone = arg.upper()
        if zone not in ZONES:
            return _reject(ctx, f"모르는 구역: {arg}")
        if ctx.state != PAUSED:
            return _reject(ctx, "reset_zone 은 PAUSED 에서만")
        slots = {**ctx.slots, zone: 0}
        full = "" if ctx.full_zone == zone else ctx.full_zone
        return Out(
            replace(ctx, slots=slots, full_zone=full),
            (Log("info", f"{zone} 구역 비움 확인, 칸 0"),),
            (True, f"{zone} 비움"),
        )

    if cmd == "answer":
        # 질문 경로(ASKING)는 T23 에서 붙인다. 지금은 ASKING 에 들어가지 않는다
        return _reject(ctx, "ASKING 상태가 아님")

    return _reject(ctx, f"모르는 명령: {ev.command}")


def not_ready_items(ctx: Ctx, base: tuple[str, ...] | list[str]) -> list[str]:
    """노드의 판단에 FSM 이 아는 사유(정지 응답 미확인 = ROBOT)를 더한다."""
    nr = list(base)
    if ctx.stop_failed and "ROBOT" not in nr:
        nr.append("ROBOT")
    return nr


def _on_label(ctx: Ctx, ev: LabelSeen) -> Out:
    if ctx.state != RUNNING or ctx.phase != PH_NONE:
        return Out(ctx)  # 다른 상태의 판독은 지금 쓰지 않는다 (2·3단계는 T19·T23)
    if ev.stage != 1 or ev.track_id in ctx.decided:
        return Out(ctx)
    if not ev.track_fresh:
        return _note(ctx, ev.track_id, "GONE", "판독 무시: 박스가 시야에 없음")
    if ev.stamp_ns < ctx.stage_start_ns:
        return _note(ctx, ev.track_id, "STALE", "판독 무시: 관측 시작 전 촬영")

    dong, zone, why = resolve_label(ev.code, ev.dong, ev.confidence, ctx.cfg)
    if why:
        # G0 임시 규칙: 불확실하면 집지 않고 다음 판독을 기다린다 (재확인 구역 경로는 T23)
        return _note(
            ctx,
            ev.track_id,
            why,
            f"대기 {why} code={ev.code!r} dong={ev.dong!r} conf={ev.confidence:.2f}",
        )

    decided = ctx.decided | {ev.track_id}
    if ctx.priority and dong != ctx.priority:
        seq = ctx.seq + 1
        box = _box(ctx, ev, seq, dong, "", -1)
        res = _result(ctx, box, "PASSED", "", "NON_TARGET", ev.now_ns, 0)
        return Out(
            replace(ctx, seq=seq, decided=decided),
            (res, Log("info", f"{box.box_id} 비대상 통과 ({dong})")),
        )

    if ctx.slots[zone] >= ctx.cfg.capacity[zone]:
        return Out(
            replace(ctx, state=PAUSED, full_zone=zone, decided=decided),
            (
                Log("warn", f"{zone} 구역 가득 참 ({ctx.cfg.capacity[zone]}칸) → PAUSED"),
                Say(f"{zone} 구역이 가득 찼습니다. 비운 뒤 알려 주세요."),
            ),
        )

    missing = [k for k in ("ROBOT", "SERVO") if k in not_ready_items(ctx, ev.not_ready)]
    if missing:
        return Out(
            ctx, (Log("warn", f"track {ev.track_id} 집지 않음: 준비 안 됨 {', '.join(missing)}"),)
        )

    seq = ctx.seq + 1
    box = _box(ctx, ev, seq, dong, zone, ctx.slots[zone])
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
            Log("info", f"{box.box_id} track {ev.track_id} {dong}→{zone} 칸 {box.slot} 파지 시작"),
        ),
    )


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
        decided_by="OCR",
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

    if ctx.phase != PH_PLACE or ctx.box is None:
        return Out(ctx, (Log("warn", f"기다리지 않던 MoveToZone 응답 무시: {ev.message}"),))

    box = ctx.box
    placed = ev.placed_stamp_ns != 0
    if ev.ok:
        reason = ""
    elif ctx.stop_requested or ev.message.strip().upper().startswith("STOPPED"):
        # 게이트웨이가 stop 으로 끊었다(voss_msgs.md MoveToZone STOPPED, #100) — 누가 stop 을 불렀든 STOPPED
        reason = "STOPPED"
    else:
        reason = "DEVICE_ERROR"
    slots = dict(ctx.slots)
    if placed:
        # 그 칸에서 개방했으면(RETURN_FAILED 포함) 칸을 쓴 것 (MC-018)
        slots[box.zone] += 1
        res = _result(ctx, box, "PLACED", box.zone, reason, ev.placed_stamp_ns, box.attempts)
    else:
        res = _result(ctx, box, "FAILED", "", reason, ev.now_ns, box.attempts)

    if ev.ok and ctx.state == PICKING:
        return Out(
            _done(ctx, state=RUNNING, slots=slots, stage_start_ns=ev.now_ns),
            (res, Log("info", f"{box.box_id} {box.zone} 칸 {box.slot} 적재 완료")),
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


def _on_stop_done(ctx: Ctx, ev: StopDone) -> Out:
    if ev.success:
        return Out(replace(ctx, stop_failed=False), (Log("info", "로봇 정지 요청 성공"),))
    return Out(
        replace(ctx, stop_failed=True),
        (Log("error", f"로봇 정지 요청 응답 없음/오류 {ev.message} — 사람이 로봇을 확인한다"),),
    )
