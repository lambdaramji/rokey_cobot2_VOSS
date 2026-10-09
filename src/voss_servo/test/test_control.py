"""control.py 제어 계산 시험 (ROS 없이). 목록·기대값은 design/U2-dd.md 5절, U2-pseudo.md 7절."""

import array
import math

import numpy as np
import pytest

from voss_servo import control, fsm

BELT = 0.048  # 벨트 속도 m/s (4.8 cm/s)
TOP = 0.10  # 박스 윗면 z m (시험용)
APPROACH = TOP + 0.040  # 접근 높이
GRASP = TOP - 0.019  # 파지 높이
LIFT = TOP + 0.050  # 들기 높이
NOW = 100.0  # 시험용 지금 시각 s


def values(**over) -> dict:
    """config_from_values 에 넣을 값 묶음 (design/U2-pseudo.md 7절 시험 설정)."""
    v = {
        "belt.speed_cmps": 4.8,
        "belt.direction_base": [1.0, 0.0, 0.0],  # 시험은 +x 로 단순하게
        "timing.latency_offset_ms": 0.0,
        "input.pose_lag_ms": 60.0,
        "input.pose_extrap_max_ms": 200.0,
        "input.blind_entry_max_age_s": 0.15,
        "control.kp_per_s": 2.0,
        "control.kp_z_per_s": 2.0,
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
        "reach.x_max_mm": 638.0,
        "rate_hz": 30.0,
    }
    v.update(over)
    return v


CFG = control.config_from_values(values())
DT = 1.0 / 30.0
BELT_V = np.array([BELT, 0.0, 0.0])


def tcp_est(x=0.0, y=0.0, z=APPROACH):
    """geometry 에 넘길 tcp_now 결과 (지평 0.06 s, 잘림 없음)."""
    return np.array([x, y, z]), 0.06, False


def geo(box=(0.0, 0.0, TOP), tcp=(0.0, 0.0, APPROACH), visible=True, age=0.05):
    """박스 관측(age 초 전 촬영)과 TCP 로 Geometry 를 만든다."""
    obs = None if box is None else np.array(box)
    stamp = None if box is None else NOW - age
    return control.geometry(tcp_est(*tcp), obs, stamp, visible, NOW, CFG)


# ------------------------------------------------------------------ 설정 변환


def test_config_from_values_units() -> None:
    cfg = control.config_from_values(values(**{"belt.direction_base": array.array("d", [0, 2, 0])}))
    assert np.allclose(cfg.belt_dir_xy, [0, 1, 0])  # 수평 성분을 다시 길이 1 로 (array.array 도)
    assert np.allclose(cfg.belt_v, [0, BELT, 0])  # cm/s → m/s
    assert cfg.pose_lag_s == pytest.approx(0.06) and cfg.pose_extrap_max_s == pytest.approx(0.2)
    assert cfg.grasp_dz == pytest.approx(-0.019)  # 윗면보다 아래 → 음수
    assert cfg.align_cross_m == pytest.approx(0.005) and cfg.dt_nominal == pytest.approx(DT)


def test_config_belt_v_has_no_z() -> None:
    cfg = control.config_from_values(values(**{"belt.direction_base": [0.995, 0.0, 0.0998]}))
    assert cfg.belt_v[2] == 0.0  # 벨트 z 성분은 버린다


# ------------------------------------------------------------------ 예측 (Δt 0·음수)


def test_predict_dt_zero_returns_obs() -> None:
    p, h, clipped = control.predict([0.1, 0.2, TOP], NOW, NOW, BELT_V, 0.0)
    assert np.allclose(p, [0.1, 0.2, TOP]) and h == 0.0 and not clipped


def test_predict_moves_with_belt() -> None:
    p, h, _ = control.predict([0.0, 0.0, TOP], NOW - 0.1, NOW, BELT_V, 0.0)
    assert p[0] == pytest.approx(0.0048) and h == pytest.approx(0.1)  # 0.1 s × 48 mm/s


def test_predict_negative_dt_clipped_and_flagged() -> None:
    p, h, clipped = control.predict([0.0, 0.0, TOP], NOW + 0.05, NOW, BELT_V, 0.0)
    assert np.allclose(p, [0.0, 0.0, TOP]) and h == 0.0 and clipped  # 미래 stamp → 0


def test_predict_latency_offset_adds() -> None:
    p, h, _ = control.predict([0.0, 0.0, TOP], NOW - 0.1, NOW, BELT_V, 0.02)
    assert h == pytest.approx(0.12) and p[0] == pytest.approx(BELT * 0.12)


