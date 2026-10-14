"""Sprint 2 S2-T08 hmi_bridge 쪽 (BRD v1.5, mqtt.md) — HMI palletize 명령 → Command arg, reset_zone PALLET,
PalletState → voss/pallet/state JSON. ROS·MQTT 없이."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from voss_hmi.mqtt_logic import CommandError, pallet_state_payload, parse_command_json


def command(kind: str, args: dict) -> str:
    return json.dumps({"command_id": str(uuid.uuid4()), "type": kind, "args": args, "raw_text": "HMI",
                       "sent_at": datetime.now(UTC).isoformat()})  # fmt: skip


def test_palletize_route_becomes_comma_arg() -> None:
    cmd = parse_command_json(
        command("palletize", {"route": ["역삼동", " 대치동", "청담동"]}), datetime.now(UTC)
    )
    assert (cmd.command, cmd.arg) == ("palletize", "역삼동,대치동,청담동")
    one = parse_command_json(command("palletize", {"route": ["대치동"]}), datetime.now(UTC))
    assert one.arg == "대치동"


@pytest.mark.parametrize(
    "args",
    [
        {"route": []},
        {"route": ["역삼동", "대치동", "청담동", "논현동"]},
        {"route": ["역삼동", "역삼동"]},
        {"route": "역삼동,대치동"},
        {"route": ["역삼동", ""]},
        {"route": ["역삼동,대치동"]},
        {"route": ["역삼동"], "extra": 1},
    ],
)
def test_palletize_bad_route_is_invalid_args(args) -> None:
    with pytest.raises(CommandError) as err:
        parse_command_json(command("palletize", args), datetime.now(UTC))
    assert err.value.code == "INVALID_ARGS"


def test_reset_zone_pallet() -> None:
    assert (
        parse_command_json(command("reset_zone", {"zone": "PALLET"}), datetime.now(UTC)).arg
        == "PALLET"
    )


def test_pallet_state_payload_is_plain_json() -> None:
    fields = {"run_id": "R", "state": "RUNNING", "route": ("역삼동", "대치동", "청담동"), "dongs": ("역삼동", "대치동", "청담동"),
              "load": (7, 3, 6), "overflow": (0, 3, 0), "excluded": (0, 0, 0), "overflow_warning": True,
              "total": 16, "done": 1, "failed": 0, "box_id": "S-015", "slot_state": ["DONE"] + ["PLANNED"] * 15,
              "slot_box_id": [""] * 16, "slot_dong": ["청담동"] * 16}  # fmt: skip
    out = pallet_state_payload(fields)
    assert (
        out["load"] == [7, 3, 6]
        and out["overflow_warning"] is True
        and len(out["slot_state"]) == 16
    )
    assert json.loads(json.dumps(out, ensure_ascii=False)) == out  # 그대로 직렬화된다
