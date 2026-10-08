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
