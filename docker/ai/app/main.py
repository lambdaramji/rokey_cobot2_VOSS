"""VOSS AI 서비스 (FastAPI) — 음성 ROS 노드 전용, 127.0.0.1:8000 (ADR-0006, web_api.md).

POST /ai/stt     Whisper 전사 (faster-whisper)
POST /ai/intent  자연어 → intent JSON (LangChain + OpenAI structured output, BRD TR-VOICE-03)
GET  /ai/health  상태

환경 변수(.env, gitignore): OPENAI_API_KEY, OPENAI_MODEL, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE,
LLM_TIMEOUT_S
"""

from __future__ import annotations

import io
import logging
import os
import time
from collections.abc import Iterator
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.intent_prompt import INTENT_SCHEMA, build_messages, normalize
from app.tts_service import iter_tts_pcm

app = FastAPI(title="VOSS AI", docs_url=None, redoc_url=None)

# 도메인 단어를 앞에 주면 고유명사 전사가 안정적이다
STT_PROMPT = os.getenv(
    "WHISPER_PROMPT",
    "헬로 로키. 역삼동, 대치동, 청담동. 분류, 보류, 멈춰, 다시 시작, 몇 개 남았어.",
)
# LLM 출력 형식. OpenAI strict JSON Schema 로 보내 스키마 밖의 키·값을 처음부터 막는다.
INTENT_RESPONSE_FORMAT = {"name": "intent", "schema": INTENT_SCHEMA, "strict": True}

_whisper = None
_intent_chain = None


def _err(code: int, message: str, detail: str = "") -> JSONResponse:
    """web_api.md: message = 대문자 코드, detail = 사람이 읽는 설명."""
    return JSONResponse(
        status_code=code, content={"ok": False, "message": message, "detail": detail}
    )


def _get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel  # 무거워서 첫 호출 때 올린다

        _whisper = WhisperModel(
            os.getenv("WHISPER_MODEL", "small"),  # pending #6: 10/08 동시 부하 시험 후 확정
            device=os.getenv("WHISPER_DEVICE", "cuda"),
            compute_type=os.getenv("WHISPER_COMPUTE", "float16"),
        )
    return _whisper


def build_intent_chain(http_client=None):
    """LangChain 체인을 만든다: 메시지 목록 → {"raw", "parsed", "parsing_error"}.

    http_client 는 시험에서 가짜 OpenAI 서버를 끼울 때만 쓴다(평소에는 None).
    OPENAI_API_KEY 는 ChatOpenAI 가 환경 변수에서 읽는다.
    """
    from langchain_openai import ChatOpenAI  # 무거워서 첫 호출 때 올린다

    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        temperature=0,
        timeout=float(os.getenv("LLM_TIMEOUT_S", "3")),
        # 재시도하지 않는다: 3 s 안에 답이 없으면 intent_parser 가 사용자에게 다시 말해 달라고 한다
        max_retries=0,
        http_client=http_client,
    )
    # include_raw=True: 파싱 실패를 예외 대신 parsing_error 로 받아 PARSE_ERROR 로 돌려준다
    return llm.with_structured_output(
        INTENT_RESPONSE_FORMAT, method="json_schema", include_raw=True
    )


def _get_intent_chain():
    """체인은 한 번만 만들어 두고 다시 쓴다."""
    global _intent_chain
    if _intent_chain is None:
        _intent_chain = build_intent_chain()
    return _intent_chain


def _llm_error_code(error: Exception) -> tuple[int, str]:
    """LLM 호출 예외 → (HTTP 상태, web_api.md 오류 코드)."""
    if "Timeout" in type(error).__name__:  # openai.APITimeoutError, httpx 시간 초과
        return 504, "LLM_TIMEOUT"
    return 502, "LLM_ERROR"


@app.get("/ai/health")
def health() -> dict:
    return {
        "ok": True,
        "whisper_model": os.getenv("WHISPER_MODEL", "small"),
        "whisper_loaded": _whisper is not None,
        "openai_model": os.getenv("OPENAI_MODEL", ""),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
    }


