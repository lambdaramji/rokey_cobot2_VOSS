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
    # U9b: 빈손은 안전 후퇴(phase LIFT) 뒤에 끝난다
    assert sc.judge_phases(last, ["PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT"]).status == "PASS"
    assert sc.judge_phases(last, ["PREPARE", "TRACK", "DESCEND", "GRASP"]).status == "FAIL"


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


# --- U9a: J12 하강 끊김 판정 (design/U9a-dd.md 4절) ---


def descend_rows(cut_t: float, blind_t: float, end_t: float = 1.2) -> list[dict]:
    """DESCEND 틱: cut_t 까지 매 틱 수신, blind_t 부터 사각 (t 는 DESCEND 시작 기준 s)."""
    rows, n = [], 0
    while n / 30.0 <= end_t:
        t = T0 + n / 30.0
        rx = T0 + min(n / 30.0, cut_t)  # cut_t 뒤로는 새 메시지가 없다
        row = tick(t, phase="DESCEND", t_calc_s=t, box_rx_s=rx, vision_blind=n / 30.0 >= blind_t)
        row["position_base_m"] = [0.0, -0.27, 0.1008]
        row["tcp_now_m"] = [0.0, -0.27, 0.1408 - 0.02 * n / 30.0]  # 20 mm/s 로 내려간다
        rows.append(row)
        n += 1
    return rows


def test_judge_descend_cut_pass() -> None:
    v = sc.judge_descend_cut(descend_rows(cut_t=0.30, blind_t=0.467), 0.5)
    assert v.status == "PASS" and "여유" in v.actual  # 최대 나이 약 0.13 → 여유 약 0.37
    assert "끊김 윗면 +34.0 mm" in v.actual  # 끊긴 순간(0.30 s) 높이, 사각 뒤 틱이 아니다


def test_judge_descend_cut_fail_small_margin() -> None:
    v = sc.judge_descend_cut(descend_rows(cut_t=0.10, blind_t=0.467), 0.5)
    assert v.status == "FAIL"  # 최대 나이 약 0.33 → 여유 약 0.17 < 0.2


def test_judge_descend_cut_fail_no_cut() -> None:
    v = sc.judge_descend_cut(descend_rows(cut_t=9.0, blind_t=0.467), 0.5)
    assert v.status == "FAIL" and "경주 없음" in v.actual  # 사각까지 계속 받았다


def test_judge_descend_cut_unknown() -> None:
    assert sc.judge_descend_cut([], 0.5).status == "UNKNOWN"  # DESCEND 틱 없음
    no_blind = descend_rows(cut_t=0.3, blind_t=9.0)
    assert sc.judge_descend_cut(no_blind, 0.5).status == "UNKNOWN"  # 사각 틱 없음


def test_grasp_profile_has_u9a_cases() -> None:
    assert {"descend_lost", "vanish"} <= set(sc.PROFILE_CASES["grasp"])  # U9b 가 뒤에 덧붙임
    assert sc.EXPECT[("grasp", "descend_lost")].reason == "OK"
    assert sc.EXPECT[("grasp", "vanish")].cause == "BOX_MISSING"


# --- U9b: 재시도·안전 후퇴 case (design/U9b-dd.md 6.3, 7.1 S1) ---


def test_u9b_cases_and_expectations() -> None:
    assert sc.PROFILE_CASES["grasp"][-3:] == ("retry", "fail_retreat", "wide")
    retry = sc.EXPECT[("grasp", "retry")]
    assert retry.attempts == 2 and retry.phases_exact == (*sc.PHASES[:4], *sc.PHASES)
    for name, cause in (("fail_retreat", "NOT_DETECTED"), ("wide", "WIDTH_OUT")):
        e = sc.EXPECT[("grasp", name)]
        assert (e.reason, e.cause, e.retreat) == ("GRASP_FAILED", cause, True)
        assert e.phases_exact == tuple(sc.PHASES[:5])  # …GRASP, LIFT(후퇴)
    empty = sc.EXPECT[("grasp", "empty")]
    assert empty.phases_last == "LIFT" and empty.retreat  # 후퇴 뒤에 끝난다


def test_u9b_launch_extra() -> None:
    assert sc.launch_extra(sc.CASES["normal"]) == []  # 기존 case 는 지금과 같은 인자
    extra = sc.launch_extra(sc.CASES["retry"])
    assert extra == [
        "gripper:=fake",
        "grip_plan:=empty,held",
        "grip_close_s:=0.5",  # S2-T29: x_max 550 에서 재시도 문턱 166 안에 들게
        "max_attempts:=3",
        "box_start_x_mm:=-250",
    ]
    assert sc.CASES["retry"].kp == 3.0 and sc.CASES["retry"].timeout_s == 60.0


