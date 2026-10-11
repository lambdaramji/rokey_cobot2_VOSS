# U-E 두산 에뮬레이터 전구간 가상 실험 — High-level design

- 이슈 #36 (T27) · 지시서 `~/cobot2/voss_handoff/active/UE-36-emulator-full-chain.md` · 작성 2026-10-10
- 브랜치 `feat/36-voss_servo-emulator-trial` · 워크트리 `~/cobot2/cobot2_voss-emu` (main 280f786) · **ROS 도메인 85 고정**
- 뒤따르는 문서: [U-E-dd.md](U-E-dd.md)(확인 항목·명령 전문) · [U-E-run.md](U-E-run.md)(결과)
- 코드를 새로 쓰지 않는 단위라 네 단계 중 pseudo·code 는 없다. HLD → DD → 실행 → run.md.

## 0. 왜 하나

지금까지 belt_servo 의 끝-끝 확인(U3 sim_check, U5 스모크)은 전부 robot_gateway `dry_run`(가짜 로봇 `DryRunDoosan` + 가짜 RG2)이었다. dry_run 은 두산 쪽 코드(`doosan.RosDoosan`)를 한 줄도 실행하지 않는다. 이 단위는 gateway 를 **real 모드**(`dry_run:=false`)로 두산 **에뮬레이터**에 붙여, 실로봇에서만 돌던 경로가 실제 `dsr_controller2` 와 함께 돌아가는지 본다. 결과는 "수용·진행·정지 여부"만 남기고 수치(주기·지연·끊김 시간)는 쓰지 않는다 — 이 PC 는 ros2_control 100 Hz 오버런이 잦고, 에뮬레이터는 speedl 끊김 동작이 실로봇과 다르다(measurements-1006 #3, ADR-0010 조건 6).

### 처음 나오는 개념 (쉽게)
| 말 | 뜻 |
|---|---|
| **에뮬레이터** | 두산 컨트롤러 소프트웨어(DRCF)를 도커 컨테이너(`dsr01_emulator`, 이미지 `doosanrobot/dsr_emulator:3.0.1`)로 띄운 것. 모터만 없고 운동학·알람·서비스는 실제 컨트롤러 프로그램이 돈다. 버전 GF03020000 — 실로봇(GF02120100)과 다르다 |
| **DRFL** | ROS 드라이버(`dsr_controller2`)가 컨트롤러와 TCP 로 통신할 때 쓰는 두산 라이브러리. ROS 토픽·서비스는 모두 이 라이브러리 함수 한 번씩으로 바뀐다 (`speedl_stream` → `Drfl->speedl`) |
| **`mode:=virtual`** | 브링업이 실로봇 컨트롤러(유선망 IP) 대신 127.0.0.1:12345(컨테이너)에 붙는 것. 래퍼 `voss-dsr-virtual-up` 이 이 값을 고정하고 인자를 받지 않는다 |
| **`rg2_dry_run`** | 에뮬레이터에는 RG2 Modbus(Compute Box)가 없으므로 gateway 안에서 RG2 만 가짜(`DryRunRg2`)로 두는 파라미터(브링업의 `gripper_virtual_node` 는 ROS 서비스 `/onrobot/sendCommand` 를 흉내 내는 별개 노드라 쓰지 않는다). 학민 PR #139 (미머지, 이 워크트리에 로컬로만 얹음) |

## 1. 지금까지(dry_run)와 이번(real + 에뮬레이터)의 차이

| 구간 | dry_run 에서 | 이번에 |
|---|---|---|
| servo_cmd → 로봇 | `DryRunDoosan.speedl` 이 속도를 적분(가속 없음) | `RosDoosan.speedl` 이 `/dsr01/dsr_controller2/speedl_stream`(reliable depth 10)에 발행 → DRFL `speedl` → 에뮬레이터가 가속 한계·알람을 포함해 움직임 |
| `/voss/robot/pose` | 가짜 로봇 위치 | service: `aux_control/get_current_tool_flange_posx`(직렬 큐) / joint_states: `/dsr01/joint_states` → `motion/fkin` |
| watchdog·stop | `DryRunDoosan.move_stop_async` 즉시 OK | `motion/move_stop`(Quick stop, 큐 밖 별도 그룹) 실제 서비스 응답 |
| 기동 TCP 확인 (`_ctrl_tcp`, #121) | `dry_run_tcp_registered` 로 흉내 | `get_current_posx` 와 플랜지 비교 — 에뮬레이터 등록 상태 그대로 |
| 그리퍼 | 가짜 | 가짜 그대로 (`rg2_dry_run`, object 40.5) — 그리퍼는 이번 실험 대상이 아님 |
| 알람·연결 끊김 토픽 | 없음 | `/dsr01/error`·`/dsr01/robot_disconnection` 구독이 살아 있음 |

## 2. 구성도

```
 [운전자 명령: 스크래치 스크립트 / 터미널]            모두 ROS_DOMAIN_ID=85
   ├─ voss-dsr-virtual-up          ─▶ ① 브링업 (m0609_rg2_bringup mode:=virtual)
   │                                    ├─ run_emulator → 도커 dsr01_emulator (DRCF, 127.0.0.1:12345)
   │                                    ├─ ros2_control_node + dsr_controller2 (/dsr01/dsr_controller2/*)
   │                                    ├─ joint_state_broadcaster (/dsr01/joint_states 100 Hz)
   │                                    └─ rviz2 (RAM 절약을 위해 기동 뒤 끈다)
   ├─ voss-dsr-virtual-exec call   ─▶ ② motion/move_joint 로 관측 자세 (펜던트 조그 대용)
   ├─ ros2 launch voss_robot …     ─▶ ③ robot_gateway real  dry_run:=false rg2_dry_run:=true
   ├─ ros2 launch voss_servo …     ─▶ ④ belt_servo (belt_servo_sim.yaml 제안값)
   ├─ ros2 run voss_servo fake_box ─▶ ⑤ fake_box (voss_config 벨트 값)
   └─ emu_goal.py (스크래치)       ─▶ ⑥ TrackAndGrasp goal 1개 (+ 3 s 뒤 cancel)

 fake_box ─/voss/vision/box (30 Hz)─▶ belt_servo ─/voss/robot/servo_cmd (30 Hz)─▶ robot_gateway(real)
                                         ▲   │ /voss/robot/gripper ──▶ DryRunRg2 (가짜, object 40.5)
                                         │   │ /voss/robot/stop ─────▶ motion/move_stop ─┐
                       /voss/robot/pose  │   ▼                                            ▼
                                         └── RosDoosan ◀─ get_current_tool_flange_posx ─ dsr_controller2 ◀─ speedl_stream
                                                        ◀─ joint_states + fkin                 │ DRFL (TCP 127.0.0.1:12345)
                                                                                               ▼
                                                                                    dsr01_emulator (DRCF GF03020000)
```

## 3. 구성 요소와 책임

| 구성 요소 | 어디서 | 이번 역할 | 바꾸는가 |
|---|---|---|---|
| 에뮬레이터 + 브링업 | `voss-dsr-virtual-up/down`(ws_dsr) | 실제 `dsr_controller2` 서비스·토픽 제공 | 아니오 (래퍼·ws_dsr 수정 금지) |
| robot_gateway (real) | `src/voss_robot` main + **PR #139 로컬 적용(미커밋)**(#134 는 10/11 main 92baa72 에 머지됨; 10/10 실험 때는 둘 다 로컬 적용) | speedl·pose·stop·watchdog·TCP 확인·가짜 RG2 | 아니오 (PR 전에 되돌림) |
| belt_servo | `src/voss_servo` main 280f786 | 추종·파지 FSM, 그리퍼 호출, 마지막 0 | 아니오 |
| fake_box | `voss_servo/fake_box.py` | `/voss/vision/box` 시나리오(normal·lost_after_s) | 아니오 |
| sim_check | `voss_servo/sim_check.py` | **실행하지 않음**(gateway dry_run 문구 판정·sim.launch 고정). 순수 판정 함수만 스크래치에서 import | 아니오 (필요 옵션은 회신에 U3 후속으로) |
| 스크래치 스크립트 | 세션 스크래치 폴더 (레포 밖) | goal 클라이언트(`emu_goal.py`), 판정(`emu_judge.py`), 순서 묶음 | 커밋 안 함 |
| 설계·결과 문서 | `src/voss_servo/design/U-E-{hld,dd,run}.md` | 이 단위의 산출물 | **이것만 PR** |

## 4. 데이터 흐름·인터페이스 (계약은 topics.md·voss_msgs.md 그대로)

| 경로 | 보내는 쪽 → 받는 쪽 | 비고 |
|---|---|---|
| `/voss/vision/box` BoxTrack | fake_box → belt_servo | best_effort·depth 1(발행)/5(구독). position_base = 박스 윗면 중심(m) |
| `/voss/robot/servo_cmd` TwistStamped | belt_servo → gateway | best_effort·depth 1, 30 Hz, stamp = 발행 시각(같은 PC 시계). gateway 는 now − stamp > 0.2 s 면 `old` 거부 |
| `/dsr01/dsr_controller2/speedl_stream` SpeedlStream | gateway → dsr_controller2 | **reliable depth 10**(ADR-0010 조건 1). vel mm/s, acc [100, 10], time 0 |
| `/voss/robot/pose` PoseStamped | gateway → belt_servo | best_effort·depth 1. TCP = 플랜지 + voss_config `tcp_offset_mm`(컨트롤러 등록과 무관) |
| `aux_control/get_current_tool_flange_posx` | gateway(큐) → dsr_controller2 | pose_source=service. 응답 수신 시각이 stamp |
| `/dsr01/joint_states` + `motion/fkin` | dsr_controller2 → gateway(큐) | pose_source=joint_states. 기동 교차 검사(서비스 플랜지와 비교) 통과 뒤 사용 |
| `/voss/robot/stop` Trigger | belt_servo(취소) → gateway → `motion/move_stop` | stop 이전 stamp 의 servo_cmd 폐기 + 0 속도 + move_stop |
| `/voss/robot/gripper` Gripper | belt_servo → gateway `DryRunRg2` | PREPARE 90 → GRASP 39 → VERIFY 39. object 40.5 면 grip_detected, #134 로 재닫기도 유지 |
| `/voss/robot/state` RobotState | gateway → (이번엔 echo 로만) | TCP 등록 상태가 detail 에 남는다 |
| `/dsr01/error`, `/dsr01/robot_disconnection` | dsr_controller2 → gateway | 알람(1215·1216)은 gateway 로그에 "두산 안내/알람" 으로 찍힌다 |
| `motion/move_joint` | 운전자(exec 래퍼) → dsr_controller2 | 관측 자세 세팅(펜던트 조그 대용). U7 절차서·지시서 §대안과 같은 **측정 전용 일회성 예외(규칙 3 예외)** — gateway 가 **떠 있지 않을 때만** 부르고, gateway 가 떠 있는 동안은 두산 서비스를 큐 밖에서 부르지 않는다 |
| `system/get_robot_system·get_robot_mode·get_robot_state`, `aux_control/get_current_posj·get_current_tool_flange_posx` | 운전자(exec 래퍼) → dsr_controller2 | 읽기 전용 상태·자세 확인(C2·C3). 같은 예외, gateway 미기동 상태에서만 |
| `tcp/config_create_tcp·set_current_tcp·get_current_tcp`, `aux_control/get_current_posx` | 운전자(exec 래퍼) → dsr_controller2 | Q3 TCP 등록 시험(C12). **컨트롤러 설정을 바꾸는 호출** — 컨테이너 rm(C13)으로 사라지며 실로봇 전제가 아니다. 같은 예외, gateway 미기동 상태에서만 |

## 5. 기동 순서·끄는 순서 (왜 그 순서인가)

기동: ① 도메인 85 가 비었는지 확인 → ② `voss-dsr-virtual-up`(컨테이너+브링업, 약 10 s, rviz2 끄기) → ③ `move_joint` 관측 자세 → ④ gateway real → pose 확인 → ⑤ belt_servo(READY) → ⑥ fake_box → ⑦ goal(emu_goal.py 가 첫 `/voss/vision/box` 를 받는 즉시 보냄 = fake_box 기동 뒤 약 2 s, DD D6).
- ③ 이 ④ 보다 앞: gateway 가 뜬 뒤에는 두산 서비스를 밖에서 부르지 않는다(단일 큐 규칙). 에뮬레이터 초기 자세(관절 0)는 팔이 곧게 선 특이점이라 speedl 이 돌지 않을 수 있어 관측 자세로 옮겨 놓는다.
- ⑥ 이 마지막: fake_box 는 뜨는 순간부터 박스를 움직인다. goal 이 늦으면 정렬 전에 P 포화 상태로 x_max 까지 쫓아가 OUT_OF_REACH/REACH_X_MAX 로 끝난다(재검 late 실험; U5 의 x 여유 검사 REACH_GRASP_ROOM 은 정렬된 뒤에만 본다). dry_run 에서는 P 포화 문제도 있었다(U3-run B.5).

case 사이: belt_servo·fake_box 를 끄고(result 뒤 0 유지 → watchdog → move_stop 까지 로그로 본 뒤) → gateway 를 끄고 → `move_joint` 로 관측 자세 복귀 → gateway 다시 → belt_servo·fake_box 다시. gateway 를 끄는 이유는 `move_joint` 를 gateway 밖에서 부르지 않기 위해서다.

끄기: belt_servo(Ctrl-C, #130 이 마지막 0 발행) → fake_box → gateway(Ctrl-C, 움직이는 중이면 `halt_on_exit` 가 0 속도+move_stop) → `voss-dsr-virtual-down`(브링업 SIGINT + 컨테이너 rm) → DD C13 의 pgrep(실행 파일 경로 패턴)이 비었는지 → `docker ps` 비었는지. belt_servo 를 gateway 보다 먼저 끄는 것은 G0 runbook 과 같다(끊기면 gateway watchdog 이 정지).

## 6. 보는 것 / 안 보는 것

보는 것(지시서 완료 기준): 명령 수용(speedl 발행 수·거부 수) · phase 진행 PREPARE→…→VERIFY · result · 마지막 cmd 0 · 0 유지 · watchdog → move_stop 횟수 · stop 응답 · TCP 확인 로그 · pose 두 소스 · 로봇이 실제로 멈췄는지(정지 뒤 위치 두 번 읽어 같음).

안 보는 것(기록하지 않음): 주기(Δt)·pose Hz·RTT·명령→움직임 지연·정지까지 시간·끊김 뒤 이동 거리 · 추종 오차 수치 · **끊김 실험 자체**(ADR-0010 조건 6). sim_check 의 J6(주기)·J7(watchdog 지연 창)·J11(추종)·J12(트랙 고정) 판정은 쓰지 않는다. watchdog 은 로그 줄 수만 센다. J5(0 유지)처럼 결과 문자열에 틱 수·초가 섞여 나오는 판정은 "통과/실패" 만 옮긴다.

## 7. 에뮬레이터 특성 (미리 아는 것 — 결과 해석에 쓰고 안전 근거로는 쓰지 않는다)

| 특성 | 출처 | 이번 실험에 미치는 영향 |
|---|---|---|
| speedl 이 0.1 s 안 오면 알람 1215 로 멈춘다 (실로봇은 계속 간다) | measurements-1006 #3 | 틱이 밀리면 중간에 서고 다음 명령에 다시 간다. "진행 여부"만 기록 |
| 알람 1216 `time` 자동 조정 (실로봇과 같음) | 같은 곳 | gateway 가 INFO "두산 안내" 로 찍음 — 정상 |
| ros2_control 100 Hz 오버런이 잦다 | 메모리 dsr-emulator-wrappers | pose 가 0.1 s 넘게 묵으면 gateway 가 `no_pose` 로 명령을 거부하고, belt_servo 는 0.3 s 면 STALE_INPUT — 생기면 그대로 기록 |
| TCP 등록이 없을 가능성이 크다 (컨테이너 새로 뜸) | #121, 10/08 사고 | `_ctrl_tcp` → "없음 → 플랜지 좌표로 명령". pose 는 config 오프셋으로 계산하므로 추종에는 영향 없음. Q3 에서 ROS `set_current_tcp` 가 되는지 본다(실로봇 자동 모드는 success=False) |
| RG2 Modbus·벨트·작업대가 없다(브링업의 `gripper_virtual_node` 는 ROS 서비스 흉내, 미사용) | — | 충돌 없음. z 하한은 gateway `servo_z_min_mm` 78 이 지킨다 |
| 전원 기동 자세 = 관절 0 으로 추정 (**확인 필요** — C2 에서 get_current_posj 로 기록) | measurements #3 주의점 9(에뮬레이터 홈 ry = 0)에서 간접 추정 | 특이점일 수 있으므로 `move_joint` 로 관측 관절값(measurements #6)으로 옮긴 뒤 시작 |
| 로봇 시스템 값 = VIRTUAL(1) | `system/get_robot_system` | 측정 스크립트(servo_stream_inspect)의 실로봇 가드 근거. run.md 에 기록 |

## 8. 리스크·대응

| 리스크 | 대응 |
|---|---|
| RAM 부족(여유 ≈1.3 GB, 스왑 사용 중) | 브링업 뒤 rviz2 프로세스만 끈다. case 마다 `free -m` 확인, 여유 300 MB 미만이면 멈추고 사용자에게 다른 세션 종료를 요청 |
| 알람 1215 로 멈춰 PREPARE 가 끝나지 않음 | 에뮬레이터 특성으로 기록. goal 상한 60 s 뒤 cancel 로 끝낸다 |
| 도메인이 겹쳐 남의 노드에 goal 이 감 | 시작 전 `ros2 node list --no-daemon` 비었는지 확인. 85 만 쓴다 |
| gateway 가 뜬 상태에서 두산 서비스를 밖에서 부름 | `move_joint` 는 gateway 를 끈 뒤에만 |
| voss_robot 로컬 변경이 PR 에 섞임 | PR 전 `git checkout -- src/voss_robot`, `git status` 로 확인. run.md 에 적용 PR·sha 명시 |
| 실로봇 환경 오인 | 모든 래퍼가 도메인 30 을 거부하고, voss-ros 는 192.168.1.x 연결·`mode:=real` 인자도 거부하며, voss-dsr-virtual-up 은 인자를 받지 않아 mode:=virtual·127.0.0.1 로 고정된다. 이 PC 에는 로봇이 없다 |

## 9. 수정 범위
- 허용: `src/voss_servo/design/U-E-*.md`, (대안 불필요 — pymodbus 가짜 RG2 서버·`scripts/README.md` 줄은 만들지 않는다).
- 금지: `src/voss_servo` 코드, `src/voss_robot`(로컬 적용은 실험용, 커밋 안 함), `src/voss_msgs`, `docs/interfaces`, `config/`, 래퍼·ws_dsr.

## 10. 산출물·완료 기준 매핑
| 완료 기준 | 어디서 확인 | DD 항목 |
|---|---|---|
| 1 에뮬레이터+gateway real, pose service·joint_states 각 1회, TCP 로그 | gateway.log, `topic echo` | E1~E6 |
| 2 normal goal 1회 phase 진행·OK 또는 막힌 단계 | result.json, attempts, gateway.log | E7 |
| 3 cancel 1회 | result.json, gateway.log, 정지 확인 | E8 |
| 4 lost 1회 | result.json, ticks, gateway.log | E9 |
| 5 끊김 실험 없음 | 절차에 없음 | — |
| 6 build/test/ruff, 잔여 프로세스 0, 컨테이너 down | RULES §4, pgrep, docker ps | E11·E12 |
| Q3 (지시서 밖, 주관 세션 승인 10/10, 15 분 한도) TCP 등록 시험 | C12 로그 | E10 |
