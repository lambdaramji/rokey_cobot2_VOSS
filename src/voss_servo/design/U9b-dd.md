# U9-b 재시도 재접근 + 안전 후퇴 — Detail design

- 이슈: #37 (T28) · 브랜치 `feat/37-voss_servo-u9b-retry` (베이스 U9-a **f01750c**, 10/12 리베이스) · 작성 2026-10-12
- 상태: **DD 승인(박병후, 10/12) → 재검 r1 반영본 재승인(10/12)**. 앞: [U9b-hld.md](U9b-hld.md). 다음: [U9b-pseudo.md](U9b-pseudo.md).
- HLD 뒤 결정(사용자 10/12): 후퇴 중 pose 끊김 → **STALE_INPUT/POSE_MISSING**(지금 규칙 6 그대로).
  주관 요청(10/12): 후퇴 시간 상한·x 가드·취소 즉시 0·로그 키·개방 무응답 처리.
- **r1 변경 요약**(9절에 근거): ① sim `retry` 기하 정정(kp 3 + 시작 −250 + 닫힘 1.2 s) ② LIFT 체류 상한은 **후퇴에만**, 정상 들기는 경고 로그 ③ 개방 대기(hold_z)에 상한 — 2.3 s 또는 x_max 면 상승 ④ 폭 밖은 **항상 후퇴**(재시도 분기 삭제 — x_f ≤ 115 라 도달 불가) ⑤ `retry_room` 기본 False ⑥ `RETREAT_CLEAR_MM` 5 → 10 ⑦ 재시도 여유 판정을 순수 함수로 ⑧ 시험·담당 밖 항목 보강.

## 0. 바뀌는 것 한눈에

```
                 ┌ 상수 ──────────────────────────────────────────────────────────────┐
params.py   ───▶ │ RETREAT_CLEAR_MM = 10.0 (핑거 끝이 박스 윗면을 이만큼 넘으면 xy 0)  │
                 └────────────────────────────────────────────────────────────────────┘
                 ┌ 판정 (fsm.py) ──────────────────────────────────────────────────────┐
fsm.py      ───▶ │ FsmState + exit_reason · exit_cause · hold_z                       │
                 │ TickEvent + retry_room · hold_expired · lift_overstay              │
                 │ Transition + retry_room_ok · retreat_done (로그용)                 │
                 │ _not_held 재작성 · 5번(그리퍼 오류) 분기 · 9c(후퇴 체류 상한)        │
                 │ _advance: 후퇴 진행(개방 대기 해제·들기 높이에서 끝)                │
                 └────────────────────────────────────────────────────────────────────┘
                 ┌ 제어 (control.py) ──────────────────────────────────────────────────┐
control.py  ───▶ │ z_plan(…, hold_z) · retreat_xy · command(…, retreat, hold_z)        │
                 │ retry_need_s · lift_max_s · retry_room_ok(tcp_x | None, …)          │
                 └────────────────────────────────────────────────────────────────────┘
belt_servo  ───▶ 기동 때 시간 2개 계산·로그 · _build_event 3필드 · lift_since·hold_since
                 · 정상 LIFT 체류 초과 WARN 1회 · 로그 4키
log_schema  ───▶ TICK·ATTEMPT 키 4개 (retreat · retreat_reason · retreat_done · retry_room_ok)
                 ┌ sim ───────────────────────────────────────────────────────────────┐
fake_gripper ──▶ │ 새 노드: 계획표대로 빈손·쥠·폭 밖 응답, 닫힘·개방 지연               │
sim.launch  ───▶ │ 인자 gripper·grip_plan·grip_close_s·max_attempts·box_start_x_mm      │
sim_check   ───▶ │ case retry · fail_retreat · wide · (empty 기대값 수정) · J-ret       │
                 └────────────────────────────────────────────────────────────────────┘
```
바꾸지 않는 것: reason 7종·phase 6종·action 필드, `grip.py`(함수 재사용만), `input_flags`·`is_vision_blind`·`blind_since_next`,
`max_attempts` 기본 1, yaml 키 목록(새 키 없음), gate_summary, docs/interfaces, src/voss_robot.

## 1. 값·상수

