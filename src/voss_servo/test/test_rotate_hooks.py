"""S2-T18 회전 연결부 시험 (ROS 없이): params·fsm·control. DD 9절 #16~#20, pseudo r2 5·6절."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
from test_control import CFG, DT, TOP, geo
from test_params import valid_values
from voss_servo.belt_servo import BeltServoNode
from voss_servo.fsm import FsmState, TickEvent
from voss_servo.params import (
    ROTATE_REQUIRED,
    check_params,
    params_digest,
    rot_cfg_from_values,
    rotate_line,
    rotate_on,
)

from voss_msgs.msg import BoxTrack
from voss_servo import control, fsm

# sim yaml 과 같은 회전 제안값 (config/belt_servo_sim.yaml rotate 블록)
ROT = {
    "rotate.deadband_deg": 4,
    "rotate.min_deg": 10,
    "rotate.max_deg": 45,
    "rotate.n_min": 5,
    "rotate.buffer_n": 15,
    "rotate.r_min": 0.97,
    "rotate.decide_max_s": 0.5,
    "rotate.start_tol_deg": 3,
    "rotate.omega_max_dps": 60,
    "rotate.alpha_dps2": 90,
    "rotate.tol_deg": 1.5,
    "rotate.omega_floor_dps": 3,
    "rotate.hold_dz_mm": 50,
    "rotate.settle_s": 0.3,
    "rotate.stall_s": 0.6,
    "rotate.still_dps": 2,
    "rotate.return_min_dz_mm": 10,
    "rotate.pose_fresh_s": 0.05,
}


def on_values(**over) -> dict:
    """회전을 켠 정상 묶음 — joint_states 짝(pose_lag 0), cutoff 30·접근 40 (현장값)."""
    v = valid_values()
    v.update(ROT)
    v.update(
        {
            "rotate.enable": True,
            "input.pose_lag_ms": 0.0,
            "z.vision_cutoff_above_top_mm": 30.0,
            "z.approach_above_top_mm": 40.0,
        }
    )
    v.update(over)
    return v


def invalid_keys(values: dict) -> list[str]:
    return [k for k, _ in check_params(values).invalid]


# ---------------------------------------------------------------- params (#18~#20)


def test_rotate_off_ready_and_digest_unchanged() -> None:
    """#18 off(키 없음·false·값만 적힘) 이면 READY 이고 sha 는 회전 키가 없을 때와 같다."""
    base = valid_values()
    assert check_params(base).ready
    sha = params_digest(base)
    with_values = {**base, **ROT, "rotate.enable": False}
    assert check_params(with_values).ready
    assert params_digest(with_values) == sha  # 튜닝 값이 적혀 있어도 off 면 같은 지문
    assert params_digest({**base, "rotate.enable": None}) == sha
    assert not rotate_on(with_values) and rotate_line(with_values) == "rotate off"


def test_rotate_on_needs_all_keys_and_bool_only() -> None:
    """#19 enable true 면 ROTATE_REQUIRED 가 null 일 때 missing, enable 은 bool 만 (문자열 "true" 거부)."""
    v = on_values()
    assert check_params(v).ready, (check_params(v).missing, check_params(v).invalid)
    assert params_digest(v) != params_digest(valid_values())  # 켜면 지문이 바뀐다
    v.pop("rotate.stall_s")
    assert check_params(v).missing == ["rotate.stall_s"]
    assert "rotate.enable" in invalid_keys(on_values(**{"rotate.enable": "true"}))
    assert not rotate_on(on_values(**{"rotate.enable": "true"}))
    assert "rotate.home_tool_yaw_deg" not in ROTATE_REQUIRED  # 선택 키


@pytest.mark.parametrize(
    ("over", "key"),
    [
        ({"rotate.hold_dz_mm": 40}, "rotate.hold_dz_mm"),  # 접근 높이와 같다
        ({"rotate.hold_dz_mm": 34, "z.approach_above_top_mm": 33.0}, "rotate.hold_dz_mm"),
        ({"rotate.min_deg": 3}, "rotate.min_deg"),  # deadband 보다 작다
        ({"rotate.max_deg": 95}, "rotate.min_deg"),  # 90 초과
        ({"rotate.n_min": 20}, "rotate.n_min"),  # buffer 보다 크다
        ({"rotate.tol_deg": 4}, "rotate.tol_deg"),  # deadband 와 같다
        ({"input.pose_lag_ms": 60.0}, "input.pose_lag_ms"),  # service 짝
        # 정지 판정 시간과 같다 (주관 검수 c)
        ({"rotate.pose_fresh_s": 0.15}, "rotate.pose_fresh_s"),
    ],
)
def test_rotate_cross_checks(over: dict, key: str) -> None:
    """#20 교차 검사 6줄 — 켰을 때만. pose_lag 60 은 joint_states 전제 위반."""
    v = on_values(**over)
    assert key in invalid_keys(v)
    off = {**v, "rotate.enable": False}
    assert key not in invalid_keys(off) or key in invalid_keys({**valid_values(), **over})


