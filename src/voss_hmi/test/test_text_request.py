"""입력 명령의 재전송·오래된 이벤트가 ROS로 들어가지 않도록 계약 검증."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from voss_hmi.text_request import parse_text_reply, parse_text_request


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
REQUEST_ID = str(uuid.uuid4())


def request(text="팔레타이징 실행해", sent_at=None):
    return json.dumps({"request_id": REQUEST_ID, "text": text,
                       "sent_at": (sent_at or NOW).isoformat()}, ensure_ascii=False)


def test_valid_text_and_reply():
    assert parse_text_request(request(), NOW) == (REQUEST_ID, "팔레타이징 실행해")
    assert parse_text_reply(json.dumps({"request_id": REQUEST_ID,
                                        "message": "싣는 순서를 동 이름으로 말씀해 주세요."}))


def test_rejects_stale_invalid_and_unexpected_fields():
    assert parse_text_request(request(sent_at=NOW - timedelta(seconds=31)), NOW) is None
    assert parse_text_request(request(text=" "), NOW) is None
    assert parse_text_request(request(text="정지\x00"), NOW) is None
    assert parse_text_request(json.dumps({"request_id": REQUEST_ID, "text": "시작",
                                          "sent_at": NOW.isoformat(), "extra": "x"}), NOW) is None
    assert parse_text_reply(json.dumps({"request_id": "wrong", "message": "ok"})) is None
