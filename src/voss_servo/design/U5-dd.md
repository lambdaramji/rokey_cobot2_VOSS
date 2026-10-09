# U5 파지 시퀀스·판정·reason — Detail design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u5-grasp` (main `309af67`) · 작성 2026-10-09
- 상태: **DD 승인(박병후, 10/09)**, 재검 r1 반영본 재승인(10/09, BUSY 0.5 s 지연 포함). 앞: [U5-hld.md](U5-hld.md)(승인, D1~D9). 다음: U5-pseudo.md.
- 단위: 시간 s, 길이는 파라미터 mm · 내부 계산 m(U2 `ControlConfig` 와 같음), 속도 m/s, 폭 mm(RG2 보고값), 힘 N.

## 0. DD 에서 새로 정한 것 (승인 항목)

| # | 항목 | 정한 것 | 이유 |
|---|---|---|---|
| E1 | timeout 기준 시각·BUSY 재요청 시점 | **요청 한 건마다** 보낸 시각부터 `gripper_timeout_s`. BUSY 응답을 받으면 `BUSY_RETRY_DELAY_S`(0.5 s) 기다렸다가 재요청하고, 재요청은 새 요청이라 시계도 새로 (**재검 r1**: "다음 틱" 33 ms 뒤면 RG2 가 아직 바쁘다 — 예: 취소된 goal 의 닫기가 1.6~2.1 s 진행 중) | BUSY 는 RG2 가 바쁘다고 바로 돌려준 응답이라 앞 요청 시간이 거의 안 쓰였다 |
| E2 | stopping 중 그리퍼 | stopping(취소 후 stop 대기) 동안 **poll 하지 않는다** → BUSY 재요청도 안 나간다. 진행 중 호출은 goal 이 끝나면 버림(D7) | 취소한 뒤 새 그리퍼 명령이 나가면 안 된다 |
| E3 | future 가 예외로 끝남 | `COMM_ERROR` 로 본다 (cause `GRIPPER_COMM_ERROR`, 로그에 예외 문자열) | rclpy 쪽 실패도 장비 통신 실패와 같은 처리 |
| E4 | FSM 에 넘기는 message | 원문이 아니라 **코드**(`OK`·`BUSY`·…·`UNKNOWN`·`UNAVAILABLE`·`TIMEOUT`). 원문은 로그에만 | `judge_grip` 이 cause 를 `GRIPPER_<message>` 로 만든다 → `GRIPPER_INVALID: width…` 같은 긴 cause 가 안 생기게. **`judge_grip`·전이표 5번은 고치지 않는다** |
| E5 | 하강 예상 시간 (**재검 r1 정정**) | U2 의 z 제어(`kp_z × 오차` 를 `descend_speed` 로 포화)를 따른 식. 거리 D, 상한 v, 가속 a, 게인 k, 허용치 tol, 감속 시작 거리 `d_p = v/k`: D > d_p 이면 `t = v/(2a) + (D − d_p)/v + ln(d_p/tol)/k`, 아니면 `t = ln(D/tol)/k` (음수면 0) | 처음 식(등속+가속, 1.68 s)은 P 감속 꼬리 약 0.5 s(≈ 24 mm)를 빼서 여유 10 mm 를 넘게 과소 추정했다. 새 식: D 59 mm·v 0.05·a 0.1·k 2·tol 2 → 0.25 + 0.68 + 1.26 = **2.19 s** (U2 시뮬레이션 2.17 s 와 일치, U2-dd 7절) |
| E6 | x 여유 계산의 x | 보정 TCP x (`geo.tcp[0]`, U2 와 같은 TCP) | 다른 판정과 같은 TCP 를 본다 (U2 DD 0절) |
| E7 | 로그 `gripper` 칸 | **진행 중 호출 기록**, 없으면 **이 goal 의 마지막 끝난 호출 기록**, 둘 다 없으면 null. GOAL_END 행에 마지막 응답이 남는다 | 게이트 실패 원인 분류(ADR-0009: 폭·grip·지연)에 바로 쓴다 |
| E8 | 늦은 응답 표시 (**재검 r1 정정**) | 호출이 **고아가 되는 순간에만**(시간초과 처리·goal 끝에 진행 중) 그 future 에 done 콜백을 단다 → 응답이 오면(이미 와 있었으면 바로) 노드 카운터 `grip_late_discarded` +1 + INFO 한 줄. 요청할 때는 콜백을 달지 않고 이름표 비교(`is_current`)도 없앤다. 틱 로그에는 넣지 않는다 | rclpy 는 future done 콜백을 executor 태스크로 미뤄 부른다. "요청 때 콜백 + 현재 호출이면 무시" 방식은 "콜백이 틱보다 먼저 돈다"는 executor 내부 순서에 기댄다 — 순서가 바뀌면 정상 응답도 늦음으로 센다. 고아 때만 달면 순서와 무관 |
| E9 | 새 교차 검사 | `gripper_timeout_s > grasp.close_time_max_s`, `grasp.hold_width_max_mm < gripper.pre_open_mm`, (재검 r1) `grasp.hold_width_min_mm > gripper.grasp_width_mm` — 빈손 보고 폭은 명령 폭 39 아래(38.0~38.7)라 하한이 명령 폭 이하면 빈손이 범위에 들어올 수 있다 | 정상 닫힘이 timeout 되는 설정·쥔 폭이 개방 폭보다 큰 오타를 기동 때 막는다 |
| E10 | 기존 e2e 시험의 가짜 gateway | `FakeClient` 에 **가짜 그리퍼 서비스를 기본으로** 추가(개방·닫기 모두 즉시 OK). 그리퍼가 없는 경우는 따로 시험 | U5 뒤에는 PREPARE 첫 요청에서 서비스가 없으면 바로 DEVICE_ERROR(D5) → 기존 LOST·취소 시험이 깨진다 |
| E11 | 응답을 늦게 주는 가짜 그리퍼 | 가짜 그리퍼 노드는 **별도 스레드 executor** 에서 돌리고 서비스 콜백 안에서 `time.sleep(delay)`. 정리 순서 고정: 그리퍼 executor shutdown → 스레드 join → 그리퍼 노드 destroy → 기존 정리 → `rclpy.try_shutdown()` (재검 r1) | belt_servo 와 같은 executor 에서 잠자면 belt_servo 틱도 멈춰 시험이 엉뚱해진다 |
| E12 | e2e 결정성 (**재검 r1**) | ① 픽스처가 `node._gripper_cli.wait_for_service(2.0)` 를 단언한 뒤 yield (D5 거짓 UNAVAILABLE 방지) ② 움직이는 시험(①~④)은 `control.kp_per_s` 를 **1.5** 로 덮어씀 ③ BUSY·INVALID 시험(⑤⑥)은 정지 박스를 띄워 LOST 와 경합하지 않게 하고 최종 reason 대신 요청·기록만 단언 | ② `READY_ARGS` 의 kp 0(FF 만)이면 가속 제한 0.1 때문에 TCP 가 박스보다 0.048²/(2·0.1) ≈ 11.5 mm 뒤처진 채 따라잡지 못해 `align_tol_along` 3 mm 정렬이 영원히 안 된다 ③ 박스가 없으면 0.5 s 에 LOST, BUSY 지연 0.5 s 와 겹친다 |
| E13 | 데이터 축소 (**재검 r1**) | `CallTag`·`GripRequest` 를 없애고 `GripCall` 하나에 모은다. `is_current` 삭제(E8) | 호출 한 건에 dataclass 5개는 많다. 초급 개발자 설명 부담 |
| E14 | 로그 칸 모양 (**재검 r1**) | `gripper` 레코드는 **키를 항상 전부** 쓰고 없는 값은 null. `verdict` 는 CLOSE·VERIFY 에만, OPEN 은 null | 집계(jq·pandas)에서 키 유무 분기가 없게. OPEN 응답에 `NOT_HELD` 가 찍혀 실패처럼 읽히지 않게 |

