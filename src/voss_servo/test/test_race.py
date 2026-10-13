"""DESCEND LOST 경주 시험 (ROS 없이) — design/U9a-dd.md 6절, U9a-pseudo.md 8절.

하강 궤적은 control.z_speed·clamp 를 그대로 써서 30 Hz 로 만들고, 틱마다 실제 fsm.is_vision_blind →
fsm.input_flags 를 돌린다. 마지막 박스 수신 높이(카메라가 놓친 높이)를 바꿔 가며 LOST 가 나는지 본다.
"""

import numpy as np
import pytest

from voss_servo import control, fsm

TOP = 0.1008  # 박스 윗면 z (m, 현장 고정 평면)
START_DZ = 0.0405  # DESCEND 시작 높이 (현장 +40.4~41.1 mm)
GRASP_DZ = -0.019  # 파지 높이
BELT = 0.048  # 벨트 속도 m/s
DT = 1.0 / 30.0  # 틱 간격
LOST = 0.5  # input.lost_timeout_s
STALE = 0.3  # input.stale_timeout_s
KP_Z, V_DOWN, V_MAX, A_MAX, TOL = 1.5, 0.05, 0.08, 0.1, 0.002  # 시연 값


def descend_track() -> list[tuple[float, float]]:
    """DESCEND 시작 → 파지 높이까지 틱별 (경과 s, TCP z m)."""
    z = TOP + START_DZ  # 접근 높이에서 시작
    # xy 는 이미 벨트 FF 로 움직이는 중 (v=0 으로 시작하면 현장과 1~2틱 어긋남, 재검 r2)
    v = np.array([BELT, 0.0, 0.0])
    t, out = 0.0, []
    while z > TOP + GRASP_DZ + TOL and t < 5.0:
        vz = control.z_speed(TOP + GRASP_DZ, z, KP_Z, V_DOWN, 0.0)  # 하강 중 위로는 안 간다
        v, _ = control.clamp(np.array([BELT, 0.0, vz]), v, V_MAX, A_MAX, DT)  # 속도·가속 상한
        z += float(v[2]) * DT  # 한 틱 이동
        t += DT
        out.append((t, z))
    return out


def crossing_t(track, above_mm: float) -> float:
    """TCP 가 윗면 + above_mm 를 처음 지나는 시각."""
    return next(t for t, z in track if (z - TOP) * 1000.0 <= above_mm)


def replay(last_rx_above_mm: float, cutoff_mm: float):
    """틱마다 사각 → 입력 끊김. 반환 (LOST 났나, 사각 진입 t, 여유 s)."""
    track = descend_track()
    last_rx = crossing_t(track, last_rx_above_mm)  # 카메라가 이 높이에서 놓쳤다
    blind, prev_age = False, 0.0  # 첫 틱부터 사각이어도 예외 없게
    for t, z in track:
        blind = fsm.is_vision_blind(fsm.DESCEND, z, TOP, cutoff_mm, blind)
        rx = min(t, last_rx)  # 이 틱까지 받은 마지막 메시지 시각
        lost, _, _ = fsm.input_flags(
            now=t, last_box_rx=rx, last_valid_rx=rx, latest_invalid=False,
            last_pose_rx=t, goal_start=0.0, vision_since=0.0,
            blind=blind, lost_timeout=LOST, stale_timeout=STALE,
        )  # fmt: skip
        if lost:
            return True, None, None
        if blind:
            return False, t, LOST - prev_age  # 마지막 비사각 틱의 나이로 여유를 센다
        prev_age = t - rx
    return False, None, None


def test_track_matches_field() -> None:
    # 원본 24회: +30 통과 0.467~0.500 s, +10 통과 0.867~0.900 s, GRASP 2.600~2.633 s (±1틱)
    track = descend_track()
    assert 0.467 - DT <= crossing_t(track, 30.0) <= 0.500 + DT
    assert 0.867 - DT <= crossing_t(track, 10.0) <= 0.900 + DT
    assert 2.600 - DT <= track[-1][0] <= 2.633 + DT


# 모두 사각(+30) 진입 **전**에 끊기는 입력 (+30 아래에서 끊기면 경주가 없어 여유가 늘 0.5 — 재검 r3).
# 38 = 실측 최대(+37.1)보다 1 mm 위까지 견디는지
@pytest.mark.parametrize("last_rx_mm", [38.0, 37.0, 36.7, 35.6, 33.0])
def test_race_cutoff30_no_lost(last_rx_mm) -> None:
    lost, t_blind, margin = replay(last_rx_mm, 30.0)
    assert not lost and t_blind is not None
    assert margin >= 0.2  # 지시서 목표 여유


def test_race_cutoff10_lost_regression() -> None:
    lost, _, _ = replay(37.0, 10.0)  # 회전 박스(+36~37 에서 놓침) — 옛 설정은 LOST
    assert lost


def test_true_vanish_at_approach_lost() -> None:
    # TRACK, 접근 높이에 머무는 TCP. 박스가 t=0 에 정말 사라짐 → 0.5 s 넘는 첫 틱에 LOST
    z, blind = TOP + 0.040, False
    first_lost = None
    for n in range(1, 30):
        t = n * DT
        blind = fsm.is_vision_blind(fsm.TRACK, z, TOP, 30.0, blind)
        lost, _, _ = fsm.input_flags(
            now=t, last_box_rx=0.0, last_valid_rx=0.0, latest_invalid=False,
            last_pose_rx=t, goal_start=0.0, vision_since=0.0,
            blind=blind, lost_timeout=LOST, stale_timeout=STALE,
        )  # fmt: skip
        if lost:
            first_lost = t
            break
    assert first_lost is not None and LOST < first_lost <= LOST + DT


def test_descend_dwell_within_cap() -> None:
    # 정상 하강의 사각(+30) 체류 < 사각 체류 상한 → S 가 정상에서 안 걸린다
    track = descend_track()
    dwell = track[-1][0] - crossing_t(track, 30.0)  # 약 2.13 s (실측 2.10~2.16)
    cfg = control.config_from_values(
        {
            "belt.speed_cmps": 4.8, "belt.direction_base": [1.0, 0.0, 0.0],
            "timing.latency_offset_ms": 0.0, "input.pose_lag_ms": 0.0,
            "input.pose_extrap_max_ms": 200.0, "input.blind_entry_max_age_s": 0.15,
            "control.kp_per_s": 1.0, "control.kp_z_per_s": KP_Z,
            "control.align_tol_along_mm": 3.0, "control.align_tol_cross_mm": 5.0,
            "limits.max_speed_mps": V_MAX, "limits.max_acc_mps2": A_MAX,
            "z.approach_above_top_mm": 40.0, "grasp.tcp_z_below_top_mm": 19.0,
            "z.lift_above_top_mm": 50.0, "z.descend_speed_mps": V_DOWN,
            "z.lift_speed_mps": 0.08, "z.height_tol_mm": TOL * 1000.0,
            "reach.x_min_mm": -107.0, "reach.x_max_mm": 600.0, "rate_hz": 30.0,
        }
    )  # fmt: skip
    cap = control.descend_blind_max_s(0.030, cfg)
    assert 2.0 < dwell < 2.3
    assert dwell < cap - 1.0  # 여유 1.0 s 를 빼도 아직 안쪽
