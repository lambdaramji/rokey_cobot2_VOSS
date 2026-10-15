# S2-T18 실기 절차서 (초안) — J6 회전 파지: 에뮬레이터 → 실측 → 실기 1단계(15·30·45°) → 5단계(60~90°)

- 작업 S2-T18 · 작성 2026-10-14 · **초안 — 1절 실행 조건이 모두 ✅ 가 되기 전에는 실행하지 않는다.**
- **2026-10-15 실기 완료 — 결과·최종 설정은 [S2T18-result.md](S2T18-result.md).** 2절 에뮬레이터는 일정상 생략하고 실기 저속 단계(R1~R3)로 대신 확인했다. 실기에서 4·5단계 뒤 6단계(flip 70·회전 중 LOST 1.2 s·max 110)를 더해 최종으로 했다.
- 대상 코드: 이 단위 PR(`feat/S2-T18-voss_servo-j6-rotate`)이 main 에 머지된 체크아웃. S2-T16(BoxTrack yaw, #51 945c67d)·D0 interface(#48 dd55e56)는 이미 main 에 있다. 기능 플래그 `rotate.enable` 기본 off — 끄면 시연 라인과 params_sha 까지 같다.
- 근거: [S2T18-hld.md](S2T18-hld.md)(D7 적용 단계·r3 주석) · [S2T18-dd.md](S2T18-dd.md)(12·13절) · [S2T18-pseudo.md](S2T18-pseudo.md)(r2) · [U9-run.md](U9-run.md)(공통 안전·기록 방식).
- **실기·공용 PC 명령은 모두 사람이(박병후) 비상정지 옆에서 실행한다.** Claude 는 실행하지 않는다(CLAUDE.md 규칙 6). 2절 에뮬레이터 단계만 개인 PC 에서 Claude 가 직접 돌린다.
- 이 문서는 계획이다. 값은 전부 **제안값**(T17 전)이고, 측정값은 measurements 에만 적는다.

## 0. 단계와 확인할 것

| 단계 | 어디서 | 누가 | 확인할 것 | 통과 기준(제안) |
|---|---|---|---|---|
| 2 | 개인 PC 두산 에뮬레이터 | Claude(래퍼) + 학민 T17 코드 | 회전이 실제로 돈다·부호·회전 중심·모든 정지 경로 각속도 0·되돌리기 | 2절 표 전부 |
| 3 | 공용 PC·실기 (로봇 정지·펜던트) | 학민·현지(담당 밖) | 측정 ① 돌린 그리퍼 간섭, 측정 ② 돌린 자세 위치·yaw 오차, yaw 관측 실험 | 결과로 max_deg·데드밴드 확정 |
| 4 | 실기 | 박병후(+동행 2) | 1단계: 0° 대조 3 + 15·30·45° 각 3 (min 10·max 45) | 4절 |
| 5 | 실기 | 박병후(+동행 2) | 60·75·90° 각 3, min_deg = 데드밴드, max 90 | 5절, pending #27 범위 확정 |

## 1. 실행 조건 (하나라도 ❌ 면 4·5단계를 시작하지 않는다)

| # | 조건 | 확인 방법 |
|---|---|---|
| ① | **T17(학민) 머지**: gateway 가 servo_cmd `angular.z` 를 **베이스 Z 각속도**로 speedl 에 넘김(지금은 두 곳에서 막힘 — `servo_guard.py:82` 가 "angular" 로 자르고, `doosan.py:443` 이 speedl `vel[3:6]` 을 항상 0 으로 보냄. 둘 다 바뀌어야 한다 — 학민 #48 리뷰). S2-T17 = #164(옛 `_2` #56) `servo_angular:=true`(기본 끔) | gateway 기동 줄 `servo angular on · ω ≤ 60 °/s · α 90 °/s² · yaw -88.7 ± 100°`. 통계 줄 `자름` 에 **`angular`·`ang_speed`·`yaw_limit` 셋 다 0**(켬이면 `angular` 는 x·y 만 센다) |
| ② | gateway `servo_acc[1]` ≥ belt_servo `rotate.alpha_dps2`(제안 90). **10 이면 J6 를 켜지 않는다**(HLD D5·9절: 90° 가 x 문턱 초과, 관성 180°). S2-T17 #164 는 PL 리뷰 🟡2 로 **기본 10 유지, `servo_angular_enable` 일 때만 90** | 켬일 때 기동 줄 `servo angular on · … α 90 °/s²` — 이 줄의 α 는 **각속도에 실제로 쓰는 값**이어야 한다(J-gw 가 읽음). sim 은 `sim_check --profile rotate_gw` 의 J-gw 가 자동 비교 |
| ③ | gateway 각속도 상한(`servo_max_ang_dps`) ≥ `rotate.omega_max_dps`(제안 60) | 기동 줄 `servo angular on · ω ≤ 60 °/s`. sim 은 J-gw |
| ④ | **회전 중심**: 에뮬레이터(2절)로 TCP 기준인지 확인, 플랜지 기준이면 gateway 가 보정(계약상 gateway 몫 — belt_servo 는 보정하지 않는다) | 2절 E3 |
| ⑤ | 만료·stop·자름 재전송 등 gateway 의 **모든 0 경로에 각속도 0**, 각속도 0 뒤 감속 거리 측정값 | 2절 E4·E5 |
| ⑥ | T16 머지(**#51 945c67d, 10/14 완료**) 이후 main 으로 **호스트·비전 컨테이너 동시 빌드**: BoxTrack 에 yaw 필드 | `ros2 interface show voss_msgs/msg/BoxTrack \| grep yaw` → 2줄. belt_servo 틱 `yaw_valid` 가 true/false |
| ⑦ | D0 interface PR #48 머지(**dd55e56, 10/14 완료** — topics.md 각속도 문구: PREPARE·TRACK·LIFT·VERIFY·안전 후퇴) | main 의 topics.md |
| ⑧ | gateway `pose_source:=joint_states` + belt_servo `input.pose_lag_ms: 0`(rotate 가 켜지면 교차 검사가 60 을 거부) | gateway 기동 줄 `pose_source joint_states 확인: … → 사용`, 회차마다 `→ service`·`거부` 없음 |
| ⑨ | 3단계 결과: 데드밴드·r_min·n_min(yaw 관측 실험), max_deg(측정 ②·간섭 ①) 를 measurements 에 기록하고 실기 yaml 에 반영 | measurements 문서 |
| ⑩ | ❌ 이면 진행 금지 — **손목 카메라 USB 케이블 고정**(커넥터 고정·여유 루프) + **gateway `servo_yaw_limit_deg` < USB 가 빠진 J6 각**(T17 케이블 실측, 100° 는 임시값 — #164 코멘트 C). 10/14 측정 ② 에서 J6 회전 뒤 USB 커넥터가 **두 번 빠졌다**(학민 #54 리뷰). 고정 뒤 펜던트로 J6 를 관측 자세에서 ±45°(5단계면 ±90°) 천천히 돌려 당김·걸림 없음 | 고정 사진 + **회차마다** `ros2 topic hz /camera/color/image_raw` ≈ 30 Hz(끊기면 그 회차 무효) |
| ⑪ | `/voss/robot/pose` 주기 ≤ 25 ms(≥ 40 Hz) — 회전 "정지" 판정은 pose 수신이 `rotate.pose_fresh_s`(0.05) 안일 때만 믿는다. 느리면 STOPPING 이 정지를 못 봐 TRACK 에 묶인다 → pose_fresh_s 를 측정 주기의 2배로 | `ros2 topic hz /voss/robot/pose` (joint_states 운용이면 약 50 Hz) |
| ⑫ | J6 **지령→pose 지연** ≤ 80 ms — belt_servo 는 이 지연을 보상하지 않는다. 시험 모형 기준 지나침이 80 ms 에서 ≈1.5°(tol), 100 ms 에서 ≈2.5°, 150 ms 에서 ≈5.5°(+ 일부 TIMEOUT) *(계산, test_rotate FakeRobot)*. 각가속 오경보는 지연과 무관하게 나지 않는다(최종 재검 반영) | 에뮬레이터·실기 틱 로그: `wz_cmd_dps` 가 처음 0 이 아닌 틱 → `wz_meas_dps` 가 처음 ≥ `still_dps` 인 틱의 시각 차에서 램프 시간(still_dps/α ≈ 22 ms)을 뺀다. 같은 회차에 **정지 상태의 `wz_meas_dps` 지터**(회전 전·되돌림 뒤 최대 |값|)도 기록한다 — 실기 yaml `rotate.still_dps`(sim 2, 실기 null → 켤 때 필수)는 이 지터보다 커야 한다. STOPPING 은 측정이 still_dps 아래로 2틱 이어져야 끝나므로(돈다고 재는 동안은 진행 안 함, #167 학민 승인 참고), 지터가 넘으면 STOPPING 이 x 끝·LOST 까지 이어진다 |
| ⑬ | **매 goal 전 관측 자세(OBSERVE, 절대 자세)** — sort_manager 는 PLACE 뒤 OBSERVE 로 돌아오고(`sort_fsm.py:935`), 실패·취소는 PAUSED → resume 때 OBSERVE(`sort_fsm.py:838`). 손목이 돌아간 채 끝난 goal(RETURN_INCOMPLETE·회전 중 취소) 뒤 회복은 이것에 기댄다 — 기준 각은 노드 수명 동안 한 번만 정하므로, OBSERVE 없이 goal 을 이어 보내면 다음 goal 들이 START_ROTATED 로 회전 없이 돌아간 손목으로 잡는다 | 단독 액션 시험(E·4단계)은 goal 사이에 MoveToZone OBSERVE 를 직접 부른다. attempts `rot_cause` 에 START_ROTATED 가 없다 |
| ⑭ | **회전 대기 중 시야 — 보류(사용자 10/14), 4단계 첫 회에서 확인.** 학민 #54 리뷰 1: 10/14 측정 ② B45 — TCP X −119.7·Z 151, 박스 +45° 에서 검출 0(박스가 화면 아래 가장자리, 카메라 광축이 TCP 보다 약 75 mm 상류), 벨트 가장자리 박스는 J6 + 쪽 +30° 부터 hull 경계에 걸려 검출 0(A0_2). 측정 ② 는 측정 정확도에 의문이 있어(사용자) 설계는 바꾸지 않고, 실제로 LOST 가 나면 그때 설계한다(후보: 회전 중 xy 목표를 카메라가 박스를 보는 오프셋에 두기 / 회전 대기 중 LOST 를 FF 예측으로 버티기). fake_box 는 xy 시야를 흉내 내지 않아 sim 에서 안 보인다 | 4단계 2번(15°) 첫 회 틱 로그: ROTATING·SETTLING 동안 `visible` 끊김 길이 < `input.lost_timeout_s`(0.5 s), cause LOST 없음. LOST 면 4단계 중단 → 설계 단위 |
| ⑮ | 회전 기준 각 = gateway yaw 한계 중심 — belt_servo 기준은 노드 기동 뒤 첫 goal 의 공구 yaw(관측 자세 = −88.72°), gateway 는 `observe_pose` 공구 yaw ± `servo_yaw_limit_deg`(100°) 밖으로 가는 각속도를 자른다. 같은 값을 두 곳에 적지 않는다(`rotate.home_tool_yaw_deg` 는 null 유지, 관측 자세를 다시 가르치면 둘이 어긋남) | belt_servo 로그 `회전 기준 공구 yaw = X°` 와 gateway 기동 줄 `yaw Y ± 100°` 의 차 ≤ `rotate.start_tol_deg`(3°) |

## 2. 단계 2 — 에뮬레이터 (개인 PC, Claude 실행, T17 코드 브랜치 필요)
**S2-T17(#164)과 S2-T18 의 에뮬레이터 확인은 이 표 하나로 한 번만 한다**(10/15 합의 — 학민 T17 에서는 빼고 S2-T18 에서 E1~E8 실행). 결과표·로그를 S2-T17·S2-T18 PR 양쪽에 붙인다. E2~E5·E8 은 gateway(T17) 완료 근거, E1·E6·E7·⑫ 는 belt_servo(T18) 근거.
에뮬레이터는 주기·지연 값은 믿지 않고 **동작 여부·방향·착지**만 본다(10/07 합의). 띄우기·정리는 `voss-dsr-virtual-up/down`, 그 밖 명령은 `voss-ros`(도메인 79).

| # | 시험 | 방법 | 통과 |
|---|---|---|---|
| E1 | 회전이 실제로 돈다 | rotate on + fake_box `yaw_deg 30`, goal 1개 | 틱 `rot_state` ROTATING → SETTLING → DONE, `tool_yaw_deg` 가 30° 바뀜, STALL 없음 |
| E2 | 부호 | 같은 회차 | `wz_cmd_dps` > 0 일 때 `tool_yaw_deg` 증가(베이스 Z +). 관측 자세에서 J6 관절은 − 방향(HLD D10 계산. 10/14 측정 ② 의 공구 yaw Δ / J6 Δ = −1.000 은 측정 ② 정확도 확인 전이라 근거로 쓰지 않고 E2 로 확정). belt_servo 는 베이스 Z 각속도·pose 공구 yaw 만 쓰므로 J6 부호에 기대지 않는다 |
| E3 | 회전 중심 | 회전 구간 TCP xy(`tcp_pose_m`) 변화 | TCP 기준이면 < 1 mm. 플랜지 기준이면 45° 에서 약 2~5 mm *(계산: tcp_offset xy 3.02 mm 만이면 2.3 mm, 공구 기울기 0.93° × 246.6 mm 성분까지 방향에 따라 최대 5.4 mm — HLD D9 의 4.7 mm 는 그 사이 한 경우)* → gateway 보정 요청(①④) |
| E4 | 정지 경로 각속도 0 | ROTATING 중 cancel / belt_servo 강제 종료(watchdog) | 다음 speedl 의 회전 성분 0, 관성 회전량 기록 |
| E5 | 감속 거리 | ω 60°/s 에서 0 지령 → 멈출 때까지 각 | 기록(α ≥ 90 이면 ≈ 20° 이하가 기대 — 계산 ω²/2α) |
| E6 | 되돌리기 | 같은 goal 의 LIFT·VERIFY | `rot_state` RETURNING → RETURNED, MoveToZone PLACE 경로 검사 통과(학민 ⑤ 질문) |
| E7 | 회전 off 회귀 | rotate off 로 같은 시나리오 | 각속도 0, 결과·착지 z 가 off 기준과 같음 |
| E8 | gateway 각속도 한계(T17) — **에뮬레이터 전용**(한계 근처까지 돌므로 실기 금지: 손목 카메라 케이블) | belt_servo 없이 `servo_cmd` 직접 발행(관측 자세, 벨트·박스 없음): ① angular.z 90°/s 0.5 s ② +30°/s 를 계속 ③ +60°/s 로 돌다가 한계 약 25° 앞에서 1°/s 로 바꿈(PL 🟡3) ④ +60°/s 로 한계 쪽으로 돌다가 지령을 끊음(watchdog, #164 코멘트 A) — ②~④ 는 − 방향도 | ① speedl `vel[5]` ≤ 60°/s, 통계 `자름 {'ang_speed': N}` ②~④ 공구 yaw 가 **관측 자세 yaw(−88.7°) ± `servo_yaw_limit_deg` 를 넘지 않음**, `yaw_limit` 자름. 멈춘 각과 한계의 차를 기록(gateway 감속 각 식 = PL 🟡3·코멘트 A 반영 뒤의 식과 비교). **`servo_yaw_limit_deg` 는 실측(T17 케이블·간섭, J6 ±30·45·90°)에서 USB 가 빠진 각보다 작아야 한다** — 100° 는 실측 전 임시값, ⑩ 과 함께 확인 |


## 3. 안전·동행 (4·5단계, 하나라도 ❌ 면 시작하지 않는다)

| 항목 | 기준 |
|---|---|
| 동행자 | 2명 이상. 비상정지 대기자는 실행자와 다른 사람(학민 또는 남현지), 손이 비상정지 위에 |
| 펜던트 | 속도 100 %(사다리꼴 쓰면 S2T14-run 기준), 영역 리밋·공간 제한 켜짐, `reach.x_max_mm` 550 |
| J6 범위 | 관측 자세 기준 ±45°(4단계) / ±90°(5단계) 밖으로 돌 일이 없음 — `rotate.max_deg` 로 보장 |
| 처음 회전 | 4단계 첫 3회는 **`rotate.omega_max_dps: 30`**(제안값의 절반)으로 돌려 움직임을 눈으로 확인한 뒤 60 으로 |
| 벨트 | 시연 속도(h250). 증속 금지 |
| 즉시 정지(소프트웨어 "멈춰" 또는 비상정지) | PREPARE·TRACK·LIFT·VERIFY 밖에서 손목이 돈다 / 핑거·카메라가 벨트 프레임·박스에 닿을 것 같다 / ACC_MISMATCH 경고 / 회전 중 박스가 화면에서 사라져 LOST |
| "멈춰" | 소프트웨어 정지(SR-NF-09). 위험하면 비상정지가 먼저 |

## 4. 단계 4 — 실기 1단계 (min 10 · max 45)

### 4.1 고정 조건 (기록한 뒤 시작)
| 항목 | 값 · 확인 |
|---|---|
| 코드 | `git rev-parse --short HEAD` (1절 ①⑥⑦ 포함) |
| 실기 yaml | 시연 라인 값 + `rotate:` 블록 — `enable: true`, 3단계 확정값(데드밴드·r_min·n_min·max_deg), `pose_fresh_s`(⑪ 측정 주기의 2배, 기본 0.05), 나머지는 sim yaml 제안값. `input.pose_lag_ms: 0` |
| belt_servo 기동 로그 | `rotate on · deadband … · min 10 · max 45 · ω 30(→60) · α 90 · home goal` 한 줄, READY. `READY 거부: … input.pose_lag_ms …` 면 ⑧ 위반 |
| 첫 goal 로그 | `회전 기준 공구 yaw = -88.7x° (노드 기동 뒤 첫 goal)` — **첫 goal 은 반드시 관측 자세에서 시작**(sort_manager 가 OBSERVE 로 보낸 직후). 다른 값이면 belt_servo 재기동 |
| params_sha256 | 기록(rotate on 이라 시연 라인과 다르다 — 정상) |

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
