"""gate_summary — belt_servo 시도 로그로 G1 게이트 회차 기록표·요약을 만든다 (ROS 없이 돈다).

- 입력: 시도 로그 `<log.dir>/attempts/servo_attempts_*.jsonl` (GOAL_END 행 1개 = 사례 1건, log_schema.py).
- 출력: docs/g1-gate.md 3절 회차 기록표와 **같은 11열** Markdown 표 + 자동 힌트 표 + 5절 "측정:" 문장.
- 원인 열은 비워 둔다. 원인은 영상·로그를 보고 사람이 정한다(g1-gate 3절). 자동 힌트는 보조일 뿐이다.
- 성공 = reason OK 이고 grasped true. 영상 확인(안전 높이까지 들림)은 사람이 따로 한다.
- 순수 함수(파싱·판정·집계·렌더)와 I/O(파일 찾기·읽기·git·쓰기·main)를 나눠 둔다 → test/test_gate_summary.py.
- 사용법: design/U6-run.md.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from voss_servo import fsm
from voss_servo import log_schema as ls

# ---------------------------------------------------------------- 상수

KST = timezone(timedelta(hours=9))  # 한국 표준시 (UTC+9)

# docs/g1-gate.md 3절 회차 기록표의 열 (순서 그대로). 문서가 바뀌면 시험이 깨진다
GATE_COLUMNS: tuple[str, ...] = (
    "#",
    "시각",
    "박스(송장)",
    "track_id",
    "reason",
    "attempts",
    "성공",
    "최초 시도 성공",
    "원인",
    "bag 시각",
    "비고",
)

# 자동 힌트 표의 열 (원인 판정 보조 — 기록표와 따로 둔다)
HINT_COLUMNS: tuple[str, ...] = (
    "#",
    "goal_id",
    "reason",
    "cause",
    "자동 힌트",
    "마지막 phase",
    "재시도 원인",
    "추종 s",
    "하강 최대 오차 mm",
)

GATE_RATIO = 0.7  # 게이트 기준 70 % (ADR-0002)
SHORT_ID = 8  # 표에 보여 줄 goal_id 앞자리 수
SHORT_SHA = 12  # 요약 문장에 넣을 sha 앞자리 수 (gateway config sha 와 같은 길이)
BLANK = "____"  # 모르는 값 자리 (g1-gate 문구와 같은 모양)
HOLD_CAUSE = "ZERO_HOLD"  # goal 끝난 뒤 0 유지 틱 표시 (belt_servo.py)

# 행 상태
COUNTED = "counted"  # 분모에 넣는 사례
INVALID = "invalid"  # 무효 (--exclude, 사람 판단)
OVER = "over"  # 분모(--limit)를 다 채운 뒤 들어온 goal


# ---------------------------------------------------------------- 자료 모양


@dataclass(frozen=True)
class GoalCase:
    """GOAL_END 행 하나 = 사례 하나."""

    goal_id: str  # goal UUID 16진수
    track_id: int | None  # 박스 트랙 번호
    t_end_s: float | None  # GOAL_END 의 t_calc_s (ROS 시각, s)
    reason: str | None  # result.reason (계약 7종)
    cause: str  # 로그용 세부 원인 (없으면 "")
    grasped: bool  # result.grasped
    attempts: int | None  # 파지 시도 수 (GOAL_END attempt, 없으면 추정)
    attempts_estimated: bool  # attempt 필드가 없어 ATTEMPT_END 수로 추정했나
    retry_causes: tuple[str, ...]  # ATTEMPT_END 행의 cause (재시도로 이어진 실패 원인)
    phase: str | None  # goal 이 끝난 phase
    config_version: Any  # voss_config 버전
    config_sha256: str | None  # voss_config sha
    params_sha256: str | None  # belt_servo 파라미터 sha
    belt_speed_mps: float | None  # 벨트 속도 설정 (m/s)


@dataclass(frozen=True)
class TickSummary:
    """goal 하나의 틱 로그 요약 (원인 판정 보조)."""

    n_ticks: int  # 0 유지 틱을 뺀 틱 수
    track_s: float  # TRACK phase 에 머문 시간 합 (s)
    descend_max_err_mm: float | None  # DESCEND 중 ‖error_m‖ 최댓값 (mm)


@dataclass(frozen=True)
class Row:
    """기록표 한 줄."""

    label: str  # "#" 칸: 분모 순번("1"…), "무효", "초과"
    status: str  # COUNTED | INVALID | OVER
    case: GoalCase  # 그 사례


@dataclass(frozen=True)
class Stats:
    """분모 안 사례의 집계."""

    counted: int  # 분모에 넣은 사례 수
    success: int  # 성공 수
    first_try: int  # 최초 시도 성공 수
    invalid: int  # 무효 수 (--exclude)
    over: int  # 분모를 넘어 들어온 수
    practice: int  # --since 전 goal 수 (연습, 표에 넣지 않음)
    reasons: dict[str, int]  # 분모 안 reason 분포
    hints: dict[str, int]  # 분모 안 실패의 자동 힌트 분포


# ---------------------------------------------------------------- 순수 함수: 파싱


def parse_lines(lines: Iterable[str], source: str) -> tuple[list[dict], list[str]]:
    """JSON Lines 를 사전 목록으로. 깨진 줄은 건너뛰고 경고를 남긴다."""
    rows: list[dict] = []  # 읽은 행
    warnings: list[str] = []  # 경고 문장
    for number, line in enumerate(lines, start=1):  # 줄 번호는 1부터
        text = line.strip()  # 앞뒤 공백·줄바꿈 제거
        if not text:
            continue  # 빈 줄은 조용히 넘긴다
        try:
            value = json.loads(text)  # 한 줄 = JSON 하나
        except json.JSONDecodeError as exc:
            warnings.append(f"{source}:{number} 깨진 줄 무시 ({exc.msg})")  # 노드가 쓰다 죽은 줄 등
            continue
        if not isinstance(value, dict):
            warnings.append(f"{source}:{number} 사전이 아닌 줄 무시")  # 숫자·목록 한 줄
            continue
        rows.append(value)  # 정상 행
    return rows, warnings


def _as_int(value: Any) -> int | None:
    """정수로 쓸 수 있으면 int, 아니면 None (bool 은 정수로 보지 않는다)."""
    if isinstance(value, bool):
        return None  # True/False 가 1/0 으로 섞이지 않게
    if isinstance(value, int):
        return value  # 정수 그대로
    if isinstance(value, float) and value.is_integer():
        return int(value)  # 2.0 → 2
    return None


def _as_float(value: Any) -> float | None:
    """유한한 실수면 float, 아니면 None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None  # 숫자가 아님
    number = float(value)  # 정수도 실수로
    return number if math.isfinite(number) else None  # NaN·무한대는 None