| 이름 | 위치 | 값 | 뜻 · 근거 |
|---|---|---|---|
| `RETREAT_CLEAR_MM` | params.py | **10.0** | 후퇴 중 보정 TCP z 가 박스 윗면 + 10 mm 를 넘으면 xy 0. 보정 TCP 는 마지막 z 명령으로 외삽돼 실제보다 몇 mm 앞설 수 있다(sim pose_lag 60 ms × 80 mm/s ≈ 5 mm) → 5 가 아니라 10. 비용은 FF 0.1 s(x +5 mm) |
| (재사용) `BLIND_DWELL_MARGIN_S` | params.py | 1.0 | 후퇴 체류 상한 여유에도 같은 값(주관 요청 1, U9-a S 와 같은 꼴). 주석 1줄 |
| `retry.max_attempts` | yaml 3종 | 1 (그대로) | 재정렬형 재시도는 현장 정렬 x(85~91)에서 x 여유가 없어 켜도 후퇴로 간다. 켜면 달라지는 것은 "1차 실패 x ≤ 225 인 박스만 재시도"뿐이고 실기 검증이 없다. **T28 '재시도 포함'은 sim 으로만 입증**(회신에 명시). 현장 증거는 GRASP_FAILED 행의 `retry_room_ok` 로 쌓인다 |

계산값(시연 설정: kp_z 1.5, 상승 0.08, 하강 0.05, 가속 0.1, tol 2, 접근 +40, 들기 +50, 파지 −19, 벨트 48 mm/s, close_max 2.3, 여유 10):

| 값 | 식 | 결과 |
|---|---|---|
| 재상승 예상 | `grip.descend_time_s(approach_dz − grasp_dz, lift_speed, a_max, kp_z, tol)` (59 mm) | 2.66 s (시뮬 2.53~2.57) |
| `retry_need_s` | 재상승 예상 + `_room_need_s`(하강 2.64 + 닫힘 상한 2.3) | **7.60 s** → 필요 x 365 + 10 = 375 mm → **실패 x ≤ 225 mm**. 2차 실패 뒤 후퇴의 FF 구간(≈0.7 s·32 mm)과 FF→0 감속(≈12 mm)은 넣지 않는다 — x 가드(`retreat_xy`)가 x_max 에서 xy 를 끊어 최악 x ≈ 612(gateway 638 안). 최종 재검 MINOR-2, 스모크 `empty,empty,held` 에서 2차 실패 x 552 → 후퇴 끝 x 594 |
| `lift_max_s` | `grip.descend_time_s(lift_dz − grasp_dz, lift_speed, …)` + 1.0 (69 mm) | 2.785 + 1.0 = **3.78 s** (후퇴 상한. 정상 LIFT 2.70~2.74 에는 경고만. 최종 재검 MINOR-1: 반올림 합 3.79 → 계산값 3.785, 기동 로그 "3.78 s") |
| 개방 대기 상한 | `close_time_max_s` | **2.3 s** (개방 시간 미측정 — 닫힘 상한을 대용) |

## 2. fsm.py

### 2.1 상태·이벤트 필드 (기존 생성 코드가 돌도록 기본값을 붙인다)

| 자료형 | 새 필드 | 형·기본 | 뜻 |
|---|---|---|---|
| `FsmState` | `exit_reason` | `str \| None = None` | 후퇴 중이면 끝에 보낼 reason(`GRASP_FAILED`·`DEVICE_ERROR`). None = 후퇴 아님 |
| | `exit_cause` | `str = ""` | 그때의 cause. 여러 틱에 걸쳐 기억해야 해서 상태에 둔다(Transition.cause 는 그 틱만) |
| | `hold_z` | `bool = False` | 개방 응답 전까지 높이 유지(폭 밖 후퇴) |
| `TickEvent` | `retry_room` | `bool = False` | 지금 TCP x 에서 재시도 1회를 끝낼 x 여유. **기본 False** — 모르면 재시도 안 함(안전 쪽, 노드와 같은 규칙) |
| | `hold_expired` | `bool = False` | 개방 대기가 상한(2.3 s)을 넘었거나 TCP x ≥ x_max |
| | `lift_overstay` | `bool = False` | LIFT 상승 체류가 상한을 넘었나 |
| `Transition` | `retry_room_ok` | `bool \| None = None` | GRASP NOT_HELD 를 판단한 틱에만 값 (로그) |
| | `retreat_done` | `bool = False` | 후퇴가 들기 높이 도달로 끝난 틱 (로그) |
| 상수 | `RETREAT_TIMEOUT` | cause | 9c |

- "후퇴" = `phase == LIFT and exit_reason is not None` → `is_retreat(state)`.
- feedback phase 는 LIFT(계약 6종 안. 주관 확인: sort_manager 는 phase 를 로그 문구에만 씀), 로그는 `retreat` 키로 구분.

### 2.2 새 순수 함수

