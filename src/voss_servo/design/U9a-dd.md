# U9-a DESCEND LOST 경주 해소 — Detail design

- 이슈: #37 (T28) · 브랜치 `feat/37-voss_servo-u9a-descend-lost` (베이스 U9-c `5604904`, 처음 aed51d5 에서 시작해 10/12 리베이스) · 작성 2026-10-12
- 상태: **DD 승인(박병후, 10/12)**. 앞 단계: [U9a-hld.md](U9a-hld.md) (승인 10/12, (나) A + S). 다음: [U9a-pseudo.md](U9a-pseudo.md).
- U9-c 와 겹치는 파일(리베이스 충돌 예상): yaml 3종(주석) · params.py(상수) · belt_servo.py(`_build_event`·틱 값) · sim_check.py(CASES·EXPECT). fsm.py 는 U9-c 가 건드리지 않는다.
- 이 문서가 정하는 것: 바뀌는 값, 새 함수(입력·출력·단위), 전이표 변경, 에러 경로, 시험 목록. 의사코드는 U9a-pseudo.md.

## 0. 바뀌는 것 한눈에

```
                     ┌ 값 ───────────────────────────────────────────┐
config/*.yaml   ───▶ │ z.vision_cutoff_above_top_mm  10 → 30 (주석)  │
                     └───────────────────────────────────────────────┘
                     ┌ S: 사각 체류 상한 ─────────────────────────────────────────────┐
params.py       ───▶ │ BLIND_DWELL_MARGIN_S = 1.0 (상수)                              │
control.py      ───▶ │ descend_blind_max_s(cutoff_m, cfg) → 상한 s  (기동 때 1번 계산)│
fsm.py          ───▶ │ blind_since_next(...) · blind_overstay(...) · step() 9b 줄     │
belt_servo.py   ───▶ │ 상한 계산 1줄 · GoalCtx.blind_since · _build_event 2줄          │  ← 범위 밖(승인됨)
                     └────────────────────────────────────────────────────────────────┘
                     ┌ 시험 ─────────────────────────────────────────────────────────┐
fake_box.py     ───▶ │ 시나리오 descend_cut(+37) · approach_cut(+45): TCP 높이로 끊기   │
sim_check.py    ───▶ │ case descend_lost(기대 OK) · vanish(기대 LOST) · 판정 J-cut     │
test/*.py       ───▶ │ test_fsm · test_control · test_params · test_fake_box ·         │
                     │ test_sim_check · test_race(새, 원본 궤적 재생)                  │
                     └───────────────────────────────────────────────────────────────┘
```
바꾸지 않는 것: `control.xy_rule`(사각 = FF 그대로), `input_flags`, `is_vision_blind` 본문, grip.py, `_not_held`·GRASP 이후, reason 7종, launch/, log_schema(U9-c 영역).

## 1. 값

| 파일 | 키 | 지금 | 바꿈 | 주석 |
|---|---|---|---|---|
| belt_servo.yaml (기본, 값 null) | `z.vision_cutoff_above_top_mm` | 주석 "제안 10 (남현지 확인)" | 값 null 유지, 주석만 | "제안 30 — 카메라 실제 이탈 윗면 +27~37 mm (measurements-1010 '의도 시험', FIELD-1010 §3). cutoff+5 < approach, height_tol < approach − (cutoff+5)" |
| belt_servo_real.yaml.example | 같은 키 | 같음 | 주석만 | 같음 |
| belt_servo_sim.yaml | 같은 키 | 10.0 | **30.0** | 같음 |
| 3종 | `input.lost_timeout_s` | 주석 | 주석만 | "DESCEND 경주는 cutoff 30 으로 없앰(U9a-hld). 0.5 유지" |
| 3종 | `input.blind_entry_max_age_s` | 주석 | 주석만 | "TRACK→DESCEND 전환에서만 씀. cutoff 와 무관" |

- **공용 PC 실값 파일**(레포 밖, 지금 10)은 사용자가 10 → 30 으로 고쳐야 한다 → 회신·U9-b 절차서 항목. 바꾸면 `params_sha256` 이 바뀐다(g1-gate 고정 조건).
- 교차 검사(params.py:202~207, 269~273)는 그대로 통과: approach 40 > 35, height_tol 2 < 5. 새 검사는 넣지 않는다(S 상한은 기존 값에서 계산되고 항상 양수).

