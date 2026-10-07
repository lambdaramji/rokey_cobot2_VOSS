# ADR-0007: 호출어 — 에너지 VAD + Whisper 전사 문자열 매칭 (1안), 경량 모델은 2안

- 날짜: 2026-10-07
- 상태: 제안됨 (정의석. PL 승인 후 "승인됨", pending #5 갱신)
- 결정자: 정의석, 승인 남현지 (PL)
- 관련: pending-decisions #5, BRD TR-VOICE-01, SR-SW-10, 이슈 #17, measurements #10, ADR-0006

## 배경
BRD TR-VOICE-01 은 "헬로, 로키"를 감지했을 때만 녹음한다. 시연까지 8일이고 G0(10/10)에는 음성이 필수가 아니다(B 범위). "헬로 로키" 전용 호출어 모델은 공개된 것이 없어 직접 학습해야 한다(openWakeWord 합성 데이터 학습 수 시간 + 실측 튜닝). Porcupine 은 접근 키·라이선스가 필요하고 한국어 발음 문구가 제한된다.

## 결정
**1안(기본): 에너지 VAD 로 말소리 구간만 잘라 Whisper(FastAPI `/ai/stt`)로 전사하고, 전사 문자열 앞부분에서 호출어를 찾는다.**
- VAD: 30 ms 프레임 RMS ≥ 임계값(기본 −40 dBFS, measurements #10 에서 조정), 0.3 s 미만 소리는 버리고, 0.7 s 무음이면 구간 끝, 최대 8 s.
- 호출어: 공백·문장부호를 뺀 앞부분이 "헬로/헬로우/hello + 로키/록키/rokey/rocky" 또는 "로키야" 이면 인정. 뒤에 명령이 붙어 있으면 그 명령만 `/voss/voice/transcript` 로, 호출어만 있으면 **다음 구간(5 s 안)**을 명령으로 본다.
- **정지 키워드("멈춰·정지·스톱·그만")는 호출어 없이 통과**(안전, intent_json.md stop 예외 · #67).
- 구간 오디오는 메모리에만 두고 파일로 저장하지 않는다(CLAUDE.md 규칙 8). 호출어가 없는 구간의 전사문은 버린다 — TR-VOICE-01 의 "녹음"은 "명령으로 받아 처리"로 해석한다.
- **텍스트 폴백**: `mode:=text` 는 터미널 한 줄 = 발화 한 번(호출어 없음). 마이크·sounddevice 가 없으면 자동 전환(R-09).

**2안(필요 시): openWakeWord 로 "hello rocky" 커스텀 모델을 학습해 VAD 앞에 둔다.** 아래 중 하나가 생기면 전환을 검토한다.
- 동시 부하 시험(10/08, MC-028)에서 Whisper 상시 전사가 비전 처리 주기·VRAM 을 침범
- 시연장 소음에서 무관한 대화가 너무 자주 전사돼 STT 지연이 3 s 목표(VT-049)를 깸

## 고려한 대안
- **openWakeWord 커스텀 학습(2안)**: 오탐·CPU 부하가 가장 좋지만 학습·튜닝 시간이 일정 밖. G0 이후 선택.
- **Porcupine**: 품질은 좋으나 접근 키·라이선스, 한국어 문구 제약.
- **푸시투토크(HMI 버튼·키)**: 가장 확실하지만 BRD 의 "호출어" 시나리오가 아님. 텍스트 폴백·HMI 버튼(R-09)으로 대신 남긴다.

## 결과
- voss_voice: `listen_logic.py`(VAD·호출어·WakeGate, pytest) + `voice_listener.py`(sounddevice 마이크 / text 폴백), FastAPI `/ai/stt` 호출(web_api.md).
- 의존성: `python3-numpy`(rosdep), `sounddevice`(pip, 마이크 모드만, 없으면 text 로 동작).
- 실측: measurements #10(1 m 내장 마이크 호출어 인식)에서 호출어 포함/미포함 각 10회, 오탐·미탐 기록. 녹음 20개 전사 ≥ 90%(#17 완료 기준)는 Whisper 크기(pending #6) 결정과 함께.
- 리스크: 무관한 대화도 STT 를 거치므로 GPU 사용이 늘어남 → 10/08 동시 부하 시험에서 확인, 문제면 2안.
