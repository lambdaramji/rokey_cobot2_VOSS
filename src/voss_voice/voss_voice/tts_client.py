"""tts_client: 로컬 FastAPI에서 PCM 음성을 받아온다.
입력: 한국어 안내 문장.
출력: PCM 바이트 조각.
근거: docs/interfaces/web_api.md, ADR-0006.
"""

import json
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TTS_URL = "http://127.0.0.1:8000/ai/tts"
HTTP_TIMEOUT_S = 10.0
PCM_CHUNK_SIZE = 4096
PCM_CONTENT_TYPE = "application/octet-stream"
PCM_FORMAT = "S16LE;rate=24000;channels=1"


class TTSClientError(RuntimeError):
    """FastAPI TTS 요청이나 PCM 형식 확인 실패를 나타낸다."""


def stream_tts_audio(text: str) -> Iterator[bytes]:
    """FastAPI에서 음성 조각을 받아 순서대로 전달한다."""
    request_body = json.dumps(
        {"text": text},
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        TTS_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            _validate_audio_headers(response.headers)

            while True:
                chunk = response.read(PCM_CHUNK_SIZE)
                if not chunk:
                    break

                yield chunk
    except HTTPError as error:
        raise TTSClientError(f"TTS HTTP status: {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise TTSClientError(f"TTS connection failed: {type(error).__name__}") from error


def _validate_audio_headers(headers) -> None:
    """FastAPI에서 약속한 PCM 형식인지 확인한다."""
    content_type = headers.get_content_type()
    audio_format = headers.get("X-Audio-Format")

    if content_type != PCM_CONTENT_TYPE:
        raise TTSClientError("Unexpected TTS Content-Type")

    if audio_format != PCM_FORMAT:
        raise TTSClientError("Unexpected PCM audio format")
