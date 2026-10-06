# voss_hmi — 정의석 (@EuiseokJeongNZ)
노드: hmi_bridge (ROS ↔ MQTT, docs/interfaces/mqtt.md), sort_logger (/voss/sort/result → DB sort_log 1행).
- Mosquitto 는 호스트 1883. 웹은 `docker/web/`: Spring Boot(Java 21, REST·SSE·MQTT 클라이언트) + React·TypeScript·Vite + Nginx. 브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다 (ADR-0005).
- DB 는 `docker/db/` PostgreSQL. `sort_log` writer = sort_logger, Spring Boot 는 읽기 전용 계정으로 조회·집계. 집계 기준은 DB 하나.
- HMI 반영 ≤ 1초. 결과 1건 = DB 1행.
- 결정 필요: MQTT JSON (pending #13, 10/08). 웹 스택·DB 종류는 ADR-0005 제안 (승인 대기)
