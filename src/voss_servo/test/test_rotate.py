"""rotate.py 시험 (ROS 없음) — S2-T18 J6 회전 파지. design/S2T18-dd.md 9절, pseudo r2 10절."""

import math
import random
from dataclasses import replace

import pytest

from voss_servo import rotate as rt

D = math.radians  # 도 → rad
HOME = D(-88.72)  # 관측 자세 공구 yaw (observe_pose ZYZ 85.25, −179.07, −6.03)
BELT = 0.0  # 시험의 벨트 방향 = 베이스 +X
DT = 1.0 / 30.0  # 서보 틱


def cfg(**kw) -> rt.RotCfg:
    """sim yaml 제안값과 같은 설정 (DD 1절)."""
    base = dict(
        deadband=D(4),
        min_rot=D(10),
        max_rot=D(45),
        tol=D(1.5),
        start_tol=D(3),
        n_min=5,
        buffer_n=15,
        r_min=0.97,
        decide_max_s=0.5,
        home_fixed=None,
        w_max=D(60),
        w_floor=D(3),
        alpha=D(90),
        hold_dz=0.050,
        return_min_dz=0.010,
        settle_s=0.3,
        stall_s=0.6,
        still=D(2),
        belt_yaw=BELT,
        lag_s=0.0,
        extrap_max_s=0.2,
    )
    base.update(kw)
    return rt.RotCfg(**base)


def inputs(**kw) -> rt.RotInputs:
    """기본 = TRACK, 박스 yaw 30° 프레임 5개, 공구는 관측 자세, 정지."""
    base = dict(
        now=0.0,
        phase="TRACK",
        retreat=False,
        hold_z=False,
        yaws=[D(30)] * 5,
        has_field=True,
        home_ref=HOME,
        psi_raw=HOME,
        psi_est=HOME,
        tilt=D(0.93),
        pose_ok=True,
        w_meas=0.0,
        wz_prev=0.0,
        dt=DT,
        err_along=-0.05,
        tcp_z=0.19,
        top_z=0.10,
    )
    base.update(kw)
    return rt.RotInputs(**base)


# ---------------------------------------------------------------- 1~8 작은 함수


def test_fold_half_same_as_vision_rule() -> None:
    """#1 비전 tracker_logic.fold_yaw 와 같은 규칙 — 경계는 + 쪽, 180° 대칭."""
    cases = {
        math.pi / 2: math.pi / 2,
        -math.pi / 2: math.pi / 2,
        math.pi: 0.0,
        -math.pi: 0.0,
        0.0: 0.0,
        3 * math.pi / 4: -math.pi / 4,
        -3 * math.pi / 4: math.pi / 4,
    }
    for a, want in cases.items():
        assert rt.fold_half(a) == pytest.approx(want, abs=1e-12)

    def vision_fold(yaw: float) -> float:  # tracker_logic.fold_yaw 의 규칙을 그대로 옮긴 비교본
        y = math.fmod(yaw, math.pi)
        if y <= -math.pi / 2:
            y += math.pi
        elif y > math.pi / 2:
            y -= math.pi
        return y

    rng = random.Random(7)
    for _ in range(2000):
        a = rng.uniform(-10, 10)
        assert rt.fold_half(a) == vision_fold(a)


def test_wrap_pi_bounds() -> None:
    """#2 (−π, π], ±π 와 ±3π 는 π."""
    for a in (math.pi, -math.pi, 3 * math.pi, -3 * math.pi):
        assert rt.wrap_pi(a) == pytest.approx(math.pi)
    assert rt.wrap_pi(D(370)) == pytest.approx(D(10))
    assert rt.wrap_pi(D(-190)) == pytest.approx(D(170))


def _zyz_quat(a: float, b: float, c: float) -> tuple[float, float, float, float]:
    """두산 ZYZ(도) → 쿼터니언 (x, y, z, w) — gateway 와 같은 정의 Rz(a)·Ry(b)·Rz(c)."""
    a, b, c = D(a), D(b), D(c)
    cb, sb = math.cos(b / 2), math.sin(b / 2)
    w = cb * math.cos((a + c) / 2)
    x = -sb * math.sin((a - c) / 2)
    y = sb * math.cos((a - c) / 2)
    z = cb * math.sin((a + c) / 2)
    return x, y, z, w