## 2. 새 상수·함수

### 2.1 params.py
| 이름 | 값 | 뜻 |
|---|---|---|
| `BLIND_DWELL_MARGIN_S` | 1.0 | 사각 체류 상한 = 예상 하강 시간 + 이 여유. 판단값(시연 중 오판 PAUSED 방지 쪽으로 넉넉히) |

### 2.2 control.py
`descend_blind_max_s(cutoff_m: float, cfg: ControlConfig) -> float`
- 입력: `cutoff_m` 사각 진입 높이(윗면 기준, m, 양수), `cfg` 의 `grasp_dz`(음수, m)·`descend_speed`·`a_max`·`kp_z`·`height_tol_m`
- 출력: 초. `grip.descend_time_s(cutoff_m − grasp_dz, descend_speed, a_max, kp_z, height_tol_m) + BLIND_DWELL_MARGIN_S`
- 값: 시연 설정(cutoff 30, grasp −19, 0.05, 0.1, 1.5, 0.002) → 2.439 + 1.0 = **3.44 s**. cutoff 10 이면 2.78 s.
- 실측 대조: 사각 진입(+30, DESCEND+0.47~0.50 s) → GRASP(2.60~2.63 s) = **2.100~2.133 s**(원본 재생 n=21) < 3.44 (여유 1.31 s). sim(dry_run) 체류는 2.30 s(여유 1.14 s). `descend_time_s` 는 정지 출발로 계산해서 이미 움직이는 실제보다 길게 나온다(안전 쪽).
- import: control → grip (grip 은 fsm 만 import → 순환 없음).

### 2.3 fsm.py
| 이름 | 입력 | 출력 | 규칙 |
|---|---|---|---|
| `DESCEND_BLIND_TIMEOUT` | — | cause 문자열 | 로그용 |
| `TickEvent.blind_overstay` | — | bool, 기본 False | 노드가 채움 |
| `blind_since_next(prev, phase, blind, now)` | prev: float\|None (지난 값), phase: 이번 틱 전이 **전** phase, blind: 이번 틱 사각, now: 노드 시계 s | float\|None | `phase == DESCEND and blind` 이면 `prev` 가 None 일 때만 `now`, 아니면 `prev` 유지. 그 밖(사각 아님·다른 phase)은 None |
| `blind_overstay(blind_since, now, limit_s)` | | bool | `blind_since is not None and now − blind_since > limit_s` (같으면 아직 아님) |

- "DESCEND 안의 사각"만 센다. TRACK 에서 사각이었다가(정상에선 없음) DESCEND 로 넘어오면 그 틱부터 센다 — 사각에 먼저 들어간 시간을 더하지 않는다(오판 쪽 방지).
- GRASP 로 넘어가면 phase ≠ DESCEND → None → 재시도 PREPARE 에서도 None. 재시도로 다시 DESCEND 에 오면 새로 센다.

### 2.4 step() 전이표 변경 (U1-dd 2절 표에 한 줄 추가)
| 순서 | 조건 | 결과 |
|---|---|---|
| 1~3 | stopping | (그대로) |
| 4 | 취소 | (그대로) |
| 5 | 그리퍼 통신 실패 | (그대로) |
| 6 | pose_stale | STALE_INPUT / POSE_MISSING (그대로) |
| 7·8 | 비전 단계 ∧ 사각 아님: box_stale / box_lost | (그대로) |
| 9 | REACH_PHASES ∧ reach | OUT_OF_REACH (그대로) |
| **9b (새)** | **phase == DESCEND ∧ ev.blind_overstay** | **DEVICE_ERROR / `DESCEND_BLIND_TIMEOUT`** |
| 10~17 | 정상 진행 | (그대로) |

