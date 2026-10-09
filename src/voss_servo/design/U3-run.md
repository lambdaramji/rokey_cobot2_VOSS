# U3 실행 절차 — belt_servo 기동(실기) · fake_box 시뮬(개인 PC)

- 이슈 #36 · 설계 [U3-hld.md](U3-hld.md)·[U3-dd.md](U3-dd.md) · 작성 2026-10-10
- 이 문서의 명령과 출력은 실제로 돌려 본 것이다(개인 PC, 도메인 34). 실기 절(A)은 로봇을 움직이는 명령이 없다.

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
- example 그대로: `넘김 17개, null 로 뺀 키 18개` → `config_sha256=db97243ec6ef` → `READY 거부: missing=[grasp.hold_width_min_mm, …]`, `ros2 action list` 비어 있음.
- 값을 다 채운 사본: `넘김 35개, null 로 뺀 키 0개` → `READY`, `/voss/servo/track_and_grasp` 보임, `ros2 param get /belt_servo gripper.pre_open_mm` = `Double value is: 90.0`(voss_config 의 정수 90 이 float 로), `retry.max_attempts` = Integer 1.
- 값을 채운 사본의 `params_sha256=2f6b9530…` 은 같은 값을 `--params-file` 로 준 사전 실험과 같다 → launch 로 띄워도 지문이 바뀌지 않는다.

## B. 개인 PC 시뮬 — sim_check

(2부 구현 뒤 작성)
