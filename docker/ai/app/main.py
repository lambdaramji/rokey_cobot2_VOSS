"""VOSS AI 서비스 (FastAPI) — 음성 ROS 노드 전용, 127.0.0.1:8000 (ADR-0006, web_api.md).

POST /ai/stt     Whisper 전사 (faster-whisper)
POST /ai/intent  자연어 → intent JSON (OpenAI structured output)
GET  /ai/health  상태

환경 변수(.env, gitignore): OPENAI_API_KEY, OPENAI_MODEL, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE
"""

from __future__ import annotations

import io
import os
import time
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.intent_prompt import INTENT_SCHEMA, build_messages, normalize
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI

app = FastAPI(title="VOSS AI", docs_url=None, redoc_url=None)

# 도메인 단어를 앞에 주면 고유명사 전사가 안정적이다
STT_PROMPT = os.getenv(
    "WHISPER_PROMPT",
    "헬로 로키. 역삼동, 대치동, 청담동. 분류, 보류, 멈춰, 다시 시작, 몇 개 남았어.",
)
_whisper = None
_intent_llm = None


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


def _get_intent_llm():
    """환경 변수 설정으로 LangChain structured-output LLM을 한 번 생성해 돌려준다."""
    global _intent_llm

    if _intent_llm is not None:
        return _intent_llm

    model = os.getenv("OPENAI_MODEL", "")
    timeout_s = float(os.getenv("LLM_TIMEOUT_S", "3"))

    llm = ChatOpenAI(
        model=model,
        temperature=0,
        timeout=timeout_s,
    )

    _intent_llm = llm.with_structured_output(
        INTENT_SCHEMA,
        method="json_schema",
        strict=True,
    )
    return _intent_llm


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
        raw = _get_intent_llm().invoke(
            build_messages(req.text, req.allowed)
        )
    except OutputParserException as error:
        return _err(422, "PARSE_ERROR", type(error).__name__)
    except Exception as error:  # noqa: BLE001 — LLM SDK 오류를 HTTP 계약 코드로 변환한다
        error_name = type(error).__name__

        if "Timeout" in error_name:
            return _err(504, "LLM_TIMEOUT", error_name)

        return _err(502, "LLM_ERROR", error_name)

    out = normalize(raw, req.text)
    if out is None:
        return _err(422, "PARSE_ERROR", "LLM output is not a valid intent")
    return {
        "ok": True,
        "intent": out,
        "llm_ms": int(1000 * (time.monotonic() - t0)),
        "model": model,
    }
