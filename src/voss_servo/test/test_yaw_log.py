"""yaw_log_values 시험 — 리허설 yaw 관측 로그 (S2-T18 0단계, 움직임 무관)."""

import math
from types import SimpleNamespace

from voss_servo.belt_servo import yaw_log_values


def test_no_box_gives_nulls() -> None:
    assert yaw_log_values(None) == (None, None)  # 트랙 메시지를 아직 못 받음


def test_old_message_without_yaw_fields_gives_nulls() -> None:
    old = SimpleNamespace(track_id=3, position_valid=True)  # S2-T16 전 BoxTrack 흉내
    assert yaw_log_values(old) == (None, None)  # 빌드 판별: yaw_valid 가 null


def test_invalid_yaw_is_not_logged_as_angle() -> None:
    box = SimpleNamespace(yaw_base=0.0, yaw_valid=False)
    assert yaw_log_values(box) == (None, False)  # 0 을 각도로 착각하지 않게


def test_valid_yaw_in_degrees() -> None:
    deg, ok = yaw_log_values(SimpleNamespace(yaw_base=math.radians(30.0), yaw_valid=True))
    assert ok is True and math.isclose(deg, 30.0)
    deg, ok = yaw_log_values(SimpleNamespace(yaw_base=-math.pi / 2 + 1e-6, yaw_valid=True))
    assert ok is True and math.isclose(deg, -90.0, abs_tol=1e-3)  # 접기 경계 근처도 그대로


def test_non_finite_yaw_keeps_valid_flag_only() -> None:
    assert yaw_log_values(SimpleNamespace(yaw_base=float("nan"), yaw_valid=True)) == (None, True)
    assert yaw_log_values(SimpleNamespace(yaw_base=float("inf"), yaw_valid=True)) == (None, True)
