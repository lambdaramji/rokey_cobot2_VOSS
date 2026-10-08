# U1 belt_servo 뼈대 — Detail design (승인 10/08)

HLD: [U1-hld.md](U1-hld.md). 팀 계약은 docs/interfaces 가 우선이다. 이 문서의 제안값은 pending #4 승인 전 "제안값"이다.

## 0. 결정 요약

| 항목 | 결정 |
|---|---|
| READY | 파라미터 검사만. gripper/stop 서비스 존재는 호출 때 실패로 처리 |
| 틱 로그 구간 | goal 진행 중 + 종료 후 0 유지 구간. IDLE 틱은 쓰지 않음 |
| `zero_hold_s` | 0.5 s 제안. 이 구간에는 새 goal reject |
| feedback | `phase` 만 (err_u/err_v 는 #102·PR #103 으로 삭제 제안, U1 은 건드리지 않음) |
| stop 호출 | U1 노드에 넣는다(U3 의 CANCELED 시나리오에 필요) |
| 재시도 개방 | goal 안 재시도는 다시 벌린다(grip_detected 인데 폭 범위 밖이어도) |
| box 보관 | track_id 별 사전, 구독 depth 5, 같은 트랙 stamp 역행 버림 |
| 비전 사각 구간 | GRASP·LIFT·VERIFY, 그리고 DESCEND 중 TCP z ≤ 박스 윗면 z + cutoff. 이 구간은 box LOST/STALE 을 보지 않음. 비전 필요 구간으로 돌아오면 시계를 다시 셈 |
| reason / cause | reason 은 계약 7종 그대로, 세부 원인은 로그 `cause` |
| config_version 없음 | READY 유지, 경고만 |
| 내부 예외 | ABORTED + DEVICE_ERROR, cause `INTERNAL_EXCEPTION` |
| depth 5 와 topics.md | PR 본문에만 적음(구독 depth 는 소비자 재량) |

## 1. params.py

| 이름 | 타입·단위 | 필수 | belt_servo.yaml 값 | 검사 |
|---|---|---|---|---|
| `belt.speed_cmps` | float, cm/s | ✅ | (bringup) | > 0 |
| `belt.direction_base` | float[3] | ✅ | (bringup) | 길이 1 ± 0.01 |
| `gripper.pre_open_mm` | float, mm | ✅ | (bringup) | > 0 |
| `gripper.grasp_width_mm` | float, mm | ✅ | (bringup) | > 0, < pre_open |
| `gripper.force_n` | float, N | ✅ | (bringup) | > 0 |
| `timing.latency_offset_ms` | float, ms | ✅ | (bringup) | 숫자 (0 유효) |
| `config_version`·`config_sha256` | str | ❌ | (bringup) | 없으면 경고 |
| `grasp.tcp_z_below_top_mm` | float, mm | ✅ | 19 | > 0 |
| `grasp.hold_width_min_mm`·`_max_mm` | float, mm | ✅ | null (제안 39.5·41.5) | > 0, min < max |
| `reach.x_min_mm`·`x_max_mm` | float, mm | ✅ | −107·638 | min < max |
| `control.kp_per_s` | float, 1/s | ✅ | null | ≥ 0 |
| `limits.max_speed_mps` | float, m/s | ✅ | null (제안 0.08) | > 0 |
| `limits.max_acc_mps2` | float, m/s² | ✅ | null (제안 0.1) | > 0 |
| `z.approach_height_mm` | float, mm | ✅ | null | > cutoff |
| `z.lift_height_mm` | float, mm | ✅ | null | > 0 |
| `z.vision_cutoff_above_top_mm` | float, mm | ✅ | null (제안 10) | ≥ 0 |
| `input.stale_timeout_s` | float, s | ✅ | null (제안 0.3) | > 0 |
| `input.lost_timeout_s` | float, s | ✅ | null (제안 0.5) | > 0 |
| `input.blind_entry_max_age_s` | float, s | ✅ | null (제안 0.1) | > 0 |
| `stop_timeout_s` | float, s | ✅ | 1.0 (제안) | > 0 |
| `rate_hz` | float, Hz | ✅ | 30 | > 0 |
| `zero_hold_s` | float, s | ✅ | 0.5 (제안) | ≥ 0 |
| `log.dir` | str | ✅ | `data/servo` | 비어 있지 않음 |

YAML 의 null 은 표시용이다. launch(U3)는 null 키를 넘기지 않고, 노드는 값이 안 온 파라미터를 미측정으로 본다.

함수: `ParamSpec`, `PARAM_SPECS`, `vector_norm`, `check_params(values) → ReadyReport(ready, missing, invalid)`, `params_digest(values) → sha256`, `ready_log_line(report)`.

## 2. fsm.py

- `FsmState(phase, attempts, stopping)`, `start() → (FsmState(PREPARE, 0, False), actions=("GRIPPER_OPEN",))`
- `TickEvent`: `cancel_requested`, `stop_result`(None|OK|FAILED|TIMEOUT|UNAVAILABLE), `box_lost`, `box_stale`, `pose_stale`, `vision_blind`, `reach`(None|X_MIN|X_MAX), `aligned`, `at_grasp_height`, `at_lift_height`, `gripper`(GripperReply|None)
- `GripperReply(ok, width_mm, grip_detected, message)`, `judge_grip(reply, w_min, w_max) → HELD|NOT_HELD|DEVICE_ERROR` (+cause)
- `Transition(state, terminal, reason, cause, grasped, actions, attempt_ended)`
- `step(state, event, w_min, w_max) → Transition`
- `is_vision_blind(phase, tcp_z_m, box_top_z_m, cutoff_mm) → bool`
- `input_flags(now, last_box_rx, last_valid_rx, latest_invalid, last_pose_rx, goal_start, vision_since, blind, lost_timeout, stale_timeout) → (box_lost, box_stale, pose_stale)` — 수신 시각 기준(MC-031: stamp 나이만으로 판단하지 않음)

전이표(위에서부터 처음 맞는 한 줄):

| # | 조건 | 적용 | 결과 (cause) |
|---|---|---|---|
| 1 | stopping, stop_result=OK | 전부 | 끝 CANCELED (STOP_OK) |
| 2 | stopping, stop_result 그 밖 | 전부 | 끝 DEVICE_ERROR (STOP_FAILED·STOP_TIMEOUT·STOP_UNAVAILABLE) |
| 3 | stopping, 응답 대기 | 전부 | 그대로 |
| 4 | cancel_requested | 전부 | stopping, 행동 REQUEST_STOP |
| 5 | gripper → DEVICE_ERROR | 전부 | 끝 DEVICE_ERROR (GRIPPER_<message> 또는 GRIPPER_NOT_OK) |
| 6 | pose_stale | 전부 | 끝 STALE_INPUT (POSE_MISSING) |
| 7 | box_stale, not vision_blind | PREPARE·TRACK·DESCEND | 끝 STALE_INPUT (BOX_INVALID) |
| 8 | box_lost, not vision_blind | PREPARE·TRACK·DESCEND | 끝 LOST (BOX_MISSING) |
| 9 | reach | PREPARE·TRACK·DESCEND·GRASP | 끝 OUT_OF_REACH (REACH_X_MIN·X_MAX) |
| 10 | PREPARE + 개방 응답 ok (message OK) | | → TRACK |
| 11 | TRACK + aligned | | → DESCEND |
| 12 | DESCEND + at_grasp_height | | → GRASP, attempts+1, GRIPPER_CLOSE |
| 13 | GRASP + HELD | | → LIFT |
| 14 | GRASP/VERIFY + NOT_HELD, attempts < 3 | | → PREPARE, GRIPPER_OPEN, attempt_ended (NOT_DETECTED·WIDTH_OUT·DROPPED) |
| 15 | GRASP/VERIFY + NOT_HELD, attempts = 3 | | 끝 GRASP_FAILED (같은 cause) |
| 16 | LIFT + at_lift_height | | → VERIFY, GRIPPER_VERIFY |
| 17 | VERIFY + HELD | | 끝 OK, grasped |

## 3. log_schema.py

틱(`kind="tick"`): `kind, goal_id, track_id, attempt, phase, stopping, terminal, box_stamp_s, pose_stamp_s, t_calc_s, t_pub_s, position_base_m, position_valid, position_source, calib_version, tcp_pose_m, predicted_m, tcp_target_m, error_m, belt_vel_mps, belt_speed_mps, cmd_vel_mps, clamped, vision_blind, reason, cause, grasped, gripper, config_version, config_sha256, params_sha256`

시도(`kind="attempt"`, 틱의 부분집합): `kind, goal_id, track_id, attempt, phase, terminal, t_calc_s, reason, cause, grasped, belt_speed_mps, gripper, position_source, calib_version, config_version, config_sha256, params_sha256`. 시도 종료(attempt_ended)와 goal 종료(terminal) 때 쓴다.

모르는 값은 null(NaN 금지). 파일 `data/servo/ticks/servo_ticks_YYYYMMDD_HHMMSS.jsonl`, `data/servo/attempts/servo_attempts_YYYYMMDD_HHMMSS.jsonl`.

## 4. 테스트 (약 36개)

- test_params: 정상 ready · null → missing · 미전달 → missing · 노름 0.5 거부 · 노름 1.005 통과 · x_min ≥ x_max 거부 · approach ≤ cutoff 거부 · 지문 결정적 · config_version 없어도 ready
- test_fsm: 정상 6단계 OK · TRACK LOST · DESCEND 사각 LOST 무시 · DESCEND 경계 위 LOST · GRASP LOST 무시 · OUT_OF_REACH · box STALE(BOX_INVALID) · 사각 구간 pose STALE(POSE_MISSING) · 취소 → CANCELED · 취소 → stop 실패·timeout·미가용 → DEVICE_ERROR · 취소가 LOST 보다 우선 · grip_detected=False 재시도 · 폭 범위 밖 재시도 · 3회 → GRASP_FAILED · VERIFY 떨어뜨림 재시도 · gripper ok=False → DEVICE_ERROR · is_vision_blind 경계 · input_flags 재시도 후 시계 다시 셈 · input_flags 메시지 없음은 STALE 아닌 LOST
- test_log_schema: 틱 키 전체 · 누락 ValueError · 시도 ⊂ 틱 · JSON 왕복·NaN 없음 · JsonlWriter tmp_path
- test_node: 파라미터 없이 생성 → ready=False·missing · READY 아님 → goal REJECT
