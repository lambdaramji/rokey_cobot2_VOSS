# voss_servo

컨베이어 위 박스를 따라가며 내려가 RG2 로 집고 들어 올려 확인까지 하는 노드 `belt_servo` 패키지. 박스 관측(`/voss/vision/box`)과 로봇 TCP(`/voss/robot/pose`)를 받아 30 Hz 속도 명령(`/voss/robot/servo_cmd`)을 내고, sort_manager 에 액션 `/voss/servo/track_and_grasp` 를 제공한다.

**현황 (10/11):** 10/10 G0 1회차 완주(TrackAndGrasp `OK`, 시도 1) · G1 s1 **20사례 중 20 성공**, 모두 시도 1([measurements-1010](../../docs/measurements-1010.md)) · 테스트 243개 통과(`colcon test-result`: `243 tests, 0 errors, 0 failures, 0 skipped`).

설계 이유는 [DESIGN.md](DESIGN.md)(결정 카드)와 [design/](design/)(단위별 HLD·DD·pseudo·run)에 있다. 이 README 는 "무엇이 어디 있고 어떻게 돌리나"만 적는다.

## 1. 역할과 책임

| 한다 | 하지 않는다 (누가) |
|---|---|
| 박스 위치 예측(촬영 시각 + 벨트 속도) → TCP 목표 → FF+P 속도 → clamp → `servo_cmd` 30 Hz | 두산 서비스·RG2 직접 호출 — **robot_gateway** (`voss_robot`, 김학민). 규칙 3 |
| 단계 진행: 사전 개방 → 추종 → 하강 → 닫기 → 들기 → 확인 | 픽셀 → 베이스 좌표 변환, 지연 보정된 `position_base` — **box_tracker** (`voss_vision`, 남현지) |
| 그리퍼 호출(goal 실행 중에는 belt_servo 만), 쥠 판정, reason 결정 | 박스 선택·구역 판단·적재·전체 상태기계 — **sort_manager** (`voss_manager`, 남현지) |
| 종료 시 0 속도 보장, 시도 로그(게이트 증거) 기록 | 속도·작업 영역 최종 강제, watchdog — **robot_gateway** (여기서도 clamp 는 한다) |
| | `voss_config.yaml` 직접 읽기 — launch 가 값만 넘긴다 (규칙 5) |

- 담당: 박병후(@ok778ts123). 리뷰어(CODEOWNERS `/src/voss_servo/`): 김학민(@rokeyhak).
- 이슈: T25 #34 · T26 #35 · T27 #36 · T28 #37 · T29 #38, 게이트 #13.

## 2. 인터페이스

계약 원문: [topics.md](../../docs/interfaces/topics.md) belt_servo 행 · [voss_msgs.md](../../docs/interfaces/voss_msgs.md) TrackAndGrasp 행. 아래는 요약이며 충돌하면 계약이 우선이다.

| 종류 | 이름 | 타입 | QoS | 주기 | 의미 |
|---|---|---|---|---|---|
| 구독 | `/voss/vision/box` | `voss_msgs/msg/BoxTrack` | best_effort · volatile · depth 5 | 30 Hz | `position_base` = 촬영 시각(`stamp`)의 박스 윗면 중심, m, base_link. 트랙마다 따로 오므로 track_id 별로 보관 |
| 구독 | `/voss/robot/pose` | `geometry_msgs/PoseStamped` | best_effort · volatile · depth 1 | ~50 Hz | TCP(핑거 끝) pose, base_link |
| 발행 | `/voss/robot/servo_cmd` | `geometry_msgs/TwistStamped` | best_effort · volatile · depth 1 | 30 Hz (`rate_hz`) | TCP 선속도 m/s, frame `base_link`, 각속도 0, `header.stamp` = 발행 시각 |
| 액션 서버 | `/voss/servo/track_and_grasp` | `voss_msgs/action/TrackAndGrasp` | rclpy 기본 | goal 당 result 1건 | goal `track_id` → feedback `phase` → result `grasped`·`reason`·`attempts` |
| 서비스 호출 | `/voss/robot/gripper` | `voss_msgs/srv/Gripper` | — | phase 진입 때 | PREPARE 개방 · GRASP 닫기 · VERIFY 재닫기. `call_async` 후 틱마다 확인 |
| 서비스 호출 | `/voss/robot/stop` | `std_srvs/srv/Trigger` | — | 취소 때 | 정상 응답 → `CANCELED`, 응답 없음·오류 → `DEVICE_ERROR` |