def test_tool_yaw_observe_pose_and_j6_sign() -> None:
    """#3 관측 자세 → −88.72°·기울기 0.93°, rz +5° → −93.72° (J6 + = 베이스 Z −), 노름 0 → None."""
    yaw, tilt = rt.tool_yaw(_zyz_quat(85.25, -179.07, -6.03))
    assert math.degrees(yaw) == pytest.approx(-88.72, abs=0.01)
    assert math.degrees(tilt) == pytest.approx(0.93, abs=0.01)
    yaw5, _ = rt.tool_yaw(_zyz_quat(85.25, -179.07, -1.03))
    assert math.degrees(yaw5) == pytest.approx(-93.72, abs=0.01)
    assert rt.tool_yaw((0.0, 0.0, 0.0, 0.0)) is None
    assert rt.tool_yaw((float("nan"), 0.0, 0.0, 1.0)) is None


def test_down_quat_round_trip() -> None:
    """#17 시험·sim 용 쿼터니언 down_quat(ψ) ↔ tool_yaw 왕복, 기울기 0."""
    for deg in range(-180, 181, 15):
        yaw, tilt = rt.tool_yaw(rt.down_quat(D(deg)))
        assert rt.wrap_pi(yaw - D(deg)) == pytest.approx(0.0, abs=1e-9)
        assert tilt == pytest.approx(0.0, abs=1e-6)


def test_aggregate_survives_fold_and_outlier() -> None:
    """#4 ±89° 섞임 → 90° 근처(0° 아님), 튀는 프레임 하나는 중앙값이 흡수, 흩어짐 → r̄ 낮음."""
    agg = rt.aggregate([D(89), D(-89), D(88), D(-88), D(89)])
    assert abs(math.degrees(agg.target)) == pytest.approx(89, abs=1.5)
    assert agg.rbar > 0.99
    one_off = rt.aggregate([D(30)] * 6 + [D(70)])
    assert math.degrees(one_off.target) == pytest.approx(30, abs=0.01)
    spread = rt.aggregate([D(0), D(45), D(-45), D(90), D(30)])
    assert spread.rbar < 0.97
    assert rt.aggregate([]) is None
    # 짝수 개 ±89° 반반: 각 그대로의 중앙값이면 0° 가 되지만 2θ 공간이면 90° (최종 재검 M10)
    even = rt.aggregate([D(89), D(89), D(-89), D(-89)])
    assert abs(math.degrees(even.target)) == pytest.approx(90, abs=0.01)


def test_law_rate_limit_expected_time() -> None:
    """#6·#7 √ 법칙(도착·상한·바닥·부호), 틱당 변화 제한, 예상 시간 해석식."""
    c = cfg()
    assert rt.law(D(1), c.w_max, c.w_floor, c.alpha, c.tol) == 0.0  # tol 안
    assert rt.law(D(80), c.w_max, c.w_floor, c.alpha, c.tol) == pytest.approx(c.w_max)
    assert rt.law(D(-80), c.w_max, c.w_floor, c.alpha, c.tol) == pytest.approx(-c.w_max)
    assert rt.law(D(1.51), c.w_max, c.w_floor, c.alpha, c.tol) == pytest.approx(c.w_floor)
    mid = rt.law(D(10), c.w_max, c.w_floor, c.alpha, c.tol)
    assert mid == pytest.approx(math.sqrt(2 * 0.8 * c.alpha * D(8.5)))
    assert rt.rate_limit(D(60), 0.0, c.alpha, DT) == pytest.approx(c.alpha * DT)
    assert rt.rate_limit(0.0, D(60), c.alpha, DT) == pytest.approx(D(60) - c.alpha * DT)
    assert rt.expected_time(D(45), D(60), D(90)) == pytest.approx(0.75 + 2 / 3)
    assert rt.expected_time(D(10), D(60), D(90)) == pytest.approx(2 * math.sqrt(10 / 90))


def test_yaw_estimate_caps_horizon() -> None:
    """#8 외삽 지평 상한, 각속도 0 이면 원값."""
    assert rt.yaw_estimate(0.1, 1.0, 0.0, 0.0, 1.5, 0.2) == 0.1
    assert rt.yaw_estimate(0.0, 1.0, 0.0, 1.0, 1.05, 0.2) == pytest.approx(0.05)
    assert rt.yaw_estimate(0.0, 1.0, 0.0, 1.0, 2.0, 0.2) == pytest.approx(0.2)


