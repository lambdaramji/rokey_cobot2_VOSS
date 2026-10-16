"""intent_parser 의 순수 로직 (ROS·HTTP 의존 없음, pytest 대상).

계약: docs/interfaces/intent_json.md
- stop 은 LLM 전에 로컬 키워드로 판정해 즉시 발행한다(안전, #67).
- 허용 동·구역·별칭은 /voss/sort/zone_map 에서 받은 것만 쓴다(YAML 직접 읽기 금지).
- LLM 응답도 믿지 않고 여기서 다시 검증한다. 실패하면 실행하지 않고 되묻는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

INTENT_TYPES = (
    "start",
    "stop",
    "resume",
    "priority",
    "answer",
    "query_history",
    "update_zone_map",
    "palletize",  # Sprint 2 (TR-PAL-01)
)
ROS_TYPES = (
    "start",
    "stop",
    "resume",
    "priority",
    "answer",
    "recheck",
    "update_zone_map",
    "palletize",
)  # Intent 로 보내는 것
QUERY_KINDS = ("count_by_dong", "held_count", "remaining_count")
HOLD = "HOLD"
DESTINATION_ANSWER_RE = re.compile(r"(.+?)(?:으로|로)보내(?:줘|주세요|줘요|요)?")
# 질문 중 "읽을 수 없다" 답 → 보류. 공백·문장부호를 지운 뒤 전체 일치(10/12 시연 문형, LLM 없이)
HOLD_ANSWER_RE = re.compile(
    r"(?:송장)?(?:확인|판독|인식)(?:이)?(?:불가|안돼|안됨|안됩니다|못해|못함)(?:입니다|이에요|예요|요)?"
    r"|보류(?:로)?(?:처리|보내)?"
    r"(?:해|해줘|해주세요|해요|합니다|할게|할게요|줘|주세요|부탁해|부탁해요|부탁합니다|입니다|요)?"
)
# "보류"의 STT 오인식(고류·고려우·보루·볼류…)을 질문 중(ASKING)에만 보류로 받는다 (10/15 현장).
_HANGUL_BASE, _HANGUL_END = 0xAC00, 0xD7A3
_JAMO_INITIAL = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JAMO_MEDIAL = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JAMO_FINAL = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
_HOLD_WORD = "보류"


def _jamo(ch: str) -> tuple[str, str, str] | None:
    """한글 음절 → (초성, 중성, 종성). 종성 없음은 ' '. 한글이 아니면 None."""
    code = ord(ch)
    if not _HANGUL_BASE <= code <= _HANGUL_END:
        return None
    code -= _HANGUL_BASE
    return _JAMO_INITIAL[code // 588], _JAMO_MEDIAL[code % 588 // 28], _JAMO_FINAL[code % 28]


def _compose(initial: str, medial: str, final: str = " ") -> str:
    return chr(
        _HANGUL_BASE
        + _JAMO_INITIAL.index(initial) * 588
        + _JAMO_MEDIAL.index(medial) * 28
        + _JAMO_FINAL.index(final)
    )


def _collapse_yu(word: str) -> str:
    """'려우'·'리우'처럼 두 음절로 늘어진 '류' 소리를 한 음절로 합친다 (고려우 → 고류)."""
    out: list[str] = []
    i = 0
    while i < len(word):
        cur, nxt = _jamo(word[i]), _jamo(word[i + 1]) if i + 1 < len(word) else None
        if cur is not None and nxt == ("ㅇ", "ㅜ", " ") and cur[1] in "ㅕㅣ" and cur[2] == " ":
            out.append(_compose(cur[0], "ㅠ"))
            i += 2
            continue
        out.append(word[i])
        i += 1
    return "".join(out)


def _jamo_tokens(word: str) -> list[str]:
    tokens: list[str] = []
    for ch in word:
        j = _jamo(ch)
        tokens.extend(j[:2] if j is not None and j[2] == " " else (j or (ch,)))
    return tokens


def _edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def sounds_like_hold(word: str) -> bool:
    """두 음절 낱말이 '보류'로 들리는가: 자모 하나 차이(고류·보루·볼류·포류),
    또는 첫 음절 모음 ㅗ + 둘째 음절 ㄹ+ㅠ/ㅕ/ㅜ 꼴(고려·모루). 소리·도로·대치는 아니다."""
    word = _collapse_yu(word)
    if len(word) != 2:
        return False
    first, second = _jamo(word[0]), _jamo(word[1])
    if first is None or second is None:
        return False
    if _edit_distance(_jamo_tokens(word), _jamo_tokens(_HOLD_WORD)) <= 1:
        return True
    return first[1] == "ㅗ" and second[0] == "ㄹ" and second[1] in "ㅠㅕㅜ" and second[2] == " "


def canonicalize_hold(squashed: str) -> str:
    """앞머리 2~3음절이 '보류'로 들리면 '보류'로 바꾸고 뒤(조사·어미)는 그대로 둔다."""
    for n in (3, 2):
        head = squashed[:n]
        if len(head) == n and all(_jamo(ch) is not None for ch in head) and sounds_like_hold(head):
            return _HOLD_WORD + squashed[n:]
    return squashed


# "재확인 시작" → 보관 중인 재확인 칸 박스 처리(type recheck, 10/12 시연, LLM 없이). 전체 일치
RECHECK_START_RE = re.compile(
    r"재확인(?:을)?(?:시작|진행|처리)?(?:해|해줘|해주세요|하자|합니다|할게|해요)?"
)

# "대치, 역삼, 청담 순서로 실어줘"·"… 순으로 트럭에 실어" → palletize(BRD TR-PAL-01, LLM 없이).
# 트럭·팔레트 + 싣는 말, 또는 "순(서)…싣는 말"이 있으면. 말한 순서 = 배송 순서(첫 배송지부터, BRD v1.5 — 10/13 PL)
PALLETIZE_RE = re.compile(
    r"(?:트럭|팔레트).*(?:실어|싣|적재|태워|올려|옮겨)"
    r"|(?:실어|싣|적재|태워|올려|옮겨).*(?:트럭|팔레트)"
    r"|순(?:서)?(?:대로|으로|로)?(?:실어|싣|적재)"
)
PALLETIZE_START_RE = re.compile(
    r"팔레타이징(?:을)?(?:실행|시작)(?:해|해줘|해주세요|하자|합니다|해요)?"
)
SHORT_ZONE_ALIASES = frozenset({"a", "b", "c", "에이", "비", "비이", "씨", "시"})
SAY_PALLET_ORDER = "동 이름을 순서대로 말씀해 주세요."

# 정지 키워드: 공백·문장부호를 지운 뒤 포함 여부로 본다. 오인식으로 멈추는 쪽은 허용한다.
STOP_KEYWORDS = ("멈춰", "멈추", "정지", "스톱", "스탑", "그만", "stop")
# 정지처럼 보여도 정지가 아닌 표현 (예: "정지 해제", "멈추지 마")
STOP_NEGATIONS = ("해제", "멈추지마", "멈추지말", "정지하지마")

SAY_NOT_READY = "로봇의 구역 정보를 받지 못했습니다. 연결 상태를 확인해 주세요."
SAY_NO_QUESTION = "지금은 답할 질문이 없습니다."
SAY_UNSUPPORTED = "지금은 지원하지 않는 명령입니다."
SAY_RETRY = "잘 못 알아들었습니다. 다시 말씀해 주세요."
SAY_WHICH_DONG = "어느 동인지 말씀해 주세요."
SAY_UNKNOWN_DONG = "등록되지 않은 동입니다. 다시 말씀해 주세요."
# palletize 경로 (TR-PAL-01: 미등록·중복·0개·4개 이상이면 실행하지 않고 되묻는다)
MAX_ROUTE = 3
SAY_ROUTE_RETRY = "배송 순서를 다시 말씀해 주세요."
SAY_ROUTE_COUNT = "배송지는 한 곳에서 세 곳까지 말씀해 주세요."
SAY_ROUTE_DUP = "같은 동이 두 번 들어 있습니다. 배송 순서를 다시 말씀해 주세요."
SAY_ROUTE_UNKNOWN = "등록되지 않은 동이 있습니다. 배송 순서를 다시 말씀해 주세요."


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
        zone_dongs: dict[str, list[str]] = {}
        for dong, zone, aliases in entries:
            if not dong:
                continue
            dongs.append(dong)
            if zone and zone not in zones:
                zones.append(zone)
            if zone:
                zone_dongs.setdefault(zone.upper(), []).append(dong)
            alias[_squash(dong)] = dong  # 정식 이름은 aliases 가 비어도 항상 허용
            if dong.endswith("동"):
                alias.setdefault(_squash(dong[:-1]), dong)  # "역삼" → 역삼동
            for a in aliases:
                alias.setdefault(_squash(a), dong)
        # 구역이 동 하나에만 대응할 때만 구역명으로 로봇 목적지를 지정할 수 있다.
        # 여러 동이 한 구역을 공유하면 임의의 동을 선택하지 않는다.
        spoken = {"A": ("에이",), "B": ("비", "비이"), "C": ("씨", "시")}
        for zone, members in zone_dongs.items():
            if len(members) != 1:
                continue
            for name in (zone, f"{zone}구역", *spoken.get(zone, ())):
                alias.setdefault(_squash(name), members[0])
            for name in spoken.get(zone, ()):
                alias.setdefault(_squash(f"{name}구역"), members[0])
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
    intent: dict | None = None  # publish: Intent 필드 (type,dong,zone,count,raw_text,box_id,route)
    query: dict | None = None  # query: {query_kind, dong}
    say: str = ""


def stop_decision(raw_text: str) -> Decision:
    return Decision("publish", intent=_intent("stop", raw_text=raw_text))


def command_acknowledgement(intent: dict) -> str:
    """접수한 명령만 안내한다. 로봇 동작 완료를 뜻하지 않는다."""
    kind = intent["type"]
    if kind == "start":
        return "분류를 시작하겠습니다."
    if kind == "stop":
        # 음성이 마이크로 되돌아와도 호출어 없는 정지로 재인식되지 않도록 정지 동사를 피한다.
        return "요청을 처리하겠습니다."
    if kind == "resume":
        return "분류를 재개하겠습니다."
    if kind == "priority":
        return f"{intent['dong']}을 우선 분류하겠습니다."
    if kind == "answer":
        return (
            "보류로 처리하겠습니다."
            if intent.get("zone") == HOLD
            else f"{intent['dong']}으로 분류하겠습니다."
        )
    if kind == "recheck":
        return "재확인을 시작하겠습니다."
    if kind == "palletize":
        return "말씀하신 순서로 적재하겠습니다."
    return ""


def _intent(
    t: str,
    dong: str = "",
    zone: str = "",
    raw_text: str = "",
    box_id: str = "",
    route: list[str] | None = None,
) -> dict:
    return {
        "type": t,
        "dong": dong,
        "zone": zone,
        "count": 0,
        "raw_text": raw_text,
        "box_id": box_id,
        "route": list(route or []),  # palletize 만, 그 밖은 []
    }


def check_route(raw, view: ZoneMapView) -> tuple[list[str], str]:
    """LLM 의 route → (정식 동 이름 경로, "") 또는 ([], 되묻기 문장). 말한 순서(첫 배송지부터)를 지킨다."""
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        return [], SAY_ROUTE_RETRY
    names = [x for x in raw if x.strip()]
    if not 1 <= len(names) <= MAX_ROUTE:
        return [], SAY_ROUTE_COUNT if names else SAY_ROUTE_RETRY
    route = [view.canonical_dong(x) for x in names]
    if any(d is None for d in route):
        return [], SAY_ROUTE_UNKNOWN
    if len(set(route)) != len(route):
        return [], SAY_ROUTE_DUP
    return route, ""


def decide_bare_dong(
    raw_text: str,
    view: ZoneMapView | None,
    sort_state: str,
    sort_box_id: str,
) -> Decision | None:
    """동 이름만 말한 발화를 로봇 질문 상태에 따라 처리한다.
    단독 동 이름이 아니면 None을 반환한다.
    """
    if view is None:
        return None

    dong = view.canonical_dong(raw_text)
    if dong is None:
        return None

    # 질문 중이 아니면 동 이름만으로 로봇 동작을 시작하지 않는다.
    if sort_state != "ASKING" or not sort_box_id:
        return Decision("say", say=SAY_NO_QUESTION)

    return Decision(
        "publish",
        intent=_intent(
            "answer",
            dong=dong,
            raw_text=raw_text,
            box_id=sort_box_id,
        ),
    )


def decide_zone_priority(raw_text: str, view: ZoneMapView | None) -> Decision | None:
    """A/B/C 구역을 먼저 분류하라는 명시적인 지시를 LLM 없이 처리한다."""
    name = r"(?P<name>(?:a|b|c|에이|비이?|씨|시)(?:구역)?)"
    ending = r"(?:해|해줘|해주세요|해요|하자|해줘요|시작해)?"
    text = _squash(raw_text)
    match = re.fullmatch(
        name + r"(?:을|를|은|는)?"
        r"(?:부터(?:먼저|우선)?(?:분류|선별|처리)?|(?:먼저|우선)(?:분류|선별|처리)?|분류|선별)"
        + ending,
        text,
    )
    if match is None:
        match = re.fullmatch(
            r"우선(?:분류|선별)?구역(?:을|은)?" + name + r"(?:으로|로)(?:설정|지정|변경)" + ending,
            text,
        )
    if match is None:
        return None
    if view is None:
        return Decision("say", say=SAY_NOT_READY)
    dong = view.canonical_dong(match.group("name"))
    if dong is None:
        return Decision("say", say=SAY_UNKNOWN_DONG)
    return Decision("publish", intent=_intent("priority", dong=dong, raw_text=raw_text))


def decide_hold_answer(
    raw_text: str,
    sort_state: str,
    sort_box_id: str,
) -> Decision | None:
    """'송장 확인 불가'·'보류' 같은 답을 보류(HOLD) 답으로 처리한다. 해당 표현이 아니면 None.
    질문 중(ASKING)에는 '고류'·'고려우'처럼 보류로 들리는 오인식도 보류로 받는다."""
    squashed = _squash(raw_text)
    if sort_state == "ASKING":
        squashed = canonicalize_hold(squashed)
    if HOLD_ANSWER_RE.fullmatch(squashed) is None:
        return None
    # 질문 중이 아니면 보류 답으로 로봇을 움직이지 않는다.
    if sort_state != "ASKING" or not sort_box_id:
        return Decision("say", say=SAY_NO_QUESTION)
    return Decision(
        "publish", intent=_intent("answer", zone=HOLD, raw_text=raw_text, box_id=sort_box_id)
    )


def decide_recheck_start(raw_text: str) -> Decision | None:
    """'재확인 시작'·'재확인 진행해 줘' → recheck. 받을 수 있는 상태인지는 sort_manager 가 판단한다."""
    if RECHECK_START_RE.fullmatch(_squash(raw_text)) is None:
        return None
    return Decision("publish", intent=_intent("recheck", raw_text=raw_text))


def decide_palletize(raw_text: str, view: ZoneMapView | None) -> Decision | None:
    """'대치, 역삼, 청담 순서로 실어줘' → palletize, route = 말한 순서 [대치동, 역삼동, 청담동](배송 순서, BRD TR-PAL-01).
    동을 하나도 말하지 않거나 4곳 이상이면 되묻는다. 받을 수 있는 상태인지는 sort_manager 가 판단한다."""
    s = _squash(raw_text)
    if PALLETIZE_START_RE.fullmatch(s):
        return Decision("say", say=SAY_PALLET_ORDER if view is not None else SAY_NOT_READY)
    if PALLETIZE_RE.search(s) is None:
        return None
    if view is None:
        return Decision("say", say=SAY_NOT_READY)
    positions = [
        index for index, char in enumerate(raw_text) if not re.fullmatch(r"[\s\.,!?~·\-]", char)
    ]
    found: dict[str, int] = {}  # 정식 동 → 원문에서 처음 나온 위치
    for alias, dong in view.alias_to_dong.items():
        if alias in SHORT_ZONE_ALIASES:
            # '비우고'의 비, '시작'의 시를 B/C 구역으로 읽지 않는다.
            pattern = re.compile(
                rf"(?<![가-힣A-Za-z]){re.escape(alias)}(?=\s*구역|\s*[,./→]|\s+|$)", re.IGNORECASE
            )
            match = pattern.search(raw_text)
            i = match.start() if match else -1
        else:
            offset = s.find(alias)
            i = positions[offset] if offset >= 0 else -1
        if alias and i >= 0 and (dong not in found or i < found[dong]):
            found[dong] = i
    if not found:
        return Decision("say", say=SAY_PALLET_ORDER)
    order = sorted(found, key=found.get)
    if len(order) > MAX_ROUTE:
        return Decision("say", say=SAY_ROUTE_COUNT)
    return Decision("publish", intent=_intent("palletize", raw_text=raw_text, route=order))


def decide_pallet_route_answer(raw_text: str, view: ZoneMapView | None) -> Decision | None:
    """순서를 되물은 직후에는 동 이름 목록만으로도 팔레타이징 경로를 확정한다."""
    if view is None:
        return Decision("say", say=SAY_NOT_READY)
    parts = re.split(r"\s*(?:,|→|->|/)\s*", raw_text.strip())
    if len(parts) == 1:
        parts = raw_text.split()
    if not parts or not any(view.canonical_dong(part) for part in parts):
        return None  # 다른 일반 명령은 기존 해석 경로로 보낸다.
    route, error = check_route(parts, view)
    if error:
        return Decision("say", say=error)
    return Decision("publish", intent=_intent("palletize", raw_text=raw_text, route=route))


def decide_destination_answer(
    raw_text: str,
    view: ZoneMapView | None,
    sort_state: str,
    sort_box_id: str,
) -> Decision | None:
    """'역삼으로 보내' 같은 목적지 답변을 처리한다.
    해당 표현이 아니면 None을 반환한다.
    """
    if view is None:
        return None

    # Whisper의 문장부호·띄어쓰기 차이를 단독 동 판정과 같이 정규화한다.
    match = DESTINATION_ANSWER_RE.fullmatch(_squash(raw_text))

    if match is None:
        return None

    dong = view.canonical_dong(match.group(1))

    if dong is None:
        return None

    # 질문 중이 아니면 목적지 답변으로 로봇을 움직이지 않는다.
    if sort_state != "ASKING" or not sort_box_id:
        return Decision("say", say=SAY_NO_QUESTION)

    return Decision(
        "publish",
        intent=_intent(
            "answer",
            dong=dong,
            raw_text=raw_text,
            box_id=sort_box_id,
        ),
    )


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
    if isinstance(llm, dict) and llm.get("type") == "unknown":
        return Decision("say", say=SAY_UNSUPPORTED)
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
        destination = llm.get("dong") or llm.get("zone")
        if not destination:
            return Decision("say", say=SAY_WHICH_DONG)
        dong = view.canonical_dong(destination)
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

    if t == "palletize":
        # 시작 조건(분류 중 박스 없음·팔레트 비어 있음)은 sort_manager 가 보고 거부 이유를 말한다(TR-PAL-02)
        route, why = check_route(llm.get("route"), view)
        if why:
            return Decision("say", say=why)
        return Decision("publish", intent=_intent(t, raw_text=raw_text, route=route))

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
