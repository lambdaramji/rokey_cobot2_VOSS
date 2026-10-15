# S2-T18 실기 절차서 (초안) — J6 회전 파지: 에뮬레이터 → 실측 → 실기 1단계(15·30·45°) → 5단계(60~90°)

- 작업 S2-T18 · 작성 2026-10-14 · **초안 — 1절 실행 조건이 모두 ✅ 가 되기 전에는 실행하지 않는다.**
- **2026-10-15 실기 완료 — 결과·최종 설정은 [S2T18-result.md](S2T18-result.md).** 2절 에뮬레이터는 일정상 생략하고 실기 저속 단계(R1~R3)로 대신 확인했다. 실기에서 4·5단계 뒤 6단계(flip 70·회전 중 LOST 1.2 s·max 110)를 더해 최종으로 했다.
- 덧붙임(10/15 저녁): 에뮬레이터 E0~E8 은 실기 전 단계로 쓰이지는 않았고, 같은 날 개인 PC 에서 따로 수행했다(2.5 — 보조 근거, 결론은 실기와 같음). 실기와 달라진 설계값은 9절.
- 대상 코드: 이 단위 PR(`feat/S2-T18-voss_servo-j6-rotate`)이 main 에 머지된 체크아웃. S2-T16(BoxTrack yaw, #51 945c67d)·D0 interface(#48 dd55e56)는 이미 main 에 있다. 기능 플래그 `rotate.enable` 기본 off — 끄면 시연 라인과 params_sha 까지 같다.
- 근거: [S2T18-hld.md](S2T18-hld.md)(D7 적용 단계·r3 주석) · [S2T18-dd.md](S2T18-dd.md)(12·13절) · [S2T18-pseudo.md](S2T18-pseudo.md)(r2) · [U9-run.md](U9-run.md)(공통 안전·기록 방식).
- **실기·공용 PC 명령은 모두 사람이(박병후) 비상정지 옆에서 실행한다.** Claude 는 실행하지 않는다(CLAUDE.md 규칙 6). 2절 에뮬레이터 단계만 개인 PC 에서 Claude 가 직접 돌린다.
- 이 문서는 계획이다. 값은 전부 **제안값**(T17 전)이고, 측정값은 measurements 에만 적는다.

## 0. 단계와 확인할 것

| 단계 | 어디서 | 누가 | 확인할 것 | 통과 기준(제안) |
|---|---|---|---|---|
| 2 | 개인 PC 두산 에뮬레이터 | Claude(래퍼), main(#164·#167 머지) | **명령·방향·기하·상태 전이**: 회전이 돈다·부호·회전 중심(등록 상태별)·gateway 가 살아 있는 정지 경로 각속도 0·되돌리기·gateway 한계 | 2절 표 전부(시간·물리 정지량은 기록만) |
| 3 | 공용 PC·실기 (로봇 정지·펜던트) | 학민·현지(담당 밖) | 측정 ① 돌린 그리퍼 간섭, 측정 ② 돌린 자세 위치·yaw 오차, yaw 관측 실험 | 결과로 max_deg·데드밴드 확정 |
| 4 | 실기 | 박병후(+동행 2) | 1단계: 0° 대조 3 + 15·30·45° 각 3 (min 10·max 45) | 4절 |
| 5 | 실기 | 박병후(+동행 2) | 60·75·90° 각 3, min_deg = 데드밴드, max 90 | 5절, pending #27 범위 확정 |

## 1. 실행 조건 (하나라도 ❌ 면 4·5단계를 시작하지 않는다)

| # | 조건 | 확인 방법 |
|---|---|---|
| ① | **T17(학민) 머지**: gateway 가 servo_cmd `angular.z` 를 **베이스 Z 각속도**로 speedl 에 넘김— **#164 머지(50da027, 10/15)** 로 해소. `servo_angular:=true` 일 때만(기본 끔) | gateway 기동 줄 `servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 100°`. 통계 줄 `자름` 에 **`angular`·`ang_speed`·`yaw_limit` 셋 다 0**(켬이면 `angular` 는 x·y 만 센다) |
| ② | gateway `servo_acc[1]` ≥ belt_servo `rotate.alpha_dps2`(제안 90). **10 이면 J6 를 켜지 않는다**(HLD D5·9절: 90° 가 x 문턱 초과, 관성 180°). S2-T17 #164 는 PL 리뷰 🟡2 로 **기본 10 유지, `servo_angular_enable` 일 때만 90** | 켬일 때 기동 줄 `servo angular on · … α 90 °/s²` — 이 줄의 α 는 **각속도에 실제로 쓰는 값**이어야 한다(J-gw 가 읽음). sim 은 `sim_check --profile rotate_gw` 의 J-gw 가 자동 비교 |
| ③ | gateway 각속도 상한(`servo_max_ang_dps`) ≥ `rotate.omega_max_dps`(제안 60) | 기동 줄 `servo angular on · ω ≤ 60 °/s`. sim 은 J-gw |
| ④ | **회전 중심**: speedl 에는 기준점 인자가 없고, 컨트롤러 **등록 TCP** 를 기준으로 돈다 — **10/15 에뮬레이터 E3′ 확인: 등록이면 TCP 이동 0.00003 mm, 미등록이면 플랜지 기준(16° 에 1.76 mm, 예측과 일치)**. 등록은 브링업마다 풀린다(`robot_gateway.py:256`). 플랜지 기준(미등록)이면 관측 자세에서 TCP 가 30° 에 3.2 mm·45° 에 4.7 mm 움직인다(반지름 6.20 mm) → 보정은 gateway 몫(계약 — belt_servo 는 보정하지 않는다) | 2절 E3′(미등록·등록 두 상태) + 4.1 "컨트롤러 TCP 등록" 줄 |
| ⑤ | **gateway 가 살아 있는** 0 경로(만료 watchdog·`/voss/robot/stop`·종료·yaw_limit 자름 재전송)에 각속도 0 — z/x 자름만이면 재전송에 직전 각속도가 그대로 실린다(의도). gateway 가 죽으면 0 을 보낼 주체가 없다(3절). 물리 정지량(감속 각·끊김 뒤 더 도는 각)은 에뮬레이터 근거가 아니다(ADR-0010 결과 6) | 2절 E4·E5(명령 판정) + ⑯ 실기 축소 확인(물리) |
| ⑥ | T16 머지(**#51 945c67d, 10/14 완료**) 이후 main 으로 **호스트·비전 컨테이너 동시 빌드**: BoxTrack 에 yaw 필드 | `ros2 interface show voss_msgs/msg/BoxTrack \| grep yaw` → 2줄. belt_servo 틱 `yaw_valid` 가 true/false |
| ⑦ | D0 interface PR #48 머지(**dd55e56, 10/14 완료** — topics.md 각속도 문구: PREPARE·TRACK·LIFT·VERIFY·안전 후퇴) | main 의 topics.md |
| ⑧ | gateway `pose_source:=joint_states` + belt_servo `input.pose_lag_ms: 0`(rotate 가 켜지면 교차 검사가 60 을 거부) | gateway 기동 줄 `pose_source joint_states 확인: … → 사용`, 회차마다 `→ service`·`거부` 없음 |
| ⑨ | 3단계 결과: 데드밴드·r_min·n_min(yaw 관측 실험), max_deg(측정 ②·간섭 ①) 를 measurements 에 기록하고 실기 yaml 에 반영 | measurements 문서 **→ 실기(#179)**: yaw 관측 실험 없이 sim 제안값(데드밴드 4·r_min 0.97·n_min 5) 채택, max 110·flip 70·회전 LOST 1.2(result 4절) |
| ⑩ | ❌ 이면 진행 금지 — **손목 카메라 USB 케이블 고정**(커넥터 고정·여유 루프) + **gateway `servo_yaw_limit_deg` < USB 가 빠진 J6 각**(T17 케이블 실측, 100° 는 임시값 — #164 코멘트 C). 10/14 측정 ② 에서 J6 회전 뒤 USB 커넥터가 **두 번 빠졌다**(학민 #54 리뷰). 고정 뒤 펜던트로 J6 를 관측 자세에서 ±45°(5단계면 ±90°) 천천히 돌려 당김·걸림 없음 | 고정 사진 + **회차마다** `ros2 topic hz /camera/color/image_raw` ≈ 30 Hz(끊기면 그 회차 무효) **→ 실기**: ±46·±91°·−110° 근처 카메라 끊김 ≤ 70 ms, 케이블 약 −123°(계산) 육안 이상 없음. gateway 한계 130 은 확인 범위 밖 — 9.2 |
| ⑪ | `/voss/robot/pose` 주기 ≤ 25 ms(≥ 40 Hz) — 회전 "정지" 판정은 pose 수신이 `rotate.pose_fresh_s`(0.05) 안일 때만 믿는다. 느리면 STOPPING 이 정지를 못 봐 TRACK 에 묶인다 → pose_fresh_s 를 측정 주기의 2배로 | 공용 PC 실측만 유효(에뮬레이터 주기는 근거 아님): `ros2 topic hz /voss/robot/pose` (joint_states 운용이면 약 50 Hz) **→ 실기**: 중앙 20 ms·최대 47~52 ms → `pose_fresh_s` 0.05 유지 |
| ⑫ | J6 **지령→pose 지연** ≤ 80 ms — belt_servo 는 이 지연을 보상하지 않는다. 시험 모형 기준 지나침이 80 ms 에서 ≈1.5°(tol), 100 ms 에서 ≈2.5°, 150 ms 에서 ≈5.5°(+ 일부 TIMEOUT) *(계산, test_rotate FakeRobot)*. 각가속 오경보는 지연과 무관하게 나지 않는다. **에뮬레이터는 기록만, 판정은 4단계 2번 첫 회(ω 30)**(2.0 원칙) | 방법(10/15 재검 B3 — 옛 "틱 차 − 22 ms" 는 +18~45 ms 편향·33 ms 계단이라 폐기): 첫 0 아닌 `wz_cmd_dps` 틱의 `t_pub_s` → `tool_yaw_deg` 가 처음 바뀐 틱의 `pose_stamp_s`(joint_states 측정 시각), **3회 이상 평균**, 분해능(pose 주기 10~20 ms)을 함께 적는다. **정지 지터**는 4단계 전 실기에서 로봇 정지 상태로 `/voss/robot/pose` 10 s 를 기록해 같은 차분(omega_meas)으로 계산 → 실기 yaml `rotate.still_dps`(실기 null, 켤 때 필수) ≥ 지터 최대의 2배. STOPPING 은 측정이 still_dps 아래로 2틱 이어져야 끝나므로 지터가 넘으면 STOPPING 이 x 끝·LOST 까지 이어진다 **→ 실기**: 지연 40~52 ms ✅(0.1° 반응 87~122 ms − 램프 47 ms), 정지 지터 0.10 °/s → `still_dps` 2 유지 |
| ⑬ | **매 goal 전 관측 자세(OBSERVE, 절대 자세)** — sort_manager 는 PLACE 뒤 OBSERVE 로 돌아오고(`sort_fsm.py:935`), 실패·취소는 PAUSED → resume 때 OBSERVE(`sort_fsm.py:838`). 손목이 돌아간 채 끝난 goal(RETURN_INCOMPLETE·회전 중 취소) 뒤 회복은 이것에 기댄다 — 기준 각은 노드 수명 동안 한 번만 정하므로, OBSERVE 없이 goal 을 이어 보내면 다음 goal 들이 START_ROTATED 로 회전 없이 돌아간 손목으로 잡는다 | 단독 액션 시험(E·4단계)은 goal 사이에 MoveToZone OBSERVE 를 직접 부른다. attempts `rot_cause` 에 START_ROTATED 가 없다 |
| ⑭ | **회전 대기 중 시야 — 보류(사용자 10/14), 4단계 첫 회에서 확인.** 학민 #54 리뷰 1: 10/14 측정 ② B45 — TCP X −119.7·Z 151, 박스 +45° 에서 검출 0(박스가 화면 아래 가장자리, 카메라 광축이 TCP 보다 약 75 mm 상류), 벨트 가장자리 박스는 J6 + 쪽 +30° 부터 hull 경계에 걸려 검출 0(A0_2). 측정 ② 는 측정 정확도에 의문이 있어(사용자) 설계는 바꾸지 않고, 실제로 LOST 가 나면 그때 설계한다(후보: 회전 중 xy 목표를 카메라가 박스를 보는 오프셋에 두기 / 회전 대기 중 LOST 를 FF 예측으로 버티기). fake_box 는 xy 시야를 흉내 내지 않아 sim 에서 안 보인다 | 4단계 2번(15°) 첫 회 틱 로그: ROTATING·SETTLING 동안 `visible` 끊김 길이 < `input.lost_timeout_s`(0.5 s), cause LOST 없음. LOST 면 4단계 중단 → 설계 단위 **→ 실기**: 문제가 실제로 났다(5단계 + 67° 이상 9/18 LOST, A형·B형 — result 3절) → **flip 70·회전 goal LOST 1.2 s** 로 해결(6단계 14/14). xy 오프셋 대책은 미적용 |
| ⑮ | 회전 기준 각 = gateway yaw 한계 중심 — belt_servo 기준은 노드 기동 뒤 첫 goal 의 공구 yaw(관측 자세 = −88.72°), gateway 는 `observe_pose` 공구 yaw ± `servo_yaw_limit_deg`(100°) 밖으로 가는 각속도를 자른다. 같은 값을 두 곳에 적지 않는다(`rotate.home_tool_yaw_deg` 는 null 유지, 관측 자세를 다시 가르치면 둘이 어긋남) | belt_servo 로그 `회전 기준 공구 yaw = X°` 와 gateway 기동 줄 `yaw Y ± 100°` 의 차 ≤ `rotate.start_tol_deg`(3°) |
| ⑯ | **물리 정지 실기 축소 확인(E8-R)** — 에뮬레이터는 스트림이 끊기면 0.1 s 에 스스로 멈춰(1215) 정지량을 보여 주지 못한다(ADR-0010 결과 6). 사람이 비상정지 옆에서: gateway `servo_yaw_limit_deg` 를 임시 20° 로(파라미터만), 관측 자세에서 `emu_rot limit` 과 같은 모양의 +10°/s 지속 → `yaw_limit` 자름·정지 상대각 ≤ 20° / 같은 조건에서 발행 끊기(watchdog) 1회 → 정지 각 기록. ⑩ 케이블 ±45° 범위 안이라 안전. F-04(5 mm/s) 와 같은 방식 | gateway 통계 `자름 {'yaw_limit': N}`·`watchdog 1`, 공구 yaw 기록, measurements **→ 실기 R3 로 수행**: 한계 20° 에서 +18.0°/−18.3° 정지(계산 17.4°), 발행 끊김 0.2~0.3 s 뒤 정지(10 °/s 에서 2.3~2.6° 더 돎) |

## 2. 단계 2 — 에뮬레이터 (개인 PC, Claude 실행, main 366eeb5 이후)
**S2-T17(#164)과 S2-T18(#167) 의 에뮬레이터 확인은 이 절 하나로 한 번만 한다**(10/15 합의 — S2-T18 쪽에서 실행). 결과표·로그는 문안을 주관에 먼저 보내고 사용자 승인 뒤 두 PR(머지됨)에 코멘트로 붙인다. 10/15 독립 재검(Opus, B1~B16) 반영판.

### 2.0 판정 원칙 (ADR-0010 결과 6)
- 에뮬레이터는 **명령 내용·방향·기하·상태 전이**만 판정한다: speedl_stream `vel[5]`, gateway 통계 줄(`자름`·`watchdog`·`stop`·`move_stop`), 기동 줄, belt_servo 틱 `rot_state`·`rot_cause`·`wz_cmd_dps`, 공구 yaw 부호, TCP xy 이동, 착지 z.
- **시간·물리 정지량은 기록만**: 지령→pose 지연(⑫), 정지 지터, pose 주기(⑪), 감속 각·끊김 뒤 더 도는 각(E4·E5·E8④). 에뮬레이터는 스트림이 끊기면 0.1 s 에 스스로 멈추고(1215), 이 PC 에서는 주기가 흔들린다. 물리 정지는 ⑯ 실기 축소 확인, 지연·지터는 4단계에서 판정한다.
- 근거 범위: 이 절은 **S2-T17 완료 기준 ① "에뮬레이터 확인 기록"** 의 근거다. ② 간섭 측정은 3단계 측정 ①(실기), ③ "watchdog·z 하한 clamp 기존 시험 통과" 는 `colcon test --packages-select voss_robot`(test_servo_guard — #164 CI 통과) + 아래 회차의 gateway 통계 `watchdog`·`z_min` 정상으로 본다.

### 2.1 기동 절차 (회차마다 같은 순서, 도메인 79)
```bash
export ROS_DOMAIN_ID=79 WS=~/cobot2/cobot2_voss-u14e D=~/cobot2/cobot2_voss_data/1015/emu/<회차>
ROS_DOMAIN_ID=79 ~/.local/bin/voss-dsr-virtual-up          # 백그라운드. 로그 "Configured and activated dsr_controller2" (기동 자세 = 관절 0, U-E E1)
# 관측 자세 — gateway 를 띄우기 전에만 두산 직접 호출(U-E HLD §4·C3, 플랜지 ≈ observe_pose ±1 mm 확인됨)
ROS_DOMAIN_ID=79 ~/.local/bin/voss-dsr-virtual-exec call /dsr01/dsr_controller2/motion/move_joint dsr_msgs2/srv/MoveJoint \
  "{pos: [-93.89, -13.54, 97.73, -0.01, 94.88, -185.08], vel: 30.0, acc: 30.0, time: 0.0, radius: 0.0, mode: 0, blend_type: 0, sync_type: 0}"
voss-ros --ws $WS ros2 launch voss_robot robot_gateway.launch.py dry_run:=false rg2_dry_run:=true dry_run_object_mm:=40.5 \
  servo_angular:=true pose_source:=joint_states config:=$WS/config/voss_config.yaml        # 백그라운드, $D/gateway.log
# 기다릴 줄: "robot_gateway started: real", "servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 100°",
#            "컨트롤러 TCP 등록 …"(기록), "이동 높이 미리 계산" 뒤(그 전 servo_cmd 는 busy 거부)
voss-ros --ws $WS ros2 bag record -o $D/bag /voss/robot/servo_cmd /voss/robot/pose /dsr01/joint_states \
  /dsr01/dsr_controller2/speedl_stream /voss/vision/box /dsr01/error                     # 백그라운드
# belt_servo 회차만 (E0·E1·E2·E4·E6·E7): rotate 켬 덮어쓰기 = {belt_servo: {ros__parameters: {rotate: {enable: true}, input: {pose_lag_ms: 0.0}}}}
voss-ros --ws $WS ros2 launch voss_servo belt_servo.launch.py params:=$WS/src/voss_servo/config/belt_servo_sim.yaml \
  config:=$WS/config/voss_config.yaml overrides:=$D/rotate_on.yaml log_dir:=$D            # E7 off 는 overrides 없이
voss-ros --ws $WS ros2 run voss_servo fake_box --ros-args -p scenario:=normal -p speed_cmps:=<voss_config belt.speed_cmps> \
  -p direction_base:="<belt.direction_base>" -p yaw_deg:=<Δ>
voss-ros --ws $WS ros2 action send_goal /voss/servo/track_and_grasp voss_msgs/action/TrackAndGrasp "{track_id: <첫 /voss/vision/box 의 track_id>}"
# 다음 시험 전: gateway 경유 관측 자세 — voss-ros ros2 service call /voss/robot/move_to_zone voss_msgs/srv/MoveToZone "{zone: OBSERVE, slot: 0, mode: ''}"
# 끝: belt_servo·fake_box → gateway 순서로 SIGINT, bag 중지, voss-dsr-virtual-down, pgrep 로 남은 노드 0
```
- 직접 발행 회차(E3′·E5·E8)는 belt_servo·fake_box 없이 `voss-ros --ws $WS ros2 run voss_servo emu_rot <모드> --dir ±1 --out $D`(관측 자세가 아니면 스스로 거부, |상대각| > 한계 + 5° 면 stop).
- 회차마다 기록: `/voss/robot/pose` Hz, `/dsr01/error`(1215 등), 시작 때 `free -m`. 과부하(gateway watchdog·1215 가 goal·지령 **도중**)면 그 회차는 버리고 다시(오염 규칙, U12).

### 2.2 시험

| # | 시험 | 방법 | 판정(에뮬레이터) | 기록만 | 대신하는 실기 항목 |
|---|---|---|---|---|---|
| E0 | 기동·정합 | 2.1 기동 + belt_servo 첫 goal(E1 회차) | gateway `servo angular on · ω ≤ 60 · α 90 · yaw -88.7 ± 100`, belt_servo `rotate on · … ω 60 · α 90`, ⑮ `회전 기준 공구 yaw` 와 gateway yaw 차 ≤ 3° | `컨트롤러 TCP 등록 …` 줄 | ①②③⑮ 확인 절차 연습 |
| E7 | off 회귀 | (a) gateway 끔·belt_servo 끔(시연 라인) (b) gateway 켬·belt_servo 끔 — 각 Δ0° goal 3회. 기준 = 머지 전 main 42ba57d 같은 절차 3회 | reason·attempts·phase 열 같음, `wz_cmd_dps` 전부 null, 착지 TCP z 기준 ±1 mm, (a) 기동 줄 `servo angular off`·`acc [100.0, 10.0]`, belt_servo `rotate off`·params_sha256 = 42ba57d 값 | 시간 열 | 시연 라인 회귀 |
| E1 | 회전 | belt_servo 켬, Δ +30°·−30°·+45° 각 1 goal(사이마다 OBSERVE) | `rot_state` ROTATING→SETTLING→DONE(→RETURNING→RETURNED), STALL·TIMEOUT 없음, **\|Δ공구 yaw − Δ\| ≤ 1.5°**(법칙이 tol 앞에서 멈춤 — 30° 면 약 28.6°), `wz_cmd_dps` ≠ 0 인 틱의 phase ⊂ {PREPARE, TRACK, LIFT, VERIFY}, gateway `자름` 에 `angular`·`ang_speed`·`yaw_limit` 0 | 첫 DESCEND `rot_err_deg`(지연 영향), `rot_time_s`, ⑫ 지연 | 4단계 각도별 회전 동작 |
| E2 | 부호 | E1 회차 | `wz_cmd_dps` > 0 → `tool_yaw_deg` 증가(베이스 Z +), −30° 회차는 반대 | J6 관절 방향(`/dsr01/joint_states`, HLD D10 은 −) | 실기 첫 회전 방향 |
| E3′ | 회전 중심 | `emu_rot pure --dir +1`(선속도 0, 30°/s 1.0 s ≈ 30°, 한계에서 멂). **(a) 미등록(기본, U-E E1)** **(b) 등록**(수동 모드에서 `config_create_tcp`·`set_current_tcp` = voss_config tcp_offset — U-E E10 방법, 가능하면) | 회전 전후 TCP xy 이동: < 1 mm → "등록 TCP 기준 회전", 3.2 ± 0.5 mm → "플랜지 기준" → gateway 보정 필요(④). 상태별로 결론을 적는다 | `컨트롤러 TCP 등록 …` 줄, 실제 회전각 | 회전 중 TCP 이동·보정 필요성(실기는 4.1 의 등록 상태와 같을 때만 유효) |
| E4 | 정지 경로(명령) | E1 회차에서 (a) ROTATING 중 goal cancel (b) ROTATING 중 belt_servo SIGINT (c) ROTATING 중 `/voss/robot/stop` — 각 뒤 같은 노드로 E1 한 번 더 | (a)(c) 다음 speedl `vel[5]` = 0·`move_stop` 호출·통계 `stop 1`, (b) 통계 `watchdog 1`·그 뒤 speedl 0, **이후 회전 재수신 정상**(새 goal 이 다시 돈다) | 관성 회전량(ADR-0010 결과 6) | ⑤ 명령 경로. 물리는 ⑯ |
| E5 | 감속 | `emu_rot brake --dir +1`(60°/s 0.9 s → 0 지령) / `--stop`(→ `/voss/robot/stop`) | 지령 0 뒤 speedl `vel[5]` = 0, `--stop` 은 move_stop 호출 | 정지까지 각(기대 ≈ 20° = 60²/(2·90), 1.2배 넘으면 gateway 각가속 가정을 학민과 재확인) | 실기 감속 거리 |
| E6 | 되돌리기 | E1 +30° 회차의 LIFT·VERIFY → MoveToZone PLACE(가짜 RG2) | RETURNING → RETURNED, 끝 `\|tool_yaw − 기준\|` ≤ 3°, PLACE 성공·`LIMIT` 없음 | 되돌리기 시간 | 학민 ⑤ 질문(정상) |
| E6b | 돌아간 손목 | Δ +30° goal 을 DONE 직후 cancel → GOAL_END `rot_cause` RETURN_INCOMPLETE(손목 ≈ +30°) → MoveToZone OBSERVE, 다시 같은 회차 → PLACE | 둘 다 성공·`LIMIT` 없음, 도착 공구 yaw = 관측 자세 ± 1°, 다음 goal `rot_cause` 에 START_ROTATED 없음 | 경로 이탈 최대(path_tol 15 mm 대비) | 학민 ⑤ 질문(돌아간 채 MoveToZone), ⑬ |
| E8 | gateway 한계 — **에뮬레이터 전용, 맨 끝**(손목이 한계 근처에 남는다, 하위 회차마다 OBSERVE) | `emu_rot` ① `over` ② `limit` ③ `crawl` ④ `cut`, ②~④ 는 `--dir +1`·`-1` 둘 다(− 방향은 −188.7° 로 ±180 을 넘으므로 상대각은 감아서) | ① speedl `vel[5]` ≤ 60, 통계 `ang_speed` ② 자름 상대각 ≈ 89°(= 100 − (30²/(2·90) + 30·0.2))·정지 < 100 ③ 60°/s 자름 ≈ 68°(= 100 − (20 + 12)) 뒤 감속 중 +1°/s 재지령 → 기어가도 < 100 ④ 40° 에서 발행 끊김 → 통계 `watchdog 1`·speedl 0. 합격 = 정지 상대각 \|·\| < 100° 이고 ≤ 계산 + 3° | ②③ 정지 각(기대 ≈ 94°·≈ 88°), ④ 끊김 뒤 더 돈 각(에뮬레이터 0.1 s 타임아웃이 먼저 — 근거 아님) | 실기에서 못 하는 한계 시험. 물리는 ⑯ |
| ⑫ | 지연·지터 | E1 회차 | — | 1절 ⑫ 방법으로 지연, 정지 상태 지터 | 4단계 2번 첫 회에서 판정 **→ 실기**: 지연 40~52 ms ✅(0.1° 반응 87~122 ms − 램프 47 ms), 정지 지터 0.10 °/s → `still_dps` 2 유지 |

### 2.3 순서
E0·E7(a)(b) → E1(+30·−30·+45, 같은 회차에서 E2·⑫ 기록) → E3′(a)(b) → E4(a)(b)(c) → E5 → E6·E6b → **E8 맨 끝**. 회차마다 OBSERVE 에서 시작, 과부하 회차는 버림. 결과는 `~/cobot2/cobot2_voss_data/1015/emu/`(레포 밖)와 결과표(measurements 또는 이 문서 끝 결과 절 — 사용자 신호 뒤 커밋).

### 2.4 이 절이 덮지 못하는 것
- 물리 정지량·지연·지터·pose 주기 → ⑯·⑫·⑪(실기).
- **gateway 가 죽으면(SIGKILL·크래시) J6 는 마지막 각속도로 계속 돈다**(ADR-0010:26) — 에뮬레이터는 0.1 s 타임아웃 때문에 재현조차 못 한다 → 3절 안전.
- 그리퍼-벨트 간섭·손목 카메라 케이블(T17 실측, ⑩), 돌린 자세 핸드아이 정확도·회전 대기 중 시야(⑭) — 실기.

### 2.5 결과 (10/15 11:57~14:27, 개인 PC, 도메인 79, main 366eeb5 + 이 브랜치 문서·emu_rot, 기준 42ba57d)
**판정 근거는 같은 날 실기(#179 [S2T18-result.md](S2T18-result.md))가 우선**이고 이 절은 보조다 — 결론은 실기와 같다(부호 +, 등록 TCP 기준 회전, 지연 40 ms 대). 에뮬레이터만의 차이(ACC_MISMATCH 폴백, 정지 지터 13.6 °/s, 45° OUT_OF_RANGE — 1단계 max 45 기준)는 실기에 없다. 실기 설정(max 110·flip 70)으로는 에뮬레이터를 다시 돌리지 않았다.
원본: `~/cobot2/cobot2_voss_data/1015/emu/`(레포 밖 — 회차별 gateway·belt_servo 로그, 틱·시도 로그, E4·E5·E8 bag, emu_rot CSV·JSON). 판정은 2.0 원칙(명령·방향·기하·상태 전이), 오염 회차(goal 중 watchdog·두산 알람·안전 정지·시작 pose 없음)는 버리고 다시 돌린 깨끗한 회차만 적는다.

| # | 결과 | 판정 |
|---|---|---|
| E0 | gateway `servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 100°`·`acc [100.0, 90.0]`, belt_servo `rotate on · deadband 4 · min 10 · max 45 · ω 60 · α 90 · home goal`, ⑮ `회전 기준 공구 yaw = -88.81°` ↔ gateway −88.7° 차 0.1° | ✅ |
| E7 | 기준 42ba57d OK 3/3 착지 +1.94·+2.06·+1.96 mm / (a) gateway 끔·회전 끔 OK 3/3 +2.02·+2.00·+2.10, `servo angular off`·`acc [100.0, 10.0]` / (b) gateway 켬·회전 끔 OK 3/3 +2.01·+2.03·+2.00. 세 조합 모두 phase 열 같음, `wz_cmd_dps` 전부 null, 자름 0, params_sha256 `234a71716551` 동일 | ✅ (기준 평균 ±0.11 mm) |
| E1 | +30°: 공구 yaw −88.81 → −59.15(변화 29.66°) → 되돌림 −88.32 / −30°: −88.81 → −118.78(−29.97°) → −89.30 / +44°: −88.81 → −45.88(42.93°) → −87.71. 셋 다 ROTATING→SETTLING→DONE→RETURNING→RETURNED, 각속도는 PREPARE·TRACK·LIFT 만, 자름 0. 첫 DESCEND `rot_err` 0.35·−0.04·1.07°(기록) | ✅ \|변화 − Δ\| 0.34·0.03·1.07° ≤ 1.5° |
| E1 참고 | (1) Δ45° 는 OUT_OF_RANGE(SKIP) — 벨트 방향 −0.74° 때문에 Δ 가 상한 45° 를 조금 넘음(설계대로, 그래서 44° 로). (2) 깨끗한 회차 중에도 회전의 약 절반에서 ACC_MISMATCH → TIMEOUT 폴백(e1m·e1m3_r2 등) — 과부하로 pose 가 띄엄띄엄 와 측정 각가속이 낮게 잡힌 에뮬레이터 시간 특성으로 판단(2.0 — 판정 제외). 폴백 경로(STOPPING→FALLBACK→RETURNING→RETURN_TIMEOUT)는 그대로 동작, goal 은 OK | 기록 |
| E2 | +지령 → 공구 yaw 증가, −30° → 감소 | ✅ (J6 관절 방향은 추종 중 x·y 이동에도 J6 가 변해 회전 구간만 분리하지 못함 — **미기록**) |
| E3′ | (a) **TCP 미등록**(에뮬레이터 기본): 제자리 16.2° 에 TCP xy 1.76 mm = 플랜지 기준 예측 2·6.20·sin(8.1°) 1.75 mm. 다른 회차도 32.9° → 3.51(예측 3.51), 89.0° → 8.69(8.69) mm. (b) **TCP 등록**(수동 모드 `config_create_tcp`·`set_current_tcp`, gateway `컨트롤러 TCP 등록 voss_config 와 같음 (차 0.0 mm)`): 16.1° 에 0.00003 mm | ✅ **등록 = TCP 기준 회전, 미등록 = 플랜지 기준** → ④·4.1: 실기는 펜던트 TCP 등록 상태에서만 켠다(미등록이면 30° 에 3.2 mm — gateway 보정 없음) |
| E4 | (a) 회전 중 취소: speedl `vel[5]` 26.6 → 취소 뒤 첫 명령(25 ms)부터 0, `rot_cause` RETURN_INCOMPLETE, 다음 goal 회전 재수신. (b) belt_servo SIGINT: 마지막 명령 0, watchdog → 0 + move_stop, 다음 goal 회전 재수신. (c) `/voss/robot/stop`: 뒤 명령 0, 다음 goal 회전 재수신 — 단 stop 이 회전 뒤에 들어감(명령줄 도구 기동 1~2 s), 회전 중 stop 은 E5(ii) 로 확인 | ✅ |
| E5 | (i) 60°/s → 0 지령: speedl 0. (ii) 60°/s 중 `/voss/robot/stop → OK`: 10 ms 부터 `vel[5]` 0, stop 이전 stamp 거부(`거부 {'stop': 1}`) | ✅ 명령. 정지까지 각 2.95°·7.79° 는 기록만(에뮬레이터, 실기 기대 ≈ 20°) |
| E6 | +30° RETURNED 뒤 MoveToZone PLACE(A 칸 0) `ok=True` | ✅ |
| E6b | DONE 뒤 취소 → RETURN_INCOMPLETE(손목 −58.89°) → **돌아간 손목으로 PLACE `ok=True`** → OBSERVE `ok=True` → 다음 goal 공구 yaw −88.72°(복원)·SKIP(SMALL)·START_ROTATED 없음 | ✅ |
| E8 | ① 90°/s 지령 → `자름 {'ang_speed': 15}` ② 30°/s 계속 → **+88.98° / −88.99°** 에서 멈춤(계산 자름 89.0°), `yaw_limit` 자름, − 방향 감은 상대각 정상 ③ 60°/s → 자름 뒤 1°/s → **+76.5° / −75.4°** < 100° ④ 40° 에서 발행 끊김 → watchdog 순간 `vel[5]` 60 → 0(± 양방향), move_stop | ✅ (④ 끊긴 뒤 더 돈 13.2° 는 기록만) |
| ⑫ | 지령 → 첫 yaw 변화 41 ms, 회전 뒤 측정 각속도 최대 13.6°/s(감속 꼬리 포함 — 정지 지터 아님) | 기록만(에뮬레이터) — 4단계에서 판정 **→ 실기**: 지연 40~52 ms ✅(0.1° 반응 87~122 ms − 램프 47 ms), 정지 지터 0.10 °/s → `still_dps` 2 유지 |

**관찰 3건**
1. **⑬·⑮ 근거**: 회전 중 취소 뒤 손목이 −67.6° 로 남은 채 새 belt_servo 노드가 첫 goal 을 받자 그 자세를 기준 각으로 잡고 30° 를 더 돌았다(e4a_r2). 실제 시스템은 매 goal 전 OBSERVE(⑬)라 막히고, ⑮ 점검(기준 각 − gateway 중심 = 21° > 3°)이 잡는다.
2. **에뮬레이터 실행 환경**: `voss-dsr-virtual-down` 뒤 `run_emulator`·`joint_state_publisher`·`gripper_virtual_node`·`static_transform_publisher` 가 남아 브링업마다 쌓였다 — 남은 joint_state_publisher 가 joint_states pose 를 오염시키고, DDS 참가자가 늘어 새 노드가 `failed to create domain` 으로 못 떴다. 회차마다 KILL·0 개 확인으로 해결(래퍼 개선은 사용자 판단 항목). 또 에뮬레이터(DRCF)가 CPU 약 4코어·문맥 전환 초당 약 170 만 회를 써 load 15~29 — 몇 분 지나면 두산 서비스가 응답하지 않아(gateway `응답 없음 3회 연속`) **회차마다 에뮬레이터를 새로 띄웠다**. 오염으로 버린 회차는 전체의 약 40 %.
3. E3′ 30°/s × 1.0 s 지령에 실제 16° 만 돌았다 — 에뮬레이터 speedl 시간 특성(판정 제외, 실기 4단계에서 회전 시간 확인).

## 3. 안전·동행 (4·5단계, 하나라도 ❌ 면 시작하지 않는다)

| 항목 | 기준 |
|---|---|
| 동행자 | 2명 이상. 비상정지 대기자는 실행자와 다른 사람(학민 또는 남현지), 손이 비상정지 위에 |
| 펜던트 | 속도 100 %(사다리꼴 쓰면 S2T14-run 기준), 영역 리밋·공간 제한 켜짐, `reach.x_max_mm` 550 |
| J6 범위 | 관측 자세 기준 ±45°(4단계) / ±90°(5단계) 밖으로 돌 일이 없음 — `rotate.max_deg` 로 보장 **→ 실기 최종: + 쪽 ≤ 70°, − 쪽 ≤ 110°(flip), gateway 한계 130(9.2)** |
| gateway 비정상 종료 | **gateway 가 죽으면(watchdog 없음) J6 가 마지막 각속도로 계속 돌 수 있다** — 선속도는 watchdog 없이 speedl 을 직접 보낸 10/06 실측에서 끊긴 뒤에도 계속 갔고(measurements-1006 #3, ADR-0010:26), 각속도는 같은 speedl 경로라 같다고 **추정**(⑯ 에서 확인). 선속도와 달리 펜던트 공간 제한이 제자리 J6 회전을 막지 못할 수 있다 *(추정)*. 4단계 ω 60 이면 관측 +45° 에서 100° 까지 약 0.9 s → 비상정지 대기자는 회전 구간 동안 손목을 본다. 근거 대조: gateway 가 **살아 있으면** 끊긴 뒤 watchdog 으로 약 0.25 s 에 선다(measurements-1010 #12 F-04, 48 mm/s → 10.3 mm), gateway 가 **죽으면** 실로봇은 1.0 s 동안 +5 mm 계속 갔다(measurements-1006 #3, ADR-0010:26) — 각속도도 같은 speedl 경로라 같은 동작으로 본다 *(추정 — ⑯ 에서 각속도로 확인)*. **펜던트 J6 관절 범위(또는 공구 방향) 제한을 관측 자세 J6 ± 케이블 안전각으로 거는 것은 팀(학민) 결정 항목** — 결정 전에는 4단계 첫 3회 ω 30 유지 |
| 처음 회전 | 4단계 첫 3회는 **`rotate.omega_max_dps: 30`**(제안값의 절반)으로 돌려 움직임을 눈으로 확인한 뒤 60 으로 |
| 벨트 | 시연 속도(h250). 증속 금지 |
| 즉시 정지(소프트웨어 "멈춰" 또는 비상정지) | PREPARE·TRACK·LIFT·VERIFY 밖에서 손목이 돈다 / 핑거·카메라가 벨트 프레임·박스에 닿을 것 같다 / ACC_MISMATCH 경고 / 회전 중 박스가 화면에서 사라져 LOST |
| "멈춰" | 소프트웨어 정지(SR-NF-09). 위험하면 비상정지가 먼저 |

## 4. 단계 4 — 실기 1단계 (min 10 · max 45)
**→ 실기(#179): 1단계 9/9(회전 8 + 0° 대조 1), ω 30·60.** 아래는 계획 원문.

### 4.1 고정 조건 (기록한 뒤 시작)
| 항목 | 값 · 확인 |
|---|---|
| 코드 | `git rev-parse --short HEAD` (1절 ①⑥⑦ 포함) |
| 실기 yaml | 시연 라인 값 + `rotate:` 블록 — `enable: true`, 3단계 확정값(데드밴드·r_min·n_min·max_deg), `pose_fresh_s`(⑪ 측정 주기의 2배, 기본 0.05), 나머지는 sim yaml 제안값. `input.pose_lag_ms: 0` |
| belt_servo 기동 로그 | `rotate on · deadband … · min 10 · max 45 · ω 30(→60) · α 90 · home goal` 한 줄, READY. `READY 거부: … input.pose_lag_ms …` 면 ⑧ 위반 |
| 첫 goal 로그 | `회전 기준 공구 yaw = -88.7x° (노드 기동 뒤 첫 goal)` — **첫 goal 은 반드시 관측 자세에서 시작**(sort_manager 가 OBSERVE 로 보낸 직후). 다른 값이면 belt_servo 재기동 |
| params_sha256 | 기록(rotate on 이라 시연 라인과 다르다 — 정상) |
| 컨트롤러 TCP 등록 | gateway 기동 줄 `컨트롤러 TCP 등록 …` 기록. E3′ 결론(등록 상태별 회전 중심)과 **같은 등록 상태**일 때만 E3′ 결과를 쓴다(등록은 브링업마다 풀린다) |

켜기·끄기 = 실기 yaml 의 `rotate.enable` 한 줄 + belt_servo 재기동(파라미터는 기동 때만 읽는다):
```bash
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=<레포>/data/servo
```

### 4.2 회차
| 순서 | 박스 각(벨트 기준) | 횟수 | ω_max | 기대 rot_state | 기대 결과 |
|---|---|---|---|---|---|
| 1 | 0° (대조) | 3 | 30 | SKIP · SMALL | 지금과 같은 OK |
| 2 | 30° | **1 → 로그 확인** → 2 | 30 | ROTATING→SETTLING→DONE→RETURNING→RETURNED | OK |
| 3 | 15° | 3 | 60 | 위와 같음 | OK |
| 4 | 30° | 3 | 60 | 위와 같음 | OK |
| 5 | 45° | 3 | 60 | 위와 같음 | OK, 보고 폭 ≤ 44.0(WIDTH_OUT 없음) |

**2번 첫 회 뒤 틱 로그 확인(5회를 한꺼번에 돌리지 않는다)**:
- 첫 DESCEND 틱 `|rot_err_deg|` ≤ 1.5(tol), `rot_delta_deg` ≈ 사진 각(± 데드밴드)
- `wz_cmd_dps` ≠ 0 인 틱의 phase 가 PREPARE·TRACK·LIFT·VERIFY 뿐
- ROTATING 동안 `tcp_pose_m` z ≥ 윗면 + 50 mm(시야 보험), `visible` 이 끊기지 않음 — 끊기면 ⑭(회전 대기 중 시야) 확인 항목으로 기록하고, LOST 면 중단
- `rot_err_deg` = 지금 따르는 목표(회전 중 목표 각, 되돌리기 중 기준 각) − `tool_yaw_deg`(pose 원값)다. `tool_yaw_est_deg` 만 **지령 각속도로 외삽한 값**이라 T17 전·STALL 구간처럼 로봇이 안 돌면 실제 자세와 어긋난다 — 실제 자세 판단은 `tool_yaw_deg`·`rot_err_deg` 로 한다
- 목표를 지나친 최대 각(ROTATING·SETTLING 동안 `rot_err_deg` 부호가 바뀐 뒤 최대값)이 tol(1.5°) 안인지. 넘으면 ⑫ 지연을 다시 잰다
- `rot_time_s` ≈ 1.2~1.6 s(ω 30 이면 더 김), GOAL_END `rot_cause` 가 비어 있거나 RETURN_INCOMPLETE 면 원인 기록
- 되돌리기: RETURNED 뒤 `|tool_yaw_deg − 기준|` ≤ `rotate.start_tol_deg`(3°) — 도착 판정은 외삽값 ≤ tol 1.5° 라 원값 로그는 1.5° 를 살짝 넘을 수 있다(10/14 학민 sim −1.53°). 다음 goal 의 START_ROTATED 기준이 start_tol 이므로 이 값으로 본다
- `rot_cause` 에 STOP_UNCONFIRMED(정지 확인 상한 1 s)가 있으면 ⑪ pose 주기를 다시 잰다
- gateway 통계 `자름` 에 `angular`·`ang_speed`·`yaw_limit` 없음, `servo_cmd 거부` 없음

### 4.3 회차마다 기록
| 회차 | 사진 각 | rot_delta | rot_state 끝 | rot_cause | rot_time_s | DESCEND rot_err | 결과 reason | 보고 폭 | 닫힘 s | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|

### 4.4 판정(제안)
- 0° 대조 3/3 OK(회귀).
- 15·30·45° 9회에서 **DESCEND LOST·WIDTH_OUT 0**, 닫힘 ≤ 2.5 s(10/12 J6 없음: 19~37° LOST 4/4, 26° 닫힘 3.08 s).
- 회전 관련 폴백(STALL·TIMEOUT·ACC_MISMATCH) 0. 하나라도 나면 원인 확인 전 5단계로 가지 않는다.

## 5. 단계 5 — 넓히기 (4단계 통과 뒤)
**→ 실기(#179): 5단계(max 90) − 12/12·+ 19/29 → 6단계(max 110·flip 70·회전 LOST 1.2 s, gateway 한계 130) 14/14 를 최종으로.** 아래는 계획 원문.
- yaml: `rotate.max_deg: 90`, `rotate.min_deg` = 데드밴드 값. 1절 ⑩ 을 ±90° 로 다시 확인.
- 회차: 60·75·90° 각 3 + 0° 대조 1. 90° 는 ±90° 접기 경계라 회전 방향이 + 쪽(fold 규칙) — 케이블 쪽 확인.
- 판정: WIDTH_OUT(46 mm 폭 파지(짧은 옆면)) 0 이면 pending #27 "허용 범위 = 모든 각도" 로 확정, 남으면 그 각 이상을 max_deg 로.

## 6. 되돌림
- `rotate.enable: false`(한 줄) → belt_servo 재기동 → 기동 줄 `rotate off`, **params_sha256 이 rotate 키를 넣기 전 값과 같은지** 확인(rotate.* 는 off 면 지문에서 빠진다).
- 이상이 있으면 그 자리에서 되돌리고 회차를 멈춘다. 재개는 원인을 measurements 에 적은 뒤.

## 7. 데이터
- 틱·시도 jsonl(회전 12키·시도 4키 포함), 회차별 위 사진(송장 변 + 벨트 변), gateway 로그(통계 줄), 가능하면 회전 구간 bag(`/camera/color/image_raw/compressed`·`/voss/robot/pose`·`/voss/vision/box`).
- 커밋하지 않는다(규칙 8). 측정값은 measurements, 결정은 DESIGN·ADR(회전 파지 DEC 후보).

## 8. 하지 않는 것
- gateway·box_tracker 수정, 벨트 증속, 재시도(max_attempts) 변경과 회전을 한 시리즈에 섞기, 시연 라인에서 rotate 켜기(리허설 결과로 따로 결정).

## 9. 실기 반영 (10/15, #179 [S2T18-result.md](S2T18-result.md)) — 설계값 → 실기값
실기와 다르면 **실기가 우선**이다. 설계값은 위 절에 그대로 두고 여기서 바꾼다.

### 9.1 바뀐 값
| 항목 | 설계(이 문서·HLD) | 실기 최종 | 근거 |
|---|---|---|---|
| 허용 범위 | 1단계 max 45 → 5단계 90, 범위 밖 = 회전 없이(a안) | **max 110 · flip 70**(+Δ > 70° → Δ − 180°, −110~−90°) — 모든 각도 처리 | 5단계 + 67° 이상 9/18 LOST → 6단계 14/14 |
| 회전 중 LOST | `input.lost_timeout_s` 0.5 | 회전 goal 의 PREPARE·TRACK 만 **1.2 s**(`rotate.lost_timeout_s`) | A형·B형 0.5~0.6 s 끊김 |
| 되돌리기 | LIFT·VERIFY 1회, 못 하면 RETURN_INCOMPLETE | 약 30° 넘으면 **RETURN_INCOMPLETE 정상**(남은 각 ≈ \|Δ\| − 39°, `rot_end_left_deg`) | 되돌림 창 ≈0.8 s |
| 회전 중심 | 등록 TCP 추정(④) | **등록 TCP 확인** — 회전 중 TCP xy ≤ 0.20 mm | R2 (에뮬레이터 E3′ 도 같음) |
| 부호 | 베이스 Z + = 공구 yaw +(E2) | 확인 | R1 |
| 지연·지터·pose 주기 | ⑫ ≤ 80 ms·⑪ ≤ 25 ms | 40~52 ms · 0.10 °/s · 중앙 20 ms | R1~R3 |
| gateway | `servo_yaw_limit_deg` 노드 기본 100 | launch 인자, **실기 130**, 등록 TCP 확인을 MoveToZone 중 건너뜀 | result 4·5절 |
| 실기 yaml | 예시 enable false·값 null | `belt_servo_real.yaml.example` = 최종값, enable true·pose_lag 0 | result 4절 |
| 에뮬레이터 E8-R(⑯) | 실기 축소 확인 계획 | 실기 R3 로 수행 | result 2절 |

### 9.2 gateway 한계 130 의 여유 — 두 계산 나란히 (결론: **학민 결정 대기 — 125 로 낮추기 또는 케이블 −135° 확인**)
공통: 기준 = 관측 자세 공구 yaw(−88.7°), − 쪽 목표 최대 110°, gateway 는 상대각 + 감속 각(v²/2α + v·watchdog 0.2 s, v = 같은 방향이면 max(새 지령, 직전 지령))이 한계에 닿으면 각속도를 0 으로 자른다. α 90 °/s², ω 60 °/s.
| | PR #179 검토 계산(result 4절) | 이 세션 계산 |
|---|---|---|
| 가정 | √ 감속 시작 = 남은 20°, 그때 60 °/s | belt_servo √ 법칙 v = min(60, √(2·0.8α·(남은 − 1.5))) → 60 °/s 는 남은 ≥ 26.5° 에서만, 남은 20° 면 51.6 °/s |
| 정상 회전 최대 판정값 | 90 + 20 + 12 + 예측 3.6 = **125.6°** → 여유 4.4°(기준 3° 어긋나면 1.4°) | 83.5 + 20 + 12 = 115.5°, 예측 3.6 더하면 **119.1°** → 여유 10.9°(3° 어긋나면 7.9°) |
| "126 아래면 큰 회전이 STALL" | 예 | 아니오 — 125 로 낮춰도 정상 경로 여유 5.9°(3° 어긋나면 2.9°) |
| 고장 경로(belt_servo 가 60 °/s 지점에서 죽어 watchdog 정지) | — | 83.5 + 60 × 0.2~0.3 + 20 = **115.5~121.5°**(3° 어긋나면 124.5°) |
| 확인된 범위 | 카메라 −109.4°(실측)·케이블 −123°(육안, 계산) | 같음 — 고장 경로 끝(121.5~124.5)이 케이블 확인 각(123)에 걸친다 |
- 차이의 원인은 "60 °/s 가 끝나는 남은 각"(20 대 26.5) 가정이다. 실제 지령 각속도는 틱 로그 `wz_cmd_dps` 로 확인할 수 있다(6단계 −109.4° 회차).
- gateway 프로세스 자체가 죽으면 한계도 없다(선속도는 watchdog 없이 끊겨도 계속 간 10/06 실측 — 각속도 미확인) → 펜던트 J6 범위 제한이 유일한 방어(팀 결정, 3절).

### 9.3 시연 라인 회전 켬 전환 — 리허설에서 확인할 것
1. gateway 기동 줄 3개 — `servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 130°`, `컨트롤러 TCP 등록 voss_config 와 같음`(없으면 회전 끔 — 미등록이면 플랜지 기준), `pose_source joint_states 확인 … → 사용` — 그리고 회차 중 `→ service` 0.
2. belt_servo `rotate on · … max 110 … flip >70 → − · lost(회전) 1.2 s`, params_sha 기록(시연 라인과 다름 — 정상).
3. 첫 goal 전 OBSERVE, `회전 기준 공구 yaw = −88.7x°` 와 gateway 중심 차 ≤ 3°(⑮).
4. **sort_manager 전체 흐름(OCR → goal) 회전 켬 N 회** — 아직 한 번도 안 함. 사이클 ≤ 30 s, goal 시작 x(시연 기준 −93~−52 mm), 회전 각 분포(+ / flip − / −), LOST·OUT_OF_REACH 0.
5. 매 goal 뒤 PLACE·OBSERVE 성공, 다음 goal START_ROTATED 0. RETURN_INCOMPLETE 는 goal reason·`rot_end_left_deg`(≈ \|Δ\| − 39°)와 같이 본다.
6. 회차마다 camera_info Hz(⑩), −100° 넘는 구간 끊김.
7. HOLD 칸 비움 — 남아 있으면 PLACE 하강 접촉 → 7060·RG2 잠김(result 6절).
8. 끄기 리허설 1회 — `rotate.enable: false` + gateway `servo_angular` 없음 → params_sha 시연 라인과 같음.
9. 비상정지 대기자가 회전 구간 동안 손목을 본다(gateway 가 죽으면 한계 없음, 9.2).
