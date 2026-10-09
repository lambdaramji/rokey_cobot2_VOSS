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
