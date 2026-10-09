"""sim_check.py 순수 판정 함수 시험 (ROS 없이) — design/U3-dd.md 8절 T-S1~T-S10."""

import pytest

from voss_servo import sim_check as sc

BELT = [0.048, -0.0006, 0.0]  # 틱 로그 belt_vel_mps 모양 (m/s)
T0 = 1791557423.8  # 사전 실험 무렵 ROS 시각


def tick(t: float, cmd=(0.048, 0.0, 0.0), **kw) -> dict:
    """틱 로그 한 행 (필요한 필드만)."""
    row = {
        "kind": "tick",
        "goal_id": "g1",
        "t_pub_s": t,
        "terminal": False,
        "stopping": False,
        "visible": True,
        "cmd_vel_mps": list(cmd),
        "belt_vel_mps": BELT,
        "tcp_now_m": [0.0, -0.27, 0.14],
        "predicted_m": [0.0, -0.27, 0.10],
        "error_m": [0.0, 0.0, 0.0],
        "err_along_m": 0.0,
        "cause": "",
    }
    row.update(kw)
    return row


def run_like_spike(n_progress: int = 40, n_hold: int = 15, dt: float = 1 / 30) -> list[dict]:
    """사전 실험과 같은 모양: 진행 틱 → 종료 틱(0) → ZERO_HOLD 틱 n_hold 개(0)."""
    rows = [tick(T0 + i * dt) for i in range(n_progress)]
    t_end = T0 + n_progress * dt
    rows.append(tick(t_end, (0.0, 0.0, 0.0), terminal=True, cause="REACH_X_MAX"))
    rows += [tick(t_end + (i + 1) * dt, (0.0, 0.0, 0.0), cause="ZERO_HOLD") for i in range(n_hold)]
    return rows


# 사전 실험 gateway 로그 줄 (scratchpad spike/logs/gateway.log 에서 그대로)
GW_NORMAL = [
    "[robot_gateway-1] [INFO] [1791557399.721964855] [robot_gateway]: robot_gateway started: "
    "dry_run (두산·RG2 연결 안 함), pose 50 Hz, servo watchdog 200 ms, max 100 mm/s",
    "[robot_gateway-1] [INFO] [1791557434.725927745] [robot_gateway]: servo rx 30.0 Hz, speedl 150, "
    "거부 0, 자름 0, watchdog 0, stop 0, move_stop 0 ok / 0 fail",
    "[robot_gateway-1] [WARN] [1791557437.561526031] [robot_gateway]: servo_cmd 끊김(watchdog) → "
    "0 속도 + move_stop",
    "[robot_gateway-1] [INFO] [1791557439.719905304] [robot_gateway]: servo rx 15.8 Hz, speedl 79, "
    "거부 0, 자름 0, watchdog 1, stop 0, move_stop 1 ok / 0 fail",
]
GW_CANCEL = [
    "[robot_gateway-1] [INFO] [1791557538.930144672] [robot_gateway]: /voss/robot/stop → OK",
    "[robot_gateway-1] [WARN] [1791557539.658807806] [robot_gateway]: servo_cmd 끊김(watchdog) → "
    "0 속도 + move_stop",
    "[robot_gateway-1] [INFO] [1791557539.718620185] [robot_gateway]: servo rx 21.6 Hz, speedl 107, "
    "거부 {'stop': 1}, 자름 0, watchdog 1, stop 1, move_stop 2 ok / 0 fail",
]
WIN = (1791557420.0, 1791557450.0)  # [goal 수락, SIGINT)


def test_result_and_cause() -> None:
    """T-S1: result·cause 일치 PASS, 하나라도 다르면 FAIL, GOAL_END 없으면 UNKNOWN."""
    exp = sc.EXPECT[("pre_u5", "lost")]
    assert sc.judge_result(exp, sc.ABORTED, "LOST", False).status == "PASS"
    assert sc.judge_result(exp, sc.ABORTED, "STALE_INPUT", False).status == "FAIL"
    assert sc.judge_result(exp, sc.CANCELED, "LOST", False).status == "FAIL"
    assert sc.judge_cause(exp, {"cause": "BOX_MISSING"}).status == "PASS"
    assert sc.judge_cause(exp, {"cause": "BOX_INVALID"}).status == "FAIL"
    assert sc.judge_cause(exp, None).status == "UNKNOWN"