- 9b 를 9 뒤에 두는 이유: x 끝에 닿았다면 로봇은 움직이고 있다 → OUT_OF_REACH 가 더 정확한 원인.
- 9b 를 10 앞에 두는 이유: 같은 틱에 `at_grasp_height` 와 겹치면 시간 초과가 이긴다 — 3.44 s 를 넘겼다는 것 자체가 이상이므로 보수적으로 끝낸다(겹칠 일은 사실상 없음).
- reason DEVICE_ERROR 근거: voss_msgs.md TrackAndGrasp 행 "gripper·gateway 서비스 실패"의 **확장 해석**(로봇이 명령대로 내려가지 않음 = 로봇·gateway 쪽 이상). sort_manager 는 비-OK reason 을 모두 PAUSED 로 보내므로 동작 차이는 없다. U9-c cause 문서에 같이 적는다.
- **U9-c `ROBOT_STALLED` 와의 관계**: U9-c 는 같은 현상(pose 변화 ≈ 0 ∧ 명령 ≠ 0, N 틱)을 **LOST 의 cause 분류**로만 쓴다(전이 없음). S 는 사각이라 LOST 검사가 꺼진 구간의 **유일한 종료 경로**다. 리베이스 뒤 S 조건을 U9-c 판정으로 앞당길지(3.44 s 보다 빨리)는 주관 결정 — 이 단위는 S 를 보수적 2차 방어로 둔다.
- **오판 한계**: 상한 3.44 s 는 실측 체류 2.10~2.13 s 의 1.6 배. 로봇 실현 속도가 명령의 약 62 % 아래(펜던트 속도 오버라이드 등)면 정상 하강도 걸린다 → U9-b 절차서 사전 점검에 "펜던트 속도 100 %" 확인.

### 2.5 belt_servo.py (범위 밖 — HLD 승인, 최소 수정)
(diff 23줄 = import 재정렬 6 · GoalCtx 1 · `__init__` 1 · 상한·로그 메서드 10 · `_build_event` 3. 판정 로직은 fsm)

| 위치 | 변경 |
|---|---|
| `__init__` READY 계산(belt_servo.py:166 옆) | `self._blind_max_s = control.descend_blind_max_s(cutoff/1000, self._ctrl) if self.ready else None` + INFO 1줄 "사각 체류 상한 3.44 s (하강 예상 2.44 + 여유 1.0)" |
| `GoalCtx` | `blind_since: float \| None = None` |
| `_build_event` (ctx.blind = blind 다음) | `ctx.blind_since = fsm.blind_since_next(ctx.blind_since, ctx.state.phase, blind, now)` |
| `_build_event` TickEvent 생성 | `blind_overstay=fsm.blind_overstay(ctx.blind_since, now, self._blind_max_s)` |
- 틱 로그 필드는 추가하지 않는다(log_schema 는 U9-c). 끝난 원인은 기존 `cause` 필드에 `DESCEND_BLIND_TIMEOUT` 로 남는다.

## 3. fake_box 시나리오 (sim 전용)

카메라가 실제로 놓치는 것을 흉내: **TCP 가 윗면 + H mm 아래로 내려오면 발행을 멈추고 다시 내지 않는다**(래치 — box_tracker 가 가장자리 판정으로 버린 뒤 다시 안 나온 것과 같음, measurements-1010 "비교").

| 시나리오 | H 기본 | 흉내 내는 것 | 기대 |
|---|---|---|---|
| `descend_cut` | **37** mm | 회전 박스(실측 최대 +36.7) — 하강 시작 직후 끊김 | OK (경주 없음) |
| `approach_cut` | **45** mm | 접근 높이로 내려오는 중 박스가 정말 사라짐 | LOST / BOX_MISSING (TRACK) |

- H 는 파라미터 `cut_above_top_mm`(없으면 시나리오 기본값). sim.launch 는 고치지 않는다 — 시나리오 이름만 넘기면 기본값이 쓰인다(launch/ 는 범위 밖).
- TCP 높이: `/voss/robot/pose`(PoseStamped, best_effort) 를 구독해 `pose.position.z` 를 쓴다(gateway dry_run 이 servo_cmd 를 적분해 낸다). 윗면 = 이 박스의 z(0.1008). 아직 pose 가 없으면 끊지 않는다.
- 순수 함수: `cut_reached(cfg, box_z, tcp_z) -> bool` = `cfg.scenario in CUT_DEFAULT_MM and tcp_z is not None and tcp_z <= box_z + cut_m`. 노드가 한 번 참이면 `self._cut = True` 로 래치. `samples_at(cfg, t, cut=False)`: cut 시나리오이고 `cut` 이면 `[]`, 아니면 normal 과 같음.
- `approach_cut` 45: dry_run 가짜 로봇은 voss_config `observe_pose` 에서 시작한다(robot_gateway.py:89, 현장 관측 자세 z ≈ 203.6 = 윗면 +103). TCP 가 접근 높이(+40)로 내려오는 TRACK 중에 +45 를 지난다 → 정렬(약 3 s 뒤) 전에 끊김. **sim 에서 TRACK 중 끊기는지 실제로 확인한다**.

