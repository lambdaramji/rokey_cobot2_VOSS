# T13 #22 — 웹 HMI DOM 지연 검증

근거: `docs/interfaces/web_api.md` (#68), `mqtt.md` (#20), `docs/plan.md`, MC-031.
명령과 HMI 정식 배포 계약은 공용 PC 로컬을 기준으로 한다. 이전 두 PC 비구동 실측은 시험 증거이나 공식 시연 배포 확정이 아니다.

**실행 준비:** 아래 명령은 각 PC의 **레포 루트에서 실행**한다. 기존 로봇·Docker·MQTT 서비스는 임의 재시작하지 않는다.

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

## S2-T08 — 팔레트 3D 화면 재생 · 반영 ≤ 1초 (공용 PC 한 대)

**전제:** Sprint 2 `voss_msgs`(PalletState)가 빌드된 워크스페이스(`integ/1013-gate-v15` 이후), `hmi_bridge`·Mosquitto·웹(Spring Boot·Nginx)이 떠 있고 **`sort_manager` 는 꺼져 있다**(재생기가 확인하고 거부한다). 재생 데이터는 `docker/web/frontend/test/fixtures/pallet_s1.json`(실제 pallet_fsm 의 S1 + slot 4 실패·#37 당겨 놓기, 화면 칸 번호 = slot + 1).

1. 공용 PC 브라우저 `http://127.0.0.1/` → F12 Console 에 `s2_pallet_dom_observer.js` 내용을 붙여 넣는다 → `S2-T08 관측 준비 완료`.
2. 공용 PC 터미널(레포 루트):
   ```bash
   source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
   python3 scripts/integration/s2_pallet_replay.py              # 1초 간격 20개, 끝나면 빈 상태로 되돌림
   ```
3. 화면 확인(재생 확인): 계획 직후 16칸 배정·"대치동 3개" 경고 → 칸 1부터 차례로 채워짐 → 칸 5(2열 1층 1줄) 청담 박스 실패 뒤 칸 7 역삼 박스가 칸 5 로 내려옴 → "16개 중 15개 적재 · 실패 1".
4. 터미널 끝의 `SENT_JSON=` 뒤 배열을 복사해 Console 에서 `vossPalletReport(<배열>)` → 20행 표와 `p95`·`최대`·`판정`. 최대 > 1000 ms 이거나 미수신이 있으면 FAIL.

**안전:** `/voss/pallet/state` 화면용 상태만 발행한다. 로봇·벨트·그리퍼 명령, `/voss/sort/command`, MQTT `voss/command` 는 발행하지 않는다. 같은 PC 시계라 시계 보정은 없다(T13 과 다름).
**판정 범위:** ROS 발행 → hmi_bridge → MQTT → SSE → React DOM. 실제 sort_manager 발행 → DOM 은 팔레타이징 실기(S2-T02·T03·T21 뒤)에서 다시 잰다.

## T14 — 지시 4종 각 1회 (#23)

`src/voss_voice/test/fixtures/intent_cases.json` 기준으로
1. **운전**: 시작/정지/재개 중 시험 지시(예 `작업 시작해`)
2. **우선**: `역삼동부터 분류해` → priority(역삼동)
3. **답변**: ASKING+box_id 확인 후 `대치동` → answer(대치동, 동일 box_id)
4. **이력**: `보류 몇 개야` → `GET /api/stats` → `/voss/voice/say`

**안전한 선행 시험:** robot과 연결되지 않은 별도 ROS_DOMAIN_ID에서
가짜 manager·ZoneMap·SortState로 텍스트 입력 경로부터 검증한다.
기존 실제 도메인에 `/voss/voice/transcript`·`/voss/voice/intent`를 시험 발행하지 않는다.
특히 음성 `start`·`priority`는 웹의 로컬 제한(비-stop 명령은 공용 PC 로컬만)
보호 대상이 **아니다**. `speech_out`·마이크/Whisper 시험과 실제
sort_manager/로봇 전체 루프는 후속이며, 김학민 현장 안전 담당자와
남현지 PL이 실제 실행과 동작 판정을 맡는다.

**T14 완료 기준:** 4유형 각각 transcript→intent_parser→sort_manager 접수
→상태·결과→HMI/DB와 TTS 응답을 실제로 1회씩 확인한다.
별도 도메인의 mock 경로와 단독 REST/TTS 시험은 준비·부분 검증이지
T14 전체 루프 완료나 실로봇 구동 완료 증거가 아니다.
