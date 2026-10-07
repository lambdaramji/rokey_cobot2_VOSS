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

app = FastAPI(title="VOSS AI", docs_url=None, redoc_url=None)

# 도메인 단어를 앞에 주면 고유명사 전사가 안정적이다
STT_PROMPT = os.getenv(
    "WHISPER_PROMPT",
    "헬로 로키. 역삼동, 대치동, 청담동. 분류, 보류, 멈춰, 다시 시작, 몇 개 남았어.",
)
_whisper = None
_openai = None


def _err(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"ok": False, "message": message})


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


def _get_openai():
    global _openai
    if _openai is None:
        from openai import OpenAI

        _openai = OpenAI()  # OPENAI_API_KEY 는 환경 변수에서만 읽는다
    return _openai


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
async def stt(audio: Annotated[UploadFile, File()], language: Annotated[str, Form()] = "ko"):
    data = await audio.read()
    if not data.startswith(b"RIFF"):
        return _err(400, "AUDIO_INVALID")
    t0 = time.monotonic()
    try:
        segments, info = _get_whisper().transcribe(
            io.BytesIO(data), language=language, beam_size=1, initial_prompt=STT_PROMPT
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:  # noqa: BLE001 — 모델·장치 오류를 코드로 돌려준다
        return _err(500, f"STT_ERROR: {type(e).__name__}")
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
        return _err(503, "LLM_ERROR: OPENAI_MODEL/OPENAI_API_KEY not set")
    t0 = time.monotonic()
    try:
        r = _get_openai().chat.completions.create(
            model=model,
            messages=build_messages(req.text, req.allowed),
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "intent", "schema": INTENT_SCHEMA, "strict": True},
            },
            temperature=0,
            timeout=float(os.getenv("LLM_TIMEOUT_S", "3")),
        )
        raw = r.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        return _err(
            504 if "Timeout" in name else 502, "LLM_TIMEOUT" if "Timeout" in name else "LLM_ERROR"
        )
    out = normalize(raw, req.text)
    if out is None:
        return _err(422, "PARSE_ERROR")
    return {
        "ok": True,
        "intent": out,
        "llm_ms": int(1000 * (time.monotonic() - t0)),
        "model": model,
    }
