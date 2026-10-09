# U3 기동 launch + fake_box 시뮬 — Detail design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u3-sim` · 작성 2026-10-10
- 상태: **DD 승인(박병후, 10/10)**, r2 독립 재검 반영(10/10, 10절). 앞 단계: [U3-hld.md](U3-hld.md). 다음: [U3-pseudo.md](U3-pseudo.md).
- 단위: 길이 m·속도 m/s(노드 내부·틱 로그), 파라미터 이름에 단위 접미사(`_mm`·`_s`·`_cmps`)가 있으면 그 단위. 시각은 ROS 시계(벽시계) 초.

## 1. `voss_servo/launch_params.py` (순수 모듈, ROS import 없음)

### 1.1 상수
| 이름 | 값 | 뜻 |
|---|---|---|
| `NODE_NAME` | `"belt_servo"` | YAML 최상위 키 |
| `NULL_STRINGS` | `params.NULL_STRINGS` 재사용 (`"null"`, `"~"`) | 비교는 **strip 만**(대소문자 구분) — 노드 `params._is_null_string`(params.py:255) 과 똑같이 (r2) |
| `CONFIG_PREFIXES` | `("belt", "gripper", "timing")` | voss_config 에서만 오는 키 묶음 |
| `CONFIG_META_KEYS` | `("config_version", "config_sha256")` | launch 가 만드는 키 |
| `CONFIG_KEYS` | PARAM_SPECS 중 첫 마디가 `CONFIG_PREFIXES` 인 이름 (지금 6개: belt.speed_cmps, belt.direction_base, gripper.pre_open_mm·grasp_width_mm·force_n, timing.latency_offset_ms) | U5 가 같은 묶음에 키를 더하면 자동 포함 |
| `SHA_LEN` | 12 | gateway `config_params.load_config` 와 같은 길이 |

### 1.2 함수
| 함수 | 입력 | 출력 | 오류 |
|---|---|---|---|
| `expand(path)` | 문자열 | `~` 를 펼친 절대 경로 문자열 | — |
| `load_yaml(path)` | 경로 | dict (빈 파일이면 `{}`) | 파일 없음·YAML 오류·최상위가 dict 아님 → `LaunchParamsError` |
| `node_section(doc, node=NODE_NAME, where="")` | dict, 노드 이름, 오류 메시지용 경로 | `doc[node]["ros__parameters"]` (dict) | 없거나 dict 아님 → `LaunchParamsError`(메시지에 where) |
| `flatten(d, prefix="")` | 중첩 dict | `{"a.b.c": 값}` (목록은 잎으로 둔다) | — |
| `is_unset(v)` | 값 | `None`·NULL_STRINGS·빈 목록이면 True. `0`·`False`·`""` 는 False (그 판단은 노드) | — |
| `drop_unset(flat)` | 평탄 dict | (남은 dict, 지운 키 목록 정렬) | — |
| `forbidden_keys(flat)` | 평탄 dict | CONFIG_PREFIXES 로 시작하거나 CONFIG_META_KEYS 인 키 목록 | — |
| `unknown_keys(flat)` | 평탄 dict | PARAM_SPECS 이름에 없는 키 목록 | — |
| `normalize(flat)` | 평탄 dict | 형을 맞춘 새 dict: kind `float` 이고 int(bool 제외) → float · `float3` 이고 숫자 목록 → float 목록 · `int` 이고 정수값 float → int · 나머지 그대로(틀린 형은 노드가 거부) | — |
| `file_sha(path)` | 경로 | 파일 바이트 sha256 앞 12자리 | 파일 없음 → `LaunchParamsError` |
| `config_values(cfg_doc, sha)` | voss_config dict, sha | CONFIG_KEYS 중 있는 값(평탄화, null 은 뺌) + `config_version`(= `version`, 없으면 뺌) + `config_sha256` = sha | — |
| `build_params(params_path, config_path, overrides_path=None, log_dir=None)` | 경로들 | `BuildResult` | 위 오류 + forbidden 키가 있으면 `LaunchParamsError` |

`BuildResult`(dataclass, frozen): `params: dict` (노드에 넘길 값) · `dropped: list[str]` (null 이라 뺀 키 — 로그용) · `warnings: list[str]` · `config_sha: str` · `sources: dict[str, str]` (params·overrides·config 의 절대 경로).

