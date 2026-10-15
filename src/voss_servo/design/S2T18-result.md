# S2-T18 실기 결과 — J6 회전 파지 (U14) 최종

- 2026-10-15 13:00~16:10, 공용 PC·실로봇(M0609 + RG2 + 손목 D435i), 벨트 h250(FF 4.56 cm/s). 실행 김학민(비상정지 동행), 기록·분석 Claude.
- **판정: 기능 시험·적용 완료**(사용자 판정 10/15 16:10). 최종 설정 = 아래 4절. 에뮬레이터 단계([S2T18-run.md](S2T18-run.md) 2절)는 일정상 생략하고, 부호·회전 중심·정지 경로는 실기 저속 단계(R1~R3)로 대신 확인했다.
- 원자료(레포 밖): 공용 PC `~/voss_data/1015/u14/` — `record.md`(회차별 기록·분석), `servo/`(틱·시도 jsonl), `mon/`(공구 yaw·pose 모니터), `bag/`(손목 영상·BoxTrack·pose 녹화 5개, 약 40 GB), `logs/`(노드 로그).

## 1. 결과 요약

| 단계 | 설정 | 회차 | 결과 |
|---|---|---|---|
| R1~R3 저속 직접 지령 | gateway 한계 20·70·100, 10 °/s | ±11·±18·±46·±91° | 아래 2절 전부 ✅ |
| 1단계 | max 45, ω 30·60 | 회전 8 + 0° 대조 1 | **9/9 OK** |
| 5단계 | max 90, ω 60(≤80°)·30(90°) | 유효 41 | − 방향 12/12, + 방향 19/29 — **+ 67° 이상 9/18**(시야 LOST) |
| **6단계(최종)** | max 110, **flip 70**, **회전 중 LOST 1.2 s**, gateway 한계 130 | **14** | **14/14 OK** — |Δ| 67.9~109.4°, + 쪽 큰 각 7회를 − 쪽(−89~−109°)으로 |

OK 회차 공통: 회전 중 TCP z ≥ 박스 윗면 + 50 mm, DESCEND·GRASP 각속도 0, 오버슈트 0°, DESCEND 시작 |rot_err| 0.74~0.85°(tol 1.5 직전에서 서는 √ 법칙 그대로), 첫 시도 성공(attempts 1), goal 8.0~8.9 s.

## 2. 실측 (R1~R3, 관측 자세·벨트 정지·박스 없음, `servo_cmd` 각속도만 직접 발행)

| 항목 | 결과 | 쓰임 |
|---|---|---|
| 부호 | `angular.z` + → 공구 yaw +(베이스 Z +) | run.md E2 |
| 회전 중심 | 회전 중 TCP xy 이동 ≤ 0.20 mm (펜던트 TCP GripperDA_v1 등록 상태) → **등록 TCP 기준 회전, gateway 보정 불필요** | run.md E3·④ |
| 지령 → pose 지연 | 40~52 ms(0.1° 반응 87~122 ms − 램프 47 ms) | run.md ⑫ ≤ 80 ms ✅ |
| 정지 지터 | 측정 각속도 최대 0.10 °/s | `still_dps` 2 유지 |
| pose 주기 | 중앙 20 ms, 최대 47~52 ms | `pose_fresh_s` 0.05 유지(⑪) |
| watchdog 정지 | 발행이 끊기면 0.2~0.3 s 뒤 정지, 그동안 10 °/s 에서 2.3~2.6° 더 돎 | run.md E4·⑤ |
| gateway yaw 한계 | 한계 20° 에서 +18.0°/−18.3° 정지(계산 17.4°, 자름 `yaw_limit`) | run.md ⑯ E8-R ✅ |
| 케이블·카메라 | ±46°·±91° 카메라 끊김 최대 68 ms, 케이블 이상 없음(육안). −120° 는 지령만(모니터 없음) | run.md ⑩ |
| 돌아간 손목 → MoveToZone | OBSERVE·HOLD PLACE 모두 ok(±11°~−110° 잔여 각에서) | run.md E6b·⑬ |

## 3. 5단계에서 찾은 문제와 6단계 대책

**+ 방향 회전의 시야 문제**(run.md ⑭가 60° 이상에서 실제로 나타남). 녹화를 `tools/vision/box_overlay.py` 재생으로 끊긴 프레임을 봤다.
- A형(회전 중): 손목 +52~74° 에서 카메라가 박스를 비스듬히 봐 **송장 후보가 박스 옆면과 한 덩어리 → 채움(0.30~0.39 < 0.80)·비율 탈락**이 0.5 s 넘게 이어짐 → LOST.
- B형(회전 뒤 TRACK): 송장 아래 끝이 **영상 아래 가장자리(v 1080)** 에 닿아 가장자리 탈락. 4건 모두 goal 이 늦은 회차(x −62~−70 mm).
- − 방향은 같은 각에서 박스가 화면 안쪽에 위에서 보여 끊김 ≤ 1 프레임(15/15). 박스 3개 모두 같은 경향 → 박스 특정 아님, 카메라 장착 기하(광축이 TCP 상류 ≈ 75 mm).

