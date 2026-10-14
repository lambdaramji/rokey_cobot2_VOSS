# 음성 표시등 연결 — 인터페이스 변경 제안 (2026-10-13)

상태: **로컬 구현·시험용 제안, 운영 계약 승인 전**. 관련 PR에는 `interface` 라벨을 붙인다.
기존 mqtt.md의 확정 7개 토픽과 ADR-0006/0007을 대체하지 않는다.

## ROS 쪽 (voss_voice 변경 PR 이 새로 추가)

- `voice_listener`의 `/voss/voice/status`: `std_msgs/String` JSON. ROS reliable/volatile, depth 10 (topics.md `/voss/voice/*` 행). main 에는 없던 토픽이며 `voice_feedback.py` 와 함께 들어온다.
- phase는 `WAKE_DETECTED`, `COMMAND_ACCEPTED`, `RECOGNITION_FAILED`, `TIMED_OUT` 네 가지다.
- 필드는 `phase`, `event_id`, `utterance_id`뿐이다. timestamp는 없다. UUID를 시각순으로 비교하지 않는다.
- `COMMAND_ACCEPTED`는 WakeGate를 통과한 **전사 텍스트 수락**이다. intent_parser의 허용 목록 검증, manager 접수, 로봇 동작 완료가 아니다.
- ADR-0007의 호출어 창은 5초다. 웹의 8초 상수는 ROS 시간 초과 이벤트가 오지 않을 때의 별도 UI 대기 한도다. 정상 경로에서는 ROS의 5초 이벤트가 먼저 올 수 있다.
- 실제 SSE 주소는 문서·StreamController·App.tsx 모두 **`GET /api/stream`**이다. `/api/events`를 새로 만들지 않는다.

## 제안 전/후

| 구간 | 변경 전 | 변경 제안 |
|---|---|---|
| ROS | 기존 음성 상태 이벤트 | 타입·필드·QoS 재사용, 중복 발행기 없음 |
| MQTT | 음성 상태 채널 없음 | `voss/voice_status`, bridge → web, **QoS 0 / retain false** |
| 인증/ACL | bridge는 기존 출력 토픽만 write | 격리 시험의 `voice_preview`에 `voss/voice_status` write만 추가; 기존 계정 권한 유지. 운영 bridge 권한 변경 여부는 인터페이스 승인 때 결정 |
| Spring SSE | 기존 이벤트 7종 | 같은 `/api/stream`에 `voice_status` 추가; payload 3개 필드 검증 |
| React | 시험 버튼/상태 reducer | 실제 이벤트, 중복/지난 발화 억제, 연결 종료 시 진행 중 발화 무효화 |

MQTT QoS 0 선택 이유: 이 이벤트는 잠깐의 화면 상태이며, 끊긴 동안 쌓인 호출어를 재접속 후 다시 노랑으로 표시하면 안 된다. **ROS reliable QoS는 그대로** 유지한다. MQTT publish는 연결 중에만 수행하고 QoS 1의 재전송 큐를 사용하지 않는다. 누락된 종료 이벤트는 UI 8초 타임아웃으로 처리한다. 이 QoS 선택은 정의석·남현지의 검토 대상이다.

## payload와 상태

```json
{"phase":"WAKE_DETECTED","event_id":"UUID","utterance_id":"UUID"}
```

ID는 공백만인 값·앞뒤 공백·128자 초과를 거부한다. 추가 필드는 ROS→MQTT 경계에서 제거한다. 원문·오디오는 웹으로 보내지 않는다.

- 실제 호출어 인식: 노랑. 호출어 없는 stop/텍스트 폴백을 통과시키기 위해 가짜 `WAKE_DETECTED`를 만들지 않는다. stop의 transcript 처리는 그대로 유지한다.
- 같은 발화의 `COMMAND_ACCEPTED`: 초록.
- 같은 발화의 `RECOGNITION_FAILED` 또는 `TIMED_OUT`: 빨강 및 안내.
- 호출 후 이벤트가 없으면 `VOICE_COMMAND_TIMEOUT_MS=8000`: 빨강.
- 아이콘 클릭: UI만 초록으로 초기화. 해당 발화의 늦은 결과는 무시한다.
- 초기 초록은 대기 기본값이지 마이크 연결 확인이 아니다.

## 중복·지연·연결 끊김

- bridge는 연결이 끊겼을 때 상태를 보관/발행하지 않는다. 다른 토픽의 전달 방식은 변경하지 않는다.
- Spring은 retained 음성 메시지를 거부하며, 음성 이벤트를 SSE snapshot에 저장하지 않는다. 새 탭·새로고침에 과거 호출어를 재생하지 않는다.
- Spring은 최근 10분/최대 1024개 event ID와 호출어 utterance ID를 기억해 중복을 제거한다.
- UI는 최근 128개 이벤트 ID와 발화 ID를 기억한다. 완료·실패·초기화·새 발화로 교체된 발화의 늦은 결과 및 다시 온 호출어를 무시한다.
- SSE 또는 MQTT가 끊기면 현재 UI 발화를 닫고 초록 기본값으로 초기화한다. 기존 OFFLINE 표시는 유지한다. 연결 복원은 호출어 이벤트가 아니다.
- 원본에 timestamp가 없으므로 **처음 보는 서로 다른 발화의 절대 생성 순서**까지 판정할 수는 없다. 현재 단일 voice_listener→단일 bridge의 순서 보장에 의존한다. 다중 발행기나 장시간 재전송이 필요하면 epoch/sequence/time 필드의 별도 계약이 필요하다.

## 미확정 사항과 담당

| 항목 | 제안/현재 의미 | 확인 담당 |
|---|---|---|
| 토픽, QoS 0, ACL, SSE 이벤트 | 본 문서 제안 | 정의석, 남현지(PL) |
| 초록의 의미 | 전사 수락; 명령 완료로 표시하지 않음 | 정의석, 남현지 |
| 8초 UI vs 5초 호출어 창 | 각각 유지 | 정의석, 남현지 |
| 다중 발행기 순서 필드 | 이번 범위 제외 | 정의석 |
| 실제 음성→웹 전체 검증 | 로컬 실마이크 시험에서 별도 기록 | Web PC 작업자 |

빌드·격리 시험·적용 명령과 증거는 `docs/testing/voice_web_link.md`에 기록한다. Nodes PC 원격 접속 및 실제 장비 실행은 이번 작업에 포함하지 않는다.