| 함수 | 입력 | 출력 | 규칙 |
|---|---|---|---|
| `is_retreat(state)` | | bool | `phase == LIFT and exit_reason is not None` |
| `is_low(state)` | | bool | 그리퍼 오류 때 그 자리 정지가 위험한가: `GRASP` · `PREPARE ∧ attempts ≥ 1`(재시도 상승 중) · 후퇴 중 |
| `lift_since_next(prev, state, now)` | 전이 **전** state | float\|None | `phase == LIFT and not hold_z` 이면 prev 없을 때만 now, 아니면 prev. 그 밖 None |
| `lift_overstay(lift_since, now, limit_s)` | | bool | `lift_since·limit 있음 ∧ now − lift_since > limit` |
| `_retreat(state, reason, cause, open_first, room_ok)` | | Transition | `phase=LIFT, exit_reason, exit_cause, hold_z=open_first`, 행동 `(GRIPPER_OPEN,)` if open_first. terminal 아님 |

### 2.3 `_not_held(state, cause, max_attempts, ev)` 재작성 (전이표 14·15 대체)

| 순서 | 조건 | 결과 |
|---|---|---|
| a | `phase == VERIFY` (DROPPED) | **끝 GRASP_FAILED/DROPPED** — 이미 들기 높이, 재정렬까지 x 363 mm 필요라 재시도 불가 |
| b | `cause == WIDTH_OUT` | **후퇴(먼저 개방)** — 재시도하려면 실패 x ≤ 115 mm 여야 해 현장·sim 모두 도달 불가 → 분기를 두지 않는다(r1) |
| c | `attempts < min(max_attempts, 3)` ∧ `ev.retry_room` | PREPARE + `GRIPPER_OPEN`, `attempt_ended`, `retry_room_ok=True` (지금 재시도와 같음) |
| d | 그 밖 (시도 다 씀 · 여유 없음) | 후퇴(닫힌 채) → GRASP_FAILED, `retry_room_ok = ev.retry_room` |

### 2.4 step() 전이표 (바뀌는 줄)

| 순서 | 조건 | 결과 | 변경 |
|---|---|---|---|
| 1~3 | stopping | stop 응답 대기 → CANCELED / DEVICE_ERROR | 그대로 — 후퇴 중 취소도 여기 (주관 2) |
| 4 | 취소 | stopping + REQUEST_STOP (명령은 command 첫 줄에서 0) | 그대로 |
| **5** | 그리퍼 판정 DEVICE_ERROR | `is_low` 면 **닫힌 채 후퇴, exit DEVICE_ERROR/GRIPPER_<코드>** (후퇴 중이면 exit 를 덮고 hold_z 해제) · 아니면 끝 DEVICE_ERROR | 바뀜 (Q2 + 주관 4) |
| 6 | pose_stale | 끝 STALE_INPUT/POSE_MISSING | 그대로 — 후퇴 중이어도 (사용자 10/12) |
| 7·8 | 비전 단계 ∧ 사각 아님 | STALE_INPUT / LOST | 그대로 |
| 9 | REACH_PHASES ∧ reach | OUT_OF_REACH | 그대로 — LIFT 는 대상 아님. x 가드는 제어(3절) |
| 9b | DESCEND ∧ blind_overstay | DEVICE_ERROR/DESCEND_BLIND_TIMEOUT | 그대로 (U9-a) |
| **9c** | **후퇴 ∧ lift_overstay** | **끝 DEVICE_ERROR/RETREAT_TIMEOUT** | 새 — 후퇴에만(r1). 정상 LIFT 는 전이 없음 |

`_advance` 바뀌는 줄 (후퇴 블록은 "LIFT ∧ at_lift → VERIFY" 줄보다 **앞**):

| 조건 | 결과 |
|---|---|
| 후퇴 ∧ hold_z ∧ (그리퍼 응답 ∨ `ev.hold_expired`) | hold_z=False (상승 시작). 응답이 없는 채 풀렸으면 개방 호출은 계속 기다린다 — 늦게 OK 가 오면 무시, TIMEOUT 이면 5번이 exit 를 DEVICE_ERROR 로 |
| 후퇴 ∧ hold_z | 그대로 (z 유지, xy FF) |
| 후퇴 ∧ at_lift_height | 끝 exit_reason/exit_cause, `retreat_done=True` |
| 후퇴 | 그대로 (상승 중) |
| LIFT(후퇴 아님) ∧ at_lift_height | VERIFY + GRIPPER_VERIFY (그대로) |
| GRASP·VERIFY ∧ NOT_HELD | `_not_held(…, ev)` |

- 후퇴 중 개방 응답의 판정(NOT_HELD 등)은 `_not_held` 로 가지 않는다 — 후퇴는 phase LIFT 라 GRASP·VERIFY 조건에 안 맞는다(재검 확인).
- **개방 대기 창(r1, 재검 MAJOR-3)**: 개방 응답이 2.3 s 안에 안 오거나 x_max 에 닿으면 열렸든 아니든 올라간다. 파지 높이에서 핑거를 멈춘 채 기다리는 것이 이 단위가 없애려던 위험이기 때문이다. 대가: 그리퍼가 아직 끼운 채면 박스를 낮게 들어 올릴 수 있음(Q2 "닫힌 채 후퇴"와 같은 판단).

