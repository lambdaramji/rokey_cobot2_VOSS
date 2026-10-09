"""sim_check — fake_box + robot_gateway dry_run 시뮬로 TrackAndGrasp 를 끝까지 돌리고 자동 판정 (sim 전용).

- 설계: design/U3-dd.md 6절, pseudo 5~7절. 절차: design/U3-run.md (B).
- 한 case = sim.launch 한 번 기동 → goal 1개 → 정리 → 판정. dry_run 가짜 로봇은 goal 뒤 제자리에 남으므로
  case 마다 새로 띄운다 (U3 사전 실험).
- 안전: 시작 전 ROS_DOMAIN_ID 30(실로봇 도메인)·이미 떠 있는 gateway 를 거부하고(J0), 띄운 gateway 가
  dry_run 이 아니면 goal 을 보내지 않고 바로 끈다(J10). sim.launch 는 dry_run 을 "true" 로 고정한다.
- 종료 코드: 0 = 전부 통과 · 1 = 하나라도 불일치 · 2 = 판정 불가(자료 없음·시간 초과·사전 점검 거부).

판정 함수(judge_* 등)는 ROS 를 쓰지 않는 순수 함수다 (test/test_sim_check.py).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------- 표·상수 (DD 6.2·6.3·6.4)

SUCCEEDED, CANCELED, ABORTED = 4, 5, 6  # action_msgs/GoalStatus
PHASES = ("PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY")  # 표준 순서


@dataclass(frozen=True)
class Case:
    """한 시험 경우: fake_box 시나리오 · gateway 물체 폭 · cancel 시각."""

    name: str
    scenario: str
    object_mm: float
    cancel_after_s: float | None = None


CASES: dict[str, Case] = {
    "lost": Case("lost", "lost_after_s", 40.5),
    "invalid": Case("invalid", "invalid_after_s", 40.5),
    "cancel": Case("cancel", "normal", 40.5, 3.0),
    "normal": Case("normal", "normal", 40.5),
    "two_boxes": Case("two_boxes", "two_boxes", 40.5),
    "empty": Case("empty", "normal", 0.0),  # 가짜 RG2 빈손 (U5 뒤)
}


@dataclass(frozen=True)
class Expect:
    """case 기대값. phases_exact 가 있으면 그 목록과 같아야, 없으면 표준 순서의 앞부분이면 된다."""

    status: int
    reason: str
    cause: str
    grasped: bool
    phases_exact: tuple[str, ...] | None = None
    phases_last: str | None = None  # 앞부분 규칙일 때 마지막 phase (없으면 무엇이든)


EXPECT: dict[tuple[str, str], Expect] = {
    # U5 전 (지금 main): PREPARE 를 못 벗어난다 (fsm.py:237)
    ("pre_u5", "lost"): Expect(ABORTED, "LOST", "BOX_MISSING", False, ("PREPARE",)),
    ("pre_u5", "invalid"): Expect(ABORTED, "STALE_INPUT", "BOX_INVALID", False, ("PREPARE",)),
    ("pre_u5", "cancel"): Expect(CANCELED, "CANCELED", "STOP_OK", False, ("PREPARE",)),
    ("pre_u5", "normal"): Expect(ABORTED, "OUT_OF_REACH", "REACH_X_MAX", False, ("PREPARE",)),
    ("pre_u5", "two_boxes"): Expect(ABORTED, "OUT_OF_REACH", "REACH_X_MAX", False, ("PREPARE",)),
    # U5 뒤 (U5 설계를 읽고 쓴 기대값 — U5 머지 뒤 실제로 확인, 다르면 U5 PR 에서 고친다)
    ("grasp", "normal"): Expect(SUCCEEDED, "OK", "", True, PHASES),
    ("grasp", "empty"): Expect(ABORTED, "GRASP_FAILED", "NOT_DETECTED", False, None, "GRASP"),
    ("grasp", "cancel"): Expect(CANCELED, "CANCELED", "STOP_OK", False),
}
PROFILE_CASES: dict[str, tuple[str, ...]] = {
    "pre_u5": ("lost", "invalid", "cancel", "normal", "two_boxes"),
    "grasp": ("normal", "empty", "cancel"),
}

# 허용치 (사전 실험 실측: Δt 33.3 ms, watchdog 종료 뒤 0.71 s, hold 15틱 0.5 s)
PERIOD_NOMINAL_MS = 1000.0 / 30.0
PERIOD_TOL_MS = 3.0
WATCHDOG_DELAY_S = (0.6, 0.9)
TRACK_LOCK_TOL_M = 0.005
FOLLOW_MIN_TICKS = 30
ZERO_EPS = 1e-9

# 대기 상한 (s)
DISCOVERY_S = 2.0  # 그래프 탐색
GRAPH_CLEAR_S = 10.0  # 앞 case 노드가 그래프에서 사라질 때까지
GW_START_S = 15.0  # gateway 시작 줄
SERVO_READY_S = 20.0  # belt_servo READY 줄
SERVER_S = 20.0  # 액션 서버
FIRST_BOX_S = 5.0  # 이번 case 의 첫 박스 메시지
ACCEPT_S = 5.0  # goal 수락
SETTLE_S = 8.0  # watchdog 줄, 그 뒤 통계 줄 (통계는 5 s 마다)
STOP_S = 15.0  # launch 종료 (launch 자체가 SIGTERM 5 s + SIGKILL 5 s 로 단계적 종료)

REAL_DOMAIN = "30"  # 공용 PC·실로봇 도메인
SIM_NODES = ("robot_gateway", "belt_servo", "fake_box")

# gateway 로그 패턴 (robot_gateway.py 문구 기준 — 바뀌면 여기만 고친다, DD 6.8)
TS = r"\[(\d+\.\d+)\] \[robot_gateway\]: "
GW_STARTED = re.compile(r"robot_gateway started: (\S+)")  # 첫 단어 dry_run | real (:239)
GW_WATCHDOG = re.compile(TS + r"servo_cmd 끊김\(watchdog\)")  # :849
GW_STOP = re.compile(TS + r"/voss/robot/stop → (\S+)")  # :885
GW_STATS = re.compile(  # :421, 5 s 마다, 찍을 때마다 0 으로 리셋
    TS + r"servo rx .*watchdog (\d+), stop (\d+), move_stop (\d+) ok / (\d+) fail"
)
SERVO_READY = re.compile(r"\[belt_servo\]: READY$")
SERVO_REFUSED = re.compile(r"\[belt_servo\]: READY 거부")


# ---------------------------------------------------------------- 판정 결과


@dataclass(frozen=True)
class Verdict:
    """판정 하나. status ∈ PASS · FAIL · UNKNOWN(자료가 있어야 하는데 없음)."""

    id: str
    item: str
    expected: str
    actual: str
    status: str


def _v(vid: str, item: str, ok: bool, expected: str, actual: str) -> Verdict:
    """참/거짓 → PASS/FAIL 판정."""
    return Verdict(vid, item, expected, actual, "PASS" if ok else "FAIL")


def _unknown(vid: str, item: str, expected: str, why: str) -> Verdict:
    """판정 불가."""
    return Verdict(vid, item, expected, why, "UNKNOWN")


@dataclass
class GatewayFacts:
    """launch.log 에서 읽은 gateway 사실 (시각은 ROS 시각 초)."""

    mode: str | None = None  # 시작 줄 첫 단어
    watchdogs: list[float] = field(default_factory=list)
    stops: list[tuple[float, str]] = field(default_factory=list)  # (시각, 결과)
    stats: list[tuple[float, int, int, int, int]] = field(default_factory=list)
    # (시각, watchdog, stop, move_stop ok, move_stop fail)


# ---------------------------------------------------------------- 순수 판정 함수 (DD 6.9)


def norm(v: Any) -> float | None:
    """벡터 길이 (None 이면 None)."""
    return None if v is None else math.sqrt(sum(float(x) * float(x) for x in v))


def select_goal_rows(rows: list[dict], goal_id: str | None) -> list[dict]:
    """이 goal 의 행만."""
    return [r for r in rows if goal_id and r.get("goal_id") == goal_id]


def split_goal_ticks(ticks: list[dict]) -> tuple[list[dict], dict | None, list[dict]]:
    """goal 틱 → (진행 틱, 종료 틱, 0 유지 틱). 종료 틱이 없으면 (전부, None, [])."""
    ticks = sorted(ticks, key=lambda r: r.get("t_pub_s") or 0.0)  # 시각 순
    idx = next((i for i, r in enumerate(ticks) if r.get("terminal")), None)
    if idx is None:
        return ticks, None, []
    hold = [r for r in ticks[idx + 1 :] if r.get("cause") == "ZERO_HOLD"]  # 종료 뒤 0 유지
    return ticks[:idx], ticks[idx], hold


def judge_result(exp: Expect, status: int, reason: str, grasped: bool) -> Verdict:
    """J1: result status·reason·grasped."""
    want = f"{exp.status}/{exp.reason}/grasped={exp.grasped}"
    got = f"{status}/{reason}/grasped={grasped}"
    ok = status == exp.status and reason == exp.reason and grasped == exp.grasped
    return _v("J1", "result", ok, want, got)


def judge_cause(exp: Expect, goal_end: dict | None) -> Verdict:
    """J2: 시도 로그 GOAL_END 의 cause."""
    if goal_end is None:
        return _unknown("J2", "cause", repr(exp.cause), "GOAL_END 행 없음")
    got = goal_end.get("cause")
    return _v("J2", "cause", got == exp.cause, repr(exp.cause), repr(got))


def judge_phases(exp: Expect, phases: list[str]) -> Verdict:
    """J3: feedback phase 열 (정확히 같거나, 표준 순서의 앞부분)."""
    is_prefix = list(phases) == list(PHASES[: len(phases)])  # 순서를 건너뛰거나 바꾸지 않음
    if exp.phases_exact is not None:
        ok, want = list(phases) == list(exp.phases_exact), f"= {list(exp.phases_exact)}"
    else:
        last_ok = exp.phases_last is None or (bool(phases) and phases[-1] == exp.phases_last)
        ok = is_prefix and last_ok
        want = "표준 순서의 앞부분" + (f", 마지막 {exp.phases_last}" if exp.phases_last else "")
    return _v("J3", "phases", ok, want, str(list(phases)))


def judge_last_zero(terminal: dict | None) -> Verdict:
    """J4: 종료 틱의 명령이 0."""
    if terminal is None:
        return _unknown("J4", "마지막 cmd 0", "0", "종료 틱 없음")
    n = norm(terminal.get("cmd_vel_mps"))
    ok = n is not None and n <= ZERO_EPS
    return _v("J4", "마지막 cmd 0", ok, "0 mm/s", "없음" if n is None else f"{n * 1000:.3f} mm/s")


def judge_zero_hold(
    terminal: dict | None, hold: list[dict], zero_hold_s: float, rate_hz: float
) -> Verdict:
    """J5: 종료 뒤 zero_hold_s 동안 0 을 계속 보냈다."""
    need_n = round(zero_hold_s * rate_hz) - 1  # 0.5 s·30 Hz → 14틱 이상
    want = f"≥ {need_n}틱 · ≥ {zero_hold_s - 1 / rate_hz:.3f} s · 전부 0"
    if terminal is None:
        return _unknown("J5", "0 유지", want, "종료 틱 없음")
    all_zero = all((norm(r.get("cmd_vel_mps")) or 0.0) <= ZERO_EPS for r in hold)
    span = (hold[-1]["t_pub_s"] - terminal["t_pub_s"]) if hold else 0.0
    ok = all_zero and len(hold) >= need_n and span >= zero_hold_s - 1 / rate_hz
    return _v("J5", "0 유지", ok, want, f"{len(hold)}틱 · {span:.3f} s · 전부 0={all_zero}")


def judge_period(ticks: list[dict]) -> Verdict:
    """J6: 틱 발행 간격 평균 33.3 ± 3 ms."""
    t = sorted(r["t_pub_s"] for r in ticks if r.get("t_pub_s") is not None)
    want = f"{PERIOD_NOMINAL_MS:.1f} ± {PERIOD_TOL_MS:g} ms"
    if len(t) < 2:
        return _unknown("J6", "주기", want, f"틱 {len(t)}개")
    dts = [(b - a) * 1000.0 for a, b in zip(t, t[1:], strict=False)]
    mean = sum(dts) / len(dts)
    ok = abs(mean - PERIOD_NOMINAL_MS) <= PERIOD_TOL_MS
    return _v("J6", "주기", ok, want, f"{mean:.1f} ms (최소 {min(dts):.1f}, 최대 {max(dts):.1f})")


def judge_follow(progress: list[dict], align_along_m: float) -> Verdict:
    """J11: PREPARE 추종 — 상류로 돌진하지 않고, 필드가 채워지고, 박스가 상류가 아니면 움직인다."""
    want = "보이는 틱 모두 벨트방향≥0 · 필드 채움 · (박스 상류 아님 → cmd≠0)"
    rows = [r for r in progress if r.get("visible") and not r.get("stopping")]
    rows = [r for r in rows if not r.get("terminal")]
    if len(rows) < FOLLOW_MIN_TICKS:
        return _unknown("J11", "추종", want, f"보이는 틱 {len(rows)}개 < {FOLLOW_MIN_TICKS}")
    bad: list[str] = []
    for r in rows:
        c, b = r.get("cmd_vel_mps"), r.get("belt_vel_mps")
        if c is None or b is None or None in (r.get(k) for k in ("tcp_now_m", "predicted_m")):
            bad.append("빈 필드")
            continue
        if r.get("error_m") is None:
            bad.append("빈 필드")
            continue
        bn = norm(b) or 1.0
        along = sum(float(ci) * float(bi) for ci, bi in zip(c, b, strict=False)) / bn
        if along < -1e-6:
            bad.append(f"벨트 반대 {along * 1000:.2f} mm/s")  # 상류로 돌진 금지 (U2 결정)
        err_along = r.get("err_along_m")
        downstream = err_along is None or err_along >= -align_along_m  # 박스가 상류가 아님
        if downstream and (norm(c) or 0.0) <= ZERO_EPS:
            bad.append("박스 하류인데 cmd 0")
    got = f"{len(rows)}틱, 위반 {len(bad)}" + (f": {sorted(set(bad))[:3]}" if bad else "")
    return _v("J11", "추종", not bad, want, got)


def line_distance(p: Any, start: Any, d: Any) -> float:
    """점 p 와 (start 를 지나고 방향 d 인) 직선 사이 거리."""
    w = [float(a) - float(b) for a, b in zip(p, start, strict=False)]
    dn = norm(d) or 1.0
    u = [float(x) / dn for x in d]
    s = sum(a * b for a, b in zip(w, u, strict=False))  # 직선 방향 성분
    return math.sqrt(max(0.0, sum(a * a for a in w) - s * s))


def judge_track_lock(rows: list[dict], start: Any, belt_dir: Any) -> Verdict:
    """J12: goal 트랙의 관측값만 쓰였다 (첫째 궤적 선에서 5 mm 안 — 둘째는 40 mm)."""
    want = f"≤ {TRACK_LOCK_TOL_M * 1000:g} mm"
    pts = [r["position_base_m"] for r in rows if r.get("position_base_m") is not None]
    if not pts or belt_dir is None:
        return _unknown("J12", "트랙 고정", want, "position_base 없음")
    worst = max(line_distance(p, start, belt_dir) for p in pts)
    return _v("J12", "트랙 고정", worst <= TRACK_LOCK_TOL_M, want, f"최대 {worst * 1000:.2f} mm")


def parse_gateway(lines: list[str]) -> GatewayFacts:
    """launch.log 줄 → gateway 사실."""
    facts = GatewayFacts()
    for line in lines:
        if facts.mode is None and (m := GW_STARTED.search(line)):
            facts.mode = m.group(1).rstrip(",")  # 첫 단어
        if m := GW_WATCHDOG.search(line):
            facts.watchdogs.append(float(m.group(1)))
        if m := GW_STOP.search(line):
            facts.stops.append((float(m.group(1)), m.group(2)))
        if m := GW_STATS.search(line):
            facts.stats.append((float(m.group(1)), *(int(m.group(i)) for i in range(2, 6))))
    return facts


def in_window(t: float, start: float | None, end: float | None) -> bool:
    """start ≤ t < end (None 이면 그쪽 끝 없음)."""
    return (start is None or t >= start) and (end is None or t < end)


def judge_dry_run(mode: str | None) -> Verdict:
    """J10: 띄운 gateway 가 dry_run 인가 (아니면 goal 을 보내지 않는다)."""
    if mode is None:
        return _unknown("J10", "gateway dry_run", "dry_run", "gateway 시작 줄 없음")
    return _v("J10", "gateway dry_run", mode == "dry_run", "dry_run", mode)


def judge_watchdog(facts: GatewayFacts, terminal_t: float | None, win: tuple) -> Verdict:
    """J7: 창 [goal 수락, SIGINT) 안에 watchdog 1회, 종료 틱 뒤 0.6~0.9 s."""
    want = f"1회 · 종료 뒤 {WATCHDOG_DELAY_S[0]}~{WATCHDOG_DELAY_S[1]} s"
    if terminal_t is None:
        return _unknown("J7", "watchdog", want, "종료 틱 없음")
    ws = [t for t in facts.watchdogs if in_window(t, *win)]
    if not ws:
        return _unknown("J7", "watchdog", want, "창 안에 watchdog 줄 없음")
    delay = ws[0] - terminal_t
    ok = len(ws) == 1 and WATCHDOG_DELAY_S[0] <= delay <= WATCHDOG_DELAY_S[1]
    return _v("J7", "watchdog", ok, want, f"{len(ws)}회 · {delay:.3f} s")


def _stats_in(facts: GatewayFacts, win: tuple) -> list[tuple]:
    """창 안의 통계 줄."""
    return [s for s in facts.stats if in_window(s[0], *win)]


def judge_move_stop(facts: GatewayFacts, cancel: bool, win: tuple) -> Verdict:
    """J8: 창 안 move_stop 성공 수 (cancel 은 stop 1 + watchdog 1 = 2)."""
    want_n = 2 if cancel else 1
    want = f"ok {want_n} · fail 0"
    st = _stats_in(facts, win)
    if not st:
        return _unknown("J8", "move_stop", want, "창 안에 통계 줄 없음")
    ok_n, fail_n = sum(s[3] for s in st), sum(s[4] for s in st)
    return _v("J8", "move_stop", ok_n == want_n and fail_n == 0, want, f"ok {ok_n} · fail {fail_n}")


def judge_stop(facts: GatewayFacts, cancel: bool, win: tuple) -> Verdict:
    """J9: 창 안 /voss/robot/stop 호출 수와 결과 (cancel 만 1회 OK)."""
    want_n = 1 if cancel else 0
    want = f"stop {want_n}" + (" · → OK" if cancel else "")
    st = _stats_in(facts, win)
    if not st:
        return _unknown("J9", "stop", want, "창 안에 통계 줄 없음")
    lines = [r for t, r in facts.stops if in_window(t, *win)]
    n = sum(s[2] for s in st)
    ok = n == want_n and len(lines) == want_n and all(r == "OK" for r in lines)
    return _v("J9", "stop", ok, want, f"stop {n} · 줄 {lines}")


def preflight_problems(domain_id: str, node_names: list[str]) -> list[str]:
    """J0: sim 을 띄우면 안 되는 이유들 (빈 목록 = 통과)."""
    problems = []
    if domain_id.strip() == REAL_DOMAIN:
        problems.append(f"ROS_DOMAIN_ID={REAL_DOMAIN} (공용 PC·실로봇 도메인)")
    present = sorted({n for n in node_names if n in SIM_NODES})
    if present:
        problems.append(f"이미 떠 있는 노드: {present}")
    return problems


def exit_code(verdicts: list[Verdict]) -> int:
    """case 하나의 종료 코드: FAIL → 1, 아니면 UNKNOWN → 2, 아니면 0."""
    statuses = {v.status for v in verdicts}
    if "FAIL" in statuses:
        return 1
    return 2 if "UNKNOWN" in statuses else 0


def worst_code(codes: list[int]) -> int:
    """여러 case 종합: 1 > 2 > 0 (숫자 max 가 아니다)."""
    if 1 in codes:
        return 1
    return 2 if 2 in codes else 0


def format_table(title: str, verdicts: list[Verdict]) -> str:
    """판정 표 (마크다운)."""
    mark = {"PASS": "✅", "FAIL": "❌", "UNKNOWN": "⚠️ 판정 불가"}
    lines = [f"== {title} ==", "| ID | 항목 | 기대 | 실제 | 판정 |", "|---|---|---|---|---|"]
    for v in verdicts:
        lines.append(f"| {v.id} | {v.item} | {v.expected} | {v.actual} | {mark[v.status]} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- 실행 부분 (ROS·프로세스·파일)


class Interrupted(Exception):
    """Ctrl+C·SIGTERM 요청. 신호 처리기는 깃발만 세우고, 기다리는 반복문이 안전한 지점에서 올린다.

    (rclpy C 확장 안에서 KeyboardInterrupt 가 나면 RuntimeError 로 바뀌어 정리 경로를 벗어난다 — U3 실측)
    """


_STOP = {"requested": False}  # 신호 처리기가 세우는 깃발


def _on_signal(signum: int, frame: Any) -> None:
    """SIGINT·SIGTERM → 깃발만 세운다 (정리 중 두 번째 신호도 정리를 끊지 않는다)."""
    _STOP["requested"] = True


def check_stop() -> None:
    """깃발이 서 있으면 Interrupted (기다리는 반복문마다 부른다)."""
    if _STOP["requested"]:
        raise Interrupted()


@dataclass
class Outcome:
    """goal 하나의 결과."""

    error: str | None = None
    goal_id: str | None = None
    t_goal: float | None = None  # 수락 ROS 시각
    phases: list[str] = field(default_factory=list)
    status: int | None = None
    reason: str | None = None
    grasped: bool | None = None
    attempts: int | None = None
    cancel_sent: bool = False


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """명령 인자 (DD 6.1)."""
    ap = argparse.ArgumentParser(prog="sim_check", description="fake_box + dry_run 시뮬 판정")
    ap.add_argument("--case", default="all", choices=[*CASES, "all"])
    ap.add_argument("--profile", default="pre_u5", choices=list(PROFILE_CASES))
    ap.add_argument("--out", default=None, help="run 폴더들의 부모 (기본 /tmp/voss_sim/<시각>)")
    ap.add_argument("--config", default=None, help="voss_config.yaml (기본 <git 최상위>/config)")
    ap.add_argument("--kp", default=None, help="control.kp_per_s 덮어쓰기")
    ap.add_argument("--goal-timeout-s", type=float, default=30.0)
    ap.add_argument("--cancel-after-s", type=float, default=None, help="cancel case 시각 덮어쓰기")
    return ap.parse_args(argv)


def default_config() -> str | None:
    """현재 git 최상위의 config/voss_config.yaml (없으면 None)."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    path = os.path.join(top, "config", "voss_config.yaml")
    return path if os.path.isfile(path) else None