## 1. `grip.py` (새, 순수 — ROS 를 import 하지 않는다)

### 1.1 상수
| 이름 | 값 | 뜻 |
|---|---|---|
| `OPEN`·`CLOSE`·`VERIFY` | 문자열 | 호출 종류 (FSM 행동 `GRIPPER_OPEN/CLOSE/VERIFY` 와 1:1) |
| `CODES` | `("OK","TIMEOUT","INVALID","BUSY","COMM_ERROR")` | Gripper.srv message 계약 |
| `UNKNOWN`·`UNAVAILABLE` | 문자열 | 계약 밖 코드 / 서비스 없음 (belt_servo 가 만드는 코드) |
| `BUSY_RETRY_MAX` | 1 | BUSY 재요청 횟수 (D3) |
| `BUSY_RETRY_DELAY_S` | 0.5 | BUSY 뒤 재요청까지 기다림 (E1, 판단값) |
| `PENDING`·`REPLY`·`BUSY_WAIT`·`RETRY`·`TIMED_OUT` | 문자열 | poll 결과 종류 |

### 1.2 데이터
| 이름 | 필드 | 비고 |
|---|---|---|
| `GripCall` (frozen) | `goal_id: str`, `attempt: int`, `kind: str`, `seq: int`, `width_mm`, `force_n`, `sent_s: float`, `busy_retries: int = 0`, `busy_at: float \| None = None` | 진행 중 호출 한 건 = 이름표 + 보낸 값. `seq` = goal 안 그리퍼 요청 순번(1부터, BUSY 재요청도 +1). `busy_at` = BUSY 응답을 받은 시각(재요청 대기 중) |
| `RawReply` (frozen) | `ok`, `width_mm`, `grip_detected`, `message: str` | srv 응답을 ROS 없이 옮긴 것 |
| `PollResult` (frozen) | `status`, `reply: fsm.GripperReply \| None`, `code: str`, `raw_message: str` | `reply` 는 REPLY·TIMED_OUT 때만 |