def test_u9b_judge_result_attempts() -> None:
    e = sc.EXPECT[("grasp", "retry")]
    assert sc.judge_result(e, sc.SUCCEEDED, "OK", True, 2).status == "PASS"
    v = sc.judge_result(e, sc.SUCCEEDED, "OK", True, 1)
    assert v.status == "FAIL" and "attempts=1" in v.actual
    plain = sc.EXPECT[("grasp", "normal")]  # attempts 기대 없음 → 보지 않는다
    assert sc.judge_result(plain, sc.SUCCEEDED, "OK", True, 7).status == "PASS"


def test_u9b_judge_retreat() -> None:
    end = tick(T0, (0.0, 0.0, 0.0), terminal=True, retreat_done=True)
    end["position_base_m"] = [0.30, -0.27, 0.1008]
    end["tcp_now_m"] = [0.34, -0.27, 0.1008 + 0.0485]  # 윗면 +48.5 mm
    assert sc.judge_retreat(end, 0.050, 0.002).status == "PASS"
    low = dict(end, tcp_now_m=[0.30, -0.27, 0.1008 - 0.019])  # 파지 높이에서 끝남
    assert sc.judge_retreat(low, 0.050, 0.002).status == "FAIL"
    undone = dict(end, retreat_done=False)
    assert sc.judge_retreat(undone, 0.050, 0.002).status == "FAIL"
    assert sc.judge_retreat(None, 0.050, 0.002).status == "UNKNOWN"
    assert sc.judge_retreat(dict(end, position_base_m=None), 0.050, 0.002).status == "UNKNOWN"


# ------------------------------------------------------------------ S2-T14 (DD 7절 N17·N19)


def zrow(phase: str, z: float, target: float | None = None, **kw) -> dict:
    """착지·z 시간 판정용 틱 (tcp_pose_m z 와 tcp_target_m z 만 의미 있음)."""
    row = {"phase": phase, "tcp_pose_m": [0.0, 0.0, z]}
    if target is not None:
        row["tcp_target_m"] = [0.0, 0.0, target]
    row.update(kw)
    return row


@pytest.mark.parametrize(
    ("low_mm", "status"), [(80.81, "PASS"), (80.79, "FAIL"), (85.79, "PASS"), (85.81, "FAIL")]
)
def test_s2t14_judge_landing_both_bounds(low_mm, status) -> None:
    rows = [zrow("DESCEND", 0.0840, 0.0818), zrow("GRASP", low_mm / 1000.0), zrow("GRASP", 0.087)]
    assert sc.judge_landing(rows).status == status  # 목표 81.8: [−1, +4] mm
    assert sc.judge_landing([zrow("GRASP", 0.08)]).status == "UNKNOWN"  # DESCEND 없음


def test_s2t14_judge_z_times() -> None:
    last = {"phase_t_descend_s": 10.0, "phase_t_grasp_s": 11.8, "phase_t_lift_s": 14.0}
    rows = [{**last, "phase_t_verify_s": 15.7}]
    trap = ("trapezoid", 1.70, 1.74)
    assert sc.judge_z_times(rows, trap).status == "PASS"  # 1.8 ≤ 2.2 · 1.7 ≤ 2.24
    slow = [{**last, "phase_t_grasp_s": 12.6, "phase_t_verify_s": 15.7}]  # P 처럼 2.6 s
    assert sc.judge_z_times(slow, trap).status == "FAIL"
    assert sc.judge_z_times(rows, None).status == "UNKNOWN"  # 프로파일 줄 없음
    assert sc.judge_z_times([last], trap).status == "UNKNOWN"  # VERIFY 진입 없음


def test_s2t14_parse_profile_line() -> None:
    from voss_servo import control

    lines = [
        "[INFO] [1.0] [belt_servo]: READY",
        "[INFO] [1.0] [belt_servo]: z 프로파일: trapezoid — DESCEND·LIFT 사다리꼴(감속 0.080 m/s², "
        f"최소 {control.TRAP_V_FLOOR_MPS * 1000:g} mm/s), PREPARE·TRACK·후퇴는 P. "
        "하강 예상 1.70 s · 들기 예상 1.74 s (되돌림: z.profile: p)",
    ]
    assert sc.parse_profile(lines) == ("trapezoid", 1.70, 1.74)
    p_line = "[INFO] [1.0] [belt_servo]: z 프로파일: p — 모든 phase P(kp_z 1.5). 하강 예상 2.64 s · 들기 예상 2.79 s (켜기: z.profile: trapezoid)"
    assert sc.parse_profile([p_line]) == ("p", 2.64, 2.79)
    assert sc.parse_profile(["[belt_servo]: READY"]) is None


