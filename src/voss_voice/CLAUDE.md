# voss_voice — 정의석 (@EuiseokJeongNZ)
노드: voice_listener ("헬로, 로키" 감지 → Whisper 로컬 STT → /voss/voice/transcript), intent_parser (LangChain + OpenAI → /voss/voice/intent, 허용 목록 검증, 거부 시 /voss/voice/say 로 되묻기), speech_out (/voss/voice/say → TTS).
- intent JSON 스키마: docs/interfaces/intent_json.md. LLM 출력은 JSON 하나만, 파싱 실패·허용 외 값은 거부.
- `OPENAI_API_KEY` 는 환경 변수. 키를 코드·YAML에 넣지 않는다.
- 텍스트 입력 폴백(터미널/HMI 입력 → transcript 토픽) 을 처음부터 둔다. 시연장 소음 대비.
- 완료 기준: 녹음 20개 전사 ≥ 90%, 지시 20개 중 19개 정확, 발화→응답 ≤ 3초.
- 결정 필요: 호출어 엔진, Whisper 크기, TTS 엔진 → docs/pending-decisions.md #5·6·12