## 4. sim_check

| case | 시나리오 | object_mm | profile | 기대 |
|---|---|---|---|---|
| `descend_lost` | descend_cut | 40.5 | grasp | SUCCEEDED · OK · grasped · phases = 표준 6단계 |
| `vanish` | approach_cut | 40.5 | grasp | ABORTED · LOST · BOX_MISSING · 앞부분 규칙, 마지막 phase TRACK |

새 판정 **J12 (J-cut)** (`judge_descend_cut(progress, lost_timeout_s, min_margin_s=0.2)`, descend_lost 에만):
- ① 실제로 사각 전에 끊겼다: DESCEND 의 마지막 `box_rx_s` 가 **첫 사각 DESCEND 틱의 `t_calc_s` 보다 2틱(0.067 s) 이상 앞**이다(시나리오가 경주를 정말 만들었는지). 고정 0.1 s 문턱은 sim 의 간격(약 0.167 s, pose_lag 60 ms 로 추정 TCP 가 실제보다 약 3 mm 낮음)과 가까워 틱 양자화에 흔들리므로 쓰지 않는다.
- ② 여유: `lost_timeout_s − max(사각 아닌 DESCEND 틱의 수신 나이) ≥ 0.2 s`.
- 둘 다 맞으면 PASS, 수치(끊긴 높이·최대 나이·여유)를 detail 에 적는다. DESCEND 틱이 없으면 UNKNOWN.
- `lost_timeout_s` 는 설치된 belt_servo_sim.yaml 에서 읽는다(`sim_check.sim_values()` 반환 사전에 키 하나 추가).
- `PROFILE_CASES["grasp"]` = (normal, empty, cancel, **descend_lost, vanish**). 기존 기대값은 그대로.
- **sim 의 한계 (최종 재검 r3 실측)**: cutoff 10 으로 되돌린 yaml 로 `descend_cut` 을 돌려도 sim 은 **LOST 를 재현하지 못한다**(goal OK, 여유 +0.007 s). dry_run 은 가감속이 없고 sim yaml 의 pose_lag 60 ms 로 추정 TCP 가 실제보다 약 3 mm 낮아, fake_box 가 실제 pose +37 에서 끊어도 belt_servo 기준으로는 약 +34 에서 끊긴 셈이기 때문이다. 그래서 **sim 의 회귀 방어선은 J1(결과)이 아니라 J12 여유 ≥ 0.2 s** 다(cutoff 10 이면 +0.007 → FAIL). "옛 LOST 를 그대로 재현"하는 것은 순수 시험 `test_race_cutoff10_lost_regression` 몫이다.

## 5. 에러 경로
| 상황 | 결과 |
|---|---|
| 사각 진입 높이(+30) 위에서 카메라가 놓침 | 0.5 s 안에 사각 → LOST 없음 (경주 해소, 여유 ≥ 0.34 s) |
| 하강 시작 직후(+39 이상)에 놓침 | 여유 0.0~0.2 s — 남은 경주(HLD 1.2 민감도). 실측 최대 +36.7 |
| 사각 안에서 로봇이 멈춤 (pose 는 옴) | 3.44 s 뒤 DEVICE_ERROR / DESCEND_BLIND_TIMEOUT (재검 r3 목업: +24.4 mm 정지 → 3.467 s) |
| 사각 **바로 위**(+30~+40)에서 로봇이 멈춤 | TCP 외삽(마지막 명령 × 최대 0.2 s ≈ 10 mm)으로 추정 TCP 가 사각에 들어가 LOST(0.5 s)·U9-c ROBOT_STALLED 가 가려지고 **S 로 끝난다**(재검 r3 목업: pose +32.6 고정 → 추정 +22.6 → 3.469 s). 둘 다 종료하고 sort_manager 는 둘 다 PAUSED — 안전. 정지 판단(U9-c stall)을 전이에 쓸지는 U9-b·주관 결정 |
| 사각 안에서 pose 끊김 | 지금처럼 0.3 s 뒤 STALE_INPUT / POSE_MISSING (6번 줄이 먼저) |
| 사각 안에서 박스가 정말 사라짐 | 알 수 없음 → GRASP NOT_DETECTED → GRASP_FAILED (핑거–벨트 약 8 mm) |
| 접근 높이에서 박스가 사라짐 | 0.5 s 뒤 LOST / BOX_MISSING (지금과 같음) |
| `_blind_max_s` 가 None (READY 아님) | 액션 서버가 없어 goal 이 오지 않는다. `blind_overstay(…, None)` 은 호출되지 않지만 방어로 limit None 이면 False |
| 재시도 상승(PREPARE) | 사각 이탈 +35 → LOST 시계 재시작. 여유 0.08~0.13 s(부분 해소) — U9-b |

