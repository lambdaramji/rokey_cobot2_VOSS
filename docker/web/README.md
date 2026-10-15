# T13 #22 — VOSS Web HMI (React + Spring Boot + MQTT + PostgreSQL)

기준: `docs/interfaces/web_api.md` (#68), `docs/interfaces/mqtt.md` (#20), ADR-0006.
기존 백엔드(`MqttStateMessageHandler`, `SortStateStore`, JUnit)를 유지하면서 기능을 추가한 **개발 통합본**입니다. 실제 로봇/브로커/DB 연동 완료를 주장하지 않습니다.

## 구현 범위

- React/TypeScript/Vite: 운전(시작·정지·재개), 동 우선·HOLD 답변·구역 초기화, 투입 예정 수량, 최신 상태·OCR·로봇 상태·구역별 집계·보류·이력, CSV.
- Spring Boot: `GET /api/stream` SSE(state·result·zone_map·robot·command_ack·log_status·pallet_state·link, 실시간 전용 voice_status·box_track·robot_pose·robot_joints·box_motion), `POST /api/commands`, `GET /api/stats`, `GET /api/sessions/current`, `PUT /api/sessions/current/plan`, `GET /api/results`, `GET /api/export.csv`.
- MQTT: 구독 12개 `voss/state`, `voss/result`, `voss/zone_map`, `voss/robot`, `voss/command/ack`, `voss/log_status`, `voss/pallet/state`, `voss/voice_status`, `voss/box_track`, `voss/robot_pose`, `voss/box_motion`, `voss/robot_joints`(QoS 1/1/1/0/1/1/1/0/0/0/1/0); `voss/command` 발행(QoS 1). 접속 스냅샷은 state·zone_map·robot·log_status·pallet_state 만 — 위치·음성 이벤트는 재생하지 않는다. retained는 브로커 토픽 계약에 따름.
- SQL: `sort_log`는 조회 전용 연결만 사용하고, 투입 수량은 별도 `session_plan` 테이블에서 관리.
- 원격 접근: `stop` 이외 명령은 Nginx가 덮어쓴 `X-Real-IP`가 localhost일 때만 허용. `X-Forwarded-For`는 무시. **단, SSH가 127.0.0.1:8080에 직접 연결되면 Nginx를 거치지 않으므로 이 헤더만으로 원격 접속자를 인증할 수 없다.**

## Sprint 2 S2-T08 — 팔레트 패널 (BRD v1.5 TR-PAL-10, 남현지)

- 화면: `src/PalletPanel.tsx`(04 / PALLETIZING). 경로 1~3곳 선택 → `palletize`, "팔레트 비움" → `reset_zone PALLET`(둘 다 공용 PC 로컬만). 3D 팔레트 4열×2줄×2층(트럭 머리 왼쪽·문 오른쪽, 동 색, 계획=옅게·옮기는 중=깜빡임·적재=진하게·실패=붉게), 위에서 본 칸 표(BRD 10.4 표와 같은 행 순서), 구역별 실을 수·초과·경로 제외, "배송 물량 남음" 경고, 진행률 "n개 중 m개".
- 3D 는 SVG 사선 투영(`src/pallet.ts`, 새 의존성 없음 — three.js·WebGL 없이 결정적이라 시험할 수 있다). 박스 비율은 실제 46×31×27 mm. 앞줄 = 1줄은 임시(결정 D6·교시 S2-T02 뒤 `FRONT_LANE` 만 바꾼다).
- 백엔드: `voss/pallet/state` 구독(QoS 1) → SSE `pallet_state`(접속 스냅샷 포함), `palletize` route 검사, `reset_zone PALLET`, SortState `PALLETIZING` 수용(빠지면 팔레타이징 중 3초 뒤 UNKNOWN).
- 시험: `npm test`(Node 22 내장 `node --test`, `test/fixtures/pallet_s1.json` = 실제 pallet_fsm 이 만든 S1 + slot 4 실패·#37 당겨 놓기 PalletState 열 — 손으로 고치지 않는다), `./gradlew test`.
- 공용 PC 재생·반영 ≤ 1초: `scripts/integration/README.md` "S2-T08".
- 로컬 표시 시험: `http://localhost/?palletReplay=1`에서 16칸을 순서대로 재생한다. 이 모드는 시험 재생 표시와 함께 팔레트 조작을 끈다.

## 공용 PC에서 테스트

레포 루트에서 다음 명령을 실행한다.

```bash
cd docker/web/backend
./gradlew clean test bootJar
cd ../frontend
npm ci
npm test
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
npm ci
npm run dev
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. Vite는 `/api`를 localhost:8080으로 전달합니다. 실제 MQTT/DB 환경 변수를 설정하지 않았다면 연결 DOWN·DB_ERROR 표시가 정상이며, 가짜 데이터를 채우지 않습니다.

**운전 안전 계약:** 공용 PC 로컬 HMI 요청은 start/resume/priority/answer/reset_zone을 허용하고, 원격에서는 stop만 허용한다 (`web_api.md` #68). 이전 임시 `VOSS_NONSTOP_COMMANDS_ENABLED`와 `VOSS_OPERATOR_IP`는 정식 계약에 없으므로 이 PR에서 사용하지 않는다. Nginx는 `X-Real-IP`를 덮어쓰고 `X-Forwarded-For`를 무시한다. Spring 8080 포트로 직접 접속하는 SSH 터널은 Nginx를 우회하므로 **실로봇 운전 중 사용 금지**이며, 다중 PC 예외는 옛 레포 #155/ADR 승인과 별도 인증 전에 허용하지 않는다.

## 공용 PC 배포

1. 테이블·계정은 **`docker/db/`가 이미 만든다** — `init/01_schema.sql`(`sort_log`, `session_plan`), `init/02_roles.sh`(`voss_web`: `sort_log` SELECT만, `session_plan` 읽기·쓰기). 별도 SQL 을 두지 않는다(스키마 이중화 방지). `sort_log` INSERT 는 `sort_logger` 계정뿐입니다.
2. `docker/web/.env.example`를 참고해 `docker/web/.env` 파일을 **로컬에서 직접 만들고** 실제 비밀번호와 JDBC URL을 입력합니다. 이 `.env`는 `.gitignore` 대상입니다. 샘플 파일에는 비밀번호를 넣지 마세요. Spring Boot의 READ/PLAN 접속값만 두며, PostgreSQL 초기화 및 logger 비밀번호는 `docker/db/.env`에 둡니다.
3. Mosquitto의 `web` 계정은 `voss/command` 쓰기 및 `voss/#` 읽기 ACL이 필요합니다. 실제 구독 테스트 때 `VOSS_MQTT_ENABLED=true`로 변경합니다.
4. Docker Compose 호스트 네트워크 사용이 공용 PC/ufw/포트 점유 정책과 맞는지 현장에서 확인합니다. 80 Nginx, 8080 Spring localhost, 1883 **공용 PC 호스트 Mosquitto(계약 mqtt.md)**, 5432 PostgreSQL localhost입니다.

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
- 두 PC 비구동 시험용 Mosquitto 컨테이너·ACL 설치 절차는 **옛 레포 #155 의 제안**이었고, 지금은 `docker/mqtt/`(T11)에 있다. 공식 시연은 mqtt.md에 따라 공용 PC 호스트에서 운영한다. 비밀번호는 커밋하지 않는다.
- 실제 DB 환경 변수, 보안 계정과 네트워크는 파일에 포함돼 있지 않습니다. 테스트 완료 전 시연 준비 완료라고 판단하지 마세요.

### Workspace 위치 표시 주의

- 구역 좌표(`src/lib/workspaceGeometry.ts`)는 10/12 voss_config 스냅샷(`CONFIG_SHA_SHORT`)의 복사본이다(플랜지 좌표, TCP 와 xy 1~3 mm 차이 — 표시엔 충분). zone_map 에는 좌표가 없어서 구역을 다시 교시하면 화면이 **조용히** 어긋나므로, voss_config 의 zones 를 바꾸면 이 파일과 SHA 를 같이 고친다.
- 운반 박스 표시(`VITE_VOSS_TCP_BOX_TOP_OFFSET_MM`, 프론트 빌드 시 환경 변수)는 **TCP 좌표계** 값이다. 그리퍼가 수직 아래 자세(ry ≈ 180°)라 TCP z 축은 base 의 아래를 향한다 → 박스 윗면이 TCP 보다 base 기준 17~19 mm 위면 TCP 좌표로는 `0,0,-17` 이다(base 기준 `+17` 을 넣으면 박스가 벨트 아래에 그려진다). servo 참고값(박병후 #37·#39 리뷰): z 17~19, 닫힘축 ≈ 0, 벨트 방향 0 ± 3 mm. 실측 검증 전에는 `VITE_VOSS_BOX_OFFSET_VERIFIED=true` 를 쓰지 않는다(기본 빌드는 운반 박스 미표시).

### USB 카메라 (카메라 메뉴)

대시보드를 `http://localhost`(개발 서버는 `http://localhost:5173`) 또는 HTTPS로 열고, USB 카메라 패널에서 **카메라 연결**을 눌러 브라우저 권한을 허용합니다. 카메라가 여러 개면 권한 허용 후 목록에서 USB 카메라를 선택하고 **카메라 변경**을 누릅니다. 일반 HTTP LAN IP 주소에서는 브라우저 카메라 접근이 제한됩니다.

영상은 해당 브라우저에서만 표시하며 서버 전송·녹화·마이크 수집을 하지 않습니다. 다른 PC에서 접속하면 그 PC의 카메라를 사용합니다. 연결 종료 또는 페이지 종료 시 카메라 사용을 해제합니다.

### 그리퍼 카메라 (카메라 메뉴)

Nodes PC에서 `voss_vision`을 빌드하고 송출 노드를 실행합니다. 기본 입력은 `/camera/color/image_raw`(rgb8 또는 bgr8)와 `/voss/vision/box`이며, 같은 촬영 시각의 박스 검출 결과를 영상에 표시합니다.

```bash
colcon build --packages-up-to voss_vision
source install/setup.bash
ros2 run voss_vision camera_preview
```

공용 PC 한 대에서 시연할 때는 그 PC에서 위 명령을 실행한 뒤 `http://localhost` → **카메라** → **그리퍼 카메라 · 영상 연결**로 확인합니다. 영상의 `T3` 같은 표시는 비전 트랙 번호이며 분류 이력의 BOX 번호와 다릅니다. 옆의 `92%` 같은 값은 그 박스 송장의 채움(윤곽 면적 ÷ 회전 사각형 면적, box_tracker 와 같은 `seg` 판정, `fill_min` 80% 이상 통과)이며 인식 신뢰도가 아닙니다. 같은 프레임에서 판정을 통과한 송장이 없으면 `-%` 입니다. 채움 % 는 송출 노드가 프레임을 보낼 때마다 판정을 한 번 더 돌립니다(1920×1080 기준 약 80 ms, 탭 하나당 약 5 Hz). 끄려면 `ros2 run voss_vision camera_preview --ros-args -p fill_percent:=false`. 판정 값은 `voss_vision` 설치 경로의 `config/box_tracker.yaml` 을 읽으며 다른 파일은 `-p seg_params_file:=<경로>` 로 지정합니다. 송출 노드의 `host` 기본값 `127.0.0.1`을 유지하고 `host:=0.0.0.0`으로 바꾸지 마세요. 그러면 카메라 영상이 Wi-Fi 쪽에 열립니다.

송출 노드는 최근 원본 프레임 최대 10장만 보관하고 JPEG 전송 전에 최대 960×540으로 줄입니다. box_tracker·OCR·belt_servo와 함께 실행할 때의 실제 부하는 아직 측정하지 않았으므로 게이트 측정 중에는 송출 노드를 실행하지 않습니다.

Web PC의 개발 서버(`npm run dev`)는 `/camera/gripper/frame.jpg`를 로컬 `127.0.0.1:8091`로 전달합니다. 따라서 개발 서버를 실행하는 PC에서 송출 노드의 `127.0.0.1:8091`에 닿아야 합니다. 카메라 메뉴의 **그리퍼 카메라 → 영상 연결**을 누르면 프레임을 요청합니다. 송출 노드가 실행되지 않았거나 입력 영상이 없으면 OFFLINE으로 표시됩니다. 배포 Nginx의 이 경로는 로컬 접속만 허용합니다.

### 실제 음성 인식과 마이크 표시등

`voice_listener` 및 `hmi_bridge`의 변경과 MQTT ACL, Spring 백엔드 변경을 함께 반영해야 한다. 호출어가 인식되면 노랑, 뒤의 전사 텍스트가 수락되면 초록, 대기 시간 초과/전사 실패는 빨강이다. 초록은 로봇 동작 완료를 의미하지 않는다. 표시 전용 시험 모드(`hmi_bridge voice_status_only:=true`, `voice_listener publish_transcript:=false`)는 `voice_preview` MQTT 계정을 쓰며 일반 bridge 계정은 그대로다(docker/mqtt/README.md). Web PC 에서 쓰던 실행기 `voice_logo_local.py` 는 레포에 없다. 전체 계약은 [voice_status.md](../../docs/interfaces/voice_status.md), 빌드·적용·구간별 확인은 [시험 및 실행 안내](../../docs/testing/voice_web_link.md)를 참고한다.