### 2.5 상태 흐름 그림

```
             NOT_HELD(GRASP)                                NOT_HELD(VERIFY) ─► 끝 GRASP_FAILED/DROPPED
       ┌──────────┼───────────────────────────┐
  WIDTH_OUT   시도 남음 ∧ 여유            그 밖
       │          └─► PREPARE(재시도) ─► …     │
       ▼                                       ▼
  LIFT(후퇴, hold_z, GRIPPER_OPEN)        LIFT(후퇴, 닫힌 채)
       └ 개방 응답 ∨ 2.3 s ∨ x_max ─► 상승 ─┤
                                           ├─ 들기 높이 도달 ─► 끝 GRASP_FAILED/<cause> (retreat_done)
  그리퍼 오류(GRASP·재시도 PREPARE·후퇴 중) ─► exit=DEVICE_ERROR, 닫힌 채 상승 ─► … ─► 끝 DEVICE_ERROR
                                           ├─ 취소 ─► stop ─► CANCELED (즉시 0)
                                           ├─ pose 끊김 ─► 끝 STALE_INPUT (즉시 0)
                                           └─ 상승 > 3.78 s ─► 끝 DEVICE_ERROR/RETREAT_TIMEOUT
```

## 3. control.py

| 함수 | 바뀜 | 규칙 |
|---|---|---|
| `z_plan(phase, top_z, cfg, hold_z=False)` | 인자 추가 | `hold_z` 이면 `(None, 0, 0)` = z 속도 0. 그 밖 그대로. 후퇴는 phase LIFT 라 들기 높이(+50)로 위로만 |
| `retreat_xy(tcp, top_z, cfg)` 새 | — | `tcp_z < top_z + RETREAT_CLEAR_MM/1000 and tcp_x < cfg.x_max` → `FF`, 아니면 `ZERO` |
| `command(…, retreat=False, hold_z=False)` | 인자 추가 | 후퇴면 `retreat_xy`, 아니면 `xy_rule`. stopping·terminal·pose 없음 0 은 그대로(취소 즉시 0) |
| `retry_need_s(cfg, room_need_s)` 새 | — | 재상승 예상 + room_need_s |
| `lift_max_s(cfg)` 새 | — | 들기 예상 + `BLIND_DWELL_MARGIN_S` |
| `retry_room_ok(tcp_x, need_s, belt_speed, cfg, margin_m)` 새 | — | `tcp_x`·`need_s` 가 None 이면 **False**, 아니면 `grip.grasp_room_ok(tcp_x, cfg.x_max, belt_speed, need_s, margin_m)` (r1: 노드 메서드 대신 순수 함수 → 시험 가능) |

- xy FF → 0 전환은 가속 제한으로 약 0.48 s 감속(x +12 mm) — z ≠ 0 이라 `clamp` 의 "0 벡터 즉시" 규칙에 걸리지 않는다.

## 4. belt_servo.py (연결만)

| 곳 | 변경 |
|---|---|
| `__init__` | READY 면 `_retry_need_s = control.retry_need_s(cfg, _room_need_s)`, `_lift_max_s = control.lift_max_s(cfg)`. 기동 로그 2줄: "재시도 x 여유: 실패 때 x_max 까지 375 mm 이상 남아야 재시도 (실패 x ≤ 225)", "후퇴 체류 상한: … 3.78 s (정상 들기는 경고만)" |
| `GoalCtx` | `lift_since`, `hold_since`(hold_z 가 켜진 시각), `retry_room_ok`, `retreat_done`, `lift_warned`(정상 LIFT 경고 1회) |
| `_build_event` | `lift_since = fsm.lift_since_next(...)` · `hold_since` = hold_z 이면 (없을 때만 now) 아니면 None · `retry_room = control.retry_room_ok(tcp_x, _retry_need_s, …)` · `hold_expired = hold_since 있음 ∧ (now − hold_since ≥ close_time_max_s ∨ tcp_x ≥ x_max)` · `lift_overstay` |
| `_tick_goal` | `tr.retry_room_ok` 기록 · 끝날 때 `retreat_done` = `tr.retreat_done` 이면 True, 후퇴 중이었으면 False, 아니면 None · `command(..., retreat=is_retreat(tr.state), hold_z=tr.state.hold_z)` · **정상 LIFT 에서 lift_overstay 면 WARN 1회** ("들기 체류 {s} s > 상한 — 로봇 속도·펜던트 오버라이드 확인", 전이 없음) |
| `_tick_values`·`_finish`·`_snapshot_values` | 로그 4키 (5절) |