### 1.3 함수
| 함수 | 입력 → 출력 | 규칙 |
|---|---|---|
| `request_for(action, pre_open_mm, grasp_width_mm)` | FSM 행동 → `(kind, width_mm)` | OPEN → pre_open, CLOSE·VERIFY → grasp_width(D1). 모르는 행동 → `ValueError` |
| `message_code(message)` | str → 코드 | 콜론 앞, 앞뒤 공백 제거, 대문자. `CODES` 에 없으면 `UNKNOWN` (빈 문자열 포함) |
| `new_call(goal_id, attempt, kind, width_mm, force_n, seq, now)` | → `GripCall` | busy_retries 0, busy_at None |
| `busy_marked(call, now)` | → `GripCall` | busy_at = now (재요청 대기 시작) |
| `retried(call, now)` | → `GripCall` | seq +1, busy_retries +1, sent_s = now, busy_at None, 나머지 같음 |
| `poll(call, done, raw, failed, now, timeout_s)` | → `PollResult` | ⓪ `busy_at` 있음(재요청 대기) → `now − busy_at ≥ BUSY_RETRY_DELAY_S` 면 RETRY, 아니면 PENDING ① done 이고 failed(예외) → REPLY, code COMM_ERROR ② done → code = message_code. BUSY 이고 busy_retries < BUSY_RETRY_MAX → BUSY_WAIT. 그 밖 → REPLY(`GripperReply(ok, width, grip, code)`) ③ 안 끝났고 `now − sent_s > timeout_s` → TIMED_OUT(`GripperReply(False, 0.0, False, "TIMEOUT")`) ④ 그 밖 PENDING. **경계: 정확히 timeout_s 면 아직 PENDING, 정확히 지연 0.5 s 면 RETRY** |
| `unavailable_reply()` | → `GripperReply(False, 0.0, False, UNAVAILABLE)` | D5 |
| `descend_time_s(dist_m, descend_speed, a_max, kp_z, tol_m)` | → s | E5. 속도·가속·게인·허용치 ≤ 0 이면 `ValueError`(기동 검사가 막으므로 방어용) |
| `grasp_room_ok(tcp_x, x_max, belt_speed, need_s, margin_m)` | → bool | `x_max − tcp_x ≥ belt_speed × need_s + margin_m` 이면 True. **같으면 True** |
| `call_record(call, state, now, reply=None, code=None, raw=None, verdict=None)` | → dict | 로그용(아래 4절). 키는 항상 전부(E14) |

## 2. `fsm.py` 수정 (작게)

- `TickEvent` 에 `grasp_room: bool = True` 추가 (기본 = 여유 있음 → U1·U2 시험 그대로 통과).
- `_advance` 의 TRACK 줄:
  ```
  TRACK + aligned + grasp_room      → DESCEND        (기존 11번)
  TRACK + aligned + not grasp_room  → 끝 OUT_OF_REACH, cause "REACH_GRASP_ROOM"   (새 11b)
  ```
- 다른 줄은 그대로. 취소·그리퍼 실패·입력·영역 검사(1~9)가 먼저라 우선순위도 그대로.
- 상수 `REACH_GRASP_ROOM = "REACH_GRASP_ROOM"`.

## 3. `belt_servo.py` 수정