def test_phases_exact_and_prefix() -> None:
    """T-S2: = [PREPARE] 와 표준 순서 앞부분 규칙."""
    exact = sc.EXPECT[("pre_u5", "normal")]
    assert sc.judge_phases(exact, ["PREPARE"]).status == "PASS"
    assert sc.judge_phases(exact, ["PREPARE", "TRACK"]).status == "FAIL"
    prefix = sc.EXPECT[("grasp", "cancel")]
    assert sc.judge_phases(prefix, ["PREPARE", "TRACK"]).status == "PASS"
    assert sc.judge_phases(prefix, ["PREPARE", "DESCEND"]).status == "FAIL"  # TRACK 건너뜀
    last = sc.EXPECT[("grasp", "empty")]
    assert sc.judge_phases(last, ["PREPARE", "TRACK", "DESCEND", "GRASP"]).status == "PASS"
    assert sc.judge_phases(last, ["PREPARE", "TRACK"]).status == "FAIL"  # GRASP 에 못 감


def test_last_zero_and_zero_hold() -> None:
    """T-S3: 사전 실험 모양 PASS / hold 중 0 아닌 틱 FAIL / hold 짧음 FAIL / 종료 틱 없음 UNKNOWN."""
    progress, terminal, hold = sc.split_goal_ticks(run_like_spike())
    assert len(progress) == 40 and terminal["terminal"] and len(hold) == 15
    assert sc.judge_last_zero(terminal).status == "PASS"
    assert sc.judge_zero_hold(terminal, hold, 0.5, 30.0).status == "PASS"
    bad = [dict(r) for r in hold]
    bad[5]["cmd_vel_mps"] = [0.001, 0.0, 0.0]
    assert sc.judge_zero_hold(terminal, bad, 0.5, 30.0).status == "FAIL"
    assert sc.judge_zero_hold(terminal, hold[:8], 0.5, 30.0).status == "FAIL"
    _, none_terminal, _ = sc.split_goal_ticks([tick(T0), tick(T0 + 0.033)])
    assert sc.judge_last_zero(none_terminal).status == "UNKNOWN"


def test_period() -> None:
    """T-S4: 평균 33.3 ms PASS, 40 ms FAIL, 틱 1개 UNKNOWN."""
    assert sc.judge_period(run_like_spike()).status == "PASS"
    assert sc.judge_period(run_like_spike(dt=0.040)).status == "FAIL"
    assert sc.judge_period([tick(T0)]).status == "UNKNOWN"


def test_follow_rule() -> None:
    """T-S5: 벨트 반대 FAIL · 빈 필드 FAIL · 박스 상류의 0 명령 PASS · 박스 하류의 0 명령 FAIL · 적으면 UNKNOWN."""
    ok = [tick(T0 + i / 30) for i in range(40)]
    assert sc.judge_follow(ok, 0.003).status == "PASS"
    back = [dict(r) for r in ok]
    back[3]["cmd_vel_mps"] = [-0.010, 0.0, 0.0]  # 상류로 돌진
    assert sc.judge_follow(back, 0.003).status == "FAIL"
    empty = [dict(r) for r in ok]
    empty[7]["predicted_m"] = None
    assert sc.judge_follow(empty, 0.003).status == "FAIL"
    waiting = [dict(r) for r in ok]
    # 기다리기 (사전 실험 cancel: 박스가 590 mm 상류일 때 명령 0)
    waiting[9].update(cmd_vel_mps=[0.0, 0.0, 0.0], err_along_m=-0.590)
    assert sc.judge_follow(waiting, 0.003).status == "PASS"
    frozen = [dict(r) for r in ok]
    frozen[9].update(cmd_vel_mps=[0.0, 0.0, 0.0], err_along_m=0.010)  # 박스가 앞에 있는데 멈춤
    assert sc.judge_follow(frozen, 0.003).status == "FAIL"
    assert sc.judge_follow(ok[:10], 0.003).status == "UNKNOWN"


