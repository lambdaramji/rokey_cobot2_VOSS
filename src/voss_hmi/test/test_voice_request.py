"""웹 버튼 음성 요청은 고정 문구만 허용한다."""

import json
from datetime import datetime, timedelta, timezone

from voss_hmi.voice_request import VOICE_PHRASES, parse_voice_request

NOW = datetime(2026, 10, 14, 20, 0, tzinfo=timezone(timedelta(hours=9)))
REQUEST_ID = "7fd11fb1-160c-4d47-98b2-5462a6789a5a"


def payload(action="start", sent_at=None, **extra):
    if sent_at is None:
        sent_at = NOW.isoformat()
    return json.dumps({"request_id": REQUEST_ID, "action": action, "sent_at": sent_at, **extra})


def test_each_allowed_action_maps_to_a_fixed_phrase():
    for action, phrase in VOICE_PHRASES.items():
        assert parse_voice_request(payload(action), NOW) == (REQUEST_ID, phrase)


def test_free_text_and_stale_requests_are_rejected():
    assert parse_voice_request(payload(text="임의 문장"), NOW) is None
    assert parse_voice_request(payload("not_allowed"), NOW) is None
    assert parse_voice_request(payload(sent_at=(NOW - timedelta(seconds=31)).isoformat()), NOW) is None
    assert parse_voice_request(payload(sent_at=(NOW + timedelta(seconds=6)).isoformat()), NOW) is None
    assert parse_voice_request("not json", NOW) is None
