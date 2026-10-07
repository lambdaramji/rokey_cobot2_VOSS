"""AI 서비스 시험 — Whisper·OpenAI 는 가짜로 바꿔 네트워크·GPU 없이 돈다.

실행: cd docker/ai && pip install -r requirements.txt httpx pytest && pytest -q
"""

import io
import json
import wave
from types import SimpleNamespace

import httpx
import pytest
from app import main
from app.intent_prompt import INTENT_SCHEMA, build_messages, normalize
from fastapi.testclient import TestClient

ALLOWED = {
    "dongs": ["역삼동", "대치동", "청담동"],
    "aliases": {"역삼동": ["역삼"]},
    "zones": ["A", "B", "C"],
}


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return out.getvalue()


# --- 순수 로직 ---
def test_schema_is_strict_and_complete():
    assert INTENT_SCHEMA["additionalProperties"] is False
    assert set(INTENT_SCHEMA["required"]) == set(INTENT_SCHEMA["properties"])


def test_messages_carry_allow_list():
    msgs = build_messages("역삼부터 해", ALLOWED)
    assert msgs[-1] == {"role": "user", "content": "역삼부터 해"}
    assert "역삼동" in msgs[0]["content"] and '"zones": ["A", "B", "C"]' in msgs[0]["content"]


@pytest.mark.parametrize(
    "raw,expect",
    [
        (
            '{"type":"priority","dong":"역삼동","zone":null,"count":0,"query_kind":null,"raw_text":"x"}',
            {"type": "priority", "dong": "역삼동", "zone": None, "query_kind": None},
        ),
        (
            '{"type":"answer","dong":null,"zone":"hold","count":0,"query_kind":null,"raw_text":"x"}',
            {"type": "answer", "dong": None, "zone": "HOLD", "query_kind": None},
        ),
        (
            '{"type":"query_history","dong":null,"zone":null,"count":0,"query_kind":"held_count","raw_text":"x"}',
            {"type": "query_history", "dong": None, "zone": None, "query_kind": "held_count"},
        ),
    ],
)
def test_normalize_ok(raw, expect):
    out = normalize(raw, "원문")
    assert {k: out[k] for k in expect} == expect
    assert out["raw_text"] == "원문" and out["count"] == 0


@pytest.mark.parametrize("raw", ["not json", '{"type":"unknown"}', '{"type":"dance"}', "{}"])
def test_normalize_rejects(raw):
    assert normalize(raw, "x") is None


# --- HTTP (가짜 모델) ---
@pytest.fixture
def client(monkeypatch):
    seg = SimpleNamespace(text=" 헬로 로키 작업 시작 ")
    fake_whisper = SimpleNamespace(
        transcribe=lambda *a, **k: ([seg], SimpleNamespace(duration=1.5))
    )
    monkeypatch.setattr(main, "_get_whisper", lambda: fake_whisper)
    return TestClient(main.app)


class FakeChain:
    """LangChain 체인 자리에 끼우는 가짜. invoke 결과(또는 예외)를 정해 둔다."""

    def __init__(self, parsed=None, error=None, parsing_error=None):
        self.parsed = parsed
        self.error = error
        self.parsing_error = parsing_error
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return {"raw": None, "parsed": self.parsed, "parsing_error": self.parsing_error}


def _use_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")