def test_s2t14_launch_extra_z_profile() -> None:
    assert sc.launch_extra(sc.CASES["normal"], "trapezoid") == ["z_profile:=trapezoid"]
    assert sc.launch_extra(sc.CASES["normal"], None) == []  # 기본 = sim yaml
    assert sc.Z_CASES == ("normal", "descend_lost")


def test_s2t14_case_x_geometry_margins() -> None:
    """DD 5절 표: 두 모드에서 retry 는 재시도, fail_retreat 는 후퇴로 갈 x 여유 (재검 M2)."""
    belt, align = 48.0, 72.0  # mm/s, sim 정렬 x (kp 1)
    desc = {"p": 2.7, "trapezoid": 1.77}  # sim DESCEND s (P 실측 체류 + 진입, 사다리꼴 재검 sim)
    retry_cap = {"p": 165.7, "trapezoid": 210.6}  # 재시도 가능 실패 x 상한 (HLD D4)
    close = sc.CASES["fail_retreat"].grip_close_s
    assert close == sc.FAIL_RETREAT_CLOSE_S == 2.2
    for mode in ("p", "trapezoid"):
        fail_x = align + belt * (desc[mode] + close)  # fail_retreat 1차 실패 x
        assert fail_x - retry_cap[mode] >= 50.0  # 후퇴로 간다, 여유 ≥ 50 mm
        retry_fail = -2.0 + belt * (desc[mode] + sc.CASES["retry"].grip_close_s)  # retry 1차 실패
        assert retry_cap[mode] - retry_fail >= 10.0  # 재시도로 간다 (P 쪽 14 mm 는 S2-T29 값)


