# S2-T18 DD — J6 회전 파지 상세 설계

- 근거: [S2T18-hld.md](S2T18-hld.md) r2(사용자 승인 10/14). 결정 번호 D0~D11 은 HLD 와 같다.
- 주관 메모 반영(10/14): ① ψ_home 기본 = goal 수락 때 공구 yaw(키 null), 고정값을 줄 때만 START_ROTATED 검사 — belt_servo 는 voss_config 를 읽지 않으므로(CLAUDE.md 규칙 5) observe_pose 를 상수로 복사하지 않는다 ② ω_meas 는 service pose(0.1 s 계단)에서 잡음이 크다 → `pose_source: joint_states` 를 전제로 하고 **교차 검사로 강제**(rotate.enable 이면 input.pose_lag_ms == 0, 런북 짝 규칙: joint_states ↔ 0, service ↔ 60).
- 원칙: **rotate.enable 이 off(키 없음·false·"null")면 회전 코드는 한 줄도 동작하지 않는다** — TickEvent 기본값·z 하한 None·각속도 기본 0 으로 지금 경로와 같은 값이 나온다. 회귀 기준 = 이 브랜치의 베이스(main + T16, #43 머지 뒤면 그것까지).
- 단위: 내부 계산은 rad·rad/s·rad/s²·s·m. 파라미터·로그는 deg·deg/s·deg/s²·mm(이름 끝에 단위).

---

## 1. 파라미터 (params.py)

| 키 | 종류 | 단위 | 필수 | 개별 검사 | 제안값(sim yaml) |
|---|---|---|---|---|---|
| `rotate.enable` | bool (r1) | - | 아니오 | — | false |
| `rotate.deadband_deg` | float | deg | enable 이면 | > 0 | 4 |
| `rotate.min_deg` | float | deg | enable 이면 | ≥ 0 | 10 |
| `rotate.max_deg` | float | deg | enable 이면 | > 0 | 45 |
| `rotate.n_min` | int | - | enable 이면 | ≥ 1 | 5 |
| `rotate.buffer_n` | int | - | enable 이면 | ≥ 1 | 15 |
| `rotate.r_min` | float | - | enable 이면 | 0 < r ≤ 1 | 0.97 |
| `rotate.decide_max_s` | float | s | enable 이면 | > 0 | 0.5 |
| `rotate.home_tool_yaw_deg` | float (r1, yaml 에 안 적음) | deg | 아니오 | — | 키 없음(= goal 수락 때 공구 yaw) |
| `rotate.start_tol_deg` | float | deg | enable 이면 | > 0 | 3 |
| `rotate.omega_max_dps` | float | deg/s | enable 이면 | > 0 | 60 |
| `rotate.alpha_dps2` | float | deg/s² | enable 이면 | > 0 | 90 |
| `rotate.tol_deg` | float | deg | enable 이면 | > 0 | 1.5 |
| `rotate.omega_floor_dps` | float | deg/s | enable 이면 | ≥ 0 | 3 |
| `rotate.hold_dz_mm` | float | mm | enable 이면 | > 0 | 50 |
| `rotate.settle_s` | float | s | enable 이면 | > 0 | 0.3 |
| `rotate.stall_s` | float | s | enable 이면 | > 0 | 0.6 |
| `rotate.still_dps` | float | deg/s | enable 이면 | > 0 | 2 |
| `rotate.return_min_dz_mm` | float | mm | enable 이면 | ≥ 0 | 10 |

- **"enable 이면 필수"**: enable 이 true 인데 값이 null 이면 `missing` (READY 거부). off 면 null 이어도 된다.
- **교차 검사** (enable 일 때만, `_cross_checks` 에 추가): `hold_dz_mm > z.approach_above_top_mm` · `hold_dz_mm ≥ z.vision_cutoff_above_top_mm + 5` · `deadband_deg ≤ min_deg < max_deg ≤ 90` · `n_min ≤ buffer_n` · `tol_deg < deadband_deg` · **`input.pose_lag_ms == 0`**(joint_states 전제, 주관 메모 ②, 사유 문구 "rotate 는 pose_source joint_states(pose_lag 0) 전제").
- **지문(params_digest)**: enable 이 true 가 아니면 `rotate.` 로 시작하는 키를 전부 뺀다(z.profile 예외 처리와 같은 자리). → sim·현장 yaml 에 rotate 값이 적혀 있어도 off 면 sha 가 지금과 같다.
- 기동 로그 한 줄(z_profile 줄 옆): `rotate off` 또는 `rotate on · deadband 4 · min 10 · max 45 · ω 60 · α 90 · home goal`.

## 2. rotate.py — 순수 함수 (ROS 없음)

| 함수 | 입력 | 출력 | 비고 |
|---|---|---|---|
| `fold_half(a)` | rad | (−π/2, π/2] rad | 180° 대칭 접기. 비전 tracker_logic.fold_yaw 와 같은 규칙(같은 경계 시험값으로 고정) |
| `wrap_pi(a)` | rad | (−π, π] rad | 공구 yaw 차이(360° 감기) |
| `tool_yaw(q)` | (x, y, z, w) | (yaw rad, tilt rad) 또는 None | yaw = atan2(r10, r00), tilt = 공구 z 축과 −Z 사이 각 = acos(−r22). 노름 0·NaN 이면 None. 노름은 정규화 |
| `aggregate(yaws)` | rad 목록 | (target rad, r̄, n) 또는 None(n=0) | 2θ 성분별 중앙값의 반각, r̄ = ‖평균(cos2θ, sin2θ)‖ |
| `decide(agg, belt_yaw, err_along, home, psi0, cfg)` | — | `Decision(verdict, cause, delta, target_abs)` | 3절 판정표 순서대로 첫 매치. verdict ∈ ROTATE·SKIP |
| `yaw_estimate(value, value_stamp, lag, wz_prev, now, max_h)` | rad, s, s, rad/s, s, s | rad | value + wz_prev × min(now − value_stamp + lag, max_h). control.tcp_now 와 같은 모양 |
| `omega_meas(prev, cur)` | (yaw, stamp)×2 | rad/s 또는 None | wrap_pi(Δyaw)/Δt, Δt ≤ 0 이면 None |
| `law(err, cfg_eff)` | rad | rad/s | sign(e)·min(ω_max, max(ω_floor, √(2·α_dec·(\|e\| − tol)))), \|e\| ≤ tol 이면 0. α_dec = 0.8·α_eff |
| `rate_limit(w, w_prev, alpha, dt)` | rad/s | rad/s | \|w − w_prev\| ≤ α·dt |
| `expected_time(delta, w_max, alpha)` | rad | s | 사다리꼴/삼각 해석식 (HLD D4) |
| `alpha_from_ramp(w_meas, elapsed, lag)` | rad/s, s, s | rad/s² 또는 None | \|w_meas\| / (elapsed − lag), elapsed − lag ≤ 0.1 이면 None |
| `rot_step(rs, inp, cfg)` | RotState, RotInputs | (RotState, wz rad/s, RotLog) | 하위 상태 전이 + 각속도. 4절 |

자료형:
- `RotCfg`(frozen): 1절 값을 rad 단위로 + `belt_yaw`(= atan2(belt_dir)), `lag_s`(pose_lag), `extrap_max_s`(pose_extrap_max), `dt_nominal`.
- `RotState`(frozen): `state` 문자열, `cause`, `home` rad, `target` rad|None, `delta` rad|None, `t_start`(회전 시작 s), `t_expected` s, `psi_start` rad, `alpha_eff` rad/s², `still_since` s|None, `settle_drift` bool, `n`·`rbar`(결정 때), `t_done` s|None, `acc_warned` bool.
- `RotInputs`(frozen): `now`, `phase`, `retreat`(is_retreat), `hold_z`, `stopping`, `terminal`, `yaws`(결정용 프레임 목록 rad — COLLECT 때만 의미), `has_field`(BoxTrack 에 yaw 필드가 있나), `psi_raw`(pose 공구 yaw rad|None), `psi_stamp`, `tilt`, `pose_ok`(자세 신선·유효), `w_meas` rad/s|None, `wz_prev`, `dt`, `err_along` m|None, `tcp_z`·`top_z` m|None.
- `RotLog`(frozen): 로그 키 값(7절).

## 3. 결정 판정표 (`decide`, 위에서부터 첫 매치)

| # | 조건 | verdict | cause |
|---|---|---|---|
| 1 | BoxTrack 에 yaw 필드 없음 | SKIP | NO_FIELD |
| 2 | 공구 자세 없음·tilt > 5° | SKIP | NO_POSE_YAW |
| 3 | home 고정값이 있고 \|wrap(ψ0 − home)\| > start_tol | SKIP | START_ROTATED |
| 4 | n < n_min | (계속 모음 — decide 안 부름) | — |
| 5 | r̄ < r_min | SKIP | SPREAD |
| 6 | err_along > 0 (박스가 이미 TCP 하류) | SKIP | DOWNSTREAM |
| 7 | \|Δ\| ≤ max(deadband, min_deg) | SKIP | SMALL |
| 8 | \|Δ\| > max_deg | SKIP | OUT_OF_RANGE |
| 9 | 그 밖 | ROTATE | — |
- Δ = fold_half(target − belt_yaw). +π/2 는 그대로 + 방향(fold 규칙).
- home = 고정값(deg→rad) 또는 goal 수락 때 ψ0. target_abs = home + Δ.
- 결정은 COLLECT 의 매 틱에 n ≥ n_min 이 되면 한 번. now − goal 시작 > decide_max_s 인데 n < n_min 이면 SKIP/NO_YAW.

## 4. 하위 상태 전이표 (`rot_step`, 매 틱 한 번, 위에서부터 첫 매치)

공통: `stopping` 또는 `terminal` 이면 wz = 0 (상태는 바꾸지 않음, 끝 틱이면 RETURN_INCOMPLETE 판단만). 모든 wz 는 마지막에 `rate_limit` 을 거친다(0 으로 가는 것도 — gateway 램프와 같은 모양. 단 stopping·terminal 의 0 은 즉시).

| 현재 | 조건 | 다음 | wz | cause/로그 |
|---|---|---|---|---|
| OFF | (enable off — 노드가 rot_step 을 부르지 않음) | OFF | 0 | — |
| COLLECT | decide → SKIP | SKIP | 0 | 판정표 cause |
| COLLECT | decide → ROTATE | ROTATING (t_start = now, psi_start = ψ, t_expected = expected_time) | law | — |
| COLLECT | 시간 초과 | SKIP | 0 | NO_YAW |
| COLLECT | 그 밖 | COLLECT | 0 | — |
| ROTATING | phase ∉ {PREPARE, TRACK} (안전망 — DESCEND 는 rot_ready 없이는 못 가므로 정상에선 없음) | STOPPING | 0 | PHASE |
| ROTATING | pose_ok 아님 | STOPPING | 0 | NO_POSE_YAW |
| ROTATING | now − t_start > 1.5·t_expected(α_eff) + 0.5 | STOPPING | 0 | TIMEOUT |
| ROTATING | now − t_start ≥ stall_s 이고 \|wrap(ψ_raw − psi_start)\| < 1° | STOPPING | 0 | STALL |
| ROTATING | \|e\| ≤ tol 이고 \|w_meas\| < still | SETTLING (still_since = now) | 0 | — |
| ROTATING | 그 밖 | ROTATING | law(e) | e = wrap(target − ψ_est). 램프 중 α 감시(아래) |
| SETTLING | \|w_meas\| ≥ still | SETTLING (still_since = now) | 0 | — |
| SETTLING | now − still_since ≥ settle_s | DONE | 0 | \|e\| > tol 이었으면 settle_drift = True(로그 SETTLE_DRIFT, 쫓지 않음) |
| STOPPING | \|w_meas\| < still 이 2틱 연속 | FALLBACK | 0 | cause 유지 |
| DONE·SKIP·FALLBACK | 되돌리기 조건(아래) 이고 \|wrap(ψ − home)\| > tol | RETURNING | law(home − ψ_est) | — |
| RETURNING | \|e_home\| ≤ tol | RETURNED | 0 | — |
| RETURNING | 되돌리기 조건이 깨짐(예: hold_z 시작) | RETURNING | 0 (대기) | — |
| RETURNING | 그 밖 | RETURNING | law(e_home) | 같은 STALL·TIMEOUT 감시 → STOPPING(RETURN_STALL·RETURN_TIMEOUT) |

- **rot_ready**(fsm 에 넘김) = 상태 ∈ {OFF, SKIP, DONE, FALLBACK, RETURNING, RETURNED}. COLLECT·ROTATING·SETTLING·STOPPING 이면 False → TRACK 에서 DESCEND 로 못 감(입력·REACH 검사는 그대로 먼저).
- **z 하한**: 상태 = ROTATING 이고 phase ∈ {PREPARE, TRACK} 일 때만 `top_z + hold_dz`. STOPPING 은 ROTATING 과 같은 하한(아직 도는 중이라 시야 보험 유지).
- **되돌리기 조건**: (phase == LIFT 이고 retreat 아님) 또는 (retreat 이고 hold_z 아님), 그리고 tcp_z ≥ top_z + return_min_dz. 재시도(PREPARE 로 돌아감)는 조건 밖 → DONE 유지(박스 각은 그대로라고 봄, 로그로 확인).
- **α 감시(ACC_MISMATCH)**: ROTATING 에서 elapsed ∈ [0.3 s, ω_max/α_param] 이고 w_meas 가 있으면 α_meas = alpha_from_ramp. α_meas < 0.6·α_param 이면 α_eff = max(α_meas, 5°/s²), acc_warned = True(경고 1회, 로그 cause_warn=ACC_MISMATCH). 이후 law·TIMEOUT 은 α_eff 로.
- **끝 틱**: terminal 이고 상태가 RETURNING 이거나 (DONE·FALLBACK 이고 \|ψ − home\| > tol) 이면 로그 `rot_cause = RETURN_INCOMPLETE`.

## 5. fsm.py · control.py 변경 (최소)

- `fsm.TickEvent` 에 `rot_ready: bool = True`(기본 = 회전 없음과 같다). `_advance` 의 `if phase == TRACK and ev.aligned:` → `ev.aligned and ev.rot_ready`. 다른 줄은 그대로.
- `control.command(..., z_floor: float | None = None)` → `z_plan` 결과 z 목표가 있고 z_floor 가 있으면 `max(z_t, z_floor)`. 기본 None 이면 지금과 같은 값(시험으로 고정).

## 6. belt_servo.py 변경

| 자리 | 변경 |
|---|---|
| 기동 | `self._rot_on = params rotate.enable is True`. RotCfg 생성(on 일 때만). 기동 로그 한 줄 |
| `_on_box` | `_rot_on` 이고 `getattr(msg, "yaw_valid", None)` 이 True·position valid·yaw 유한 → `self._yaw_hist[track_id]`(deque maxlen buffer_n)에 (stamp, yaw) 추가. 필드 없음 여부는 `self._yaw_field = hasattr(msg, "yaw_valid")` 로 기억 |
| `_prune_boxes` | 지우는 트랙의 `_yaw_hist` 도 지움 |
| `_on_pose` | `_rot_on` 이면 tool_yaw(q) → `self._yaw_value`(값이 바뀐 첫 stamp 유지, pose_value_stamp 와 같은 규칙)·`self._yaw_prev_value`·tilt |
| goal 수락 | `ctx.rot = RotState(COLLECT, home = 고정값 또는 ψ0)` (`_rot_on` 아니면 None). ψ0 없으면 decide 에서 NO_POSE_YAW |
| `_build_event` | `_rot_on` 이면 RotInputs 를 만들어 `rot_step` → `ctx.rot`, `ctx.wz`, `ctx.rot_log`. TickEvent 에 `rot_ready`. try/except: 예외면 ctx.rot = STOPPING(INTERNAL), wz 0, 에러 로그 1회(goal 은 계속 — 진단과 같은 규칙) |
| `_tick_goal` | `control.command(..., z_floor=rot_z_floor)` · `self._publish(vel, ctx.wz)` |
| `_publish(vel, wz=0.0)` | `msg.twist.angular.z = wz`. `self._last_wz = wz`. **다른 모든 호출(ZERO·_safe_zero·_tick_hold)은 인자를 주지 않으므로 0** |
| `_tick_values` | 7절 로그 키 (`_rot_on` 아니면 전부 None) |
| `rot_step` 의 stopping·terminal | fsm 전이 **뒤** 상태로 판단해야 하므로 rot_step 은 `_tick_goal` 에서 fsm.step 다음, command 전에 다시 wz 만 0 으로 덮는다(전이표 공통 줄) |

순서(한 틱): `_build_event`(rot_step → rot_ready) → `fsm.step` → (tr.terminal·stopping 이면 wz = 0) → `command(z_floor)` → `_publish(vel, wz)` → 로그.

## 7. 로그 키 (log_schema.py)

틱(전부 enable off 면 null): `rot_state`, `rot_cause`, `yaw_target_deg`(박스 목표 각, 베이스), `rot_delta_deg`(Δ), `tool_yaw_deg`(pose 원값), `tool_yaw_est_deg`(외삽), `rot_err_deg`, `wz_cmd_dps`, `wz_meas_dps`, `rot_n`, `rot_rbar`, `rot_time_s`(회전 시작→DONE/FALLBACK).
시도(부분집합): `rot_state`, `rot_cause`, `rot_delta_deg`, `rot_time_s`.
→ 틱 12 키·시도 4 키 증가(시험의 개수 단언 갱신). #43 의 2 키는 그 PR 머지 뒤 리베이스로 합친다.

## 8. fake_box · sim.launch · sim_check

- `fake_box` 파라미터: `yaw_deg`(기본 0 = 지금과 같음), `yaw_mode`: `valid`(기본) | `invalid`(yaw_valid=false, yaw_base 0). BoxTrack `yaw_base = fold_half(belt_yaw + yaw_deg)`. "필드 없음(NO_FIELD)"은 메시지 타입이 같아 sim 으로 흉내 낼 수 없으므로 단위 시험(SimpleNamespace)에서만 확인한다.
- `sim.launch`: 인자 `rotate`(""/true) → 덮어쓰기 yaml 에 `rotate.enable: true`, `box_yaw_deg` → fake_box `yaw_deg`. sim yaml(`belt_servo_sim.yaml`)에는 rotate 제안값을 넣고 `enable: false`(지문에서 빠짐 → 기존 sha 유지 확인).
- `sim_check` 새 케이스(프로필 `rotate`):
| case | box_yaw | rotate | 기대 |
|---|---|---|---|
| `rotate_stall` | 30° | on | SUCCEEDED/OK, 틱에 ROTATING → STOPPING → FALLBACK, rot_cause STALL, gateway "angular" 자름 경고 = **예상 결과**(J 판정에서 자름 0 기준 제외) |
| `rotate_small` | 3° | on | OK, rot_state SKIP, cause SMALL, wz 전부 0 |
| `rotate_invalid` | 30°, yaw_mode invalid | on | OK, SKIP/NO_YAW |
- 기존 프로필(pre_u5·grasp) 전부: rotate 인자 없이 = 지금과 같은 기대값·종료 코드(회귀).

## 9. 시험 목록 (새 시험 ≥ 10)

**test_rotate.py (순수 함수)**
1. `fold_half` 경계: +π/2 → +π/2, −π/2 → +π/2, ±π, 0, 3π/4 → −π/4 (tracker_logic 규칙과 같은 표).
2. `wrap_pi` 경계.
3. `tool_yaw`: 관측 자세 ZYZ(85.25, −179.07, −6.03) 쿼터니언 → yaw −88.72°±0.01, tilt 0.93°±0.01. rz +5° → −93.72°(D10 부호 고정). 노름 0 → None.
4. `aggregate`: ±89° 섞임 → 90° 근처(0° 아님), 한 프레임 튐(+40° 하나) → 영향 작음, 흩어짐 → r̄ < 0.97.
5. `decide` 판정표 9줄 각각 한 경우씩(첫 매치 순서 포함).
6. `law`: \|e\| ≤ tol → 0, 큰 e → ω_max, 감속 구간 √ 식, floor.
7. `rate_limit`·`expected_time`(HLD D4 표 값 재현: 45° ω60 α90 연속식 1.417 s).
8. `yaw_estimate`: 외삽 지평 상한, wz 0 이면 원값.
9. `rot_step` 이산 시뮬(가짜 로봇 = 지연 24 ms + 자체 α 로 적분): α 일치 45° → 끝 각 오차 ≤ tol, 지나침 ≤ tol, 시간 ≈ 1.30 s ± 0.1.
10. `rot_step` α 불일치(로봇 α 10, 설정 90) → ACC_MISMATCH 경고 + 지나침 ≤ 3°(감시 없을 때 16° 와 대비) 또는 TIMEOUT→STOPPING.
11. `rot_step` STALL(로봇이 안 돎) → stall_s 뒤 STOPPING → 2틱 정지 확인 → FALLBACK, rot_ready 순서(STOPPING 동안 False).
12. `rot_step` 관성(로봇이 0 지령 뒤 α 로 감속) → STOPPING 이 멈출 때까지 유지.
13. SETTLING drift → DONE + settle_drift, 쫓지 않음(wz 0).
14. 되돌리기: LIFT·tcp_z 조건, hold_z 중 대기, 재시도(PREPARE)면 DONE 유지, 끝 틱 RETURN_INCOMPLETE.
15. stopping·terminal → wz 0 즉시.

**test_fsm.py**: 16. TRACK + aligned + rot_ready False → TRACK 유지, True → DESCEND. 기본 TickEvent → 지금과 같은 전이(기존 시험 전부 그대로).
**test_control.py**: 17. z_floor None → 기존 값 동일, z_floor 가 있으면 PREPARE·TRACK z 목표 = max.
**test_params.py**: 18. enable off 면 rotate 키 null 이어도 READY, sha = rotate 키 없을 때와 같음(값을 적어도 같음). 19. enable on + null → missing. 20. 교차 검사 각 줄(pose_lag 60 이면 invalid 사유 문구).
**test_log_schema.py**: 21. 키 개수·순서, 시도 ⊆ 틱.
**test_fake_box.py**: 22. yaw_deg → yaw_base(fold), yaw_mode invalid.
**test_action_e2e.py** (FakeClient 에 각속도 적분·α·지연 옵션 추가 — 시험 파일 안에서만): 23. rotate on + 30° 박스 + 적분 → OK, 틱에 ROTATING→SETTLING→DONE, DESCEND 진입 때 \|rot_err\| ≤ tol, LIFT 에서 RETURNED, servo_cmd angular.z ≠ 0 은 PREPARE·TRACK·LIFT 틱에서만. 24. rotate on + 적분 없음 → STALL 폴백 → OK. 25. **rotate off 회귀**: 같은 시나리오에서 모든 servo_cmd angular = 0, 틱 rot 키 null, 결과 동일. 26. 취소 중(ROTATING) → 다음 발행부터 angular 0.
**test_sim_check.py**: 27. 새 Expect·case 표 일관성.

## 10. 에러 경로 요약
| 경로 | 각속도 | 상태 |
|---|---|---|
| 취소(stopping) | 즉시 0 | 유지 |
| goal 끝(terminal)·0 유지·예외 `_safe_zero` | 0 (`_publish` 기본값) | 끝 틱 RETURN_INCOMPLETE 판단 |
| rot_step 예외 | 0 | STOPPING(INTERNAL) → 정지 확인 뒤 FALLBACK |
| 입력 끊김·LOST·REACH | 기존 fsm 이 goal 을 끝냄 → 0 | — |
| pose 끊김 | ROTATING 이면 STOPPING(NO_POSE_YAW). pose_stale 이 길면 기존 STALE_INPUT 이 먼저 끝냄 | — |

## 11. 바뀌지 않는 것 (회귀로 확인)
액션 인터페이스·feedback phase·reason·QoS, xy 제어·clamp·사다리꼴 z, 그리퍼 흐름, 0 유지, 로그 파일 구조(키만 추가), off 일 때 params_sha.

## 12. r1 변경 (pseudo 재검 반영, 10/14 — 이 절이 위 본문보다 우선)
Opus 독립 재검(필수 10·권장 12)을 세션이 코드로 확인한 뒤 반영했다. 상세 의사코드는 [S2T18-pseudo.md](S2T18-pseudo.md) 11절.
- **로그 스냅샷**: 회전 로그 키 12개를 `ROT_KEYS` 로 묶고 `_snapshot_values`(0 유지 틱·예외 GOAL_END)에도 넣는다 — 빠지면 `make_tick` 이 예외를 내 off 에서도 행이 사라진다.
- **파라미터 종류**: `bool` kind 를 새로 둔다(rotate.enable). `home_tool_yaw_deg` 는 `float` 선택 키이고 yaml 에는 적지 않는다(없으면 goal 수락 때 공구 yaw). rotate_on = 값이 bool True 일 때만. config/belt_servo.yaml·real.example 에도 rotate 키(enable false, 나머지 null)를 넣어 세 yaml 키 집합을 맞춘다(T-L12).
- **sim**: rotate 케이스 덮어쓰기에 `input.pose_lag_ms: 0`(교차 검사 전제), `_wants_overrides` 에 rotate 추가. gateway '자름' 판정은 5 s 통계 줄의 angular 수로.
- **각속도 출력**: law 출력만 `rate_limit(cfg.alpha)` 를 거친다. STOPPING·대기·PHASE 이탈·종료의 0 은 **즉시 0**(VERIFY 각속도 0 — 13절 r2 에서 되돌리기는 VERIFY 에서도 낸다). α_eff 는 law·TIMEOUT 에만.
- **α 감시**: 지령이 rate_limit 에 막혀 오르는 틱이 2틱 이어질 때만 잰다(√ 감속 구간 제외 — 일치일 때 Δ 10~20° 오경보 제거).
- **되돌리기**: 전용 필드(ret_*), 1회만, SKIP 은 되돌리지 않음, **LIFT 에서만**(VERIFY 는 0). 4절 "VERIFY 중에도" 는 없앤다. → **13절 r2 에서 LIFT·VERIFY 로 바뀜**(코드 기준).
- **예외**: rot_step 예외면 그 goal 의 회전을 끄고(wz 0) 노드가 측정 각속도 정지 2틱을 확인한 뒤 진행. geo None 방어.
- **입력**: pose_ok 나이 ≤ pose_extrap_max(0.2 s), omega_meas 는 pose 메시지가 0.05 s 안에 왔을 때만 "정지 = 0", 끊겼으면 None. dt 는 이번 틱 effective_dt. COLLECT 는 판정표 1~3(필드·자세·시작 자세)을 프레임 수보다 먼저, 필드 여부를 아직 모르면 대기.
- **시험**: e2e 박스는 TCP 60 mm 상류에서 시작, 시험 쿼터니언 = Rz(ψ)·Rx(π). 시험 #9 시간 = SETTLING 진입 1.40~1.60 s.

## 13. r2 변경 (Fable 5.1 전 과정 독립 재검 반영, 10/14 — 12절보다 우선)
상세: [S2T18-pseudo.md](S2T18-pseudo.md) 12절(16건 중 15건 채택, 1건 기각).
- **α 감시**: 단일 표본 |ω|/(경과 − lag) → **두 측정 각속도의 기울기**(간격 ≥ 0.1 s). 지연이 상쇄돼 α 일치에서 오경보 0, α45·10 정확 검출(재검 스크립트 재실행으로 확인).
- **TIMEOUT**: cfg.alpha 기준(α_eff 로 늘리지 않음). **SETTLING 상한** 1.0 s → DONE + SETTLE_TIMEOUT. FALLBACK 의 t_done 은 비어 있을 때만.
- **home 기준(home_ref)**: 고정값(`rotate.home_tool_yaw_deg`)이 없으면 **노드 기동 뒤 첫 goal 의 공구 yaw** 를 기억하고, 매 goal 시작 자세를 그것과 start_tol 로 비교(START_ROTATED). "매 goal 전 OBSERVE"(sort_manager G0 임시 규칙)에 기대지 않는다. voss_config 를 읽지 않는 규칙 5 도 지킨다.
- **되돌리기**: LIFT 와 **VERIFY**(사다리꼴 LIFT 는 +10 뒤 ≈0.9 s 라 45° 회귀 1.47 s 에 모자람). D0 interface 문안도 "PREPARE·TRACK·LIFT·VERIFY" 로.
- **정지 판정**: YAW_HOLD_MAX 0.15 s(service 갱신 0.1 s 보다 길게). `input.pose_lag_ms == 0` 교차 검사는 "joint_states 강제"가 아니라 **belt_servo yaml 짝 검사**다(gateway pose_source 는 run 전제·기동 로그로 확인).
- **단순화**: OFF 상태 삭제(off 면 ctx.rot = None), sim 의 rotate_invalid·fake_box yaw_mode 삭제(NO_YAW 는 단위·e2e).
- **문구**: 머리말 "off 면 한 줄도 동작 안 함" → "off 면 기존 로그 열 값·제어 경로·params_sha 가 같다(새 로그 열은 null, `_yaw_field` 기록만 실행)".
- 기각: deadband·min_deg 통합 — 1단계(min 10)→5단계(min = 데드밴드) 전환을 yaml 만으로 하려면 둘 다 필요하고, tol < deadband 검사의 기준이다.

## 14. 최종 재검 반영 (Opus 5.5 PR 전 독립 재검, 10/14 — 13절보다 우선)
재검자가 코드·sim·직접 만든 가짜 gateway 스모크(goal 20)·변이 시험(11건)으로 본 결과를 세션이 다시 재현·확인한 뒤 반영했다.
- **α 감시 표본**: 측정 각속도가 지령과 **같은 방향**이고 `still` 이상일 때만 잰다. 지령 지연 ≥ 0.1 s 에서 (1) 출발 전 정지 표본 (2) 목표를 지나친 뒤 되돌아올 때 아직 앞 방향으로 감속하는 표본이 α 를 거의 0 으로 재 ACC_MISMATCH 오경보 → α_eff 5°/s² 로 떨어지던 것을 막는다(지연 24~150 ms 전 구간 오경보 0, 느린 로봇 45·10°/s² 검출은 그대로 *(재현)*).
- **예외로 끈 goal**: `_rot_inputs` 를 거치지 않는 `_rot_dead_tick`(각속도 0 + 측정 정지 2틱)으로 — `_rot_inputs` 안 예외가 반복되면 TRACK 에 묶이던 경로를 없앤다.
- **end_cause**: ROTATING·SETTLING 에서 끝나도(회전 중 취소) 손목이 기준에서 tol 밖이면 RETURN_INCOMPLETE.
- **13절 home 문구의 범위**: "매 goal 전 OBSERVE 에 기대지 않는다" 는 **기준 각을 정하는 일**에 대한 말이다. 손목이 돌아간 채 끝난 goal 뒤의 **회복**은 sort_manager 의 OBSERVE 복귀에 기댄다(run.md ⑬). PREPARE 에서 기준 각으로 되돌리는 안은 새 동작이라 이 단위에 넣지 않는다.
- **지령 지연 보상 없음**: 지연 80 ms 를 넘으면 지나침이 tol 을 넘는다 → run.md ⑫ 측정. 보상(외삽 지평에 지령 지연 추가)은 측정 뒤 별도.
- **시험**: 짝수 개 ±89° 2θ 중앙값, `_push_yaw` 무효 프레임, `_try_home_ref` 유효 pose 조건, 정지 2틱, 지연 100·120 ms 오경보 없음, 회전 중 취소 end_cause — 재검이 살아남았다고 보고한 변이 4건과 새 수정 2건을 시험이 잡는 것을 변이로 확인.
- 기각·보류: `_rot_ever` 는 지금 구조에서 결과를 바꾸지 않는 방어 조건(기준 각이 None 으로 돌아가지 않음)이지만, 기준 규칙의 의도를 코드에 남기는 값이라 그대로 둔다. rotate 키가 범위 밖이면 off 여도 READY 거부 — 형식 검사는 off 여도 하는 기존 규칙(다른 블록과 같음)이라 그대로. 로그 키 목록 두 곳(rotate·log_schema)은 순서 일치를 시험으로 고정해 두었다.

## 15. #54 리뷰 반영 (김학민 10/14 — 14절보다 우선)
세션이 각 지적을 코드·S2-T17 브랜치(옛 `_2` #56 → #164, `33d62c9`)로 확인한 뒤 반영했다.
- **STOPPING 상한 `STOP_CAP` 1.0 s** (리뷰 4, 재리뷰로 정정): **마지막으로 "돈다"고 잰 뒤(처음엔 들어온 뒤) 측정 없이** 1.0 s 가 지나면 FALLBACK + 경고 `STOP_UNCONFIRMED`(원래 원인은 유지). 측정이 계속 "돈다"면(예: gateway α 가 느려 늦게 섬) 진행하지 않고 각속도 0·z 하한을 유지한 채 정지 2틱을 기다린다 — 그동안 박스가 흘러가면 x 끝·LOST 가 goal 을 끝낸다. goal 을 끝내는 안은 TrackAndGrasp 종료 사유(인터페이스 어휘)를 새로 만들어야 해 택하지 않았다. 예외로 끈 goal(`_rot_dead_tick`)도 같은 규칙. 1.0 s = 60°/s 를 α 90 으로 세우는 0.67 s + pose 정지 판정 여유.
- **STALL 이동 창** (리뷰 5): 시작 각 기준(1° 이상 돈 뒤 멈추면 TIMEOUT 까지 모름) → "계속 돌라고 했는데(|지령| ≥ ω 바닥) 최근 stall_s 동안 1° 미만" 으로. 1° 움직이거나 거의 0 을 지령하면 기준을 지금으로 옮긴다. ROTATING·RETURNING 같은 함수(`_stall_window`), `ret_psi_start` 필드는 없앴다.
- **sim_check** (리뷰 2·3·7): 케이스마다 gateway 각속도 켬/끔(`gw_angular`, sim.launch `gw_angular:=true` → gateway `servo_angular:=true`). `rotate_stall` 은 끔이어야 성립(켬 기동 줄이면 FAIL), 새 `rotate_ok`(프로필 `rotate_gw`, S2-T17 gateway 필요 — 없으면 UNKNOWN) = ROTATING→SETTLING→DONE→RETURNING→RETURNED·첫 DESCEND |rot_err| ≤ 1.5°·`ang_speed`·`yaw_limit` 0. 자름은 `angular`·`ang_speed`·`yaw_limit` 키별로 센다. J-ang 은 gateway 끔 + 셋 다 0. 켬이면 J-gw: belt_servo ω·α ≤ gateway 기동 줄 ω·α.
- **문서만** (리뷰 6·8·9·run.md): 기준 각은 `home_tool_yaw_deg` null 유지(같은 값을 두 곳에 두지 않음) + run.md ⑮ 로그 대조. 되돌리기 판정은 run.md 4.2 에 start_tol 기준. yaml α 주석. run.md ①②③ 확인 줄, ⑩ USB 고정 ❌, E2 부호 실측.
- **보류 — 리뷰 1 (회전 대기 중 시야)**: 측정 ② B45 에서 정렬 자리(TCP X −119.7·Z 151, 박스 +45°) 검출 0 보고. HLD D2-2 "+46 이면 보인다" 는 hand_eye 모델 계산. 측정 ② 정확도에 의문이 있어 설계는 바꾸지 않고(사용자 10/14), 4단계 첫 회 틱 로그로 확인한 뒤 실제로 LOST 가 나면 설계 단위로 다룬다(후보: 회전 중 xy 목표 오프셋 / 회전 대기 중 LOST 를 FF 예측으로) — run.md ⑭.