def test_omega_meas_still_vs_dropout_vs_service_steps() -> None:
    """#16 값 그대로 + 메시지 신선 → 0, 끊김 → None, service 계단(0.1 s)에서 0 오판 없음."""
    assert rt.omega_meas((0.0, 1.0), (0.1, 1.05), 1.06, 0.01) == pytest.approx(2.0)
    assert rt.omega_meas((0.0, 1.0), (0.1, 1.05), 1.25, 0.01) == 0.0  # 0.2 s 그대로 = 정지
    assert rt.omega_meas((0.0, 1.0), (0.1, 1.05), 1.25, 0.2) is None  # 메시지 끊김
    assert rt.omega_meas(None, (0.1, 1.05), 1.06, 0.01) is None
    for k in range(1, 6):  # service: 0.1 s 마다 값이 바뀌는 회전 중
        cur = (0.1 * k, 1.0 + 0.1 * k)
        prev = (0.1 * (k - 1), 1.0 + 0.1 * (k - 1))
        for frac in (0.0, 0.05, 0.099):
            w = rt.omega_meas(prev, cur, cur[1] + frac, 0.01)
            assert w == pytest.approx(1.0)  # 0 으로 튀지 않는다


# ---------------------------------------------------------------- 5·15 결정


def test_pre_checks_order_and_decide_table() -> None:
    """#5·#15 판정표 순서: 필드 → 자세 → 시작 자세(프레임보다 먼저) → 흩어짐 → 하류 → 작은 각 → 범위 밖."""
    c = cfg()
    assert rt.pre_checks(inputs(has_field=False), c) == rt.NO_FIELD
    assert rt.pre_checks(inputs(has_field=None), c) == "WAIT"
    assert rt.pre_checks(inputs(psi_raw=None), c) == rt.NO_POSE_YAW
    assert rt.pre_checks(inputs(tilt=D(6)), c) == rt.NO_POSE_YAW
    assert rt.pre_checks(inputs(psi_raw=HOME + D(5), yaws=[]), c) == rt.START_ROTATED
    assert rt.pre_checks(inputs(), c) is None
    agg = rt.aggregate
    assert rt.decide(agg([D(0), D(45), D(-45), D(90), D(30)]), inputs(), c)[0] == rt.SPREAD
    assert rt.decide(agg([D(30)] * 5), inputs(err_along=0.002), c)[0] == rt.DOWNSTREAM
    assert rt.decide(agg([D(8)] * 5), inputs(), c)[0] == rt.SMALL  # min_deg 10 이하
    assert rt.decide(agg([D(60)] * 5), inputs(), c)[0] == rt.OUT_OF_RANGE
    cause, delta = rt.decide(agg([D(30)] * 5), inputs(), c)
    assert cause == "" and math.degrees(delta) == pytest.approx(30)
    cause, delta = rt.decide(agg([D(-80)] * 5), inputs(), cfg(max_rot=D(90)))
    assert cause == "" and math.degrees(delta) == pytest.approx(-80)  # 접힌 최단 방향


def test_collect_waits_then_no_yaw_and_start_rotated_first() -> None:
    """#15 필드 모름이면 대기, 마감 지나면 NO_YAW, START_ROTATED 는 프레임 부족보다 먼저."""
    c = cfg()
    rs = rt.RotState(rt.COLLECT, t_goal=0.0)
    out = rt.rot_step(rs, inputs(has_field=None, yaws=[]), c)
    assert out.state.state == rt.COLLECT and not out.ready and out.wz == 0.0
    out = rt.rot_step(out.state, inputs(now=0.6, yaws=[D(30)] * 3), c)
    assert (out.state.state, out.state.cause) == (rt.SKIP, rt.NO_YAW) and out.ready
    out = rt.rot_step(rs, inputs(psi_raw=HOME + D(10), yaws=[]), c)
    assert (out.state.state, out.state.cause) == (rt.SKIP, rt.START_ROTATED)


# ---------------------------------------------------------------- 가짜 로봇 적분기


