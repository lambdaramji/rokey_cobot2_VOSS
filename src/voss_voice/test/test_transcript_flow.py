"""TranscriptFlow 시험: stop 이 앞 발화의 LLM 대기에 막히지 않는지(안전, #71 리뷰), AI 꺼짐 안내."""

import threading
import time

from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import SAY_AI_DOWN, SAY_BUSY, TranscriptFlow

from voss_voice.http_client import IntentParseError
from voss_voice.intent_logic import SAY_RETRY

VIEW = ZoneMapView.from_entries([("역삼동", "A", ["역삼"]), ("대치동", "B", [])])


def _flow(post_intent, get_stats=lambda q: {"ok": True, "count": 1}):
    published, said = [], []
    f = TranscriptFlow(post_intent, get_stats, published.append, said.append)
    f.view = VIEW
    return f, published, said


def test_stop_is_not_blocked_by_slow_llm():
    started = threading.Event()

    def slow_llm(text, allowed):
        started.set()
        time.sleep(1.5)  # 앞 발화가 LLM 을 오래 기다리는 중
        return {"type": "priority", "dong": "역삼동"}

    f, published, _ = _flow(slow_llm)
    t = threading.Thread(target=f.handle, args=("역삼 먼저 해",))
    t.start()
    assert started.wait(1.0)

    t0 = time.monotonic()
    kind, _ = f.handle("멈춰")
    stop_ms = 1000 * (time.monotonic() - t0)
    assert kind == "stop"
    assert stop_ms < 100, f"stop 이 {stop_ms:.0f} ms 걸림"
    assert published[0]["type"] == "stop"  # 앞 발화보다 먼저 나감

    t.join()
    assert [p["type"] for p in published] == ["stop", "priority"]


