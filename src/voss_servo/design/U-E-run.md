# U-E 실행 절차·결과 — 두산 에뮬레이터 전구간 가상 실험 (개인 PC)

- 이슈 #36 · 설계 [U-E-hld.md](U-E-hld.md)·[U-E-dd.md](U-E-dd.md) · 실행 2026-10-10 13:36~15:20 · 도메인 85 · 워크트리 `~/cobot2/cobot2_voss-emu`(main 280f786)
- **실험에 쓴 voss_robot 변경(미커밋, 이 PR 에 없음)**: 10/10 = main 280f786 + PR #139 a25d0c2(rg2_dry_run·launch 인자) + PR #134 99422b3(가짜 RG2 `<=`). 10/11 최종 재검 = main 92baa72(#134 머지됨) + #139 head a0db91e(started 줄 등에 `RG2 FAKE`, 에뮬레이터 노드 검사, 테스트 추가) — 같은 판정. PR 브랜치는 10/11 origin/main 으로 리베이스했다(voss_servo 변경 없음).
- 이 문서의 명령과 출력은 실제로 돌려 본 것이다. **수치(주기·지연·끊김 시간·이동 거리)는 적지 않는다**(지시서, ADR-0010 조건 6). 위치값·횟수·통과 여부만 남긴다.
- 에뮬레이터 결과는 measurements 가 아니라 이 문서와 회신에만 둔다.
- **우선순위**: 이 문서는 가상 실험 기록이다. 10/10 실기(G0·G1 20/20, PR #145 `docs/measurements-1010.md`)가 belt_servo 판단의 기준이며, 둘이 어긋나면 실기 기록이 우선한다. 실기와 겹치는 관측(특이점 안내 3205 가 x≈600 부근에서 남 — measurements-1010 #14, watchdog → move_stop 로그 순서, joint_states 교차 검사 `0.00 mm → 사용`)은 서로 모순되지 않았다.

## 1. 결과 표 (DD §2 E1~E12)

| 항목 | 기대 | 관측 | 비고 |
|---|---|---|---|
| E1 브링업 | dsr_controller2 활성, VIRTUAL·STANDBY, joint_states·speedl_stream 존재 | `Configured and activated dsr_controller2`, `robot_system=1`(VIRTUAL) `robot_mode=1`(AUTONOMOUS) `robot_state=1`(STANDBY), 토픽 둘 다 있음, 기동 자세 `posj [0,0,0,0,0,0]`(관절 0 확인), `/dsr01/joint_states` 발행자 2(joint_state_broadcaster·joint_state_publisher) | 1회차 브링업은 5 분 뒤 DRFL 끊김(§4 ①) → 재기동 |
| E2 관측 자세 | move_joint 성공, 플랜지 ≈ measurements #6 ±5 mm | `success=True`, 플랜지 `[-12.23, -271.64, 450.85, 85.50, -179.07, -5.69]` (#6 `[-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]` 와 1 mm 안) | 에뮬레이터 운동학 = 실로봇 |
| E3 gateway real | started real 줄 + RG2 가짜 WARN, sha256, RobotState | `robot_gateway started: real /dsr01/dsr_controller2/, …`, `RG2 가짜(rg2_dry_run) — 실제 그리퍼는 움직이지 않는다. 실기에서는 끈다`, `voss_config version=1 sha256=db97243ec6ef`(belt_servo 와 같음), RobotState `READY connected=True gripper_width_mm 100.0` | `두산 서비스가 안 보인다` 없음 |
| E4 TCP 확인(#121) | `컨트롤러 TCP 등록 …` 1줄 | 미등록 상태: `컨트롤러 TCP 등록 없음 → 플랜지 좌표로 명령 (차 0.0 mm)`, RobotState.detail `controller STANDBY, TCP 등록 없음(플랜지 모드 — 펜던트 공간 제한이 핑거 끝을 못 막음)` | 등록 뒤는 E10 |
| E5 pose(service) | base_link, 관측 TCP ±0.005 m, fail 0 | `frame_id base_link`, position (−0.0152, −0.2771, 0.2043) m (기대 (−0.0145, −0.2765, 0.2036)), 통계 `fail 0` | 종료 중 `pose 조회 실패: TIMEOUT 0.50s` 1줄(정상 종료 과정) |
| E6 pose(joint_states) | 교차 검사 통과, E5 와 같은 위치 | `pose_source joint_states 확인: 서비스 플랜지와 0.00 mm → 사용 (guard pose 지연 20 ms)`, position 동일 | 기동 첫 틱 `pose 조회 실패: joint_states 없음·0.1 s 넘게 오래됨` 1회, 첫 5 s 통계 `fail 1` 뒤 `fail 0` |
| E7 normal | 4/OK/grasped=True, phases 6, 마지막 0, 0 유지, watchdog 1, move_stop 1, stop 0, gripper 3줄 | **전부 ✅**: `4/OK/grasped=True` attempts 1, cause `''`, `[PREPARE, TRACK, DESCEND, GRASP, LIFT, VERIFY]`, 마지막 cmd 0, 0 유지 통과, watchdog 1, `move_stop ok 1 fail 0`, stop 0. 통계 합계 speedl 302·거부 0·자름 0. gripper `90.0 → OK 폭 90.0 grip False` / `39.0 → OK 폭 40.5 grip True` / `39.0 → OK 폭 40.5 grip True`(VERIFY 재닫기 유지 = #134). GOAL_END phase VERIFY verdict HELD | 두산 알람 0, 안내 1(§4 ③). 3회차에 성립(1·2회차는 §4 ④·⑤ 의 스크립트·래퍼 문제) |
| E8 cancel | 5/CANCELED, STOP_OK, stop → OK, move_stop 2, 정지 | **전부 ✅**: `5/CANCELED/grasped=False`, cause `STOP_OK`, `[PREPARE, TRACK]`(재검 재현에서는 `[PREPARE, TRACK, DESCEND]` — 3 s 취소가 TRACK→DESCEND 경계에 걸려 실행마다 다르다. 하강 중 취소도 OK), 마지막 0, 0 유지 통과, watchdog 1, `move_stop ok 2 fail 0`, `stop 1 · OK`, `/voss/robot/stop → OK` 1줄. 정지: joint_states 1 s 간격 2회 관절 6개 차 0.00 rad. 통계 `거부 {'stop': 1}`(stop 이전 stamp 의 servo_cmd 1건 폐기 — F-04 의도; 재현에서는 0 — 타이밍에 따라 0 또는 1) | 알람 0, 안내 1 |
| E9 lost | 6/LOST, BOX_MISSING, watchdog→move_stop | **전부 ✅**: `6/LOST/grasped=False`, cause `BOX_MISSING`, `[PREPARE, TRACK]`, 마지막 0, 0 유지 통과, watchdog 1, `move_stop ok 1`, stop 0, 거부 0 | fake_box `lost_after_s:=3.0`(D10). 10/11 재현에서는 알람 1215 가 1회(§3) |
| — 기준 5 | 끊김 실험 없음 | 하지 않았다 | ADR-0010 조건 6 |
| E10 TCP 등록 시험(Q3) | success 값·info·재기동 gateway 줄 | AUTONOMOUS(mode 1): `config_create_tcp`·`set_current_tcp` **둘 다 success=False**(실로봇 #121 과 같음). `set_robot_mode 0`(MANUAL) 뒤: 둘 다 **True**, `get_current_tcp info='GripperDA_v1'`, `get_current_posx` 가 플랜지+오프셋(z 144.9 = 플랜지 391.5 − 246.6)로 바뀜. AUTONOMOUS 복귀 뒤에도 등록 유지. gateway 재기동: service·joint_states 모두 `컨트롤러 TCP 등록 voss_config 와 같음 (차 0.0 mm)`, joint_states 교차 검사 `0.00 mm → 사용`, pose 두 소스 동일 | 등록은 컨테이너 rm 으로 사라진다. 실로봇은 펜던트에서 등록(자동 모드 ROS 호출 불가) |
| E11 정리 | 종료 로그 정상, pgrep 0, 컨테이너 없음 | 세 case 모두 `process has finished cleanly`·Traceback 0. `voss-dsr-virtual-down` 뒤 브링업 자식(ros2_control_node·joint_state_publisher·robot_state_publisher·run_emulator·static_transform_publisher ×2)이 남아 TERM 으로 정리(§4 ①). 최종: 잔여 프로세스 0, `dsr01_emulator` 없음, 도메인 85 `node list` 비어 있음 | 정리 중 pgrep 패턴 `[s]pawner` 가 GNOME 데몬(gvfsd-trash·recent·network·dnssd)의 `--spawner` 인자에 걸려 TERM 을 보낸 실수가 있었다(§4 ⑧) |
| E12 검증 | build·test·ruff, design 문서만 | `git checkout -- src/voss_robot` 뒤 `git status` 에 `design/U-E-{hld,dd,run}.md` 만. colcon build 3 packages finished · colcon test voss_servo **230 tests, 0 errors, 0 failures** · ruff check All checks passed, format 43 files already formatted | voss_robot 변경은 커밋되지 않았다 |

판정 도구: 스크래치 `emu_judge.py`(sim_check 순수 함수 재사용, DD D8). 표의 "전부 ✅" 는 J1·J2·J3·J4·J5·watchdog 줄 수·J8·J9 의 8개 판정. 두산 알람·안내 줄 수는 case 로그 파일 전체 기준(파일 = 그 case 의 gateway 수명).

**해석의 한계(ADR-0010 조건 6)**: watchdog·move_stop 은 "호출됐고 응답이 OK 였다" 까지만 확인한 것이다. 에뮬레이터는 speedl 이 0.1 s 끊기면 스스로 서므로(알람 1215) 로봇이 선 **원인**이 move_stop 인지 1215 인지는 가릴 수 없다. cancel 의 관절 차 0 도 "에뮬레이터가 섰다" 는 동작 확인이지 안전 근거가 아니다. 또 C10 은 watchdog move_stop 까지 끝난 뒤에 읽으므로 "stop 만으로 섰다" 는 구분하지 못하고, `/dsr01/joint_states` 발행자가 2개(broadcaster·joint_state_publisher)라 `echo --once` 가 어느 쪽을 받는지는 정해져 있지 않다(값은 관측 자세와 달라 갱신되는 토픽임은 확인).

### 1.1 독립 재검 재현 (Opus 서브에이전트, 15:3x, TCP 등록 상태, OUT=/tmp/voss_emu_review)
| case | 재검 판정 | 원 판정 | 비고 |
|---|---|---|---|
| normal | ✅ 8/8 | ✅ | TCP 등록 상태에서도 같은 결과(gateway `voss_config 와 같음`) |
| cancel | ✅ 8/8 | ✅ | phases `[PREPARE, TRACK, DESCEND]` |
| lost | ✅ 8/8 | ✅ | LOST 는 fake_box 기동 뒤 D10 예상대로 |
| 추가 normal + `pose_source:=joint_states` | ✅ | — | 교차 검사 통과 뒤 goal OK. belt_servo 는 sim yaml 의 `pose_lag_ms` 60(service 기준값) 그대로 — 실기 runbook(#135·#141)은 joint_states 일 때 belt_servo 0·box_tracker 15 를 쓴다. 이 실험은 추종 오차를 보지 않으므로 영향 없음 |
| 추가 empty(`dry_run_object_mm:=0`) | ✅ sim_check `grasp/empty` 기대와 일치 | — | `6/GRASP_FAILED/NOT_DETECTED`, GRASP 에서 끝, 마지막 0, watchdog 1, move_stop ok 1 |
| 추가 late(goal 을 fake_box 기동 뒤 ≈7 s 에) | ⚠ | — | `6/OUT_OF_REACH` 이지만 cause **REACH_X_MAX**(REACH_GRASP_ROOM 아님): 정렬 전에 P 포화로 x_max 까지 쫓아감. gateway `자름 x_max` 3회, 두산 안내 **3205**(특이점 구역 Outside→Inside, 팔을 뻗은 x≈600 부근), **알람 1215** 가 0 유지 뒤·watchdog 전에 1회(controller MOVING) — §3 |

재검에서 확인된 무해한 관측: belt_servo 틱 로그의 `tcp_extrap_capped` 가 case 마다 2~7틱 True — 전부 로봇이 서 있는 구간(goal 첫 틱·LIFT 뒤 VERIFY)으로, pose 값이 바뀌지 않아 기준 stamp 가 오래된 것으로 보이기 때문. last_cmd ≈ 0 이라 해롭지 않지만 G1 데이터에서 이 값을 pose 지연으로 세면 안 된다(U2 후속: 정지 중 판정 제외 여부).

## 2. 재현 절차 (명령 전문은 DD §1 C0~C14 — 여기에는 실제 쓴 순서와 차이만)
1. C0 → C1 `ROS_DOMAIN_ID=85 voss-dsr-virtual-up`(백그라운드, PID 파일) → `pkill -f "[r]viz2 -d .*m0609_rg2_bringup"`.
2. C2(상태·posj) → C3(move_joint 관측 자세) → C4 gateway(service) → C5 echo → C6 gateway(joint_states) 재기동 → 끔.
3. case 마다 `bash emu_case.sh <normal|cancel|lost>`(C3·C4·C5·C7~C11 묶음, 스크래치 — DD §4). 스크립트의 실제 구현에서 DD 와 다른 점: ① `set -m`(비대화형 bash 의 `&` 작업이 SIGINT 를 무시로 상속받는 문제, §4 ④) ② 래퍼 거부 시 재시도(§4 ⑤) ③ fake_box 에 `setsid` 를 쓰지 않음(`set -m` 이 그룹을 만든다; setsid 는 fork 해서 PID 파일이 어긋남) ④ stop 뒤 PID 가 사라질 때까지 대기(최대 15 s) 후 남으면 그룹 SIGKILL.
4. Q3: C12 를 AUTONOMOUS 에서 1회(실패) → `system/set_robot_mode {robot_mode: 0}` → C12 다시(성공) → `set_robot_mode 1` 복귀 → gateway 를 service·joint_states 로 각 1회 재기동해 TCP 줄 기록.
5. C13 정리 → C14 되돌리기·검증.

## 3. 에뮬레이터 특성 (해석에만 쓰고 안전 근거로는 쓰지 않는다)
- 기동 자세는 관절 0(E1 확인). speedl 전에 move_joint 로 관측 자세로 옮겼다.
- 알람 1215(0.1 s 타임아웃)는 10/10 세 case 에서 0회였지만 **실행에 따라 0~1회** 난다(10/11 재현 lost 1회, 재검 late 1회). 나는 시점은 항상 같다: goal 이 끝나 0 유지가 끝난 뒤, 컨트롤러가 아직 MOVING(감속 중)인 채 스트림이 끊기면 1215 가 먼저 나고 그다음 gateway watchdog 이 move_stop 을 부른다. 즉 **에뮬레이터는 watchdog 보다 먼저 스스로 선다** — 실로봇은 반대로 계속 간다(ADR-0010). 틱이 밀려서가 아니라 "0 유지가 감속보다 먼저 끝났다" 는 신호라, §4.1·§5 의 DEC-16 질문(0 유지 시간 vs 감속)과 같은 현상이다. 30 Hz 틱 자체는 세 case 모두 거부 0·old 0 으로 밀리지 않았다. 같은 실험에서 안내 3205(특이점 구역 진입)가 x≈600 부근에서 났다 — 실기 G1 에서 x 상한 근처 자세를 볼 때 참고. 안내 1216(`[SpeedL] Time adjusted automatically considering acceleration limit you set`)은 case 마다 1회, 실로봇에서도 같은 안내(measurements #3).
- TCP 는 처음에 미등록(플랜지 모드). 자동 모드에서는 ROS 로 등록 불가, 수동 모드에서는 가능(E10).
- 로봇 시스템 값은 정상일 때 1(VIRTUAL). DRFL 이 끊겨 FaultOccured 가 된 뒤에는 0(REAL)·state 3(SAFE_OFF)·posj 0 을 돌려줬다(§4 ①) — 측정 스크립트의 "robot_system==0 → 실로봇" 가드는 이 상태를 실로봇으로 오인할 수 있다.

## 4. 알려진 차이·시행착오 (재현할 사람이 알아야 할 것)
① **호스트 과부하 → DRFL 끊김**: 1회차 브링업 5 분 뒤(다른 세션의 그림 내보내기 + 검증 에이전트와 겹쳐 load ≈20) ros2_control 오버런 뒤 `Disconnected.. Please check out Ethernet Cable..`, DRCF 로그 `OPERATION_CLIENT_DISCONNECTED → CCtrlStateFaultOccured`. 재연결 없음 → `voss-dsr-virtual-down` 뒤 다시 `up`. down 뒤 ros2_control_node·joint_state_publisher·run_emulator·robot_state_publisher 가 INT/TERM 을 무시하고 남아 KILL 로 정리했다(10/11 재검의 정상 down 은 깨끗했고, 10/11 내 재실행에서는 down 직후 pgrep 에 자식들이 남아 TERM 으로 정리됐다 — 실행마다 다르므로 **down 뒤 pgrep 확인은 항상** 한다)(옛 run_emulator 를 TERM 으로 끝내면 종료 처리에서 **새 컨테이너를 rm 할 수 있으므로** KILL). 에뮬레이터 DRCF 는 4코어(--cpuset-cpus 0-3)를 상시 점유해 load 가 20 안팎이다 — 실험 중 다른 무거운 작업을 피한다.
② gateway 종료 때 `pose 조회 실패: TIMEOUT 0.50s` 1줄, joint_states 기동 첫 틱 `joint_states 없음` 1줄은 정상 경로. service 소스 gateway 를 SIGINT 로 끌 때 `The following exception was never retrieved: cannot use Destroyable because destruction was requested` 1줄이 나올 수 있다(10/11 재검 관측, 무해 — 학민 참고).
③ 두산 안내 1216 은 case 마다 1회(위 §3).
④ **비대화형 스크립트의 백그라운드 launch 가 SIGINT 를 무시**(bash 가 `&` 작업에 SIG_IGN 을 준다; `/proc/<pid>/status` SigIgn 에 SIGINT 비트) → ros2 launch·robot_gateway(SignalHandlerOptions.NO + KeyboardInterrupt 의존)가 Ctrl-C 를 못 받는다. `set -m` 으로 해결. 터미널에서 손으로 띄울 때는 해당 없음.
⑤ **래퍼 가드 경합**: voss-ros·voss-dsr-virtual-exec 는 `pgrep -f` 로 금지 문자열을 찾는데 다른 래퍼 인스턴스(다른 세션 포함)의 pgrep 자체가 그 문자열을 cmdline 에 갖고 있어 **동시에 돌면 서로를 잡아 거부**한다. 또 실행자의 명령문에 그 문자열이 글자 그대로 들어가면 자기 셸을 잡는다. 스크립트는 거부 시 1 s 뒤 최대 5회 재시도한다. (사용자 판단 항목: 래퍼의 패턴을 `mode:=rea[l]` 처럼 자기 자신과 매치되지 않게.)
⑥ 도구 셸의 `grep` 은 ugrep 별칭이라 파일 2개 이상을 주면 멈춘다(`/usr/bin/grep` 사용). 재현자는 터미널에서 돌리므로 해당 없음.
⑦ normal 1·2회차 실패는 ④·⑤ 탓이며 로봇·belt_servo·gateway 문제가 아니었다(1회차 goal 미전송, 2회차 fake_box 기동 거부).
⑧ C13 정리 때 잔여 프로세스를 이름 패턴으로 찾으면서 `[s]pawner`(ros2_control spawner 의도)가 GNOME 가상 파일시스템 데몬 4개(`gvfsd-trash·recent·network·dnssd`, 인자 `--spawner`)에도 걸려 TERM 을 보냈다. 이 데몬은 필요할 때 GNOME 이 다시 띄우는 보조 프로세스라 작업 데이터 영향은 없지만, **정리는 PID 파일이나 실행 파일 경로로만** 해야 한다는 교훈(DD C0·C13 패턴을 그렇게 고쳤다).

## 4.0 10/11 PR 전 최종 재검 (Opus, 에뮬레이터 재기동·재현·DD 손 실행)
- normal·cancel·lost 모두 8/8 통과(E7~E9 와 같음), DD C0~C14 를 손으로 따라 E1~E6·E12 재확인. 조건부 go → 지적 반영: #134 머지·#139 a0db91e 문구, 1215 해석(위 §3), C14 untracked 파일, goal 타이밍 사실대로, 틱 수 등 수치 삭제, C2·C4·C9 재현성, HLD 패턴 통일, runbook pose_lag 참조, 종료 예외 1줄.
- 받아들이지 않은 것: "emu_goal 을 fake_box 보다 먼저 띄워 대기" 순서 변경(현재 순서로 세 번 모두 재현됐고 D10 에 여유를 적는 것으로 충분), 문서 분량(설계·절차·결과 3개 문서가 각각 한 역할이라 합치지 않음).

## 4.1 재검에서 받아들이지 않았거나 범위 밖으로 넘긴 지적
- "스크립트 3개를 레포에 넣어야 재현 가능" → 주관 세션 결정(레포에 launch·스크립트 추가 없음)대로 레포 밖에 둔다. 대신 최종본 sha256 앞 12자리를 §6 에 적는다. 결과를 만든 뒤 스크립트가 두 번 바뀌었다(setsid 제거·OUT 환경변수·pgrep 패턴 — 판정 로직은 그대로). 재검이 최종본으로 세 case 를 다시 돌려 같은 판정을 얻었으므로 결과는 최종본 기준으로 봐도 된다. **10/11 재부팅으로 `/tmp` 의 실험 로그·스크립트 원본이 지워져** 스크립트는 같은 내용으로 다시 만들었고(홈 폴더에 보관, §6), 10/11 최종 재검이 그 사본으로 다시 돌린다.
- "zero_hold 0.5 s < 80 mm/s 에서 acc 100 감속 시간" → 에뮬레이터 수치라 근거로 쓰지 않는다. 설계 질문("0 유지 시간이 감속 시간보다 짧아도 되는가 — gateway watchdog 의 move_stop 이 감속을 끊는 것이 의도인가")으로 주관 세션·학민에게 넘긴다(§5).

## 5. 담당 밖 요청·후속
- 학민(#41): #139 머지(#134 는 10/11 머지됨). 이 실험이 둘을 전제로 OK 경로를 확인함. 참고로 rg2_dry_run 에서 `rg2_host·rg2_port` 는 무시되므로 문서에 "둘은 rg2_dry_run 에서 무시" 한 줄.
- U3 후속(내 몫): sim_check 에 "외부에서 띄운 gateway(real)로 판정" 옵션(J10 dry_run 판정 건너뛰기, launch.log 대신 gateway.log 경로 입력) — 이번엔 스크래치 emu_judge.py 로 대신했다.
- 사용자 판단: 래퍼 pgrep 패턴(④·⑤).
- 주관 세션(DEC-16): 0 유지 0.5 s 와 감속 시간의 관계(§4.1) — 실기 F-04 기록(0 명령 뒤 약 0.5 s 감속)과 함께 판단.
- U2 후속: `tcp_extrap_capped` 를 정지 중에는 세지 않을지(§1.1).

## 6. 산출물 위치
레포: `src/voss_servo/design/U-E-{hld,dd,run}.md`. 레포 밖(커밋 안 함): 스크립트 3개는 `~/cobot2/voss_emu_work/`(재부팅에 안 지워지는 보관본; sha256 앞 12자리 `emu_case.sh 5100d5442589`·`emu_goal.py 68eb407fc57a`·`emu_judge.py 92ccc15639d3` (10/11 최종 재검 뒤 success 검사·gateway 선점 검사·t_sigint 누락 처리 추가)). 10/10 실험 로그(`/tmp/voss_emu/`, `/tmp/voss_emu_review/`)는 10/11 재부팅으로 사라졌다 — 이 문서의 표가 그 기록이다. 다시 돌리면 `/tmp/voss_emu/<case>/` 에 같은 구조로 생긴다.
