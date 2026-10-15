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

## P0 변경안 — 중복 처리 방식 선택, 실환경 검증 대기

Web PC stop은 LLM·zone_map·TTS·웹 HTTP 대기 전에 ROS `/voss/voice/intent` 경로를 먼저 시도하고 REST도 시도한다. 사용자 선택은 manager에서 **진행 중인** 중복 stop 호출을 한 작업으로 묶는 것이다. 첫 stop이 실패하거나 timeout 나면 다음 stop은 재시도한다. 시간차로 들어온 후속 stop은 gateway의 멱등 서비스를 다시 부를 수 있다. 단순 시간 기반 중복 제거는 실패 후 재시도를 막을 수 있어 쓰지 않는다.

Web PC ROS 발행은 DDS 도메인·네트워크·피어 설정에 따라 Nodes PC에 도착하지 않을 수 있다. 로컬 발행 성공만으로 독립 안전 경로나 물리 정지를 보장하지 않는다. 두 PC의 DDS 실제 도달, Spring/MQTT 장애 시 동작, 중복 stop 및 최종 RobotState는 현장 안전 담당자 통제 아래 측정해야 한다. 브라우저·Spring Boot의 ROS 직접 연결은 제안하지 않으며 ADR-0006의 기존 경계를 유지한다.

음성 정지는 보조 수단이다. 운용 중 안전 정지는 물리 비상정지·HMI 정지 버튼을 사용한다. 음성 정지를 요청했는데 로봇이 멈추지 않으면 작업자는 즉시 물리 비상정지를 누른다. 현장 정지 경로와 지연 측정 전에는 음성 정지를 안전 정지 수단으로 인정하지 않는다.

## 결정 필요

1. Web PC↔Nodes PC DDS가 끊긴 상황에서 음성 정지의 도달 여부와 위 물리 비상정지·HMI 정지 절차의 현장 확인.
2. 최종 로봇 상태와 중복 stop 순서·지연의 현장 측정 결과.
