"""/ai/intent 의 프롬프트·JSON 스키마·응답 정리 (네트워크 없음, pytest 대상).

계약: docs/interfaces/intent_json.md, docs/interfaces/web_api.md
LLM 은 해석만 한다. 최종 검증은 ROS 쪽 intent_parser 가 다시 한다.
"""

from __future__ import annotations

import json

TYPES = ["start", "stop", "resume", "priority", "answer", "query_history", "update_zone_map"]
QUERY_KINDS = ["count_by_dong", "held_count", "remaining_count"]

# OpenAI structured output (strict) 스키마 — 모든 필드 필수, 없으면 null
INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "dong", "zone", "count", "query_kind", "raw_text"],
    "properties": {
        "type": {"type": "string", "enum": TYPES + ["unknown"]},
        "dong": {"type": ["string", "null"]},
        "zone": {"type": ["string", "null"]},
        "count": {"type": "integer"},
        "query_kind": {"type": ["string", "null"], "enum": QUERY_KINDS + [None]},
        "raw_text": {"type": "string"},
    },
}

_RULES = """너는 물류 분류 로봇의 음성 지시를 JSON 하나로 바꾸는 해석기다. 설명 없이 JSON 만 낸다.
type:
- start: 작업·분류 시작, "전부/전체 분류" (dong=null)
- stop: 멈춤·정지 / resume: 다시 시작·재개
- priority: 특정 동을 먼저 분류 (dong 필수)
- answer: 로봇이 물은 박스가 어느 동인지 답함. 동 이름이면 dong, "보류"면 zone="HOLD"
- query_history: 기록 질문. 동별 처리 수=count_by_dong(dong 필수), 보류 수=held_count, 남은 수=remaining_count
- update_zone_map: 동의 구역을 바꿈 (dong, zone 필수)
- unknown: 위에 해당하지 않음
dong 은 반드시 허용 목록의 정식 이름으로 적는다(별칭이면 정식 이름으로 바꾼다). 목록에 없으면 null.
zone 은 허용 구역 또는 "HOLD" 만. count 는 항상 0. raw_text 는 입력 원문 그대로."""


def build_messages(text: str, allowed: dict) -> list[dict]:
    dongs = allowed.get("dongs") or []
    aliases = allowed.get("aliases") or {}
    zones = allowed.get("zones") or []
    allow = json.dumps({"dongs": dongs, "aliases": aliases, "zones": zones}, ensure_ascii=False)
    return [
        {"role": "system", "content": f"{_RULES}\n허용 목록: {allow}"},
        {"role": "user", "content": text},
    ]


def normalize(raw: str | dict, text: str) -> dict | None:
    """LLM 출력 → intent JSON. 파싱 실패·unknown 이면 None (intent_parser 가 되묻는다)."""
    try:
        d = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError):
        return None
    t = d.get("type")
    if t not in TYPES:
        return None
    zone = d.get("zone")
    return {
        "type": t,
        "dong": d.get("dong") or None,
        "zone": zone.upper() if isinstance(zone, str) and zone else None,
        "count": 0,
        "query_kind": d.get("query_kind") if d.get("query_kind") in QUERY_KINDS else None,
        "raw_text": text,
    }