def test_pose_lag_reason_text() -> None:
    """교차 검사 사유 문구가 joint_states 전제를 말한다 (기동 로그에서 원인을 바로 알게)."""
    why = dict(check_params(on_values(**{"input.pose_lag_ms": 60.0})).invalid)
    assert "joint_states" in why["input.pose_lag_ms"]


def test_rot_cfg_units_and_belt_yaw() -> None:
    """deg → rad, mm → m, ms → s, 벨트 방향 각, home 은 선택."""
    cfg = rot_cfg_from_values(on_values(), (0.0, 1.0, 0.0))
    assert cfg.w_max == pytest.approx(math.radians(60))
    assert cfg.hold_dz == pytest.approx(0.050)
    assert cfg.belt_yaw == pytest.approx(math.pi / 2)
    assert cfg.home_fixed is None and cfg.lag_s == 0.0 and cfg.extrap_max_s == pytest.approx(0.2)
    assert cfg.pose_fresh_s == pytest.approx(0.05)
    fixed = rot_cfg_from_values(on_values(**{"rotate.home_tool_yaw_deg": -88.72}), (1.0, 0.0, 0))
    assert math.degrees(fixed.home_fixed) == pytest.approx(-88.72)
    assert "home -88.72" in rotate_line(on_values(**{"rotate.home_tool_yaw_deg": -88.72}))


# ---------------------------------------------------------------- fsm (#16)


def test_track_waits_for_rotation_then_descends() -> None:
    """#16 TRACK + aligned 라도 rot_ready 거짓이면 TRACK 유지, 참이면 DESCEND. 기본값은 지금과 같다."""
    s = FsmState(fsm.TRACK, 0, False)
    hold = fsm.step(s, TickEvent(aligned=True, rot_ready=False), 39.5, 44.0, 1)
    assert hold.state.phase == fsm.TRACK and not hold.terminal
    go = fsm.step(s, TickEvent(aligned=True, rot_ready=True), 39.5, 44.0, 1)
    assert go.state.phase == fsm.DESCEND
    assert TickEvent().rot_ready is True  # 기본 = 회전 없음
    assert fsm.step(s, TickEvent(aligned=True), 39.5, 44.0, 1).state.phase == fsm.DESCEND


def test_rotation_wait_does_not_hide_reach_or_lost() -> None:
    """회전을 기다리는 TRACK 에서도 x 끝·LOST 는 그대로 먼저 (무한 대기 없음)."""
    s = FsmState(fsm.TRACK, 0, False)
    reach = fsm.step(s, TickEvent(aligned=True, rot_ready=False, reach="X_MAX"), 39.5, 44.0, 1)
    assert reach.terminal and reach.reason == fsm.OUT_OF_REACH
    lost = fsm.step(s, TickEvent(rot_ready=False, box_lost=True), 39.5, 44.0, 1)
    assert lost.terminal and lost.reason == fsm.LOST


# ---------------------------------------------------------------- control (#17)


def test_z_floor_none_is_unchanged_and_floor_lifts_target() -> None:
    """#17 z_floor None 이면 지금과 같은 명령, 값이 있으면 PREPARE·TRACK z 목표 = max(접근, 하한)."""
    g = geo()
    prev = control.zero_cmd()
    base = control.command(fsm.TRACK, False, False, g, prev, DT, CFG)
    same = control.command(fsm.TRACK, False, False, g, prev, DT, CFG, z_floor=None)
    assert np.allclose(base.vel, same.vel) and base.rule == same.rule
    floor = TOP + 0.050
    up = control.command(fsm.TRACK, False, False, g, prev, DT, CFG, z_floor=floor)
    assert up.tcp_target[2] == pytest.approx(floor)  # 접근 +40 대신 +50
    assert up.vel[2] > base.vel[2]  # 위로 (또는 덜 내려감)
    low = control.command(fsm.TRACK, False, False, g, prev, DT, CFG, z_floor=TOP)
    assert low.tcp_target[2] == pytest.approx(base.tcp_target[2])  # 하한이 낮으면 영향 없음


