"""S2-T14 사다리꼴 z 프로파일 시험 (ROS 없이). 목록은 design/S2T14-dd.md 7절 N1~N14, N6'·N13'.

폐루프 도우미 run_z: control.command 를 30 Hz 로 부르고, 로봇은 두 모델 중 하나로 움직인다.
- ideal: 명령 속도를 그대로 낸다.
- delay_ramp(τ): 명령을 τ 늦게 받고, 자기 속도를 0.1 m/s² 램프로 명령 쪽으로 바꾼다
  (gateway speedl acc 100 mm/s², HLD 0.3 의 B 모델 — 10/12 틱 맞춤 평균 0.31 mm).
TCP 추정은 기본으로 로봇 실제 위치(외삽 없음). 후속(HLD 12.2): Robot(pose_lag) 로 pose 지연, run_z(cfg_lag) 로
설정 pose_lag 외삽, run_z(coast_ticks) 로 LIFT 도달 뒤 관성을 넣는다.
"""

import math
from collections import deque

import numpy as np
import pytest

from voss_servo import control, fsm, grip, params

TOP = 0.1008  # 박스 윗면 z (10/12 실측)
TARGET = TOP - 0.019  # 파지 목표 TCP z = 81.8 mm
APPROACH = TOP + 0.040
LIFT_Z = TOP + 0.050
DT = 1.0 / 30.0
BELT = 0.048
RAMP = 0.1  # 로봇 램프 m/s² (gateway servo_acc)


def values(**over) -> dict:
    """시연 설정 (FIELD-1012 '바꾸지 않을 것': kp_z 1.5, close 2.5, x_max 550)."""
    v = {
        "belt.speed_cmps": 4.8,
        "belt.direction_base": [1.0, 0.0, 0.0],
        "timing.latency_offset_ms": 0.0,
        "input.pose_lag_ms": 0.0,
        "input.pose_extrap_max_ms": 200.0,
        "input.blind_entry_max_age_s": 0.15,
        "control.kp_per_s": 1.0,
        "control.kp_z_per_s": 1.5,
        "control.align_tol_along_mm": 3.0,
        "control.align_tol_cross_mm": 5.0,
        "limits.max_speed_mps": 0.08,
        "limits.max_acc_mps2": 0.1,
        "z.approach_above_top_mm": 40.0,
        "grasp.tcp_z_below_top_mm": 19.0,
        "z.lift_above_top_mm": 50.0,
        "z.descend_speed_mps": 0.05,
        "z.lift_speed_mps": 0.08,
        "z.height_tol_mm": 2.0,
        "reach.x_min_mm": -107.0,
        "reach.x_max_mm": 550.0,
        "rate_hz": 30.0,
    }
    v.update(over)
    return v


P = control.config_from_values(values())  # z.profile 없음 = p
TRAP = control.config_from_values(values(**{"z.profile": "trapezoid"}))


# ------------------------------------------------------------------ 폐루프 도우미