def _make_case(end: dict, retry_rows: list[dict]) -> tuple[GoalCase, list[str]]:
    """GOAL_END 행 + 같은 goal 의 ATTEMPT_END 행들 → GoalCase."""
    warnings: list[str] = []
    goal_id = str(end.get("goal_id"))  # 사례 이름
    retry_causes = tuple(str(r.get("cause") or "") for r in retry_rows)  # 재시도 원인들
    attempts = _as_int(end.get("attempt"))  # GOAL_END 의 시도 수 (기준값)
    estimated = attempts is None  # 필드가 없으면 추정한다
    if estimated:
        attempts = len(retry_rows) + 1  # 재시도 수 + 마지막 시도 1회
        warnings.append(
            f"goal {goal_id[:SHORT_ID]}: attempt 없음 → ATTEMPT_END 수로 추정 {attempts}"
        )
    elif attempts < len(retry_rows):
        warnings.append(  # 시도 수가 재시도 행보다 적으면 로그가 이상하다
            f"goal {goal_id[:SHORT_ID]}: attempt {attempts} < ATTEMPT_END {len(retry_rows)}행"
        )
    case = GoalCase(
        goal_id=goal_id,
        track_id=_as_int(end.get("track_id")),
        t_end_s=_as_float(end.get("t_calc_s")),
        reason=end.get("reason"),
        cause=str(end.get("cause") or ""),
        grasped=end.get("grasped") is True,  # null·false 는 모두 못 잡음
        attempts=attempts,
        attempts_estimated=estimated,
        retry_causes=retry_causes,
        phase=end.get("phase"),
        config_version=end.get("config_version"),
        config_sha256=end.get("config_sha256"),
        params_sha256=end.get("params_sha256"),
        belt_speed_mps=_as_float(end.get("belt_speed_mps")),
    )
    return case, warnings


