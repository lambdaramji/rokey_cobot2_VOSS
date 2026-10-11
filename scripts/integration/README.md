# T13 DOM 실측 · T14 전체 루프 준비 (정의석)

근거: `docs/interfaces/web_api.md` (#68, #54 MC-031), `mqtt.md` (#20),
`intent_json.md`, `docs/plan.md` (T13 #22, T14 #23).
2대 PC 배치는 `docs/interfaces/deployment_two_pc_trial.md`의 **시험 제안**으로,
현장 PL·안전 승인 전 확정된 정식 배포 계약을 대체하지 않는다.

**실행 위치:** 아래의 Nodes PC 명령은 각 PC에서 **해당 레포 루트로 이동한 뒤** 실행한다. 개인 홈 디렉터리 경로는 문서에 기록하지 않는다.

## T13 — 12회 ROS 발행 → Web PC React DOM 실측

**전제:** Nodes PC의 `hmi_bridge`·`sort_logger`, Web PC Mosquitto·Spring Boot·React가 이미 실행 중.
*기존 노드·컨테이너를 재시작하지 않는다.*

1. **Web PC** HMI `http://127.0.0.1/`를 열고 F12 → Console.
   `t13_dom_observer.js` 내용을 **직접 복사하여 콘솔에 붙여 넣는다**.
   `T13 관측 준비 완료` 문구가 보이면 다음 단계로 넘어간다.
2. **Nodes PC** (일반 ROS 도메인, 재기동 필요 없음):
   ```bash
      source /opt/ros/jazzy/setup.bash
   source install/setup.bash
   python3 scripts/integration/t13_dom_publisher.py
   ```
3. Web PC Console의 12행 `console.table`과 최종 `p95`, `최대 지연 상한`,
   `판정`을 복사한다. 시계 오프셋·RTT 오차도 시험 증거에 포함한다.
   12개 중 1개라도 `상한>1000ms`면 실패로 보고 원인 분석한다.

**안전:** 스크립트는 `/voss/sort/state`에 IDLE·ready=false 상태만 발행한다.
로봇·벨트·그리퍼 제어 명령은 전혀 발행하지 않는다. `sort_manager` 또는
기존 SortState 발행자가 있으면 실행을 거부한다. 시험 전 로봇이 운전 중이
아닌지 현장 담당자가 확인한다. 브라우저는 Web PC 로컬에서 연다.

**판정 범위:** 이 시험은 ROS 발행기→MQTT→SSE→React DOM의 비구동 실측이다.
문서의 **manager 상태 변경 로그→DOM** 전체 기준은 실제 manager가 동작하는
현장 안전 검증에서 추가 실측해야 한다. `UNKNOWN`은 3초 상태 미수신 시 정상이다.

## T14 — 지시 4종 각 1회 (#23)

`src/voss_voice/test/fixtures/intent_cases.json` 기준으로
1. **운전**: 시작/정지/재개 중 시험 지시(예 `작업 시작해`)
2. **우선**: `역삼동부터 분류해` → priority(역삼동)
3. **답변**: ASKING+box_id 확인 후 `대치동` → answer(대치동, 동일 box_id)
4. **이력**: `보류 몇 개야` → `GET /api/stats` → `/voss/voice/say`

**안전한 선행 시험:** robot과 연결되지 않은 별도 ROS_DOMAIN_ID에서
가짜 manager·ZoneMap·SortState로 텍스트 입력 경로부터 검증한다.
기존 실제 도메인에 `/voss/voice/transcript`·`/voss/voice/intent`를 시험 발행하지 않는다.
특히 음성 `start`·`priority`는 Web PC의 `VOSS_NONSTOP_COMMANDS_ENABLED=false`
보호 대상이 **아니다**. `speech_out`·마이크/Whisper 시험과 실제
sort_manager/로봇 전체 루프는 후속이며, 김학민 현장 안전 담당자와
남현지 PL이 실제 실행과 동작 판정을 맡는다.

**T14 완료 기준:** 4유형 각각 transcript→intent_parser→sort_manager 접수
→상태·결과→HMI/DB와 TTS 응답을 실제로 1회씩 확인한다.
별도 도메인의 mock 경로와 단독 REST/TTS 시험은 준비·부분 검증이지
T14 전체 루프 완료나 실로봇 구동 완료 증거가 아니다.

## T14 비구동 4유형 실행 (T13 지연 실측 후)

**Nodes PC**: 기존 메인 도메인의 ROS 노드는 그대로 두고,
시험 스크립트와 자식 voice_listener(text)·intent_parser만 `179` 도메인에서 실행한다.

```bash
git pull --ff-only origin feat/22-web-hmi-initial
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to voss_voice --symlink-install
source install/setup.bash

# 이 명령 줄에만 시험용 ROS 격리 설정 적용 (현재 셸 ROS_DOMAIN_ID를 변경하지 않음).
ROS_DOMAIN_ID=179 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST python3 scripts/integration/t14_voice_dry_run.py
```

- 실제 `voice_listener(mode=text)`·`intent_parser`와 Web PC 실시간 `/ai/intent`,
  `/api/stats` HTTP 경로를 호출한다. 시작·우선·답변 Intent는 **모의 manager에만** 도달한다.
- `query_history`는 현재 Web HMI `NO_SESSION`이면
  `기록을 조회할 수 없습니다.` 안내를 정확히 반환하는지 검사한다. 이것은
  이력 정상 조회 성공 검증이 아니라 NO_SESSION 폴백 검증이다.
- ROS_DOMAIN_ID 179에 **어떤 기존 노드라도 보이면 중단**한다.
- 4/4는 텍스트 폴백/Intent/TTS 안내 토픽의 선행 시험 결과이며,
  실제 TTS 오디오 재생·마이크 호출어·Whisper STT·실제 sort_manager 접수·HMI 전체 루프의 완료와 다르다.
- 오류 로그: `~/.local/state/voss-t14/{voice_listener,intent_parser}.log`.

## T14 실제 manager 접수 + 실제 TTS 스피커 동시 시험 (격리, 비구동)

**목적/제약:** `sort_manager` **실제 노드**의 IDLE 상태 priority(역삼동) 수락을
관리자 로그로 증명하고, **실제 `speech_out`**이 FastAPI `/ai/tts`를 호출해
Nodes PC `aplay`로 스피커 재생을 완료하는지 한 번에 검증한다.
실제 manager의 IDLE priority는 `/voss/voice/say`를 생성하지 않기 때문에,
**TTS 문장만 시험기가 발행**한다. manager→고유 안내 Say→TTS 전체 연결
완료라고 판정하지 않는다. 실제 robot_gateway·TrackAndGrasp·MoveToZone을
연결하거나 `start`·`stop`을 보내지 않는다.

**PC:** 오직 **Nodes PC `<Nodes PC>`** 터미널에서 실행.
Web PC의 기존 FastAPI `8000` 포트/SSH 터널·Docker·MQTT·DB를 재설정하지 않는다.
사전 조건: 기존 분리 PC SSH `127.0.0.1:8000` 포워드 유지, Nodes PC에서
`aplay` 사용 가능하고 스피커 연결/음량 설정, 실제 ROS 도메인과 구분되는
`ROS_DOMAIN_ID=179`+로컬 탐색. 격리 도메인 179에 남은 동일 사용자 소유의 T14 음성·관리자 시험 노드만
자동 SIGTERM으로 정리하고, 정리가 안 되거나 다른 노드가 남아 있으면 새 시험을 **중단**한다.

```bash
# [Nodes PC — <Nodes PC>]
git pull --ff-only origin feat/22-web-hmi-initial || exit 1
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to voss_manager voss_voice --symlink-install || exit 1
source install/setup.bash

# ROS 없이 실행 가능한 순수 판정 함수 3개 시험 (pytest가 설치된 경우)
python3 -m pytest -q scripts/integration/test_t14_trial_checks.py

# 실제 manager·speech_out, 로봇 비구동/격리
ROS_DOMAIN_ID=179 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  python3 scripts/integration/t14_manager_tts_trial.py
```

성공은 두 로그 증거로 판정한다: `sort_manager.log`에
`intent priority → priority '역삼동': True`, `speech_out.log`에
`TTS_FIRST_PCM_WRITTEN`과 `TTS_FINISHED`. 시험기는 PCM 전달 지연을 출력한다.
**최종 실제 음성 청취는 현장 사람이 직접 확인**한다(로그만으로 소리가 들리는지
보장하지 않는다). 관련 로그는 `~/.local/state/voss-t14/manager-tts/`.

**실제 실로봇 T14 전체 검증:** 남현지 PL과 김학민 안전 담당자가 현장에서
로봇 안전 점검/비상정지 준비를 마친 후 기존 공식 ROS 도메인의 실제 manager,
TTS, HMI/DB 상태를 별도 검증한다. 이 스크립트 2건 PASS만으로
T14 #23 전체 완료 처리 금지.

## T14 후속 1회 통합: 실제 마이크 → Whisper → manager + 이력 → TTS

**모두 Nodes PC에서만 실행.** 별도 ROS_DOMAIN_ID=179과 LOCALHOST 탐색이 필수.
이 시험은 실제 `voice_listener(mode=mic)`, `intent_parser`, `sort_manager`,
`speech_out`를 실행한다. 실제 로봇/서보/게이트웨이 서비스·액션에는 연결하지
않으며, `start`·`resume`·`stop`·`answer` 명령은 시험에서 발행하지 않는다.
manager는 IDLE에서 `priority`만 접수한다. `hmi_bridge`를 별도 도메인에서 실행해
공유 MQTT 상태를 오염시키지 않는다.

```bash
# [Nodes PC — <Nodes PC>] Web PC 작업 없음
git pull --ff-only origin feat/22-web-hmi-initial || exit 1
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to voss_manager voss_voice --symlink-install || exit 1
source install/setup.bash
python3 -m pytest -q scripts/integration/test_t14_trial_checks.py || exit 1
ROS_DOMAIN_ID=179 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST python3 scripts/integration/t14_mic_history_speech_trial.py
```

스크립트 화면이 지시하는 때 마이크에 **1)** `헬로 로키, 역삼동부터 분류해`,
**2)** `헬로 로키, 보류 몇 개야`를 각각 한 번 말한다. 키보드 입력을
마이크로 간주하지 않는다. 마이크/보이스 패키지가 없거나 입력 장치가 없으면
text 폴백을 탐지하고 **실패** 처리한다. 로컬 FastAPI `/ai/stt`를 실제 호출한다.
마이크 입력 전에 무음 WAV로 Whisper를 사전 적재한다(녹음 파일 생성 없음).
사전 적재 HTTP 상한은 90초이고, 발화 입력 대기 상한은 85초다.
음성 노드 자체 STT timeout은 5초로 유지한다.
실제 manager priority 수락과 ROS 이력 안내 `/voss/voice/say`·`speech_out`
첫 PCM ≤3 s·재생 완료를 검증한다. 음성 청취 여부는 사람이 판정한다.

