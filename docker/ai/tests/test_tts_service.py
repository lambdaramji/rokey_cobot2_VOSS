"""T10 /ai/tts 계약과 오류 처리를 모의 스트림으로 검증한다."""

from app import main
from fastapi.testclient import TestClient

TEST_PCM = b"\x00\x00\x01\x00"


def test_tts_stream_returns_pcm(monkeypatch) -> None:
    """PCM 응답 본문과 Content-Type을 확인한다."""
    monkeypatch.setenv("TTS_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TTS_MODEL", "gpt-4o-mini-tts")
    monkeypatch.setenv("TTS_VOICE", "coral")

    def fake_tts(text: str):
        assert text == "분류를 시작합니다"
        yield TEST_PCM[:2]
        yield TEST_PCM[2:]

    monkeypatch.setattr(main, "iter_tts_pcm", fake_tts)

    response = TestClient(main.app).post(
        "/ai/tts",
        json={"text": "분류를 시작합니다"},
    )

    assert response.status_code == 200
    assert response.content == TEST_PCM
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-audio-format"] == "S16LE;rate=24000;channels=1"


def test_tts_rejects_blank_text() -> None:
    """공백 문장은 합성을 요청하지 않는다."""
    response = TestClient(main.app).post(
        "/ai/tts",
        json={"text": "  "},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "TTS_INVALID"


def test_tts_rejects_too_long_text() -> None:
    """입력 길이 제한을 확인한다."""
    response = TestClient(main.app).post(
        "/ai/tts",
        json={"text": "가" * 501},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "TTS_INVALID"


def test_tts_requires_configuration(monkeypatch) -> None:
    """API 키가 없으면 모델을 호출하지 않는다."""
    monkeypatch.delenv("TTS_OPENAI_API_KEY", raising=False)

    response = TestClient(main.app).post(
        "/ai/tts",
        json={"text": "테스트"},
    )

    assert response.status_code == 503
    assert response.json()["message"] == "TTS_UNAVAILABLE"


def test_tts_timeout_returns_error_code(monkeypatch) -> None:
    """첫 PCM 수신 전의 시간 초과는 504로 반환한다."""
    monkeypatch.setenv("TTS_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TTS_MODEL", "gpt-4o-mini-tts")
    monkeypatch.setenv("TTS_VOICE", "coral")

    def fake_timeout(text: str):
        raise TimeoutError("simulated timeout")
        yield b""  # 제너레이터 형태를 유지한다.

    monkeypatch.setattr(main, "iter_tts_pcm", fake_timeout)

    response = TestClient(main.app).post(
        "/ai/tts",
        json={"text": "테스트"},
    )

    assert response.status_code == 504
    assert response.json()["message"] == "TTS_TIMEOUT"