### 1.3 `build_params` 순서 (HLD 4A)
1. params → `load_yaml` → `node_section` → `flatten` → `drop_unset`.
2. overrides 가 있으면 같은 처리 후 `dict.update` (같은 키 덮어씀, 새 키 추가). 지운 키는 dropped 에 합친다. 단 overrides 가 **값을 준** 키는 dropped 에서 뺀다.
3. 1·2 합친 결과에 `forbidden_keys` 가 있으면 오류: `"params/overrides 에 voss_config 키가 있다(규칙 5): [...]"`.
4. `log_dir` 이 있으면 `log.dir = expand(log_dir)`. 없고 `log.dir` 이 상대 경로면 경고 1줄("log.dir 상대 경로 — 실행 위치 기준").
5. config → `load_yaml` + `file_sha` → `config_values` 합침.
6. `normalize`.
7. `unknown_keys` 가 있으면 경고 1줄("PARAM_SPECS 에 없는 키(노드가 무시): [...]").

### 1.4 오류 메시지 형식
`LaunchParamsError("<무엇>: <경로 또는 키> — <어떻게>")`. 예: `"파일 없음: /home/rokey/voss_ws/config/belt_servo_real.yaml — example 을 복사해 값 채우기(U3-run.md A)"`.

## 2. `launch/belt_servo.launch.py`

| 인자 | 기본값 | 필수 | 뜻 |
|---|---|---|---|
| `params` | `""` | ✅ (비면 오류) | belt_servo 파라미터 YAML |
| `config` | `~/voss_ws/config/voss_config.yaml` | | gateway launch 와 같은 기본 |
| `overrides` | `""` | | 덮어쓸 YAML (sim 의 kp 등) |
| `log_dir` | `""` | | `log.dir` 덮어쓰기 (절대 경로로 펼침) |

- `OpaqueFunction` 하나: `build_params(...)` → 액션 목록 `[LogInfo(요약), LogInfo(경고)…, Node(...)]`.
- 요약 1줄: `belt_servo launch: params=<경로> overrides=<경로|-> config=<경로> config_sha256=<12> 넘김 <N>개, null 로 뺀 키 <M>개 [...]`.
- `Node(package="voss_servo", executable="belt_servo", name="belt_servo", output="screen", parameters=[result.params])`. 네임스페이스 없음. `emulate_tty` 는 쓰지 않는다(pty 면 rcutils 가 색 코드를 넣어 로그 파일이 지저분해진다, gateway launch 와 같게 — r2).
- `LaunchParamsError` 는 잡지 않는다 → launch 가 메시지를 보이고 멈춘다(노드를 띄우지 않음).

## 3. YAML 세 개

- 키 집합 규칙: `config/belt_servo.yaml` = `belt_servo_real.yaml.example` = `belt_servo_sim.yaml` (평탄화한 키 집합이 같다 — 테스트 T-L12). voss_config 키는 셋 다 넣지 않는다.
- example 은 `setup.py` 설치 대상이 아니다(`config/*.yaml` 만 설치). 사용법: 레포에서 `~/voss_ws/config/belt_servo_real.yaml` 로 복사.

| 키 | belt_servo.yaml (main) | example | sim | sim 값 출처 |
|---|---|---|---|---|
| grasp.tcp_z_below_top_mm | 19.0 | 19.0 | 19.0 | 결정값 |
| grasp.hold_width_min_mm / max | null | null (제안 39.5 / 43.5 — T34 측정 기준 제안, measurements·ADR 확정 전) | 39.5 / 43.5 | U5 지시서·CONTRACT T34 (0° 40.7~41.2, 30° 43.0). main 주석의 41.5 갱신은 U5 몫 |
| reach.x_min_mm / x_max_mm | −107 / 620 | −107 / 620 | −107 / 620 | measurements #6, #122 |
| control.kp_per_s | null | null (U4) | **1.0** | 사전 실험(sim 전용) |
| control.kp_z_per_s | null | null (≤ 2) | 1.5 | U2 DD 7.1 (kp_z × 0.05 ≤ 0.1) |
| control.align_tol_along_mm / cross_mm | null | null (3 / 5) | 3.0 / 5.0 | U2 DD 7.1 |
| limits.max_speed_mps / max_acc_mps2 | null | null (0.08 / 0.1) | 0.08 / 0.1 | U2 DD 7.1 |
| z.approach_above_top_mm | null | null (없음) | **40.0** | 사전 실험(sim 전용, cutoff+5 보다 큼) |
| z.lift_above_top_mm | null | null (없음) | **50.0** | sim 전용 |
| z.vision_cutoff_above_top_mm | null | null (10) | 10.0 | U2 DD 7.2 |
| z.descend_speed_mps / lift_speed_mps | null | null (0.05 / 0.08) | 0.05 / 0.08 | U2 DD 7.1 |
| z.height_tol_mm | null | null (2) | 2.0 | U2 DD 7.1 |
| input.stale_timeout_s / lost_timeout_s | null | null (0.3 / 0.5) | 0.3 / 0.5 | U2 DD 7.2 |
| input.pose_lag_ms | 60.0 | 60.0 | 60.0 | 측정값 |
| input.pose_extrap_max_ms | null | null (200) | 200.0 | U2 DD 7.1 |
| input.blind_entry_max_age_s | null | null (0.15) | 0.15 | U2 DD 7.1 |
| retry.max_attempts | 1 | 1 | 1 | U9 전 |
| stop_timeout_s / rate_hz / zero_hold_s | 1.0 / 30.0 / 0.5 | 같음 | 같음 | main |
| log.dir | data/servo | data/servo (T7 은 `log_dir:=` 로 덮어씀) | **/tmp/voss_sim/servo** (sim_check 는 run 폴더로 덮어씀) | 사람이 log_dir 없이 sim yaml 로 띄워도 git 추적 폴더 `data/servo/attempts/`(게이트 증거)를 가짜 시도로 오염시키지 않게 (r2) |