이력 데이터는 동일 Web PC의 Spring Boot `GET /api/sessions/current`를 먼저
읽는다. 현재 세션이 없으면 `GET /api/stats`의 `NO_SESSION` 폴백 안내
`기록을 조회할 수 없습니다.`만 검사하여 **실제 DB 집계 검증 미완료**라고 표시한다.
현재 세션이 있으면 `보류는 N개입니다.` 안내를 검사하지만 정확한 DB 행 수와의
일치 여부는 별도 검증이 필요하다. HMI React 화면 DOM 반영과 manager가
자체 생성한 안내를 TTS로 보내는 경로, 실로봇 움직임은 이 시험 범위 밖이다.
로그: `~/.local/state/voss-t14/manager-tts/`. 실행 전 격리 시험 노드를
자동 정리하고, 종료되지 않거나 무관한 노드가 남으면 중단한다. 환경에 문제가 생겨도 Web PC 컨테이너,
SSH 터널, 메인 ROS 도메인의 서비스를 재시작하지 않는다.

## T14 실제 DB 집계 안내 + 실제 manager 자체 Say→TTS (연속 비구동)

Web API 계약 `docs/interfaces/web_api.md`를 따르며 **읽기 전용 GET만** 사용한다.
Nodes PC에서 SSH 로컬 8080/8000 포워드가 기존에 열려 있어야 한다.
현재 세션이 있으면 `intent_parser`의 정규 `held_count` 조회를 사용한다.
현재 세션이 없다면 `NO_SESSION`을 우회하거나 세션을 위조하지 않는다.
대신 명시적인 `session_id=all`로 PostgreSQL 실제 전체 이력 집계를 읽어
시험기 Say로 TTS를 재생하며 **전체 이력 조회와 현재 세션 음성 이력 조회를 구분**한다.

