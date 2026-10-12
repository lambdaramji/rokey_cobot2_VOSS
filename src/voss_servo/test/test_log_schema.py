"""log_schema.py 시험 (ROS 없이)."""

import json
import math
from datetime import datetime

import pytest

from voss_servo import log_schema as ls


def sample_values() -> dict:
    """틱 키 전부에 값을 넣은 예 (kind 제외)."""
    values = {k: None for k in ls.TICK_FIELDS if k != "kind"}
    values.update(goal_id="g1", track_id=7, attempt=1, phase="TRACK", stopping=False)
    values.update(position_base_m=[0.1, -0.2, 0.08], cmd_vel_mps=[0.0, 0.0, 0.0])
    values.update(
        gripper={"ok": True, "width_actual_mm": 40.2, "grip_detected": True, "message": "OK"}
    )
    return values


def test_tick_has_every_schema_key() -> None:
    record = ls.make_tick(**sample_values())
    assert tuple(record) == ls.TICK_FIELDS  # 키 전부, 정해진 순서
    assert record["kind"] == "tick"


def test_missing_key_raises() -> None:
    values = sample_values()
    del values["box_rx_s"]
    with pytest.raises(ValueError, match="box_rx_s"):
        ls.make_tick(**values)


U9C_TICK_KEYS = {
    "box_u_px", "box_v_px", "obs_rx_age_s", "other_box_rx_age_s", "box_pub_count",
    "tcp_vel_meas_mps", "stall_ticks", "belt_speed_est_mps", "belt_speed_est_span_s", "cause_fsm",
    *ls.PHASE_T_KEYS.values(),
}  # fmt: skip
U9C_ATTEMPT_KEYS = U9C_TICK_KEYS - {
    "box_u_px", "box_v_px", "obs_rx_age_s", "tcp_vel_meas_mps"
}  # fmt: skip


def test_u9c_keys_present_and_counts() -> None:
    """U9-c 새 키 16개(틱)·12개(시도), obs_age_s 이름 유지 (10/10 로그 호환)."""
    assert U9C_TICK_KEYS <= set(ls.TICK_FIELDS) and len(U9C_TICK_KEYS) == 16
    assert U9C_ATTEMPT_KEYS <= set(ls.ATTEMPT_FIELDS) and len(U9C_ATTEMPT_KEYS) == 12
    assert "obs_age_s" in ls.TICK_FIELDS
    assert (len(ls.TICK_FIELDS), len(ls.ATTEMPT_FIELDS)) == (74, 34)  # U9b 후퇴 4키 포함
    assert len(set(ls.TICK_FIELDS)) == len(ls.TICK_FIELDS)  # 중복 키 없음
    assert list(ls.PHASE_T_KEYS) == ["PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY"]


def test_attempt_is_subset_of_tick() -> None:
    tick = ls.make_tick(**sample_values())
    record = ls.to_attempt(tick, ls.GOAL_END)
    assert set(record) <= set(ls.TICK_FIELDS)
    assert record["kind"] == "attempt" and record["event"] == ls.GOAL_END
    assert record["gripper"]["message"] == "OK"  # 그리퍼 응답의 message 도 남는다


def test_json_round_trip_without_nan() -> None:
    values = sample_values()
    values["error_m"] = [math.nan, 0.0, math.inf]  # 계산 실패 값이 섞여도
    line = ls.to_json_line(ls.make_tick(**values))
    assert "NaN" not in line and "Infinity" not in line
    assert json.loads(line)["error_m"] == [None, 0.0, None]


def test_writer_appends_lines(tmp_path) -> None:
    ticks, attempts = ls.log_paths(str(tmp_path / "servo"), datetime(2026, 10, 8, 9, 30, 0))
    assert ticks.name == "servo_ticks_20261008_093000.jsonl" and ticks.is_absolute()
    writer = ls.JsonlWriter(ticks)
    assert not ticks.exists()  # 처음 쓸 때까지 파일을 만들지 않는다
    tick = ls.make_tick(**sample_values())
    writer.write(tick)
    writer.write(tick)
    writer.close()
    lines = ticks.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["track_id"] == 7


def test_u9b_retreat_keys_in_tick_and_attempt() -> None:
    """U9b 후퇴·재시도 4키: 틱·시도 둘 다, grasped 바로 뒤 순서 (U9b-dd 5절)."""
    keys = ["retreat", "retreat_reason", "retreat_done", "retry_room_ok"]
    for fields in (ls.TICK_FIELDS, ls.ATTEMPT_FIELDS):
        i = fields.index("grasped")
        assert list(fields[i + 1 : i + 5]) == keys