box 구독 depth 5 는 소비자 재량이다(발행 쪽 depth 1 과 호환, topics.md 10/08 변경 이력).

**phase 6단계** (feedback, 진행 표시용): `PREPARE` → `TRACK` → `DESCEND` → `GRASP` → `LIFT` → `VERIFY`

**reason 7종** (sort_manager 는 status 가 아니라 reason 으로 분기한다):

| reason | action status | 뜻 |
|---|---|---|
| `OK` | SUCCEEDED | LIFT·VERIFY 완료 = 인계. `grasped=true` |
| `GRASP_FAILED` | ABORTED | 쥠 판정 실패(감지 없음·폭 범위 밖·VERIFY 에서 놓침) |
| `LOST` | ABORTED | 내 track_id 가 `input.lost_timeout_s` 동안 안 옴 |
| `OUT_OF_REACH` | ABORTED | 추종 구간 x 끝, 파지 높이 도달 불가, 또는 정렬 시점 x 여유 부족 |
| `STALE_INPUT` | ABORTED | `position_valid=false` 또는 pose 끊김이 `input.stale_timeout_s` 지속 |
| `DEVICE_ERROR` | ABORTED | 그리퍼·stop 서비스 실패, 내부 예외, 노드 종료 |
| `CANCELED` | CANCELED | 취소 후 `/voss/robot/stop` 정상 응답 |

`grasped=false` 는 "인계 미완료"이지 빈손이 아니다 — belt_servo 는 끝난 뒤 그리퍼를 자동으로 열지 않는다. 세부 원인은 로그의 `cause` 에 남는다(예: `BOX_MISSING`, `BOX_INVALID`, `POSE_MISSING`, `REACH_X_MAX`, `REACH_GRASP_ROOM`, `NOT_DETECTED`, `WIDTH_OUT`, `DROPPED`, `GRIPPER_<코드>`, `STOP_OK`, `NODE_SHUTDOWN`, `INTERNAL_EXCEPTION`).

## 3. 디렉터리 구조

```
src/voss_servo/
├── CLAUDE.md                 패키지 요약 (Claude·팀원용)
├── DESIGN.md                 결정 카드 BH-DEC-01~18, 미확정 경계
├── design/                   단위별 설계: U1(뼈대)·U2(제어)·U3(launch·sim)·U5(파지) 의 hld/dd/pseudo, U3-run·U6-run 절차서
├── config/
│   ├── belt_servo.yaml                 기본 파라미터 (미측정 = null)
│   ├── belt_servo_real.yaml.example    실기 값 파일 틀 (복사해서 레포 밖에 둔다)
│   └── belt_servo_sim.yaml             sim 전용 제안값 (실기 금지)
├── launch/
│   ├── belt_servo.launch.py  belt_servo 단독 기동 (실기·sim 공용)
│   └── sim.launch.py         fake_box + robot_gateway dry_run + belt_servo
├── voss_servo/
│   ├── belt_servo.py         ROS 노드 (구독·발행·액션·타이머·서비스 호출·로그)
│   ├── params.py             파라미터 표 PARAM_SPECS, 기동 검사, 지문
│   ├── fsm.py                픽업 상태기계 (전이·reason·attempts·쥠 판정)
│   ├── control.py            예측·TCP 외삽·FF+P·Z 계획·clamp·영역
│   ├── grip.py               그리퍼 호출 생애·message 코드·x 여유
│   ├── log_schema.py         틱·시도 로그 레코드, JSONL 쓰기
│   ├── launch_params.py      launch 파라미터 합치기 (null 제거·형 맞추기)
│   ├── fake_box.py           가짜 /voss/vision/box (sim)
│   ├── sim_check.py          sim 자동 실행·판정
│   └── gate_summary.py       시도 로그 → G1 기록표
└── test/                     pytest 13개 파일 (5절 표)
```

실행 파일(setup.py): `belt_servo` · `fake_box` · `sim_check` · `gate_summary`.

## 4. 동작 구조

### 4.1 노드 안의 데이터 흐름