def test_stt_ok(client):
    r = client.post(
        "/ai/stt", files={"audio": ("seg.wav", _wav(), "audio/wav")}, data={"language": "ko"}
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["text"] == "헬로 로키 작업 시작"
    assert body["duration_ms"] == 1500


def test_stt_rejects_non_wav(client):
    r = client.post("/ai/stt", files={"audio": ("x.mp3", b"ID3....", "audio/mpeg")})
    assert r.status_code == 400 and r.json()["message"] == "AUDIO_INVALID"


def test_intent_needs_key_and_model(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    r = client.post("/ai/intent", json={"text": "시작", "allowed": ALLOWED})
    body = r.json()
    assert r.status_code == 503 and body["ok"] is False
    assert body["message"] == "LLM_ERROR" and "OPENAI_MODEL" in body["detail"]


def test_intent_ok(client, monkeypatch):
    _use_model(monkeypatch)
    parsed = {
        "type": "priority",
        "dong": "역삼동",
        "zone": None,
        "count": 0,
        "query_kind": None,
        "raw_text": "역삼부터",
    }
    chain = FakeChain(parsed=parsed)
    monkeypatch.setattr(main, "_get_intent_chain", lambda: chain)

    r = client.post("/ai/intent", json={"text": "역삼부터 해", "allowed": ALLOWED})

    body = r.json()
    assert body["ok"] is True
    assert body["intent"]["dong"] == "역삼동"
    assert body["intent"]["raw_text"] == "역삼부터 해"  # 원문은 LLM 이 아니라 요청에서 가져온다
    assert chain.messages[-1] == {"role": "user", "content": "역삼부터 해"}


def test_intent_parse_failure_maps_to_parse_error(client, monkeypatch):
    _use_model(monkeypatch)
    chain = FakeChain(parsed=None, parsing_error=ValueError("bad json"))
    monkeypatch.setattr(main, "_get_intent_chain", lambda: chain)

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 422
    assert r.json()["message"] == "PARSE_ERROR"
    assert r.json()["detail"] == "ValueError"


def test_intent_unknown_type_maps_to_parse_error(client, monkeypatch):
    _use_model(monkeypatch)
    chain = FakeChain(parsed={"type": "dance"})
    monkeypatch.setattr(main, "_get_intent_chain", lambda: chain)

    r = client.post("/ai/intent", json={"text": "춤춰"})

    assert r.status_code == 422 and r.json()["message"] == "PARSE_ERROR"


def test_intent_timeout_maps_to_code(client, monkeypatch):
    _use_model(monkeypatch)

    class APITimeoutError(Exception):
        pass

    monkeypatch.setattr(main, "_get_intent_chain", lambda: FakeChain(error=APITimeoutError()))

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 504 and r.json()["message"] == "LLM_TIMEOUT"
    assert r.json()["detail"] == "APITimeoutError"


def test_intent_other_error_maps_to_llm_error(client, monkeypatch):
    _use_model(monkeypatch)
    monkeypatch.setattr(main, "_get_intent_chain", lambda: FakeChain(error=RuntimeError()))

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 502 and r.json()["message"] == "LLM_ERROR"


# --- 진짜 LangChain 체인 + 가짜 OpenAI 서버 (httpx MockTransport, 네트워크 없음) ---
def _real_chain_with_fake_server(monkeypatch, handler):
    """build_intent_chain 으로 진짜 체인을 만들고, HTTP 만 가짜 서버로 보낸다."""
    _use_model(monkeypatch)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    chain = main.build_intent_chain(http_client=http_client)
    monkeypatch.setattr(main, "_get_intent_chain", lambda: chain)


def _openai_reply(content: str) -> dict:
    """OpenAI chat.completions 응답 모양 (필요한 필드만)."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def test_real_chain_sends_strict_json_schema_and_parses_reply(client, monkeypatch):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        content = json.dumps(
            {
                "type": "answer",
                "dong": None,
                "zone": "HOLD",
                "count": 0,
                "query_kind": None,
                "raw_text": "보류",
            }
        )
        return httpx.Response(200, json=_openai_reply(content))

    _real_chain_with_fake_server(monkeypatch, handler)

    r = client.post("/ai/intent", json={"text": "그건 보류해", "allowed": ALLOWED})

    # OpenAI 로 나간 요청: 모델·온도·strict JSON Schema 가 그대로 실린다
    assert sent["model"] == "test-model"
    assert sent["temperature"] == 0
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"] == INTENT_SCHEMA
    # 응답은 기존 계약 그대로
    body = r.json()
    assert body["ok"] is True and body["intent"]["zone"] == "HOLD"
    assert body["model"] == "test-model"


def test_real_chain_timeout_maps_to_llm_timeout(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    _real_chain_with_fake_server(monkeypatch, handler)

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 504 and r.json()["message"] == "LLM_TIMEOUT"


def test_real_chain_server_error_maps_to_llm_error(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    _real_chain_with_fake_server(monkeypatch, handler)

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 502 and r.json()["message"] == "LLM_ERROR"


def test_real_chain_broken_json_maps_to_parse_error(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_reply("not json"))

    _real_chain_with_fake_server(monkeypatch, handler)

    r = client.post("/ai/intent", json={"text": "시작"})

    assert r.status_code == 422 and r.json()["message"] == "PARSE_ERROR"


def test_health_never_leaks_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    body = client.get("/ai/health").json()
    assert body["openai_key_set"] is True and "sk-secret" not in json.dumps(body)
