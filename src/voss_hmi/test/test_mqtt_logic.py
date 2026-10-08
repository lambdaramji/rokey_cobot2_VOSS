"""mqtt_logic 계약 시험."""

from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest

from voss_hmi.mqtt_logic import CommandError, parse_command_json


NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone(timedelta(hours=9)))


def _payload(command_type: str, args: dict, sent_at: datetime | None = None) -> str:
    data = {
        "command_id": str(uuid.uuid4()),
        "type": command_type,
        "args": args,
        "raw_text": "HMI 버튼",
        "sent_at": (sent_at or NOW).isoformat(),
    }
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize(
    "command_type,args,expected_arg",
    [
        ("start", {}, "ALL"),
        ("stop", {}, ""),
        ("resume", {}, ""),
        ("priority", {"dong": "역삼동"}, "역삼동"),
        ("answer", {"box_id": "b-01", "dong": "대치동"}, "b-01|대치동"),
        ("answer", {"box_id": "b-02", "zone": "HOLD"}, "b-02|HOLD"),
        ("reset_zone", {"zone": "RECHECK"}, "RECHECK"),
    ],
)
def test_valid_commands_are_converted_to_ros_args(command_type, args, expected_arg):
    parsed = parse_command_json(_payload(command_type, args), NOW)
    assert parsed.command == command_type
    assert parsed.arg == expected_arg


def test_non_stop_command_older_than_30_seconds_is_rejected():
    old = NOW - timedelta(seconds=31)

    with pytest.raises(CommandError) as error:
        parse_command_json(_payload("start", {}, old), NOW)

    assert error.value.code == "EXPIRED"


def test_stop_is_accepted_even_when_old():
    old = NOW - timedelta(minutes=10)
    parsed = parse_command_json(_payload("stop", {}, old), NOW)
    assert parsed.command == "stop"


@pytest.mark.parametrize(
    "command_type,args",
    [
        ("start", {"unexpected": 1}),
        ("priority", {}),
        ("priority", {"dong": ""}),
        ("answer", {"box_id": "b-01", "dong": "역삼동", "zone": "HOLD"}),
        ("answer", {"box_id": "b-01", "zone": "A"}),
        ("reset_zone", {"zone": "OBSERVE"}),
    ],
)
def test_invalid_args_are_rejected(command_type, args):
    with pytest.raises(CommandError) as error:
        parse_command_json(_payload(command_type, args), NOW)

    assert error.value.code == "INVALID_ARGS"


def test_timestamp_without_timezone_is_rejected():
    data = json.loads(_payload("start", {}))
    data["sent_at"] = "2026-10-08T14:00:00"

    with pytest.raises(CommandError) as error:
        parse_command_json(json.dumps(data), NOW)

    assert error.value.code == "INVALID_SENT_AT"


def test_non_json_payload_is_rejected():
    with pytest.raises(CommandError) as error:
        parse_command_json("{not-json", NOW)

    assert error.value.code == "INVALID_JSON"
