# voss_voice — 정의석 (@EuiseokJeongNZ)
노드: voice_listener ("헬로, 로키" 감지 → 녹음 → FastAPI `/stt`(Whisper) → /voss/voice/transcript), intent_parser (FastAPI `/intent`(OpenAI structured output) → 허용 목록 검증 → /voss/voice/intent, 거부 시 /voss/voice/say 로 되묻기), speech_out (/voss/voice/say → TTS).
- AI 서비스: `docker/ai/` FastAPI (Python 3.12, Whisper, OpenAI API). ROS 토픽 계약은 그대로, AI 처리만 HTTP 로 분리 (ADR-0006). FastAPI 응답도 intent_parser 가 다시 검증한다.
- intent JSON 스키마: docs/interfaces/intent_json.md. LLM 출력은 JSON 하나만, 파싱 실패·허용 외 값은 거부.
- `OPENAI_API_KEY` 는 FastAPI 컨테이너의 환경 변수(`.env`, gitignore)에만. 키를 코드·YAML·compose 에 넣지 않는다.
- intent_parser 구조: 판단 로직은 `intent_logic.py`(순수 함수), 처리 흐름은 `transcript_flow.py`(stop 은 잠금 밖에서 즉시, LLM·REST 는 잠금으로 하나씩 — pytest), HTTP 는 `http_client.py`(표준 라이브러리), 노드는 ROS 입출력만. 정답 세트 20건: `test/fixtures/intent_cases.json`.
  - LLM 앞 지름길(#124): 질문 중(ASKING)이면 동 이름만 말한 발화("역삼")와 "~로 보내" 를 LLM 없이 바로 answer 로 보낸다. 질문 중이 아니면 같은 발화에 "지금은 답할 질문이 없습니다" 만 답하고 명령은 내지 않는다. FastAPI `PARSE_ERROR` 는 되묻기, 연결 실패는 "연결할 수 없습니다" 로 나눠 답한다.
  - 실제 API 평가: `test/eval_real_intent.py`(CI 제외, FastAPI·키 필요). LLM 모델은 `gpt-4o`(pending #18).
- 텍스트 입력 폴백(터미널/HMI 입력 → transcript 토픽) 을 처음부터 둔다. 시연장 소음 대비.
- voice_listener(ADR-0007): `mode:=mic`(기본, 에너지 VAD → `/ai/stt` → 호출어 확인) / `mode:=text`(한 줄 = 발화). 로직은 `listen_logic.py`(pytest). 정지 키워드는 호출어 없이 통과. 큐가 차면 오래된 프레임부터 버린다.
  - 마이크 모드 설치(Ubuntu 24.04, PEP 668): `sudo apt install libportaudio2 && pip install --user --break-system-packages sounddevice`. 없으면 text 모드로 자동 전환되므로 시작 로그에서 "mic 모드" 를 꼭 확인한다.
  - text 모드는 stdin 이 필요해 `ros2 launch` 로는 입력을 받지 못한다. 별도 터미널에서 `ros2 run voss_voice voice_listener --ros-args -p mode:=text`. HMI 텍스트 입력(R-09)은 hmi_bridge 경로로 따로 둔다.
- 완료 기준: 녹음 20개 전사 ≥ 90%, 지시 20개 중 19개 정확, 발화→응답 ≤ 3초.
- 결정 필요: Whisper 크기, TTS 엔진 → docs/pending-decisions.md #6·12. 호출어는 ADR-0007(승인)