class FakeRobot:
    """지령 각속도를 lag 만큼 늦게, 자기 각가속(robot_alpha)으로 따라가는 J6. pose 는 period 마다."""

    def __init__(self, psi0: float, robot_alpha: float, lag: float = 0.024, period: float = 0.02):
        self.psi, self.w = psi0, 0.0  # 실제 공구 yaw·각속도
        self.alpha, self.lag, self.period = robot_alpha, lag, period
        self.cmds: list[tuple[float, float]] = [(-1.0, 0.0)]  # (시각, 지령)
        self.value: tuple[float, float] | None = (psi0, 0.0)  # (값, 그 값이 처음 온 stamp)
        self.prev: tuple[float, float] | None = None
        self.t, self.last_pub = 0.0, 0.0
        self.max_dev = 0.0  # 목표를 지나친 최대 각 (호출자가 설정한 목표 기준)

    def command(self, t: float, wz: float) -> None:
        self.cmds.append((t, wz))

    def _cmd_at(self, t: float) -> float:
        w = 0.0
        for tc, wc in self.cmds:
            if tc <= t:
                w = wc
        return w

    def advance(self, t_end: float, h: float = 0.001) -> None:
        while self.t < t_end - 1e-12:
            want = self._cmd_at(self.t - self.lag)  # 지연된 지령
            step = self.alpha * h
            self.w += max(-step, min(step, want - self.w))  # 로봇 자체 램프
            self.psi += self.w * h
            self.t += h
            if self.t - self.last_pub >= self.period - 1e-9:  # pose 발행 (joint_states 50 Hz)
                self.last_pub = self.t
                if self.value is None or abs(rt.wrap_pi(self.psi - self.value[0])) >= rt.YAW_SAME:
                    self.prev, self.value = self.value, (self.psi, self.t)


def run(
    delta_deg: float,
    robot_alpha_deg: float = 90.0,
    lag: float = 0.024,
    seconds: float = 6.0,
    c: rt.RotCfg | None = None,
    stuck: bool = False,
    stuck_at: float | None = None,
):
    """30 Hz 로 rot_step 을 돌린다. 박스 yaw = 벨트 + Δ. 반환: 상태 기록·로봇·마지막 출력."""
    c = c or cfg(max_rot=D(90))
    robot = FakeRobot(HOME, 0.0 if stuck else D(robot_alpha_deg), lag)
    rs = rt.RotState(rt.COLLECT, t_goal=0.0)
    wz, t, hist = 0.0, 0.0, []
    out = None
    while t < seconds:
        if stuck_at is not None and t >= stuck_at:
            robot.alpha, robot.w = 0.0, 0.0  # 돌다가 멈춤 (gateway 자름·걸림)
        robot.advance(t)
        w_meas = rt.omega_meas(robot.prev, robot.value, t, 0.0)
        psi_raw = robot.value[0]
        psi_est = rt.yaw_estimate(psi_raw, robot.value[1], c.lag_s, wz, t, c.extrap_max_s)
        inp = inputs(
            now=t,
            yaws=[BELT + D(delta_deg)] * 5,
            psi_raw=psi_raw,
            psi_est=psi_est,
            w_meas=w_meas,
            wz_prev=wz,
        )
        out = rt.rot_step(rs, inp, c)
        rs, wz = out.state, out.wz
        robot.command(t, wz)
        hist.append((round(t, 4), rs.state, out.warn))
        if rs.target is not None:
            over = rt.wrap_pi(robot.psi - rs.target) * math.copysign(1.0, rs.delta)
            robot.max_dev = max(robot.max_dev, over)
        t += DT
    return hist, robot, out


def first_time(hist, state: str) -> float | None:
    return next((t for t, s, _ in hist if s == state), None)


# ---------------------------------------------------------------- 9~13 rot_step 이산 시뮬


def test_matched_alpha_45_settles_on_time_without_overshoot() -> None:
    """#9 α 일치, Δ45° → SETTLING 진입 1.40~1.60 s, DONE = SETTLING + settle, 끝 오차·지나침 ≤ tol."""
    hist, robot, out = run(45)
    t_settle, t_done = first_time(hist, rt.SETTLING), first_time(hist, rt.DONE)
    assert 1.40 <= t_settle <= 1.60
    assert t_done - t_settle == pytest.approx(0.3, abs=DT + 1e-6)
    assert abs(rt.wrap_pi(robot.psi - out.state.target)) <= cfg().tol
    assert robot.max_dev <= cfg().tol
    assert out.state.cause == "" and not out.state.acc_warned