def _sort_key(case: GoalCase) -> tuple[bool, float]:
    """끝난 시각 순서. 시각이 없는 사례는 맨 뒤."""
    return (case.t_end_s is None, case.t_end_s or 0.0)


def collect_cases(rows: Iterable[dict]) -> tuple[list[GoalCase], list[str]]:
    """시도 로그 행들 → 끝난 시각 순 사례 목록 (GOAL_END 1행 = 사례 1건)."""
    warnings: list[str] = []
    ends: dict[str, dict] = {}  # goal_id → GOAL_END 행 (처음 것)
    retries: dict[str, list[dict]] = {}  # goal_id → ATTEMPT_END 행들
    for row in rows:
        if row.get("kind") != "attempt":
            continue  # 틱 행 등은 무시
        if not row.get("goal_id"):
            warnings.append(f"goal_id 없는 {row.get('event')} 행 무시")  # 묶을 수 없다
            continue
        goal_id = str(row["goal_id"])  # 사례 이름 (문자열로 맞춘다)
        if row.get("event") == ls.ATTEMPT_END:
            retries.setdefault(goal_id, []).append(row)  # 재시도로 이어진 시도 끝
        elif row.get("event") == ls.GOAL_END:
            if goal_id in ends:
                warnings.append(f"goal {goal_id[:SHORT_ID]}: GOAL_END 중복 — 첫 행만 씀")
                continue
            ends[goal_id] = row  # 사례 1건
    for goal_id in retries:
        if goal_id not in ends:  # 끝 행 없이 시도만 있다 = 노드가 goal 도중 죽음
            warnings.append(f"goal {goal_id[:SHORT_ID]}: ATTEMPT_END 만 있고 GOAL_END 없음")
    cases: list[GoalCase] = []
    for goal_id, end in ends.items():
        case, case_warnings = _make_case(end, retries.get(goal_id, []))
        cases.append(case)
        warnings.extend(case_warnings)
    cases.sort(key=_sort_key)  # 끝난 시각 순서 = 회차 순서
    return cases, warnings


def parse_since(text: str) -> float:
    """본 측정 시작(선언) ISO 시각 → epoch 초. 시간대가 없으면 KST 로 본다."""
    moment = datetime.fromisoformat(text)  # 예: 2026-10-10T14:05:00
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)  # 현장 시계 = 한국 시각
    return moment.timestamp()  # ROS 시각(벽시계)과 같은 기준


# ---------------------------------------------------------------- 순수 함수: 판정·분류


def is_success(case: GoalCase) -> bool:
    """성공 = reason OK 이고 grasped true (g1-gate 1절, 영상 확인은 사람이)."""
    return case.reason == fsm.OK and case.grasped


def is_first_try_success(case: GoalCase) -> bool:
    """최초 시도 성공 = 성공이면서 attempts 1."""
    return is_success(case) and case.attempts == 1


def match_excludes(cases: list[GoalCase], prefixes: Iterable[str]) -> tuple[set[str], list[str]]:
    """--exclude goal_id(앞자리 허용) → 무효로 뺄 goal_id 집합."""
    chosen: set[str] = set()
    warnings: list[str] = []
    for prefix in prefixes:
        key = prefix.strip().lower()  # 대소문자 무시
        hits = [c.goal_id for c in cases if c.goal_id.lower().startswith(key)]  # 앞자리 일치
        if not key or not hits:
            warnings.append(f"--exclude {prefix!r}: 맞는 goal 없음")
        elif len(hits) > 1:
            warnings.append(f"--exclude {prefix!r}: goal {len(hits)}개와 겹침 — 더 길게 적을 것")
        else:
            chosen.add(hits[0])  # 정확히 하나만 무효로
    return chosen, warnings


def classify(
    cases: list[GoalCase], since_s: float | None, excluded: set[str], limit: int
) -> tuple[list[Row], int]:
    """사례 → 기록표 줄. (줄 목록, --since 전 연습 goal 수)."""
    rows: list[Row] = []
    practice = 0  # 선언 전 goal 수
    counted = 0  # 분모에 넣은 수
    for case in cases:
        if since_s is not None and (case.t_end_s is None or case.t_end_s < since_s):
            practice += 1  # 선언 전(또는 시각 모름) = 연습, 표에 넣지 않는다
            continue
        if case.goal_id in excluded:
            rows.append(Row("무효", INVALID, case))  # 무효도 표에 남긴다, 분모 칸은 쓰지 않는다
        elif counted < limit:
            counted += 1  # 분모 한 칸 채움
            rows.append(Row(str(counted), COUNTED, case))
        else:
            rows.append(Row("초과", OVER, case))  # 분모를 다 채운 뒤의 goal
    return rows, practice


