"""팔레타이징 검증 (verify/palletizing, BRD v1.5) 4단계 — HMI 경로(TR-PAL-01·10). mqtt.md 의 palletize·voss/pallet/state 를
hmi_bridge 가 따르는지 (S2-T08 브리지 쪽). 웹 3D 화면은 결정 D5 — 여기서 보지 않는다.
"""

import json
import pathlib
import uuid
from datetime import UTC, datetime

from voss_hmi.mqtt_logic import parse_command_json

PKG = pathlib.Path(__file__).resolve().parents[1]


def test_hmi_palletize_command_becomes_command_arg() -> None:
    """HMI 경로 입력·시작 버튼 = 음성과 같은 Command palletize(arg "역삼동,대치동,청담동")."""
    now = datetime.now(UTC)
    payload = json.dumps({"command_id": str(uuid.uuid4()), "type": "palletize",
                          "args": {"route": ["역삼동", "대치동", "청담동"]}, "raw_text": "HMI 버튼",
                          "sent_at": now.isoformat()})  # fmt: skip
    cmd = parse_command_json(payload, now)
    assert (cmd.command, cmd.arg) == ("palletize", "역삼동,대치동,청담동")


def test_hmi_bridge_forwards_pallet_state() -> None:
    src = (PKG / "voss_hmi" / "hmi_bridge.py").read_text(encoding="utf-8")
    assert '"/voss/pallet/state"' in src and '"voss/pallet/state"' in src and "retain=True" in src
