# T13 DOM 실측 · T14 전체 루프 준비 (정의석)

근거: `docs/interfaces/web_api.md` (#68, #54 MC-031), `mqtt.md` (#20),
`intent_json.md`, `docs/plan.md` (T13 #22, T14 #23).
2대 PC 배치는 `docs/interfaces/deployment_two_pc_trial.md`의 **시험 제안**으로,
현장 PL·안전 승인 전 확정된 정식 배포 계약을 대체하지 않는다.

## T13 — 12회 ROS 발행 → Web PC React DOM 실측

**전제:** Nodes PC의 `hmi_bridge`·`sort_logger`, Web PC Mosquitto·Spring Boot·React가 이미 실행 중.
*기존 노드·컨테이너를 재시작하지 않는다.*

1. **Web PC** HMI `http://127.0.0.1/`를 열고 F12 → Console.
   `t13_dom_observer.js` 내용을 **직접 복사하여 콘솔에 붙여 넣는다**.
   `T13 관측 준비 완료` 문구가 보이면 다음 단계로 넘어간다.
2. **Nodes PC** (일반 ROS 도메인, 재기동 필요 없음):
   ```bash
   cd ~/collaboration/rokey_cobot2_VOSS-t13
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