- example 머리 주석: 쓰는 법(복사 위치·값 채우기·T7 명령), "결정값은 바꾸지 말 것, 바꾸면 measurements·PR", null 은 미측정(READY 거부됨).
- sim 머리 주석: "**sim 전용 — 실기 금지.** 값은 미측정 제안값(sim 동작 확인용). kp·approach·lift 는 사전 실험 값(design/U3-hld.md 2절)".
- U5 가 새 필수 키를 PARAM_SPECS·belt_servo.yaml 에 더하면: T-L12 가 깨지고 sim yaml 은 READY 거부된다(깨지는 것이 알람). 머지 순서 **권고: #130 → U3 → U5**(주관 세션 의견, 10/10 — 팀 상황·리뷰 진행에 따라 바뀔 수 있다). 그 순서면 U5 머지 직후 U3 담당 follow-up 커밋으로 example·sim yaml 에 새 키를 보탠다. 순서가 바뀌면 나중에 머지되는 쪽에서 보탠다(회신·PR 본문에 명시, r2).

## 4. `voss_servo/fake_box.py`

### 4.1 파라미터
| 이름 | 기본 | 뜻 |
|---|---|---|
| `scenario` | `"normal"` | normal · invalid_after_s · lost_after_s · two_boxes |
| `track_id` | 1 | 첫 박스 |
| `start_xyz_m` | [−0.100, −0.271, 0.1008] | 시작 위치 (윗면 중심, base_link). 카메라 유효 범위 상류 끝·관측 자세 y·벨트 면 73.8 + 27 mm |
| `speed_cmps` | **없음(필수)** | sim.launch 가 voss_config `belt.speed_cmps` 를 넘김 |
| `direction_base` | **없음(필수)** | 같은 곳 `belt.direction_base` |
| `rate_hz` | 30.0 | 발행 주기 |
| `invalid_after_s` | 8.0 | 시작 뒤 이 시각부터 position_valid=false (scenario invalid_after_s) |
| `lost_after_s` | 8.0 | 시작 뒤 이 시각부터 발행 안 함 (scenario lost_after_s). 8 s = 콜드 스타트(gateway·belt_servo·sim_check 연결)보다 넉넉히 (r2) |
| `second_track_id` | 2 | two_boxes 의 둘째 |
| `second_offset_m` | [0.060, 0.040, 0.0] | 둘째 = 첫째 + 이만큼 (60 mm 하류, 40 mm 가로 — 첫째 궤적 선에서 40 mm 떨어짐) |

필수 값이 없거나 scenario 가 모르는 이름이면 ERROR 로그 + 종료 코드 1(노드를 띄우지 않음).

- `speed_cmps`·`direction_base` 를 기본값 없이 둔 것은 **의도**다: 숫자를 코드에 복사하면 voss_config 와 어긋날 수 있다. 지시서의 "기본은 voss_config 값" 은 sim.launch 가 voss_config 에서 읽어 넘기는 것으로 지킨다(단독 `ros2 run` 때는 `-p` 로 준다).

### 4.2 순수 함수
| 함수 | 입력 | 출력 |
|---|---|---|
| `belt_velocity(speed_cmps, direction)` | cm/s, 3 숫자 | m/s 벡터 (방향은 단위벡터로 나눠 씀, 길이 0 → ValueError) |
| `position_at(start, vel, t)` | m, m/s, s | m |
| `samples_at(cfg, t)` | `FakeBoxConfig`, 시작 뒤 초 | `list[BoxSample]` (`track_id`, `xyz`, `valid`) — 시나리오 표대로 |

