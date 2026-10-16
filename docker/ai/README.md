# VOSS AI 서비스 (FastAPI · Whisper · LangChain + OpenAI)

ADR-0006 · 계약: `docs/interfaces/web_api.md` (`/ai/stt`, `/ai/intent`), `intent_json.md`.
**음성 ROS 노드 전용**이라 `127.0.0.1:8000` 에만 바인드하고 Nginx 로 노출하지 않는다.

| 구성 | 값 | 근거 |
|---|---|---|
| 이미지 | `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04`, Python 3.12 (venv `/opt/venv`) | ADR-0006 |
| STT | faster-whisper 1.1 (CTranslate2, CUDA 12·cuDNN 9), 모델 크기는 pending #6 | ADR-0006 |
| intent | LangChain `ChatOpenAI.with_structured_output(..., method="json_schema")` + strict JSON Schema, 재시도 없음, timeout `LLM_TIMEOUT_S`(기본 3 s) | BRD TR-VOICE-03, ADR-0006 |
| LLM 모델 | `.env` 의 `OPENAI_MODEL=gpt-4o` — intent 20문장 20/20 (10/08) | pending #18 결정, #124 |


## 실행 (공용 PC, 사람이 실행)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/ai
cp .env.example .env          # OPENAI_API_KEY, OPENAI_MODEL 채우기 (.env 는 커밋 금지)
docker compose up -d --build
curl -s http://127.0.0.1:8000/ai/health

서비스는 시작하자마자 Whisper 를 백그라운드로 적재한다(`WHISPER_PRELOAD=0` 이면 첫 STT 때 적재). `whisper_loaded` 가 `true` 가 되기 전의 STT 요청은 5초 제한에 걸리므로 `scripts/web_pc_voice.sh` 는 `true` 를 기다린 뒤 음성 노드를 띄운다(10/15).
```
- Whisper 가중치는 첫 `/ai/stt` 호출 때 내려받아 `whisper-cache` 볼륨에 둔다(레포·이미지에 넣지 않음).
- 모델 크기 `WHISPER_MODEL` 은 pending #6 — 10/08 비전과 동시 부하 시험(`nvidia-smi`) 후 확정. GPU 가 모자라면 `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE=int8`.
- 운영자가 `docker/ai/.env`의 `WHISPER_PROMPT`를 확인한다. `.env.example`의 호출어·동 이름·A/B/C 구역 및 분류/보류 용어를 참고해 갱신하고 AI 컨테이너를 다시 생성한다. 실제 `.env` 값은 로그나 Git에 복사하지 않는다.

## 단독 확인
```bash
curl -s -X POST http://127.0.0.1:8000/ai/intent -H 'Content-Type: application/json' \
  -d '{"text":"역삼부터 분류해","allowed":{"dongs":["역삼동","대치동","청담동"],"aliases":{},"zones":["A","B","C"]}}'
arecord -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav && \
  curl -s -F audio=@/tmp/t.wav -F language=ko http://127.0.0.1:8000/ai/stt   # 녹음 파일은 시험 후 지운다
```

## 시험
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest && PYTHONPATH=. pytest -q tests
# Whisper 는 가짜, OpenAI 는 httpx 가짜 서버로 대체한다 — 네트워크·GPU·API 키 없이 돈다
```
CI(colcon)는 ROS 패키지만 돌리므로 이 시험은 PR 전에 로컬에서 돌린다.