class Robot:
    """명령 → 실제 z 속도. tau 만큼 늦게 받고, ramp 가 있으면 그 가속으로만 속도를 바꾼다.

    pose_lag: 실제 pose 지연 — seen(t) 가 이만큼 옛 위치를 돌려준다 (S2-T14 후속, HLD 12.2).
    """

    def __init__(
        self, z0: float, tau: float = 0.0, ramp: float | None = None, pose_lag: float = 0.0
    ) -> None:
        self.z = z0  # 실제 TCP z
        self.v = 0.0  # 실제 z 속도
        self.tau, self.ramp = tau, ramp
        self.queue: deque = deque()  # (적용 시각, 명령 vz)
        self.cmd = 0.0  # 지금 적용 중인 명령
        self.pose_lag = pose_lag
        self.hist: list[tuple[float, float]] = [(-1.0, z0)]  # (시각, z) — 서브스텝마다

    def seen(self, t: float) -> float:
        """pose 가 보여 주는 z = 시각 t − pose_lag 의 실제 z. 지연 0 이면 지금 z 그대로."""
        if self.pose_lag == 0.0:
            return self.z  # 기존 시험과 비트 단위로 같게 (시각 비교를 하지 않는다)
        when = t - self.pose_lag
        return next(z for tt, z in reversed(self.hist) if tt <= when + 1e-12)

    def step(self, t: float, vz_cmd: float, sub: int = 10) -> None:
        """시각 t 에 명령 vz_cmd 를 보내고 dt 동안 sub 조각으로 적분한다."""
        self.queue.append((t + self.tau, vz_cmd))
        h = DT / sub
        for k in range(sub):
            now = t + k * h
            while self.queue and self.queue[0][0] <= now + 1e-12:
                self.cmd = self.queue.popleft()[1]  # 늦게 도착한 명령
            if self.ramp is None:
                self.v = self.cmd  # 즉시 따라감
            else:
                dv = self.cmd - self.v
                self.v += max(-self.ramp * h, min(self.ramp * h, dv))  # 램프
            self.z += self.v * h
            if self.pose_lag:
                self.hist.append((now + h, self.z))  # 서브스텝마다 (틱마다면 실효 지연이 늘어난다)


def make_geo(cfg: control.ControlConfig, z: float) -> control.Geometry:
    """박스 바로 위(정렬됨)·보이지 않음(사각) 상태의 Geometry. TCP 추정 = 실제 z."""
    tcp = (np.array([0.0, 0.0, z]), 0.0, False)
    return control.geometry(tcp, np.array([0.0, 0.0, TOP]), 100.0, False, 100.0, cfg)


def run_z(cfg, phase, z0, robot=None, xy_ff=False, max_s=6.0, cfg_lag=0.0, coast_ticks=0):
    """phase 하나(DESCEND 또는 LIFT)를 전이까지 돌린다. DESCEND 는 이어서 GRASP 램프로 멈출 때까지.

    추정 z = robot.seen(t) + 마지막 명령 z × cfg_lag (control.tcp_now 와 같은 규칙, 설정 pose_lag).
    LIFT 는 도달하면 끝, coast_ticks > 0 이면 도달 뒤 0 명령(VERIFY·후퇴 끝)으로 그만큼 더 돌려 관성을 잰다.
    반환 dict: t_reach(전이 시각), land(GRASP 중 실제 z 최소), top(실제 z 최대), cmds, dv_max.
    """
    rob = robot or Robot(z0)
    prev = np.array([BELT if xy_ff else 0.0, 0.0, 0.0])  # 직전 발행 속도
    t, cur, t_reach = 0.0, phase, None
    land, top_z, cmds, dv_max = math.inf, -math.inf, [], 0.0
    grasp_ticks = 0
    while t < max_s:
        g = make_geo(
            cfg, rob.seen(t) + float(prev[2]) * cfg_lag
        )  # pose 지연이 있으면 옛 위치를 본다
        if cur == fsm.DESCEND and g.at_grasp_height:
            cur, t_reach = fsm.GRASP, t  # 파지 높이 도달 → GRASP (z 요구 0, clamp 램프로 정지)
        if cur == fsm.LIFT and g.at_lift_height and t_reach is None:
            t_reach = t
            for k in range(coast_ticks):  # 도달 뒤 0 명령 — 로봇은 지연·램프만큼 더 간다
                rob.step(t + k * DT, 0.0)
                top_z = max(top_z, rob.z)
            break
        retreat = xy_ff and cur == fsm.LIFT
        cmd = control.command(cur, False, False, g, prev, DT, cfg, retreat=retreat)
        dv_max = max(dv_max, float(np.linalg.norm(cmd.vel - prev)))
        cmds.append(cmd)
        prev = cmd.vel
        rob.step(t, float(cmd.vel[2]))
        if cur == fsm.GRASP:
            land = min(land, rob.z)
            grasp_ticks += 1
            if grasp_ticks > 45:  # GRASP 1.5 s 면 충분히 멈췄다
                break
        top_z = max(top_z, rob.z)
        t += DT
    return {"t_reach": t_reach, "land": land, "top": top_z, "cmds": cmds, "dv_max": dv_max}


