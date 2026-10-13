"""diagnose.py 진단 계산 시험 (ROS 없이). 목록은 design/U9c-dd.md 7절."""

import pytest

from voss_servo import diagnose as dg

# ---------------------------------------------------------------- lost_cause (DD 3절, D1)

MY_RX = 100.0  # 내 트랙 마지막 수신 시각


def test_no_publisher_is_vision_down() -> None:
    assert dg.lost_cause(0, MY_RX, None, 0) == dg.VISION_DOWN


def test_publisher_unknown_does_not_blame_vision() -> None:
    assert dg.lost_cause(None, MY_RX, None, 0) is None  # 조회 실패는 0 으로 치지 않는다


def test_other_track_cut_same_frame_is_vision_down() -> None:
    """재검 F2 회귀: id 순 발행으로 다른 트랙이 1 ms 늦게 와도 동시 끊김이다."""
    assert dg.lost_cause(1, MY_RX, MY_RX + 0.001, 0) == dg.VISION_DOWN


@pytest.mark.parametrize(
    ("other_rx", "expected"),
    [
        # 경계 0.2 s 바로 안·밖 (정확히 0.2 는 float 뺄셈 오차로 시험하지 않는다)
        (MY_RX - 0.1999, dg.VISION_DOWN),
        (MY_RX + 0.1999, dg.VISION_DOWN),
        (MY_RX - 0.2001, None),  # 다른 트랙이 먼저 사라짐 (정상 이탈)
        (MY_RX + 0.2001, None),  # 다른 트랙이 더 오래 보였다
        (MY_RX + 0.6, None),  # 다른 트랙은 지금도 옴
    ],
)
def test_simultaneous_loss_boundary(other_rx, expected) -> None:
    assert dg.lost_cause(1, MY_RX, other_rx, 0) == expected


def test_simultaneous_exact_boundary() -> None:
    """경계 0.2 s 는 동시 (≤). 0.0 과 0.2 는 float 로 정확해 `<` 돌연변이를 잡는다 (재검 R7)."""
    assert dg.lost_cause(1, 0.0, 0.2, 0) == dg.VISION_DOWN


def test_single_box_stays_fsm_cause() -> None:
    """D1: 박스 1개(다른 트랙 없음)는 판단하지 않는다 → 노드는 BOX_MISSING 유지."""
    assert dg.lost_cause(1, MY_RX, None, 0) is None


def test_my_track_never_received_skips_simultaneous_rule() -> None:
    assert dg.lost_cause(1, None, MY_RX, 0) is None


@pytest.mark.parametrize(("stall_n", "expected"), [(10, dg.ROBOT_STALLED), (9, None)])
def test_stall_boundary(stall_n, expected) -> None:
    assert dg.lost_cause(1, MY_RX, None, stall_n) == expected


def test_vision_down_wins_over_stall() -> None:
    assert dg.lost_cause(0, MY_RX, None, 50) == dg.VISION_DOWN
    assert dg.lost_cause(1, MY_RX, MY_RX, 50) == dg.VISION_DOWN


# ---------------------------------------------------------------- measured_velocity (DD 4.1)


def test_velocity_from_two_values() -> None:
    v = dg.measured_velocity(((0.0, 0.0, 0.2), 10.0), ((0.0048, 0.0, 0.195), 10.1), 10.15, 0.2)
    assert v == pytest.approx([0.048, 0.0, -0.05])


def test_value_held_too_long_is_zero() -> None:
    v = dg.measured_velocity(((0.0, 0.0, 0.2), 10.0), ((0.0048, 0.0, 0.2), 10.1), 10.31, 0.2)
    assert v == [0.0, 0.0, 0.0]  # 0.21 s 동안 값이 그대로 = 멈춤


def test_first_change_after_long_hold_is_unknown() -> None:
    """재검 R1: goal 전 60 s 정지 뒤 첫 변화는 dt 가 정지 기간 전체라 속도 ≈ 0 이 된다 → 모름(None)."""
    prev, cur = ((0.0, 0.0, 0.2), 0.0), ((0.0001, 0.0, 0.2), 60.0)
    assert dg.measured_velocity(prev, cur, 60.01, 0.2) is None


def test_velocity_unknown_cases() -> None:
    cur = ((0.0, 0.0, 0.2), 10.0)
    assert dg.measured_velocity(None, None, 10.0, 0.2) is None  # pose 없음
    assert dg.measured_velocity(None, cur, 10.05, 0.2) is None  # 값 하나뿐
    assert dg.measured_velocity(cur, cur, 10.05, 0.2) is None  # stamp 같음


# ---------------------------------------------------------------- stall_count (DD 4.2)


def test_stall_count_rules() -> None:
    assert dg.stall_count(3, 0.048, 0.0) == 4  # 명령은 있는데 안 움직임
    assert dg.stall_count(3, 0.048, 0.012) == 0  # 0.25 × 0.048 = 0.012 → 움직인 것으로
    assert dg.stall_count(3, 0.048, 0.0119) == 4
    assert dg.stall_count(3, 0.009, 0.0) == 0  # 명령이 작으면 판단 안 함
    assert dg.stall_count(0, 0.01, 0.0) == 1  # 경계: 0.01 은 판단한다 (≥, 재검 R7)
    assert dg.stall_count(3, 0.048, None) == 0  # 측정 모름


