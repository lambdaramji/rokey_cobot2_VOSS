import json

import pytest
from voss_hmi.voice_status import parse_voice_status


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "[]",
        "{}",
        "{",
        '{"phase": []}',
        '{"phase":"WAKE_DETECTED","event_id":" ","utterance_id":"a"}',
    ],
)
def test_invalid_status_is_dropped(raw):
    assert parse_voice_status(raw) is None


def test_only_display_contract_fields_are_forwarded():
    payload = {"phase": "WAKE_DETECTED", "event_id": "event", "utterance_id": "attempt"}
    assert parse_voice_status(json.dumps({**payload, "text": "private transcript"})) == payload


def test_disconnect_drops_without_queue_and_reconnect_sends_only_new_event():
    from unittest.mock import Mock

    from voss_hmi.voice_status import forward_voice_status

    client = Mock()
    client.is_connected.return_value = False
    client.publish.return_value.rc = 0
    payload = {"phase": "WAKE_DETECTED", "event_id": "old", "utterance_id": "u1"}
    assert not forward_voice_status(client, json.dumps(payload))
    client.publish.assert_not_called()
    client.is_connected.return_value = True
    payload.update(event_id="new", utterance_id="u2")
    assert forward_voice_status(client, json.dumps(payload))
    client.publish.assert_called_once_with(
        "voss/voice_status", json.dumps(payload), qos=0, retain=False
    )


def test_publish_race_with_disconnect_is_not_retried():
    from unittest.mock import Mock

    from voss_hmi.voice_status import forward_voice_status

    client = Mock()
    client.is_connected.return_value = True
    client.publish.return_value.rc = 4
    payload = {"phase": "WAKE_DETECTED", "event_id": "e", "utterance_id": "u"}
    assert not forward_voice_status(client, json.dumps(payload))
    assert client.publish.call_count == 1
