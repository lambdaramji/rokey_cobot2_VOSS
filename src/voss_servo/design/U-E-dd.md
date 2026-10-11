# U-E 두산 에뮬레이터 전구간 가상 실험 — Detail design

- 이슈 #36 · HLD [U-E-hld.md](U-E-hld.md) · 작성 2026-10-10 · 결과는 [U-E-run.md](U-E-run.md)
- 모든 명령은 **개인 PC, 도메인 85**, 워크트리 `~/cobot2/cobot2_voss-emu`. 로봇·벨트·그리퍼는 없다.
- 약어: `WS=$HOME/cobot2/cobot2_voss-emu`, `OUT=/tmp/voss_emu`, 래퍼는 `~/.local/bin/` 의 `voss-ros`·`voss-dsr-virtual-{up,down,exec}`. 아래 명령은 블록 단위로 따로 실행해도 되게 **절대 경로**로 적었다(도구 셸은 호출마다 cwd 가 초기화된다).

## 0. DD 에서 정한 것 (승인 항목)

| ID | 결정 | 이유 |
|---|---|---|
| D1 | 모든 명령에 `ROS_DOMAIN_ID=85` 를 앞에 붙인다. 래퍼 3종 모두 이 환경값을 쓴다 | 지시서 UE-36 "도메인 85–89 만"(RULES §2 표에는 같은 대역이 U-B 로 적혀 있다 — U-B 는 done 이라 겹치지 않음). 34 는 사용자 전용 |
| D2 | gateway 는 main + **PR #139 diff 로컬 적용(미커밋)**. 10/10 실험은 main 280f786 + #139 a25d0c2 + #134 99422b3; 10/11 최종 재검은 #134 가 main 92baa72 에 머지된 뒤 #139 head **a0db91e**(started 줄·RobotState.detail·5 s 로그에 `RG2 FAKE`, 에뮬레이터 노드 `/dsr01/virtual_node` 없으면 기동 거부, `test/test_rg2_dry_run.py` 추가)로 같은 판정. PR 전 `git checkout -- src/voss_robot` + 추가된 untracked 파일 제거(C14) | **주관 세션 결정(10/10) — 지시서 "수정 금지: src/voss_robot"·RULES §2 의 예외**이며 커밋·PR 에 넣지 않는다. 회신 "가정" 항목에 명시. 머지는 G1 뒤라 기다리면 오늘 실험이 안 된다 |
| D3 | 관측 자세 세팅 = `motion/move_joint` 에 measurements #6 관절값 `[-93.89, -13.54, 97.73, -0.01, 94.88, -185.08]`, vel 30·acc 30 deg/s(²), SYNC. **gateway 가 떠 있지 않을 때만**, case 마다 반복 | 전원 기동 자세는 관절 0 으로 추정(C2 에서 기록). 두산 서비스를 gateway 밖에서 부르는 것은 측정 전용 일회성 예외(HLD §4)로 한정 |
| D4 | gateway 인자: `dry_run:=false rg2_dry_run:=true dry_run_object_mm:=40.5 pose_source:=service config:=$WS/config/voss_config.yaml`. z 하한·x 범위·watchdog 은 노드 기본값(78 / −107~638 / 0.2 s). `rg2_host`·`rg2_port` 는 rg2_dry_run 에서 무시되므로 쓰지 않는다 | G0 전제와 같은 값. 가짜 RG2 물체 40.5 = 실측 보고폭(CONTRACT) |
| D5 | belt_servo 값 = `belt_servo_sim.yaml`(sim 제안값) 그대로, `belt_servo.launch.py` 로 기동, `log_dir:=$OUT/<case>` | sim_check 와 같은 값이라 결과를 U3-run B.2 와 나란히 볼 수 있다. 값 수정 없음 |
| D6 | fake_box 는 `ros2 run` 으로 띄우고 벨트 값(`speed_cmps`·`direction_base`)은 `launch_params.config_values` 로 voss_config 에서 읽어 넘긴다. **goal 은 emu_goal.py 가 첫 `/voss/vision/box` 를 받는 즉시 보낸다**(sim_check `run_goal` 과 같은 방식; 실측 fake_box 노드 생성 뒤 약 2 s). 늦었으면 fake_box 를 끄고 다시 띄운 뒤 goal | sim.launch 의 "숫자를 복사하지 않는다" 유지. U5 x 여유 검사(`grip.grasp_room_ok`): 정렬 때 x_max 620 까지 벨트 4.8 cm/s × (하강 ≈2.64 s + 닫힘 2.1 s) + 10 ≈ 238 mm 가 남아야 하므로 TCP x ≤ ≈382 mm, 즉 fake_box 기동 뒤 약 10 s 안에 정렬돼야 한다. 늦으면 정렬(aligned)에 이르기 전에 P 포화 상태로 x_max 까지 쫓아가 **REACH_X_MAX** 로 끝난다(재검 late 실험: gateway `자름 x_max`, 두산 안내 3205 특이점 구역, 알람 1215 동반). REACH_GRASP_ROOM 은 정렬된 뒤에만 나온다(fsm.py:245). 몇 초가 한계인지는 미확인 |
| D7 | goal 클라이언트 = 스크래치 `emu_goal.py`(feedback phase 수집, 첫 박스 대기, cancel_after_s, 결과 → `result.json`). 수동 대안은 `ros2 action send_goal --feedback` + Ctrl-C(CLI 가 cancel 요청을 보낸다, ros2action send_goal.py:146~170) | sim_check 는 sim.launch(dry_run 고정)와 묶여 있어 그대로 못 쓴다. 판정 창(goal 수락~SIGINT)을 같게 하려면 ROS 시각을 남겨야 한다 |
| D8 | 판정 = 스크래치 `emu_judge.py` 가 sim_check 의 **순수 함수를 import** 해 J1 result·J2 cause·J3 phases·J4 마지막 0·J5 0 유지·J8 move_stop·J9 stop 을 그대로 쓰고, watchdog 은 **창 안 로그 줄 수만**(J7 의 지연 창은 쓰지 않음). J6 주기·J10 dry_run·J11 추종·J12 트랙 고정은 쓰지 않는다. J1 표기는 sim_check 형식 `4/OK/grasped=True`(4=SUCCEEDED, 5=CANCELED, 6=ABORTED) | 지시서 "수치 안 씀". sim_check 는 수정하지 않는다(U3 후속 옵션은 회신에) |
| D9 | case 순서 normal → cancel → lost. case 마다 belt_servo·fake_box 를 새로 띄우고, 사이에 gateway 를 끄고 `move_joint` 로 관측 자세 복귀 → gateway 다시(C3 → C4 부터) | 로봇이 goal 뒤 제자리에 남는다(U3-run B.5 와 같음). gateway 밖 서비스 호출을 gateway 미기동 상태로 한정하려면 gateway 를 꺼야 한다 |
| D10 | lost case 는 `lost_after_s:=3.0`. 이 값은 **fake_box 기동(노드 생성) 기준**이고 goal 과 무관(fake_box.py t0). LOST 는 마지막 수신 뒤 lost_timeout 0.5 s 가 지난 ≈3.5 s 에 판정된다. 기대 phases 는 표준 순서의 앞부분(판정은 그렇게 보고, 관측은 `[PREPARE, TRACK]`). goal 은 ≈2 s 에 나가므로 여유가 약 1 s 뿐 — 호스트가 느려 emu_goal 기동이 늦으면 "박스 메시지 없음" 으로 끝난다(그러면 다시) | 사각은 GRASP·LIFT·VERIFY 뿐 아니라 DESCEND 에서도 TCP z ≤ 윗면+10 mm 면 들어가 LOST 가 안 난다. 손 계산(kp 1.0·벨트 48 mm/s): 출발 ≈0.8 s, 정렬 ≥3.5~4 s, 사각 진입 ≈4.4 s 이상 → 4.0 s 는 판정과 겹칠 수 있어 3.0 s 로 |
| D11 | cancel 은 goal 수락 3 s 뒤(sim_check cancel case 와 같음). goal 상한 60 s, 넘으면 cancel 하고 "진행 안 됨" 으로 기록 | 1215 로 멈춰 PREPARE 가 안 끝나는 경우의 탈출구 |
| D12 | TCP 등록 시험(Q3)은 **세 case 뒤**, gateway 를 끈 상태에서 15 분 한도 | goal 결과를 "에뮬레이터 그대로" 상태에서 먼저 얻는다. 등록 여부는 speedl 경로에 영향이 없다(pose 는 config 오프셋) |
| D13 | 브링업 뒤 **브링업 자식 rviz2 만** 끈다(`pkill -f "[r]viz2 -d .*m0609_rg2_bringup"`). case 전마다 `free -m`, 여유 300 MB 미만이면 멈추고 사용자에게 알린다 | RAM 여유 ≈1.3 GB. 래퍼는 수정하지 않는다 |
| D14 | 모든 노드 출력은 `RCUTILS_COLORIZED_OUTPUT=0 PYTHONUNBUFFERED=1` 로 파일에 남긴다: `$OUT/bringup.log`, `$OUT/<case>/{gateway,belt_servo,fake_box}.log`, `result.json`, `ticks/`, `attempts/`. **띄운 프로세스는 PID 파일(`$OUT/<이름>.pid`)로 관리하고, 끌 때는 그 PID 에만 SIGINT** — 이름 패턴 pkill 은 다른 세션(도메인 34·75~84·90)의 같은 이름 프로세스까지 죽인다 | RULES §2 "내 프로세스만". sim_check 가 launch.log 를 판정하는 방식과 같다. 레포에 넣지 않는다 |
| D15 | 정지 확인(cancel) = `/dsr01/joint_states` 를 1 s 간격으로 두 번 읽어 joint_1~6 의 position 차이 < 1.7e-4 rad(≈0.01°). 실행 전 `topic info -v` 로 발행자 수를 기록(joint_state_publisher 가 같은 이름으로 함께 낼 수 있음) | 서비스 호출 없이(gateway 가 떠 있으므로) 토픽으로만 본다. echo 값 단위는 rad |

