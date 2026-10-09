# U3 실행 절차 — belt_servo 기동(실기) · fake_box 시뮬(개인 PC)

- 이슈 #36 · 설계 [U3-hld.md](U3-hld.md)·[U3-dd.md](U3-dd.md) · 작성 2026-10-10
- 이 문서의 명령과 출력은 실제로 돌려 본 것이다(개인 PC). 실기 절(A)은 로봇을 움직이는 명령이 없다.
- **ROS 도메인**: 사용자 대화형·데모는 34. 작업 세션은 RULES §2 배정 대역만(U3 = 75~79) — 명령 앞에 `ROS_DOMAIN_ID=75` 처럼 붙인다. 같은 PC 에서 도메인이 겹치면 goal·servo_cmd 가 남의 노드로 간다.

## A. 공용 PC 실기 기동 — G0 runbook T7 (사람이 비상정지 옆에서)

### A.1 선행
- 브링업(T1·T2)과 robot_gateway(T4)가 떠 있다. gateway 로그에 `robot_gateway started: real …` 과 `voss_config version=1 sha256=<12자리>` 가 있다.
- 레포를 빌드했다: `colcon build --symlink-install --packages-select voss_msgs voss_servo` → `source install/setup.bash`.

### A.2 값 파일 준비 (처음 한 번)
```bash
cp src/voss_servo/config/belt_servo_real.yaml.example ~/voss_ws/config/belt_servo_real.yaml
```
- 값 파일은 레포 밖에 둔다(커밋하지 않는다).
- null 은 미측정이다. **측정해서 measurements 에 남긴 값만** 채운다. null 이 남아 있으면 belt_servo 는 기동하되 goal 을 받지 않는다(아래 A.4 ①).
- `belt.*`·`gripper.*`·`timing.*` 은 이 파일에 쓰지 않는다. voss_config 에서 launch 가 읽어 넘긴다(쓰면 launch 가 멈춘다).

### A.3 기동 명령 (T7 에 적을 한 줄)
```bash
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=$HOME/voss_ws/src/rokey_cobot2_VOSS/data/servo
```
- `config:=` 를 안 주면 gateway 와 같은 `~/voss_ws/config/voss_config.yaml` 을 읽는다.
- `log_dir:=` 는 꼭 준다. 시도 로그 `data/servo/attempts/` 가 게이트 증거다(레포 경로가 다르면 맞게 고친다).

### A.4 기대 로그
```
[launch.user]: belt_servo launch: params=…/belt_servo_real.yaml overrides=- config=…/voss_config.yaml config_sha256=<12자리> 넘김 N개, null 로 뺀 키 M개 […]
[belt_servo]: config_version=1 config_sha256=<12자리> params_sha256=<64자리>
[belt_servo]: READY                         ← ② 값을 다 채운 경우
[belt_servo]: READY 거부: missing=[…] invalid=[…] — 액션 서버 미생성   ← ① null 이 남은 경우
```
- `config_sha256` 은 gateway 로그의 `voss_config … sha256=` 과 **같아야 한다**(같은 voss_config 파일을 읽었다는 뜻).
- `params_sha256` 을 G0 기록표에 적는다(같은 값 = 같은 설정).
- ① 이면: missing 목록의 키를 측정값으로 채우거나, 측정 전이면 G0 에서 belt_servo 단계를 하지 않는다. invalid 는 교차 검사 실패(값 조합이 안 맞음).
- launch 가 노드를 띄우지 않고 멈추면(파일 없음·YAML 오류·규칙 5) 메시지에 경로와 이유가 나온다.

### A.5 확인
```bash
ros2 action list | grep track_and_grasp      # READY 면 /voss/servo/track_and_grasp 가 보인다
```

### A.6 끄는 순서 (runbook 183행)
`stop` → PAUSED 확인 → 벨트 12 V 끄기 → T8 sort_manager → **T7 belt_servo(Ctrl+C)** → T6 → … → gateway. belt_servo 를 gateway 보다 먼저 끈다(끊기면 gateway watchdog 이 0 속도 + move_stop).

