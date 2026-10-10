"""FastAPI TTS 응답 형식과 스트림 수신을 검증한다."""

import io
import json
from email.message import Message

import pytest

from voss_voice import tts_client


class FakeAudioResponse(io.BytesIO):
    """실제 HTTP 호출 대신 PCM 데이터를 전달한다."""

    def __init__(self, data: bytes, valid: bool = True) -> None:
        super().__init__(data)
        self.headers = Message()

        content_type = "application/octet-stream"
        if not valid:
            content_type = "application/json"

        self.headers["Content-Type"] = content_type
        self.headers["X-Audio-Format"] = tts_client.PCM_FORMAT


def test_tts_client_receives_pcm_in_order(monkeypatch) -> None:
    """PCM 조각을 순서대로 이어 받을 수 있다."""
    expected_pcm = b"\x01\x00\x02\x00"

    def fake_urlopen(request, timeout):
        assert request.get_method() == "POST"
        body = json.loads(request.data.decode("utf-8"))
        assert body["text"] == "안녕하세요"
        return FakeAudioResponse(expected_pcm)

    monkeypatch.setattr(tts_client, "urlopen", fake_urlopen)

    received_pcm = b"".join(tts_client.stream_tts_audio("안녕하세요"))

    assert received_pcm == expected_pcm


def test_tts_client_rejects_wrong_content_type(monkeypatch) -> None:
    """오류 JSON을 PCM 음성으로 잘못 재생하지 않는다."""

    def fake_urlopen(request, timeout):
        return FakeAudioResponse(b'{"ok":false}', valid=False)

    monkeypatch.setattr(tts_client, "urlopen", fake_urlopen)

    with pytest.raises(tts_client.TTSClientError):
        list(tts_client.stream_tts_audio("테스트"))