## 6. 시험 목록 (pytest)

| 파일 | 시험 | 확인하는 것 |
|---|---|---|
| test_fsm | `test_blind_since_starts_in_descend_blind` · `_keeps_first_time` · `_clears_when_visible_or_other_phase` | 2.3 규칙 |
| test_fsm | `test_blind_overstay_boundary` (같으면 False, 넘으면 True, None 이면 False) | 경계 |
| test_fsm | `test_step_descend_overstay_device_error` · `_ignored_outside_descend` · `_pose_stale_first` · `_reach_first` · `_cancel_first` | 9b 위치 |
| test_fsm | `test_cutoff30_track_band_visible` (was_blind 거짓·참 둘 다: TRACK 38~42 + x≥600 처짐 1.3 mm → 사각 아님. 참이면 이탈 +35 와 비교) · `test_retry_rise_exits_above_35` (−17 → +40 상승, +35 초과에서 사각 해제) | 히스테리시스·재시도 PREPARE 복귀 |
| test_fsm | `test_blind_since_retry_sequence` (DESCEND 사각 → GRASP → PREPARE → DESCEND 사각: GRASP 에서 None, 두 번째 DESCEND 에서 새 시각) · `test_blind_overstay_one_tick_boundary` (상한 −1틱 거짓, +1틱 참) | S 가 재시도에서 새로 세는지 |
| test_race (새) | `test_race_cutoff30_no_lost` — control.z_speed·clamp 로 만든 하강 궤적(30 Hz) + 마지막 수신 +37 → is_vision_blind·input_flags 를 틱마다 → LOST 없이 사각 진입, 여유 ≥ 0.2 | 완료 기준 2 "경주" |
| test_race | `test_race_cutoff10_lost_regression` — 같은 입력, cutoff 10 → LOST (옛 문제 재현) | 시험이 진짜 경주를 잡는지 |
| test_race | `test_true_vanish_at_approach_lost` — 접근 높이(+40)에 머무는 TCP, 수신 끊김 → 0.5 s 초과 틱에 LOST | 완료 기준 2 "진짜 소실" |
| test_race | `test_descend_dwell_within_cap` — 같은 궤적의 사각 체류 < descend_blind_max_s | S 가 정상에서 안 걸림 |
| test_control | `test_descend_blind_max_s_values` (cutoff 30 → 3.44, 10 → 2.78, ±0.01) | 2.2 |
| test_params | `test_cutoff30_passes_cross_checks` · `test_cutoff33_fails_height_tol` · `test_cutoff35_fails_approach` | 교차 검사 |
| test_fake_box | `test_cut_reached_threshold` · `test_cut_scenarios_send_nothing_when_cut` · `test_cut_default_heights` · 모르는 시나리오 ValueError 유지 | 3 |
| test_sim_check | `test_judge_descend_cut_pass_fail_unknown` · `test_grasp_profile_has_new_cases` | 4 |
| test_fsm·test_params·test_node | 기존 시험의 cutoff 10 고정값(test_fsm.py:164, test_params.py:31, test_node.py:111)은 순수 함수 경계 시험이라 그대로 둔다 — 값이 아니라 규칙을 시험한다 | 1 |

- `test_race` 의 궤적은 원본 재생값(사각 진입 +30 에 0.47~0.50 s)과 ±1틱 안으로 맞는지 같이 확인한다(시뮬이 현실과 같은 시계인지).
- sim: `sim_check --profile grasp --case all` (도메인 72) — 기존 3 + 새 2 전부 PASS.

## 7. 다음
승인되면 U9a-pseudo.md(함수별 한국어 의사코드) → 코드.