## 5. 로그 키 (log_schema.py, U9-c 방식: TICK_FIELDS·ATTEMPT_FIELDS 튜플에 이름·주석 추가)

| 키 | 틱 | 시도 | 값 |
|---|---|---|---|
| `retreat` | ✓ | ✓ | null \| `"OPENING"`(hold_z) \| `"RISING"` |
| `retreat_reason` | ✓ | ✓ | null \| 후퇴 끝에 보낼 reason |
| `retreat_done` | ✓ | ✓ | null(후퇴 없음) \| true(들기 높이 도달로 끝) \| false(후퇴 중 취소·pose 끊김·체류 초과로 끝) |
| `retry_room_ok` | ✓ | ✓ | null \| 마지막 GRASP 실패 때 재시도 x 여유 |

- result 의 reason·attempts·grasped 는 바뀌지 않는다(주관 3). cause 는 원래 판정 그대로.
- 옛 로그 호환: gate_summary·sim_check 는 `.get` 으로 읽는다(재검 확인). 키는 "grasped" 다음에 넣는다.

## 6. sim — 가짜 그리퍼와 케이스

gateway dry_run 가짜 RG2 는 물체 폭이 기동 때 고정이라 "1차 빈손 → 2차 쥠"을 못 만든다(지시서).

### 6.1 `fake_gripper` 노드 (새, voss_servo, sim 전용 — setup.py entry point)
- 서비스 `/voss/sim/gripper` (voss_msgs/Gripper). sim.launch 가 belt_servo 의 `/voss/robot/gripper` 를 `SetRemap` 으로 이 이름에 잇는다(재검 확인: GroupAction 안 include 의 Node 에도 적용). 인터페이스 변경 없음.
- 파라미터: `plan`(닫기 요청마다 하나: `empty`·`held`·`wide`, 다 쓰면 마지막 반복), `close_s` 1.7, `open_s` 1.0, `verify_s` 0.2, `pre_open_mm` 90.
- 순수 함수 `fake_reply(state, plan, width_req, pre_open_mm)`: 요청 폭 ≥ 60 → 개방 / 이미 닫힘 → 확인 재닫힘(결과 유지, 계획 소비 안 함) / 그 밖 → 계획표 다음. 폭: empty 38.4·grip False, held 41.0·True, wide 46.5·True.
- 지연은 콜백 안 sleep (별 프로세스·요청은 한 번에 하나라 belt_servo 와 무관 — 재검 확인).

### 6.2 sim.launch 인자 (기본값이면 지금과 똑같이 동작)
| 인자 | 기본 | 뜻 |
|---|---|---|
| `gripper` | `gateway` | `fake` 면 fake_gripper 기동 + remap |
| `grip_plan` | `held` | fake 계획 (쉼표 구분) |
| `grip_close_s` | 1.7 | fake 닫힘 지연 |
| `max_attempts` | (yaml 값) | `retry.max_attempts` 덮어쓰기 (kp 와 같은 덮어쓰기 파일) |
| `box_start_x_mm` | −100 | fake_box 시작 x |

### 6.3 sim_check 케이스 (Case 에 `grip_plan`·`grip_close_s`·`max_attempts`·`start_x_mm`·`kp`·`timeout_s` 추가, 기본 None = 지금 동작)

| case | 설정 | 기대 |
|---|---|---|
| `retry` | fake `empty,held`, 닫힘 **1.2 s**, max 3, **kp 3**, 박스 시작 x **−250**, 한계 60 s | SUCCEEDED · OK · grasped · **attempts 2** · phases = PREPARE TRACK DESCEND GRASP PREPARE TRACK DESCEND GRASP LIFT VERIFY |
| `fail_retreat` | fake `empty`, 닫힘 1.7, max 3, 나머지 기본 | ABORTED · GRASP_FAILED/NOT_DETECTED · attempts 1 · phases …GRASP LIFT · J-ret |
| `wide` | fake `wide`, 닫힘 1.7, max 3 | ABORTED · GRASP_FAILED/WIDTH_OUT · J-ret (fake 로그에 개방 1회) |
| `empty` (기존) | gateway object 0, max 1 | 기대값 수정: phases 마지막 **LIFT** + J-ret |