def sim_values() -> dict[str, float]:
    """설치된 belt_servo_sim.yaml 에서 판정에 쓰는 값 (zero_hold_s·rate_hz·align_tol_along)."""
    from ament_index_python.packages import get_package_share_directory

    from voss_servo.launch_params import flatten, load_yaml, node_section

    path = os.path.join(get_package_share_directory("voss_servo"), "config", "belt_servo_sim.yaml")
    flat = flatten(node_section(load_yaml(path)))
    return {
        "zero_hold_s": float(flat["zero_hold_s"]),
        "rate_hz": float(flat["rate_hz"]),
        "align_along_m": float(flat["control.align_tol_along_mm"]) / 1000.0,
    }


def read_lines(path: str) -> list[str]:
    """파일 줄 목록 (없으면 [])."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def wait_for_line(path: str, pattern: re.Pattern, timeout: float, after_t: float | None = None):
    """로그 파일을 0.2 s 마다 다시 읽어 pattern 에 맞는 줄을 기다린다 → match 또는 None.

    after_t 가 있으면 첫 그룹(시각)이 after_t 보다 뒤인 줄만.
    """
    deadline = time.monotonic() + timeout
    while True:
        for line in read_lines(path):
            m = pattern.search(line)
            if m and (after_t is None or float(m.group(1)) > after_t):
                return m
        if time.monotonic() >= deadline:
            return None
        check_stop()
        time.sleep(0.2)


def read_jsonl(folder: str) -> list[dict]:
    """folder/*.jsonl 의 모든 행 (없으면 [])."""
    rows: list[dict] = []
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        for line in read_lines(path):
            if line.strip():
                rows.append(json.loads(line))
    return rows


class SimRunner:
    """ROS 노드 하나로 case 들을 차례로 돌린다."""

    def __init__(self, args: argparse.Namespace, out_root: str, sim: dict[str, float]) -> None:
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy

        from voss_msgs.msg import BoxTrack

        self.rclpy = rclpy
        self.args, self.out_root, self.sim = args, out_root, sim
        self.node = rclpy.create_node("sim_check")
        self.last_box_stamp = 0.0  # 받은 BoxTrack stamp 중 가장 늦은 것 (ROS 초)
        qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.node.create_subscription(BoxTrack, "/voss/vision/box", self._on_box, qos)

    def _on_box(self, msg) -> None:
        t = msg.stamp.sec + msg.stamp.nanosec * 1e-9
        self.last_box_stamp = max(self.last_box_stamp, t)

    def now(self) -> float:
        """ROS 시각 (초) — fake_box stamp·틱 로그·gateway 로그와 같은 시계."""
        return self.node.get_clock().now().nanoseconds * 1e-9

    def spin_for(self, seconds: float) -> None:
        """seconds 동안 콜백을 돌린다."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            check_stop()
            self.rclpy.spin_once(self.node, timeout_sec=0.05)

    def preflight(self, first: bool) -> list[str]:
        """J0: 도메인·이미 떠 있는 노드. 두 번째 case 부터는 앞 case 노드가 사라질 때까지 기다린다."""
        self.spin_for(DISCOVERY_S)
        if not first:
            end = time.monotonic() + GRAPH_CLEAR_S
            while time.monotonic() < end and preflight_problems("", self.node.get_node_names()):
                self.spin_for(0.5)
        domain = os.environ.get("ROS_DOMAIN_ID", "0")
        return preflight_problems(domain, self.node.get_node_names())

    def start_launch(self, case: Case, run_dir: str):
        """sim.launch 를 새 프로세스 그룹으로 띄운다. 출력 → run_dir/launch.log."""
        cmd = [
            "ros2",
            "launch",
            "voss_servo",
            "sim.launch.py",
            f"config:={self.args.config}",
            f"scenario:={case.scenario}",
            f"object_mm:={case.object_mm:g}",
            f"log_dir:={run_dir}",
        ]
        if self.args.kp is not None:
            cmd.append(f"kp:={self.args.kp}")
        env = dict(os.environ, PYTHONUNBUFFERED="1", RCUTILS_COLORIZED_OUTPUT="0")
        # 닫기는 run_case 의 finally
        log = open(os.path.join(run_dir, "launch.log"), "w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env
        )
        return proc, log

    def stop_launch(self, proc) -> tuple[float, bool]:
        """launch 에만 SIGINT (launch 가 자식에 전파) → 기다림 → 남으면 그룹에 SIGKILL.

        반환 (SIGINT 보낸 ROS 시각, SIGKILL 썼나).
        """
        t_int = self.now()
        if proc.poll() is not None:
            return t_int, False
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=STOP_S)
            return t_int, False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)  # 마지막 수단만 그룹 전체
            proc.wait()
            return t_int, True

    def run_goal(self, case: Case, t_case: float) -> Outcome:
        """액션 서버·이번 case 박스를 기다린 뒤 goal 1개 → 결과."""
        from rclpy.action import ActionClient

        from voss_msgs.action import TrackAndGrasp

        client = ActionClient(self.node, TrackAndGrasp, "/voss/servo/track_and_grasp")
        try:
            end = time.monotonic() + SERVER_S
            while not client.wait_for_server(timeout_sec=0.5):  # 짧게 끊어 깃발을 본다
                check_stop()
                if time.monotonic() >= end:
                    return Outcome(error="액션 서버 없음")
            end = time.monotonic() + FIRST_BOX_S
            while self.last_box_stamp < t_case and time.monotonic() < end:
                check_stop()
                self.rclpy.spin_once(self.node, timeout_sec=0.05)
            if self.last_box_stamp < t_case:
                return Outcome(error="이번 case 의 박스 메시지 없음")
            out = Outcome()
            goal = TrackAndGrasp.Goal()
            goal.track_id = 1
            fut = client.send_goal_async(
                goal, feedback_callback=lambda fb: out.phases.append(fb.feedback.phase)
            )
            end = time.monotonic() + ACCEPT_S
            while not fut.done() and time.monotonic() < end:
                check_stop()
                self.rclpy.spin_once(self.node, timeout_sec=0.05)
            handle = fut.result() if fut.done() else None
            if handle is None or not handle.accepted:
                out.error = "goal 거부 또는 수락 응답 없음"
                return out
            # belt_servo 틱 로그 goal_id 와 같은 형식 (UUID 16바이트 hex)
            out.goal_id = bytes(handle.goal_id.uuid).hex()
            out.t_goal = self.now()
            t0 = time.monotonic()
            res_f = handle.get_result_async()
            cancel_after = (
                self.args.cancel_after_s
                if (case.cancel_after_s is not None and self.args.cancel_after_s is not None)
                else case.cancel_after_s
            )
            while not res_f.done():
                check_stop()
                self.rclpy.spin_once(self.node, timeout_sec=0.05)
                elapsed = time.monotonic() - t0
                if cancel_after is not None and not out.cancel_sent and elapsed >= cancel_after:
                    handle.cancel_goal_async()
                    out.cancel_sent = True
                if elapsed > self.args.goal_timeout_s:
                    out.error = f"goal 결과 시간 초과 ({self.args.goal_timeout_s:g} s)"
                    return out
            res = res_f.result()
            out.status, out.reason = res.status, res.result.reason
            out.grasped, out.attempts = res.result.grasped, res.result.attempts
            return out
        finally:
            client.destroy()

    def run_case(self, case: Case, first: bool) -> list[Verdict]:
        """case 하나: 사전 점검 → 기동 → goal → 정리 → 판정."""
        run_dir = os.path.join(self.out_root, case.name)
        os.makedirs(run_dir, exist_ok=True)
        exp = EXPECT[(self.args.profile, case.name)]
        problems = self.preflight(first)
        if problems:  # 안전: sim 을 띄우지 않는다
            return [Verdict("J0", "사전 점검", "문제 없음", "; ".join(problems), "FAIL")]
        verdicts = [Verdict("J0", "사전 점검", "문제 없음", "문제 없음", "PASS")]
        launch_log = os.path.join(run_dir, "launch.log")
        out, t_int, killed = Outcome(error="시작 전"), None, False
        t_case = self.now()
        proc, log = self.start_launch(case, run_dir)
        try:
            m = wait_for_line(launch_log, GW_STARTED, GW_START_S)
            verdicts.append(judge_dry_run(m.group(1) if m else None))
            if verdicts[-1].status != "PASS":
                return verdicts  # 안전: 실기 gateway 일 수 있으면 goal 을 보내지 않는다 (finally 가 끈다)
            if wait_for_line(launch_log, SERVO_READY, SERVO_READY_S) is None:
                refused = wait_for_line(launch_log, SERVO_REFUSED, 0.0)
                why = refused.string.strip() if refused else "READY 줄 없음"
                verdicts.append(_unknown("J1", "result", "belt_servo READY", why))
                return verdicts
            out = self.run_goal(case, t_case)
            if out.error is None:  # 정착: watchdog 줄 → 그 뒤 통계 줄
                wd = wait_for_line(launch_log, GW_WATCHDOG, SETTLE_S)
                if wd is not None:
                    wait_for_line(launch_log, GW_STATS, SETTLE_S, after_t=float(wd.group(1)))
        finally:
            t_int, killed = self.stop_launch(proc)
            log.close()
        return verdicts + self.judge_case(case, exp, out, run_dir, t_int, killed)

    def judge_case(
        self, case: Case, exp: Expect, out: Outcome, run_dir: str, t_int: float, killed: bool
    ) -> list[Verdict]:
        """파일을 읽어 판정 (DD 6.4·6.5)."""
        from voss_servo.fake_box import DEFAULT_START_M

        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump({**asdict(out), "t_sigint": t_int, "sigkill": killed}, f, indent=2)
        ticks = select_goal_rows(read_jsonl(os.path.join(run_dir, "ticks")), out.goal_id)
        attempts = select_goal_rows(read_jsonl(os.path.join(run_dir, "attempts")), out.goal_id)
        goal_end = next((r for r in attempts if r.get("event") == "GOAL_END"), None)
        progress, terminal, hold = split_goal_ticks([r for r in ticks if r.get("kind") == "tick"])
        v: list[Verdict] = []
        if out.error:
            v.append(_unknown("J1", "result", f"{exp.status}/{exp.reason}", out.error))
        else:
            v.append(judge_result(exp, out.status, out.reason, out.grasped))
        v.append(judge_cause(exp, goal_end))
        v.append(judge_phases(exp, out.phases))
        v.append(judge_last_zero(terminal))
        v.append(judge_zero_hold(terminal, hold, self.sim["zero_hold_s"], self.sim["rate_hz"]))
        v.append(judge_period(progress + ([terminal] if terminal else []) + hold))
        facts = parse_gateway(read_lines(os.path.join(run_dir, "launch.log")))
        win = (out.t_goal, t_int)
        cancel = case.cancel_after_s is not None
        terminal_t = terminal["t_pub_s"] if terminal else None
        v += [
            judge_watchdog(facts, terminal_t, win),
            judge_move_stop(facts, cancel, win),
            judge_stop(facts, cancel, win),
        ]
        if self.args.profile == "pre_u5" and case.name in ("normal", "two_boxes"):
            v.append(judge_follow(progress, self.sim["align_along_m"]))
        if case.name == "two_boxes":
            belt = next((r.get("belt_vel_mps") for r in ticks if r.get("belt_vel_mps")), None)
            rows = progress + ([terminal] if terminal else [])
            v.append(judge_track_lock(rows, DEFAULT_START_M, belt))
        if killed:
            v.append(_unknown("J-", "정리", "SIGINT 로 종료", "SIGKILL 사용 (launch 가 안 끝남)"))
        return v

    def close(self) -> None:
        self.node.destroy_node()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.config = args.config or default_config()
    if not args.config or not os.path.isfile(os.path.expanduser(args.config)):
        print("sim_check: voss_config.yaml 없음 — 레포 안에서 실행하거나 --config", flush=True)
        sys.exit(2)
    args.config = os.path.abspath(os.path.expanduser(args.config))
    names = PROFILE_CASES[args.profile] if args.case == "all" else (args.case,)
    if any((args.profile, n) not in EXPECT for n in names):
        print(f"sim_check: profile {args.profile} 에 없는 case: {args.case}", flush=True)
        sys.exit(2)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.abspath(args.out or os.path.join("/tmp/voss_sim", stamp))
    os.makedirs(out_root, exist_ok=True)

    import rclpy
    from rclpy.signals import SignalHandlerOptions

    # rclpy 기본 SIGINT 처리기는 컨텍스트를 먼저 내린다 → 끄고, SIGINT·SIGTERM 은 깃발만 세운다
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    runner = SimRunner(args, out_root, sim_values())
    codes: dict[str, int] = {}
    try:
        for i, name in enumerate(names):
            verdicts = runner.run_case(CASES[name], first=(i == 0))
            code = 2 if any(v.id == "J0" and v.status == "FAIL" for v in verdicts) else None
            code = exit_code(verdicts) if code is None else code
            codes[name] = code
            text = format_table(f"{name} (profile {args.profile})", verdicts)
            print(text + f"\n→ 종료 코드 {code}\n", flush=True)
            with open(os.path.join(out_root, name, "verdict.json"), "w", encoding="utf-8") as f:
                json.dump({"code": code, "verdicts": [asdict(v) for v in verdicts]}, f, indent=2)
            if code == 2 and verdicts[0].status == "FAIL":
                break  # 사전 점검 거부 → 남은 case 를 돌리지 않는다
    except Interrupted:  # Ctrl+C·SIGTERM: run_case 의 finally 가 sim 을 이미 껐다
        print("sim_check: 중단됨 — 띄운 sim 은 정리했다 (판정 불가)", flush=True)
        codes["중단"] = 2
    finally:
        runner.close()
        rclpy.try_shutdown()
    print("== 요약 ==\n| case | 종료 코드 | run 폴더 |\n|---|---|---|")
    for name, code in codes.items():
        folder = os.path.join(out_root, name) if name in CASES else "-"  # 중단 행은 폴더 없음
        print(f"| {name} | {code} | {folder} |")
    sys.exit(worst_code(list(codes.values())))


if __name__ == "__main__":
    main()