# ---------------------------------------------------------------- belt_servo 회전 보조 메서드 (최종 재검 M4·M5·M12)


class _Log:
    def info(self, *_a, **_k) -> None:
        pass


class _Node:
    """BeltServoNode 의 회전 보조 메서드만 빌려 쓰는 가짜 (ROS 없이)."""

    _pose_ok = BeltServoNode._pose_ok
    _try_home_ref = BeltServoNode._try_home_ref
    _push_yaw = BeltServoNode._push_yaw
    _rot_dead_tick = BeltServoNode._rot_dead_tick

    def __init__(self) -> None:
        self._rot_cfg = rot_cfg_from_values(on_values(), (0.0, 1.0, 0.0))
        self._yaw_hist: dict = {}
        self._yaw_value, self._yaw_prev, self._tilt = None, None, None
        self._pose = None  # (msg, 수신 시각)
        self._home_ref, self._rot_ever = None, False

    def get_logger(self) -> _Log:
        return _Log()


def _box(yaw_deg: float, t: float, yaw_valid: bool = True) -> BoxTrack:
    m = BoxTrack()
    m.track_id = 3
    m.stamp.sec, m.stamp.nanosec = int(t), int(round((t - int(t)) * 1e9))
    m.yaw_base, m.yaw_valid = math.radians(yaw_deg), yaw_valid
    return m


def test_push_yaw_keeps_only_valid_frames_in_time_order() -> None:
    """yaw_valid=false·position 무효·NaN·시각 역행 프레임은 버퍼에 들어가지 않는다 (M4)."""
    n = _Node()
    n._push_yaw(_box(30, 1.0, yaw_valid=False), True)
    n._push_yaw(_box(30, 1.1), False)  # position 무효
    n._push_yaw(_box(float("nan"), 1.2), True)
    assert n._yaw_hist == {}
    n._push_yaw(_box(30, 1.3), True)
    n._push_yaw(_box(31, 1.3), True)  # 같은 stamp 반복
    n._push_yaw(_box(32, 1.2), True)  # 시각이 뒤로
    assert [round(math.degrees(y), 3) for _, y in n._yaw_hist[3]] == [30.0]


def test_home_ref_only_from_valid_fresh_pose_and_once() -> None:
    """기준 공구 yaw 는 기울기 ≤ 5°·pose 신선할 때만, 이미 있으면 안 바꾼다 (주관 검수 a, M5)."""
    n = _Node()
    n._yaw_value, n._pose = (math.radians(-88.7), 9.9), (None, 10.0)
    n._tilt = math.radians(6.0)  # 기울어짐
    n._try_home_ref(10.05)
    assert n._home_ref is None
    n._tilt = math.radians(1.0)
    n._try_home_ref(10.0 + n._rot_cfg.extrap_max_s + 0.01)  # pose 가 끊김
    assert n._home_ref is None
    n._try_home_ref(10.05)  # 유효
    assert math.degrees(n._home_ref) == pytest.approx(-88.7)
    n._yaw_value = (math.radians(-60.0), 10.1)
    n._try_home_ref(10.15)  # 한 번 정하면 그대로
    assert math.degrees(n._home_ref) == pytest.approx(-88.7)


def test_rot_dead_tick_needs_two_still_ticks() -> None:
    """예외로 끈 goal: 각속도 0, 측정 정지가 2틱 이어져야 진행 · 움직이면 다시 센다 (M12, 권장 2)."""
    n = _Node()
    ctx = SimpleNamespace(wz=0.3, rot_still_n=0, rot_io=None)
    n._yaw_prev, n._yaw_value = (0.00, 1.00), (0.02, 1.02)  # 1 rad/s 로 도는 중
    n._pose = (None, 1.02)
    assert n._rot_dead_tick(ctx, 1.03) is False and ctx.wz == 0.0
    assert ctx.rot_io[2] == pytest.approx(1.0)
    n._pose = (None, 1.30)  # 값은 그대로, pose 는 계속 온다 → 정지
    assert n._rot_dead_tick(ctx, 1.31) is False  # 1틱
    assert n._rot_dead_tick(ctx, 1.34) is True  # 2틱
    n._yaw_prev, n._yaw_value = (0.02, 1.02), (0.05, 1.36)  # 다시 움직임 (0.34 s 뒤 첫 변화 = 모름)
    n._pose = (None, 1.36)
    assert n._rot_dead_tick(ctx, 1.37) is False and ctx.rot_still_n == 0
