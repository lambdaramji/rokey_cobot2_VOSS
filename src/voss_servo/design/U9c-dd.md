# U9-c DD — 값·cause·로그 보강 (T28 #37)

HLD: design/U9c-hld.md. 모든 문턱은 **제안값**이다(실측 전이며, belt_servo 파라미터는 ADR-0012 범위 밖).
r2 (10/12): 독립 재검(Fable 5.1) 결과 중 세션이 재확인한 것만 반영했다. 반영·기각 내역은 8절.

## 1. 값 변경 ③

| 키 | 전 → 후 | 출처 (yaml 주석) | 파일 |
|---|---|---|---|
| `reach.x_max_mm` | 620 → **600** | measurements-1010 #13(x 600~618 TRACK z 처짐 1.3→4.3 mm, 2/2) · #14(특이점 안내 3205/3206 x≈600) · FIELD §4 | belt_servo.yaml · belt_servo_real.yaml.example · belt_servo_sim.yaml |
| `grasp.close_time_max_s` | 2.1 → **2.3** | measurements-1010 7·8절 적재 15칸 닫기 1625~2128 ms(2.1 초과 1회) · FIELD §5 #13 | 같은 3개 |

- `params.py` 검사 규칙은 그대로다. 두 값 모두 기존 교차 검사를 통과한다: `x_min −107 < x_max 600`, `gripper_timeout 3.0 > close_time_max 2.3`.
- 함께 고칠 주석: `gripper_timeout_s` 의 "T34 닫힘 최대 2.1 s + 여유"(belt_servo.yaml:49, example:55)를 "10/10 최대 2128 ms(close_time_max 2.3) + 여유"로 바꾼다.

> 지시서는 close 출처를 "measurements-1010 §2"라고 적었지만, 2128 ms 는 7·8절(445·452행)에 있다(§2 는 펜던트 공간 제한). 주석에는 7·8절로 적는다.

### 1.1 x 여유 문턱 영향 (계산)
정렬 순간 `x_max − TCP x ≥ 벨트 × (하강 예상 + close_time_max) + room_margin` 이어야 DESCEND 한다. 이 식에서 TCP x 의 상한을 "문턱"이라 부른다.
하강 예상은 `grip.descend_time_s(0.059, 0.05, 0.1, 1.5, 0.002)` = **2.639 s** 이다(10/10 현장값: approach 40, 파지 −19, kp_z 1.5).

| x_max | close | 필요 길이 (48 mm/s) | 문턱 (TCP x ≤) |
|---|---|---|---|
| 620 | 2.1 | 237.5 mm | 382.5 (10/10) |
| 600 | 2.1 | 237.5 | 362.5 (FIELD §4 의 값) |
| 620 | 2.3 | 247.1 | 372.9 |
| **600** | **2.3** | **247.1** | **352.9 (U9-c 이후)** |