# ------------------------------------------------------------------ N1~N4 법칙·범위


def test_n1_trap_far_saturates_with_sign() -> None:
    v = control.z_speed_trap(0.0, 0.1, 0.08, 0.002, 0.005, 0.05, 0.08)
    assert v == pytest.approx(-0.05)  # 내려가는 상한
    assert control.z_speed_trap(0.1, 0.0, 0.08, 0.002, 0.005, 0.05, 0.08) == pytest.approx(0.08)


def test_n2_trap_decel_curve_is_sqrt_and_monotone() -> None:
    speeds = []
    for d_mm in (12.0, 9.0, 6.0, 4.0, 3.0):  # 감속 구간 안 (√(2·0.08·d) < 0.05 ↔ d − tol < 15.6 mm)
        v = -control.z_speed_trap(0.0, d_mm / 1000.0, 0.08, 0.002, 0.005, 0.05, 0.08)
        assert v == pytest.approx(math.sqrt(2 * 0.08 * (d_mm - 2.0) / 1000.0))
        speeds.append(v)
    assert speeds == sorted(speeds, reverse=True)  # 가까울수록 느려진다 (단조)


def test_n3_trap_floor_zero_and_one_way() -> None:
    f = control.z_speed_trap
    assert f(0.0, 0.0021, 0.08, 0.002, 0.005, 0.05, 0.08) == pytest.approx(-0.005)  # 바닥 5 mm/s
    assert f(0.0, 0.0015, 0.08, 0.002, 0.005, 0.05, 0.08) == pytest.approx(-0.005)  # tol 안도 바닥
    assert f(0.05, 0.05, 0.08, 0.002, 0.005, 0.05, 0.08) == 0.0  # 목표 = 0
    assert f(0.1, 0.0, 0.08, 0.002, 0.005, 0.05, 0.0) == 0.0  # 그 방향 상한 0 → 안 간다
    assert f(0.0, 0.01, 0.08, 0.002, 0.005, 0.003, 0.08) == pytest.approx(-0.003)  # 바닥 ≤ 상한


def test_n4_z_law_scope() -> None:
    for phase in (fsm.DESCEND, fsm.LIFT):
        assert control.z_law(phase, TRAP) == control.Z_LAW_TRAP
    for phase in (fsm.PREPARE, fsm.TRACK, fsm.GRASP, fsm.VERIFY):
        assert control.z_law(phase, TRAP) == control.Z_LAW_P  # 머무는 phase 는 P (HLD D2)
    for phase in (fsm.PREPARE, fsm.TRACK, fsm.DESCEND, fsm.GRASP, fsm.LIFT, fsm.VERIFY):
        assert control.z_law(phase, P) == control.Z_LAW_P  # p 모드는 전부 P


# ------------------------------------------------------------------ N5 P 회귀 (틱 단위 동일)


def old_command(phase, stopping, terminal, geo, prev_v, dt, cfg, retreat=False, hold_z=False):
    """f9f1d28 의 control.command 본문 복사 (참조). 새 코드와 독립이어야 회귀를 잡는다."""
    c = control
    if stopping or terminal:
        return c.zero_cmd()
    if geo is None or not geo.has_obs or geo.p_pred is None or geo.top_z is None:
        return c.zero_cmd()
    rule = c.retreat_xy(geo.tcp, geo.top_z, cfg) if retreat else c.xy_rule(phase, geo.visible)
    z_t, v_down, v_up = c.z_plan(phase, geo.top_z, cfg, hold_z)
    target = c.tcp_target(geo.p_pred, z_t if z_t is not None else float(geo.tcp[2]))
    e = target - geo.tcp
    if rule == c.ZERO:
        v = c.zero_cmd()
    else:
        v = c.ff_p(e, cfg.belt_v, cfg.belt_dir_xy, cfg.kp_xy, use_p=(rule == c.FF_P))
    v[2] = 0.0 if z_t is None else c.z_speed(z_t, float(geo.tcp[2]), cfg.kp_z, v_down, v_up)
    v, _ = c.clamp(v, prev_v, cfg.v_max, cfg.a_max, dt)
    return v


