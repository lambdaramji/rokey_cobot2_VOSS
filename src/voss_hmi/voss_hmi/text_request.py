"""웹 자연어 입력의 형식·시각을 검증해 ROS 전사 경로로 전달한다."""

import json
import uuid
from datetime import datetime


def parse_text_request(payload: str, now: datetime) -> tuple[str, str] | None:
    if len(payload) > 1024:
        return None
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"request_id", "text", "sent_at"}:
            return None
        request_id, text, sent_at = data["request_id"], data["text"], data["sent_at"]
        if not all(isinstance(value, str) for value in (request_id, text, sent_at)):
            return None
        if str(uuid.UUID(request_id)) != request_id or not 1 <= len(text.strip()) <= 240:
            return None
        if any(ord(char) < 32 and char not in "\t\n" for char in text):
            return None
        sent_time = datetime.fromisoformat(sent_at)
        if sent_time.tzinfo is None or now.tzinfo is None:
            return None
        if not -5 <= (now - sent_time).total_seconds() <= 30:
            return None
        return request_id, text.strip()
    except (ValueError, TypeError, KeyError):
        return None


def parse_text_reply(payload: str) -> dict | None:
    if len(payload) > 1024:
        return None
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"request_id", "message"}:
            return None
        request_id, message = data["request_id"], data["message"]
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            return None
        if not isinstance(message, str) or not 1 <= len(message) <= 300:
            return None
        return data
    except (ValueError, TypeError):
        return None
