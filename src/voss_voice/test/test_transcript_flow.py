"""TranscriptFlow 시험: stop 이 앞 발화의 LLM 대기에 막히지 않는지(안전, #71 리뷰), AI 꺼짐 안내."""

import threading
import time

from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import SAY_AI_DOWN, TranscriptFlow

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

    f, published, _ = _flow(llm)
    ts = [threading.Thread(target=f.handle, args=(f"시작 {i}",)) for i in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak[0] == 1 and len(published) == 3


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