실제 manager의 별도 Say는 가짜 readiness/MoveToZone 서비스가 OBSERVE 이동을
`T14_SIMULATED_OBSERVE_FAILURE`로 거절하도록 해서 실제 manager FSM의
`관측 자세로 가지 못해 일시정지했습니다.`를 생성한다. 가짜 서비스만
ROS_DOMAIN_ID=179에서 뜨므로 로봇 구동 없음. DB·MQTT에 쓰지 않는다.

```bash
# [Nodes PC - <Nodes PC>]
git pull --ff-only origin feat/22-web-hmi-initial || exit 1
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -q scripts/integration/test_t14_trial_checks.py || exit 1
ROS_DOMAIN_ID=179 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST python3 scripts/integration/t14_db_manager_say_trial.py
```

성공 근거는 manager 자체 `/voss/voice/say` 내용, manager OBSERVE 실패 로그,
첫 번째 PCM 재생 완료, 실 DB 조회 `held_count`와 생성된 문장 일치,
두 번째 PCM 재생 완료다. 두 안내가 스피커에서 들렸는지 사람의 청각 확인 필요.
로그 `~/.local/state/voss-t14/manager-tts/`.

기존 ROS_DOMAIN_ID=179·LOCALHOST의 동일 사용자 T14 시험 노드 4종은
시작 전 자동 SIGTERM으로 정리한다. 다른 도메인·다른 사용자는 건드리지
않고, 정리되지 않으면 **중단**한다. `start` 명령은 반드시 가짜 준비/서비스가 있는 격리
도메인에서만 시험기가 실행한다.