**대책(6단계, 이 PR)**
1. `rotate.flip_above_deg` 70 — 박스는 180° 대칭이라 Δ > +70° 이면 Δ − 180°(−110~−90°)로 돌린다. 있으면 `max_deg` 를 180 − flip(110) 까지 허용.
2. `rotate.lost_timeout_s` 1.2 — 회전을 쓴 goal(ROTATING·SETTLING·DONE·STOPPING·FALLBACK)의 PREPARE·TRACK 에서만 LOST 기준을 늘린다(그 밖 0.5 그대로). 끊긴 동안은 마지막 관측 + FF 예측으로 따라간다. 6단계에서 +69.3°·늦은 goal(−58 mm) 회차가 0.50 s 끊긴 뒤 계속 진행해 OK.
3. 트랙 번호 유지는 box_tracker 의 기존 hold_id(sort_manager `/voss/sort/state` PICKING 트랙은 끊겨도 지우지 않음)가 맡는다 — 코드 변경 없음. 단독 시험 도구도 goal 때 PICKING 을 발행해 같은 조건으로 시험했다.

## 4. 최종 설정

**robot_gateway**
```bash
ros2 launch voss_robot robot_gateway.launch.py dry_run:=false pose_source:=joint_states \
  servo_angular:=true servo_yaw_limit_deg:=130 config:=$HOME/voss_ws/config/voss_config.yaml
```
- `servo_max_ang_dps` 60·`servo_ang_acc_dps2` 90 는 노드 기본. 한계 130 = − 쪽 최대 110 + 0.2 s × 60 °/s(12) + 여유.
- 펜던트 TCP 는 voss_config `tcp_offset_mm` 로 등록(기동 줄 `컨트롤러 TCP 등록 voss_config 와 같음`).

**belt_servo** (`config/belt_servo_real.yaml.example` 의 rotate 블록 = 최종값, `enable` 만 실기 yaml 에서 true)

| 키 | 값 | 키 | 값 |
|---|---|---|---|
| enable | **true**(실기 yaml) | input.pose_lag_ms | **0** (joint_states) |
| deadband_deg | 4 | min_deg | 10 |
| max_deg | **110** | flip_above_deg | **70** |
| lost_timeout_s | **1.2** | omega_max_dps | 60 |
| alpha_dps2 | 90 | tol_deg | 1.5 |
| n_min · buffer_n | 5 · 15 | r_min | 0.97 |
| decide_max_s | 0.5 | start_tol_deg | 3 |
| omega_floor_dps | 3 | hold_dz_mm | 50 |
| settle_s · stall_s | 0.3 · 0.6 | still_dps | 2 |
| return_min_dz_mm | 10 | pose_fresh_s | 0.05 |

기동 줄: `rotate on · deadband 4 · min 10 · max 110 · ω 60 · α 90 · home goal · flip >70 → − · lost(회전) 1.2 s`. 첫 goal 은 관측 자세에서(회전 기준 공구 yaw = −88.72°).

**끄기**: 실기 yaml `rotate.enable: false` + gateway 를 `servo_angular` 없이 → 시연 라인과 params_sha 까지 같다(rotate.* 는 끄면 지문에서 빠진다).

## 5. 같이 고친 것 (gateway, 김학민 담당)
- `servo_yaw_limit_deg` launch 인자 — 실기 단계별 한계(20·70·100·130)를 노드 기본 100 대신 줄 수 있게. 비우면 기존과 같음.
- **등록 TCP 확인 오판** — joint_states 운용 중 2 s 마다 TCP·플랜지 posx 를 차례로 읽어 비교하는데, MoveToZone(300 mm/s) 중에는 두 값이 30 mm 어긋나 TCP 를 "모름"으로 보고 pose_source 를 service(10 Hz)로 **영구 전환**했다(10/12~10/15 시연·통합 로그에도 여러 번). MoveToZone 중에는 확인하지 않도록 수정 — 그 뒤 HOLD MoveToZone 수십 회에도 joint_states 유지.

## 6. 알려진 한계·남은 일
- **RETURN_INCOMPLETE**: 되돌림 창(LIFT z ≥ 윗면 + 10 ~ VERIFY 끝)이 약 0.8 s 라 약 14° 넘는 회전은 goal 끝에 손목이 돌아간 채(끝 지령 0 → 감속분만큼 더 돌아옴). 다음 MoveToZone(PLACE·OBSERVE)이 자세를 맞춘다(HOLD PLACE 모두 ok). 로그 의미 정리 또는 VERIFY 연장은 후속.
- + 방향 60~70° 는 시야 여유가 작다(6단계 68~70° 3/3, 그중 1회 0.5 s 끊김). 회전 중 xy 목표를 카메라가 박스를 보는 쪽으로 옮기는 대책(③)은 미적용.
- 회전을 켠 채 **sort_manager 전체 흐름**(OCR 뒤 goal, 시연 기준 x −93~−52 mm) 회차는 아직 없다 — 단독 액션 시험만.
- 운영 주의: HOLD 칸에 박스가 남아 있으면 PLACE 하강 중 접촉 → 두산 알람 2/5/7060·SAFE_STOP·RG2 안전 스위치 S1·S2 잠김(268 = 104) → Compute Box 전원 재투입으로 복구(약 15분).
- 이 문서의 값은 공용 PC 단독 시험 기준이다. 에뮬레이터 E1~E8 결과는 별도로 붙으면 이 문서에 링크한다.
