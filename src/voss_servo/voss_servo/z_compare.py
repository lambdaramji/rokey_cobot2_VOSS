"""z 프로파일 비교표 — p(P 제어) 와 trapezoid(사다리꼴) 시도의 단계 시간·착지를 나란히 (S2-T14).

T29 실기 "끄고 5회(s4a) + 켜고 5회(s4b)" 를 한 표로 뽑는다 (design/S2T14-run.md).
  ros2 run voss_servo z_compare <log.dir>/attempts --ticks <log.dir>/ticks
- 입력 규칙은 gate_summary 와 같다(파일·attempts 폴더·log.dir). 틱은 선택(착지 z·err_along 용).
- 단계 시간·착지·err_along 은 reason OK 인 goal 만 센다. 실패 goal 은 reason 별 개수만 (S2T14-dd 4절).
- 총 시간 = GOAL_END t_calc − 같은 goal 의 첫 ATTEMPT_END 의 PREPARE 진입 (재시도 goal 도 goal 시작부터).
- z_profile 키가 없는 옛 로그(10/12 이전)는 p 로 본다.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field

from voss_servo import log_schema as ls
from voss_servo.gate_summary import find_files, read_rows

PHASES = ("PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY")  # 표준 단계 순서
LAND_MIN_MM = 80.0  # 착지 z 가 이보다 낮으면 되돌림 조건 (S2T14-run.md)
PROFILE_ORDER = ("p", "trapezoid")  # 표 열 순서


@dataclass
class Stats:
    """프로파일 하나의 집계."""

    goals: int = 0  # GOAL_END 수
    ok: int = 0  # reason OK 수
    reasons: Counter = field(default_factory=Counter)  # reason 별 수
    retried: int = 0  # 시도 2회 이상인 OK goal 수
    phase_s: dict[str, list[float]] = field(default_factory=dict)  # 단계 → OK goal 시간들
    total_s: list[float] = field(default_factory=list)  # OK goal 총 시간들
    land_mm: list[float] = field(default_factory=list)  # 착지 − 목표 (mm)
    land_z_mm: list[float] = field(default_factory=list)  # 착지 z 절대값 (mm)
    err_along_mm: list[float] = field(default_factory=list)  # GRASP 진입 벨트 방향 오차
    clamped_ticks: int = 0  # DESCEND 중 clamp 로 잘린 틱 수 합


# ---------------------------------------------------------------- 순수 함수


def profile_of(row: dict) -> str:
    """행의 z 프로파일. 키가 없으면(옛 로그) p."""
    return row.get("z_profile") or "p"


def first_starts(rows: list[dict]) -> dict[str, float]:
    """goal_id → 첫 ATTEMPT_END 의 PREPARE 진입 시각 (= goal 시작)."""
    out: dict[str, float] = {}
    for r in rows:
        if r.get("event") != ls.ATTEMPT_END or r.get("goal_id") is None:
            continue
        t = r.get("phase_t_prepare_s")
        if t is not None and r["goal_id"] not in out:  # 파일 순서 = 시간 순서
            out[r["goal_id"]] = float(t)
    return out


def phase_durations(row: dict) -> dict[str, float | None]:
    """GOAL_END 한 행 → 단계별 시간 s (마지막 시도 기준). 진입 안 한 단계는 None."""
    t = [row.get(ls.PHASE_T_KEYS[p]) for p in PHASES]  # 단계 진입 시각
    out: dict[str, float | None] = {}
    for i, phase in enumerate(PHASES):
        if t[i] is None:
            out[phase] = None  # 이 단계에 안 들어갔다
            continue
        nxt = next((x for x in t[i + 1 :] if x is not None), None)  # 다음으로 들어간 단계
        end = nxt if nxt is not None else row.get("t_calc_s")  # 마지막 단계는 goal 끝까지
        out[phase] = float(end) - float(t[i]) if end is not None else None
    return out


def landing(goal_ticks: list[dict]) -> tuple[float, float] | None:
    """(착지 z, 목표 z) mm. 목표 = DESCEND 마지막 틱 목표 z, 착지 = GRASP 동안 pose z 최소."""
    desc = [r for r in goal_ticks if r.get("phase") == "DESCEND" and r.get("tcp_target_m")]
    grasp = [r for r in goal_ticks if r.get("phase") == "GRASP" and r.get("tcp_pose_m")]
    if not desc or not grasp:
        return None
    target = float(desc[-1]["tcp_target_m"][2])
    low = min(float(r["tcp_pose_m"][2]) for r in grasp)  # 가장 낮게 내려간 높이
    return low * 1000.0, target * 1000.0


def tick_facts(goal_ticks: list[dict]) -> tuple[float | None, int]:
    """(GRASP 첫 틱 err_along mm, DESCEND clamped 틱 수)."""
    first = next((r for r in goal_ticks if r.get("phase") == "GRASP"), None)
    along = first.get("err_along_m") if first else None
    clamped = sum(1 for r in goal_ticks if r.get("phase") == "DESCEND" and r.get("clamped"))
    return (float(along) * 1000.0 if along is not None else None), clamped


def summarize(rows: list[dict], ticks_by_goal: dict[str, list[dict]] | None) -> dict[str, Stats]:
    """시도 행 (+ goal 별 틱) → 프로파일별 Stats."""
    starts = first_starts(rows)
    out: dict[str, Stats] = {}
    for end in (r for r in rows if r.get("event") == ls.GOAL_END):
        st = out.setdefault(profile_of(end), Stats())
        st.goals += 1
        reason = end.get("reason") or "?"
        st.reasons[reason] += 1
        if reason != "OK":
            continue  # 실패는 개수만 (실패까지의 시간이 단계 중앙값에 섞이지 않게)
        st.ok += 1
        st.retried += 1 if (end.get("attempt") or 0) > 1 else 0
        for phase, sec in phase_durations(end).items():
            if sec is not None:
                st.phase_s.setdefault(phase, []).append(sec)
        start = starts.get(end.get("goal_id"), end.get("phase_t_prepare_s"))
        if start is not None and end.get("t_calc_s") is not None:
            st.total_s.append(float(end["t_calc_s"]) - float(start))
        goal_ticks = (ticks_by_goal or {}).get(end.get("goal_id"), [])
        land = landing(goal_ticks)
        if land is not None:
            st.land_z_mm.append(land[0])
            st.land_mm.append(land[0] - land[1])
        along, clamped = tick_facts(goal_ticks)
        if along is not None:
            st.err_along_mm.append(along)
        st.clamped_ticks += clamped
    return out


def _mid(xs: list[float], digits: int = 2) -> str:
    """중앙값 [최소~최대] 문자열. 없으면 —."""
    if not xs:
        return "—"
    return f"{statistics.median(xs):.{digits}f} [{min(xs):.{digits}f}~{max(xs):.{digits}f}]"


def _diff(a: list[float], b: list[float]) -> str:
    """중앙값 차이 (trapezoid − p)."""
    if not a or not b:
        return "—"
    return f"{statistics.median(b) - statistics.median(a):+.2f}"


def format_md(stats: dict[str, Stats]) -> str:
    """프로파일별 표 (행 = 항목, 열 = p · trapezoid · 차이)."""
    cols = [p for p in PROFILE_ORDER if p in stats] + [p for p in stats if p not in PROFILE_ORDER]
    empty = Stats()
    p, t = stats.get("p", empty), stats.get("trapezoid", empty)
    lines = ["| 항목 | " + " | ".join(cols) + " | 차이 (trapezoid − p) |"]
    lines.append("|---" * (len(cols) + 2) + "|")

    def row(name: str, cells: list[str], diff: str = "") -> None:
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {diff} |")

    row("goal / OK", [f"{stats[c].goals} / {stats[c].ok}" for c in cols])
    row(
        "실패 reason",
        [
            ", ".join(f"{k} {v}" for k, v in stats[c].reasons.items() if k != "OK") or "—"
            for c in cols
        ],
    )
    row("재시도한 OK goal", [str(stats[c].retried) for c in cols])
    for phase in PHASES:
        cells = [_mid(stats[c].phase_s.get(phase, [])) for c in cols]
        row(f"{phase} s", cells, _diff(p.phase_s.get(phase, []), t.phase_s.get(phase, [])))
    row("총 시간 s", [_mid(stats[c].total_s) for c in cols], _diff(p.total_s, t.total_s))
    row("착지 − 목표 mm", [_mid(stats[c].land_mm) for c in cols], _diff(p.land_mm, t.land_mm))
    row("착지 z mm", [_mid(stats[c].land_z_mm, 1) for c in cols])
    row(
        f"착지 z < {LAND_MIN_MM:g} mm (되돌림)",
        [str(sum(z < LAND_MIN_MM for z in stats[c].land_z_mm)) for c in cols],
    )
    row("GRASP 진입 err_along mm", [_mid(stats[c].err_along_mm) for c in cols])
    row("DESCEND clamp 틱 합", [str(stats[c].clamped_ticks) for c in cols])
    return "\n".join(lines)


def group_ticks(rows: list[dict], goal_ids: set[str]) -> dict[str, list[dict]]:
    """틱 행 → goal 별 목록 (시각 순)."""
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("kind") == "tick" and r.get("goal_id") in goal_ids:
            out.setdefault(r["goal_id"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r.get("t_calc_s") or 0.0)
    return out


# ---------------------------------------------------------------- 명령


def main(argv: list[str] | None = None) -> int:
    """종료 코드 0 = 정상, 2 = 시도 로그 없음."""
    ap = argparse.ArgumentParser(prog="z_compare", description="z 프로파일별 단계 시간·착지 비교")
    ap.add_argument("inputs", nargs="+", help="attempts jsonl 파일, attempts 폴더 또는 log.dir")
    ap.add_argument("--ticks", nargs="+", help="틱 jsonl 파일·ticks 폴더·log.dir (선택)")
    args = ap.parse_args(argv)
    files = find_files(args.inputs, "attempts", "servo_attempts_*.jsonl")
    if not files:
        print(f"z_compare: 시도 로그 파일 없음: {args.inputs}", file=sys.stderr)
        return 2
    rows, warnings = read_rows(files)
    ticks_by_goal: dict[str, list[dict]] | None = None
    if args.ticks:
        goal_ids = {
            r["goal_id"] for r in rows if r.get("event") == ls.GOAL_END and r.get("goal_id")
        }
        tick_rows, tick_warnings = read_rows(find_files(args.ticks, "ticks", "servo_ticks_*.jsonl"))
        ticks_by_goal = group_ticks(tick_rows, goal_ids)
        warnings += tick_warnings
    print(format_md(summarize(rows, ticks_by_goal)))
    for w in warnings:
        print(f"경고: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