@pytest.mark.parametrize("lag", [0.024, 0.045, 0.10, 0.12])
@pytest.mark.parametrize("delta", [10.5, 12, 15, 20, 30, 45, 90])
def test_matched_alpha_never_warns(delta: float, lag: float) -> None:
    """#9b α 일치면 지연 24~120 ms, 1단계 아래쪽 각에서도 ACC_MISMATCH 없음 (r2-1 오경보 회귀).

    지연 100 ms 이상은 출발 지연·지나친 뒤 되돌아옴을 α 로 재지 않는지 (최종 재검 권장 3).
    """
    hist, _, out = run(delta, lag=lag)
    assert not any(w for _, _, w in hist)
    assert out.state.state == rt.DONE and out.state.alpha_eff == pytest.approx(cfg().alpha)


@pytest.mark.parametrize(("robot_alpha", "lo", "hi"), [(45.0, 40.0, 50.0), (10.0, 8.0, 12.0)])
def test_slow_robot_alpha_detected_by_slope(robot_alpha: float, lo: float, hi: float) -> None:
    """#10b 로봇 각가속이 느리면 두 표본 기울기로 그 값을 잡아 제동 (경고 1회)."""
    hist, robot, out = run(45, robot_alpha_deg=robot_alpha, seconds=8.0)
    assert sum(1 for _, _, w in hist if w == rt.ACC_MISMATCH) == 1
    assert lo <= math.degrees(out.state.alpha_eff) <= hi


@pytest.mark.parametrize("delta", [15, 20, 45])
def test_slow_robot_overshoot_bounded(delta: float) -> None:
    """#10 로봇 α 10·설정 90: 경고 뒤 끝이 DONE 또는 STOPPING(TIMEOUT)→FALLBACK, 지나침 ≤ 3°."""
    hist, robot, out = run(delta, robot_alpha_deg=10.0, seconds=10.0)
    assert out.state.state in (rt.DONE, rt.FALLBACK)
    assert robot.max_dev <= D(3)


def test_stall_then_stop_confirm_then_fallback() -> None:
    """#11 로봇이 안 돎 → stall_s 뒤 STOPPING(각속도 즉시 0) → 2틱 정지 확인 → FALLBACK, 그동안 ready 거짓."""
    c = cfg(max_rot=D(90))
    rs = rt.RotState(rt.COLLECT, t_goal=0.0)
    t, wz, seen = 0.0, 0.0, []
    while t < 1.2:
        held = t > 0.2  # 값이 0.15 s 넘게 그대로 → w_meas 0
        inp = inputs(now=t, psi_raw=HOME, psi_est=HOME, w_meas=0.0 if held else None, wz_prev=wz)
        out = rt.rot_step(rs, inp, c)
        if out.state.state == rt.STOPPING:
            assert out.wz == 0.0 and not out.ready and out.z_floor is not None
        seen.append(out.state.state)
        rs, wz = out.state, out.wz
        t += DT
    assert rt.STOPPING in seen and seen[-1] == rt.FALLBACK and rs.cause == rt.STALL
    assert rs.t_done is not None


def test_stall_after_partial_rotation_uses_moving_window() -> None:
    """1° 이상 돈 뒤 멈춰도 stall_s 안팎에 STALL — TIMEOUT(45° ≈ 2.6 s)까지 기다리지 않는다 (학민 #54 리뷰 5)."""
    hist, robot, out = run(45, stuck_at=0.5)
    t_stall = next(t for t, s, _ in hist if s == rt.STOPPING)
    assert out.state.cause == rt.STALL and out.state.state == rt.FALLBACK
    assert 0.5 + cfg().stall_s - DT <= t_stall <= 0.5 + cfg().stall_s + 0.2  # 멈춘 뒤 ≈ stall_s
    assert abs(rt.wrap_pi(robot.psi - HOME)) > D(1)  # 실제로 조금 돌았던 경우


def test_stopping_cap_when_motion_unknown() -> None:
    """측정 각속도를 계속 모르면(pose 지터·끊김) STOP_CAP 뒤 경고와 함께 FALLBACK (학민 #54 리뷰 4)."""
    c = cfg()
    rs = rt.RotState(rt.STOPPING, home=HOME, cause=rt.STALL, t_start=0.0)
    t = 0.0
    while t < rt.STOP_CAP - DT:
        out = rt.rot_step(rs, inputs(now=t, w_meas=None), c)
        assert out.state.state == rt.STOPPING and out.wz == 0.0 and not out.ready
        rs, t = out.state, t + DT
    out = rt.rot_step(rs, inputs(now=rt.STOP_CAP + 0.001, w_meas=None), c)
    assert out.state.state == rt.FALLBACK and out.warn == rt.STOP_UNCONFIRMED and out.ready
    assert out.state.cause == rt.STALL and out.state.stop_move_t is None  # 원래 원인은 그대로