def auto_hint(reason: str | None, cause: str) -> tuple[str, str]:
    """reason·cause → (g1-gate 원인 코드 힌트, 짧은 설명). 성공이면 ("", "")."""
    if reason == fsm.OK:
        return "", ""  # 성공은 힌트 없음 (grasped 는 따로 본다)
    if reason in (fsm.LOST, fsm.STALE_INPUT):
        return "L", "입력 상실(검출·pose 끊김)"
    if reason == fsm.OUT_OF_REACH:
        return "R", "도달 한계 — 추종이 늦었나 A·T 도 확인"
    if reason == fsm.GRASP_FAILED:
        if cause == "DROPPED":
            return "G", "들다 놓침 — T·G 확인"
        return "G", "못 잡음 — A·T 도 확인"  # NOT_DETECTED·WIDTH_OUT
    if reason == fsm.DEVICE_ERROR:
        if cause in ("INTERNAL_EXCEPTION", "NODE_SHUTDOWN"):
            return "X", "belt_servo 내부 예외·종료 — 실행 경로"
        if cause.startswith("STOP_"):
            return "D", "stop 응답 실패 — gateway 로그로 D·X 구분"
        return "D", "장치(그리퍼 등) — gateway 로그로 D·X 구분"
    if reason == fsm.CANCELED:
        return "?", "취소 — 누가 왜 취소했는지 확인"
    return "?", "알 수 없는 reason"


def row_hint(case: GoalCase) -> tuple[str, str]:
    """사례 하나의 힌트 (OK 인데 grasped false 같은 이상값도 표시)."""
    if case.reason == fsm.OK and not case.grasped:
        return "?", "OK 인데 grasped false — 로그 확인"
    return auto_hint(case.reason, case.cause)


def count_stats(rows: list[Row], practice: int) -> Stats:
    """기록표 줄 → 집계."""
    counted = [r.case for r in rows if r.status == COUNTED]  # 분모 안 사례
    failed = [c for c in counted if not is_success(c)]  # 분모 안 실패
    return Stats(
        counted=len(counted),
        success=sum(1 for c in counted if is_success(c)),
        first_try=sum(1 for c in counted if is_first_try_success(c)),
        invalid=sum(1 for r in rows if r.status == INVALID),
        over=sum(1 for r in rows if r.status == OVER),
        practice=practice,
        reasons=dict(Counter(str(c.reason) for c in counted)),
        hints=dict(Counter(row_hint(c)[0] or "?" for c in failed)),
    )


# ---------------------------------------------------------------- 순수 함수: 틱 요약


def _norm_mm(vec: Any) -> float | None:
    """[x, y, z] m → 길이 mm. 값이 비면 None."""
    if not isinstance(vec, list) or not vec:
        return None
    parts = [_as_float(v) for v in vec]  # null 섞임 확인
    if any(p is None for p in parts):
        return None
    return math.sqrt(sum(p * p for p in parts)) * 1000.0  # m → mm


def summarize_ticks(rows: Iterable[dict], goal_ids: set[str]) -> dict[str, TickSummary]:
    """틱 행 → goal_id 별 요약 (0 유지 틱 제외)."""
    per_goal: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("kind") != "tick" or row.get("goal_id") not in goal_ids:
            continue  # 관심 없는 goal
        if row.get("cause") == HOLD_CAUSE:
            continue  # goal 끝난 뒤 0 유지 구간은 빼고
        if _as_float(row.get("t_calc_s")) is None:
            continue  # 시각 없는 틱은 계산에 못 쓴다
        per_goal.setdefault(row["goal_id"], []).append(row)
    return {gid: _one_goal_ticks(ticks) for gid, ticks in per_goal.items()}