```
/voss/vision/box ─▶ _on_box  ─▶ track_id 별 최신값 + 수신 시각   (콜백은 보관만)
/voss/robot/pose ─▶ _on_pose ─▶ 최신 pose + 수신 시각

30 Hz 타이머 _on_tick (판단은 여기 한 곳)
  ① _build_event : 입력 나이·valid·사각 여부 + control.geometry() (aligned·at_*_height·reach)
                   + 그리퍼 응답 poll(grip.poll) + x 여유(grip.grasp_room_ok)
  ② fsm.step     : 다음 phase · 종료 reason · 행동(GRIPPER_OPEN/CLOSE/VERIFY, REQUEST_STOP)
  ③ _handle_actions ─▶ /voss/robot/gripper, /voss/robot/stop  (call_async, 기다리지 않음)
  ④ control.command : 새 phase 기준 속도 → clamp (stopping·terminal 이면 0)
  ⑤ servo_cmd 발행 · feedback(phase) 발행
  ⑥ 로그 ─┬─ 틱 로그   <log.dir>/ticks/servo_ticks_<시각>.jsonl     (매 틱, git 미추적)
          └─ 시도 로그 <log.dir>/attempts/servo_attempts_<시각>.jsonl (ATTEMPT_END·GOAL_END, 게이트 증거)
  ⑦ 종료면 result 를 채우고 zero_hold_s 동안 0 을 계속 발행
```

액션 `execute` 콜백은 결과(Future)를 기다리기만 하고 실제 진행은 타이머가 한다. 단일 executor 다(DEC-14).

### 4.2 픽업 상태기계 (`fsm.py`)

```
goal ─▶ PREPARE ──개방 응답──▶ TRACK ──정렬(aligned)──▶ DESCEND ──파지 높이──▶ GRASP
         (사전 개방 요청)          │ x 여유 부족 → OUT_OF_REACH          (닫기 요청, attempts+1)
                                                                              │ HELD
        OK(grasped=true) ◀──HELD── VERIFY ◀──들기 높이── LIFT ◀────────────────┘
                              (재닫기 요청)
```

| phase | XY 속도 | Z | 그리퍼 |
|---|---|---|---|
| PREPARE | 보이면 FF+P, 안 보이면 FF | 접근 높이로 | 개방 요청 |
| TRACK | 보이면 FF+P, 잠깐 안 보이면 FF | 접근 높이 유지 | — |
| DESCEND | 사각 전 FF+P, 사각 구간 FF 만 | 파지 높이로 | — |
| GRASP | FF 만 | 고정 | 닫기 요청 |
| LIFT | 0 | 들기 높이로 | — |
| VERIFY | 0 | 0 | 닫기 재전송으로 확인 |

- 한 틱에 전이표 위에서부터 처음 맞는 한 줄만 적용한다: 취소·stop 대기 → 그리퍼 실패 → 입력(pose·box) → 영역 → 정상 진행.
- GRASP → LIFT 는 닫힘 응답 + `grip_detected` + 보고 폭이 `grasp.hold_width_min_mm`~`max_mm` 안일 때만. 닫힘만으로는 올라가지 않는다.
- 비전 사각 구간(TCP 가 박스 윗면 + `z.vision_cutoff_above_top_mm` 아래, 그리고 GRASP·LIFT·VERIFY)에서는 박스 미수신을 LOST/STALE 로 보지 않고 마지막 유효 관측 + 벨트 속도로 간다. pose 끊김은 사각에서도 STALE_INPUT.
- 상태기계 표와 전이 번호: [design/U1-dd.md](design/U1-dd.md) 2절, x 여유: [design/U5-hld.md](design/U5-hld.md).

### 4.3 안전 규칙 (코드로 보장)