@app.post("/ai/stt")
def stt(audio: Annotated[UploadFile, File()], language: Annotated[str, Form()] = "ko"):
    # 동기 def: 블로킹 전사를 FastAPI 스레드풀에서 돌려 /ai/intent 를 막지 않는다
    data = audio.file.read()
    if not data.startswith(b"RIFF"):
        return _err(400, "AUDIO_INVALID", "WAV (RIFF) only")
    t0 = time.monotonic()
    try:
        segments, info = _get_whisper().transcribe(
            io.BytesIO(data), language=language, beam_size=1, initial_prompt=STT_PROMPT
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:  # noqa: BLE001 — 모델·장치 오류를 코드로 돌려준다
        return _err(500, "STT_ERROR", type(e).__name__)
    return {
        "ok": True,
        "text": text,
        "duration_ms": int(1000 * info.duration),
        "stt_ms": int(1000 * (time.monotonic() - t0)),
        "model": f"whisper-{os.getenv('WHISPER_MODEL', 'small')}",
    }


class IntentRequest(BaseModel):
    text: str
    allowed: dict = {}


@app.post("/ai/intent")
def intent(req: IntentRequest):
    model = os.getenv("OPENAI_MODEL")
    if not model or not os.getenv("OPENAI_API_KEY"):
        return _err(503, "LLM_ERROR", "OPENAI_MODEL/OPENAI_API_KEY not set")
    t0 = time.monotonic()
    try:
        result = _get_intent_chain().invoke(build_messages(req.text, req.allowed))
    except Exception as e:  # noqa: BLE001 — 네트워크·API 오류를 계약 코드로 바꾼다
        status, code = _llm_error_code(e)
        return _err(status, code, type(e).__name__)

    raw = result["parsed"]
    if raw is None:  # 모델이 스키마에 맞는 JSON 을 내지 못했다 (거절 응답 포함)
        error = result.get("parsing_error")
        detail = type(error).__name__ if error else "no structured output"
        return _err(422, "PARSE_ERROR", detail)
    # normalize: 허용 type·대문자 zone 정리. 허용 목록(동·구역) 최종 검증은 intent_parser 가 한다
    out = normalize(raw, req.text)
    if out is None:
        return _err(422, "PARSE_ERROR", "LLM output is not a valid intent")
    return {
        "ok": True,
        "intent": out,
        "llm_ms": int(1000 * (time.monotonic() - t0)),
        "model": model,
    }


# T10: /ai/tts는 ROS speech_out 전용이며 외부에 노출하지 않는다.
TTS_MAX_TEXT_LENGTH = 500
TTS_MEDIA_TYPE = "application/octet-stream"
TTS_LOGGER = logging.getLogger(__name__)


class TTSRequest(BaseModel):
    text: str


def _continue_tts_stream(
    first_chunk: bytes,
    remaining: Iterator[bytes],
) -> Iterator[bytes]:
    """첫 PCM 조각에 이어 나머지 음성을 전송한다."""
    try:
        yield first_chunk
        yield from remaining
    except Exception as error:
        # 응답 전송 후에는 HTTP 상태를 변경할 수 없다.
        TTS_LOGGER.error(
            "TTS_STREAM_FAILED: %s",
            type(error).__name__,
        )
        raise
    finally:
        remaining.close()


@app.post("/ai/tts")
def tts(request: TTSRequest):
    """유효한 텍스트를 PCM 스트림으로 바꿔 반환한다."""
    text = request.text.strip()

    if not text or len(text) > TTS_MAX_TEXT_LENGTH:
        return _err(400, "TTS_INVALID")

    required = ("TTS_OPENAI_API_KEY", "TTS_MODEL", "TTS_VOICE")
    if any(not os.getenv(name) for name in required):
        return _err(503, "TTS_UNAVAILABLE")

    pcm_stream = iter_tts_pcm(text)

    try:
        first_chunk = next(pcm_stream)
    except StopIteration:
        return _err(502, "TTS_ERROR", "Empty audio")
    except Exception as error:
        # 외부 SDK의 오류 세부 내용은 응답에 노출하지 않는다.
        error_name = type(error).__name__
        TTS_LOGGER.error("TTS_FAILED: %s", error_name)

        pcm_stream.close()
        if "Timeout" in error_name:
            return _err(504, "TTS_TIMEOUT", error_name)

        return _err(502, "TTS_ERROR", error_name)

    return StreamingResponse(
        _continue_tts_stream(first_chunk, pcm_stream),
        media_type=TTS_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store",
            "X-Audio-Format": "S16LE;rate=24000;channels=1",
        },
    )