def test_stopping_never_proceeds_while_measured_moving() -> None:
    """측정이 "아직 돈다"(20°/s)면 상한이 지나도 진행하지 않고 0 유지 — 서면 정지 2틱 뒤 FALLBACK (재리뷰)."""
    c = cfg()
    rs = rt.RotState(rt.STOPPING, home=HOME, cause=rt.TIMEOUT, t_start=0.0)
    t = 0.0
    while t < 3 * rt.STOP_CAP:  # 각가속이 느린 손목: 오래 돈다
        out = rt.rot_step(rs, inputs(now=t, w_meas=D(20)), c)
        assert (
            out.state.state == rt.STOPPING and out.wz == 0.0 and not out.ready and out.warn is None
        )
        assert out.z_floor is not None  # 그동안 z 하한(윗면 +50)도 유지
        rs, t = out.state, t + DT
    out = rt.rot_step(rs, inputs(now=t, w_meas=0.0), c)
    out = rt.rot_step(out.state, inputs(now=t + DT, w_meas=0.0), c)
    assert out.state.state == rt.FALLBACK and out.warn is None and out.ready  # 정상 정지 확인
    # 돌다가 측정이 끊기면: 마지막으로 돈다고 잰 뒤 STOP_CAP 이 지나야 진행
    rs = rt.RotState(rt.STOPPING, home=HOME, cause=rt.TIMEOUT, t_start=0.0)
    rs = rt.rot_step(rs, inputs(now=0.5, w_meas=D(20)), c).state
    held = rt.rot_step(rs, inputs(now=0.5 + rt.STOP_CAP - 0.01, w_meas=None), c)
    assert held.state.state == rt.STOPPING
    went = rt.rot_step(held.state, inputs(now=0.5 + rt.STOP_CAP, w_meas=None), c)
    assert went.state.state == rt.FALLBACK and went.warn == rt.STOP_UNCONFIRMED


def test_stopping_waits_for_inertia() -> None:
    """#12 0 지령 뒤에도 로봇이 감속하며 도는 동안 STOPPING 유지 (관성)."""
    c = cfg()
    rs = rt.RotState(rt.STOPPING, cause=rt.TIMEOUT, home=HOME, t_start=0.0)
    for k in range(10):
        out = rt.rot_step(rs, inputs(now=k * DT, w_meas=D(20) - k * D(1)), c)  # 아직 돈다
        assert out.state.state == rt.STOPPING and out.wz == 0.0
        rs = out.state
    out = rt.rot_step(rs, inputs(now=1.0, w_meas=0.0), c)
    out = rt.rot_step(out.state, inputs(now=1.0 + DT, w_meas=0.0), c)
    assert out.state.state == rt.FALLBACK


def test_settling_drift_and_cap() -> None:
    """#13·#19 정착 중 밀려도 쫓지 않고 DONE + settle_drift, 계속 움직이면 상한에서 SETTLE_TIMEOUT."""
    c = cfg()
    rs = rt.RotState(rt.SETTLING, home=HOME, target=HOME + D(30), still_since=0.0, settle_start=0.0)
    out = rt.rot_step(rs, inputs(now=0.31, psi_raw=HOME + D(27), w_meas=0.0), c)
    assert out.state.state == rt.DONE and out.state.settle_drift and out.wz == 0.0
    assert rt.end_cause(out.state, HOME + D(27), c.tol) == rt.RETURN_INCOMPLETE  # 돌아간 채 끝
    assert rt.end_cause(out.state, HOME, c.tol) == rt.SETTLE_DRIFT  # 되돌아왔으면 정착 밀림만
    moving = rt.rot_step(rs, inputs(now=1.0, w_meas=D(5)), c)
    assert (moving.state.state, moving.state.cause) == (rt.DONE, rt.SETTLE_TIMEOUT)