def test_predict_negative_offset_floor_zero() -> None:
    p, h, clipped = control.predict([0.0, 0.0, TOP], NOW - 0.01, NOW, BELT_V, -0.05)
    assert h == 0.0 and p[0] == 0.0 and not clipped  # 과거로 되돌리지 않는다


# ------------------------------------------------------------------ 현재 TCP 외삽 (lag 0·60·상한)


def test_tcp_now_lag0_same_stamp_is_raw() -> None:
    tcp, h, capped = control.tcp_now([0.0, 0.0, 0.2], NOW, 0.0, BELT_V, NOW, 0.12)
    assert np.allclose(tcp, [0.0, 0.0, 0.2]) and h == 0.0 and not capped


def test_tcp_now_lag60_moves_2_88mm_at_48mmps() -> None:
    tcp, h, capped = control.tcp_now([0.0, 0.0, 0.2], NOW, 0.06, BELT_V, NOW, 0.12)
    assert tcp[0] == pytest.approx(0.00288) and h == pytest.approx(0.06) and not capped


def test_tcp_now_over_max_caps_at_max() -> None:
    tcp, h, capped = control.tcp_now([0.0, 0.0, 0.2], NOW - 0.07, 0.06, BELT_V, NOW, 0.12)
    assert h == pytest.approx(0.13) and capped  # 지평은 자르기 전 값으로 남긴다
    assert tcp[0] == pytest.approx(BELT * 0.12)  # 상한(120 ms)에서 멈춘 외삽 = 5.76 mm


def test_tcp_now_future_stamp_uses_lag_only() -> None:
    tcp, h, _ = control.tcp_now([0.0, 0.0, 0.2], NOW + 0.01, 0.06, BELT_V, NOW, 0.12)
    assert h == pytest.approx(0.06) and tcp[0] == pytest.approx(0.00288)


def test_geometry_box_and_pose_different_stamps() -> None:
    # 박스는 0.1 s 전 촬영, pose 는 0.02 s 전 응답 (lag 60) → 각자 지금으로 옮긴 뒤 차이
    tcp = control.tcp_now([0.0, 0.0, APPROACH], NOW - 0.02, 0.06, BELT_V, NOW, 0.12)
    g = control.geometry(tcp, np.array([0.01, 0.0, TOP]), NOW - 0.1, True, NOW, CFG)
    box_now = 0.01 + BELT * 0.1  # 14.8 mm
    tcp_x = BELT * 0.08  # 3.84 mm
    assert g.err_along == pytest.approx(box_now - tcp_x)


# ------------------------------------------------------------------ 영역 끝


def test_in_reach_boundaries() -> None:
    assert control.in_reach(-0.107, -0.107, 0.638) is None  # 경계는 구간 안
    assert control.in_reach(0.638, -0.107, 0.638) is None
    assert control.in_reach(-0.107 - 1e-6, -0.107, 0.638) == "X_MIN"
    assert control.in_reach(0.638 + 1e-6, -0.107, 0.638) == "X_MAX"


def test_geometry_reach_uses_corrected_tcp() -> None:
    # 원본 pose 는 구간 안(637 mm)이지만 보정 TCP 는 637 + 2.88 mm → 밖
    tcp = control.tcp_now([0.637, 0.0, APPROACH], NOW, 0.06, BELT_V, NOW, 0.12)
    g = control.geometry(tcp, None, None, False, NOW, CFG)
    assert g.reach == "X_MAX"


def test_geometry_no_obs_still_reach() -> None:
    g = control.geometry(tcp_est(x=-0.2), None, None, True, NOW, CFG)
    assert g.reach == "X_MIN" and not g.has_obs and not g.visible and not g.aligned


# ------------------------------------------------------------------ 속도·가속 포화


def test_clamp_under_limits_untouched() -> None:
    v, clamped = control.clamp([0.05, 0.0, 0.0], [0.049, 0.0, 0.0], 0.08, 0.1, DT)
    assert np.allclose(v, [0.05, 0, 0]) and not clamped


def test_clamp_speed_keeps_direction() -> None:
    v, clamped = control.clamp([0.06, 0.08, 0.0], [0.048, 0.064, 0.0], 0.08, 10.0, DT)
    assert np.linalg.norm(v) == pytest.approx(0.08) and clamped
    assert v[1] / v[0] == pytest.approx(0.08 / 0.06)  # 방향은 그대로


def test_clamp_acc_limits_change() -> None:
    v, clamped = control.clamp([0.05, 0.0, 0.0], [0.0, 0.0, 0.0], 0.08, 0.1, DT)
    assert v[0] == pytest.approx(0.1 * DT) and clamped  # 첫 틱 3.33 mm/s


