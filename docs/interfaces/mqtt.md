# MQTT (hmi_bridge ↔ Spring Boot) — #52 MC-026 합의 반영, 최종 확정은 정의석 #20 (10/08)

브라우저는 MQTT 에 붙지 않는다. **Spring Boot 가 MQTT 클라이언트**이고 브라우저는 HTTP·SSE(`web_api.md`)만 쓴다. hmi_bridge(ROS) 는 MQTT ↔ ROS 변환만 하고 원격 여부를 다시 판단하지 않는다(판정은 Spring Boot, web_api.md).

## 브로커
- Mosquitto, 공용 PC **호스트** 1883 (ADR-0006, #55 MC-026). 위치는 pending #13 에 남은 항목이라 #20 에서 재확인하고, 시연 때 `wlo1` 개방 여부도 #20 에서 정한다.
- `allow_anonymous false`, 비밀번호는 `.env`(gitignore). ACL: `voss/command` 쓰기는 Spring Boot 계정(`web`)만, hmi_bridge 계정(`bridge`)은 `voss/command` 읽기·나머지 `voss/#` 쓰기, 개인 PC 디버그 계정(`debug`)은 `voss/#` 읽기만(web_api.md, #68 리뷰). 상세 설정은 #20.

## 토픽
| 토픽 | 방향 | QoS | retained | JSON |
|---|---|---|---|---|
| `voss/state` | ROS → 웹 | 1 | false | SortState 필드 이름 그대로: `state`, `box_id`, `pending_question`, `track_id`, `ready`, `not_ready`, `session_id`. Spring Boot 가 최신값을 메모리에 두고 SSE 로 넘긴다 |
| `voss/result` | ROS → 웹 | 1 | false | SortResult 필드 이름 그대로. `stamp`·`started_at` 은 ISO 문자열(0 시각은 `null` — DB 규약(#52 MC-020)과 같다, 정의석 #84 확인) |
| `voss/zone_map` | ROS → 웹 | 1 | **true** | `{"version", "entries": [{"dong", "zone", "code", "aliases"}]}` |
| `voss/robot` | ROS → 웹 | 0 | false | `{"connected", "state", "action", "gripper_width_mm", "error_code", "detail", "stamp"}` — RobotState(voss_msgs.md 합의·IDL 반영 대기), `stamp` = header.stamp |
| `voss/command` | 웹 → ROS | 1 | false | `{"command_id", "type", "args", "raw_text", "sent_at"}` — Spring Boot 가 `command_id`(UUID)·`sent_at` 을 붙인다(web_api.md `POST /api/commands`) |
| `voss/command/ack` | ROS → 웹 | 1 | false | `{"command_id", "ok", "message", "acked_at"}` — `/voss/sort/command` 응답(= manager **접수**, 완료 아님) |

- 시각은 모두 ISO-8601 `+09:00` 문자열(공용 PC 시스템 시계). ROS Time 은 hmi_bridge 가 바꾼다.
- `type` 은 Command canonical 명령(voss_msgs.md): `start`·`stop`·`resume`·`priority`·`answer`·`reset_zone`. `args` 객체 → `Command.arg` 문자열 변환표는 #20 에서 확정한다. 변환 결과는 Command.srv 형식을 따른다 — start `""`/`ALL`, priority 동 이름, answer `<box_id>|<동 또는 HOLD>`, reset_zone 구역.
- 로그 상태(`/voss/log/status`)를 웹으로 넘기는 토픽 — 정의석 제안: `voss/log_status`, QoS 1, retained true, `{"status": "STARTING|OK|DB_ERROR|SPOOL_FULL", "stamp": "…"}`(SSE `log_status` 와 같은 형식, Spring Boot 재기동 뒤에도 DB_ERROR 를 바로 표시). #20 에서 확정(SRD v1.0 F-11).

## 명령 처리 규칙 (hmi_bridge)
- 같은 `command_id` 는 10분 동안 기억하고 다시 실행하지 않는다(ack 는 다시 보낸다).
- `sent_at` 이 30초보다 오래된 명령은 실행하지 않고 `ok=false`, `message="EXPIRED"` 로 ack 한다. **단 `stop` 은 예외** — 늦게 와도 실행한다(멈추는 쪽은 막지 않는다는 web_api.md 원칙, 정의석 #84 리뷰).
- `/voss/sort/command` 응답을 그대로 ack 로 보낸다. 실제 완료는 `voss/state`·`voss/result` 로 본다.

## HMI 지연 (≤ 1초, #54 MC-031)
- manager 상태 변경 로그 → 브라우저 DOM(전체 구간)과 hmi_bridge 수신 → DOM(부분 구간)을 둘 다 기록한다.
- 측정 브라우저는 공용 PC 에서 띄워 같은 시스템 시계를 쓴다. 개인 PC 브라우저 수치는 참고로만 쓴다.

## 변경 이력
- 2026-10-05: 초안.
- 2026-10-07: SRD v1.0 정합 (#6). #52 MC-026 합의(정의석 결정)를 옮김 — 6개 토픽·QoS·retained, command/ack JSON, 10분 중복 억제·30초 EXPIRED, ISO 시각, Spring Boot 가 클라이언트. `voss/robot` 필드(#55). 브로커 위치·args 변환표·로그 상태 토픽은 #20. #84 리뷰 반영: stop 은 EXPIRED 예외, result 0 시각 = null 확정, `voss/log_status` 제안.
