# VOSS AI 서비스 (FastAPI · Whisper · OpenAI)

ADR-0006 · 계약: `docs/interfaces/web_api.md` (`/ai/stt`, `/ai/intent`), `intent_json.md`.
**음성 ROS 노드 전용**이라 `127.0.0.1:8000` 에만 바인드하고 Nginx 로 노출하지 않는다.

## 실행 (공용 PC, 사람이 실행)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/ai
cp .env.example .env          # OPENAI_API_KEY, OPENAI_MODEL 채우기 (.env 는 커밋 금지)
docker compose up -d --build
curl -s http://127.0.0.1:8000/ai/health
```
- Whisper 가중치는 첫 `/ai/stt` 호출 때 내려받아 `whisper-cache` 볼륨에 둔다(레포·이미지에 넣지 않음).
- 모델 크기 `WHISPER_MODEL` 은 pending #6 — 10/08 비전과 동시 부하 시험(`nvidia-smi`) 후 확정. GPU 가 모자라면 `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE=int8`.

## 단독 확인
```bash
curl -s -X POST http://127.0.0.1:8000/ai/intent -H 'Content-Type: application/json' \
  -d '{"text":"역삼부터 분류해","allowed":{"dongs":["역삼동","대치동","청담동"],"aliases":{},"zones":["A","B","C"]}}'
arecord -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav && \
  curl -s -F audio=@/tmp/t.wav -F language=ko http://127.0.0.1:8000/ai/stt   # 녹음 파일은 시험 후 지운다
```

## 시험
```bash
pip install -r requirements.txt httpx pytest && PYTHONPATH=. pytest -q tests   # Whisper·OpenAI 는 가짜로 대체
```
CI(colcon)는 ROS 패키지만 돌리므로 이 시험은 PR 전에 로컬에서 돌린다.