## 1. 절차와 명령 전문

### C0 사전 점검 (매번)
```bash
free -m | head -2
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros bash -c 'ros2 node list --no-daemon'                 # 비어 있어야 한다
pgrep -af "lib/voss_robot/robot_gatewa[y]|lib/voss_servo/belt_serv[o]|lib/voss_servo/fake_bo[x]|[b]ringup.launch|[d]sr_emulator" ; docker ps  # 비어 있어야 한다 (실행 파일 경로로 찾아 자기 셸·로그 이름 오탐 방지)
mkdir -p /tmp/voss_emu
cd $HOME/cobot2/cobot2_voss-emu && git diff --stat src/voss_robot && git status --short src/voss_robot   # #139 diff 가 얹혀 있는지 (파일 수는 head 에 따라 다름; a0db91e 는 untracked test 1개 포함)
```
비어 있지 않으면: 내 세션 것(`/tmp/voss_emu/*.pid` 의 PID)이면 `kill -INT $(cat …pid)` 로 정리하고, 다른 세션의 프로세스면 건드리지 않고 도메인을 86~89 로 바꾼다.

### C1 브링업 (에뮬레이터 + dsr_controller2), 백그라운드
```bash
ROS_DOMAIN_ID=85 RCUTILS_COLORIZED_OUTPUT=0 PYTHONUNBUFFERED=1 ~/.local/bin/voss-dsr-virtual-up > /tmp/voss_emu/bringup.log 2>&1 &
echo $! > /tmp/voss_emu/bringup.pid
sleep 15 && grep -n "activated dsr_controller2\|rror" /tmp/voss_emu/bringup.log | tail -5 ; docker ps --format '{{.Names}} {{.Status}}'
pkill -f "[r]viz2 -d .*m0609_rg2_bringup"       # 이 브링업의 rviz2 만. 브링업은 계속 돈다
```
기대: 약 10 s 뒤 `Configured and activated dsr_controller2`(메모리 dsr-emulator-wrappers), `docker ps` 에 `dsr01_emulator`.