@pytest.mark.parametrize("state", [rt.ROTATING, rt.SETTLING])
def test_end_cause_cancel_mid_rotation(state: str) -> None:
    """돌다가(ROTATING·SETTLING) 취소로 끝나도 손목이 기준에서 벗어났으면 RETURN_INCOMPLETE (최종 재검)."""
    rs = rt.RotState(state, home=HOME)
    assert rt.end_cause(rs, HOME + D(9.6), cfg().tol) == rt.RETURN_INCOMPLETE
    assert rt.end_cause(rs, HOME, cfg().tol) == ""  # 아직 거의 안 돌았으면 원인 없음
    skip = rt.RotState(rt.SKIP, home=HOME, cause=rt.START_ROTATED)
    assert rt.end_cause(skip, HOME + D(9.6), cfg().tol) == rt.START_ROTATED  # 안 돈 goal 그대로


def test_timeout_uses_cfg_alpha_not_alpha_eff() -> None:
    """#19 TIMEOUT 상한은 설정 α 기준 — 측정 α 가 작아도 늘어나지 않는다 (r2-8)."""
    c = cfg()
    rs = rt.RotState(
        rt.ROTATING, home=HOME, target=HOME + D(45), delta=D(45),
        t_start=0.0, psi_start=HOME, alpha_eff=D(5),
    )  # fmt: skip
    limit = rt.TIMEOUT_K * rt.expected_time(D(45), c.w_max, c.alpha) + rt.TIMEOUT_ADD
    out = rt.rot_step(rs, inputs(now=limit + 0.01, psi_raw=HOME + D(20), w_meas=D(10)), c)
    assert (out.state.state, out.state.cause) == (rt.STOPPING, rt.TIMEOUT)


# ---------------------------------------------------------------- 14·20 되돌리기


def test_return_only_lift_verify_high_and_once() -> None:
    """#14·#20 LIFT·VERIFY·높이 조건, 개방 대기 후퇴 제외, SKIP 은 안 되돌림, 실패 뒤 다시 안 함, rot_time 불변."""
    c = cfg()
    done = rt.RotState(rt.DONE, home=HOME, target=HOME + D(30), t_start=0.0, t_done=1.8)
    rot = HOME + D(30)
    assert rt.rot_step(done, inputs(phase="TRACK", psi_raw=rot), c).state.state == rt.DONE
    low = inputs(phase="LIFT", psi_raw=rot, tcp_z=0.105)
    assert rt.rot_step(done, low, c).state.state == rt.DONE  # 윗면 +5 — 아직 낮다
    hold = inputs(phase="LIFT", retreat=True, hold_z=True, psi_raw=rot)
    assert rt.rot_step(done, hold, c).state.state == rt.DONE
    out = rt.rot_step(done, inputs(phase="VERIFY", psi_raw=rot, psi_est=rot), c)
    assert out.state.state == rt.RETURNING and out.wz < 0.0  # 원래 각 쪽으로
    skip = rt.RotState(rt.SKIP, cause=rt.START_ROTATED, home=HOME)
    assert rt.rot_step(skip, inputs(phase="LIFT", psi_raw=rot), c).state.state == rt.SKIP
    stopped = replace(out.state, state=rt.STOPPING, cause=rt.RETURN_STALL)
    fb = rt.rot_step(stopped, inputs(phase="LIFT", psi_raw=rot, w_meas=0.0), c)
    fb = rt.rot_step(fb.state, inputs(phase="LIFT", psi_raw=rot, w_meas=0.0), c)
    assert fb.state.state == rt.FALLBACK and fb.state.t_done == 1.8  # 덮지 않음
    again = rt.rot_step(fb.state, inputs(phase="LIFT", psi_raw=rot), c)
    assert again.state.state == rt.FALLBACK  # ret_tried — 다시 안 함
    back = rt.rot_step(out.state, inputs(phase="LIFT", psi_raw=HOME, psi_est=HOME), c)
    assert back.state.state == rt.RETURNED and back.wz == 0.0


def test_retry_prepare_keeps_done_and_ready() -> None:
    """#14 재시도(PREPARE 로 돌아감)는 되돌리기 조건 밖 → DONE 유지, 정렬 허용."""
    rs = rt.RotState(rt.DONE, home=HOME, target=HOME + D(30), t_start=0.0, t_done=1.8)
    out = rt.rot_step(rs, inputs(phase="PREPARE", psi_raw=HOME + D(30)), cfg())
    assert out.state.state == rt.DONE and out.ready and out.wz == 0.0