- **`retry` 기하(r1 정정, 재검 MAJOR-1)**: sim 정렬 x 는 하강이 아니라 **P 추격**이 정한다. 팔은 박스가 48/kp mm 상류에 올 때 따라가기 시작하고 오차가 3 mm 까지 줄어드는 데 ln(16)/kp s 가 걸려, kp 1 이면 박스 시작점과 무관하게 정렬 x ≈ 71~72(재계산: 시작 −100 → 72.5, −250 → 71.4. 10/12 sim 실측 79). 그래서 kp 3 + 시작 −250 → 정렬 x −2.4. 닫힘 1.2 s 로 1차 실패 x ≈ −2.4 + 48 × (2.64 + 1.2) ≈ 182 ≤ 225(여유 43) → 재정렬 ≈ 305 ≤ 352.9 → 2차 GRASP. 닫힘 1.7 이면 여유 19 mm 뿐이라 1.2 로 둔다(x 여유 판정 자체는 close_max 2.3 으로 하므로 판정 경로는 같다). 실행해서 값을 기대값 옆에 적는다.
- **J-ret**: 끝 틱 TCP z ≥ 박스 윗면 + 들기 − tol(+48 mm) ∧ `retreat_done` true.
- `Expect` 에 `attempts`·`retreat` 추가, J1 에 attempts 비교. `PROFILE_CASES["grasp"]` 에 세 케이스. pre_u5 실패(베이스부터)는 안 건드림.

## 7. 시험 목록

### 7.1 새 pytest

| 파일 | 시험 | 확인 |
|---|---|---|
| test_fsm | T1 재시도 여유 있음 | GRASP NOT_DETECTED, attempts 1 < 3, retry_room → PREPARE·OPEN·attempt_ended·retry_room_ok True |
| | T2 여유 없음 → 후퇴 | retry_room False → LIFT·exit GRASP_FAILED/NOT_DETECTED·행동 없음·terminal 아님·retry_room_ok False |
| | T3 시도 다 씀(max 1) → 후퇴 | |
| | T4 DROPPED 즉시 끝 | VERIFY NOT_HELD, 시도·여유 있어도 terminal GRASP_FAILED/DROPPED |
| | T5 폭 밖 → 항상 후퇴 | retry_room True·시도 남아도 → LIFT·hold_z·OPEN → 개방 응답 → hold_z False → at_lift → GRASP_FAILED/WIDTH_OUT·retreat_done |
| | T6 개방 대기 상한 | hold_z + hold_expired(응답 없음) → hold_z False, exit 그대로 |
| | T7 GRASP 닫힘 오류 → 후퇴 | 닫기 TIMEOUT → LIFT·exit DEVICE_ERROR/GRIPPER_TIMEOUT → at_lift → DEVICE_ERROR |
| | T8 후퇴 개방 무응답 | hold_z 중 TIMEOUT 응답 → hold_z False·exit DEVICE_ERROR |
| | T9 처음 PREPARE 그리퍼 오류 | attempts 0 → 즉시 DEVICE_ERROR (그대로) |
| | T10 재시도 PREPARE 그리퍼 오류 | attempts 1 → 후퇴 DEVICE_ERROR |
| | T11 후퇴 중 취소 | stopping → STOP_OK → CANCELED |
| | T12 후퇴 중 pose 끊김 | STALE_INPUT/POSE_MISSING |
| | T13 후퇴 체류 상한 | 후퇴 + lift_overstay → DEVICE_ERROR/RETREAT_TIMEOUT · 정상 LIFT + lift_overstay → 전이 없음 |
| | T14 후퇴는 x 끝으로 안 끊김 | 후퇴 + reach X_MAX → terminal 아님 |
| | T15 재시도 중 LOST | PREPARE(attempts 1), 보임 + box_lost → LOST |
| | T16 `lift_since_next`·`lift_overstay` 경계 | hold_z 중 None, 같으면 아님 |
| | T17 TickEvent 기본값 | `TickEvent()` 의 retry_room False → GRASP 실패는 후퇴 |
| test_control | C1 `z_plan(hold_z)` → None · C2 `retreat_xy` 3경우(윗면+10 아래 FF / 위 ZERO / x ≥ x_max ZERO) · C3 `command(retreat)` 후퇴 틱 FF·위로만·stopping 0 · C4 `retry_need_s` 7.60 · `lift_max_s` 3.78 · C5 `retry_room_ok` None → False, 경계 225 |
| test_log_schema | L1 4키가 TICK·ATTEMPT 에 있고 부분집합 규칙 유지 |
| test_fake_gripper (새) | G1 `fake_reply` 표 · 계획 소진 뒤 반복 · 닫힌 뒤 재닫기 = verify(소비 안 함) · 모르는 계획 거부 |
| test_sim_check | S1 새 EXPECT 키 · J1 attempts · J-ret 통과/실패/자료 없음 |

