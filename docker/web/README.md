# T13 #22 — VOSS Web HMI (React + Spring Boot + MQTT + PostgreSQL)

기준: `docs/interfaces/web_api.md` (#68), `docs/interfaces/mqtt.md` (#20), ADR-0006.
기존 백엔드(`MqttStateMessageHandler`, `SortStateStore`, JUnit)를 유지하면서 기능을 추가한 **개발 통합본**입니다. 실제 로봇/브로커/DB 연동 완료를 주장하지 않습니다.

## 구현 범위

- React/TypeScript/Vite: 운전(시작·정지·재개), 동 우선·HOLD 답변·구역 초기화, 투입 예정 수량, 최신 상태·OCR·로봇 상태·구역별 집계·보류·이력, CSV.
- Spring Boot: `GET /api/stream` SSE(상태·결과·zone_map·robot·command_ack·log_status·link), `POST /api/commands`, `GET /api/stats`, `GET /api/sessions/current`, `PUT /api/sessions/current/plan`, `GET /api/results`, `GET /api/export.csv`.
- MQTT: `voss/state`, `voss/result`, `voss/zone_map`, `voss/robot`, `voss/command/ack`, `voss/log_status` 구독; `voss/command` 발행(총 7개 토픽). QoS 1/1/1/0/1/1, 명령 발행 QoS 1; retained는 브로커 토픽 계약에 따름.
- SQL: `sort_log`는 조회 전용 연결만 사용하고, 투입 수량은 별도 `session_plan` 테이블에서 관리.
- 원격 접근: `stop` 이외 명령은 Nginx가 덮어쓴 `X-Real-IP`가 localhost일 때만 허용. `X-Forwarded-For`는 무시.

## 사용자 PC에서 테스트

```bash
cd ~/collaboration/rokey_cobot2_VOSS-t13/docker/web/backend
./gradlew clean test bootJar
cd ../frontend
npm install
npm run build
```

**주의:** JUnit 성공과 운영 환경 MQTT 인증·DB 테이블·브라우저 렌더링·실물 로봇 동작 성공은 별개입니다. 실제 기기 제어는 현장 안전 담당자가 수행하세요.

## 개발 실행

```bash
# 터미널 1: Spring Boot (기본 MQTT 비활성화)
cd docker/web/backend
./gradlew bootRun

# 터미널 2: React 개발 서버
cd docker/web/frontend
npm install
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. Vite는 `/api`를 localhost:8080으로 전달합니다. 실제 MQTT/DB 환경 변수를 설정하지 않았다면 연결 DOWN·DB_ERROR 표시가 정상이며, 가짜 데이터를 채우지 않습니다.

## 공용 PC 배포

1. PostgreSQL의 **별도 웹 계획 테이블** 생성: `sql/session_plan.sql`. 전용 계획 계정은 `session_plan`만 SELECT/INSERT/UPDATE(필요 시 DELETE)할 수 있게 권한을 설정하고, **조회 계정은 `sort_log` SELECT만** 허용합니다. `sort_log` INSERT 권한은 `sort_logger`에만 줍니다.
2. `docker/web/.env.example`를 참고해 `docker/web/.env` 파일을 **로컬에서 직접 만들고** 실제 비밀번호와 JDBC URL을 입력합니다. 이 `.env`는 `.gitignore` 대상입니다. 샘플 파일에는 비밀번호를 넣지 마세요.
3. Mosquitto의 `web` 계정은 `voss/command` 쓰기 및 `voss/#` 읽기 ACL이 필요합니다. 실제 구독 테스트 때 `VOSS_MQTT_ENABLED=true`로 변경합니다.
4. Docker Compose 호스트 네트워크 사용이 공용 PC/ufw/포트 점유 정책과 맞는지 현장에서 확인합니다. 80 Nginx, 8080 Spring localhost, 1883 Mosquitto, 5432 PostgreSQL localhost입니다.

```bash
cd docker/web
docker compose up --build -d
docker compose logs --tail=100 backend frontend
```

`/ai`는 Nginx에서 프록시하지 않습니다. FastAPI는 여전히 음성 ROS 노드의 localhost:8000 접속 전용입니다.

## 검증표 (테스트 수행 후 채우기)

| 요구사항 | 시험 조건 | 횟수 | 증거 | 판정 |
|---|---|---:|---|---|
| MQTT 토픽·QoS | JUnit 설정 검사 | 미검증 | 사용자 환경 `./gradlew test` | 확인 필요 |
| 원격 안전 제한 | X-Real-IP 원격 start 403·stop 허용 | 미검증 | CommandControllerTest | 확인 필요 |
| 상태 시간초과 | 메시지 수신 없이 3초 후 UNKNOWN | 미검증 | SortStateStoreTest 및 브라우저 | 확인 필요 |
| REST·DB | 실제 sort_log 1건 조회 및 summary·CSV | 미검증 | DB SQL/응답 증거 | 확인 필요 |
| MQTT 수신·명령 | broker ↔ hmi_bridge 왕복·ack | 미검증 | broker/ROS 로그 | 확인 필요 |
| HMI 반영 ≤1초 | manager 상태변경 → 브라우저 DOM, bridge 수신 → DOM | 미검증 | 동일 PC의 시각·로그 | 실측 필요 |

## 유의사항

- `voss/command`의 HTTP 202는 **브로커 전달**을 의미하며 manager의 접수/로봇 동작 완료가 아닙니다. `command_ack`와 `state`/`result`로 따로 표시합니다.
- 현재 세션은 `SortState.session_id`만 기준으로 하며 첫 `start` 전 `""`입니다. 암묵적인 결과·통계·CSV 조회에는 `404 NO_SESSION`을 반환합니다. 현재 세션 요약은 `""`·planned·0 건으로 반환합니다(DB 서비스가 접속 가능한 경우).
- `session_plan`의 `next` 예정 수량은 새 세션이 처음 조회될 때 실제 session_id로 옮깁니다. 첫 상태 수신 직후가 아니라 첫 DB 조회 시점에 반영되는 구현이므로 팀 계약의 엄격한 트리거와 차이가 있습니다. 실제 통합시험에서 확인 후 필요하면 인터페이스 변경 없이 처리 시점을 맞추세요.
- 실제 DB 환경 변수, 보안 계정과 네트워크는 파일에 포함돼 있지 않습니다. 테스트 완료 전 시연 준비 완료라고 판단하지 마세요.