def test_clamp_speed_and_acc_both() -> None:
    v, clamped = control.clamp([0.2, 0.0, 0.0], [0.0, 0.0, 0.0], 0.08, 0.1, DT)
    assert v[0] == pytest.approx(0.1 * DT) and clamped  # 속도 먼저 자르고 가속으로 또 자름


def test_clamp_zero_is_immediate() -> None:
    v, clamped = control.clamp([0.0, 0.0, 0.0], [0.05, 0.0, 0.0], 0.08, 0.1, DT)
    assert not np.any(v) and not clamped  # 정지는 가속 제한 없이 바로 0


def test_effective_dt_first_tick_and_caps() -> None:
    assert control.effective_dt(None, NOW, DT) == DT  # 첫 틱
    assert control.effective_dt(NOW - 0.03, NOW, DT) == pytest.approx(0.03)
    assert control.effective_dt(NOW - 1.0, NOW, DT) == pytest.approx(2 * DT)  # 오래 멈춘 뒤


def test_effective_dt_negative_is_nominal() -> None:
    assert control.effective_dt(NOW + 0.01, NOW, DT) == DT
    assert control.effective_dt(NOW, NOW, DT) == DT


# ------------------------------------------------------------------ FF+P · Kp 0 · 기다리기


def test_ff_p_kp0_is_belt_only() -> None:
    v = control.ff_p([0.01, 0.004, 0.0], BELT_V, [1, 0, 0], 0.0, use_p=True)
    assert np.allclose(v, [BELT, 0, 0])  # Kp 0 = FF 만 (개루프)


def test_ff_p_no_p_when_not_used() -> None:
    v = control.ff_p([0.01, 0.004, 0.05], BELT_V, [1, 0, 0], 2.0, use_p=False)
    assert np.allclose(v, [BELT, 0, 0])  # z 오차도 xy 에 섞이지 않는다


def test_ff_p_box_downstream_adds() -> None:
    v = control.ff_p([0.01, 0.0, 0.0], BELT_V, [1, 0, 0], 2.0, use_p=True)
    assert v[0] == pytest.approx(BELT + 0.02)  # 박스가 앞에 있으면 더 빨리


def test_ff_p_box_upstream_waits_along_zero() -> None:
    v = control.ff_p([-0.05, 0.004, 0.0], BELT_V, [1, 0, 0], 2.0, use_p=True)
    assert v[0] == pytest.approx(0.0)  # 0.048 − 0.1 < 0 → 상류로 가지 않고 기다린다
    assert v[1] == pytest.approx(0.008)  # 가로는 P 그대로


def test_split_error_along_cross() -> None:
    d = np.array([math.cos(0.3), math.sin(0.3), 0.0])  # 기울어진 벨트 방향
    e = 0.003 * d + 0.004 * np.array([-d[1], d[0], 0.0]) + np.array([0, 0, 0.05])
    along, cross = control.split_error(e, d)
    assert along == pytest.approx(0.003) and cross == pytest.approx(0.004)  # z 는 무시


# ------------------------------------------------------------------ Z 계획


def test_z_plan_each_phase() -> None:
    assert control.z_plan(fsm.PREPARE, TOP, CFG) == pytest.approx((APPROACH, 0.05, 0.08))
    assert control.z_plan(fsm.TRACK, TOP, CFG) == pytest.approx((APPROACH, 0.05, 0.08))
    assert control.z_plan(fsm.DESCEND, TOP, CFG) == pytest.approx((GRASP, 0.05, 0.0))
    assert control.z_plan(fsm.LIFT, TOP, CFG) == pytest.approx((LIFT, 0.0, 0.08))
    assert control.z_plan(fsm.GRASP, TOP, CFG) == (None, 0.0, 0.0)
    assert control.z_plan(fsm.VERIFY, TOP, CFG) == (None, 0.0, 0.0)


def test_z_speed_caps_down_and_up() -> None:
    assert control.z_speed(0.0, 0.1, 2.0, 0.05, 0.08) == pytest.approx(-0.05)  # 내려가는 상한
    assert control.z_speed(0.1, 0.0, 2.0, 0.05, 0.08) == pytest.approx(0.08)  # 올라가는 상한
    assert control.z_speed(0.0, 0.01, 2.0, 0.05, 0.08) == pytest.approx(-0.02)  # 가까우면 P
    assert control.z_speed(0.1, 0.0, 2.0, 0.05, 0.0) == 0.0  # 하강 중 위로는 안 감


# ------------------------------------------------------------------ 전환 플래그