### A.7 개인 PC 에서 같은 확인 (10/10 실측)
```bash
cd ~/cobot2/cobot2_voss
voss-ros ros2 launch voss_servo belt_servo.launch.py params:=<example 사본> config:=$PWD/config/voss_config.yaml log_dir:=/tmp/voss_l3
```
- example 그대로: `넘김 22개, null 로 뺀 키 16개` → `config_sha256=db97243ec6ef` → `READY 거부: missing=[control.kp_per_s, …]`, `ros2 action list` 비어 있음. (U5 #131 머지 전 main 에서는 `경고: PARAM_SPECS 에 없는 키(노드가 무시): [grasp.close_time_max_s, grasp.room_margin_mm, gripper_timeout_s]` 한 줄도 찍힌다 — 정상)
- 값을 다 채운 사본: `넘김 38개, null 로 뺀 키 0개` → `READY`, `/voss/servo/track_and_grasp` 보임, `ros2 param get /belt_servo gripper.pre_open_mm` = `Double value is: 90.0`(voss_config 의 정수 90 이 float 로), `retry.max_attempts` = Integer 1.
- 값을 채운 사본의 `params_sha256=2f6b9530…` 은 같은 값을 `--params-file` 로 준 사전 실험과 같다 → launch 로 띄워도 지문이 바뀌지 않는다.

## B. 개인 PC 시뮬 — sim_check (로봇 없음)

### B.1 한 번에 (권장)
```bash
cd ~/cobot2/cobot2_voss
colcon build --symlink-install --packages-select voss_msgs voss_servo voss_robot
voss-ros ros2 run voss_servo sim_check --case all --out /tmp/voss_sim/run1            # 사용자 (도메인 34)
ROS_DOMAIN_ID=75 voss-ros ros2 run voss_servo sim_check --case all --out /tmp/voss_sim/run1   # 작업 세션 (배정 대역)
```
- 시작 전 `voss-ros bash -c 'ros2 node list --no-daemon'` 가 비어 있는지 본다(sim_check 의 J0 도 같은 검사를 한다).
- 레포 안에서 실행한다(`--config` 기본 = git 최상위 `config/voss_config.yaml`). 다른 곳이면 `--config <경로>`.
- case 마다 sim.launch(fake_box + gateway dry_run + belt_servo)를 새로 띄우고 goal 1개 → 정리 → 판정. pre_u5 5 case 약 2분.
- 시작 전 사전 점검(J0): `ROS_DOMAIN_ID=30` 이거나 `robot_gateway`·`belt_servo`·`fake_box` 가 이미 떠 있으면 아무것도 띄우지 않고 종료 코드 2. 띄운 gateway 가 `dry_run` 이 아니면(J10) goal 을 보내지 않고 바로 끈다.
- 인자: `--case lost|invalid|cancel|normal|two_boxes|empty|all` · `--profile pre_u5|grasp` · `--kp <1/s>` · `--goal-timeout-s 30` · `--cancel-after-s 3`.

### B.2 기대 출력 (10/10 실측, main 309af67 + U3 — 도메인 34 에서 2회, 도메인 75 에서 1회)
| case | result | cause | phases | J5 0 유지 | J6 Δt 평균 | J7 watchdog | J8 move_stop | 기타 |
|---|---|---|---|---|---|---|---|---|
| lost | 6 / LOST | BOX_MISSING | [PREPARE] | 15~16틱 0.50~0.53 s | 33.3 ms | 1회 0.71~0.76 s | 1 | |
| invalid | 6 / STALE_INPUT | BOX_INVALID | [PREPARE] | 15~16틱 0.50~0.53 s | 33.3 ms | 1회 0.71~0.76 s | 1 | |
| cancel | 5 / CANCELED | STOP_OK | [PREPARE] | 15~16틱 0.50~0.53 s | 33.3 ms | 1회 0.71~0.76 s | 2 | stop 1 → OK |
| normal | 6 / OUT_OF_REACH | REACH_X_MAX | [PREPARE] | 15~16틱 0.50~0.53 s | 33.3 ms | 1회 0.71~0.76 s | 1 | J11 439~445틱 위반 0 |
| two_boxes | 6 / OUT_OF_REACH | REACH_X_MAX | [PREPARE] | 15~16틱 0.50~0.53 s | 33.3 ms | 1회 0.71~0.76 s | 1 | J12 최대 0.00 mm (track 1·2 둘 다 30 Hz 발행 — depth 10 구독자로 확인. depth 1 구독자는 같은 틱의 앞 건이 덮여 track 1 이 거의 안 보인다, belt_servo 는 depth 5) |

끝에 요약 표, 종료 코드 0. `--profile grasp --case normal` 은 지금(U5 전) **종료 코드 1**(J1·J2·J3 ❌)이 정상이다 — 도구가 실패를 잡는지 확인한 결과.

### B.3 종료 코드
`0` 전부 통과 · `1` 하나라도 불일치(❌) · `2` 판정 불가(⚠️: 자료 없음·시간 초과·사전 점검 거부). 여러 case 면 1 > 2 > 0.

### B.4 run 폴더 (`--out` 아래 case 마다)
`launch.log`(fake_box·gateway·belt_servo 출력 전부) · `ticks/`·`attempts/`(belt_servo JSONL) · `result.json`(goal_id·phases·status·reason·SIGINT 시각) · `verdict.json`(판정 표). 레포에 넣지 않는다.

### B.5 단계별로 손으로 볼 때
```bash
cd ~/cobot2/cobot2_voss
voss-ros ros2 launch voss_servo sim.launch.py config:=$PWD/config/voss_config.yaml scenario:=normal log_dir:=/tmp/voss_sim/manual
# 다른 터미널
voss-ros ros2 action send_goal --feedback /voss/servo/track_and_grasp voss_msgs/action/TrackAndGrasp "{track_id: 1}"
```
- **모든 sim 명령에 `log_dir:=/tmp/voss_sim/<이름>` 을 준다**(안 주면 sim yaml 의 `/tmp/voss_sim/servo`).
- dry_run 가짜 로봇은 goal 뒤 제자리에 남는다 → 다음 시험 전에 launch 를 끄고 다시 띄운다.
- **goal 은 launch 뒤 5 s 안에 보낸다.** fake_box 는 기동 순간부터 박스를 움직인다. goal 이 늦으면(약 7 s 이상) 박스가 멀리 앞서 P 항이 포화(0.08 m/s)되고, gateway 가 `x + v²/2a ≥ 638`(80 mm/s 면 606 mm)에서 vx 를 0 으로 자르는데 가짜 로봇은 램프 없이 그 자리에 서서 belt_servo 의 x_max 620 에 영영 닿지 못한다 → goal 이 PREPARE 에서 끝나지 않는다(gateway 통계에 `자름 {'x_max': …}` 가 계속 찍힘). 그렇게 되면 cancel 하고 launch 를 다시 띄운다. sim_check 는 박스가 오자마자(기동 뒤 1 s 안) goal 을 보내므로 해당 없다. 실로봇은 감속 램프로 638 근처까지 가므로 이 정지는 dry_run 에서만 생긴다(10/10 독립 재검 실측).
- scenario 는 `normal | invalid_after_s | lost_after_s | two_boxes`, 빈손은 `object_mm:=0`, kp 는 `kp:=<값>`.

### B.6 U5 뒤
`voss-ros ros2 run voss_servo sim_check --profile grasp --case all` → 목표: normal OK·grasped=true(phase 6개), empty GRASP_FAILED, cancel CANCELED.
- **알려진 상태(10/10)**: gateway 가짜 RG2 가 `닫힘 폭 < object_mm < 현재 폭` 으로 판정해서, 이미 물체 폭에서 멈춘 뒤 VERIFY 재닫기는 grip=false → normal 이 **VERIFY 에서 DROPPED(GRASP_FAILED)** 로 끝나 J1 ❌ 가 난다. 학민의 `<=` 수정 전까지는 이것이 정상 결과다. 기대값은 목표(OK)로 두었다(버그에 맞춰 기준을 낮추지 않는다).
- U5 #131 의 새 필수 키(`grasp.close_time_max_s`·`grasp.room_margin_mm`·`gripper_timeout_s`)는 example·sim yaml 에 미리 넣었다. #131 머지 전 main 노드는 이 키를 무시하고, launch 는 `경고: PARAM_SPECS 에 없는 키(노드가 무시): […]` 한 줄을 찍는다(정상). 이후 키가 더 생기면 test_launch_params T-L12 가 알려 준다.

### B.7 정리
sim_check 가 Ctrl+C·SIGTERM 을 받아도 sim 을 끄고 "중단됨" 한 줄과 종료 코드 2 로 끝난다(10/10 실측: goal 도중 SIGINT → 노드 셋 finished cleanly, 남은 프로세스 없음). sim_check 자체가 강제 종료(SIGKILL)되어 sim 이 남으면:
```bash
pgrep -af "ros2 launch voss_servo sim[.]launch"     # 남았는지 확인 → 그 PID 에 kill -INT
```