def _one_goal_ticks(ticks: list[dict]) -> TickSummary:
    """goal 하나의 틱 목록 → TickSummary."""
    ticks = sorted(ticks, key=lambda r: r["t_calc_s"])  # 시각 순
    track_s = 0.0  # TRACK 머문 시간
    for prev, nxt in zip(ticks, ticks[1:], strict=False):  # 이웃한 두 틱
        if prev.get("phase") == fsm.TRACK:
            track_s += nxt["t_calc_s"] - prev["t_calc_s"]  # 앞 틱 phase 로 구간을 센다
    errors = [_norm_mm(t.get("error_m")) for t in ticks if t.get("phase") == fsm.DESCEND]
    errors = [e for e in errors if e is not None]  # 계산된 값만
    return TickSummary(
        n_ticks=len(ticks),
        track_s=track_s,
        descend_max_err_mm=max(errors) if errors else None,
    )


# ---------------------------------------------------------------- 순수 함수: 렌더


def kst_hms(t: float | None) -> str:
    """ROS 시각(epoch 초) → KST HH:MM:SS."""
    if t is None:
        return "?"
    return datetime.fromtimestamp(t, KST).strftime("%H:%M:%S")


def md_cell(value: Any) -> str:
    """표 칸 문자열. None 은 빈칸, | 는 이스케이프."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")  # 표가 깨지지 않게


def md_row(cells: Iterable[Any]) -> str:
    """칸 목록 → Markdown 표 한 줄."""
    return "| " + " | ".join(md_cell(c) for c in cells) + " |"


def _ox(flag: bool) -> str:
    """참/거짓 → ○/×."""
    return "○" if flag else "×"


def _note(row: Row) -> str:
    """비고 칸: cause + 재시도 원인 + 상태 표시."""
    parts: list[str] = []
    if row.case.cause:
        parts.append(row.case.cause)  # 마지막 원인
    if row.case.retry_causes:
        parts.append("재시도: " + ",".join(c or "?" for c in row.case.retry_causes))
    if row.case.attempts_estimated:
        parts.append("attempts 추정")
    if row.status == INVALID:
        parts.append("무효(--exclude)")
    if row.status == OVER:
        parts.append("분모 밖(--limit 초과)")
    return " · ".join(parts)


def gate_cells(row: Row) -> list[str]:
    """기록표 한 줄의 칸 (GATE_COLUMNS 순서). 박스·원인·bag 시각은 사람이 채운다."""
    case = row.case
    return [
        row.label,  # #
        kst_hms(case.t_end_s),  # 시각 (GOAL_END)
        "",  # 박스(송장) — 사람
        "" if case.track_id is None else str(case.track_id),  # track_id
        case.reason or "",  # reason
        "" if case.attempts is None else str(case.attempts),  # attempts
        _ox(is_success(case)),  # 성공
        _ox(is_first_try_success(case)),  # 최초 시도 성공
        "",  # 원인 — 사람 (g1-gate 3절)
        "",  # bag 시각 — 사람
        _note(row),  # 비고
    ]


def total_cells(stats: Stats, limit: int) -> list[str]:
    """합계 줄 (g1-gate 표 마지막 줄 모양)."""
    cells = ["합계"] + [""] * (len(GATE_COLUMNS) - 1)  # 빈칸으로 채운 뒤
    cells[GATE_COLUMNS.index("성공")] = f"{stats.success}/{limit}"
    cells[GATE_COLUMNS.index("최초 시도 성공")] = f"{stats.first_try}/{limit}"
    cells[GATE_COLUMNS.index("비고")] = f"무효 {stats.invalid}회"
    return cells


def render_gate_table(rows: list[Row], stats: Stats, limit: int) -> str:
    """g1-gate 3절과 같은 열의 기록표."""
    lines = [md_row(GATE_COLUMNS), md_row(["---"] * len(GATE_COLUMNS))]  # 머리 + 구분선
    lines += [md_row(gate_cells(r)) for r in rows]  # 사례 줄
    lines.append(md_row(total_cells(stats, limit)))  # 합계 줄
    return "\n".join(lines)


def _fmt(value: float | None, digits: int) -> str:
    """숫자 → 문자열, 없으면 "-"."""
    return "-" if value is None else f"{value:.{digits}f}"


def hint_cells(row: Row, ticks: dict[str, TickSummary] | None) -> list[str]:
    """자동 힌트 표 한 줄 (HINT_COLUMNS 순서)."""
    case = row.case
    code, why = row_hint(case)  # g1 코드 힌트
    tick = ticks.get(case.goal_id) if ticks is not None else None  # 틱 요약 (없을 수 있음)
    return [
        row.label,
        case.goal_id[:SHORT_ID],  # --exclude 에 이 앞자리를 쓴다
        case.reason or "",
        case.cause,
        f"{code} {why}".strip(),
        case.phase or "",
        ",".join(c or "?" for c in case.retry_causes),
        _fmt(tick.track_s, 2) if tick else "-",
        _fmt(tick.descend_max_err_mm, 1) if tick else "-",
    ]


def render_hint_table(rows: list[Row], ticks: dict[str, TickSummary] | None) -> str:
    """자동 힌트 표 (원인 판정 보조, 측정 기록표와 따로)."""
    lines = [md_row(HINT_COLUMNS), md_row(["---"] * len(HINT_COLUMNS))]
    lines += [md_row(hint_cells(r, ticks)) for r in rows]
    return "\n".join(lines)


def distinct(values: Iterable[Any]) -> list[str]:
    """None 을 뺀 서로 다른 값 (처음 나온 순서)."""
    seen: list[str] = []
    for value in values:
        text = None if value is None else str(value)
        if text is not None and text not in seen:
            seen.append(text)
    return seen


def joined(values: list[str], width: int | None = None) -> str:
    """값 목록 → 한 칸 문자열. 없으면 ____, 여러 개면 / 로 잇는다."""
    if not values:
        return BLANK
    cut = [v[:width] if width else v for v in values]  # sha 는 앞자리만
    return "/".join(cut)


def belt_text(belt_label: str, speeds_mps: list[str]) -> str:
    """벨트 표기 "h250(4.77 cm/s)" 모양. 속도는 로그 belt_speed_mps(m/s) 를 cm/s 로."""
    if not speeds_mps:
        return f"{belt_label}(__ cm/s)"
    cmps = "/".join(f"{float(s) * 100.0:.2f}" for s in speeds_mps)  # m/s → cm/s
    return f"{belt_label}({cmps} cm/s)"


def percent(part: int, whole: int) -> str:
    """정수 백분율 문자열 (분모 0 이면 __)."""
    return "__" if whole == 0 else f"{round(100.0 * part / whole)}"


def measurement_sentence(stats: Stats, belt: str, main_hash: str, params_sha: str) -> str:
    """g1-gate 5절 "측정:" 문장을 채운다."""
    return (
        f"- 측정: {stats.counted}사례 중 {stats.success}회 성공"
        f"({percent(stats.success, stats.counted)} %), "
        f"최초 시도 성공 {stats.first_try}회, 무효 {stats.invalid}회. "
        f"벨트 {belt}, main {main_hash}, belt_servo 파라미터 sha {params_sha} "
        f"(measurements-1010 #__)"
    )


def header_line(series: str, rows: list[Row], main_hash: str, params_sha: str) -> str:
    """g1-gate 3절 표 위 한 줄 (시작 시각 = 첫 분모 사례가 끝난 시각)."""
    first = next((r.case for r in rows if r.status == COUNTED), None)  # 1번 사례
    start = kst_hms(first.t_end_s) if first else BLANK
    return (
        f"시리즈: `{series}` · 시작 시각 {start} · main {main_hash} · "
        f"belt_servo 파라미터 sha {params_sha} · goal 경로(sort_manager / 시험 도구) {BLANK}"
    )


def _dist_text(counts: dict[str, int]) -> str:
    """{"L": 2, "G": 1} → "G 1 · L 2" (없으면 "없음")."""
    if not counts:
        return "없음"
    return " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))


@dataclass(frozen=True)
class Meta:
    """요약에 넣는 설정·실행 정보."""

    series: str  # 시리즈 이름 (s1)
    limit: int  # 분모 (20)
    main_hash: str  # main 커밋 해시
    belt_label: str  # 아두이노 벨트 설정 (h250)
    since_text: str | None  # --since 원문


def summary_lines(cases: list[GoalCase], stats: Stats, meta: Meta) -> list[str]:
    """요약 문단 줄들."""
    params = distinct(c.params_sha256 for c in cases)  # 섞이면 고정 조건 위반
    configs = distinct(c.config_sha256 for c in cases)
    versions = distinct(c.config_version for c in cases)
    speeds = distinct(c.belt_speed_mps for c in cases)
    need = math.ceil(GATE_RATIO * meta.limit - 1e-9)  # 20 → 14
    lines = [
        measurement_sentence(
            stats, belt_text(meta.belt_label, speeds), meta.main_hash, joined(params, SHORT_SHA)
        ),
        "- 실패 원인: A __ · T __ · G __ · R __ · L __ · D __ · X __ · S __ "
        "(원인 열을 사람이 판정한 뒤 채운다)",
        f"- 자동 힌트 분포(실패 {stats.counted - stats.success}건, 원인 아님): {_dist_text(stats.hints)}",
        f"- reason 분포: {_dist_text(stats.reasons)}",
        f"- 게이트 기준: {meta.limit}사례 중 {need} 이상 — 현재 성공 {stats.success}, "
        f"분모 {stats.counted}/{meta.limit}",
        f"- 설정: config_version {joined(versions)} · config_sha256 {joined(configs)} · "
        f"params_sha256 {joined(params)}",
        f"- 분모 밖: 선언 전(연습) {stats.practice}건"
        f"{' (--since ' + meta.since_text + ')' if meta.since_text else ''} · "
        f"--limit 초과 {stats.over}건",
    ]
    return lines


def check_warnings(cases: list[GoalCase], stats: Stats, limit: int) -> list[str]:
    """집계 결과에서 사람이 봐야 할 점."""
    warnings: list[str] = []
    if not cases:
        warnings.append("GOAL_END 행이 없다 — 입력 파일·log_dir 확인")
    if stats.counted < limit:
        warnings.append(f"분모 미달 {stats.counted}/{limit} (측정 중이면 정상)")
    for name in ("params_sha256", "config_sha256", "belt_speed_mps"):
        values = distinct(getattr(c, name) for c in cases)  # 사례마다 같은가
        if len(values) > 1:
            warnings.append(f"{name} 값이 섞임 {values} — 고정 조건이 바뀌었으면 새 시리즈")
    return warnings


def render_report(
    rows: list[Row],
    cases: list[GoalCase],
    stats: Stats,
    meta: Meta,
    ticks: dict[str, TickSummary] | None,
    warnings: list[str],
) -> str:
    """measurements 에 붙일 Markdown 전체."""
    params = joined(distinct(c.params_sha256 for c in cases), SHORT_SHA)
    parts = [
        f"### G1 회차 기록 — 시리즈 {meta.series} (gate_summary 자동 집계)",
        "",
        header_line(meta.series, rows, meta.main_hash, params),
        "",
        render_gate_table(rows, stats, meta.limit),
        "",
        "**원인 열은 사람이 영상·로그로 판정해 채운다**(g1-gate 3절). 성공 ○ 도 영상에서 박스가 "
        "안전 높이까지 들렸는지 사람이 확인한다.",
        "",
        "**요약**",
        "",
        *summary_lines(cases, stats, meta),
        "",
        "**자동 힌트**(reason·cause 기반 보조, 원인 판정 아님)",
        "",
        render_hint_table(rows, ticks),
    ]
    if warnings:
        parts += ["", "**집계 경고**", "", *[f"- {w}" for w in warnings]]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- I/O


def find_files(paths: Iterable[str], subdir: str, pattern: str) -> list[Path]:
    """파일은 그대로, 폴더는 그 안과 <폴더>/<subdir> 안의 pattern 파일."""
    found: list[Path] = []
    for text in paths:
        path = Path(text).expanduser()
        if path.is_file():
            found.append(path)  # 파일 직접 지정
        elif path.is_dir():
            found += sorted(path.glob(pattern))  # attempts 폴더를 줬을 때
            found += sorted((path / subdir).glob(pattern))  # log.dir 을 줬을 때
    unique: list[Path] = []
    for path in found:
        if path.resolve() not in [u.resolve() for u in unique]:
            unique.append(path)  # 같은 파일 두 번 읽지 않게
    return unique


def read_rows(files: list[Path]) -> tuple[list[dict], list[str]]:
    """여러 jsonl 파일 → 행 목록 + 경고."""
    rows: list[dict] = []
    warnings: list[str] = []
    for path in files:
        with path.open(encoding="utf-8", errors="replace") as handle:  # 한 줄씩 읽는다
            file_rows, file_warnings = parse_lines(handle, path.name)
        rows += file_rows
        warnings += file_warnings
    return rows, warnings


def git_short_head() -> str | None:
    """이 소스가 있는 레포의 `git rev-parse --short HEAD` (실패하면 None)."""
    here = Path(__file__).resolve().parent  # symlink-install 이면 src 쪽으로 풀린다
    for cwd in (here, Path.cwd()):  # 소스 폴더 → 실행 폴더 순서
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            continue  # git 없음·레포 아님
        return out.stdout.strip() or None
    return None


def append_md(path: Path, text: str) -> None:
    """--md 파일 끝에 붙인다 (없으면 만든다, 기존 내용은 지우지 않는다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gap = "\n" if path.exists() and path.stat().st_size > 0 else ""  # 앞 내용과 한 줄 띄움
    with path.open("a", encoding="utf-8") as handle:
        handle.write(gap + text)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """명령줄 인자."""
    parser = argparse.ArgumentParser(
        prog="gate_summary", description="belt_servo 시도 로그 → G1 회차 기록표·요약 (Markdown)"
    )
    parser.add_argument("inputs", nargs="+", help="attempts jsonl 파일, attempts 폴더 또는 log.dir")
    parser.add_argument(
        "--since", help='"본 측정 시작" 시각 ISO (예: 2026-10-10T14:05, 시간대 없으면 KST)'
    )
    parser.add_argument("--limit", type=int, default=20, help="분모 (기본 20)")
    parser.add_argument("--series", default="s1", help="시리즈 이름 (기본 s1)")
    parser.add_argument(
        "--exclude", action="append", default=[], help="무효로 뺄 goal_id (앞 8자리 이상, 여러 번)"
    )
    parser.add_argument("--ticks", nargs="+", help="틱 jsonl 파일·ticks 폴더·log.dir (선택)")
    parser.add_argument("--md", help="이 파일 끝에 결과를 붙인다 (예: docs/measurements-1010.md)")
    parser.add_argument("--main", help="main 커밋 해시 (없으면 git rev-parse --short HEAD)")
    parser.add_argument("--belt", default="h250", help="아두이노 벨트 설정 표기 (기본 h250)")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit 은 1 이상")
    if args.since:
        try:
            args.since_s = parse_since(args.since)  # 형식을 여기서 확인
        except ValueError:
            parser.error(f"--since 형식 오류: {args.since!r} (예: 2026-10-10T14:05)")
    else:
        args.since_s = None
    return args


def load_ticks(paths: list[str] | None, goal_ids: set[str]) -> tuple[dict | None, list[str]]:
    """--ticks 가 있으면 틱 요약, 없으면 None."""
    if not paths:
        return None, []
    files = find_files(paths, "ticks", "servo_ticks_*.jsonl")
    if not files:
        return {}, [f"--ticks {paths}: 틱 파일 없음"]
    rows, warnings = read_rows(files)  # 30 Hz 로그라 크다 — 한 번만 읽는다
    return summarize_ticks(rows, goal_ids), warnings


def main(argv: list[str] | None = None) -> int:
    """명령 실행. 종료 코드 0 = 정상, 2 = 입력 파일 없음."""
    args = parse_args(argv)
    files = find_files(args.inputs, "attempts", "servo_attempts_*.jsonl")
    if not files:
        print(f"gate_summary: 시도 로그 파일 없음: {args.inputs}", file=sys.stderr)
        return 2
    raw, warnings = read_rows(files)  # 깨진 줄은 경고로
    cases, case_warnings = collect_cases(raw)
    excluded, ex_warnings = match_excludes(cases, args.exclude)
    rows, practice = classify(cases, args.since_s, excluded, args.limit)
    stats = count_stats(rows, practice)
    shown = {r.case.goal_id for r in rows}  # 표에 나온 goal 만 틱 요약
    ticks, tick_warnings = load_ticks(args.ticks, shown)
    meta = Meta(
        series=args.series,
        limit=args.limit,
        main_hash=args.main or git_short_head() or BLANK,
        belt_label=args.belt,
        since_text=args.since,
    )
    warnings = warnings + case_warnings + ex_warnings + tick_warnings
    warnings += check_warnings([r.case for r in rows], stats, args.limit)
    report = render_report(rows, [r.case for r in rows], stats, meta, ticks, warnings)
    print(report, end="")  # 화면에 그대로
    for line in warnings:
        print(f"gate_summary 경고: {line}", file=sys.stderr)  # 경고는 stderr 에도
    if args.md:
        append_md(Path(args.md).expanduser(), report)
        print(f"gate_summary: {args.md} 끝에 붙임", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