| scenario | t < T | t ≥ T |
|---|---|---|
| normal | [첫째 valid] | 같음 |
| invalid_after_s | [첫째 valid] | [첫째 **invalid** (위치는 계속 계산)] |
| lost_after_s | [첫째 valid] | [] (발행 없음 = 미검출, 계약) |
| two_boxes | [첫째 valid, 둘째 valid] | 같음 |

### 4.3 노드
- 시작 시각 = 노드 생성 시각(`time.monotonic`). 타이머 `1/rate_hz` 마다 `samples_at` → `BoxTrack` 으로 바꿔 발행.
- BoxTrack: `stamp` = 발행 직전 `get_clock().now()`, `u`·`v`·`bbox` 0, `position_source = SOURCE_HAND_EYE`, `calib_version = "fake"`.
- QoS: best_effort · volatile · keep_last depth 1 (topics.md 발행 쪽, box_tracker 와 같게). two_boxes 는 한 틱에 2건 연달아 발행 — CycloneDDS best_effort 는 write 때 바로 보내 덮임이 드물지만, J12 가 실패하면 이 원인을 먼저 의심한다(재검 #13, 계약 유지를 택함).
- 시작 로그 1줄: scenario·시작 위치·벨트 속도 벡터(mm/s)·T.

## 5. `launch/sim.launch.py`

| 인자 | 기본 | 뜻 |
|---|---|---|
| `config` | `""` (**필수**) | 레포 `config/voss_config.yaml` 절대 경로 (sim_check 가 넘김) |
| `scenario` | `normal` | fake_box 에 그대로 |
| `object_mm` | `40.5` | gateway `dry_run_object_mm` (0 = 빈손) |
| `kp` | `""` | 있으면 `control.kp_per_s` 덮어쓰기 |
| `log_dir` | `""` | belt_servo `log_dir` |
| `invalid_after_s` / `lost_after_s` | `8.0` / `8.0` | fake_box 에 그대로 |

- `OpaqueFunction`: `config` 가 비면 오류. `load_yaml(config)` → `config_values` 로 belt 값 → fake_box 파라미터.
- include 형식(Jazzy): `IncludeLaunchDescription(PythonLaunchDescriptionSource(경로), launch_arguments={…}.items())` — dict 를 그대로 넘기면 `tuple(dict)` 로 키만 남아 깨진다(launch/actions/include_launch_description.py:72·239, r2).
- gateway: `<voss_robot share>/launch/robot_gateway.launch.py`, 인자 `{dry_run: "true", dry_run_object_mm: object_mm, config: config}`. **`dry_run` 은 인자로 받지 않고 항상 "true"**(sim 에서 실기로 새지 않게).
- belt_servo: `<voss_servo share>/launch/belt_servo.launch.py`, 인자 `{params: <share>/config/belt_servo_sim.yaml, config, overrides, log_dir}`. `kp` 가 있으면 `log_dir`(없으면 임시 폴더)에 `sim_overrides.yaml`(`belt_servo: ros__parameters: control: kp_per_s: <kp>`)을 쓰고 그 경로를 overrides 로.
- 노드 셋 다 `output="screen"`.

## 6. `voss_servo/sim_check.py`

### 6.1 인자
| 인자 | 기본 | 뜻 |
|---|---|---|
| `--case` | `all` | lost · invalid · cancel · normal · two_boxes · empty · all |
| `--profile` | `pre_u5` | 기대값 묶음 (6.3) |
| `--out` | `/tmp/voss_sim/<YYYYmmdd_HHMMSS>` | run 폴더들의 부모 |
| `--config` | `<현재 git 최상위>/config/voss_config.yaml` | 못 찾으면 종료 코드 2 |
| `--kp` | (없음) | sim.launch `kp` |
| `--goal-timeout-s` | 30.0 | goal 결과 대기 상한 |
| `--cancel-after-s` | 3.0 | cancel case: goal 수락 뒤 cancel 시각 |

### 6.2 case 표
| case | fake scenario | object_mm | cancel | 포함 profile |
|---|---|---|---|---|
| lost | lost_after_s | 40.5 | — | pre_u5 |
| invalid | invalid_after_s | 40.5 | — | pre_u5 |
| cancel | normal | 40.5 | 3.0 s | pre_u5, grasp |
| normal | normal | 40.5 | — | pre_u5, grasp |
| two_boxes | two_boxes | 40.5 | — | pre_u5 |
| empty | normal | 0 | — | grasp |

`all` = 그 profile 에 포함된 case 전부(순서대로). 한 case = run 폴더 `<out>/<case>/` 하나 = sim 한 번 기동.

### 6.3 기대값 (status: 4 SUCCEEDED · 5 CANCELED · 6 ABORTED)
| profile · case | status | reason | cause (attempts GOAL_END) | grasped | phases |
|---|---|---|---|---|---|
| pre_u5 · lost | 6 | LOST | BOX_MISSING | false | = [PREPARE] |
| pre_u5 · invalid | 6 | STALE_INPUT | BOX_INVALID | false | = [PREPARE] |
| pre_u5 · cancel | 5 | CANCELED | STOP_OK | false | = [PREPARE] |
| pre_u5 · normal | 6 | OUT_OF_REACH | REACH_X_MAX | false | = [PREPARE] |
| pre_u5 · two_boxes | 6 | OUT_OF_REACH | REACH_X_MAX | false | = [PREPARE] |
| grasp · normal | 4 | OK | (빈 문자열) | true | = 표준 6개 전부 |
| grasp · empty | 6 | GRASP_FAILED | NOT_DETECTED | false | 접두사, 마지막 GRASP |
| grasp · cancel | 5 | CANCELED | STOP_OK | false | 접두사 |

grasp profile 은 U5 머지 뒤 실제 값으로 다시 확인한다(지금은 U5 설계를 읽고 쓴 기대값 — U5 회신과 다르면 U5 PR 에서 고친다). lost·invalid 의 grasp 기대값은 정하지 않는다(사각 구간에 걸리면 결과가 달라진다 — U9).

### 6.4 공통 판정 (모든 case)
| ID | 항목 | 규칙 | 허용치 |
|---|---|---|---|
| J1 | result | 6.3 표의 status·reason·grasped 일치 | 정확히 |
| J2 | cause | attempts 로그 GOAL_END 의 cause 일치 | 정확히 |
| J3 | phases | 6.3 표 (= 목록 또는 접두사) | — |
| J4 | 마지막 0 | goal 틱 중 terminal 틱 cmd = 0 | ‖cmd‖ ≤ 1e-9 |
| J5 | 0 유지 | terminal 뒤 `cause=="ZERO_HOLD"` 틱 전부 0, 마지막 − terminal ≥ zero_hold_s − 1/rate_hz | 개수 ≥ round(zero_hold_s·rate_hz) − 1 |
| J6 | 주기 | goal 틱(ZERO_HOLD 포함) `t_pub_s` Δt 평균 | 33.3 ± 3 ms |
| J7 | watchdog | 창 [goal 수락, SIGINT 보낸 시각) 안의 gateway WARN watchdog: 개수와 (시각 − terminal 틱 `t_pub_s`) | 1회, 0.6 ~ 0.9 s |
| J8 | move_stop | 같은 창 안 통계 줄의 move_stop ok 합 / fail 합 | ok = 1 (cancel 2), fail 0 |
| J9 | stop | 같은 창 안 통계 stop 합, `/voss/robot/stop → OK` 줄 | 0 (cancel: 1 + OK 줄 1) |

창을 SIGINT 전으로 자르는 이유: PR #130 뒤에는 belt_servo 가 종료 때 0 을 한 번 더 보내 gateway 가 재무장할 수 있다 → 종료 처리 중 생기는 watchdog·통계는 판정에서 뺀다(r2).
| J10 | dry_run | gateway 시작 줄 첫 단어가 `dry_run` | 아니면 **즉시 FAIL·sim 정지** (안전), 줄이 없으면 UNKNOWN |

### 6.5 case 별 추가 판정
| ID | case | 규칙 |
|---|---|---|
| J11 | normal · two_boxes (pre_u5) | `visible` 이고 terminal·stopping 아닌 틱(≥ 30개) 모두: cmd·d̂ ≥ −1e-6 (상류로 돌진 안 함, d̂ = `belt_vel_mps` 방향) · `tcp_now_m`·`predicted_m`·`error_m` 가 null 아님. 그중 `err_along_m ≥ −align_tol_along`(박스가 TCP 상류에 있지 않음) 인 틱은 ‖cmd‖ > 0 |
| J12 | two_boxes | `position_base_m` 가 있는 모든 goal 틱: 첫째 궤적 선(시작 위치 지나고 방향 d̂)까지 거리 ≤ 5 mm (둘째는 40 mm) |

- J11 의 ‖cmd‖ > 0 을 "박스가 상류가 아닐 때" 로 한정한 이유: 박스가 상류면 기다리기 규칙(U2)으로 벨트 방향 성분이 0 이 되고, y·z 오차까지 0 이면 명령이 정확히 0 이다 — 정상 동작이다(사전 실험 cancel goal 의 0 명령 73틱은 전부 err_along ≈ −590 mm, r2 재계산).
- J12 의 검증 범위: 노드가 `position_base_m` 을 goal 트랙 보관값에서 꺼내므로(belt_servo.py:593-603) J12 는 "track_id 별 보관이 섞이지 않는다" 를 확인한다(지시서 "다른 track_id 무시" 와 같은 뜻).

### 6.6 판정 결과와 종료 코드
- 각 판정 = `Verdict(id, 항목, 기대, 실제, status)`, status ∈ `PASS`·`FAIL`·`UNKNOWN`(자료가 있어야 하는데 없음: 패턴 못 찾음·로그 파일 없음·goal 시간 초과).
- 종료 코드: 하나라도 FAIL → 1. FAIL 없고 UNKNOWN 있음 → 2. 아니면 0. 여러 case 면 가장 나쁜 값 = `worst_code`: 1 > 2 > 0 (숫자 max 가 아님).
- 출력: case 마다 표(ID·항목·기대·실제·판정) + 맨 끝 요약 표(case × 종료 코드). 같은 내용을 `<run>/verdict.json` 에.

### 6.7 한 case 실행 순서와 대기 시간
0. **사전 점검**(case 마다): `ROS_DOMAIN_ID == "30"`(공용 PC·실로봇 도메인) 이면 거부. 그래프 탐색 2 s 뒤 `robot_gateway`·`belt_servo`·`fake_box` 노드가 이미 있으면 거부(실기 gateway 에 goal 이 가거나 두 sim 이 섞임). 거부 = J0 FAIL·종료 코드 2, sim 을 띄우지 않는다. 판단은 순수 함수 `preflight_problems(domain_id, node_names)`.
1. run 폴더 만들기. `ros2 launch voss_servo sim.launch.py config:=… scenario:=… object_mm:=… log_dir:=<run> [kp:=…]` 를 자식 프로세스로(새 프로세스 그룹, 출력 → `<run>/launch.log`, 환경 `PYTHONUNBUFFERED=1`·`RCUTILS_COLORIZED_OUTPUT=0`).
2. launch.log 에서 gateway 시작 줄 확인(J10, ≤ 15 s).
3. rclpy 노드 `sim_check`: 액션 서버 대기(≤ 20 s) + `/voss/vision/box` 첫 메시지 대기(≤ 5 s, 구독 QoS best_effort depth 5). **stamp 가 이번 case 시작(ROS 시각) 이후인 메시지만** 인정(앞 case 의 남은 메시지 배제, r2).
4. goal(track_id 1) 전송 → 수락 확인 → feedback phase 기록 → (cancel case) 수락 뒤 `--cancel-after-s` 에 cancel → result 대기(≤ `--goal-timeout-s`).
5. 정착 대기: launch.log 에 watchdog WARN 이 나오고, **그 뒤 시각의 gateway 통계 줄**이 나올 때까지(≤ 8 s — 통계는 5 s 마다).
6. **launch 프로세스에만** SIGINT(launch 가 자식에 SIGINT → SIGTERM 5 s → SIGKILL 5 s 로 단계적으로 전파) → ≤ 15 s 대기 → 남으면 프로세스 그룹에 SIGKILL(로그에 표시). SIGINT 보낸 ROS 시각을 기록(J7~J9 창의 끝).
7. 파일 읽기: `<run>/ticks/*.jsonl`·`<run>/attempts/*.jsonl` 에서 goal_id(= goal UUID 16바이트 hex) 행만. `result.json` 저장.
8. 판정 → 표.
어느 단계든 시간 초과 → 그 뒤 판정은 UNKNOWN, 6 단계(정리)는 항상 한다(`try/finally`).
- `--config` 기본이 "현재 git 최상위" 라서 레포 밖에서 실행하면 종료 2 → U3-run (B) 명령은 `cd ~/cobot2/cobot2_voss && …` 로 쓴다.

### 6.8 gateway 로그 패턴 (상수 한 곳, robot_gateway.py 문구 기준 — 바뀌면 여기만 고침)
| 이름 | 정규식 (요지) | 출처 |
|---|---|---|
| `GW_STARTED` | `robot_gateway started: dry_run` | robot_gateway.py:241 |
| `GW_WATCHDOG` | `\[(\d+\.\d+)\] \[robot_gateway\]: servo_cmd 끊김\(watchdog\)` | :849 |
| `GW_STOP` | `\[(\d+\.\d+)\] \[robot_gateway\]: /voss/robot/stop → (\S+)` | :885 |
| `GW_STATS` | `\[(\d+\.\d+)\] \[robot_gateway\]: servo rx .* watchdog (\d+), stop (\d+), move_stop (\d+) ok / (\d+) fail` | :421 |

### 6.9 순수 함수 목록
`preflight_problems(domain_id, node_names)` · `select_goal_rows(rows, goal_id)` · `split_goal_ticks(rows)` → (진행 틱, terminal 틱, hold 틱) · `parse_gateway(lines)` → `GatewayFacts(started_dry_run, watchdog_times, stop_results, stats_totals{watchdog, stop, ms_ok, ms_fail})` · `judge_result` · `judge_cause` · `judge_phases` · `judge_last_zero` · `judge_zero_hold` · `judge_period` · `judge_watchdog` · `judge_move_stop` · `judge_stop` · `judge_follow` · `judge_track_lock` · `exit_code(verdicts)` · `worst_code(codes)` · `in_window(t, start, end)` · `format_table(verdicts)`. 판정 함수는 모두 `Verdict` 하나를 돌려준다.

## 7. 패키지 파일
- `package.xml` exec_depend 추가: `launch`, `launch_ros`, `voss_robot`(sim.launch include — PR 본문에 "sim 전용 include 의존" 한 줄), `python3-yaml`, `action_msgs`(GoalStatus).
- `setup.py` entry_points 추가: `fake_box = voss_servo.fake_box:main`, `sim_check = voss_servo.sim_check:main`. data_files 는 그대로(launch/*.py, config/*.yaml — sim yaml 설치, example 은 설치 안 함).

## 8. 테스트 목록 (L1, 순수 함수)

**`test/test_launch_params.py`**
| ID | 확인 |
|---|---|
| T-L1 | flatten: 중첩 → 점 이름, 목록은 잎 |
| T-L2 | drop_unset: None·"null"·" null "·"~"·[] 지움, 0·False·""·"NULL"(노드와 같게 대소문자 구분) 남김 |
| T-L3 | overrides 가 같은 키 덮어쓰고 새 키 추가, 덮어쓴 키는 dropped 에서 빠짐 |
| T-L4 | params 에 belt.* / config_version 이 있으면 LaunchParamsError |
| T-L5 | unknown 키 → warnings 1줄, 값은 그대로 |
| T-L6 | normalize: 90 → 90.0(float kind), [1, 0, 0] → floats(float3), True 는 그대로, max_attempts 1.0 → 1(int) |
| T-L7 | config_values: CONFIG_KEYS 6개 + version → config_version, null 값은 뺌 |
| T-L8 | file_sha: 길이 12, 같은 파일 같은 값, 한 바이트 바꾸면 다름, gateway 방식(hashlib 앞 12)과 같음 |
| T-L9 | 파일 없음·깨진 YAML·ros__parameters 없음 → LaunchParamsError (메시지에 경로) |
| T-L10 | log_dir: `~/x` → 절대 경로로 log.dir 덮어씀, 없고 상대면 경고 |
| T-L11 | build_params 전체: 레포 belt_servo.yaml + 레포 voss_config → null 키는 dropped, voss_config 6키·지문 포함, 넘긴 값은 전부 PARAM_SPECS 이름 |
| T-L12 | 키 집합: belt_servo.yaml = example = sim (평탄화 키 집합) |
| T-L13 | sim yaml → build_params → `params.check_params` 가 READY (sim 값이 교차 검사 통과) |

**`test/test_fake_box.py`**
| ID | 확인 |
|---|---|
| T-F1 | belt_velocity: 4.8 cm/s·[0.99992, −0.01292, 0] → ‖v‖ = 0.048 m/s, 방향 유지 |
| T-F2 | position_at: t=0 시작점, t=10 → +0.48 m(벨트 방향) |
| T-F3 | normal: 언제나 첫째 valid 1개 |
| T-F4 | invalid_after_s: T 전 valid, T 뒤 invalid(위치는 계속 움직임) |
| T-F5 | lost_after_s: T 뒤 빈 목록 |
| T-F6 | two_boxes: 두 개, track_id 다름, 둘째 = 첫째 + offset, 첫째 궤적 선에서 40 mm |
| T-F7 | 모르는 scenario·방향 길이 0 → ValueError |

**`test/test_sim_check.py`**
| ID | 확인 |
|---|---|
| T-S1 | judge_result·judge_cause: 일치 PASS, 하나라도 다르면 FAIL |
| T-S2 | judge_phases: = [PREPARE] PASS / [PREPARE, TRACK] FAIL, 접두사 [PREPARE, TRACK] PASS / [PREPARE, DESCEND] FAIL |
| T-S3 | judge_last_zero·judge_zero_hold: 사전 실험과 같은 모양 PASS / hold 중 0 아닌 틱 FAIL / hold 짧음 FAIL |
| T-S4 | judge_period: 평균 33.3 PASS / 40 FAIL |
| T-S5 | judge_follow: 벨트 반대 성분 FAIL, null tcp FAIL, 박스 상류(err_along −590 mm)의 0 명령 PASS, 박스 하류의 0 명령 FAIL, 해당 틱 30개 미만 UNKNOWN |
| T-S6 | judge_track_lock: 첫째 궤적 PASS, 둘째 값 섞임 FAIL |
| T-S7 | parse_gateway: 사전 실험 실제 로그 줄(normal·cancel) → watchdog 1·stop 0/1·move_stop 1/2 |
| T-S8 | judge_watchdog·move_stop·stop: 지연 0.71 PASS / 0.3 FAIL / 줄 없음 UNKNOWN / SIGINT 뒤 두 번째 watchdog 은 창 밖이라 무시 |
| T-S9 | exit_code·worst_code: FAIL 우선 1, UNKNOWN 만 2, 전부 PASS 0, [2, 1, 0] → 1 |
| T-S10 | preflight_problems: 도메인 "30" 거부, robot_gateway·belt_servo·fake_box 가 그래프에 있으면 거부, "34"·빈 그래프 통과 |

합계 30개 (launch_params 13 · fake_box 7 · sim_check 10).

## 9. 실물 확인 (L3·L4·L5 — code 단계)
- L3: `voss-ros ros2 launch voss_servo belt_servo.launch.py params:=<example 사본> config:=<레포 config> log_dir:=<scratch>` → "READY 거부: missing=[…]"·액션 서버 없음 / 값 채운 사본 → "READY"·config_sha256 = gateway 와 같은 12자리·`ros2 param get /belt_servo gripper.pre_open_mm` = 90.0(double).
- L4: `voss-ros ros2 run voss_servo sim_check --case all --out <scratch>/sim` → pre_u5 5 case 종료 코드 0.
- L5: ① `--profile grasp --case normal` 은 지금 main 에서 **FAIL(종료 코드 1)** 이어야 한다(도구가 실패를 잡는지) ② normal run 하나는 틱 로그·launch.log 를 손으로 계산해 J5·J6·J7 값과 대조.

## 10. `design/U3-run.md` 목차 (code 단계 6에서 작성, 실제 돌린 명령·출력만)
- (A) 공용 PC 실기 기동 (G0 T7): 선행(브링업 T1·T2, gateway T4 떠 있음) · 값 파일 준비(example → `~/voss_ws/config/belt_servo_real.yaml`, null 채우기는 측정값만) · 기동 명령 한 줄(`params:=`·`log_dir:=<레포>/data/servo`) · 기대 로그(launch 요약 줄, `config_version=… config_sha256=<gateway 와 같은 12자리> params_sha256=…`, `READY` 또는 `READY 거부: missing=[…]` 과 그때 할 일) · 확인 `ros2 action list` 에 `/voss/servo/track_and_grasp` · 끄는 순서(runbook 183행: belt_servo 를 gateway 보다 먼저) · 로봇을 움직이는 명령 없음.
- (B) 개인 PC sim: 빌드·`cd ~/cobot2/cobot2_voss` · `voss-ros ros2 run voss_servo sim_check --case all --out …` · 기대 출력 표(pre_u5 5 case) · 단계별 수동 절차(sim.launch 를 직접 띄우고 `ros2 action send_goal` 로 goal — **모든 sim 명령에 `log_dir:=/tmp/voss_sim/<이름>` 명시**) · run 폴더 구조 · 종료 코드 뜻 · U5 뒤 `--profile grasp`.

## 11. 변경 기록
- 2026-10-10 r1: 초안. 승인.
- 2026-10-10 r2: 독립 재검 반영 — Include 형식(`.items()`), sim yaml log.dir /tmp, fake_box T 8 s, `--no-launch` 삭제·사전 점검 J0, emulate_tty 삭제·색 끔, SIGINT 는 launch 에만·STOP 15 s, case 시작 뒤 stamp 만 인정, J7~J9 창 제한, J11 정의 보정, J12 범위 명시, NULL 비교 노드와 같게, worst_code, U3-run 목차, U5 머지 순서 메모, 테스트 30개.
