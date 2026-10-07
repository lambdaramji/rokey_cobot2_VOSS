"""AI 서비스 시험 — Whisper·OpenAI 는 가짜로 바꿔 네트워크·GPU 없이 돈다.

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


def _fake_openai(content=None, exc=None):
    def create(**kw):
        if exc:
            raise exc
        assert kw["response_format"]["json_schema"]["strict"] is True
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_stt_ok(client):
    r = client.post(
        "/ai/stt", files={"audio": ("seg.wav", _wav(), "audio/wav")}, data={"language": "ko"}
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["text"] == "헬로 로키 작업 시작"
    assert body["duration_ms"] == 1500


def test_stt_rejects_non_wav(client):
    r = client.post("/ai/stt", files={"audio": ("x.mp3", b"ID3....", "audio/mpeg")})
    assert r.status_code == 400 and r.json() == {"ok": False, "message": "AUDIO_INVALID"}


def test_intent_needs_key_and_model(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    r = client.post("/ai/intent", json={"text": "시작", "allowed": ALLOWED})
    assert r.status_code == 503 and r.json()["ok"] is False


def test_intent_ok(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    content = json.dumps(
        {
            "type": "priority",
            "dong": "역삼동",
            "zone": None,
            "count": 0,
            "query_kind": None,
            "raw_text": "역삼부터",
        }
    )
    monkeypatch.setattr(main, "_get_openai", lambda: _fake_openai(content))
    r = client.post("/ai/intent", json={"text": "역삼부터 해", "allowed": ALLOWED})
    body = r.json()
    assert (
        body["ok"]
        and body["intent"]["dong"] == "역삼동"
        and body["intent"]["raw_text"] == "역삼부터 해"
    )


def test_intent_timeout_maps_to_code(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    class APITimeoutError(Exception):
        pass

    monkeypatch.setattr(main, "_get_openai", lambda: _fake_openai(exc=APITimeoutError()))
    r = client.post("/ai/intent", json={"text": "시작"})
    assert r.status_code == 504 and r.json()["message"] == "LLM_TIMEOUT"


def test_health_never_leaks_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    body = client.get("/ai/health").json()
    assert body["openai_key_set"] is True and "sk-secret" not in json.dumps(body)