def test_aligned_needs_all_five() -> None:
    assert geo().aligned  # 다섯 조건 모두 참
    assert not geo(visible=False).aligned  # 안 보임
    assert not geo(box=(0.0031, 0.0, TOP), age=0.0).aligned  # 벨트 방향 3.1 mm
    assert not geo(box=(0.0, 0.0051, TOP)).aligned  # 가로 5.1 mm
    assert not geo(tcp=(0.0, 0.0, APPROACH + 0.0021)).aligned  # 높이 2.1 mm
    # 관측 나이만 어긋나게: 박스를 나이만큼 상류에 두면 예측 위치 = TCP (벨트 방향 오차 0)
    assert not geo(box=(-BELT * 0.16, 0.0, TOP), age=0.16).aligned  # 나이 0.16 s > 0.15
    assert geo(box=(-BELT * 0.14, 0.0, TOP), age=0.14).aligned  # 나이 0.14 s 는 통과


def test_at_grasp_and_lift_height() -> None:
    # 허용치 2 mm 의 안쪽·바깥쪽 (부동소수 등호 경계에 기대지 않게)
    assert geo(tcp=(0, 0, GRASP + 0.0019)).at_grasp_height
    assert not geo(tcp=(0, 0, GRASP + 0.0021)).at_grasp_height
    assert geo(tcp=(0, 0, LIFT - 0.0019)).at_lift_height
    assert not geo(tcp=(0, 0, LIFT - 0.0021)).at_lift_height


# ------------------------------------------------------------------ 단계별 명령 (HLD 3절)


def cmd(phase, g, prev=BELT_V, stopping=False, terminal=False):
    """시험용 command 호출 (직전 속도 = 벨트 속도라 가속 제한에 거의 안 걸린다)."""
    return control.command(phase, stopping, terminal, g, prev, DT, CFG)


def test_command_prepare_visible_ff_p() -> None:
    c = cmd(fsm.PREPARE, geo(box=(0.002, 0.0, TOP), age=0.0))
    assert c.rule == control.FF_P and c.vel[0] > BELT  # 박스가 앞 → 더 빨리


def test_command_prepare_not_visible_ff_xy_z_to_approach() -> None:
    c = cmd(fsm.PREPARE, geo(tcp=(0.0, 0.0, GRASP), visible=False))  # 재시도 복귀: 파지 높이
    assert c.rule == control.FF and c.vel[0] == pytest.approx(BELT, abs=0.004)  # 박스와 같이
    assert c.vel[2] > 0  # 접근 높이로 올라간다


def test_command_track_visible_ff_p_and_z() -> None:
    g = geo(box=(0.0, 0.002, TOP), tcp=(0, 0, APPROACH + 0.001), age=0.0)
    c = cmd(fsm.TRACK, g, prev=np.array([BELT, 0.003, -0.001]))  # 가속 제한에 안 걸리게
    assert c.rule == control.FF_P and not c.clamped
    assert c.vel[1] == pytest.approx(0.004)  # 가로 P 2 × 2 mm
    assert c.vel[2] == pytest.approx(-0.002)  # 접근 높이로 1 mm 내려감 × kp_z 2


def test_command_track_not_visible_ff_only() -> None:
    c = cmd(fsm.TRACK, geo(box=(0.0, 0.002, TOP), age=0.0, visible=False))
    assert c.rule == control.FF and np.allclose(c.vel[:2], [BELT, 0.0])


def test_command_descend_visible_ff_p_z_down() -> None:
    c = cmd(fsm.DESCEND, geo(), prev=np.array([BELT, 0.0, -0.05]))
    assert c.rule == control.FF_P and c.vel[2] == pytest.approx(-0.05)  # 하강 상한
    assert c.tcp_target[2] == pytest.approx(GRASP)


def test_command_descend_blind_ff_only() -> None:
    c = cmd(fsm.DESCEND, geo(box=(0.004, 0.0, TOP), visible=False), prev=[BELT, 0, -0.05])
    assert c.rule == control.FF and c.vel[0] == pytest.approx(BELT)  # 오차가 있어도 P 없음


def test_command_grasp_ff_only_z_zero() -> None:
    c = cmd(fsm.GRASP, geo(box=(0.004, 0.002, TOP), tcp=(0, 0, GRASP), visible=False))
    assert c.rule == control.FF and np.allclose(c.vel, [BELT, 0.0, 0.0])
    assert c.error[2] == 0.0  # z 목표 없음 = 높이 오차 0


