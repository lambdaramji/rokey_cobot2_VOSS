"""intent_parser 의 순수 로직 (ROS·HTTP 의존 없음, pytest 대상).

계약: docs/interfaces/intent_json.md
- stop 은 LLM 전에 로컬 키워드로 판정해 즉시 발행한다(안전, #67).
- 허용 동·구역·별칭은 /voss/sort/zone_map 에서 받은 것만 쓴다(YAML 직접 읽기 금지).
- LLM 응답도 믿지 않고 여기서 다시 검증한다. 실패하면 실행하지 않고 되묻는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

INTENT_TYPES = ("start", "stop", "resume", "priority", "answer", "query_history", "update_zone_map")
ROS_TYPES = (
    "start",
    "stop",
    "resume",
    "priority",
    "answer",
    "update_zone_map",
)  # Intent 로 보내는 것
QUERY_KINDS = ("count_by_dong", "held_count", "remaining_count")
HOLD = "HOLD"

# 정지 키워드: 공백·문장부호를 지운 뒤 포함 여부로 본다. 오인식으로 멈추는 쪽은 허용한다.
STOP_KEYWORDS = ("멈춰", "멈추", "정지", "스톱", "스탑", "그만", "stop")
# 정지처럼 보여도 정지가 아닌 표현 (예: "정지 해제", "멈추지 마")
STOP_NEGATIONS = ("해제", "멈추지마", "멈추지말", "정지하지마")

SAY_NOT_READY = "준비 중입니다. 잠시 후 다시 말씀해 주세요."
SAY_NO_QUESTION = "지금은 답할 질문이 없습니다."
SAY_UNSUPPORTED = "지금은 지원하지 않는 명령입니다."
SAY_RETRY = "잘 못 알아들었습니다. 다시 말씀해 주세요."
SAY_WHICH_DONG = "어느 동인지 말씀해 주세요."
SAY_UNKNOWN_DONG = "등록되지 않은 동입니다. 다시 말씀해 주세요."


def _squash(text: str) -> str:
    """비교용: 소문자, 공백·문장부호 제거."""
    return re.sub(r"[\s\.,!?~·\-]+", "", text.lower())


def is_stop(text: str) -> bool:
    s = _squash(text)
    if not s or any(n in s for n in STOP_NEGATIONS):
        return False
    return any(k in s for k in STOP_KEYWORDS)


@dataclass(frozen=True)
class ZoneMapView:
    """/voss/sort/zone_map 에서 만든 허용 목록."""

    dongs: tuple[str, ...]  # 정식 동 이름
    zones: tuple[str, ...]  # A/B/C …
    alias_to_dong: dict[str, str] = field(default_factory=dict)  # _squash(별칭) → 정식 이름
    version: str = ""

    @classmethod
    def from_entries(
        cls, entries: list[tuple[str, str, list[str]]], version: str = ""
    ) -> ZoneMapView:
        """entries = [(dong, zone, aliases), …] (ZoneMapEntry 에서 code 는 쓰지 않음)."""
        dongs: list[str] = []
        zones: list[str] = []
        alias: dict[str, str] = {}
        for dong, zone, aliases in entries:
            if not dong:
                continue
            dongs.append(dong)
            if zone and zone not in zones:
                zones.append(zone)
            alias[_squash(dong)] = dong  # 정식 이름은 aliases 가 비어도 항상 허용
            if dong.endswith("동"):
                alias.setdefault(_squash(dong[:-1]), dong)  # "역삼" → 역삼동
            for a in aliases:
                alias.setdefault(_squash(a), dong)
        return cls(tuple(dongs), tuple(zones), alias, version)

    def canonical_dong(self, raw: str | None) -> str | None:
        if not raw:
            return None
        return self.alias_to_dong.get(_squash(raw))

    def llm_allowed(self) -> dict:
        """FastAPI /ai/intent 요청의 allowed 필드 (web_api.md)."""
        aliases: dict[str, list[str]] = {d: [] for d in self.dongs}
        for a, d in self.alias_to_dong.items():
            if a != _squash(d):
                aliases[d].append(a)
        return {"dongs": list(self.dongs), "aliases": aliases, "zones": list(self.zones)}


@dataclass(frozen=True)
class Decision:
    """intent_parser 가 할 일 하나.

    kind: publish(Intent 발행) | query(REST /api/stats) | say(발화만, 실행 안 함)
    """

    kind: str
    intent: dict | None = None  # publish: Intent 필드 (type,dong,zone,count,raw_text,box_id)
    query: dict | None = None  # query: {query_kind, dong}
    say: str = ""


def stop_decision(raw_text: str) -> Decision:
    return Decision("publish", intent=_intent("stop", raw_text=raw_text))


def _intent(t: str, dong: str = "", zone: str = "", raw_text: str = "", box_id: str = "") -> dict:
    return {
        "type": t,
        "dong": dong,
        "zone": zone,
        "count": 0,
        "raw_text": raw_text,
        "box_id": box_id,
    }


def decide(
    llm: dict | None,
    raw_text: str,
    view: ZoneMapView | None,
    sort_state: str = "",
    sort_box_id: str = "",
    allow_update_zone_map: bool = False,
) -> Decision:
    """LLM 이 낸 intent JSON 을 검증해 할 일을 정한다. stop 키워드 판정은 이 함수보다 먼저 한다."""
    if is_stop(raw_text):
        return stop_decision(raw_text)
    if view is None:
        return Decision("say", say=SAY_NOT_READY)
    if not isinstance(llm, dict):
        return Decision("say", say=SAY_RETRY)

    t = llm.get("type")
    if t not in INTENT_TYPES:
        return Decision("say", say=SAY_RETRY)

    if t in ("start", "stop", "resume"):
        return Decision("publish", intent=_intent(t, raw_text=raw_text))

    if t == "priority":
        if not llm.get("dong"):
            return Decision("say", say=SAY_WHICH_DONG)
        dong = view.canonical_dong(llm.get("dong"))
        if dong is None:
            return Decision("say", say=SAY_UNKNOWN_DONG)
        return Decision("publish", intent=_intent(t, dong=dong, raw_text=raw_text))

    if t == "answer":
        if sort_state != "ASKING" or not sort_box_id:
            return Decision("say", say=SAY_NO_QUESTION)
        zone = (llm.get("zone") or "").upper()
        if zone == HOLD:
            return Decision(
                "publish", intent=_intent(t, zone=HOLD, raw_text=raw_text, box_id=sort_box_id)
            )
        dong = view.canonical_dong(llm.get("dong"))
        if dong is None:
            return Decision("say", say=SAY_UNKNOWN_DONG if llm.get("dong") else SAY_WHICH_DONG)
        return Decision(
            "publish", intent=_intent(t, dong=dong, raw_text=raw_text, box_id=sort_box_id)
        )

    if t == "query_history":
        kind = llm.get("query_kind")
        if kind not in QUERY_KINDS:
            return Decision("say", say=SAY_RETRY)
        dong = ""
        if kind == "count_by_dong":
            if not llm.get("dong"):
                return Decision("say", say=SAY_WHICH_DONG)
            d = view.canonical_dong(llm.get("dong"))
            if d is None:
                return Decision("say", say=SAY_UNKNOWN_DONG)
            dong = d
        return Decision("query", query={"query_kind": kind, "dong": dong})

    # update_zone_map: C 선택 범위 (MC-033). 채택 전에는 실행하지 않는다.
    if not allow_update_zone_map:
        return Decision("say", say=SAY_UNSUPPORTED)
    dong = view.canonical_dong(llm.get("dong"))
    zone = (llm.get("zone") or "").upper()
    if dong is None or zone not in view.zones:
        return Decision("say", say=SAY_RETRY)
    return Decision("publish", intent=_intent(t, dong=dong, zone=zone, raw_text=raw_text))


def stats_sentence(query: dict, resp: dict | None) -> str:
    """/api/stats 응답을 읽을 문장으로. DB 장애·실패면 조회 불가 문장."""
    if not resp or not resp.get("ok"):
        return "기록을 조회할 수 없습니다."
    n = int(resp.get("count", 0))
    kind = query["query_kind"]
    if kind == "count_by_dong":
        return f"{query['dong']}은 지금까지 {n}개입니다."
    if kind == "held_count":
        return f"보류는 {n}개입니다."
    return f"남은 수량은 {n}개입니다."


class SayDeduper:
    """intent_parser 가 내는 문장의 중복 억제 (MC-025). 같은 문장을 window 초 안에 다시 내지 않는다."""

    def __init__(self, window_s: float = 3.0) -> None:
        self.window_s = window_s
        self._last: dict[str, float] = {}

    def allow(self, text: str, now: float) -> bool:
        t = self._last.get(text)
        if t is not None and now - t < self.window_s:
            return False
        self._last[text] = now
        return True
