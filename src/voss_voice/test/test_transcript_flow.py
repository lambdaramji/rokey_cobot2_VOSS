"""TranscriptFlow 시험: stop 이 앞 발화의 LLM 대기에 막히지 않는지(안전, #71 리뷰), AI 꺼짐 안내."""

import threading
import time

from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import SAY_AI_DOWN, SAY_BUSY, TranscriptFlow

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
