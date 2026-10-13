# voss_hmi — 정의석 (@EuiseokJeongNZ)
노드: hmi_bridge (ROS ↔ MQTT, docs/interfaces/mqtt.md), sort_logger (/voss/sort/result → DB sort_log 1행).
- Mosquitto 는 호스트 1883. 웹은 `docker/web/`: Spring Boot(Java 21, REST·SSE·MQTT 클라이언트) + React·TypeScript·Vite + Nginx. 브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다 (ADR-0006).
- DB 는 `docker/db/` PostgreSQL. `sort_log` writer = sort_logger, Spring Boot 는 읽기 전용 계정으로 조회·집계. 집계 기준은 DB 하나.
- HMI 반영 ≤ 1초. 결과 1건 = DB 1행.
- sort_logger 구조: 저장 흐름 `result_store.py`(바로 DB → 실패 시 스풀 → 1·2·5·10·30초 재전송, pytest), 변환·상태·스풀 파일 `log_logic.py`, DB `db_writer.py`(psycopg2), 노드는 ROS 입출력만.
  - 성공 로그 `db_committed box_id=… at=…` 가 G0 commit 증거. 같은 box_id 조회는 `docker/db/README.md` 의 SELECT.
  - `/voss/log/status`: 첫 DB 연결 전 STARTING(→ sort_manager 가 start 거부), 스풀 대기 중 DB_ERROR, 스풀 못 씀·1000행 이상 SPOOL_FULL.
  - DB 가 거부한 행(허용 외 값)은 `<spool>.rejected` 에 따로 둔다 — 스풀을 막지 않게.
  - 실행 전: `sudo mkdir -p /var/lib/voss/spool && sudo chown $USER /var/lib/voss/spool`, `export VOSS_DB_LOGGER_PASSWORD=…`(docker/db/.env 와 같은 값).
  - 실제 DB 시험: `VOSS_TEST_DB_PORT=5432 … pytest test/test_db_writer_postgres.py` (값이나 psycopg2 가 없으면 그 파일만 건너뜀 — 모듈 수준 importorskip 은 다른 시험 수집까지 막아서 쓰지 않는다).
  - **Sprint 2 (S2-T07, BRD v1.5, 남현지)**: `sort_log.slot`(-1 → NULL) 기록, `/voss/pallet/result` → `pallet_log`(싣지 않은 박스 OVERFLOW·EXCLUDED 포함, 별도 스풀 `pallet_log.jsonl`, 로그 접두어 `pallet_log db_committed`), 서비스 `/voss/log/list_placements`(그 세션 PLACED·A/B/C + DONE 여부, 실패 `INVALID`·`SPOOL_PENDING`·`DB_ERROR`). `/voss/log/status` 는 두 저장 흐름 중 나쁜 쪽. 연결 때 스키마를 보고 마이그레이션 전 DB 면 slot 없이 쓰며 경고(`docker/db/migrations/20261012_sprint2_pallet.sql`).
- 결정 필요: MQTT JSON·Mosquitto 위치 (pending #13, 10/08). 웹 스택·DB 종류는 ADR-0006 으로 결정
