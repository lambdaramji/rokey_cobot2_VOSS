# U5 파지 시퀀스·판정·reason — High-level design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u5-grasp` (main `309af67` 기준) · 작성 2026-10-09
- 상태: **HLD 승인(박병후, 10/09)** — D8 하한 질문(37.9 아님, 빈손은 범위 밖) 설명 후 승인. 다음: [U5-dd.md](U5-dd.md). 이 문서는 설계 단계 작업 노트다. 팀 계약은 docs/interfaces 가 우선이다.
- 범위: belt_servo 가 `/voss/robot/gripper` 를 **실제로 부르는 부분**(사전 개방·닫기·확인), 응답 판정 연결, 늦은 응답 버림, `message` → reason, x 여유 사전 검사, 새 파라미터. 재시도 **동작**(U9)은 하지 않는다. launch·실기 yaml 예시·fake_box·sim_check 는 U3(병렬) — U5 는 `launch/`·`config/*.example`·`config/belt_servo_sim.yaml`·`launch_params.py`·`fake_box.py`·`sim_check.py` 를 건드리지 않는다.
- 이미 있는 것(U1 #109): 순수 FSM 의 전이표(PREPARE→…→VERIFY, `judge_grip`, attempts, 취소 → stop → CANCELED/DEVICE_ERROR, 0 유지). 노드의 `_handle_actions` 는 그리퍼 행동을 받으면 `"U5 에서 구현"` 로그만 찍는다 — 그래서 지금 goal 은 PREPARE 를 못 벗어난다. **U5 는 이 빈 자리를 채운다.**
- 계약: topics.md belt_servo 행(goal 중 gripper 는 belt_servo 만, 비동기, 닫히는 동안 추종 계속), voss_msgs.md Gripper·TrackAndGrasp 행(GRASP→LIFT = 닫힘 완료 응답 + grip_detected + 보고폭 범위, 늦은 응답은 goal/attempt 별로 버림, grasped=false 자동 개방 금지).
- 측정 근거: measurements-1008 #14 (T34, #123 머지) — 39 mm·14 N, 0° 보고 폭 40.7~41.2, 15° 42.2~43.0, 30° 42.0~42.5, 벨트 방향 ±10 mm 12/12, 닫힘 1.6~2.1 s, 빈손 38.0~38.7.

## 0. 이 작업에서 정할 것 (HLD 승인 항목)

| # | 항목 | 제안 | 근거 |
|---|---|---|---|
| D1 | VERIFY 확인 방법 | **닫기 명령(39 mm·14 N)을 한 번 더** 보내 응답의 `grip_detected`·폭으로 판정 | Gripper.srv 에 "상태만 묻기"가 없다. 이미 쥐고 있으면 RG2 는 더 닫히지 않고 곧 응답할 것으로 **추정**(실 RG2 재닫기 거동은 T34 에서 재지 않음 → G0 전 벤치 확인 항목). 박스가 빠졌으면 빈손 폭 + grip 없음 → `DROPPED`. **재검 r1: 현재 DryRunRg2 는 재닫기에서 grip=false 를 낸다**(`rg2.py` 조건 `width < object_mm < 현재 폭` 이 `40.5 < 40.5` 로 거짓) → dry_run OK 경로를 위해 gateway 쪽 한 글자 수정(`<=`)을 담당 밖 요청(학민 #41) |
| D2 | 응답 `message` 읽기 | **콜론 앞 대문자 코드**로 판정(`"INVALID: width"` → `INVALID`). 모르는 코드 → `UNKNOWN` = DEVICE_ERROR. 원문은 로그에 그대로 | gateway rg2.py 가 `"INVALID: …"`, `"COMM_ERROR: RG2 safety_err"` 처럼 이유를 붙인다 |
| D3 | 코드별 처리 | OK → FSM 판정(HELD/NOT_HELD) · TIMEOUT·COMM_ERROR → DEVICE_ERROR · **BUSY → `BUSY_RETRY_DELAY_S`(0.5 s, 판단값) 뒤 같은 명령 1회 재요청, 또 BUSY 면 DEVICE_ERROR**(재검 r1: 지시서의 "다음 틱"은 33 ms 라 RG2 가 아직 바쁨 — 10/09 사용자 승인) · INVALID → DEVICE_ERROR + "설정 오류(폭·힘)" ERROR 로그 | U5 지시서 매핑 |
| D4 | 응답 기다림 한계 | `gripper_timeout_s` **3.0**(제안, 기본 파일에 값). 넘으면 TIMEOUT 으로 보고 DEVICE_ERROR(cause `GRIPPER_TIMEOUT`). 사전 개방·닫기·확인 모두 같은 한계 | T34 닫힘 최대 2.1 s + 여유. `stop_timeout_s` 1.0 과 같은 성격의 판단값 |
| D5 | 서비스가 없을 때 | 요청 순간 `service_is_ready()` 거짓 → 기다리지 않고 DEVICE_ERROR(`GRIPPER_UNAVAILABLE`) | stop 의 `STOP_UNAVAILABLE` 과 같은 방식(U1) |
| D6 | **x 여유 사전 검사** | TRACK → DESCEND 로 가려는 순간 `x_max − TCP x < 벨트속도 × (하강 예상 시간 + 닫힘 최대 시간) + 여유` 이면 **DESCEND 에 들어가지 않고** OUT_OF_REACH(cause `REACH_GRASP_ROOM`) | GRASP 중에는 FF 로 벨트를 따라가므로(U2) 닫히는 1.6~2.1 s 동안 약 80~100 mm 더 간다. 닫는 도중 x 끝에 닿으면 박스를 반쯤 쥔 채 끝난다 |
| D7 | goal 이 끝났는데 그리퍼 호출이 아직 진행 중 | 서비스 호출은 취소할 수 없으므로 **그대로 두고 응답이 오면 버린다**(로그 `gripper_late_discarded`). 끝난 뒤 개방·닫기 요청은 새로 보내지 않는다 | 자동 개방 금지(MC-014). 예: GRASP 중 취소 → RG2 는 끝까지 닫힘 → 박스를 쥔 채 CANCELED 일 수 있다 — sort_manager·사람이 확인 |
| D8 | T34 값의 기본 파일 | `config/belt_servo.yaml` 의 `grasp.hold_width_min_mm`·`max_mm` 을 null → **39.5·43.5**, 새 `grasp.close_time_max_s` **2.1** — 주석에 measurements-1008 #14 | #123 머지로 측정값이 main 에 있다. 범위 = "쥐었다고 인정하는 폭"이라 빈손은 범위 **밖(아래)** 이어야 한다. 하한 39.5 = 빈손 최대 38.7 **+** 0.8(쥔 최소 40.7 과는 1.2 — 두 무리 사이 틈 2.0 mm 의 가운데쯤), 상한 43.5 = 회전 최대 43.0 + 0.5. 경계값은 제안 |
| D9 | fake 환경 확인 | scratchpad **일회성 BoxTrack 발행 스크립트**(커밋 안 함) + main gateway `dry_run:=true dry_run_object_mm:=40.5`, belt_servo 는 `voss-ros ros2 run voss_servo belt_servo --ros-args --params-file <scratchpad 시험 yaml>` | 사용자 결정(10/09). **지시서 정리(10/09 주관 세션): OK·grasped=true 완료 기준은 자체 e2e pytest(FakeGripper·FakeClient)로 충족하고, gateway dry_run 스모크는 선택**(U3 sim.launch 가 머지돼 있으면 그것으로). U3 와는 서로 기다리지 않는다 |

## 1. 개념 두 개 (처음 보는 것만)

**① 기다리지 않고 들여다보기 (future poll).** 식당 진동벨을 생각한다.
```
주문(call_async) ──▶ 진동벨(future)을 받는다 ──▶ 자리로 돌아와 하던 일(30 Hz 추종)을 계속
                                                  │ 틱마다 한 번 "벨 울렸나?"(future.done()) 확인
                                                  ▼
                                    울림 → 음식(응답) 받기 / 3 s 지나도 안 울림 → TIMEOUT
```
카운터 앞에 서서 기다리면(동기 호출) 그동안 servo_cmd 가 끊기고, speedl 은 끊겨도 마지막 속도로 계속 간다(ADR-0010). 그래서 **절대 서서 기다리지 않는다.** stop 호출(U1)이 이미 이 방식이고 그리퍼도 똑같이 한다.

**② 이름표로 늦은 응답 버리기.** 진동벨에 `(goal, 시도 번호, 종류, 순번)` 이름표를 붙인다.
```
goal A 시도 1 닫기 벨 ── (3 s 넘어 TIMEOUT 처리, goal A 끝) ── 한참 뒤 벨 울림
                                                                  │
지금 들고 있는 벨 = 없음(또는 goal B 의 벨) ≠ 이 벨  ──▶  버린다 + 로그
```
노드는 "지금 기다리는 벨" 하나만 들고 있고, 틱의 poll 은 **그 벨만** 들여다본다. 벨을 내려놓는 순간(시간초과·goal 끝) 그 벨은 "고아"가 되고, 고아 벨이 나중에 울리면 무조건 버리고 센다(재검 r1: 버림 표시는 고아가 될 때만 단다 — executor 의 콜백 순서에 기대지 않게). 그래서 이전 시도·이전 goal 의 응답이 지금 판정에 섞이지 않는다(MC-012·013). 요청 메시지에 attempt 필드를 넣지 않아도 되는 이유다. BUSY 재요청은 순번만 올린 새 벨이다.

## 2. 모듈 구성

```
                     ┌────────────────────── belt_servo.py (ROS 노드) ──────────────────────┐
/voss/vision/box ──▶ │ _on_box / _on_pose (최신값 보관, U1·U2 그대로)                        │
/voss/robot/pose ──▶ │                                                                      │
                     │ 30 Hz _tick_goal                                                      │
                     │   ① _build_event ─┬─ U2: geometry → aligned·at_*·reach               │
                     │                   ├─ U5: _poll_gripper ──▶ grip.poll() ──▶ ev.gripper │
                     │                   └─ U5: grip.grasp_room_ok() ──▶ ev.grasp_room       │
                     │   ② fsm.step (U1 + U5 한 줄) ──▶ actions                             │
                     │   ③ _handle_actions ─ GRIPPER_OPEN/CLOSE/VERIFY ─▶ _request_gripper ──┼──▶ /voss/robot/gripper (call_async)
                     │                     └ REQUEST_STOP ─▶ _request_stop (U1) ──────────────┼──▶ /voss/robot/stop
                     │   ④ control.command (U2) ─▶ servo_cmd 발행 · 틱 로그(gripper 칸 채움) │──▶ /voss/robot/servo_cmd
                     └──────────────────────────────────────────────────────────────────────┘
                              ▲ 순수 함수만 부른다
             ┌────────────────┴───────────────┐
             │ grip.py (새, ROS 없음)          │  호출 이름표·순번 / message → 코드 / 기다림 판정
             │                                 │  (응답·TIMEOUT·BUSY 재요청·버림) / x 여유 계산
             │ fsm.py (U1, 한 줄 추가)          │  TickEvent.grasp_room, TRACK 전이에 여유 검사
             └─────────────────────────────────┘
```

| 모듈 | 책임 | ROS 의존 | 테스트 |
|---|---|---|---|
| `grip.py` (새) | 그리퍼 호출 한 건의 생애(보냄 → 응답 / BUSY 재요청 / TIMEOUT), message 코드화, x 여유 계산 | 없음 | `test_grip.py` 순수 |
| `fsm.py` (수정 소) | `TickEvent.grasp_room`(기본 True), TRACK + aligned 때 여유 없으면 OUT_OF_REACH | 없음 | `test_fsm.py` 에 행 추가 |
| `belt_servo.py` (수정) | `_request_gripper`·`_poll_gripper`·늦은 응답 로그 콜백, `_build_event` 에 두 칸, 틱·시도 로그 gripper 칸 | 있음 | `test_action_e2e.py`: 가짜 그리퍼 서비스 4 케이스 + α, `test_node.py`: 가짜 future |
| `params.py` (수정) | `gripper_timeout_s`, `grasp.close_time_max_s`, `grasp.room_margin_mm` 추가·검사 | 없음 | `test_params.py` |
| `log_schema.py` (필요 시 소) | gripper 칸 내용 정리 함수 | 없음 | `test_log_schema.py` |
| `config/belt_servo.yaml` | 새 키 + T34 값(D8) | — | 기동 검사 |

## 3. phase 별 그리퍼 호출 (승인된 FSM 위에 얹는 것)

| phase | 들어갈 때 보내는 요청 | 기다리는 동안 움직임(U2) | 응답이 오면 |
|---|---|---|---|
| PREPARE | 개방 `pre_open_mm` 90·`force_n` 14 | 접근 높이에서 FF+P | OK → TRACK (폭·grip 은 보지 않음). 실패 코드 → DEVICE_ERROR |
| TRACK | — | FF+P, 정렬 기다림 | — · **정렬됐는데 x 여유 부족 → OUT_OF_REACH(`REACH_GRASP_ROOM`)** |
| DESCEND | — | 하강 | — |
| GRASP | 닫기 `grasp_width_mm` 39·14 N (attempts +1) | **FF 만**, z 고정 | HELD(OK + grip + 폭 범위) → LIFT · NOT_HELD → GRASP_FAILED(U5 는 max_attempts 1) · 실패 코드 → DEVICE_ERROR |
| LIFT | — | xy 0, z 위로 | — |
| VERIFY | 닫기 39·14 N 한 번 더 (D1) | 0 | HELD → **OK, grasped=true** · NOT_HELD → `DROPPED` → GRASP_FAILED · 실패 코드 → DEVICE_ERROR |

- 한 번에 진행 중인 그리퍼 호출은 **최대 하나**. FSM 이 한 phase 에서 하나만 시키고, 응답이 와야 다음 phase 로 가므로 겹치지 않는다.
- stopping(취소 후 stop 응답 대기) 중에는 FSM 이 그리퍼 응답을 보지 않는다(U1 전이표 3). 진행 중 호출은 D7 대로 버린다.

## 4. 끝나는 길과 그리퍼 (완료 기준 "grasped=false 면 개방 없음" · "마지막 cmd 0")

| 끝나는 길 | reason | 그 뒤 그리퍼 요청 | 마지막 servo_cmd |
|---|---|---|---|
| VERIFY HELD | OK, grasped=true | 없음 (놓기는 MoveToZone PLACE) | 0 (U1 0 유지 0.5 s) |
| GRASP/VERIFY NOT_HELD, 시도 소진 | GRASP_FAILED | **없음** | 0 |
| 그리퍼 TIMEOUT·COMM_ERROR·INVALID·BUSY 2회·UNKNOWN·UNAVAILABLE | DEVICE_ERROR | **없음** (진행 중 호출은 버림) | 0 |
| 정렬 후 x 여유 부족 / 구간 끝 / Z_MIN | OUT_OF_REACH | 없음 | 0 |
| LOST · STALE_INPUT | LOST · STALE_INPUT | 없음 | 0 |
| 취소 → stop OK / 실패·무응답 | CANCELED / DEVICE_ERROR | 없음 | 0 |
| 내부 예외 | DEVICE_ERROR(`INTERNAL_EXCEPTION`) | 없음 | 0 (U1 `_safe_zero`) |

- "끝난 뒤 개방 요청 없음"은 구조로 보장한다: 그리퍼 요청은 `_handle_actions` 에서만 나가고, FSM 은 종료 전이에 행동을 붙이지 않는다. 재시도 개방(GRIPPER_OPEN, 전이표 14)은 goal 안에서 다음 시도를 위한 것이고 U5 기본 `max_attempts=1` 에서는 나오지 않는다. 테스트로도 확인한다.
- 마지막 cmd 0 은 U1·U2 가 이미 보장한다(terminal 틱 0 + 0 유지). U5 는 그리퍼 경로 케이스마다 다시 확인한다.

## 5. 선택과 대안

| 선택 | 대안 | 대안을 안 쓴 이유 |
|---|---|---|
| 틱마다 future 확인(poll) | `add_done_callback` 에서 바로 FSM 진행 | FSM 은 틱 한 곳에서만 돌아야 순서가 분명하다(U1 원칙). 콜백은 "늦은 응답 로그"에만 쓴다 |
| 이름표 비교로 버림 | 요청에 attempt 번호 넣기 | Gripper.srv 를 바꿔야 한다(인터페이스 변경, 담당 밖). 계약도 "future 로 버린다" |
| VERIFY = 닫기 재전송 | `/voss/robot/state` 의 `gripper_width_mm` 읽기 | RobotState 에 grip_detected 가 없고 2 Hz 라 늦다. 판정 규칙을 GRASP 와 하나로 유지 |
| x 여유는 DESCEND 전 한 번 | GRASP 중에도 계속 검사 | GRASP 중 끝내면 반쯤 쥔 채 멈춘다. 들어가기 전에 막는 게 안전. GRASP 중 구간 끝은 기존 REACH 검사(X_MAX)가 그대로 잡는다 |
| BoxTrack 일회성 스크립트 | U3 fake_box 기다리기 | 사용자 결정(D9). U3 와 병렬이라 기다리면 G0 전에 못 끝낸다 |

## 6. Detail design 에서 정할 것

1. `grip.py` 함수 목록·입출력: 호출 기록(dataclass) 필드, `poll` 의 결과 종류(대기 / 응답 / 재요청 / 시간초과), 코드 집합.
2. x 여유 식의 정확한 항: 하강 예상 시간 = (접근 높이 − 파지 높이) / `descend_speed` (가속 구간 포함 여부), 계산에 쓰는 TCP x(보정 TCP).
3. 새 파라미터 이름·단위·검사(아래 부록 A).
4. 틱·시도 로그 `gripper` 칸 내용(종류·순번·보낸/받은 시각·지연·ok·폭·grip·message 원문·코드·판정).
5. 테스트 목록: grip 순수 / fsm 추가 행 / e2e(`test_action_e2e.py`) 4 케이스(정상·빈손·늦은 응답·정지 실패) + BUSY 1회·2회 + INVALID + UNAVAILABLE + TIMEOUT + 끝난 뒤 개방 없음 + 마지막 cmd 0 / params.
6. dry_run 스모크 절차(scratchpad 스크립트·시험 yaml 내용, object 40.5 → OK, 0 → GRASP_FAILED).

## 부록 A. 새·바뀌는 파라미터 (이름 제안, 검사는 DD)

| 이름 | 단위 | 기본 파일 | 근거 |
|---|---|---|---|
| `gripper_timeout_s` | s | 3.0 (제안) | T34 닫힘 최대 2.1 s + 여유 |
| `grasp.close_time_max_s` | s | 2.1 | T34 닫힘 90→39 최대 (measurements-1008 #14, x 여유 계산용) |
| `grasp.room_margin_mm` | mm | 10.0 (제안) | 판단값 |
| `grasp.hold_width_min_mm` | mm | null → **39.5** | 빈손 최대 38.7 + 0.8 — 빈손이 범위 아래로 빠지게 (#14) |
| `grasp.hold_width_max_mm` | mm | null → **43.5** | 회전 30° 까지 최대 43.0 + 0.5 (#14) |

예시 계산(접근 40 mm·kp_z 2·하강 상한 0.05·가속 0.1·height_tol 2, DD E5 식 — 재검 r1 로 P 감속 꼬리 포함): 하강 ≈ 2.19 s(U2 시뮬레이션 2.17 s 와 일치), 닫힘 2.1 s → 48 mm/s × 4.29 s ≈ 206 mm + 10 = **216 mm** → DESCEND 진입 때 TCP x ≤ 620 − 216 = **404 mm** 여야 한다. 관측 자세에서 정렬은 보통 x ≈ −13~+7 mm(U2 시뮬레이션)라 정상 흐름에서는 걸리지 않고, 늦게 정렬된 박스만 막는다.

## 7. 변경 기록
- 2026-10-09: 초안 (작업 세션 U5). 같은 날 범위 재시작 — launch·실기 예시는 U3 로, main 기준으로 다시 씀, T34(#123) 값을 기본 파일에. 재검 r1(독립 서브에이전트) 반영: D1 DryRunRg2 사실 정정·벤치 확인, D3 BUSY 지연 재요청, 하강 시간 예시, 시험 위치.