- 지시서의 "약 363"은 x_max 하나만 바꾼 값이다. 두 값을 함께 바꾸면 필요 길이는 늘고(237.5 → 247.1) 문턱은 **352.9 mm** 로 내려간다.
- 정상 정렬 x 는 85~91 mm 라 여유가 260 mm 넘게 남는다 → 정상 사이클 영향 없음.
- 벨트 7 cm/s 라면 필요 길이 355.7, 문턱 244.3 이다. FIELD 의 시뮬 정렬 x 135 보다 크므로 통과한다.
- **U9-b 입력:** 재시도 재정렬 x≈421(FIELD §5 #12)은 문턱 352.9 보다 68 mm 더 멀다. 재접근 재설계가 이 숫자를 넘어야 한다.
- sim_check 기대값은 cause·phase 만 보고 X_MAX 시각은 보지 않는다(J1~J12, 재검으로 확인). 그래서 **바꿀 기대값이 없다**. 코드 단계에서 실제로 돌려 확인한다.

## 2. 새 로그 필드

규칙은 그대로다: 키 끝에 단위, 모르면 null, 시도 키 ⊂ 틱 키.

| 키 | 단위·형 | 값 | null 조건 | 시도 행에도 |
|---|---|---|---|---|
| `box_u_px`, `box_v_px` | px, float | 내 트랙 최신 메시지의 BoxTrack.u·v (`box_stamp_s` 와 같은 메시지) | 메시지 없음 | — |
| `obs_rx_age_s` | s | now − 마지막 **유효** 관측의 **수신** 시각 | 유효 관측 없음 | — |
| `other_box_rx_age_s` | s | now − 이 goal 동안 **다른 트랙** 메시지의 마지막 수신 시각 | goal 중 다른 트랙 없음 | ✅ |
| `box_pub_count` | 개 | `/voss/vision/box` 발행자 수. **LOST 틱에서만** 조회 | LOST 틱이 아님·조회 실패 | ✅ |
| `tcp_vel_meas_mps` | m/s [x,y,z] | pose 값 차분 측정 속도(§4.1). z 성분 = "측정 z 속도" | pose 값 2개 미만 | — |
| `stall_ticks` | 틱 | "명령 ≠ 0 인데 측정 ≈ 0" 연속 틱 수 | — (0부터) | ✅ |
| `belt_speed_est_mps` | m/s | 관측열 직선 맞춤 속도, 벨트 방향 성분(§4.3) | 점 부족·시간 폭 부족 | ✅ |
| `belt_speed_est_span_s` | s | 맞춤에 쓴 관측의 시간 폭(신뢰도 참고) | 점 부족 | ✅ |
| `cause_fsm` | str | fsm.step 이 낸 원래 cause (덮어쓰기 전) | 스냅샷 행(0 유지·예외·종료) — fsm 을 거치지 않음 | ✅ |
| `phase_t_prepare_s` … `phase_t_verify_s` (6개) | s, 노드 시계 | 이 시도에서 그 phase 에 처음 들어간 시각 | 아직 안 들어감 | ✅ |

- `obs_age_s` 는 **이름을 유지**한다. 10/10 원본·U-A·measurements-1010 과 호환하기 위해서다. log_schema 주석을 "now − 마지막 유효 관측의 촬영 stamp(BoxTrack.stamp)"로 명확히 한다.
- **단계 시각 규칙 (r2, 재검 F1):**
  - 시도 단위다. 첫 PREPARE 시각 = goal 수락 시각(`_execute`, 첫 틱보다 1틱 이내 앞)이다.
  - phase 진입은 `ctx.phase_seen`(지난 틱에 기록한 phase)과 `tr.state.phase` 를 비교해 판정한다. 그래서 `ctx.state` 대입 순서에 의존하지 않는다.
  - **재시도 틱(`tr.attempt_ended`)에서는 지우지 않는다.** 그 틱의 틱 행과 ATTEMPT_END 행이 끝난 시도의 시각을 그대로 담는다. 새 시도는 `ctx.phase_t_next = {PREPARE: now}` 로 예약하고, 다음 틱 진단 첫머리에 교체한다.
  - 이렇게 하는 이유: 같은 틱에서 틱 행(belt_servo.py:415) → ATTEMPT_END(417)가 같은 dict 로 만들어진다. 바로 지우면 끝난 시도의 DESCEND·GRASP 시각이 사라진다.
- 스냅샷 행(0 유지·INTERNAL_EXCEPTION·NODE_SHUTDOWN): 단계 시각은 `_last_goal` 에서 가져오고, `cause_fsm` 과 나머지 새 키는 null 이다(재검 F8 — fsm 을 거치지 않은 행이라 원래 cause 가 없다).
- 키 수: 틱 54 → 70 (+16), 시도 18 → 30 (+12).

## 3. cause 세분 ④ — `diagnose.lost_cause`

**적용 조건 (r2, 재검 F7 변형).**
- `tr.reason == LOST` 이면 진단한다.
- 진단 결과가 `VISION_DOWN`·`ROBOT_STALLED` 일 때만 `tr.cause` 를 바꾸고, 특정 원인이 없으면 **fsm 이 낸 cause 를 그대로 둔다.**
- 이렇게 하면 지금은 fsm cause 가 `BOX_MISSING` 하나뿐이라 결과가 같다. 그리고 U9-a 가 LOST 에 새 cause 를 만들어도 그 값을 지우지 않는다.

| 순서 | cause | 조건 (모두 LOST 틱 기준) | 힌트 |
|---|---|---|---|
| 1 | `VISION_DOWN` | `box_pub_count == 0` (box_tracker 발행자 없음. None = 조회 실패는 0 으로 치지 않음) | L |
| 1 | `VISION_DOWN` | **또는** 다른 트랙과 내 트랙의 마지막 수신이 모두 있고 \|other_rx − my_rx\| ≤ `SIMUL_LOSS_S` 0.2 s | L |
| 2 | `ROBOT_STALLED` | `stall_ticks ≥ STALL_TICKS_N` | X |
| 3 | (fsm cause 유지) | 그 밖 — 지금은 `BOX_MISSING` | L |

**r2 수정 (재검 F2).** 처음에는 "다른 트랙도 lost_timeout 넘게 안 옴" 조건을 함께 걸었다. 이 조건은 중복이면서 경계에서 해롭다.
- 중복인 이유: LOST 틱이면 now − my_rx > 0.5 이다. other_rx ≤ my_rx + 0.2 이면 다른 트랙도 0.3 s 넘게 안 온 것이다(30 Hz 9프레임). 다른 트랙이 지금도 오고 있으면 other_rx ≈ now > my_rx + 0.5 라서 0.2 조건에서 이미 빠진다.
- 해로운 이유: box_tracker 는 한 프레임의 트랙을 id 순서로 차례로 발행한다(box_track.py:96, box_tracker.py:300~309). 그래서 동시 끊김이어도 other_rx = my_rx + 약 1 ms 가 된다. LOST 첫 틱은 now − my_rx ∈ (0.5, 0.533] 이므로, 약 3 % 확률로 "다른 트랙은 아직 0.5 이하"가 되어 BOX_MISSING 으로 놓친다.

### D1 — "모든 트랙이 끊김"을 그대로 쓸 수 없다 (10/12 사용자 승인)
box_tracker 는 **미검출 프레임을 발행하지 않는다**(box_tracker.py:5, box_track.py:96). 그래서 벨트 위 박스가 하나뿐일 때 그 박스가 시야에서 사라지면 `/voss/vision/box` 전체가 조용해진다. 이것은 카메라가 죽었을 때와 구별되지 않는다.
- **채택:** 발행자 0, 또는 다른 트랙과 **동시에** 끊긴 경우만 VISION_DOWN 으로 본다. 박스가 하나뿐이면 fsm cause(BOX_MISSING)를 유지한다.
- **알려진 한계 (힌트 문구에 "추정"을 붙인다):**
  1. 박스 1개 + 카메라 USB 끊김(10/10 사건 2회) → BOX_MISSING 으로 남는다. 판단 재료는 `box_pub_count`·`box_rx_s`·box_tracker 5초 로그다.
  2. 박스 2개가 하강 중 0.2 s 안에 함께 시야를 벗어나면 → VISION_DOWN 오판이 난다(재검 F3, 빈도 미상). 확인은 `other_box_rx_age_s`·box_tracker 로그로 한다. 영향은 힌트·로그뿐이고 제어와는 무관하다.
  3. box_tracker 가 **크래시**하면 DDS lease 가 끝날 때까지 발행자 수가 1 로 남는다 *(lease 길이 미확인)*. 그래서 ① 은 정상 종료·미기동만 확실히 잡는다.
- 완전히 가르려면 box_tracker 쪽 신호(프레임 heartbeat 또는 카메라 상태)가 필요하다 → 9절 담당 밖 요청(남현지).
- 재ID·goal 전 수신은 영향이 없다(재검 반박 실패): 새 트랙 ID 는 폐기 15프레임 + min_hits 뒤라 LOST 틱보다 늦게 생긴다. `other_rx` 는 GoalCtx 값이라 goal 전 수신은 None 이다.

**순서 근거.** 비전이 죽으면 로봇 상태와 무관하게 박스가 안 보인다 → VISION_DOWN 이 먼저다. 로봇이 멈춰 있으면(카메라는 손목에 있음) 박스가 시야 밖으로 흘러간다 → 그다음이 ROBOT_STALLED 다.

## 4. 순수 함수

### 4.1 `diagnose.measured_velocity(prev, cur, now, hold_max_s) -> list|None`
- `prev`·`cur`: `(위치 tuple, 그 값이 처음 온 stamp)`. 노드가 "값이 바뀔 때마다" 하나씩 민다(`control.pose_value_stamp` 결과가 바뀌면 이전 것을 prev 로).
- `cur` 없음 → None.
- `now − cur.stamp > hold_max_s` → [0,0,0] (값이 멈춤 = 로봇 정지).
- prev 없음 또는 stamp 차 ≤ 0 → None.
- stamp 차 > hold_max_s → None (r4, 2차 재검 R1): goal 전에 오래 멈춰 있던 값에서 처음 바뀌면 dt 가 정지 기간 전체라 속도 ≈ 0 이 나와 출발 때 stall 을 부풀린다.
- 그 밖 → (cur − prev) / (cur.stamp − prev.stamp).
- `POSE_HOLD_MAX_S = 0.2`: service pose 는 0.1 s 계단 + 메시지 간격 20 ms. 계단 한 칸으로는 "멈춤"이 되지 않게 그 두 배로 잡는다.

### 4.2 `diagnose.stall_count(prev_n, cmd_speed, meas_speed) -> int`
- `meas_speed is None` → 0 (모르면 정지라 하지 않는다).
- `cmd_speed ≥ STALL_CMD_MIN_MPS` 이고 `meas_speed < STALL_RATIO × cmd_speed` → prev_n + 1.
- 그 밖 → 0.
- `cmd_speed` = **직전 틱에 발행한** 명령 크기(`_last_cmd`, 이번 틱 발행 전)다. 측정 속도가 명령보다 늦게 따라오기 때문이다. `_last_cmd` 는 `_publish`(belt_servo.py:754)에서만 바뀐다.

### 4.3 `control.belt_speed_fit(samples, dir_xy, max_points, min_points, min_span_s) -> (v|None, span|None)`
- `samples`: `(촬영 stamp, xyz)` 목록(시간순). 최근 `max_points` 만 쓴다.
- s_i = dir_xy · xy_i (벨트 방향 성분). t_i 는 첫 점 기준으로 뺀다(수치 안정).
- 점 < min_points → (None, None). 시간 폭 < min_span_s 이거나 분산(t) = 0 → (None, span).
- 최소제곱 기울기 v = Σ(t−t̄)(s−s̄) / Σ(t−t̄)² → (v, span). v 는 부호 있는 m/s 다(벨트 방향이 양수).
- **관측열 규칙:**
  - 내 트랙의 **새 유효 관측**(stamp 가 앞 점보다 클 때)만 넣고, 길이 `FIT_MAX_POINTS` 의 deque 로 둔다.
  - **시도마다 비운다**(goal 시작·`attempt_ended`, 재검 F13 — 실패한 파지가 박스를 밀면 s 열에 계단이 생긴다).
  - 노드는 틱당 "마지막 유효 관측" 하나만 본다. 그래서 틱 사이에 메시지가 2개 오면 하나를 건너뛴다. 편향은 없고 점 수만 줄어든다(재검 F15).

### 4.4 `diagnose.speed_warn_step(run, warned, est, set_speed, span, new_obs, ratio) -> (run, fire)`
- **r2 (재검 F4):** `new_obs` 가 거짓이면(이번 틱에 관측열에 새 점이 없으면) `(run, False)` — run 을 유지한다. 이렇게 해야 사각 진입 뒤 같은 추정값으로 15틱을 채우는 퇴화를 막는다.
- `est is None` 또는 `span < WARN_MIN_SPAN_S` → (0, False).
- `|est − set| / set ≥ ratio`(인자, 노드는 `SPEED_WARN_RATIO` 0.10) → run + 1, 아니면 0.
- `fire = (not warned) and run ≥ SPEED_WARN_TICKS_M`. 노드는 fire 일 때 WARN 1줄을 찍고 goal 의 warned 를 True 로 바꾼다(시도마다 비우지 않음).
- WARN 문구: `벨트 속도 추정 4.20 cm/s ≠ 설정 4.80 cm/s (−12.5 %, 새 관측 15회 연속, 폭 2.1 s) — FF 는 설정값 그대로, 벨트 속도 설정 확인`
- **goal 끝 INFO 1줄 (r3, B안):** terminal 틱에서 `벨트 속도 추정 4.70 cm/s (설정 4.80, −2.1 % ≥ 2 %, 폭 3.1 s) — 로그 전용` (추정값 없으면 `추정 없음(점 n개)`). `diagnose.speed_note(est, set, span, n)` 순수 함수로 문구를 만든다.

### 4.5 상수 (diagnose.py 머리, 30 Hz 기준 근거 주석)

| 상수 | 제안값 | 근거 |
|---|---|---|
| `POSE_HOLD_MAX_S` | 0.2 | service 계단 0.1 + 메시지 0.02 의 약 2배 |
| `STALL_CMD_MIN_MPS` | 0.01 | 정상 추종 명령 ≈ 0.048(FF). 0 근처 명령은 판단하지 않는다 |
| `STALL_RATIO` | 0.25 | "안 움직임" 기준. 램프 첫 0.3 s 에는 측정이 0 근처일 수 있지만 N 이 흡수한다(아래) |
| `STALL_TICKS_N` | 10 (≈0.33 s) | 재검 램프 시뮬: service pose 에서 연속 stall 최대 6틱, joint_states 0틱. 10/10 틱 로그 재생(26 goal, joint_states): 최대 0틱. lost_timeout 0.5 s 보다 짧다 |
| `SIMUL_LOSS_S` | 0.2 | 같은 카메라 프레임 끊김이면 트랙들의 마지막 수신 차는 몇 ms~한 프레임 |
| `FIT_MAX_POINTS` | 90 (≈3 s) | 잡음 σ 1 mm 가정 시 기울기 σ: 30점·1 s 0.6 mm/s(1.3 %), 90점·3 s 0.12 mm/s(0.25 %) |
| `FIT_MIN_POINTS` | 15 | 0.5 s 분량 |
| `FIT_MIN_SPAN_S` | 0.5 | 이보다 짧으면 null |
| `WARN_MIN_SPAN_S` | **2.0** (r2, 재검 F9) | 1.5 s(45점)는 σ 0.34 mm/s = 0.7 % 이고, 2.0 s(60점)는 0.46 % 다. 2 % 경고는 σ ≤ 0.5 % 일 때만 낸다 |
| `SPEED_INFO_RATIO` | 0.02 | goal 끝 INFO 줄에 "2 % 이상" 표시 — 10/12 결정(2 % 이상 차이면 추정 FF 후보), 판단은 로그로 오프라인 |
| `SPEED_WARN_RATIO` | **0.10** (r3, 10절 B안) | 10/12 결정의 "10 % 이상 goal 거부" 단계와 같은 값. 지금은 WARN 만 — 명백한 설정 오류(h500 인데 4.8 등) 알림 |
| `SPEED_WARN_TICKS_M` | 15 (새 관측 15회 ≈ 0.5 s) | 한두 번 튐 무시 |

## 5. belt_servo 연결 (전이·제어 변경 없음)

| 위치 | 변경 |
|---|---|
| `__init__` | `_pose_prev_value`(직전 pose 값·stamp) 하나 추가. 다른 트랙 수신 시각은 goal 단위라 GoalCtx 에 둔다 |
| `_on_box` | goal 중이고 다른 트랙이면 `ctx.other_rx = now` |
| `_on_pose` | `pose_value_stamp` 결과의 값이 바뀌면 이전 것을 `_pose_prev_value` 로 |
| `GoalCtx` | `obs_hist`(deque), `stall_n`, `speed_run`, `speed_warned`, `other_rx`, `phase_t`(dict), `phase_t_next`, `phase_seen`, `diag`(이번 틱 진단 값 묶음) |
| `_tick_goal` | `fsm.step` 바로 뒤(`ctx.state = tr.state` 앞)에 `tr = self._diagnose(ctx, tr, now)` **한 줄** 추가. 그 아래 순서는 그대로 |
| `_diagnose` (새) | **전체를 try/except** (재검 F6). 실패하면 `ctx.diag` 값 null + error 로그 1회(goal 당), tr 을 그대로 돌려준다. 실패한 틱이 재시도 틱이면 새 시도 준비(단계 시각 예약·관측열 비우기)는 except 안에서도 한다(r4, 2차 재검 R2). 순서: 예약된 단계 시각 교체 → 관측열 갱신 → 측정 속도 → stall → 속도 추정·WARN → 단계 시각 기록(재시도면 예약) → cause_fsm 보관 → (LOST 이면) 발행자 수 조회 + `lost_cause` + 필요할 때만 `replace(tr, cause=…)` |
| `_tick_values`·`_snapshot_values`·`_finish` | 새 키 채우기, `_last_goal` 에 단계 시각 추가 |

- `_finish` 의 경고 줄 `goal 종료 reason=LOST cause=VISION_DOWN` 은 자동으로 새 cause 를 쓴다(덮어쓴 tr.cause 가 넘어감, belt_servo.py:421). 결과 봉투는 reason·grasped·attempts 뿐이라 계약 영향이 없다.
- `count_publishers` 는 `_diagnose` 안에서 LOST 틱에만 1회 부른다.

## 6. gate_summary

| 항목 | 전 | 후 |
|---|---|---|
| TickSummary | `descend_max_err_mm` (‖error_m‖ 최대, 59 mm 높이차가 지배) | `descend_max_along_mm` = max\|err_along_m\|, `descend_max_cross_mm` = max err_cross_m (DESCEND 틱) |
| 힌트 표 열 | "하강 최대 오차 mm" | "하강 최대 벨트방향 오차 mm", "하강 최대 가로 오차 mm" (열 이름에 `err_along_m`·`err_cross_m` 출처 각주) |
| `auto_hint` | LOST → L | LOST+`VISION_DOWN` → L "비전 전체 끊김 추정 — box_tracker 5초 로그·other_box_rx_age_s 확인" / LOST+`ROBOT_STALLED` → X "명령은 나갔는데 로봇 정지 — gateway 로그로 X·D 구분" / 그 밖 LOST → L (기존) |

- 10/10 틱 로그에도 `err_along_m`·`err_cross_m` 이 있어 재집계가 가능하다.
- 힌트 표는 g1-gate 3절 기록표(GATE_COLUMNS)가 아닌 보조 표다. `test_table_columns_match_g1_gate` 는 열 수를 자동으로 따른다.
- measurements-1010 422행의 열 이름 메모는 담당 밖 문서라 9절에 적는다.

## 7. 시험 목록 (pytest)

| 파일 | 시험 |
|---|---|
| test_params | yaml 3종 x_max 600·close 2.3 / close 2.3 + timeout 3.0 통과 / timeout 2.3 = close 거부 (경계) |
| test_diagnose (새) | **lost_cause:** 발행자 0 → VISION_DOWN / 발행자 None → 비전 판단 안 함 / 다른 트랙 +1 ms 동시 끊김(LOST 첫 틱 0.5005 s) → VISION_DOWN (F2 회귀) / \|Δ\| = 0.2 → VISION_DOWN, 0.2001 → None / 박스 1개 → None / stall 10 → ROBOT_STALLED, 9 → None / 발행자 0 + stall → VISION_DOWN(순서) · **measured_velocity:** 일정 속도·멈춤(hold 초과)·값 1개·stamp 같음 · **stall_count:** 증가·리셋·None·명령 작음·비율 경계 · **램프 회귀:** acc 0.1 램프 + 응답 지연 0.23 s 시퀀스에서 최대 연속 < 10 · **speed_warn_step:** 비율 경계(10 %)·M 경계·1회만·span 부족·new_obs 거짓이면 run 유지 |
| test_control | belt_speed_fit: 직선 정확(오차 < 1e-9) / 잡음 σ 1 mm 90점 → 0.5 % 안 (고정 seed) / 점 부족 (None, None) / 폭 부족 (None, span) / 가로 성분 무시 / max_points 자르기 |
| test_log_schema | 새 키 존재, 시도 ⊂ 틱, make_tick 키 불일치 오류 |
| test_gate_summary | along·cross 최대 (부호 있는 along 의 절댓값) / 힌트 VISION_DOWN→L·ROBOT_STALLED→X / 과거 형식 틱(새 키 없음)도 집계 |
| test_node / e2e (재검 F5) | 기존 통과 + ① LOST 경로 GOAL_END 에 cause_fsm=BOX_MISSING·phase_t_* 존재 ② `count_publishers` 를 0 으로 바꾼 LOST → GOAL_END·`_finish` 경고 cause=VISION_DOWN, cause_fsm=BOX_MISSING ③ `_diagnose` 안 예외 → goal 은 계속(INTERNAL_EXCEPTION 아님) ④ `retry.max_attempts: 2` + 빈손 → ATTEMPT_END 행 phase_t_grasp_s non-null, GOAL_END phase_t_prepare_s > ATTEMPT_END 의 것 |
| sim_check | 개인 PC 도메인 70–71, grasp 3건 통과 (11절 — pre_u5 5건은 U5 머지 뒤부터 원래 실패, 베이스 aed51d5 에서도 같은 실패) |

## 8. 독립 재검 반영 (r2, Fable 5.1, 10/12)

세션이 지적마다 코드·계산·로그로 다시 확인한 뒤 판정했다.

| ID | 지적 | 판정 | 근거·처리 |
|---|---|---|---|
| F1 | 재시도 틱에 단계 시각을 지우면 ATTEMPT_END 가 새 시도 시각을 담음 | **반영** | belt_servo.py:415·417 같은 dict 확인 → 예약 교체(2절) |
| F2 | "다른 트랙도 끊김" 조건 중복 + 경계 3 % 놓침 | **반영** | box_track.py:96 id 순 발행 확인, 계산 일치 → 조건 삭제(3절) |
| F3 | 박스 2개 동시 이탈 오판 | **반영(한계 기재)** | 힌트 "추정" 문구 + 3절 한계 2. 가장자리 u·v 제외 규칙은 기각(화면 크기·bbox 경계 규칙 = 새 판단, 이 단위 범위 밖) |
| F4 | WARN run 이 새 관측 없이도 증가 | **반영** | `new_obs` 인자(4.4). 10/10 로그 재생 → 10절 |
| F5 | 노드 경로 통합 시험 없음 | **반영** | 7절 test_node/e2e ②~④ |
| F6 | 진단 예외가 goal 을 끊음 | **반영** | `_diagnose` try/except (5절) |
| F7 | BOX_MISSING 조건이 U9-a 새 cause 를 비켜 감 | **변형 반영** | LOST 면 진단하되, 특정 원인이 없으면 fsm cause 유지(재검안 "LOST 만으로 덮어쓰기"는 U9-a cause 를 지우므로 택하지 않음) |
| F8 | 스냅샷 cause_fsm 의미 | **반영** | null (2절) |
| F9 | 1.5 s 근거 계산 오류 | **반영** | 재계산 0.72 % 확인 → 2.0 s |
| F10 | HLD "문턱이 커진다" 방향 오류 | **반영** | HLD 0절 문구 |
| F11 | gripper_timeout 주석·DESIGN.md:112 | **반영** | yaml 주석(1절), DESIGN 은 9절 |
| F12 | ROBOT_STALLED 힌트 X·D 구분 | **반영** | 6절 문구 |
| F13 | 관측열 시도마다 비우기 | **반영** | 4.3 |
| F14 | GOAL_END 에 사각 진입 시각 추가 | **기각** | 틱 `vision_blind` 전환으로 이미 구할 수 있다. 사각 판정 자체가 U9-a 에서 바뀔 수 있어 U9-a 가 필요한 필드를 정하는 것이 맞다 |
| F15 | 틱당 관측 1개 | **반영(기록만)** | 4.3 한 줄 |

## 9. 담당 밖 요청 (회신 "담당 밖 요청"에 그대로 옮긴다)

| 대상 | 요청 | 이유 |
|---|---|---|
| 남현지 (box_tracker, interface) | 프레임 heartbeat 또는 카메라 상태 신호(예: 프레임마다 "검출 0개" 표시, 또는 별도 상태 토픽) | 박스 1개일 때 카메라 끊김과 박스 소실을 belt_servo 가 가를 수 없다(3절 D1 한계 1) |
| 남현지 (box_tracker) | 10절의 추정 편향(이동 중 position_base 의 벨트 방향 속도 4.69 vs bag 4.76) 확인 의견 | 추정값을 FF 로 쓰기 전 전제 |
| 주관 (DESIGN r8) | DESIGN.md:112 `close_time_max_s 2.1` → 2.3, :223 ③·:233 x_max 620 → 600 반영, 142행 "T34 닫힘 최대 2.1 s" | 수정 금지 파일 |
| 학민 (measurements-1010 기록) | 422행 "하강 최대 오차 mm" 메모 옆에 "U9-c 부터 along·cross 두 열" 한 줄 (선택) | 도구 열 이름 변경 |

## 10. 10/10 틱 로그 오프라인 재생 결과 (재검 F4②, 세션 실행)

입력: `~/Downloads/servo_ticks_20261010_164210.jsonl` (G1 시리즈 포함 26 goal, joint_states pose). 이 DD 의 fit·WARN·stall 규칙을 그대로 재생했다.
- **stall:** 26 goal 전부 최대 연속 0틱이다 → 정상 회차 ROBOT_STALLED 오탐 없음. LOST 5건도 로봇이 움직이고 있어 fsm cause(BOX_MISSING)가 유지된다.
- **속도 추정:** 관측 90~120점, 폭 ≥ 2.0 s 구간 추정값이 대부분 **4.68~4.73 cm/s** 다(최대 4.76, goal 안 흔들림 약 ±0.02 → 정밀도는 충분). 그런데 설정 4.80 보다 **약 −1.5~−2.5 %** 낮고, bag 측정 4.76(measurements-1010 #11, box_tracker 좌표로 잰 리허설 값 — 그때 로봇 동작 여부는 기록에서 확인 못 함)보다도 약 −1.4 % 낮다.
- **결과:** 2 % 규칙이면 **26 goal 중 22 goal 에서 WARN** 이 난다.
  - 실제 벨트(4.76)와 설정(4.80)의 차는 −0.8 % 다. 따라서 이 WARN 의 절반 이상은 **추정기 편향** 때문이다 *(원인 추측: 로봇 이동 중 position_base 의 속도 비례 오차 — pose 보간 지연 잔차 등)*.
- **결정 (10/12 사용자, B안):** goal 마다 끝에 INFO 한 줄(추정·설정·차이 %, 2 % 이상이면 표시), WARN 은 10 % 차이가 새 관측 15회 연속일 때 goal 당 1회. 지시서의 "2 % WARN"과 다름 → 회신 변경점. 추정값 틱·시도 로그는 그대로.

## 11. 구현 결과 (10/12, 개인 PC)

| 검증 | 결과 |
|---|---|
| colcon build (voss_msgs·voss_robot·voss_servo) | 통과 |
| colcon test voss_servo | **292 tests, 0 failures** (베이스 aed51d5 246 → +46: test_diagnose 신규, control·params·log_schema·gate_summary·e2e 추가. r4 에서 +3) |
| ruff check · format --check | 통과 |
| sim_check `--profile grasp --case all` (도메인 70) | normal OK(6 phase) · empty GRASP_FAILED/NOT_DETECTED · cancel CANCELED/STOP_OK — **3/3 종료 코드 0** (r4 수정 뒤 다시 실행해도 3/3) |
| 시뮬 로그 새 필드 | 3건 모두 `belt_speed_est_mps` 4.80 cm/s(가짜 박스 = 설정 속도, 폭 2.97 s·90점) · `stall_ticks` 최대 0 · 단계 시각 순서대로(normal: TRACK +0.30, DESCEND +3.50, GRASP +6.20, LIFT +6.54, VERIFY +9.40 s) · goal 끝 INFO 1줄 |
| sim_check `--profile pre_u5` | 5/5 종료 코드 1 — **기존 문제**. U5 이후 박스가 사라지기 전에 파지가 끝나(OK) "PREPARE 에서 끝남" 기대값과 어긋난다. 베이스 aed51d5(U-F 워크트리)에서 lost 케이스를 돌려도 같은 J1·J2·J3 실패를 확인했다. 기대값 재설계는 이 단위 범위 밖이라 회신에 후속으로 적는다 |

e2e 에서 확인한 것: 발행자 0 LOST → GOAL_END cause VISION_DOWN·cause_fsm BOX_MISSING·box_pub_count 0 / 다른 트랙만 보이는 LOST → BOX_MISSING 유지 / 진단 예외 → goal 은 LOST/BOX_MISSING 으로 정상 종료 / 재시도 2회 → ATTEMPT_END 에 끝난 시도의 GRASP 시각, GOAL_END 에 새 시도 시각 / 정상 파지 추정 속도 0.048 ± 2 %.

## 12. 최종 독립 재검 (r4, Fable 5.1, PR 전, 10/12)

재검자가 도메인 71 에서 다시 돌려 확인한 것:
- pytest 289 · colcon test 289 · ruff 통과 · sim_check grasp 3/3 · pre_u5 lost 가 베이스와 같은 실패.
- 노드 경로 스모크 6건(가짜 로봇·가짜 박스):
  - 동시 끊김 → VISION_DOWN(pub 1), 발행자 종료 → VISION_DOWN(pub 0)
  - 로봇 고정 → ROBOT_STALLED(stall 60), 움직이는 로봇 → stall 0
  - 박스 0.88× → WARN 정확히 1회(−12.0 %), 0.97× → WARN 0·INFO "≥ 2 %"
  - x_max 600 에서 REACH_X_MAX(TCP x 0.6005)
- 10/10 재생: 2 % 규칙 22/26, 10 % 규칙 0/26. gate_summary 새 열 정상.
- 판정: "PR 가능".

세션이 지적마다 다시 확인한 뒤 판정했다:

| ID | 지적 | 판정 | 처리 |
|---|---|---|---|
| R1 | goal 전 오래 정지 → 첫 차분 속도 ≈ 0 → 출발 stall 부풀림(service lag 0.3 이면 11 ≥ N) | **반영** | 세션 재현: 60 s 정지 뒤 첫 변화 1.7e-6 m/s. `dt > hold_max_s` → None (4.1). 램프 시험에 lag 0.3 추가 |
| R2 | 진단 예외가 재시도 틱이면 새 시도 준비가 빠짐 | **반영** | except 안에서 예약·비우기 (5절) |
| R3 | "실패한 틱은 null" 설명이 실제(obs_rx_age·other age·stall 은 채움)와 다름 | **반영** | docstring·5절 문구 정정 (동작은 유지) |
| R4 | 시험 수 시작값 249 는 오기, 베이스 246 | **반영** | 11절 수치 정정 |
| R5 | 새 관측 없는 틱에도 90점 맞춤 재계산(205 µs/틱) | **기각** | 틱 예산의 0.6 %, sim_check 주기 통과. 캐시는 상태를 하나 더 늘린다 |
| R6 | "goal 시작 틱 시각" → 실제는 수락 시각 | **반영** | 2절 문구 |
| R7 | 정확한 경계값 시험 없음 | **변형 반영** | 재검이 제안한 `100.0 + 0.2` 는 float 로 0.20000000000000284 가 되어 시험이 틀린다(세션 확인) → `lost_cause(1, 0.0, 0.2, 0)` 와 `stall_count(0, 0.01, 0.0) == 1` 로 추가 |

PR 본문에 적을 것: 완료 기준 2 의 pre_u5 5건은 문자 그대로는 미충족(기존 문제, 근거 11절) · diff 약 500줄(conventions 권장 300 초과, 값·스키마·진단·시험이 한 단위) · 공용 PC 실기 yaml(레포 밖)은 x_max 600·close 2.3 을 사람이 반영 · B안(지시서 2 % WARN 과 다름).