@pytest.mark.parametrize(
    "phase", [fsm.PREPARE, fsm.TRACK, fsm.DESCEND, fsm.GRASP, fsm.LIFT, fsm.VERIFY]
)
@pytest.mark.parametrize("retreat", [False, True])
@pytest.mark.parametrize("hold_z", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_n5_p_mode_matches_old_command(phase, retreat, hold_z, visible) -> None:
    prev = np.array([0.03, 0.001, -0.02])
    for z in (APPROACH + 0.03, APPROACH, TOP + 0.01, TARGET + 0.0015, TARGET - 0.001):
        tcp = (np.array([0.004, -0.002, z]), 0.05, False)
        g = control.geometry(tcp, np.array([0.0, 0.0, TOP]), 99.95, visible, 100.0, P)
        new = control.command(phase, False, False, g, prev, DT, P, retreat=retreat, hold_z=hold_z)
        ref = old_command(phase, False, False, g, prev, DT, P, retreat=retreat, hold_z=hold_z)
        assert np.array_equal(new.vel, ref)  # 비트까지 같다 (np.array_equal, 근사 아님)


def test_n5_p_mode_closed_loop_trajectory_identical() -> None:
    rob_new, rob_ref = Robot(APPROACH), Robot(APPROACH)
    prev_new = prev_ref = np.zeros(3)
    for k in range(90):  # 3 s 하강 (P 는 2.6 s 쯤 도달 — 끝까지 같은 phase 로 비교)
        g_new, g_ref = make_geo(P, rob_new.z), make_geo(P, rob_ref.z)
        new = control.command(fsm.DESCEND, False, False, g_new, prev_new, DT, P).vel
        ref = old_command(fsm.DESCEND, False, False, g_ref, prev_ref, DT, P)
        assert np.array_equal(new, ref), k
        rob_new.step(k * DT, float(new[2]))
        rob_ref.step(k * DT, float(ref[2]))
        prev_new, prev_ref = new, ref


# ------------------------------------------------------------------ N6·N6'·N7·N9 폐루프


def test_n6_trap_descend_ideal_no_overshoot_budget_and_faster() -> None:
    trap, p = run_z(TRAP, fsm.DESCEND, APPROACH), run_z(P, fsm.DESCEND, APPROACH)
    assert trap["land"] - TARGET >= -0.001  # 지나침 ≤ 1 mm (완료 기준 3, GRASP 램프 포함)
    assert trap["dv_max"] <= 0.1 * DT + 1e-9  # 매 틱 가속 예산 안
    assert all(np.linalg.norm(c.vel) <= 0.08 + 1e-9 for c in trap["cmds"])  # 속도 상한 안
    assert trap["t_reach"] < p["t_reach"] - 0.8  # P(≈2.6 s) 보다 0.8 s 넘게 짧다


@pytest.mark.parametrize(
    ("tau", "low_mm"),
    [(0.024, -0.5), (0.060, -1.0), (0.100, -2.5)],  # HLD D1 (a) 표 −0.27 / −2.20 에 여유
)
def test_n6p_trap_landing_with_delay_and_ramp(tau, low_mm) -> None:
    out = run_z(TRAP, fsm.DESCEND, APPROACH, robot=Robot(APPROACH, tau=tau, ramp=RAMP))
    assert (out["land"] - TARGET) * 1000.0 >= low_mm
    assert out["land"] >= params.GATEWAY_Z_MIN_MM / 1000.0 + 0.001  # 하한 78 위


@pytest.mark.parametrize(
    ("real_lag", "cfg_lag", "tau", "low_mm", "high_mm"),
    [
        (
            0.060,
            0.0,
            0.060,
            -3.5,
            -2.5,
        ),  # 보정 안 된 60 ms — 착지 78.8 (HLD 12.2, 학민 76.8 은 τ100)
        (0.060, 0.060, 0.060, -1.0, 9.0),  # 보정됨 — −0.5
        (0.020, 0.0, 0.024, 0.0, 9.0),  # 현장형: joint_states 실제 15~20 ms · 설정 0 — +0.5
    ],
)
def test_f6_trap_landing_with_pose_lag(real_lag, cfg_lag, tau, low_mm, high_mm) -> None:
    rob = Robot(APPROACH, tau=tau, ramp=RAMP, pose_lag=real_lag)
    out = run_z(TRAP, fsm.DESCEND, APPROACH, robot=rob, cfg_lag=cfg_lag)
    assert low_mm <= (out["land"] - TARGET) * 1000.0 <= high_mm


@pytest.mark.parametrize("tau", [0.024, 0.060, 0.100])
def test_n6p_p_mode_lands_above_target(tau) -> None:
    out = run_z(P, fsm.DESCEND, APPROACH, robot=Robot(APPROACH, tau=tau, ramp=RAMP))
    assert (out["land"] - TARGET) * 1000.0 >= 1.0  # P 는 문턱 근처에서 멈춘다 (현장 +1.75~1.89)


def test_f1_z_law_retreat_is_p() -> None:
    """후속 (나): 후퇴는 사다리꼴에서도 P (HLD 12.1). 정상 LIFT·DESCEND 는 사다리꼴 그대로."""
    assert control.z_law(fsm.LIFT, TRAP, retreat=True) == control.Z_LAW_P
    assert control.z_law(fsm.LIFT, TRAP) == control.Z_LAW_TRAP
    assert control.z_law(fsm.DESCEND, TRAP) == control.Z_LAW_TRAP


def test_f2_trap_retreat_equals_p_retreat() -> None:
    """사다리꼴 모드의 후퇴 RISING 명령 = P 모드 후퇴 명령 (틱·비트 단위, 10/12 실기 동작 그대로)."""
    a = run_z(TRAP, fsm.LIFT, TARGET, xy_ff=True)
    b = run_z(P, fsm.LIFT, TARGET, xy_ff=True)
    assert len(a["cmds"]) == len(b["cmds"])
    assert all(np.array_equal(x.vel, y.vel) for x, y in zip(a["cmds"], b["cmds"], strict=True))


def test_f3_lift_tail_command_and_coast() -> None:
    """도달 직전 틱 z 명령(학민 제안)과 도달 뒤 관성까지 잰 진짜 지나침 (N7 교체)."""
    trap, p = run_z(TRAP, fsm.LIFT, TARGET), run_z(P, fsm.LIFT, TARGET)  # 정상 LIFT
    assert abs(float(trap["cmds"][-1].vel[2])) <= 0.006  # 꼬리 ≤ 6 mm/s
    assert trap["t_reach"] < p["t_reach"] - 0.5  # 사다리꼴이 0.5 s 넘게 짧다
    assert trap["dv_max"] <= 0.1 * DT + 1e-9
    for cfg in (TRAP, P):  # 후퇴 (두 모드 모두 P)
        out = run_z(cfg, fsm.LIFT, TARGET, xy_ff=True)
        assert abs(float(out["cmds"][-1].vel[2])) <= 0.006
    for xy_ff in (False, True):  # 지연 + 램프 τ24: 도달 뒤 20틱 관성 포함 최고 z
        rob = Robot(TARGET, tau=0.024, ramp=RAMP)
        out = run_z(TRAP, fsm.LIFT, TARGET, robot=rob, xy_ff=xy_ff, coast_ticks=20)
        assert out["top"] <= LIFT_Z + 0.002  # 들기 목표 + 2 mm 안


@pytest.mark.parametrize("robot_tau", [None, 0.024, 0.060, 0.100])
def test_n9_analytic_vs_closed_loop(robot_tau) -> None:
    """해석식 vs 폐루프 도달 시간. 위험한 쪽(실제가 해석보다 길다)은 0.08 s 이하여야 한다.

    이상 로봇은 틱 양자화로 실제가 0.03 s 길다(P 도 2.70 vs 2.64). 지연·램프 로봇은 실제가 짧다
    (DESCEND 0.03~0.07, LIFT 0.17~0.20 s) — 해석식이 긴 쪽 = x 여유·상한 모두 보수적.
    0.08 s × 48 mm/s ≈ 4 mm < room_margin 10 mm.
    """

    def robot(z0):
        return None if robot_tau is None else Robot(z0, tau=robot_tau, ramp=RAMP)

    d = run_z(TRAP, fsm.DESCEND, APPROACH, robot=robot(APPROACH))["t_reach"]
    lift = run_z(TRAP, fsm.LIFT, TARGET, robot=robot(TARGET))["t_reach"]
    e_d = control.z_move_time_s(0.059, 0.05, TRAP, control.Z_LAW_TRAP)
    e_l = control.z_move_time_s(0.069, 0.08, TRAP, control.Z_LAW_TRAP)
    for actual, expect in ((d, e_d), (lift, e_l)):
        assert actual - expect <= 0.08  # 실제가 해석보다 길어도 0.08 s 까지
        assert expect - actual <= 0.25  # 해석식이 너무 길지도 않다 (상한이 둔해지지 않게)


# ------------------------------------------------------------------ N8 해석식


def test_n8_trap_time_values() -> None:
    assert grip.trap_time_s(0.059, 0.05, 0.1, 0.08, 0.002) == pytest.approx(1.7025, abs=1e-4)
    assert grip.trap_time_s(0.069, 0.08, 0.1, 0.08, 0.002) == pytest.approx(1.736, abs=1e-3)
    assert grip.trap_time_s(0.049, 0.05, 0.1, 0.08, 0.002) == pytest.approx(1.5025, abs=1e-4)
    assert grip.trap_time_s(0.002, 0.05, 0.1, 0.08, 0.002) == 0.0  # 이미 도달 구간
    with pytest.raises(ValueError):
        grip.trap_time_s(0.059, 0.05, 0.1, 0.0, 0.002)


# ------------------------------------------------------------------ N10·N11 종속 수치·z 하한


def test_n10_dependent_values_trapezoid() -> None:
    room = control.grasp_room_need_s(TRAP, 2.5)
    assert room == pytest.approx(4.2025, abs=1e-3)  # 1.7025 + 2.5
    assert control.descend_blind_max_s(0.030, TRAP) == pytest.approx(2.5025, abs=1e-3)
    assert control.lift_max_s(TRAP) == pytest.approx(3.785, abs=0.005)  # 후퇴는 P (후속 (나))
    need = control.retry_need_s(TRAP, room)  # 재상승은 P (2.660) 그대로
    assert need == pytest.approx(6.862, abs=2e-3)
    assert (0.550 - (BELT * need + 0.010)) * 1000.0 == pytest.approx(210.6, abs=0.2)  # 실패 x 문턱


def test_n10_dependent_values_p_unchanged() -> None:
    room = control.grasp_room_need_s(P, 2.5)
    assert room == pytest.approx(5.139, abs=2e-3)  # f9f1d28 값
    assert control.descend_blind_max_s(0.030, P) == pytest.approx(3.44, abs=0.01)
    assert control.lift_max_s(P) == pytest.approx(3.785, abs=0.005)
    assert control.retry_need_s(P, room) == pytest.approx(7.80, abs=0.02)


def test_n11_floor_margin_by_profile() -> None:
    z_min = params.GATEWAY_Z_MIN_MM / 1000.0
    # 사다리꼴: 목표 ≥ z_min + 3 mm
    assert control.grasp_floor_blocked(z_min + 0.0029 + 0.019, TRAP)
    assert not control.grasp_floor_blocked(z_min + 0.0031 + 0.019, TRAP)
    # P: 문턱(목표 + tol) ≥ z_min + 1 mm — 목표 z_min − 0.9 mm 도 통과 (지금 식 그대로)
    assert not control.grasp_floor_blocked(z_min - 0.0009 + 0.019, P)
    assert control.grasp_floor_blocked(z_min - 0.0011 + 0.019, P)


# ------------------------------------------------------------------ N12·N13·N13'·N14 파라미터


def full_values(**over) -> dict:
    """check_params 가 READY 를 주는 묶음 (test_params.valid_values 와 같은 값 + 시연 값)."""
    from test_params import valid_values  # 같은 폴더 시험 모듈

    v = valid_values()
    v.update(over)
    return v


@pytest.mark.parametrize("value", [None, "p", "trapezoid", "null"])
def test_n12_profile_accepted(value) -> None:
    v = full_values()
    if value is not None:
        v["z.profile"] = value
    assert params.check_params(v).ready  # 선택 키: 없음·null 도 READY


@pytest.mark.parametrize("value", ["trap", "", "P", 1, True])
def test_n12_profile_rejected(value) -> None:
    report = params.check_params(full_values(**{"z.profile": value}))
    assert not report.ready and "z.profile" in [k for k, _ in report.invalid]


def test_n13_digest_p_equals_missing_and_null() -> None:
    base = full_values()
    d0 = params.params_digest(base)
    assert params.params_digest({**base, "z.profile": "p"}) == d0
    assert params.params_digest({**base, "z.profile": "null"}) == d0  # --params-file null
    assert params.params_digest({**base, "z.profile": "trapezoid"}) != d0


def test_n14_config_profile_and_decel() -> None:
    assert P.z_profile == "p" and TRAP.z_profile == "trapezoid"
    assert TRAP.a_dec == pytest.approx(0.08)  # 0.8 × max_acc
    null = control.config_from_values(values(**{"z.profile": "null"}))
    assert null.z_profile == "p"


def test_command_z_v_req_logged() -> None:
    g = make_geo(TRAP, APPROACH)
    belt = np.array([BELT, 0.0, 0.0])  # xy 는 이미 벨트 속도 (FF) — 가속 예산을 z 가 다 쓴다
    cmd = control.command(fsm.DESCEND, False, False, g, belt, DT, TRAP)
    assert cmd.z_v_req == pytest.approx(-0.05)  # clamp 전 요구 (발행값은 −0.0033 로 잘림)
    assert cmd.vel[2] == pytest.approx(-0.1 * DT)
    grasp = control.command(fsm.GRASP, False, False, g, belt, DT, TRAP)
    assert grasp.z_v_req is None  # 목표 z 없음


# ------------------------------------------------------------------ 재검(최종) 보강


def test_floor_constant_used_by_z_command() -> None:
    """최소 속도는 상수로 z_command 가 쓴다 (상수를 0 으로 바꾸면 조준점 앞에서 멈춘다)."""
    assert control.TRAP_V_FLOOR_MPS == pytest.approx(0.005)
    tcp_z = TARGET + 0.002 + 0.00001  # 조준점(목표 + tol) 바로 위 0.01 mm
    vz = control.z_command(TARGET, 0.05, 0.0, fsm.DESCEND, tcp_z, TRAP)
    assert vz == pytest.approx(-control.TRAP_V_FLOOR_MPS)


def test_n18_blind_entry_time_same_in_both_modes() -> None:
    """보이는 구간(+40 → +30)은 두 모드 모두 가속 제한 출발이라 사각 진입 시각이 같다 (HLD 8절)."""

    def entry_tick(cfg) -> int:
        out = run_z(cfg, fsm.DESCEND, APPROACH)
        z = APPROACH
        for k, cmd in enumerate(out["cmds"]):
            z += float(cmd.vel[2]) * DT  # 이상 로봇: 명령대로 움직인다
            if z <= TOP + 0.030:
                return k
        raise AssertionError("사각 진입 없음")

    assert entry_tick(TRAP) == entry_tick(P)  # 같은 틱 (≈ 0.45 s)
