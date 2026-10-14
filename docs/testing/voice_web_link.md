# 실제 음성 상태 → 웹 마이크 연결: 구현·시험·적용 안내

작성: 2026-10-13. 범위: 현재 Web PC의 로컬 소스. Nodes PC SSH·실제 로봇·벨트·그리퍼 실행 없음.
계약 변경은 [음성 상태 제안](../interfaces/voice_status.md)이며 운영 확정 전이다. 관련 PR 라벨: `interface`.

> **레포 반영 범위(10/14 리뷰):** 아래 파일 중 `scripts/integration/voice_logo_local.py`, `scripts/integration/test_voice_web_e2e.py`, `docs/testing/voice_web_link_results.txt`, `docs/testing/voice_web_link_e2e.txt` 는 Web PC 로컬에만 있고 이 레포(PR #37~#42)에는 없다. 격리 E2E·실마이크 실행기 절차는 그 파일이 올라온 뒤에 재현할 수 있다. 브리지·웹 쪽 파일은 PR #38(voss_hmi·docker/mqtt)·#39(docker/web)에 있다.

## 구현 결과

기존 `voice_listener` → `/voss/voice/status` → **기존 hmi_bridge** → Mosquitto → **기존 Spring MQTT 구독자** → **기존 `/api/stream` SSE** → App → VossSortingWorkspace → voiceIndicator 경로를 사용한다.
새 웹소켓 서버·별도 상시 MQTT 클라이언트는 만들지 않는다. 격리 시험에만
`voice_preview` MQTT 계정을 사용한다.

`COMMAND_ACCEPTED`는 전사 텍스트가 수락됐다는 의미다. intent 해석 성공/manager 접수/로봇 완료로 의미를 넓히지 않는다.
정지 우회 처리·허용 목록·Intent 메시지·DB 경로·웹 명령의 로컬 접근 제한을 변경하지 않는다.

## 변경 파일

| 파일 | 핵심 변경 |
|---|---|
| `docs/interfaces/voice_status.md`, `mqtt.md`, `web_api.md` | 변경 전/후, 제안 QoS·ACL·SSE 이름, 5초/8초 의미와 검토 담당 |
| `src/voss_voice/voss_voice/voice_feedback.py` | 기존 이벤트 재사용. 호출어 없는 stop/텍스트 입력에 가짜 WAKE 이벤트를 만들지 않음 |
| `src/voss_hmi/voss_hmi/voice_status.py` | JSON 검증·필드 최소화·연결 중 QoS 0 전달 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py` | 기존 클라이언트로 음성 상태 전달, 격리 시험용 `voice_status_only` |
| `docker/mqtt/acl` | 기존 계정 ACL을 유지하고 `voice_preview`의 음성 상태 토픽 write만 추가 |
| `docker/web/backend/.../mqtt/MqttSubscriberConfig.java` | 기존 구독에 음성 토픽 추가, retained 메타데이터 전달 |
| `docker/web/backend/.../mqtt/MqttEventRouter.java`, `VoiceStatusFilter.java` | 검증·retained 거부·최근 중복 제거·기존 SSE로 전달 |
| `docker/web/frontend/src/App.tsx` | SSE 음성 이벤트 전달, 연속 WAKE/완료를 순서대로 반영, 연결 종료 시 진행 상태 무효화 |
| `docker/web/frontend/src/lib/voiceIndicator.ts` | 최근 ID 이력으로 중복·지난 발화 결과·재호출어 억제 |
| `docker/web/frontend/src/components/VossSortingWorkspace.tsx` | 연결 종료 시 UI 초기화; 디자인·로봇 애니메이션은 변경하지 않음 |
| Python/Java/프런트 관련 test 파일 | 상태 전이, 잘못된 값, 중복, retained, SSE 회귀 검증 |
| `scripts/integration/voice_logo_local.py` | 기존 listener+bridge 코드의 표시 전용 모드로 실제 마이크 시험, 전용 인증 및 명령 경로 비활성화 |
| `scripts/integration/test_voice_web_e2e.py`, `frontend/test/voiceDom.mjs`, `vite.voice-test.config.mjs` | 임시 인증 브로커·Spring·실제 ROS bridge·Chrome DOM 격리 통합시험 |

이전 대화의 USB/그리퍼 카메라, 레이아웃, 다른 작업자의 파일 변경은 이번 음성 연결 변경 범위와 분리한다.

## 자동 검증 결과

- Python: **198 통과, 6 건너뜀**. 6개는 `VOSS_TEST_DB_PORT` 미설정으로 생략한 실제 PostgreSQL 시험이며 이번 변경은 DB를 수정하지 않는다.
- Java: **53 통과**, `test bootJar` 성공.
- 프런트 reducer: **12 통과**. `npm run build` 성공.
- ROS/인증 MQTT/Spring SSE/실제 Chrome DOM: **12개 검증 통과**.
- `colcon build --symlink-install --packages-up-to voss_voice voss_hmi`: **3개 패키지 성공**.


최종 실행 결과는 아래 표와 `voice_web_link_results.txt` 및 원본 `voice_web_link_e2e.txt`에 기록한다. 증거의 순서는 **요구사항 → 시험 조건 → 횟수 → 증거 → 판정**이다.

| 요구사항 | 시험 조건 | 횟수 | 증거 | 판정 |
|---|---|---:|---|---|
| 호출어 → 노랑 | ROS 179에서 String 발행, 실제 bridge/MQTT/Spring/Chrome 사용 | 최종 통합시험 1회 | `PASS ROS 호출어 → MQTT → SSE → DOM 노랑` | 통과 |
| 전사 수락 → 초록 | 같은 utterance ID의 COMMAND_ACCEPTED | 1회 | `PASS 전사 수락 → 초록` | 통과 |
| 실패 → 빨강·안내 | RECOGNITION_FAILED 전달 및 DOM 문구 검사 | 1회 | `PASS 실패 → 빨강 + 안내` | 통과 |
| 호출 후 결과 없음 → 8초 빨강 | ROS 종료 이벤트 없이 6.5초 노랑 유지, 이후 타임아웃 검사 | 1회 | `PASS 결과 미수신 8초 → 빨강` | 통과 |
| 클릭 → 초록·안내 제거 | 실제 DOM click | 1회 | `PASS 클릭 → 초록 + 안내 제거` | 통과 |
| 지난 발화·중복 무시 | 이전 결과·다시 온 WAKE·같은 event ID 순차 주입 | 1회 + reducer 테스트 | `PASS 이전 발화 결과·호출어·중복 무시` | 통과 |
| 새로고침에 과거 호출어 재생 없음 | 노랑 중 Page.reload | 1회 | `PASS 새로고침 시 지난 호출어 재생 없음` | 통과 |
| SSE 끊김·복원 시 이전 발화 무효화 | 격리 Vite에서 실제 SSE 소켓 종료 후 EventSource 자동 재연결 | 최종 1회 | `PASS SSE 연결 끊김·복원 시 이전 발화 초기화` | 통과 |
| retained 음성 이벤트 거부 | 임시 브로커에 retained 저장, 임시 Spring 재시작·MQTT 재구독·새 SSE 연결 | 최종 1회 | `PASS retained 호출어 거부` | 통과 |
| MQTT 끊김·재연결 | 임시 브로커만 종료/재기동, 끊긴 사이 ROS 발행 | 1회 | `PASS 브로커 끊김·재연결에 오프라인 호출어 재생 없음` | 통과 |
| 기존 웹 상태 유지 | 기존 state JSON의 PAUSED 수신/DOM 검사 | 1회 + Java 회귀 시험 | `PASS 기존 state SSE 표시 유지` | 통과 |
| 로봇 제어 변경 없음 | voice_status_only, publish_transcript=false, ROS 179/LOCALHOST, 제어 코드 비교 | 1회 검토 | 정지/intent_parser/CommandController/DB 코드 변경 없음 | 통과 |

시험 중 임시 Spring의 기본 graceful shutdown이 열린 SSE 종료를 기다려 재시작 시험이 한 차례 실패했다. **시험 프로세스에만** `--server.shutdown=immediate`를 지정해 재검증했다. 운영 종료 설정은 변경하지 않았다. 이후 Vite 프록시가 상위 Spring 종료 때 기존 SSE를 즉시 닫지 않는 조건을 발견해, 실제 SSE 소켓 단절 시험과 새 SSE 연결의 retained 거부 시험을 분리했다. 단절 통지가 없는 무응답 상태에서는 기존 UI 8초 타임아웃이 적용된다.

실제 마이크로 사람이 발화한 전체 경로는 이번 자동시험에 포함하지 않는다. 사용자 제공 증거로 실제 발화→ROS WAKE_DETECTED/COMMAND_ACCEPTED는 확인됐지만, 실제 발화→웹 전체는 아래 절차로 별도 판정해야 한다.

### 2026-10-13 전용 계정 재검증

- 기존 브로커의 `mosquitto.conf`·ACL·비밀번호 파일을
  `docker/mqtt/secrets/backup-20261013T062651/`에 백업했다. 기존 3개 계정의
  해시와 ACL은 보존하고 `voice_preview` 한 계정 및 음성 토픽 write 한 규칙만
  추가한 뒤 HUP으로 다시 읽혔다. 암호는 Git 제외 파일
  `docker/mqtt/secrets/preview.env`(600)에만 보관한다.
- 같은 Mosquitto 2.1.2의 격리 브로커에서 음성 토픽 발행 허용,
  `voss/state`·`voss/command` 발행 거부, 읽기 전달 부재를 확인했다.
- 활성 브로커 + ROS 179/LOCALHOST + `voice_status_only` + 현행 소스의
  별도 Spring(루프백 18080) 조합에서 `WAKE_DETECTED`, `COMMAND_ACCEPTED`가
  모두 `GET /api/stream`의 `voice_status` SSE로 도착했다.
- 임시 브로커·Spring·Chrome DOM 격리 E2E 12개 항목이 통과했다.
- 현재 실행 중인 웹 백엔드 이미지는 음성 상태 구독 코드가 없는 이전 버전이라
  활성 8080 SSE에는 이벤트가 오지 않았다. 활성 웹 표시 적용에는 백엔드·프런트
  새 이미지 배포와 인터페이스 승인이 남아 있다. 실제 마이크 발화는 이번
  재검증에 포함하지 않았다. 로봇 명령은 발행하지 않았다.

## 재현 가능한 로컬 빌드·자동시험

저장소 루트에서:

```bash
cd <레포 루트>
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-up-to voss_voice voss_hmi
source install/setup.bash
PYTHONPATH=src/voss_voice:src/voss_hmi python3 -m pytest --import-mode=importlib src/voss_voice/test src/voss_hmi/test -q
node --experimental-strip-types --test --test-isolation=none docker/web/frontend/test/voiceIndicator.test.mjs
npm run build --prefix docker/web/frontend
```

Node 24 기준 reducer 시험이다. Java 빌드·시험:

```bash
cd <레포 루트>/docker/web/backend
./gradlew test bootJar --no-daemon
```

격리 E2E(기존 운영 서비스 변경 없음, `mosquitto`, `mosquitto_passwd`, Java 21, Chrome 필요):

```bash
cd <레포 루트>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 scripts/integration/test_voice_web_e2e.py
```

매번 임시 디렉터리·인증 파일·동적 loopback 포트를 생성하며 종료 시 정리한다. 상태 이벤트만 발행하며 실마이크나 장비를 열지 않는다.

## Web PC 브로커 적용 및 실제 마이크 시험

브로커 설정·ACL·비밀번호 파일은 먼저 Git 제외 영역에 백업한다. 기존 계정과
그 권한은 유지하고 `voice_preview` 계정 및 `voss/voice_status` write ACL만
추가한다. 비밀번호는 대화형 입력 또는 권한 600의 로컬 비밀 파일로만 다룬다.
적용 후 새 계정의 해당 토픽 발행 성공과 다른 토픽 발행·구독 거부를 확인한다.

백엔드·프런트를 새 소스로 빌드하고 반영할 때 SSE는 잠시 끊긴 뒤 자동 복구된다.

```bash
docker compose -f docker/web/compose.yaml build backend frontend
docker compose -f docker/web/compose.yaml up -d --no-deps backend frontend
```

실제 마이크 시험용 터미널에서 환경과 Git 제외 전용 계정 파일을 로드한다.
암호를 커맨드 인수나 채팅에 넣지 않는다.

```bash
cd <레포 루트>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=179
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
unset ROS_STATIC_PEERS
source docker/mqtt/secrets/preview.env
python3 scripts/integration/voice_logo_local.py
```

이 실행기는 기존 voice_listener와 hmi_bridge만 사용하며 `publish_transcript=false`, `voice_status_only=true`를 지정한다. 시험 모드의 MQTT client ID는 `voss-hmi-voice-preview`로 구분해 기존 `voss-hmi-bridge` 연결을 밀어내지 않는다. 노드 하나당 MQTT 클라이언트 하나만 사용한다. 기존 음성 노드가 이미 떠 있으면 두 개를 동시에 실행하지 말고 시험 대상 한 개만 사용한다. `mic 모드` 로그를 확인한다. `text 모드`로 폴백했다면 실마이크 검증으로 기록하지 않는다. `Ctrl+C`로 두 시험 노드를 종료한다. 실제 명령 해석을 확인하려고 intent_parser/manager/robot 노드를 추가할 필요는 없다.

## 구간별 관측과 실마이크 판정

- **음성→ROS:** 별도 터미널에 동일 ROS 환경을 로드하고 `ros2 topic echo /voss/voice/status std_msgs/msg/String`. 호출어에서 WAKE_DETECTED, 같은 utterance의 후속 결과를 확인한다. 호출어만 말하면 기본 5초 후 TIMED_OUT이 올 수 있다.
- **ROS→MQTT:** bridge 시작 로그에서 `MQTT connected` 확인. `ros2 topic info /voss/voice/status -v`로 기존 bridge 구독 확인. 정확한 payload 관측은 기존 web/debug read 계정으로 아래 관측기를 실행한다.
- **MQTT→SSE:** `curl -N http://localhost/api/stream`에서 `event:voice_status`와 JSON 3개 필드 확인. `link`의 mqtt도 UP이어야 한다. `/api/events`를 사용하지 않는다.
- **SSE→UI:** `http://localhost/`를 열고 개발자 도구 Network의 `/api/stream` 이벤트와 아이콘 색을 함께 확인한다. `?micTest=1` 버튼을 누른 결과와 구분한다.

기존 읽기 계정으로 MQTT를 관측하는 예(새 운영 MQTT 클라이언트가 아니라 일시적인 확인 도구):

```bash
python3 - <<'PY'
import getpass
import paho.mqtt.client as mqtt
client = mqtt.Client(client_id='voss-voice-observer')
client.username_pw_set('debug', getpass.getpass('기존 debug MQTT 비밀번호: '))
client.on_connect = lambda c, u, f, rc: c.subscribe('voss/voice_status', qos=0) if rc == 0 else print('인증 실패')
client.on_message = lambda c, u, m: print(m.payload.decode(), flush=True)
client.connect('127.0.0.1', 1883)
client.loop_forever()
PY
```

실제 발화 판정 순서:

1. 시작 전 초록.
2. “헬로 로키”라고 말한 뒤 Whisper 결과가 나왔을 때 노랑.
3. 짧은 후속 문장의 전사 수락 시 초록.
4. 실패 이벤트가 실제 발생하면 빨강·안내.
5. 호출어 후 침묵하면 ROS 5초 또는 전달 누락 시 UI 8초에 빨강·안내.
6. 아이콘 클릭 시 초록·안내 제거. ROS 노드가 재시작되지 않는지 확인.

실패를 일부러 만들기 위해 현장 AI·브로커·로봇 서비스를 종료하지 않는다. 실패/네트워크 장애의 재현은 위 격리 E2E 증거로 별도 기록한다.

## 미확정·후속

- 운영 토픽/QoS/ACL/SSE 이벤트 승인: 정의석·남현지(PL), `interface` PR 검토.
- 전사 수락을 넘어 정상 **명령 처리 완료**를 표시하려면 intent/manager 결과의 상관 ID 계약이 추가로 필요하다. 이번에는 그 의미를 임의로 확정하지 않았다.
- 처음 보는 서로 다른 발화의 절대 시각 순서: 원본에 timestamp/sequence가 없어 단일 발행기 순서를 전제로 한다.
- 실제 마이크→웹 전체: 사용자 발화로 위 절차 수행 후 횟수·이벤트 ID·화면 결과를 별도 기록.

### 이번 연결 보강의 정확한 파일 경로

```text
docs/interfaces/voice_status.md
docs/interfaces/mqtt.md
docs/interfaces/web_api.md
docs/testing/voice_web_link.md
docs/testing/voice_web_link_results.txt
docs/testing/voice_web_link_e2e.txt
docker/web/README.md
docker/mqtt/acl
src/voss_voice/voss_voice/voice_feedback.py
src/voss_voice/test/test_voice_feedback.py
src/voss_hmi/voss_hmi/voice_status.py
src/voss_hmi/voss_hmi/hmi_bridge.py
src/voss_hmi/test/test_voice_status.py
docker/web/backend/src/main/java/com/voss/web/mqtt/MqttSubscriberConfig.java
docker/web/backend/src/main/java/com/voss/web/mqtt/MqttEventRouter.java
docker/web/backend/src/main/java/com/voss/web/mqtt/VoiceStatusFilter.java
docker/web/backend/src/test/java/com/voss/web/mqtt/MqttSubscriberConfigTest.java
docker/web/backend/src/test/java/com/voss/web/mqtt/MqttEventRouterTest.java
docker/web/backend/src/test/java/com/voss/web/mqtt/MqttRouterSseIntegrationTest.java
docker/web/backend/src/test/java/com/voss/web/mqtt/VoiceStatusFilterTest.java
docker/web/frontend/src/App.tsx
docker/web/frontend/src/components/VossSortingWorkspace.tsx
docker/web/frontend/src/lib/voiceIndicator.ts
docker/web/frontend/test/voiceIndicator.test.mjs
docker/web/frontend/test/voiceDom.mjs
docker/web/frontend/test/vite.voice-test.config.mjs
scripts/integration/voice_logo_local.py
scripts/integration/test_voice_web_e2e.py
```

기존 `voice_listener.py`의 `/voss/voice/status` 발행과 `publish_transcript` 옵션은 재사용한다. 이번 연결 보강에서 별도의 상태 발행기를 추가하지 않았다.