| 규칙 | 위치 |
|---|---|
| 기동 검사(READY) 실패면 **액션 서버를 만들지 않는다.** 로그 `READY 거부: missing=[…] invalid=[…] — 액션 서버 미생성` | `belt_servo.py` `_startup_check`·`_setup_ros` |
| goal 이 어떻게 끝나든 종료 틱은 0, 이어서 `zero_hold_s` 동안 0 반복. 진행·0 유지 중이거나 `track_id ≤ 0` 인 goal 은 reject | `_finish`·`_start_hold`·`_tick_hold` |
| 0 명령에는 가속 제한을 걸지 않는다 (멈출 때는 바로 0) | `control.clamp` |
| goal 이 끝난 뒤 그리퍼 요청을 새로 보내지 않고, 늦게 온 응답은 버린다 | `grip.py`, `_orphan_gripper`·`_on_grip_late` |
| Ctrl+C·SIGTERM: rclpy 시그널 처리기를 끄고 첫 신호에서 이후 신호를 무시한 뒤, context 가 살아 있을 때 0 을 한 번 보내고 로그를 닫는다. 진행 중 goal 은 `DEVICE_ERROR`(cause `NODE_SHUTDOWN`) | `main`·`_on_stop_signal`·`destroy_node` |
| SIGKILL 등 강제 종료 때의 정지는 robot_gateway watchdog 책임 | ADR-0010 |

## 5. 모듈별 역할

| 모듈 | 책임 | 순수 | 들어가는 값 → 나오는 값 | 테스트 |
|---|---|---|---|---|
| `params.py` | 키 표 `PARAM_SPECS`(38키), 형·범위·교차 검사, `params_sha256` | 예 | 파라미터 dict → `ReadyReport`(ready·missing·invalid) | `test_params.py` |
| `fsm.py` | phase 전이, reason·cause, attempts, `judge_grip`, 사각 판정 | 예 | `FsmState` + `TickEvent` → `Transition`(다음 상태·행동) | `test_fsm.py` |
| `control.py` | `predict`·`tcp_now`·`tcp_target`·`split_error`·`ff_p`·`z_plan`·`clamp`·`in_reach`, 입구 `geometry`·`command` | 예 (NumPy, 단위 m·m/s·s) | 관측·pose·설정 → `Geometry` / `Command`(속도·clamped) | `test_control.py` |
| `grip.py` | 호출 이름표·순번, `message` → 코드, `poll`(응답·BUSY 재요청·TIMEOUT), `descend_time_s`·`grasp_room_ok` | 예 | `GripCall` + 응답·시각 → `PollResult` | `test_grip.py` |
| `log_schema.py` | 틱·시도 레코드(시도 키 ⊂ 틱 키), JSON 한 줄, `JsonlWriter` | 쓰기만 아님 | 틱 값 → JSON 줄 / 파일 | `test_log_schema.py` |
| `belt_servo.py` | ROS 연결, 이벤트 모으기, 서비스 호출, 로그 채우기 | 아니오 | 메시지 → 메시지·로그 | `test_node.py`·`test_action_e2e.py`·`test_shutdown.py` |
| `launch_params.py` | YAML 평탄화·null 제거·overrides·voss_config 키와 지문·형 맞추기 | 예 | YAML 경로들 → `BuildResult`(params·warnings) | `test_launch_params.py` |
| `fake_box.py` | 시나리오별 박스 위치 계산 + 30 Hz 발행 노드 | 계산 부분만 | 시각·시나리오 → `BoxSample` | `test_fake_box.py` |
| `sim_check.py` | sim 기동·goal·정리, `judge_*` 판정, 표·종료 코드 | 판정 부분만 | result·틱 로그·launch.log → `Verdict` | `test_sim_check.py` |
| `gate_summary.py` | 시도 로그 → g1-gate 11열 표·자동 힌트·"측정:" 문장 | 파싱·집계·렌더 부분 | `servo_attempts_*.jsonl` → Markdown | `test_gate_summary.py` |

`test_smoke.py` 는 import 확인. `test_action_e2e.py`·`test_node.py` 는 실행별 도메인(150 + pid % 70)을 쓴다.

## 6. 파라미터

원본 [config/belt_servo.yaml](config/belt_servo.yaml). 값의 근거·제안값 성격은 [design/U2-dd.md](design/U2-dd.md) 7절, 값 규칙은 [voss_config.md](../../docs/interfaces/voss_config.md).