def test_llm_calls_are_serialized():
    active, peak, lock = [0], [0], threading.Lock()

    def llm(text, allowed):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        return {"type": "start"}

    f, published, said = _flow(llm)
    kinds = []
    ts = [
        threading.Thread(target=lambda i=i: kinds.append(f.handle(f"시작 {i}")[0]))
        for i in range(3)
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # 한 번에 하나만 LLM 을 부르고, 그사이 온 발화는 기다리지 않고 "처리 중" 으로 돌려보낸다
    assert peak[0] == 1
    assert sorted(kinds) == ["busy", "busy", "publish"] and len(published) == 1
    assert said == [SAY_BUSY]  # 같은 문장은 3 초 중복 억제


def test_busy_utterances_do_not_hold_threads():
    """처리 중에 온 발화는 바로 돌아와야 한다 — 잠금을 기다리면 executor 스레드(4)가 차서
    "멈춰" 를 받을 스레드가 없어진다(#71 리뷰: 일반 발화 4개 쌓이면 stop 2.8 s 지연 재현)."""
    started = threading.Event()

    def slow_llm(text, allowed):
        started.set()
        time.sleep(1.0)
        return {"type": "start"}

    f, published, _ = _flow(slow_llm)
    t = threading.Thread(target=f.handle, args=("시작해",))
    t.start()
    assert started.wait(1.0)
    t0 = time.monotonic()
    kinds = [f.handle(f"역삼 먼저 {i}")[0] for i in range(6)]
    assert kinds == ["busy"] * 6
    assert 1000 * (time.monotonic() - t0) < 100
    assert f.handle("멈춰")[0] == "stop"
    t.join()


def test_ai_down_says_so_instead_of_retry():
    f, published, said = _flow(lambda t, a: None)
    kind, _ = f.handle("역삼 먼저 해")
    assert kind == "say" and said == [SAY_AI_DOWN] and published == []


def test_stop_works_even_when_ai_down_and_no_zone_map():
    f, published, _ = _flow(lambda t, a: None)
    f.view = None
    assert f.handle("정지")[0] == "stop" and published[0]["type"] == "stop"


def test_answer_uses_state_at_utterance_time():
    seen = {}

    def llm(text, allowed):
        seen["state_before"] = "ASKING"
        f.state, f.box_id = "RUNNING", ""  # LLM 대기 중 상태가 바뀌어도
        return {"type": "answer", "dong": "역삼동"}

    f, published, _ = _flow(llm)
    f.state, f.box_id = "ASKING", "b7"
    f.handle("역삼이야")
    assert published[0]["box_id"] == "b7"


def test_query_goes_to_stats_and_is_spoken():
    f, published, said = _flow(
        lambda t, a: {"type": "query_history", "query_kind": "held_count"},
        get_stats=lambda q: {"ok": True, "count": 2},
    )
    assert f.handle("보류 몇 개야")[0] == "query"
    assert said == ["보류는 2개입니다."] and published == []


def test_empty_text_ignored():
    f, published, said = _flow(lambda t, a: {"type": "start"})
    assert f.handle("   ")[0] == "empty" and not published and not said


def test_bare_dong_is_rejected_when_not_asking() -> None:
    """질문 중이 아니면 동 이름만으로 우선 분류를 시작하지 않는다."""
    def unexpected_llm(text: str, allowed: dict) -> dict:
        """로컬 판단 대상에서는 LLM 호출을 금지한다."""
        raise AssertionError("LLM이 호출되면 안 됩니다")

    flow, published, spoken = _flow(unexpected_llm)
    flow.state = "IDLE"

    result_kind, _ = flow.handle("대치동")

    assert result_kind == "say"
    assert published == []
    assert spoken == ["지금은 답할 질문이 없습니다."]


def test_bare_dong_becomes_answer_when_asking() -> None:
    """질문 중에는 동 이름을 현재 박스의 답변으로 처리한다."""
    def unexpected_llm(text: str, allowed: dict) -> dict:
        """로컬 답변 처리에서는 LLM 호출을 금지한다."""
        raise AssertionError("LLM이 호출되면 안 됩니다")

    flow, published, _ = _flow(unexpected_llm)
    flow.state = "ASKING"
    flow.box_id = "test-box-12"

    result_kind, _ = flow.handle("대치동")

    assert result_kind == "publish"
    assert len(published) == 1
    assert published[0]["type"] == "answer"
    assert published[0]["dong"] == "대치동"
    assert published[0]["box_id"] == "test-box-12"


def test_parse_error_asks_user_to_repeat_without_publishing() -> None:
    """LLM 파싱 실패 시 실행하지 않고 다시 말해 달라고 안내한다."""

    def raise_parse_error(text: str, allowed: dict) -> dict:
        """가짜 LLM에서 PARSE_ERROR를 발생시킨다."""
        raise IntentParseError("FastAPI /ai/intent: PARSE_ERROR")

    flow, published, spoken = _flow(raise_parse_error)

    result_kind, _ = flow.handle("오늘 날씨 알려줘")

    assert result_kind == "say"
    assert published == []
    assert spoken == [SAY_RETRY]

    # 예외 처리 후 잠금이 풀렸는지도 확인한다.
    second_kind, _ = flow.handle("로봇 춤춰")
    assert second_kind == "say"


def test_destination_answer_uses_current_box_id() -> None:
    """질문 중 목적지 발화를 현재 박스의 답변으로 처리한다."""
    def unexpected_llm(text: str, allowed: dict) -> dict:
        """로컬 답변 처리에서 LLM 호출을 금지한다."""
        raise AssertionError("LLM을 호출하면 안 됩니다")

    flow, published, _ = _flow(unexpected_llm)
    flow.state = "ASKING"
    flow.box_id = "box-12"

    result_kind, _ = flow.handle("역삼으로 보내")

    assert result_kind == "publish"
    assert len(published) == 1
    assert published[0]["type"] == "answer"
    assert published[0]["dong"] == "역삼동"
    assert published[0]["box_id"] == "box-12"


def test_destination_answer_without_question_is_rejected() -> None:
    """질문 상태가 아니면 목적지 발화로 명령을 발행하지 않는다."""
    def unexpected_llm(text: str, allowed: dict) -> dict:
        """질문이 없는 목적지 발화를 LLM에 보내지 않는다."""
        raise AssertionError("LLM을 호출하면 안 됩니다")

    flow, published, spoken = _flow(unexpected_llm)
    flow.state = "IDLE"

    result_kind, _ = flow.handle("역삼으로 보내")

    assert result_kind == "say"
    assert published == []
    assert spoken == ["지금은 답할 질문이 없습니다."]


def test_explicit_priority_is_preserved_while_asking() -> None:
    """질문 중에도 명시적인 우선순위 지시는 유지한다."""
    def fake_llm(text: str, allowed: dict) -> dict:
        """명시적인 우선순위 명령을 반환한다."""
        return {"type": "priority", "dong": "역삼동"}

    flow, published, _ = _flow(fake_llm)
    flow.state = "ASKING"
    flow.box_id = "box-12"

    result_kind, _ = flow.handle("역삼 먼저 분류해")

    assert result_kind == "publish"
    assert len(published) == 1
    assert published[0]["type"] == "priority"
    assert published[0]["box_id"] == ""
