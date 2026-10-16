# MQTT (hmi_bridge ↔ 웹 HMI) — 정의석 확정 예정 (10/08)

브로커: Mosquitto, 호스트 1883.

| 토픽 | 방향 | JSON (제안) |
|---|---|---|
| voss/state | ROS → 웹 | `{"state":"RUNNING","box_id":"b03","pending_question":""}` |
| voss/result | ROS → 웹 | SortResult 필드 그대로 |
| voss/zone_map | ROS → 웹 (retained) | `{"version":"3","entries":[{"dong":"역삼동","zone":"A"},...]}` |
| voss/command | 웹 → ROS | `{"command":"start","arg":""}` → `/voss/sort/command` |

HMI 반영 지연 목표 ≤ 1초. 웹 스택·실행 위치는 미정.

## 변경 이력
- 2026-10-05: 초안.