### 3.1 GoalCtx 새 필드
| 필드 | 타입 | 뜻 |
|---|---|---|
| `grip_call` | `GripCall \| None` | 지금 기다리는 호출 (없으면 None). BUSY 재요청 대기 중에도 남아 있다(`busy_at`) |
| `grip_future` | rclpy Future \| None | 그 호출의 진동벨. 응답을 소비했으면(BUSY 대기 포함) None |
| `grip_seq` | int = 0 | 이 goal 에서 보낸 요청 수 |
| `grip_ready_reply` | `GripperReply \| None` | 요청 순간 만들어진 응답(UNAVAILABLE) — 다음 틱에 FSM 으로 |
| `grip_log` | dict \| None | 로그 `gripper` 칸 (E7) |

노드 필드: `self.grip_late_discarded = 0` (E8).

### 3.2 함수
| 함수 | 하는 일 | 에러 경로 |
|---|---|---|
| `_handle_actions` | `GRIPPER_*` → `_request_gripper`, `REQUEST_STOP` → 기존 | — |
| `_request_gripper(ctx, action, now)` | `grip.request_for` → `new_call`(seq = `grip_seq + 1`, attempt = **전이 후** `ctx.state.attempts`) → `_send_gripper` | — |
| `_send_gripper(ctx, call, now)` | `ctx.grip_seq = call.seq`(BUSY 재요청 순번도 반영, r2) → 서비스 없으면 보내지 않고 `grip_ready_reply = unavailable_reply()` + 로그 기록 + 기다리는 호출 비움 → 있으면 `call_async(Gripper.Request(width, force))`, ctx 에 보관(콜백은 달지 않는다, E8). **처음 요청·BUSY 재요청이 같은 함수** | 서비스 없음 = D5 (재요청 때도, r2) |
| `_poll_gripper(ctx, now)` → `GripperReply \| None` | `grip_ready_reply` 가 있으면 꺼내 돌려줌 → `grip_call` 없으면 None → future 상태를 `RawReply` 로 옮겨 `grip.poll` → PENDING: None · BUSY_WAIT: WARN 로그, `grip_call = busy_marked`, `grip_future = None` → None · RETRY: `_send_gripper(retried)` → None · REPLY: `grip_call=None`, 로그 기록, INVALID 이면 ERROR "gripper 설정 오류(폭·힘) — message=<원문>", reply 반환 · TIMED_OUT: `_orphan_gripper` 뒤 REPLY 와 같이 | future.result() 예외 → failed=True (E3) |
| `_orphan_gripper(ctx)` | `grip_future` 가 있으면 `add_done_callback(_on_grip_late(call))` 을 달고 ctx 의 `grip_call`·`grip_future` 를 비운다 (이미 끝난 future 면 콜백이 곧바로 불린다) | — |
| `_on_grip_late(call, fut)` (done 콜백) | `grip_late_discarded += 1`, INFO "gripper_late_discarded goal=… attempt=… kind=… seq=… code=… message=…" | 콜백 예외는 잡아서 로그만 |
| `_build_event` | stopping 이 아니면 `gripper=self._poll_gripper(...)` (E2), `grasp_room` = `geo` 가 있으면 `grip.grasp_room_ok(geo.tcp[0], cfg.x_max, ‖cfg.belt_v‖, t_desc + close_time_max, margin)`, 없으면 True | — |
| `_tick_values`·`_snapshot_values` | `gripper` 칸 = `ctx.grip_log` (스냅샷은 `_last_goal["gripper"]`) | — |
| `_finish` | `_last_goal` 에 `gripper: ctx.grip_log` 추가. 진행 중 호출이 있으면 `_orphan_gripper(ctx)` — 호출 자체는 취소하지 않고 응답이 오면 버린다(D7) | — |

