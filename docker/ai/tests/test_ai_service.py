"""AI 서비스 시험 — Whisper·LangChain LLM은 가짜로 바꿔 네트워크·GPU 없이 돈다.

실행: cd docker/ai && pip install -r requirements.txt httpx pytest && pytest -q
"""

import io
import json
import wave
from types import SimpleNamespace

import pytest
from app import main
from app.intent_prompt import INTENT_SCHEMA, build_messages, normalize
from fastapi.testclient import TestClient
from langchain_core.exceptions import OutputParserException

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

class FakeIntentLlm:
    """네트워크 없이 LangChain structured-output 호출 결과를 흉내 낸다."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def invoke(self, messages):
        """가짜 LLM 결과를 반환하거나 지정한 예외를 발생시킨다."""
        if self.error is not None:
            raise self.error

        return self.result

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
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    result = {
        "type": "priority",
        "dong": "역삼동",
        "zone": None,
        "count": 0,
        "query_kind": None,
        "raw_text": "역삼부터",
    }

    fake_llm = FakeIntentLlm(result=result)
    monkeypatch.setattr(main, "_get_intent_llm", lambda: fake_llm)

    response = client.post(
        "/ai/intent",
        json={
            "text": "역삼부터 해",
            "allowed": ALLOWED,
        },
    )

    body = response.json()

    assert body["ok"]
    assert body["intent"]["dong"] == "역삼동"
    assert body["intent"]["raw_text"] == "역삼부터 해"


def test_intent_timeout_maps_to_code(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    class APITimeoutError(Exception):
        pass

    fake_llm = FakeIntentLlm(error=APITimeoutError())
    monkeypatch.setattr(main, "_get_intent_llm", lambda: fake_llm)

    response = client.post(
        "/ai/intent",
        json={"text": "시작"},
    )

    assert response.status_code == 504
    assert response.json()["message"] == "LLM_TIMEOUT"
    assert response.json()["detail"] == "APITimeoutError"


def test_health_never_leaks_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    body = client.get("/ai/health").json()
    assert body["openai_key_set"] is True and "sk-secret" not in json.dumps(body)

def test_intent_parse_error_maps_to_code(client, monkeypatch):
    """LangChain 구조화 출력 파싱 실패가 PARSE_ERROR로 변환되는지 확인한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    fake_llm = FakeIntentLlm(
        error=OutputParserException("invalid structured output")
    )
    monkeypatch.setattr(main, "_get_intent_llm", lambda: fake_llm)

    response = client.post(
        "/ai/intent",
        json={
            "text": "역삼부터 해",
            "allowed": ALLOWED,
        },
    )

    body = response.json()

    assert response.status_code == 422
    assert body["ok"] is False
    assert body["message"] == "PARSE_ERROR"
    assert body["detail"] == "OutputParserException"

def test_intent_llm_uses_strict_json_schema(monkeypatch):
    """LangChain이 계약된 strict JSON Schema 설정으로 구성되는지 확인한다."""
    calls = {}
    fake_structured_llm = object()

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            calls["schema"] = schema
            calls["structured"] = kwargs
            return fake_structured_llm

    monkeypatch.setattr(main, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(main, "_intent_llm", None)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_S", "3")

    result = main._get_intent_llm()

    assert result is fake_structured_llm
    assert calls["init"]["model"] == "test-model"
    assert calls["init"]["temperature"] == 0
    assert calls["init"]["timeout"] == 3.0
    assert calls["schema"] is INTENT_SCHEMA
    assert calls["structured"] == {
        "method": "json_schema",
        "strict": True,
    }