def test_track_lock() -> None:
    """T-S6: 첫째 궤적 PASS, 둘째(40 mm 옆) 값이 섞이면 FAIL."""
    start = (-0.100, -0.271, 0.1008)
    first = [
        tick(T0, position_base_m=[start[0] + d, start[1] - d * 0.0125, start[2]])
        for d in (0, 0.2, 0.4)
    ]
    assert sc.judge_track_lock(first, start, BELT).status == "PASS"
    mixed = first + [tick(T0, position_base_m=[0.0, start[1] + 0.040, start[2]])]
    assert sc.judge_track_lock(mixed, start, BELT).status == "FAIL"
    assert sc.judge_track_lock([tick(T0)], start, BELT).status == "UNKNOWN"


def test_parse_gateway_spike_lines() -> None:
    """T-S7: 사전 실험 실제 줄 → mode·watchdog·stop·통계."""
    n = sc.parse_gateway(GW_NORMAL)
    assert n.mode == "dry_run"
    assert n.watchdogs == [pytest.approx(1791557437.561526031)]
    assert sum(s[3] for s in n.stats) == 1 and sum(s[2] for s in n.stats) == 0
    c = sc.parse_gateway(GW_CANCEL)
    assert c.stops == [(pytest.approx(1791557538.930144672), "OK")]
    assert sum(s[3] for s in c.stats) == 2 and sum(s[2] for s in c.stats) == 1
    assert sc.parse_gateway(["robot_gateway started: real /dsr01, pose 50 Hz"]).mode == "real"


def test_gateway_judges_and_window() -> None:
    """T-S8: 지연 0.71 PASS / 0.3 FAIL / 줄 없음 UNKNOWN / SIGINT 뒤 두 번째 watchdog 은 무시."""
    facts = sc.parse_gateway(GW_NORMAL)
    terminal_t = 1791557436.8487787  # 사전 실험 normal 종료 틱
    assert sc.judge_watchdog(facts, terminal_t, WIN).status == "PASS"
    assert sc.judge_watchdog(facts, terminal_t + 0.41, WIN).status == "FAIL"  # 지연 0.3 s
    assert sc.judge_watchdog(sc.GatewayFacts(), terminal_t, WIN).status == "UNKNOWN"
    assert sc.judge_move_stop(facts, False, WIN).status == "PASS"
    assert sc.judge_stop(facts, False, WIN).status == "PASS"
    late = sc.parse_gateway(GW_NORMAL + [GW_NORMAL[2].replace("37.561526031", "51.0")])
    assert sc.judge_watchdog(late, terminal_t, WIN).status == "PASS"  # 창(…50.0) 밖은 무시
    cancel = sc.parse_gateway(GW_CANCEL)
    cwin = (1791557530.0, 1791557545.0)
    assert sc.judge_move_stop(cancel, True, cwin).status == "PASS"
    assert sc.judge_stop(cancel, True, cwin).status == "PASS"
    assert sc.judge_move_stop(cancel, False, cwin).status == "FAIL"  # cancel 아닌데 2회
    assert sc.judge_dry_run("dry_run").status == "PASS"
    assert sc.judge_dry_run("real").status == "FAIL"
    assert sc.judge_dry_run(None).status == "UNKNOWN"


def test_exit_codes() -> None:
    """T-S9: case 는 FAIL → 1, UNKNOWN 만 → 2, 전부 PASS → 0. 종합은 1 > 2 > 0."""
    p = sc.Verdict("J1", "x", "a", "a", "PASS")
    f = sc.Verdict("J2", "x", "a", "b", "FAIL")
    u = sc.Verdict("J3", "x", "a", "?", "UNKNOWN")
    assert sc.exit_code([p, p]) == 0
    assert sc.exit_code([p, u]) == 2
    assert sc.exit_code([u, f]) == 1
    assert sc.worst_code([2, 1, 0]) == 1  # 숫자 max(2) 가 아니다
    assert sc.worst_code([0, 2]) == 2 and sc.worst_code([0, 0]) == 0


def test_preflight() -> None:
    """T-S10: 도메인 30 거부, sim 노드가 이미 있으면 거부, 34·빈 그래프 통과."""
    assert sc.preflight_problems("34", ["sim_check"]) == []
    assert sc.preflight_problems("30", [])
    problems = sc.preflight_problems("34", ["sim_check", "robot_gateway"])
    assert problems and "robot_gateway" in problems[0]