- **PR #130(U2 세션, 열림)과의 경계**: `main()`·`destroy_node()`·`_finish_on_shutdown()` 은 U5 가 고치지 않는다. 노드 종료 중 goal 은 #130 이 `_finish(DEVICE_ERROR, "NODE_SHUTDOWN")` 으로 끝낸다 → U5 의 `_finish` 변경(`_last_goal["gripper"]`)이 그 경로에도 그대로 적용되고, 진행 중 그리퍼 호출은 D7 대로 그대로 둔다(종료 때 새 그리퍼 요청 없음). `NODE_SHUTDOWN` 은 reason 매핑에서 DEVICE_ERROR 의 cause 로만 쓰며 grip 쪽 코드 이름과 겹치지 않는다(`GRIPPER_*`·`REACH_GRASP_ROOM`). #130 이 먼저 머지되면 바로 main 을 rebase 한다(test_node.py 끝 추가끼리라 충돌 작음).
- 단일 스레드 executor(`rclpy.spin`, DEC-14)라 done 콜백과 틱이 동시에 돌지 않는다 → 잠금 불필요. 순서(콜백이 틱보다 먼저인지)에는 기대지 않는다(E8).
- `t_desc + close_time_max` 는 READY 때 한 번 계산해 `self._room_need_s` 에 둔다. `t_desc` 입력 = (approach_dz − grasp_dz, descend_speed, a_max, kp_z, height_tol) — 모두 U2 `ControlConfig` 에 있다.
- 기존 docstring 의 "gripper 는 U5"·"호출은 U5" 문구는 정리한다.

### 3.3 phase 전이와 호출 (예: 정상)
```
틱 n   : _execute → start() → GRIPPER_OPEN → _request_gripper(seq1, OPEN, attempt 0)
틱 n+k : _poll_gripper → REPLY(OK) → ev.gripper → PREPARE→TRACK
...    : TRACK + aligned + grasp_room → DESCEND
...    : DESCEND + at_grasp_height → GRASP, attempts 1, GRIPPER_CLOSE → seq2 CLOSE attempt 1
...    : REPLY(OK, grip, 40.9) → HELD → LIFT
...    : at_lift_height → VERIFY, GRIPPER_VERIFY → seq3 VERIFY attempt 1
...    : REPLY(OK, grip, 40.9) → HELD → 끝 OK grasped=true → 0 유지
```

## 4. 로그 `gripper` 칸 (틱·시도 공통, log_schema 필드 이름은 그대로)

```json
{"kind": "CLOSE", "attempt": 1, "seq": 2, "state": "REPLY",
 "sent_s": 12.301, "rx_s": 14.102, "latency_s": 1.801,
 "width_cmd_mm": 39.0, "force_n": 14.0,
 "ok": true, "width_actual_mm": 40.9, "grip_detected": true,
 "message": "OK", "code": "OK", "verdict": "HELD", "busy_retries": 0}
```
- `state`: `PENDING` | `BUSY_WAIT` | `REPLY` | `TIMED_OUT` | `UNAVAILABLE`. 키는 항상 전부 쓰고 모르는 값은 null(E14).
- `verdict`: CLOSE·VERIFY 만 `fsm.judge_grip(reply, w_min, w_max)[0]` (HELD | NOT_HELD | DEVICE_ERROR), OPEN 은 null(폭은 그대로 남아 빈손 폭 확인에 쓸 수 있다).
- `log_schema.py` 는 주석(필드 설명)만 고친다. 키 목록은 바뀌지 않는다.

## 5. 파라미터 (`params.py` · `config/belt_servo.yaml`)