### 7.2 바뀌는 기존 시험 (기대값이 설계대로 바뀜)
- test_fsm:52 빈손 재시도 → `TickEvent(..., retry_room=True)` 명시(기본값 False 때문).
- test_fsm:59 WIDE 재시도 → **후퇴(LIFT·hold_z·OPEN)**.
- test_fsm:64 DROPPED → PREPARE 였던 것 → **terminal GRASP_FAILED/DROPPED**.
- test_fsm:69·74·79 시도 다 씀 → terminal 이었던 것 → **후퇴** + at_lift 뒤 terminal.
- test_fsm:277 표의 같은 줄.
- test_action_e2e(가짜 로봇이 명령을 적분 — 후퇴가 실제로 올라간다): `test_retry_phase_times_per_attempt`(max 2, 재시도 여유 판정을 통과하는지 — e2e 값 need 6.43 s·319 mm, TCP x 0 근처라 통과 예상) · 빈손(440줄, 개방 요청 없음 유지) · 늦은 응답 TIMEOUT(490) · BUSY 2회(540) · INVALID(553) — 모두 reason 같고 후퇴 시간만 늘어남. 결과 대기 한계가 모자라면 늘린다.
- test_sim_check: `("grasp","empty")` phases_last GRASP → LIFT.

### 7.3 sim·스모크 (개인 PC, voss-ros, 도메인 74, 앞뒤 점검)
- `sim_check --profile grasp --case all` (기존 + retry·fail_retreat·wide). 수치: 정렬 x·1차 실패 x·재정렬 x·후퇴 끝 z·후퇴 시간.
- build·colcon test·ruff.

## 8. 담당 밖·후속 (회신에 적을 것)
1. 1차 정렬 x 를 앞당기는 것(goal 시점·관측 자세)이 현장에서 재시도를 살리는 유일한 길 — 남현지·학민. 근거: 1차 실패 x ≤ 225 ⇔ 정렬 x ≤ 약 20 mm.
2. voss_msgs.md TrackAndGrasp: ① `GRASP_FAILED`("3회 모두 실패") → "시도 한도 소진 또는 재시도 x 여유 없음 — 후퇴 뒤 보냄" ② **"grasped=false → 자동 개방하지 않는다"의 예외**: 폭 밖(WIDTH_OUT) 실패는 belt_servo 가 결과 전에 파지 높이(박스가 벨트 위에 있는 채)에서 연다 → 풀린 박스는 미분류로 하류로 간다(sort_manager 주석). interface 문구, 필드 변경 없음.
3. 후속 이슈(T28 하위): 저고도 종료 DESCEND_BLIND_TIMEOUT·DESCEND/GRASP 중 OUT_OF_REACH 후퇴 · gate_summary "마지막 phase" 를 후퇴면 "LIFT(후퇴)"로 표기 · `auto_hint` 에서 RETREAT_TIMEOUT·DESCEND_BLIND_TIMEOUT 을 "X(로봇 안 움직임)"로.
4. 알려진 한계 기록: 그리퍼 오류 뒤 닫힌 채 후퇴 때 RG2 가 아직 닫는 중이면(gateway rg2 한계 6 s > belt_servo 3 s) 박스를 끌 수 있음 · (e) 제자리 재닫힘은 현장 x 에서 성립하는 유일한 안 → NOT_DETECTED 실패가 1건이라도 나오면 1순위로 재검.
5. DESIGN.md: DEC-08(재시도)·DEC-17 변경점 — 주관 r8.

## 9. 재검 r1 처리표 (독립 Fable 5.1, 10/12 — 지적별 내 판단)