def test_command_lift_xy_zero_z_up() -> None:
    c = cmd(fsm.LIFT, geo(tcp=(0, 0, GRASP), visible=False), prev=np.zeros(3))
    assert c.rule == control.ZERO and c.vel[0] == 0.0 and c.vel[1] == 0.0
    assert c.vel[2] == pytest.approx(0.1 * DT)  # 위로, 첫 틱은 가속 제한


def test_command_lift_from_belt_speed_decelerates_xy() -> None:
    c = cmd(fsm.LIFT, geo(tcp=(0, 0, GRASP), visible=False))  # 직전 = 벨트 속도
    assert 0 < c.vel[0] < BELT and c.vel[2] > 0 and c.clamped  # xy 는 서서히 줄고 z 는 오른다


def test_command_verify_zero() -> None:
    c = cmd(fsm.VERIFY, geo(tcp=(0, 0, LIFT), visible=False))
    assert not np.any(c.vel) and c.rule == control.ZERO and not c.clamped  # 바로 0


def test_command_stopping_terminal_zero() -> None:
    for kw in ({"stopping": True}, {"terminal": True}):
        c = cmd(fsm.TRACK, geo(), **kw)
        assert not np.any(c.vel) and c.rule == control.ZERO_STOP


def test_command_no_obs_zero() -> None:
    c = cmd(fsm.TRACK, geo(box=None))
    assert not np.any(c.vel) and c.rule == control.ZERO_NO_OBS


def test_command_no_pose_zero() -> None:
    c = cmd(fsm.TRACK, None)
    assert not np.any(c.vel) and c.rule == control.ZERO_NO_POSE


def test_command_upstream_box_never_moves_upstream() -> None:
    c = cmd(fsm.PREPARE, geo(box=(-0.08, 0.0, TOP), age=0.0), prev=np.zeros(3))
    assert c.vel[0] >= 0.0  # 박스가 80 mm 뒤 → 기다린다 (HLD 0절)


def test_finite_vec_rejects_nan() -> None:
    assert control.finite_vec([0.0, math.nan, 0.0]) is None
    assert control.finite_vec([0.0, math.inf, 0.0]) is None
    assert np.allclose(control.finite_vec([1, 2, 3]), [1, 2, 3])


# ------------------------------------------------------------------ r4: PR #122 학민 리뷰


def test_pose_value_stamp_keeps_first_stamp_while_value_repeats() -> None:
    # gateway service: 50 Hz 로 오지만 값은 0.1 s 마다만 바뀐다 (ADR-0010 69행)
    v = control.pose_value_stamp(None, (0.0, 0.0, 0.2), 10.00)
    v = control.pose_value_stamp(v, (0.0, 0.0, 0.2), 10.02)  # 같은 값 반복
    v = control.pose_value_stamp(v, (0.0, 0.0, 0.2), 10.08)
    assert v == ((0.0, 0.0, 0.2), 10.00)  # 처음 stamp 유지
    v = control.pose_value_stamp(v, (0.0048, 0.0, 0.2), 10.10)  # 값이 바뀐 첫 메시지
    assert v == ((0.0048, 0.0, 0.2), 10.10)


def test_repeated_pose_value_extrapolates_by_real_age() -> None:
    # 값이 10.00 에 처음 오고 10.08 까지 반복 → 지금 10.08 이면 지평 = 0.08 + lag 0.06 = 0.14
    position, stamp = control.pose_value_stamp(
        control.pose_value_stamp(None, (0.0, 0.0, 0.2), 10.00), (0.0, 0.0, 0.2), 10.08
    )
    tcp, h, capped = control.tcp_now(position, stamp, 0.06, BELT_V, 10.08, 0.18)
    assert h == pytest.approx(0.14) and not capped
    assert tcp[0] == pytest.approx(BELT * 0.14)  # 마지막 메시지 stamp 로 계산했다면 2.88 mm 에 그침


def test_grasp_floor_blocked_reach_z_min() -> None:
    # 문턱 = 윗면 − 19 + 2 mm. gateway z 하한 78 + 여유 1 = 79 mm 보다 낮으면 닿을 수 없다
    assert geo(box=(0.0, 0.0, 0.0955)).reach == "Z_MIN"  # 문턱 78.5 mm
    assert geo(box=(0.0, 0.0, 0.0965)).reach is None  # 문턱 79.5 mm
    assert geo(box=(0.0, 0.0, 0.1008)).reach is None  # 공칭 윗면 100.8 mm (파지 81.8)


def test_reach_x_before_z_min() -> None:
    g = control.geometry(tcp_est(x=0.7), np.array([0.7, 0.0, 0.09]), NOW, True, NOW, CFG)
    assert g.reach == "X_MAX"  # 둘 다 걸리면 x 가 먼저
