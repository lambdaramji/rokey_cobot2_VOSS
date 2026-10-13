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
cd ~/collaboration/rokey_cobot2_VOSS_2/docker/web/backend
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

1. 테이블·계정은 **`docker/db/`가 이미 만든다** — `init/01_schema.sql`(`sort_log`, `session_plan`), `init/02_roles.sh`(`voss_web`: `sort_log` SELECT만, `session_plan` 읽기·쓰기). 별도 SQL 을 두지 않는다(스키마 이중화 방지). `sort_log` INSERT 는 `sort_logger` 계정뿐입니다.
2. `docker/web/.env.example`를 참고해 `docker/web/.env` 파일을 **로컬에서 직접 만들고** 실제 비밀번호와 JDBC URL을 입력합니다. 이 `.env`는 `.gitignore` 대상입니다. 샘플 파일에는 비밀번호를 넣지 마세요. Spring Boot의 READ/PLAN 접속값만 두며, PostgreSQL 초기화 및 logger 비밀번호는 `docker/db/.env`에 둡니다.
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

### Web PC USB 카메라

Web PC에서 대시보드를 `http://localhost`(개발 서버는 `http://localhost:5173`) 또는 HTTPS로 열고, USB 카메라 패널에서 **카메라 연결**을 눌러 브라우저 권한을 허용합니다. 카메라가 여러 개면 권한 허용 후 목록에서 USB 카메라를 선택하고 **카메라 변경**을 누릅니다. 일반 HTTP LAN IP 주소에서는 브라우저 카메라 접근이 제한됩니다.

영상은 해당 브라우저에서만 표시하며 서버 전송·녹화·마이크 수집을 하지 않습니다. 다른 PC에서 접속하면 그 PC의 카메라를 사용합니다. 연결 종료 또는 페이지 종료 시 카메라 사용을 해제합니다. USB 분리나 권한 거부 시 안내를 확인한 뒤 다시 연결합니다.

### Nodes PC 그리퍼 카메라 + 바운딩 박스

카메라 메뉴에서 USB 카메라와 그리퍼 카메라를 별도로 연결합니다. 그리퍼 미리보기는 기존 `/camera/color/image_raw` (`rgb8`/`bgr8`) 및 `/voss/vision/box` (`BoxTrack`)를 읽는 전용 노드입니다. 검출을 새로 수행하지 않으며 `box_tracker`가 실행돼 있어야 박스가 표시됩니다.

Nodes PC에서 워크스페이스 빌드·환경 로드 후 실행:

```bash
colcon build --packages-select voss_vision
source install/setup.bash
ros2 run voss_vision camera_preview
```

송출 노드는 Nodes PC의 `127.0.0.1:8091`에만 바인드합니다. Web PC의 새 터미널에서 SSH 로컬 포워드를 유지합니다. `NODES_USER`와 `NODES_HOST`는 실제 Nodes PC 계정·주소로 바꿉니다(저장된 시험 문서의 IP는 현재 주소인지 확인 필요).

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8091:127.0.0.1:8091 NODES_USER@NODES_HOST
```

변경된 Web 프런트/Nginx를 재빌드·재시작합니다. 개발 Vite 서버도 설정 변경 후 재시작합니다. 브라우저의 **카메라 → 그리퍼 카메라 → 영상 연결**을 누르면 `/camera/gripper/frame.jpg`를 통해 최대 약 5 fps로 표시합니다. 이미지·박스는 촬영 timestamp가 정확히 일치할 때만 합성하고, 검출 대기를 위해 약 0.2초 버퍼링합니다. 검출이 늦거나 없으면 박스 없이 영상을 표시합니다. 1초보다 오래된 수신 영상은 503으로 거부하며, 브라우저는 실패 시 이전 영상을 숨기고 재시도합니다. 미리보기는 최대 30프레임을 메모리에 보관하며 녹화하지 않습니다.

토픽이 다르면 `--ros-args -p image_topic:=... -p box_topic:=...`로 지정합니다. 로봇 제어·기존 MQTT/DB 경로는 그대로 사용합니다. 실제 USB/ROS 카메라와 두 PC 간 연결은 현장에서 확인해야 합니다.

### 실제 음성 인식과 마이크 표시등

`voice_listener` 및 `hmi_bridge`의 변경과 MQTT ACL, Spring 백엔드 변경을 함께 반영해야 한다. 호출어가 인식되면 노랑, 뒤의 전사 텍스트가 수락되면 초록, 대기 시간 초과/전사 실패는 빨강이다. 초록은 로봇 동작 완료를 의미하지 않는다. 집 PC에서 명령을 발행하지 않고 실제 마이크로 시험하는 실행기는 `scripts/integration/voice_logo_local.py`다. 표시 전용 모드는 `voice_preview` 계정을 사용하며 일반 bridge 계정은 그대로다. 전체 계약은 [voice_status.md](../../docs/interfaces/voice_status.md), 빌드·적용·구간별 확인은 [시험 및 실행 안내](../../docs/testing/voice_web_link.md)를 참고한다.