| # | 지적 | 판단 | 근거·처리 |
|---|---|---|---|
| MAJOR-1 | sim `retry` 기하 틀림(정렬 x 는 P 추격이 정함, −250 시작이어도 71) | **수용** | 독립 재계산 일치(kp 1: 72.5/71.4, kp 3 + −250: −2.4). 6.3 정정, 닫힘 1.2 s 로 여유 43 mm |
| MAJOR-2 | 정상 LIFT 에 3.79 s 상한 → 20/20 성공 경로를 오판으로 끊을 수 있음(여유 1.05 s, 1.39×) | **수용(변형)** | 들기 예상(2.79)이 실측(2.73)과 거의 같아 여유가 +1.0 뿐 — 성공 경로를 바꾸려면 현장 자료가 먼저. 후퇴에만 상한, 정상 LIFT 는 WARN 1회(구멍은 로그로 보이게). **사용자 DD 판단 3 을 바꾸는 것 — 재승인 항목** |
| MAJOR-3 | 폭 밖 개방 대기 = 파지 높이 정지 위험(무응답 6.5 s → x_max 에서 xy 0) | **수용** | hold_expired(2.3 s ∨ x_max) 로 상승. "열린 뒤 상승"(Q3)의 정상 경로는 그대로, 고장 때만 Q2 와 같은 판단 |
| MINOR-4 | e2e `test_retry_phase_times_per_attempt` 누락 | **수용** | 7.2 에 e2e 5개 명시 |
| MINOR-5 | 폭 밖 개방이 "자동 개방 금지" 문구와 충돌 | **수용(문서)** | 8.2 담당 밖 요청에 예외 문구. 동작은 사용자 Q3 결정대로 |
| MINOR-6 | gate_summary 마지막 phase LIFT 오독 | **후속** | 수정 허용 범위 밖(지시서) → 8.3 |
| MINOR-7 | 시험 공백 4건 | **부분 수용** | ① `retry_room_ok` 순수 함수 + C5 ② 폭 밖 재시도 분기 삭제로 해당 없음 ③ 늦은 응답 폐기는 기존 e2e(490줄)가 지킴 → 7.2 에 유지 확인 ④ 후퇴 중 top_z 변화는 FF 라 무해 — 시험 가치 낮아 불채택 |
| NIT-8 | `retry_room` 기본 True ↔ 노드 "모르면 False" | **수용** | 기본 False(T17), test_fsm:52 명시 |
| NIT-9 | 후퇴 xy 0 높이 5 mm 는 외삽 앞섬에 약함 | **수용** | 10 mm |
| NIT-10a | 폭 밖 재시도 분기는 죽은 코드 | **수용** | x_f ≤ 115 도달 불가 → `retry_room_open`·재시도 hold_z·T6(옛) 삭제 |
| NIT-10b | `exit_cause` 는 `Transition.cause` 와 중복 | **불수용** | Transition.cause 는 그 틱만 — 후퇴 끝 틱까지 기억하려면 상태 필드가 필요 |
| 결정 의견 | (c)+후퇴 타당 · (e) 보류는 표본 0 판단 · max 1 동의 · T28 재시도는 sim 만 입증 · P2 근거 보강 | **반영** | 1절·8.4·HLD P2 에 voss_msgs.md BoxTrack "PICKING 동안 트랙 폐기 안 함" 인용 |

## 10. 최종 재검 r2 처리표 (독립 Fable 5.1, PR 전, 10/12 — 지적별 내 판단)

재검이 직접 돌린 것(도메인 72·73): build·colcon test 371/0·ruff · `sim_check --profile grasp` 8/8 · 스모크 6종(재시도 `empty,empty,held` 2회 시도 뒤 후퇴, 후퇴 중 취소 → 다음 틱 0·CANCELED·`retreat_done` false, sim.launch 기본값은 remap 없음, gripper:=fake 때 belt_servo 만 remap, 개방 2.6 s 지연 → 2.37 s 에 상승, 서비스 직접 호출). BLOCKER·MAJOR 없음, 판정 yes-with-fixes.

| # | 지적 | 판단 | 처리 |
|---|---|---|---|
| MINOR-1 | 문서 3.79 ≠ 실제 3.78 (반올림 합) | **수용** | 계산 2.7848 + 1.0 = 3.7848 확인. control.py 주석·DD·pseudo·U9-run·C4(3.785 ±0.005) 를 3.78 로 |
| MINOR-2 | 재시도 예산에 2차 실패 뒤 후퇴 FF·감속이 없음(스모크 끝 x 594) | **수용(문서)** | 코드 변경 없음 — x 가드가 x_max 에서 끊어 최악 ≈612(gateway 638 안), 현장 max_attempts 1. 1절 표에 근거 한 줄 |
| MINOR-3 | `grip_plan:=bogus` 면 fake_gripper 만 죽고 belt_servo 는 READY | **수용** | sim.launch 에서 `parse_plan` 선검증 → launch 가 바로 실패 |
| NIT-4 | yaml 주석 "U9 에서 3 으로 켠다" 가 결정과 어긋남 | **수용** | belt_servo.yaml·real.yaml.example 주석을 "1 유지" 로 (값 불변) |
| NIT-5 | `_hold_expired` 만 `>=` | **수용** | `>` 로 통일("같으면 아직") |
| NIT-6 | log_schema·sim.launch·setup.py 가 지시서 허용 목록에 글자로는 없음 | **회신에 명시** | DD 0절에서 승인된 범위 |
| NIT-7 | 변경 줄 수가 conventions 권장(300줄) 초과 | **PR 본문에 안내** | 설계 문서가 대부분, 코드는 fsm → control → belt_servo 순으로 읽기 안내 |
| 사용자 결정 표기 | 후퇴 중 pose 끊김·RETREAT_TIMEOUT 은 중간 높이 정지 가능, WIDTH_OUT 결과 전 개방, hold_expired 미개방 상승, 후퇴 phase LIFT | 변경 없음 | 이미 DD·U9-run 에 명시 |
