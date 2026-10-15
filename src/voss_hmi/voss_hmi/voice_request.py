"""검증된 웹 버튼 이벤트를 Nodes PC 음성 안내 문구로 변환한다."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

VOICE_PHRASES = {
    "start": "시작 명령을 전달했습니다.",
    "stop": "정지 명령을 전달했습니다.",
    "resume": "재개 명령을 전달했습니다.",
    "priority": "우선 분류 변경을 요청했습니다.",
    "answer": "작업자 답변을 전달했습니다.",
    "reset_zone": "구역 초기화를 요청했습니다.",
    "palletize": "팔레트 적재 명령을 전달했습니다.",
    "plan": "투입 예정 수량을 저장했습니다.",
}


def parse_voice_request(payload: str, now: datetime) -> tuple[str, str] | None:
    """오래됐거나 형식이 틀린 요청은 발화하지 않는다. 임의 텍스트는 받지 않는다."""
    if len(payload) > 512:
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or set(data) != {"request_id", "action", "sent_at"}:
        return None
    request_id = data["request_id"]
    action = data["action"]
    sent_at = data["sent_at"]
    if not isinstance(request_id, str) or not isinstance(action, str) or not isinstance(sent_at, str):
        return None
    try:
        uuid.UUID(request_id)
        sent_time = datetime.fromisoformat(sent_at)
    except ValueError:
        return None
    if sent_time.tzinfo is None or now.tzinfo is None:
        return None
    age = (now - sent_time).total_seconds()
    if not -5 <= age <= 30:
        return None
    phrase = VOICE_PHRASES.get(action)
    return (request_id, phrase) if phrase else None