def _sim_launch():
    """launch/sim.launch.py 를 모듈로 읽는다 (설치 없이 소스에서)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "launch" / "sim.launch.py"
    spec = importlib.util.spec_from_file_location("sim_launch_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_s2t14_sim_launch_overrides(tmp_path) -> None:
    """z_profile 만 줘도 덮어쓰기 파일이 생기고 z.profile 이 들어간다 (재검 m5 의 조건 누락 방지)."""
    import yaml

    mod = _sim_launch()
    assert mod._wants_overrides("", "", "trapezoid")
    assert not mod._wants_overrides("", "", "")
    path = mod._write_overrides(str(tmp_path), "", "", "trapezoid")
    body = yaml.safe_load(open(path, encoding="utf-8"))
    assert body == {"belt_servo": {"ros__parameters": {"z": {"profile": "trapezoid"}}}}


def _rows(states_causes, wz=0.0):
    return [{"rot_state": s, "rot_cause": c, "wz_cmd_dps": wz} for s, c in states_causes]


def _c(angular=0, ang_speed=0, yaw_limit=0) -> dict:
    return {"angular": angular, "ang_speed": ang_speed, "yaw_limit": yaw_limit}


def test_rotation_judges_and_angular_clamps() -> None:
    """S2-T18 J-rot·J-ang: STALL 폴백·SMALL 생략 판정, COLLECT 는 있어도 없어도, 통계 줄의 각속도 자름 합."""
    stall = _rows(
        [("COLLECT", None), ("ROTATING", None), ("STOPPING", "STALL"), ("FALLBACK", "STALL")]
    )
    assert sc.judge_rotation("rotate_stall", stall, _c(3), None).status == "PASS"
    assert sc.judge_rotation("rotate_stall", stall[1:], _c(3), False).status == "PASS"  # 첫 틱 결정
    assert (
        sc.judge_rotation("rotate_stall", stall, _c(0), None).status == "FAIL"
    )  # 각속도를 안 냈다
    # gateway 각속도 켬이면 STALL 기대 자체가 성립하지 않는다 (학민 #54 리뷰 2)
    assert sc.judge_rotation("rotate_stall", stall, _c(3), True).status == "FAIL"
    small = _rows([("COLLECT", None), ("SKIP", "SMALL"), ("SKIP", "SMALL")])
    assert sc.judge_rotation("rotate_small", small, _c(), None).status == "PASS"
    wz5 = _rows([("SKIP", "SMALL")], wz=5.0)
    assert sc.judge_rotation("rotate_small", wz5, _c(), None).status == "FAIL"
    assert sc.judge_no_angular(_c(), None).status == "PASS"
    assert sc.judge_no_angular(_c(2), False).status == "FAIL"
    assert sc.judge_no_angular(_c(0, 1), None).status == "FAIL"  # 켬 gateway 의 키도 센다
    assert sc.judge_no_angular(_c(), True).status == "FAIL"  # 켬이면 angular 가 z 를 안 센다
    ts = "[INFO] [1791557440.100000000] [robot_gateway]: "
    lines = [
        ts + "servo rx 30.0 Hz, speedl 150, 거부 0, 자름 {'angular': 12}, watchdog 0, stop 0, "
        "move_stop 0 ok / 0 fail",
        ts.replace("40.1", "45.1") + "servo rx 30.0 Hz, speedl 150, 거부 0, 자름 0, watchdog 0, "
        "stop 0, move_stop 0 ok / 0 fail",
        ts.replace("40.1", "50.1") + "servo rx 30.0 Hz, speedl 150, 거부 0, "
        "자름 {'speed': 1, 'ang_speed': 4, 'yaw_limit': 2}, watchdog 0, stop 0, move_stop 0 ok / 0 fail",
    ]
    facts = sc.parse_gateway(lines)
    assert sc.angular_clamps(facts, (1791557430.0, None)) == _c(12, 4, 2)
    assert sc.angular_clamps(facts, (1791557446.0, None)) == _c(0, 4, 2)  # 창 앞의 줄은 세지 않는다
    assert facts.ang_on is None  # 기동 줄 없음 = 옛 gateway
    assert ("rotate", "rotate_stall") in sc.EXPECT and sc.PROFILE_CASES["rotate"]
    assert sc.launch_extra(sc.CASES["rotate_stall"]) == ["rotate:=true", "box_yaw_deg:=30"]
    assert sc.launch_extra(sc.CASES["rotate_ok"])[-1] == "gw_angular:=true"
    assert sc.launch_extra(sc.CASES["normal"]) == []  # 회전 off 케이스는 인자 없음


def test_gateway_angular_lines_and_rotate_ok() -> None:
    """S2-T17 gateway 기동 줄(켬/끔) → J-rot rotate_ok·J-gw 한도 교차 검사 (학민 #54 리뷰 2·7)."""
    on = (
        "[WARN] [1.0] [robot_gateway]: servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 100°"
    )
    facts = sc.parse_gateway([on])
    assert facts.ang_on is True and facts.ang_limits == (60.0, 90.0)
    off = "[INFO] [1.0] [robot_gateway]: servo angular off (각속도는 0 으로 자름)"
    assert sc.parse_gateway([off]).ang_on is False
    seq = ["ROTATING", "SETTLING", "DONE", "RETURNING", "RETURNED"]
    rows = [{"rot_state": s, "rot_cause": None, "wz_cmd_dps": 10.0, "phase": "TRACK"} for s in seq]
    rows.insert(
        3, {"rot_state": "DONE", "phase": "DESCEND", "rot_err_deg": -0.8, "wz_cmd_dps": 0.0}
    )
    assert sc.judge_rotation("rotate_ok", rows, _c(), True).status == "PASS"
    assert (
        sc.judge_rotation("rotate_ok", rows, _c(0, 3), True).status == "FAIL"
    )  # gateway 가 잘랐다
    assert sc.judge_rotation("rotate_ok", rows, _c(), None).status == "UNKNOWN"  # S2-T17 전 gateway
    bad = [dict(r, rot_err_deg=-2.0) if r.get("phase") == "DESCEND" else r for r in rows]
    assert sc.judge_rotation("rotate_ok", bad, _c(), True).status == "FAIL"  # 남은 각 > tol
    zero = [dict(r, rot_err_deg=0.0) if r.get("phase") == "DESCEND" else r for r in rows]
    assert sc.judge_rotation("rotate_ok", zero, _c(), True).status == "PASS"  # 0.0 도 값 (재리뷰)
    line = "[INFO] [2.0] [belt_servo]: rotate on · deadband 4 · min 10 · max 45 · ω 60 · α 90 · home goal"
    assert sc.parse_servo_rotate([line]) == (60.0, 90.0)
    assert sc.judge_gw_limits((60.0, 90.0), (60.0, 90.0)).status == "PASS"
    assert sc.judge_gw_limits((60.0, 90.0), (60.0, 10.0)).status == "FAIL"  # servo_acc[1] 10
    assert sc.judge_gw_limits(None, (60.0, 90.0)).status == "UNKNOWN"
    assert ("rotate_gw", "rotate_ok") in sc.EXPECT and sc.PROFILE_CASES["rotate_gw"] == (
        "rotate_ok",
    )
