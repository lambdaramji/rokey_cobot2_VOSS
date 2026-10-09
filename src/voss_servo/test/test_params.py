"""params.py 기동 검사 시험 (ROS 없이)."""

import array

from voss_servo.params import check_params, params_digest, ready_log_line


def valid_values() -> dict:
    """모든 필수 값이 들어 있는 정상 묶음 (시험용 값, 제안값 포함)."""
    return {
        "belt.speed_cmps": 4.8,
        "belt.direction_base": [0.99992, -0.01292, 0.0],
        "gripper.pre_open_mm": 90.0,
        "gripper.grasp_width_mm": 39.0,
        "gripper.force_n": 14.0,
        "timing.latency_offset_ms": 0.0,
        "config_version": 1,
        "config_sha256": "abc",
        "grasp.tcp_z_below_top_mm": 19.0,
        "grasp.hold_width_min_mm": 39.5,
        "grasp.hold_width_max_mm": 41.5,
        "reach.x_min_mm": -107.0,
        "reach.x_max_mm": 638.0,
        "control.kp_per_s": 0.0,
        "limits.max_speed_mps": 0.08,
        "limits.max_acc_mps2": 0.1,
        "z.approach_above_top_mm": 40.0,
        "z.lift_above_top_mm": 50.0,
        "z.vision_cutoff_above_top_mm": 10.0,
        "input.stale_timeout_s": 0.3,
        "input.lost_timeout_s": 0.5,
        "retry.max_attempts": 1,
        "stop_timeout_s": 1.0,
        "rate_hz": 30,
        "zero_hold_s": 0.5,
        "log.dir": "data/servo",
        # U2 제어 값 (design/U2-dd.md 2절, 제안값)
        "control.kp_z_per_s": 2.0,
        "control.align_tol_along_mm": 3.0,
        "control.align_tol_cross_mm": 5.0,
        "z.descend_speed_mps": 0.05,
        "z.lift_speed_mps": 0.08,
        "z.height_tol_mm": 2.0,
        "input.pose_lag_ms": 60.0,
        "input.pose_extrap_max_ms": 200.0,
        "input.blind_entry_max_age_s": 0.15,
    }


def test_all_valid_is_ready() -> None:
    report = check_params(valid_values())
    assert report.ready, ready_log_line(report)  # 실패하면 이유가 보이게


def test_null_value_is_missing() -> None:
    values = valid_values()
    values["control.kp_per_s"] = None  # YAML null 과 같은 뜻
    report = check_params(values)
    assert not report.ready
    assert report.missing == ["control.kp_per_s"]
    assert "control.kp_per_s" in ready_log_line(report)  # 로그에 키 이름이 나온다


def test_not_passed_is_missing() -> None:
    values = valid_values()
    del values["belt.speed_cmps"]  # launch 가 넘기지 않음
    report = check_params(values)
    assert "belt.speed_cmps" in report.missing


def test_direction_norm_half_rejected() -> None:
    values = valid_values()
    values["belt.direction_base"] = [0.5, 0.0, 0.0]  # 길이 0.5
    report = check_params(values)
    assert ("belt.direction_base", "norm 0.500") in report.invalid


def test_direction_norm_boundary_passes() -> None:
    values = valid_values()
    values["belt.direction_base"] = array.array(
        "d", [1.005, 0.0, 0.0]
    )  # ROS 배열 모양, 허용 경계 안
    assert check_params(values).ready


def test_reach_min_ge_max_rejected() -> None:
    values = valid_values()
    values["reach.x_min_mm"] = 700.0  # x_max 638 보다 큼
    names = [k for k, _ in check_params(values).invalid]
    assert "reach.x_min_mm" in names


def test_approach_inside_blind_zone_rejected() -> None:
    values = valid_values()
    values["z.approach_above_top_mm"] = 15.0  # 사각 이탈 높이 10 + 5 = 15 이하
    names = [k for k, _ in check_params(values).invalid]
    assert "z.approach_above_top_mm" in names


def test_retry_out_of_range_rejected() -> None:
    for bad in (0, 4, 1.0):  # 범위 밖, 정수 아님
        values = valid_values()
        values["retry.max_attempts"] = bad
        assert not check_params(values).ready, bad


def test_config_version_str_and_missing_keep_ready() -> None:
    values = valid_values()
    values["config_version"] = "1"  # 문자열도 허용
    assert check_params(values).ready
    del values["config_version"]  # 없어도 READY (경고는 노드가 남김)
    del values["config_sha256"]
    assert check_params(values).ready


def test_bool_is_not_a_number() -> None:
    values = valid_values()
    values["rate_hz"] = True  # True 가 1 로 섞이면 안 된다
    assert not check_params(values).ready


def test_digest_is_deterministic_and_sensitive() -> None:
    a = valid_values()
    b = dict(reversed(list(a.items())))  # 순서만 다름
    assert params_digest(a) == params_digest(b)  # 같은 값 = 같은 지문
    assert len(params_digest(a)) == 64
    b["rate_hz"] = 31
    assert params_digest(a) != params_digest(b)  # 값이 바뀌면 지문도 바뀜


def test_digest_ignores_log_dir_and_config_identity() -> None:
    a = valid_values()
    b = dict(a, **{"log.dir": "/elsewhere", "config_version": 2, "config_sha256": "zzz"})
    assert params_digest(a) == params_digest(b)  # 실행 위치·voss_config 지문은 제어 설정이 아니다


def test_null_string_from_params_file_is_missing() -> None:
    values = valid_values()
    values["control.kp_per_s"] = "null"  # --params-file 로 YAML null 이 문자열로 들어온 경우
    report = check_params(values)
    assert report.missing == ["control.kp_per_s"] and not report.invalid