| 그룹 | 키 | 기본 파일 값의 성격 |
|---|---|---|
| launch 가 voss_config 에서 넘김 | `belt.speed_cmps`·`belt.direction_base`·`gripper.pre_open_mm`·`grasp_width_mm`·`force_n`·`timing.latency_offset_ms`·`config_version`·`config_sha256` | **이 패키지 YAML 에 쓰면 launch 가 멈춘다** (규칙 5) |
| `grasp.*` | `tcp_z_below_top_mm` 19.0 | 결정값 (pending #16, ADR-0009) |
| | `hold_width_min_mm` 39.5 · `hold_width_max_mm` 43.5 · `close_time_max_s` 2.1 | T34 측정(measurements-1008 #14) 기반, 경계값은 제안 |
| | `room_margin_mm` 10.0 | 제안 (판단값) |
| `reach.*` | `x_min_mm` −107.0 · `x_max_mm` 620.0 | 측정(measurements #6) · 유효값 |
| `control.*` | `kp_per_s`·`kp_z_per_s`·`align_tol_along_mm`·`align_tol_cross_mm` | null (제안값은 주석) |
| `limits.*` | `max_speed_mps`·`max_acc_mps2` | null (제안 0.08 · 0.1) |
| `z.*` | `approach_above_top_mm`·`lift_above_top_mm`·`vision_cutoff_above_top_mm`·`descend_speed_mps`·`lift_speed_mps`·`height_tol_mm` | null |
| `input.*` | `stale_timeout_s`·`lost_timeout_s`·`pose_extrap_max_ms`·`blind_entry_max_age_s` | null |
| | `pose_lag_ms` 60.0 | 측정값, gateway `pose_source: service` 기준 |
| 기타 | `retry.max_attempts` 1 · `stop_timeout_s` 1.0 · `gripper_timeout_s` 3.0 · `rate_hz` 30.0 · `zero_hold_s` 0.5 · `log.dir` `data/servo` | 계약(30 Hz)·제안값. 재시도 3회는 U9 |

- **null = 미측정.** launch 는 null 키를 넘기지 않고, 노드는 필수 키가 비면 READY 를 거부한다(`--params-file` 로 직접 넘겨 문자열 `"null"` 이 와도 미측정으로 본다). 모르는 값으로 움직이지 않는 것이 정상 동작이다.
- `input.pose_lag_ms` 는 gateway `pose_source` 와 짝이다. G0 런북 T7 은 `joint_states` 면 0, `service` 면 60 을 쓴다([g0-runbook.md](../../docs/g0-runbook.md) T7, measurements-1010 #10). 기본 파일은 아직 60 이다.
- 실기 값 파일은 **레포 밖** `~/voss_ws/config/belt_servo_real.yaml` (`.gitignore` 로 커밋 차단). 틀은 [belt_servo_real.yaml.example](config/belt_servo_real.yaml.example).
- 일부 값만 바꾸려면 같은 모양의 YAML 을 `overrides:=<경로>` 로 준다(예: 첫 실기 FF 만 = 런북의 `belt_servo_kp0.yaml`). 합치는 순서: `params` → `overrides` → `log_dir` → voss_config → 형 맞추기(`PARAM_SPECS` 종류대로, `90` → `90.0`).
- 세 YAML(기본·example·sim)의 키 집합은 같아야 한다 — `test_launch_params.py` T-L12 가 검사한다.

## 7. 실행 방법

### 7.1 개인 PC — 빌드·테스트·린트

워크스페이스(`~/voss_ws`)에서 빌드·테스트, 린트는 레포 루트에서 실행한다(루트 `pyproject.toml` 설정).

```bash
cd ~/voss_ws && colcon build --symlink-install --packages-up-to voss_servo   # voss_robot 도 exec_depend 라 함께 빌드
source install/setup.bash
colcon test --packages-select voss_servo && colcon test-result --verbose
cd ~/voss_ws/src/rokey_cobot2_VOSS && ruff check src/voss_servo && ruff format --check src/voss_servo
```

같은 PC 에서 다른 작업과 겹치지 않게 `ROS_DOMAIN_ID` 를 따로 잡는다(공용 PC 30 은 쓰지 않는다).

### 7.2 개인 PC — sim (로봇 없음)

`sim_check` 가 case 마다 `sim.launch.py`(fake_box + robot_gateway `dry_run:=true` 고정 + belt_servo)를 새로 띄우고 goal 1개를 보낸 뒤 판정한다. 레포 루트에서 실행한다.

```bash
colcon build --symlink-install --packages-select voss_msgs voss_servo voss_robot
ros2 run voss_servo sim_check --case all --out /tmp/voss_sim/run1                    # pre_u5 프로필
ros2 run voss_servo sim_check --profile grasp --case all --out /tmp/voss_sim/run2    # 파지까지
```

- 인자: `--case lost|invalid|cancel|normal|two_boxes|empty|all` · `--profile pre_u5|grasp` · `--kp` · `--goal-timeout-s` · `--cancel-after-s` · `--config`.
- 종료 코드: `0` 전부 통과 · `1` 불일치 · `2` 판정 불가. 사전 점검(J0)은 `ROS_DOMAIN_ID=30` 이거나 gateway·belt_servo·fake_box 가 이미 떠 있으면 아무것도 띄우지 않고 2 로 끝난다.
- 단계별로 손으로 볼 때는 `sim.launch.py` + `ros2 action send_goal` — 절차와 주의(goal 은 launch 뒤 5 s 안에)는 [design/U3-run.md](design/U3-run.md) B.5.

### 7.3 공용 PC — 실기 (G0 런북 T7)

> 로봇·벨트·그리퍼를 움직이는 명령은 **사람이 비상정지 옆에서** 실행한다(CLAUDE.md 규칙 6). Claude 는 실행하지 않는다.

선행: 브링업(T1)·robot_gateway(T2)가 떠 있다. 처음 한 번 값 파일을 만든다.

```bash
cp src/voss_servo/config/belt_servo_real.yaml.example ~/voss_ws/config/belt_servo_real.yaml   # null 은 측정값으로만 채운다
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=$HOME/voss_ws/src/rokey_cobot2_VOSS/data/servo
```

| 확인 | 정상 |
|---|---|
| 기동 로그 | `config_version=… config_sha256=<12자리> params_sha256=<64자리>` 다음 `READY` |
| `config_sha256` | T2 gateway 로그의 voss_config sha256 앞 12자리와 같음 |
| `pose_lag_ms=…` 줄 | gateway `pose_source` 와 맞음(service → 60, joint_states → 0) |
| `ros2 action list` | `/voss/servo/track_and_grasp` 보임 |

`READY 거부: missing=[…]` 는 그 키가 null, `invalid=[…]` 는 교차 검사 실패다. 끌 때는 **gateway 보다 먼저** belt_servo 를 Ctrl+C 로 끈다(런북 183행 순서).

### 7.4 로그와 게이트 집계

| 로그 | 위치 | git |
|---|---|---|
| 틱 로그 (30 Hz, goal 진행 중 + 0 유지 구간) | `<log.dir>/ticks/servo_ticks_<YYYYmmdd_HHMMSS>.jsonl` | 미추적 |
| 시도 로그 (ATTEMPT_END·GOAL_END) | `<log.dir>/attempts/servo_attempts_<YYYYmmdd_HHMMSS>.jsonl` | 추적 (게이트 증거) |

노드 기동 1회 = 파일 1쌍. G1 집계는 GOAL_END 행 1개 = 사례 1건으로 센다.

```bash
ros2 run voss_servo gate_summary data/servo --since 2026-10-10T14:05 --series s1                       # 중간 확인
ros2 run voss_servo gate_summary data/servo --since <시각> --series s1 --ticks data/servo \
  --exclude <goal_id 앞 8자리> --md docs/measurements-1010.md                                        # 최종, 파일 끝에 붙임
```

원인 열은 비워 두고 사람이 영상·로그로 채운다. 자세히: [design/U6-run.md](design/U6-run.md), 판정 기준: [g1-gate.md](../../docs/g1-gate.md).

## 8. 수정·확장 가이드

| 바꾸려는 것 | 고칠 곳 | 같이 고칠 테스트·문서 |
|---|---|---|
| 속도 계산(예측·FF+P·clamp·Z) | `control.py` | `test_control.py`, design/U2-* |
| 단계 전이·reason 조건 | `fsm.py` | `test_fsm.py`(전이표 번호), design/U1-dd.md 2절 |
| 그리퍼 판정·재요청·x 여유 | `grip.py`, `fsm.judge_grip` | `test_grip.py`, `test_action_e2e.py` |
| 파라미터 추가 | `params.py` `PARAM_SPECS`(검사 포함) → `config/belt_servo.yaml`·`belt_servo_real.yaml.example`·`belt_servo_sim.yaml` 세 곳 | `test_params.py`, `test_launch_params.py` T-L12 |
| 로그 필드 | `log_schema.py` (시도 키는 틱 키의 부분집합 유지) → `gate_summary.py` 읽는 쪽 | `test_log_schema.py`, `test_gate_summary.py` |
| 새 sim 시나리오 | `fake_box.py` `SCENARIOS` → `sim.launch.py` 인자 → `sim_check.py` 기대값 | `test_fake_box.py`, `test_sim_check.py` |

- **설계 흐름:** 단위 하나마다 HLD → DD → pseudo → code 순서로 `design/U<n>-{hld,dd,pseudo}.md` 를 먼저 쓰고 승인받는다. 결정 이유가 바뀌면 [DESIGN.md](DESIGN.md) 해당 카드를 갱신한다.
- **PR:** 브랜치 `<type>/<이슈>-voss_servo-<설명>`, 리뷰어 김학민(CODEOWNERS). 토픽·메시지 필드·액션·`voss_config.yaml` 을 바꾸면 코드보다 먼저 `docs/interfaces/` 를 고치고 `interface` 라벨(규칙 2). 실측값은 measurements 문서에만.
- **금지:** `/dsr01/...`·RG2 직접 호출(규칙 3) · `voss_config.yaml` 직접 읽기(규칙 5) · D435i 깊이 사용(규칙 4) · 실로봇 명령의 자동 실행(규칙 6) · 실값 파일·로그 이외 데이터 커밋(규칙 8).

## 9. 관련 문서

| 문서 | 내용 |
|---|---|
| [DESIGN.md](DESIGN.md) | 결정 카드 18개, 우선순위(§4), 미확정 경계(§9) |
| [design/U1-hld.md](design/U1-hld.md) · [U2-hld.md](design/U2-hld.md) · [U3-hld.md](design/U3-hld.md) · [U5-hld.md](design/U5-hld.md) | 뼈대 · 제어 · launch/sim · 파지 설계 (각 DD·pseudo 동봉) |
| [design/U3-run.md](design/U3-run.md) · [design/U6-run.md](design/U6-run.md) | 실기 기동·sim 절차 · 게이트 집계 사용법 |
| [docs/interfaces/topics.md](../../docs/interfaces/topics.md) · [voss_msgs.md](../../docs/interfaces/voss_msgs.md) | 토픽·액션 계약 |
| [ADR-0009](../../docs/adr/0009-grasp-31mm-width.md) · [ADR-0010](../../docs/adr/0010-doosan-servo-command-path.md) · [ADR-0012](../../docs/adr/0012-numeric-targets-approved.md) · [ADR-0002](../../docs/adr/0002-grasp-method-gate.md) | 31 mm 폭 파지 · 두산 서보 경로(speedl_stream) · 수치 목표 · 게이트 |
| [measurements-1006](../../docs/measurements-1006.md) · [1008](../../docs/measurements-1008.md) · [1010](../../docs/measurements-1010.md) | 실측값 |
| [g0-runbook.md](../../docs/g0-runbook.md) · [g1-gate.md](../../docs/g1-gate.md) | 현장 기동 순서 · 게이트 절차 |

## 10. 알려진 한계·후속

- **재시도 동작은 U9(T28 #37).** 지금 `retry.max_attempts` 는 1 이라 GRASP_FAILED 가 첫 실패에서 바로 난다. 계약상 최대 3회.
- **x ≥ 600 z 처짐:** TRACK z 목표 140.8 에서 x 618 → 136.5 로 2/2 재현(measurements-1010 #13). 원인 조사 중.
- **사각 진입 전 LOST:** G1 의도 시험의 LOST 3회는 시야가 윗면 +31~37 mm 에서 끊긴 뒤 사각(`vision_cutoff_above_top_mm`) 진입 전에 `lost_timeout_s` 가 먼저 지났다(measurements-1010 의도 시험 절). 분석 중.
- `input.pose_lag_ms` 기본 파일·example 은 60 이고, `joint_states` 기준 값(0)은 시험값이다 — 반영은 후속. `grasp.hold_width_max_mm` 도 기본 43.5 이지만 10/10 현장은 44.0 을 썼다(measurements-1010 #10) — 기본값 갱신 후속.
- 미정값: Kp·안전 한계·단계 전환 값은 제안값만 있고, 48 mm/s 에서의 `acc`·watchdog 초과 거리, belt_servo READY 상태 토픽은 미확정이다(DESIGN.md §9).
