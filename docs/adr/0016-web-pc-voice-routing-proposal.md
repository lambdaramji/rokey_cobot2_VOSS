# ADR-0016 제안: Web PC 음성·텍스트 명령의 전달 경로

- 상태: **제안, PL·로봇 안전 담당자 검토 전** (PR #176)
- 관련: 승인된 ADR-0006, `docs/interfaces/intent_json.md`, `mqtt.md`, `web_api.md`

## 배경

ADR-0006은 브라우저·Spring Boot와 ROS 사이의 경계를 MQTT로 정한다. 시연 구성에서는 마이크·`voice_listener`·`intent_parser`·`speech_out`을 Web PC에서도 실행한다. 이 ROS 노드는 브라우저나 Spring Boot가 아니며, `command_transport=web_api`에서 명령을 로컬 Spring REST로 넘긴다. 기본 `command_transport=ros`는 기존 Nodes PC 운용 경로다.

## 현재 구현

```text
Web PC 마이크/텍스트 → intent_parser → POST /api/commands (Web PC)
  → Spring Boot → MQTT voss/command → Nodes PC hmi_bridge
  → /voss/sort/command → sort_manager → /voss/robot/stop (stop일 때)
```

Web PC 텍스트 입력은 먼저 `voss/voice/text` → Web PC `hmi_bridge` → `/voss/voice/text`를 지나 `intent_parser`에 도착한다. 답변은 반대 방향의 `/voss/voice/text/reply` → `voss/voice/text/reply` → SSE `text_reply`다. `/api/stream`은 구역 지도·질문 상태의 보조 문맥이다. Spring/MQTT가 끊기면 현재 Web PC 음성 stop의 단일 명령 경로도 끊긴다. REST의 `202`는 접수일 뿐 정지 완료가 아니다.

## P0 변경 제안 — 결정 대기

Web PC stop은 LLM·zone_map·TTS·웹 HTTP 대기 전에 ROS `/voss/voice/intent` 경로도 시도한다. 웹 경로와의 중복 `stop`이 Nodes PC에서 두 번 처리될 때의 정책은 PL·로봇 담당자가 결정한다. 현재 sort_manager는 반복 stop마다 `/voss/robot/stop`을 호출하며, gateway stop은 멱등으로 설계되어 있다. 이전 stop이 실패하면 재시도를 허용해야 하므로 단순 시간 기반 중복 제거는 안전 근거가 아니다.

Web PC ROS 발행은 DDS 도메인·네트워크·피어 설정에 따라 Nodes PC에 도착하지 않을 수 있다. 로컬 발행 성공만으로 독립 안전 경로나 물리 정지를 보장하지 않는다. 두 PC의 DDS 실제 도달, Spring/MQTT 장애 시 동작, 중복 stop 및 최종 RobotState는 현장 안전 담당자 통제 아래 측정해야 한다. 브라우저·Spring Boot의 ROS 직접 연결은 제안하지 않으며 ADR-0006의 기존 경계를 유지한다.

## 결정 필요

1. 중복 stop을 그대로 멱등 서비스에 전달할지, 작업 단위로 묶되 실패 재시도를 보존할지.
2. Web PC↔Nodes PC DDS가 끊긴 상황에서 필요한 별도 정지 수단과 운용 절차.