# ---------------------------------------------------------------- U2 제어 값 (design/U2-dd.md 2절)

U2_KEYS = (
    "control.kp_z_per_s",
    "control.align_tol_along_mm",
    "control.align_tol_cross_mm",
    "z.descend_speed_mps",
    "z.lift_speed_mps",
    "z.height_tol_mm",
    "input.pose_lag_ms",
    "input.pose_extrap_max_ms",
    "input.blind_entry_max_age_s",
)


def invalid_keys(values: dict) -> list[str]:
    """invalid 로 걸린 키 이름 목록."""
    return [k for k, _ in check_params(values).invalid]


def test_u2_null_keys_are_missing() -> None:
    values = valid_values()
    for k in U2_KEYS:
        values[k] = None  # yaml null = 미측정
    report = check_params(values)
    assert not report.ready and sorted(report.missing) == sorted(U2_KEYS)


def test_pose_lag_zero_is_allowed() -> None:
    values = valid_values()
    values["input.pose_lag_ms"] = 0.0  # 0 = 보정 없음 (유효)
    values["input.pose_extrap_max_ms"] = 120.0  # ≥ 0 + 120
    assert check_params(values).ready


def test_max_speed_equal_gateway_rejected() -> None:  # 검사 1: gateway 100 mm/s 보다 작게
    values = valid_values()
    values["limits.max_speed_mps"] = 0.1
    assert "limits.max_speed_mps" in invalid_keys(values)


def test_max_acc_over_robot_ramp_rejected() -> None:  # 검사 2: 로봇 램프 0.1 이하
    values = valid_values()
    values["limits.max_acc_mps2"] = 0.11
    assert "limits.max_acc_mps2" in invalid_keys(values)
    values["limits.max_acc_mps2"] = 0.1  # 같으면 통과
    assert check_params(values).ready


def test_max_speed_not_above_belt_rejected() -> None:  # 검사 3: 벨트보다 빨라야 따라간다
    values = valid_values()
    values["limits.max_speed_mps"] = 0.048  # 벨트 4.8 cm/s 와 같음
    values["z.lift_speed_mps"] = 0.04
    values["z.descend_speed_mps"] = 0.04
    assert invalid_keys(values) == ["limits.max_speed_mps"]


def test_descend_over_max_speed_rejected() -> None:  # 검사 4
    values = valid_values()
    values["z.descend_speed_mps"] = 0.09
    values["control.kp_z_per_s"] = 1.0  # 검사 9 는 통과시키고
    assert invalid_keys(values) == ["z.descend_speed_mps"]


def test_lift_over_max_speed_rejected() -> None:  # 검사 5
    values = valid_values()
    values["z.lift_speed_mps"] = 0.09
    assert invalid_keys(values) == ["z.lift_speed_mps"]


def test_extrap_max_below_lag_plus_period_rejected() -> None:  # 검사 6
    values = valid_values()
    values["input.pose_extrap_max_ms"] = 179.0  # 60 + 120 = 180 미만 (값 0.1 s 갱신 + 메시지 20 ms)
    assert invalid_keys(values) == ["input.pose_extrap_max_ms"]
    values["input.pose_extrap_max_ms"] = 180.0  # 경계는 통과
    assert check_params(values).ready


def test_along_tol_over_cross_rejected() -> None:  # 검사 7: 벨트 방향이 더 엄격
    values = valid_values()
    values["control.align_tol_along_mm"] = 6.0
    assert invalid_keys(values) == ["control.align_tol_along_mm"]


def test_cross_tol_over_10_rejected() -> None:  # 검사 8: 상한 10 mm (확정)
    values = valid_values()
    values["control.align_tol_cross_mm"] = 10.5
    assert invalid_keys(values) == ["control.align_tol_cross_mm"]
    values["control.align_tol_cross_mm"] = 10.0  # 경계는 통과
    assert check_params(values).ready


def test_kp_z_times_descend_over_acc_rejected() -> None:  # 검사 9
    values = valid_values()
    values["control.kp_z_per_s"] = 2.5  # 2.5 × 0.05 = 0.125 > 0.1
    assert invalid_keys(values) == ["control.kp_z_per_s"]


def test_height_tol_reaching_blind_exit_rejected() -> None:  # 검사 10
    values = valid_values()
    values["z.height_tol_mm"] = 25.0  # 접근 40 − (사각 10 + 5) = 25 → 같으면 거부
    assert invalid_keys(values) == ["z.height_tol_mm"]


def test_direction_vertical_rejected() -> None:  # 검사 11: 길이 1 이지만 수평 성분이 없다
    values = valid_values()
    values["belt.direction_base"] = [0.0, 0.0, 1.0]
    assert invalid_keys(values) == ["belt.direction_base"]


def test_kp_z_zero_rejected() -> None:  # 개별 검사: 0 이면 높이를 못 바꾼다
    values = valid_values()
    values["control.kp_z_per_s"] = 0.0
    assert "control.kp_z_per_s" in invalid_keys(values)


def test_null_strings_in_cross_checked_keys_do_not_crash() -> None:
    # --params-file 로 belt_servo.yaml 을 그대로 주면 교차 검사 대상 키도 "null" 문자열이 된다
    values = valid_values()
    for k in (
        "z.approach_above_top_mm",
        "z.vision_cutoff_above_top_mm",
        "z.height_tol_mm",
        "limits.max_speed_mps",
        "control.kp_z_per_s",
        "input.pose_extrap_max_ms",
    ):
        values[k] = "null"
    report = check_params(values)  # 예외 없이
    assert not report.ready and not report.invalid and "z.height_tol_mm" in report.missing