| 이름 | kind | 단위 | 필수 | 개별 검사 | 기본 파일 |
|---|---|---|---|---|---|
| `gripper_timeout_s` | float | s | ✅ | > 0 | 3.0 (제안) |
| `grasp.close_time_max_s` | float | s | ✅ | > 0 | 2.1 (measurements-1008 #14) |
| `grasp.room_margin_mm` | float | mm | ✅ | ≥ 0 | 10.0 (제안) |
| `grasp.hold_width_min_mm` | (기존) | mm | | | null → 39.5 |
| `grasp.hold_width_max_mm` | (기존) | mm | | | null → 43.5 |

교차 검사(E9): `gripper_timeout_s > grasp.close_time_max_s` · `grasp.hold_width_max_mm < gripper.pre_open_mm` · `grasp.hold_width_min_mm > gripper.grasp_width_mm`.
yaml 주석: 폭 범위 근거(빈손 38.0~38.7 은 범위 아래, 0° 40.7~41.2, 회전 30° 까지 43.0), 닫힘 1.6~2.1 s, x 여유 식, 판단값은 "제안" 표기. `gripper_timeout_s` 옆에 "gateway `rg2_timeout_s` 6.0 — belt_servo 가 3 s 에 포기해도 RG2 자원은 최대 6 s 까지 잡혀 다음 요청이 BUSY 가 될 수 있다" 주석(재검 r1).
기본 파일은 여전히 null 키(Kp 등)가 있어 READY 거부 — 바뀌지 않는다.

## 6. 테스트 목록

### 6.1 `test_grip.py` (새, 순수) — 함수 19개 (parametrize 포함 수집 23)
1. `message_code`: `"OK"`→OK · `"INVALID: width 200"`→INVALID · `"COMM_ERROR: RG2 safety_err"`→COMM_ERROR · `" busy "`→BUSY · `""`→UNKNOWN · `"WHAT"`→UNKNOWN (parametrize 6)
2. `request_for`: OPEN 90 · CLOSE 39 · VERIFY 39 · 모르는 행동 ValueError (4)
3. `poll` PENDING(안 끝남, 시간 안) · 경계 정확히 timeout_s → PENDING · 초과 → TIMED_OUT(code TIMEOUT) (3)
4. `poll` REPLY OK(값 그대로, message=코드) · BUSY 첫 번째 → BUSY_WAIT · 대기 0.49 s → PENDING / 0.5 s → RETRY · BUSY 재요청 뒤 → REPLY(BUSY) · 예외 → REPLY(COMM_ERROR) (5)
5. `retried`·`busy_marked`: seq·busy_retries +1, sent_s 갱신, busy_at 비움, goal·attempt·kind·폭 그대로 (1)
6. (삭제 — `is_current` 없음, E8)
7. `descend_time_s`: (0.059, 0.05, 0.1, 2, 0.002) → 2.19 ± 0.01 · 짧은 거리(0.02 < d_p) → ln(10)/2 ≈ 1.15 (2)
8. `grasp_room_ok` 경계: 딱 같으면 True, 1 mm 모자라면 False (1)

### 6.2 `test_fsm.py` 추가 — 5개
1. TRACK + aligned + grasp_room False → OUT_OF_REACH `REACH_GRASP_ROOM`, 행동 없음
2. TRACK + aligned + grasp_room True → DESCEND (기본값으로도)
3. grasp_room False 는 TRACK 밖(PREPARE·DESCEND·GRASP)에서 무시
4. code 기반 실패: GripperReply(False, …, "BUSY"/"UNAVAILABLE"/"TIMEOUT") → DEVICE_ERROR `GRIPPER_BUSY`/`GRIPPER_UNAVAILABLE`/`GRIPPER_TIMEOUT` (parametrize)
5. **종료 전이에는 행동이 없다**: 모든 terminal 경로(OK·GRASP_FAILED·DEVICE_ERROR·OUT_OF_REACH·LOST·STALE·CANCELED·stop 실패)에서 `actions == ()` (parametrize) — "grasped=false 면 개방 없음"의 FSM 쪽 보장

### 6.3 `test_params.py` 추가 — 5개
새 키 미전달 → missing · timeout ≤ close_time_max → invalid · hold_max ≥ pre_open → invalid · hold_min ≤ grasp_width → invalid · `config/belt_servo.yaml` 의 hold 39.5·43.5·close 2.1·timeout 3.0·margin 10 (파일 읽기)

### 6.4 `test_node.py` 수정·추가 — 6개
- `READY_ARGS` 에 새 키 3개 추가, hold_width_max 41.5 → 43.5.
- 가짜 future 로(spin 없이): ① 서비스 없음 → 다음 poll 이 UNAVAILABLE 응답 ② goal 이 끝날 때 진행 중이던 호출 → 고아 → 그 future 가 나중에 끝나면 카운터 +1, 새 goal 의 `_poll_gripper` 는 그 응답을 보지 않음 ③ BUSY → 0.5 s 대기 뒤 재요청(seq +1), 다음 CLOSE 는 seq 3 ④ stopping 중에는 poll 안 함 ⑤ (r2) BUSY 대기 중 서비스가 사라지면 재요청하지 않고 바로 UNAVAILABLE ⑥ 시간초과 뒤 늦은 응답 버림

### 6.5 `test_action_e2e.py` (가짜 gateway 확장) — 지시서 4 케이스 + 4개
가짜 gateway: `FakeClient` 에 **pose 적분**(받은 servo_cmd 속도로 50 Hz 위치 갱신, 시작 TCP (0, 0, 0.2)) + 30 Hz 박스(움직임: 벨트 속도 / 정지, 윗면 z 0.16) 옵션. 움직이는 시험은 `control.kp_per_s:=1.5`(E12). 가짜 그리퍼 `FakeGripper` 노드(별도 스레드 executor, E11): 종류별 시나리오 `{OPEN: …, CLOSE: …}` = (지연 s, ok, width, grip, message), 받은 요청 목록 기록.

| 시험 | 시나리오 | 기대 |
|---|---|---|
| **① 정상** | 개방 OK · 닫기 OK grip 40.9 · 확인 OK grip 40.9 | SUCCEEDED, OK, grasped=true, attempts 1 · feedback `PREPARE,TRACK,DESCEND,GRASP,LIFT,VERIFY` · 그리퍼 요청 `[90, 39, 39]` · `grip_late_discarded == 0` · 마지막 cmd 0 |
| **② 빈손** | 닫기 OK grip=false 38.4 | ABORTED, GRASP_FAILED, cause NOT_DETECTED, attempts 1 · 그리퍼 요청 `[90, 39]` (**개방 재요청 없음**) · 0.6 s 더 돌려도 요청 수 그대로 · `grip_late_discarded == 0` · 마지막 cmd 0 |
| **③ 늦은 응답** | `gripper_timeout_s` 0.5 · `grasp.close_time_max_s` 0.4 로 덮어씀(E9 때문에 같이), 닫기 지연 1.0 s | ABORTED, DEVICE_ERROR, cause GRIPPER_TIMEOUT · 1.0 s 뒤 응답 도착 → `grip_late_discarded == 1` · 요청 `[90, 39]` · 마지막 cmd 0 |
| **④ 정지 실패** | 닫기 지연 1.0 s, stop 서비스 실패 | GRASP 중 cancel → ABORTED, DEVICE_ERROR, cause STOP_FAILED_TIMEOUT · 늦은 닫기 응답 버림 · 요청 `[90, 39]` · 마지막 cmd 0 |
| ⑤ BUSY 1회 | 정지 박스, stop 정상, 개방 첫 응답 BUSY, 두 번째 OK | 요청 `[90, 90]`, 두 요청 간격 ≥ 0.45 s, `grip_log.busy_retries == 1`·`seq == 2`, feedback 에 TRACK → 취소해 CANCELED 로 정리(r2: 진행 중 goal 을 남기지 않게) |
| ⑥ BUSY 2회 | 정지 박스, 개방 BUSY 계속 | DEVICE_ERROR `GRIPPER_BUSY`, 요청 `[90, 90]` |
| ⑦ INVALID | 개방 `"INVALID: width"` | DEVICE_ERROR `GRIPPER_INVALID` |
| ⑧ 서비스 없음 | 가짜 그리퍼 안 띄움 | DEVICE_ERROR `GRIPPER_UNAVAILABLE` |
| ⑨ x 여유 부족 (r2) | 움직이는 박스, `reach.x_max_mm` 200 | OUT_OF_REACH `REACH_GRASP_ROOM`, phase TRACK 에서 끝, feedback `[PREPARE, TRACK]`, 요청 `[90]`, 마지막 cmd 0 |

기존 시험(LOST·취소 3종·예외·PREPARE 추종)은 기본 가짜 그리퍼(즉시 OK)로 그대로 통과해야 한다.
**합계 예상: 기존 129 + 약 41 (19 + 5 + 5 + 4 + 8) = 약 170.** e2e 파일 실행 시간 +15~20 s 예상. **실제(S4, 10/10): 189 passed** — parametrize 로 늘어남, e2e 14개 34 s, 3회 반복 모두 통과. **재검 r2 반영 후: 191 passed**(test_grip 23·test_node 18·e2e 15·test_fsm 46·test_params 33 수집 + 나머지), e2e 15개 37 s, 3회 반복 모두 통과.

## 7. dry_run 스모크 (S5, **선택** — 커밋 안 함, scratchpad)

완료 기준 "OK·grasped=true 1회"는 6.5 ① e2e pytest 로 충족한다(지시서 정리 10/09). 아래는 실제 gateway 코드와의 연결 확인용 선택 단계다. U3 sim.launch·sim_check 가 먼저 머지되면 그것으로 대신한다.

| 항목 | 내용 |
|---|---|
| 빌드 | 워크트리에서 `colcon build --packages-select voss_msgs voss_robot voss_servo` (ws_dsr source) |
| gateway | `voss-ros ros2 launch voss_robot robot_gateway.launch.py dry_run:=true dry_run_object_mm:=40.5 config:=<워크트리>/config/voss_config.yaml` — 가짜 로봇은 관측 자세(TCP z ≈ 0.2035 m)에서 시작 |
| belt_servo | `voss-ros ros2 run voss_servo belt_servo --ros-args --params-file <scratchpad>/belt_servo_smoke.yaml` — 기본 yaml 복사 + null 에 제안값(`control.kp_per_s` 는 0 보다 크게, E12) + voss_config 값(belt·gripper·timing) 직접 기입 |
| 박스 | scratchpad `box_feed.py`: 첫 `/voss/robot/pose` 를 읽고 박스를 TCP 보다 50 mm 상류, 윗면 z 0.101 m(파지 TCP z ≈ 82 + 19, measurements-1008 #14) 에서 `direction_base × 0.048 m/s` 로 30 Hz 발행, SOURCE_HAND_EYE |
| goal | `voss-ros ros2 action send_goal /voss/servo/track_and_grasp voss_msgs/action/TrackAndGrasp "{track_id: 1}" --feedback` |
| 확인 | object 40.5: OK·grasped=true, feedback 6단계 순서, 틱 로그 마지막·0 유지 cmd 0, gateway 로그 gripper 요청 90→39→39 · object 0: GRASP_FAILED(NOT_DETECTED), gateway 로그에 그 뒤 gripper 요청 없음 |
| 정리 | 띄운 프로세스 모두 종료, 로그는 scratchpad 에 남김 |
| **선행 (재검 r1)** | 현재 `DryRunRg2` 는 VERIFY 재닫기(39)에서 `39 < 40.5 < 40.5` 가 거짓이라 grip=false → DROPPED → GRASP_FAILED. object 40.5 → OK 경로는 gateway `rg2.py` 의 조건을 `<=` 로 바꾸는 학민 수정(담당 밖 요청, 회신에 적음)이 있어야 한다. 그 전에는 object 40.5 경로가 GRASP→LIFT→VERIFY 까지 가서 DROPPED 로 끝나는 것까지만 확인 가능 — 완료 기준에는 영향 없음(e2e 로 충족) |

### 7.1 S5 결과 (10/10, 개인 PC 도메인 34, main gateway dry_run)
| 회 | 조건 | feedback | 결과 | 그리퍼 요청(gateway 로그) | 확인 |
|---|---|---|---|---|---|
| 1 | object 40.5, 박스가 goal 3.8 s 전부터 흐름(스크립트 타이밍 탓 — 시작 오차 +133 mm 하류) | 6단계 전부 | GRASP_FAILED / DROPPED | 90 → 39(grip, 40.5) → 39(**grip 없음 39.0** — DryRunRg2 재닫기 `40.5 < 40.5`, 예상대로) | 정렬 5.6 s 뒤 x 400 mm 에서 DESCEND(여유 한계 404 mm 통과), 30 Hz(평균 33.3 ms), 마지막 0, 0.7 s 뒤 watchdog move_stop 1회, 자름·거부 0 |
| 2 | object 없음, 박스 발행과 goal 을 붙임(50 mm 상류 시작) | PREPARE→TRACK→DESCEND→GRASP | GRASP_FAILED / NOT_DETECTED | 90 → 39(grip 없음) **끝 — 개방 요청 없음** | 정렬 2.0 s, DESCEND x 88.7 mm, 하강 2.14 s(식 2.19 s), 마지막 0, watchdog move_stop 1회 |

로그·스크립트는 scratchpad(`s5/`)에만 둔다(커밋 안 함).

## 8. 변경 기록
- 2026-10-09: 초안 (작업 세션 U5). 같은 날 PR #130(NODE_SHUTDOWN) 경계 추가.
- 2026-10-10: 재검 r2(최종, 독립 서브에이전트·직접 실행) 반영 — BUSY 재요청 뒤 `grip_seq` 동기화(순번 중복 버그), 재요청 때도 서비스 없음 검사(`_send_gripper` 로 합침), e2e ⑤ 취소로 정리, e2e ⑨ x 여유 노드 경로, 시험 개수. 불수용: "rclpy 가 done 콜백을 즉시 부른다" 정정 — Jazzy `executors.py:508` 이 `future._set_executor(self)` 뒤 `set_result` 하므로 executor 태스크로 미뤄진다(E8 근거 그대로 맞음).
- 2026-10-09: 재검 r1(독립 서브에이전트) 반영 — E1 BUSY 지연, E5 하강 시간 식 정정, E8 고아 때만 콜백, E9 hold_min 검사, E11 정리 순서, E12~E14 신설, 6·7절 시험·스모크 갱신.