### C2 로봇 상태 (읽기 전용, gateway 전)
```bash
E=~/.local/bin/voss-dsr-virtual-exec; P=/dsr01/dsr_controller2
ROS_DOMAIN_ID=85 $E call $P/system/get_robot_system dsr_msgs2/srv/GetRobotSystem
ROS_DOMAIN_ID=85 $E call $P/system/get_robot_mode   dsr_msgs2/srv/GetRobotMode
ROS_DOMAIN_ID=85 $E call $P/system/get_robot_state  dsr_msgs2/srv/GetRobotState
ROS_DOMAIN_ID=85 $E call $P/aux_control/get_current_posj dsr_msgs2/srv/GetCurrentPosj     # 기동 자세 기록 (관절 0 추정)
ROS_DOMAIN_ID=85 $E topic list | grep -E "joint_states|speedl_stream|servol_stream"
ROS_DOMAIN_ID=85 $E topic info -v /dsr01/joint_states | grep "Publisher count"             # 발행자 수 (D15; "Node name" 은 구독자까지 센다)
```
기대: `robot_system=1`(VIRTUAL), `robot_state=1`(STANDBY). mode(0 MANUAL / 1 AUTONOMOUS)·posj 는 기록만.

### C3 관측 자세 세팅 (gateway 가 꺼져 있을 때만, case 마다)
```bash
E=~/.local/bin/voss-dsr-virtual-exec; P=/dsr01/dsr_controller2
ROS_DOMAIN_ID=85 $E call $P/motion/move_joint dsr_msgs2/srv/MoveJoint \
  "{pos: [-93.89, -13.54, 97.73, -0.01, 94.88, -185.08], vel: 30.0, acc: 30.0, time: 0.0, radius: 0.0, mode: 0, blend_type: 0, sync_type: 0}"
ROS_DOMAIN_ID=85 $E call $P/aux_control/get_current_tool_flange_posx dsr_msgs2/srv/GetCurrentToolFlangePosx "{ref: 0}"
```
기대: `success: true`(래퍼 20 s 안: 최대 185°/30 deg/s ≈ 7 s), 플랜지 posx ≈ `[-11.5, -271.1, 450.2, 85.3, -179.1, -6.0]`(measurements #6) — 위치 ±5 mm(판단값). 에뮬레이터 운동학이 실로봇과 같다는 뜻. 다르면 그대로 기록.

### C4 robot_gateway real 모드, 백그라운드 (case 폴더마다; `CASE` 는 normal | cancel | lost | pose_js | tcp_reg)
```bash
CASE=normal; WS=$HOME/cobot2/cobot2_voss-emu; mkdir -p /tmp/voss_emu/$CASE
ROS_DOMAIN_ID=85 RCUTILS_COLORIZED_OUTPUT=0 PYTHONUNBUFFERED=1 ~/.local/bin/voss-ros --ws $WS \
  ros2 launch voss_robot robot_gateway.launch.py dry_run:=false rg2_dry_run:=true dry_run_object_mm:=40.5 \
  pose_source:=service config:=$WS/config/voss_config.yaml > /tmp/voss_emu/$CASE/gateway.log 2>&1 &
echo $! > /tmp/voss_emu/gateway.pid
for i in $(seq 1 30); do grep -q "컨트롤러 TCP" /tmp/voss_emu/$CASE/gateway.log 2>/dev/null && break; sleep 0.5; done   # TCP 확인 줄은 기동 1~8 s 뒤
grep -n "voss_config version\|RG2 가짜\|RG2 FAKE\|robot_gateway started\|컨트롤러 TCP\|두산 서비스가 안 보인다\|RobotState\|pose .* Hz" /tmp/voss_emu/$CASE/gateway.log | head
```
기대 로그(robot_gateway.py 문구):
```
voss_config version=1 sha256=db97243ec6ef                      ← 레포 config 의 12자리 (U3-run A.7 과 같음)
RG2 가짜(rg2_dry_run) — 실제 그리퍼는 움직이지 않는다. 실기에서는 끈다   ← WARN (#139 a25d0c2). a0db91e 부터는 started 줄 끝·RobotState.detail·5 s 로그에 `RG2 FAKE(rg2_dry_run)` 도 찍힌다
robot_gateway started: real /dsr01/dsr_controller2/, pose 50 Hz, servo watchdog 200 ms, max 100 mm/s, TCP z ≥ 78.0 mm, x -107~638 mm, acc [100.0, 10.0]
컨트롤러 TCP 등록 없음 → 플랜지 좌표로 명령 (차 x.x mm)          ← 예상. "voss_config 와 같음" 또는 ERROR 면 그대로 기록
RobotState READY connected=True …                                ← gripper_width_mm 100.0 (DryRunRg2 기본)
pose N Hz, rtt … fail 0, skip …                                  ← 5 s 마다. Hz·rtt 값은 기록하지 않는다
```
`두산 서비스가 안 보인다` 가 찍히면 브링업 미완 — C1 로그 확인. gateway 를 끌 때는 `kill -INT $(cat /tmp/voss_emu/gateway.pid); sleep 4`.

### C5 pose(service) 확인
```bash
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $HOME/cobot2/cobot2_voss-emu ros2 topic echo --once /voss/robot/pose
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $HOME/cobot2/cobot2_voss-emu ros2 topic echo --once /voss/robot/state
```
기대: `frame_id: base_link`, position ≈ (−0.0145, −0.2765, 0.2036) m = 관측 자세 TCP(geometry.flange_to_tcp(observe_pose, tcp_offset) = (−14.49, −276.54, 203.58) mm, U7 실로봇 값과 일치) ±0.005 m. RobotState `READY`, detail 에 TCP 메모.

### C6 pose(joint_states) 확인 — S4 에서 gateway 재기동 1회
```bash
kill -INT $(cat /tmp/voss_emu/gateway.pid); sleep 4           # 정상 종료(halt_on_exit 는 servo 비활성이라 조용)
# C4 블록을 CASE=pose_js, pose_source:=joint_states 로 다시 실행 (mkdir 포함)
grep -n "pose_source joint_states\|컨트롤러 TCP" /tmp/voss_emu/pose_js/gateway.log
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $HOME/cobot2/cobot2_voss-emu ros2 topic echo --once /voss/robot/pose
kill -INT $(cat /tmp/voss_emu/gateway.pid); sleep 4
```
기대: `pose_source joint_states 확인: 서비스 플랜지와 X.XX mm → 사용 (guard pose 지연 20 ms)`, pose position 이 C5 와 같음(±0.005 m). `거부`·`→ service` 가 나오면 그 줄을 기록.
**여기서 gateway 는 꺼져 있다.** 이후 goal case 는 반드시 C3(관측 자세) → C4(`pose_source:=service`, `CASE=<case>`) 부터 다시 시작한다(D9).

### C7 belt_servo (case 마다 — C4 gateway 가 떠 있는 상태에서, 백그라운드)
```bash
CASE=normal; WS=$HOME/cobot2/cobot2_voss-emu
ROS_DOMAIN_ID=85 RCUTILS_COLORIZED_OUTPUT=0 PYTHONUNBUFFERED=1 ~/.local/bin/voss-ros --ws $WS \
  ros2 launch voss_servo belt_servo.launch.py params:=$WS/src/voss_servo/config/belt_servo_sim.yaml \
  config:=$WS/config/voss_config.yaml log_dir:=/tmp/voss_emu/$CASE > /tmp/voss_emu/$CASE/belt_servo.log 2>&1 &
echo $! > /tmp/voss_emu/belt_servo.pid
sleep 5 && grep -n "belt_servo launch\|config_sha256\|READY\|로그:" /tmp/voss_emu/$CASE/belt_servo.log
```
기대: `넘김 38개, null 로 뺀 키 0개`, `config_sha256=db97243ec6ef`(gateway 와 같음), `READY`, `로그: ticks=… attempts=…`.

### C8 fake_box (goal 직전, 백그라운드)
```bash
CASE=normal; WS=$HOME/cobot2/cobot2_voss-emu
read SPEED DIR < <(ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $WS python3 -c \
 "from voss_servo.launch_params import config_values, file_sha, load_yaml; p='$WS/config/voss_config.yaml'; c=config_values(load_yaml(p), file_sha(p)); print(c['belt.speed_cmps'], '['+','.join(str(float(x)) for x in c['belt.direction_base'])+']')")
ROS_DOMAIN_ID=85 RCUTILS_COLORIZED_OUTPUT=0 PYTHONUNBUFFERED=1 ~/.local/bin/voss-ros --ws $WS \
  ros2 run voss_servo fake_box --ros-args -p scenario:=normal -p speed_cmps:=$SPEED -p direction_base:="$DIR" \
  -p lost_after_s:=3.0 > /tmp/voss_emu/$CASE/fake_box.log 2>&1 &
echo $! > /tmp/voss_emu/fake_box.pid
```
case 별 `scenario`: normal·cancel → `normal`, lost → `lost_after_s`(D10 의 3.0 s). **스크립트로 띄울 때는 `set -m`**(비대화형 bash 는 `&` 작업에 SIGINT 무시를 상속시킨다)을 켜고, 그러면 각 작업이 자기 프로세스 그룹이 되므로 끌 때 `kill -INT -- -$(cat …pid)` 로 ros2 run 부모와 노드 자식을 함께 끈다(`setsid` 는 쓰지 않는다 — fork 해서 PID 파일이 어긋난다). 터미널에서 손으로 띄우면 Ctrl-C 로 충분하다.

### C9 goal (fake_box 의 첫 박스를 받는 즉시 — emu_goal.py 가 기다린다)
```bash
CASE=normal   # cancel 이면 --cancel-after-s 3.0 을 붙인다. 스크립트 위치는 run.md §6
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $HOME/cobot2/cobot2_voss-emu python3 ~/cobot2/voss_emu_work/emu_goal.py --out /tmp/voss_emu/$CASE --goal-timeout-s 60
```
`[voss-ros] 거부: … 프로세스가 떠 있음` 이 나오면(래퍼 경합, run.md §4 ⑤) 1 s 뒤 다시. 그사이 박스가 앞서 갔으면(fake_box 기동 뒤 3 s 넘음) C8 부터 다시 띄운다.
수동 대안: `ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros --ws $HOME/cobot2/cobot2_voss-emu ros2 action send_goal --feedback /voss/servo/track_and_grasp voss_msgs/action/TrackAndGrasp "{track_id: 1}"` (fake_box 뒤 바로, cancel 은 Ctrl-C).

### C10 정지 확인 (cancel case 만, C9 result 직후·gateway 종료 전)
```bash
CASE=cancel
for i in 1 2; do ROS_DOMAIN_ID=85 ~/.local/bin/voss-dsr-virtual-exec topic echo --once /dsr01/joint_states | grep -A7 "^name\|^position"; sleep 1; done
grep -n "/voss/robot/stop →" /tmp/voss_emu/$CASE/gateway.log
```
기대: joint_1~6 의 position(rad) 차이 < 1.7e-4 rad(≈0.01°, D15). `/voss/robot/stop → OK` 1줄. normal·lost 는 건너뛴다.

### C11 정착 → 종료 (case 마다)
```bash
CASE=normal
sleep 1.5; grep -n "servo_cmd 끊김(watchdog)" /tmp/voss_emu/$CASE/gateway.log     # result 뒤 0 유지 0.5 s → 200 ms → 1줄
# 통계 줄(5 s 마다)이 watchdog 시각 뒤에 찍힐 때까지 0.2 s 간격으로 최대 8 s 기다린다 (sim_check 와 같음) — emu_case.sh 가 한다
grep -n "servo rx" /tmp/voss_emu/$CASE/gateway.log | tail -3
date +%s.%N > /tmp/voss_emu/$CASE/t_sigint                                        # 판정 창의 끝 (ROS 시각 = 벽시계)
kill -INT -- -$(cat /tmp/voss_emu/belt_servo.pid); kill -INT -- -$(cat /tmp/voss_emu/fake_box.pid)   # set -m 이면 그룹, 손으로 띄웠으면 Ctrl-C
# 둘이 사라진 뒤(최대 15 s) gateway: kill -INT -- -$(cat /tmp/voss_emu/gateway.pid)
grep -n "Traceback\|NODE_SHUTDOWN\|종료 정지" /tmp/voss_emu/$CASE/belt_servo.log /tmp/voss_emu/$CASE/gateway.log
pgrep -af "lib/voss_robot/robot_gatewa[y]|lib/voss_servo/belt_serv[o]|lib/voss_servo/fake_bo[x]" || echo "(내 노드 없음)"
```
기대: goal 이 끝난 뒤 끄므로 `NODE_SHUTDOWN`·`종료 정지` 줄은 **없는 것이 정상**(있으면 goal 중 종료 = 기록). `Traceback` 없음. belt_servo 종료 때 보내는 마지막 0 이 gateway 에 다시 무장돼 파일 전체에는 watchdog 줄이 2개일 수 있다(판정은 창 안 1개). 다음 case 는 C3 부터.

### C12 TCP 등록 시험 (Q3, 세 case 뒤, gateway 꺼진 상태, 15 분 한도)
```bash
E=~/.local/bin/voss-dsr-virtual-exec; P=/dsr01/dsr_controller2
ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros bash -c 'ros2 service list | grep -E "tcp/|tool/"'     # 서비스 이름 확인
ROS_DOMAIN_ID=85 $E call $P/tcp/config_create_tcp dsr_msgs2/srv/ConfigCreateTcp "{name: GripperDA_v1, pos: [1.382, 2.684, 246.642, 0.0, 0.0, 0.0]}"
ROS_DOMAIN_ID=85 $E call $P/tcp/set_current_tcp    dsr_msgs2/srv/SetCurrentTcp    "{name: GripperDA_v1}"
ROS_DOMAIN_ID=85 $E call $P/tcp/get_current_tcp    dsr_msgs2/srv/GetCurrentTcp
ROS_DOMAIN_ID=85 $E call $P/aux_control/get_current_posx dsr_msgs2/srv/GetCurrentPosx "{ref: 0}"
# 그 뒤 C4 블록을 CASE=tcp_reg 로 다시 실행해 "컨트롤러 TCP 등록 …" 줄을 기록하고 kill -INT 로 끈다
```
기대(정보 수집): 각 `success` 값, `get_current_tcp.info`, 등록되면 `get_current_posx` 가 플랜지+오프셋(z ≈ 203.6)으로 바뀌고 gateway 가 `voss_config 와 같음 (차 0.x mm)` 을 찍는다. 실로봇(자동 모드)에서는 `set_current_tcp` 가 success=False 였다(#121) — 에뮬레이터 결과를 run.md 에 그대로. 등록은 컨테이너 rm(C13)으로 사라진다.

### C13 정리
```bash
ROS_DOMAIN_ID=85 ~/.local/bin/voss-dsr-virtual-down
pgrep -af "lib/voss_robot/robot_gatewa[y]|lib/voss_servo/belt_serv[o]|lib/voss_servo/fake_bo[x]|[b]ringup.launch|[d]sr_emulator|[r]viz2 -d .*m0609" || echo "(없음)"
docker ps -a --filter name=dsr01_emulator --format '{{.Names}} {{.Status}}' ; ROS_DOMAIN_ID=85 ~/.local/bin/voss-ros bash -c 'ros2 node list --no-daemon'
```
### C14 되돌리기·검증 (PR 전)
```bash
cd ~/cobot2/cobot2_voss-emu && git checkout -- src/voss_robot && git status --short     # #139 가 추가한 untracked 파일(a0db91e: src/voss_robot/test/test_rg2_dry_run.py)은 checkout 으로 안 지워진다 → 그 파일만 지우고 다시 status. design/U-E-* 만 남아야. 커밋은 파일 3개를 명시해 add (`git add -A` 금지)
source /opt/ros/jazzy/setup.bash && source ~/ws_cobot_pjt/ws_dsr/install/setup.bash && colcon build --symlink-install --packages-select voss_msgs voss_servo voss_robot
source install/setup.bash && colcon test --packages-select voss_servo && colcon test-result --verbose
~/.local/bin/ruff check src/voss_servo && ~/.local/bin/ruff format --check src/voss_servo
```

## 2. 확인 항목과 기대값

| E | 완료 기준 | 항목 | 기대 | 판정 방법 | 에뮬레이터라 보지 않는 것 |
|---|---|---|---|---|---|
| E1 | 1 | 브링업 | dsr_controller2 활성 로그, `robot_system=1`, `robot_state=1`, `/dsr01/joint_states`·`speedl_stream` 존재, 기동 posj 기록 | C1·C2 | 100 Hz 오버런 경고 횟수 |
| E2 | 1 | 관측 자세 | `move_joint success=true`, 플랜지 ≈ measurements #6 값 ±5 mm | C3 | 이동 시간 |
| E3 | 1 | gateway real 기동 | `started: real /dsr01/dsr_controller2/` **와** `RG2 가짜(rg2_dry_run)` WARN 둘 다, sha256 12자리, RobotState `gripper_width_mm 100.0`, `서비스가 안 보인다` 없음 | gateway.log, state echo | — |
| E4 | 1 | TCP 확인(#121) | `컨트롤러 TCP 등록 …` 한 줄. "없음 → 플랜지 좌표" 예상. ERROR 면 "확인 필요" | gateway.log, RobotState.detail | — |
| E5 | 1 | pose(service) | pose 1건 이상, `base_link`, position ≈ 관측 TCP ±0.005 m, 통계 `fail 0` | C5 | Hz·rtt |
| E6 | 1 | pose(joint_states) | `joint_states 확인 … → 사용`, position 이 E5 와 같음 ±0.005 m (차이 mm 는 위치값이라 기록) | C6 | stamp 지연 |
| E7 | 2 | normal | J1 `4/OK/grasped=True` · J2 cause `""` · J3 phases 6개 표준 순서 · J4 마지막 cmd 0 · J5 0 유지 통과 · 창 안 watchdog 줄 1 · J8 `move_stop ok 1 fail 0` · J9 stop 0 · gripper 로그 3줄(90 OK grip False / 39 폭 40.5 grip True / 39 grip True) · 통계 `거부 0`(old·no_pose 가 있으면 횟수 기록). **막히면** 마지막 phase·reason·cause·gateway 마지막 경고 | emu_judge.py + gateway.log | Δt·추종 오차·지연. 알람 1215/1216 횟수는 "특성" 칸에 |
| E8 | 3 | cancel | J1 `5/CANCELED/grasped=False` · J2 `STOP_OK` · `/voss/robot/stop → OK` 1줄 · J8 `move_stop ok 2` · J9 stop 1 OK · J4·J5 · 정지: 관절 차 < 1.7e-4 rad (C10) | emu_judge.py + C10 | 정지까지 시간·거리 |
| E9 | 4 | lost | J1 `6/LOST/grasped=False` · J2 `BOX_MISSING` · J3 `[PREPARE]` 또는 `[PREPARE, TRACK]`(DESCEND 까지 허용) · J4·J5 · 창 안 watchdog 1 · J8 `move_stop ok 1` · J9 stop 0 | emu_judge.py | LOST 까지 시간 |
| — | 5 | 끊김 실험 | 하지 않는다(ADR-0010 조건 6) | 절차에 없음 | — |
| E10 | Q3 | TCP 등록 시험 | `config_create_tcp`·`set_current_tcp` success 값, `get_current_tcp.info`, 재기동 gateway 의 TCP 줄 | C12 | — |
| E11 | 6 | 정리 | launch 의 `process has finished cleanly`·Traceback 없음, pgrep 0, 컨테이너 없음, node list 비어 있음 | C11·C13 | — |
| E12 | 6 | 검증 | voss_robot 되돌린 뒤 build·test·ruff 통과, `git status` 에 design 문서만 | C14 | — |

E7~E9 공통 보조 기록(gateway.log 통계 줄 합계): `speedl N`(발행 수 > 0), `거부 {…}`, `자름 {…}`, `두산 알람`/`두산 안내` 줄 수.

## 3. case 별 기대값 (sim_check `Expect` 재사용)
| case | fake_box scenario | cancel | Expect | 출처 |
|---|---|---|---|---|
| normal | normal | — | `EXPECT[("grasp","normal")]` = `Expect(4, "OK", "", True, PHASES)` | sim_check |
| cancel | normal | 3.0 s | `EXPECT[("grasp","cancel")]` = `Expect(5, "CANCELED", "STOP_OK", False)` | sim_check |
| lost | lost_after_s (3.0) | — | `Expect(6, "LOST", "BOX_MISSING", False)` (phases 는 표준 순서 앞부분, 마지막 무관) | U-E 정의 (grasp 프로필에 lost 가 없음) |

## 4. 스크래치 스크립트 (레포 밖, 커밋 안 함)

| 파일 | 역할 | 함수 |
|---|---|---|
| `emu_goal.py` | 첫 `/voss/vision/box` 를 기다렸다가 goal 1개를 보내고 feedback phase 를 모은 뒤 `result.json` 에 쓴다. `--cancel-after-s` 면 그 시각에 cancel | `parse_args` · `wait_server` · `wait_first_box`(sim_check 와 같은 best_effort depth 5 구독) · `send_and_wait`(sim_check.run_goal 과 같은 루프: feedback 콜백, cancel, 상한) · `write_result`(goal_id hex, phases, status, reason, grasped, attempts, t_goal·t_result = ROS 초, cancel_sent, error) |
| `emu_judge.py` | `result.json`·`ticks/`·`attempts/`·`gateway.log`·`t_sigint` 를 읽어 표를 찍는다 | `load_case`(Expect) · `read_logs`(sim_check `read_jsonl`·`select_goal_rows`·`split_goal_ticks`·`read_lines`·`parse_gateway`) · `judge_all`(sim_check `judge_result`·`judge_cause`·`judge_phases`·`judge_last_zero`·`judge_zero_hold`·`judge_move_stop`·`judge_stop` + `watchdog_count`(창 안 줄 수 == 1)) · `gateway_extras`(speedl 합계·거부·자름·알람 줄 수·gripper 줄) · `format_table`(sim_check 것) |
| `emu_case.sh` | C3·C4·C5·C7~C11 을 case 하나로 묶는다(인자: case 이름; cancel 이면 C10 포함; C6 은 S4 에서 1회만이라 넣지 않음). 통계 줄 대기 루프 포함. 명령은 위 전문과 같다 | — |

판정 창: `win = (result.json 의 t_goal, t_sigint 파일의 시각)`. 두 시각 모두 벽시계(ROS 시각 = 벽시계, sim_check 와 같은 전제).

## 5. run.md 결과 표 틀
```
| 항목 | 기대 | 관측 | 비고 |
|---|---|---|---|
| E1 브링업 | … | … | … |
… E12 까지. 알려진 차이(에뮬레이터 특성) 절과 "담당 밖 요청" 절을 뒤에 둔다.
```
"관측" 칸은 수용/진행/정지 여부와 로그 원문(짧게). 주기·지연·거리 수치는 쓰지 않는다. 위치값(mm·rad)은 기록해도 된다.

## 6. 시간·중단 조건
- 예상: S4(C0~C6) 20 분 · S5(normal) 15 분 · S6(cancel·lost) 20 분 · Q3 15 분 · S7 20 분.
- 중단: RAM 여유 < 300 MB → 멈추고 사용자에게 다른 세션 종료 요청 · 브링업이 30 s 안에 활성 안 됨 → bringup.log 를 붙여 보고 · goal 60 s 상한 → cancel 후 기록 · 같은 case 를 2번 돌려도 판정 불가면 그 case 는 "판정 불가 + 이유" 로 끝낸다.

## 7. 변경 기록
- 2026-10-10 초안(S2·S3 동시). 주관 세션 의견 반영: #139·#134 로컬 적용, launch 파일 추가 없음, Q3 15 분, rviz2 끄기.
- 2026-10-11 PR 전 최종 재검(Opus, 재현 3 case + DD 손 실행) 반영: D2 #134 머지·#139 a0db91e, D6·D10 goal 타이밍 사실대로, C0·C2·C4·C9·C10·C11·C14 재현성(대기 루프·CASE·재시도·untracked 파일).
- 2026-10-10 독립 재검(Opus 서브에이전트, 재현 3 case + 추가 3 실험) 반영: D6 늦은 goal → REACH_X_MAX, D2 #139 head 메모, C8·C11 setsid 제거·set -m, pgrep 실행 파일 경로.
- 2026-10-10 검증 워크플로(4 관점 + 반박 검증, 확정 12·참고 15) 반영: pkill `\|` 오류 → PID 파일 관리(D14), 자기 셸 제외 pgrep, goal 타이밍 = 첫 박스 수신 뒤 1~2 s(D6, U5 x 여유), lost 3.0 s(D10), C10/C11 순서 교체, 폴더 생성, 절대 경로, rad 단위(D15), J1 정수 표기, 기준 5 행, 규칙 3 예외 범위(HLD §4), 주관 세션 사실 2건(E3 WARN·gripper_width 100.0, rg2_host 무시).