# ---------------------------------------------------------------- 상태 공통·로그


def test_hold_floor_ready_and_first_tick() -> None:
    """COLLECT→ROTATING 첫 틱에 지령이 나오고 z 하한이 걸리며 정렬은 막힌다."""
    c = cfg(max_rot=D(90))
    out = rt.rot_step(rt.RotState(rt.COLLECT, t_goal=0.0), inputs(), c)
    assert out.state.state == rt.ROTATING and not out.ready
    assert out.z_floor == pytest.approx(0.10 + 0.05)
    assert out.wz == pytest.approx(c.alpha * DT)  # 가속 한도에서 시작
    assert math.degrees(out.state.target - HOME) == pytest.approx(30)


def test_phase_exit_stops_immediately() -> None:
    """ROTATING 중 phase 가 PREPARE·TRACK 을 벗어나면 STOPPING, 각속도 즉시 0."""
    rs = rt.RotState(
        rt.ROTATING, home=HOME, target=HOME + D(30), delta=D(30),
        t_start=0.0, psi_start=HOME, alpha_eff=D(90),
    )  # fmt: skip
    out = rt.rot_step(rs, inputs(phase="DESCEND", wz_prev=D(40)), cfg())
    assert (out.state.state, out.state.cause, out.wz) == (rt.STOPPING, rt.PHASE, 0.0)
    assert out.z_floor is None  # DESCEND 에는 z 하한을 걸지 않는다


def test_log_values_keys_and_off() -> None:
    """로그 키 13개, 회전 꺼짐이면 전부 None, 끝 틱 RETURN_INCOMPLETE·남은 각."""
    assert rt.log_values(None, 0.0, None, None, None, False, None, D(1.5)) == dict.fromkeys(
        rt.ROT_LOG_KEYS
    )
    rs = rt.RotState(
        rt.DONE, home=HOME, target=HOME + D(30), delta=D(30), box_target=D(30),
        t_start=0.0, t_done=1.8, n=5, rbar=1.0,
    )  # fmt: skip
    v = rt.log_values(rs, 0.0, 0.0, HOME + D(30), HOME + D(30), True, None, D(1.5))
    assert tuple(v) == rt.ROT_LOG_KEYS
    assert v["rot_cause"] == rt.RETURN_INCOMPLETE and v["rot_time_s"] == pytest.approx(1.8)
    assert v["rot_delta_deg"] == pytest.approx(30) and v["rot_err_deg"] == pytest.approx(0)
    assert v["rot_end_left_deg"] == pytest.approx(30)  # 끝 틱: 손목이 기준에서 +30° 남음
    mid = rt.log_values(rs, 0.0, 0.0, HOME + D(30), HOME + D(30), False, None, D(1.5))
    assert mid["rot_end_left_deg"] is None  # 끝 틱이 아니면 null
    back = rt.log_values(rs, 0.0, 0.0, HOME + D(-100), None, True, None, D(1.5))
    assert back["rot_end_left_deg"] == pytest.approx(-100)  # − 쪽(flip)도 감아서 부호 유지


def test_no_home_ref_means_no_rotation() -> None:
    """주관 검수 a: 유효한 pose 로 정한 기준이 없으면 지금 자세로 대신하지 않고 NO_POSE_YAW 로 돌리지 않는다."""
    c = cfg()
    assert rt.pre_checks(inputs(home_ref=None), c) == rt.NO_POSE_YAW
    out = rt.rot_step(rt.RotState(rt.COLLECT, t_goal=0.0), inputs(home_ref=None), c)
    assert (out.state.state, out.state.cause, out.state.home) == (rt.SKIP, rt.NO_POSE_YAW, None)
    assert out.wz == 0.0 and out.ready


def test_omega_meas_fresh_parameter() -> None:
    """주관 검수 c: "값 그대로 = 정지" 를 믿는 pose 수신 나이를 파라미터로 (pose 가 느린 소스 대응)."""
    prev, cur = (0.0, 1.0), (0.1, 1.05)
    assert rt.omega_meas(prev, cur, 1.25, 0.08) is None  # 기본 0.05 — 80 ms 전 수신은 끊김으로 본다
    assert rt.omega_meas(prev, cur, 1.25, 0.08, fresh_s=0.1) == 0.0  # 10 Hz 소스면 0.1 로