def ramp_position(t: float, acc: float = 0.1, v_max: float = 0.048) -> float:
    """0 에서 가속 acc 로 v_max 까지 올린 뒤 일정 속도로 간 거리."""
    t_ramp = v_max / acc
    if t <= t_ramp:
        return 0.5 * acc * t * t
    return 0.5 * acc * t_ramp * t_ramp + v_max * (t - t_ramp)


def ramp_stall_max(lag: float, step: float, rate: float = 30.0) -> int:
    """정상 출발(명령 램프 + 로봇 응답 지연 + pose 값 계단)에서 최대 연속 stall 틱."""
    dt = 1.0 / rate
    n, worst = 0, 0
    prev_val, cur_val, last_slot = None, None, None
    for k in range(120):
        t = k * dt
        slot = int(t / step + 1e-9)  # pose 값이 바뀌는 칸 (service 0.1 s, joint_states 0.02 s)
        if slot != last_slot:
            x = ramp_position(max(t - lag, 0.0))  # 로봇은 명령보다 lag 늦게 같은 램프
            if cur_val is None or x != cur_val[0][0]:
                prev_val, cur_val = cur_val, ((x, 0.0, 0.0), t)
            last_slot = slot
        cmd = min(0.1 * max(t - dt, 0.0), 0.048)  # 직전 틱에 발행한 명령 크기
        v = dg.measured_velocity(prev_val, cur_val, t, dg.POSE_HOLD_MAX_S)
        n = dg.stall_count(n, cmd, dg.speed_of(v))
        worst = max(worst, n)
    return worst


@pytest.mark.parametrize(("lag", "step"), [(0.062, 0.1), (0.23, 0.1), (0.3, 0.1), (0.062, 0.02)])
def test_ramp_start_does_not_reach_stall_threshold(lag, step) -> None:
    """재검 램프 시뮬 회귀: 정상 출발에서 연속 stall 이 N(10) 에 못 미친다 (goal 전 정지 포함, R1)."""
    assert ramp_stall_max(lag, step) < dg.STALL_TICKS_N


def test_ramp_sim_detects_real_stall() -> None:
    """시뮬 자체 확인: 로봇이 아예 안 따라오면(지연 무한) N 을 넘는다."""
    assert ramp_stall_max(lag=99.0, step=0.1) >= dg.STALL_TICKS_N


# ---------------------------------------------------------------- speed_warn_step (DD 4.4, B안)

SET = 0.048


def run_warn(est: float, n: int, span: float = 2.5, new_obs: bool = True):
    run, warned, fires = 0, False, 0
    for _ in range(n):
        run, fire = dg.speed_warn_step(run, warned, est, SET, span, new_obs, dg.SPEED_WARN_RATIO)
        if fire:
            fires += 1
            warned = True
    return run, fires


def test_warn_ratio_boundary_ten_percent() -> None:
    assert run_warn(SET * 0.8999, 15)[1] == 1  # 10 % 바로 넘음 → 경고
    assert run_warn(SET * 0.9001, 50)[1] == 0  # 10 % 바로 안 → 경고 없음
    assert run_warn(SET * 0.979, 50)[1] == 0  # B안: 2 % 차이는 경고 없음 (goal 끝 INFO 만)


def test_warn_needs_m_consecutive_and_fires_once() -> None:
    assert run_warn(SET * 0.8, 14)[1] == 0
    assert run_warn(SET * 0.8, 15)[1] == 1
    assert run_warn(SET * 0.8, 60)[1] == 1  # goal 당 한 번


def test_warn_short_span_resets() -> None:
    assert run_warn(SET * 0.8, 30, span=1.9) == (0, 0)  # 2.0 s 미만은 믿지 않는다


def test_warn_without_new_obs_keeps_run() -> None:
    """재검 F4: 새 관측이 없으면 세지도, 지우지도 않는다 (사각 뒤 같은 추정값 반복)."""
    run, fire = dg.speed_warn_step(7, False, SET * 0.8, SET, 2.5, False, dg.SPEED_WARN_RATIO)
    assert (run, fire) == (7, False)


def test_warn_unknown_estimate_resets() -> None:
    assert dg.speed_warn_step(7, False, None, SET, None, True, dg.SPEED_WARN_RATIO) == (0, False)


# ---------------------------------------------------------------- 문구


def test_speed_note_marks_two_percent() -> None:
    assert "≥ 2 %" in dg.speed_note(0.0470, SET, 3.1, 90)  # −2.1 %
    assert "≥" not in dg.speed_note(0.0476, SET, 3.1, 90)  # −0.8 %
    assert "추정 없음" in dg.speed_note(None, SET, None, 3)


def test_speed_warn_text_has_numbers() -> None:
    text = dg.speed_warn_text(0.042, SET, 2.1)
    assert "4.20 cm/s" in text and "4.80 cm/s" in text and "-12.5 %" in text
