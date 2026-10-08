"""intent_logic 단위 시험 (ROS·네트워크 없이). LLM 응답은 정답 JSON 으로 흉내 낸다.

실제 OpenAI 로 정답 세트 20건을 돌리는 시험(VC-EUS-INTENT-01)은 FastAPI /ai/intent 가 생긴 뒤 같은 fixture 로 한다.
"""

import json
import pathlib

import pytest
from voss_voice.intent_logic import (
    SAY_NO_QUESTION,
    SAY_NOT_READY,
    SAY_RETRY,
    SAY_UNKNOWN_DONG,
    SAY_UNSUPPORTED,
    SAY_WHICH_DONG,
    SayDeduper,
    ZoneMapView,
    decide,
    decide_bare_dong,
    decide_destination_answer,
    is_stop,
    stats_sentence,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "intent_cases.json"
VIEW = ZoneMapView.from_entries(
    [("역삼동", "A", ["역삼"]), ("대치동", "B", ["대치"]), ("청담동", "C", [])], version="1"
)


def _llm_from_expect(e: dict) -> dict:
    """정답대로 답한 LLM 응답 (별칭을 섞어 intent_parser 의 정규화도 확인)."""
    if e["kind"] == "query":
        return {
            "type": "query_history",
            "query_kind": e["query_kind"],
            "dong": e["dong"][:-1] or None,
        }
    return {"type": e["type"], "dong": e["dong"] or None, "zone": e["zone"] or None}


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def test_fixture_has_20_cases_4_groups_x_5():
    cases = _cases()
    assert len(cases) == 20
    groups = {}
    for c in cases:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
    assert groups == {"운전": 5, "우선": 5, "답변": 5, "이력": 5}


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_fixture_case_with_correct_llm(case):
    e = case["expect"]
    d = decide(_llm_from_expect(e), case["text"], VIEW, case["state"], case.get("box_id", ""))
    assert d.kind == e["kind"]
    if e["kind"] == "publish":
        assert d.intent["type"] == e["type"]
        assert d.intent["dong"] == e["dong"]
        assert d.intent["zone"] == e["zone"]
        assert d.intent["box_id"] == e.get("box_id", "")
    else:
        assert d.query == {"query_kind": e["query_kind"], "dong": e["dong"]}


# --- stop: LLM·zone_map 없이 즉시 (안전) ---
@pytest.mark.parametrize(
    "text", ["멈춰", "멈춰!", "잠깐 정지", "스톱", "그만해", "로키 멈춰 줘", "STOP"]
)
def test_stop_keywords(text):
    assert is_stop(text)
    d = decide(None, text, None)  # LLM 실패, zone_map 미수신이어도
    assert d.kind == "publish" and d.intent["type"] == "stop"


@pytest.mark.parametrize("text", ["정지 해제", "멈추지 마", "역삼동부터 분류해", "다시 시작"])
def test_not_stop(text):
    assert not is_stop(text)


# --- 거부·되묻기 ---
def test_no_zone_map_means_not_ready():
    assert decide({"type": "start"}, "시작", None).say == SAY_NOT_READY


@pytest.mark.parametrize(
    "llm", [None, {}, {"type": "dance"}, "start", {"type": "query_history", "query_kind": "x"}]
)
def test_invalid_llm_output_is_rejected(llm):
    d = decide(llm, "아무거나 해", VIEW, "RUNNING")
    assert d.kind == "say" and d.say == SAY_RETRY


def test_priority_needs_known_dong():
    assert decide({"type": "priority"}, "먼저 해", VIEW).say == SAY_WHICH_DONG
    assert (
        decide({"type": "priority", "dong": "삼성동"}, "삼성동 먼저", VIEW).say == SAY_UNKNOWN_DONG
    )


def test_alias_never_leaves_parser():
    d = decide({"type": "priority", "dong": "역삼"}, "역삼 먼저", VIEW)
    assert d.intent["dong"] == "역삼동"


def test_answer_only_while_asking_and_carries_box_id():
    llm = {"type": "answer", "dong": "청담동"}
    assert decide(llm, "청담동", VIEW, "RUNNING", "b1").say == SAY_NO_QUESTION
    assert decide(llm, "청담동", VIEW, "ASKING", "").say == SAY_NO_QUESTION
    d = decide(llm, "청담동", VIEW, "ASKING", "b1")
    assert d.intent["box_id"] == "b1"


def test_box_id_empty_for_non_answer():
    d = decide({"type": "start"}, "시작", VIEW, "ASKING", "b1")
    assert d.intent["box_id"] == ""


def test_update_zone_map_is_scope_c():
    llm = {"type": "update_zone_map", "dong": "대치동", "zone": "C"}
    assert decide(llm, "대치동을 C로", VIEW).say == SAY_UNSUPPORTED
    d = decide(llm, "대치동을 C로", VIEW, allow_update_zone_map=True)
    assert d.intent["type"] == "update_zone_map" and d.intent["zone"] == "C"


def test_llm_allowed_payload():
    a = VIEW.llm_allowed()
    assert a["dongs"] == ["역삼동", "대치동", "청담동"]
    assert a["zones"] == ["A", "B", "C"]
    assert "역삼" in a["aliases"]["역삼동"]


# --- 이력 응답 문장 ---
def test_stats_sentences():
    q = {"query_kind": "count_by_dong", "dong": "역삼동"}
    assert stats_sentence(q, {"ok": True, "count": 3}) == "역삼동은 지금까지 3개입니다."
    assert (
        stats_sentence({"query_kind": "held_count", "dong": ""}, {"ok": True, "count": 1})
        == "보류는 1개입니다."
    )
    assert (
        stats_sentence({"query_kind": "remaining_count", "dong": ""}, {"ok": True, "count": 5})
        == "남은 수량은 5개입니다."
    )
    assert stats_sentence(q, None) == "기록을 조회할 수 없습니다."
    assert stats_sentence(q, {"ok": False, "message": "DB_ERROR"}) == "기록을 조회할 수 없습니다."


def test_say_dedup_window():
    d = SayDeduper(window_s=3.0)
    assert d.allow("다시 말씀해 주세요.", 0.0)
    assert not d.allow("다시 말씀해 주세요.", 2.0)
    assert d.allow("다시 말씀해 주세요.", 5.1)
    assert d.allow("다른 문장", 2.0)


@pytest.mark.parametrize(
    ("text", "dong"),
    [
        ("대치동.", "대치동"),
        ("대치동!", "대치동"),
        ("역삼", "역삼동"),
        ("청담동", "청담동"),
    ],
)
def test_bare_dong_recognizes_punctuation_and_aliases(text: str, dong: str) -> None:
    """문장부호·별칭이 있어도 등록된 동의 질문 답변으로 처리한다."""
    decision = decide_bare_dong(text, VIEW, "ASKING", "box-12")
    assert decision is not None and decision.kind == "publish"
    assert decision.intent["type"] == "answer"
    assert decision.intent["dong"] == dong
    assert decision.intent["raw_text"] == text
    assert decision.intent["box_id"] == "box-12"


@pytest.mark.parametrize(
    ("text", "dong"),
    [
        ("역삼으로 보내.", "역삼동"),
        ("역삼으로, 보내", "역삼동"),
        ("역삼으로 보내요", "역삼동"),
        ("대치로 보내!", "대치동"),
        ("역삼으로 보내 줘", "역삼동"),
        ("역삼으로 보내주세요", "역삼동"),
        ("역삼으로 보내줘요", "역삼동"),
        ("대치동으로 보내?", "대치동"),
        ("청담동으로 보내", "청담동"),
    ],
)
def test_destination_answer_handles_whisper_variations(text: str, dong: str) -> None:
    """공백·문장부호·어미를 허용하고 원문과 현재 박스 ID를 보존한다."""
    decision = decide_destination_answer(text, VIEW, "ASKING", "box-12")
    assert decision is not None and decision.kind == "publish"
    assert decision.intent["type"] == "answer"
    assert decision.intent["dong"] == dong
    assert decision.intent["raw_text"] == text
    assert decision.intent["box_id"] == "box-12"


@pytest.mark.parametrize(
    ("state", "box_id"),
    [("RUNNING", "box-12"), ("IDLE", ""), ("ASKING", "")],
)
def test_destination_answer_requires_active_question(state: str, box_id: str) -> None:
    """질문 상태·박스 ID가 없으면 목적지 지시를 발행하지 않는다."""
    decision = decide_destination_answer("역삼으로 보내.", VIEW, state, box_id)
    assert decision is not None and decision.kind == "say"
    assert decision.say == SAY_NO_QUESTION


@pytest.mark.parametrize(
    "text",
    [
        "역삼 말고 대치로 보내",
        "역삼으로 보내지 마",
        "강남으로 보내.",
        "역삼 쪽으로 보내",
        "대치동이요",
        "보류로 보내",
    ],
)
def test_destination_rule_does_not_match_unknown_or_complex_phrases(text: str) -> None:
    """복합·부정·미등록 목적지는 로컬 답변으로 취급하지 않는다."""
    assert decide_destination_answer(text, VIEW, "ASKING", "box-12") is None


def test_local_answers_require_zone_map() -> None:
    """zone_map 수신 전에는 stop 외 로컬 답변을 만들지 않는다."""
    assert decide_bare_dong("대치동.", None, "ASKING", "box-12") is None
    assert decide_destination_answer("역삼으로 보내.", None, "ASKING", "box-12") is None


@pytest.mark.parametrize(
    ("state", "box_id"),
    [("RUNNING", "box-12"), ("ASKING", "")],
)
def test_bare_dong_requires_active_question(state: str, box_id: str) -> None:
    """단독 동 이름도 ASKING과 박스 ID가 있어야 발행한다."""
    decision = decide_bare_dong("대치동.", VIEW, state, box_id)
    assert decision is not None and decision.kind == "say"
    assert decision.say == SAY_NO_QUESTION
