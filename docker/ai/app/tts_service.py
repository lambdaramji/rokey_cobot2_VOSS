"""OpenAI TTS를 호출해 PCM 음성 조각을 전달한다.
입력: 한국어 안내 문장, FastAPI 환경 변수.
출력: 24kHz 16-bit little-endian PCM 스트림.
근거: docs/interfaces/web_api.md, pending #12.
"""

import os
from collections.abc import Iterator

from openai import OpenAI

PCM_CHUNK_SIZE = 4096
DEFAULT_TIMEOUT_S = 5.0
TTS_INSTRUCTIONS = (
    "한국어로 또렷하고 자연스럽게 안내하세요. 로봇 작업 안내이므로 차분하고 짧게 말하세요."
)


def iter_tts_pcm(text: str) -> Iterator[bytes]:
    """OpenAI 생성 음성을 PCM 단위로 순서대로 전달한다."""
    client = OpenAI(
        api_key=os.environ["TTS_OPENAI_API_KEY"],
        max_retries=0,
        timeout=float(os.getenv("TTS_TIMEOUT_S", DEFAULT_TIMEOUT_S)),
    )

    with client.audio.speech.with_streaming_response.create(
        model=os.environ["TTS_MODEL"],
        voice=os.environ["TTS_VOICE"],
        input=text,
        instructions=TTS_INSTRUCTIONS,
        response_format="pcm",
    ) as response:
        for chunk in response.iter_bytes(chunk_size=PCM_CHUNK_SIZE):
            if chunk:
                yield chunk
