# S4 실기 절차서 — FF 여러 값 × 닫힘 오프셋 자 측정 (s4a) · 비스듬 · 사다리꼴 (s4b)

- 작업 S2-T15 · #31(측정) · T29 회귀(ADR-0002:32) · S2-T14 실기. 작성 2026-10-13, 실행 10/14(로봇 시간은 09:30 스탠드업에서 확정).
- 대상 코드: 공용 PC 체크아웃 **`integ/1014-s4` (81dcc3e)** = main fec4c77(T29 값 close 2.5 · x_max 550) + #30 사다리꼴 + #33 gripper_timeout 4.0 + 학민 `z.lift_done_below_mm` 코드. belt_servo 코드는 main 44e3ff3 과 lift_done_below 키(선택 키)만 다르다. s4a·s4b·비스듬은 **같은 코드 커밋**에서 yaml·voss_config 만 바꾼다(params_sha 는 조건마다 다르고 코드 sha 는 하나).
- 근거: [U13-belt-along.md](U13-belt-along.md)(측정 설계·부호) · [S2T14-run.md](S2T14-run.md)(s4b 확인·되돌림) · [U9-run.md](U9-run.md)(안전·기록 방식).
- **모든 명령은 사람이(박병후) 공용 PC 에서 비상정지 옆에서 실행한다.** Claude 는 실행하지 않는다(CLAUDE.md 규칙 6).
- 계획 문서다. 측정값은 measurements-1014 에만 적는다. S2-T11 리허설(sort_manager 흐름)은 이 문서 밖 — 같은 날이면 순서는 스탠드업에서 정한다.
- 부호: **y = TCP − 박스 중심(벨트 방향), + = TCP 가 하류(박스 앞쪽을 잡음).**

## 0. 한눈에

| 순서 | 블록 | 회차 | 운전 | 목적 |
|---|---|---|---|---|
| 준비 | 박스 표시·송장 오프셋 ℓ_k · 기동 확인 · **벨트 정지 실측 ①** | — | — | 기준·고정 조건 |
| 1 | s4a FF **4.69** | 8 | send_goal + 자 측정 | 시연 FF 후보, 기준 |
| 2 | s4a FF **4.80** | 6 | 같음 | G1·s2 와 대조 |
| 3 | s4a FF **4.60** | 6 | 같음 | FF 항 기울기 c |
| — | **벨트 정지 실측 ②** | — | — | 중간 변화 |
| 4 | s4a FF **4.74** | 4 | 같음 | 비선형 확인 |
| 5 | s4a FF **4.64** | 4 | 같음 | 비선형 확인 |
| 6 | s4a FF **4.69** | 2 | 같음 | 결정 FF 합계 10회(ADR-0002:32), 처음·끝 비교 |
| 7 | 비스듬 **20 · 30 · 37°** (FF 4.69, p) | 3 | 같음 + 각도 사진 | U9-a 경주 해소 첫 실증, gripper_timeout 4.0 |
| 8 | s4b 사다리꼴 (FF 4.69) | 1 → 확인 → 4 | 같음 | S2-T14 실기 · 체류 시간 다른 조건 |
| 끝 | **벨트 정지 실측 ③** · 원래 설정 복귀 | — | — | — |

- FF 4.69 = 10/12 추종 중 추정(46.92 mm/s). **아침 정지 실측 ①이 10/12 의 4.73 과 ±0.03 넘게 다르면 4.69 도 같은 만큼 옮긴다**(예: 4.70 → 4.66). 다른 수준은 그대로.
- 결정 FF 가 4.69 가 아니게 되면(#28, 스탠드업) 블록 1·6 을 그 값으로 바꾸고 나머지는 그대로.
- **시간이 모자라면 빼는 순서**: 5(4.64) → 4(4.74) → 3(4.60) → 8 의 4회 → 7. 블록 1·2 는 지킨다(앞 2블록 14회만으로는 c 판정이 약하다 — U13 4.3).

### 시간 추정

| 항목 | 시간 |
|---|---|
| 회차 1번 = 박스 투입·track_id 읽기 15 s + goal 12 s + 정지 확인 5 s + 자 측정·사진 30 s + 놓기·OBSERVE 복귀 20 s | **약 80~90 s** |
| s4a 30회 | 약 45 분 |
| FF 전환 5번(voss_config 고침 + belt_servo 재기동 + 확인 줄) | 약 8 분 |
| 벨트 정지 실측 3번(박스 5개씩) | 약 9 분 |
| 준비(박스 표시·ℓ_k 5개·기동 확인) | 약 15 분 |
| 비스듬 3 + s4b 5(재기동 포함) | 약 15 분 |
| **합계** | **약 90 분** (블록 1·2·3 만이면 약 50 분) |

## 1. 안전·동행 (하나라도 ❌ 면 시작하지 않는다)

| 항목 | 기준 |
|---|---|
| 동행자 | 2명 이상. **비상정지 대기자는 실행자와 다른 사람**, 손이 비상정지 위에. 자 측정은 동행자(측정자) |
| 펜던트 속도 | **100 %**(사각 체류 상한 3.44 s(p) / 2.50 s(사다리꼴)의 전제) |
| gateway | `servo_max_speed_mm_s` 100 · `servo_acc` 100 · z 하한 78 · `pose_source:=joint_states` |
| 작업 영역 | 영역 리밋·펜던트 공간 제한 켜짐, `reach.x_max_mm` **550** |
| 벨트 | h250. 증속 금지 |
| **정지 상태 접근 규칙** (자 측정) | ① 실행자가 send_goal 터미널에 **결과(result)가 찍힌 것**을 소리 내어 확인 ② 로봇이 멈춘 뒤 **2 s 더 기다림**(belt_servo 0 유지 0.5 s → gateway watchdog 정지) ③ 실행자는 키보드에서 손을 뗀다 — 측정 중 어떤 명령도 보내지 않는다 ④ 측정자는 핑거 사이·아래에 손을 넣지 않는다(자는 박스·패드 **옆면**에 댄다) ⑤ 측정 중 새 박스를 벨트에 올리지 않는다 ⑥ 측정자가 물러난 것을 확인한 뒤에만 놓기 명령 |
| 들고 있는 동안 | TCP(핑거 끝)는 들기 높이(윗면 +48~50, 10/12 실측) — 들린 박스 밑면(핑거 끝 −8)과 벨트 위 박스 윗면 사이 약 40 mm. 그래도 측정 중엔 투입하지 않는다 |
| 첫 회차 확인 | 자 측정이 안전하게 되는지(위치·자세), 패드 끝이 보이는지. 안 되면 U13 3.2 대안(측면 사진만) |
| "멈춰" | 소프트웨어 정지(SR-NF-09). 위험하면 **비상정지가 먼저** |
| 보호정지·일시정지 | 측정을 위해 일부러 걸지 않는다(걸었을 때 gateway·RG2 상태가 미확인). 걸렸으면 학민과 복구 절차 확인 뒤 재개 |

## 2. 고정 조건 (기록한 뒤 시작)

| 항목 | 값 · 확인 |
|---|---|
| 코드 | `git rev-parse --short HEAD` → **`81dcc3e`**(`integ/1014-s4`), 빌드 시각. 기동 로그 다섯 줄 + `z 프로파일` 줄로 이 코드인지 확인(아래 표) |
| **`z.lift_done_below_mm` (필수 확인)** | 실기 yaml 에 **키가 없거나 0** 이어야 한다(특히 s4b 사다리꼴). 30 이 있으면 LIFT 끝 속도 71 mm/s 로 끝점 위 27~31 mm 지나친다(U12 후속 분석). 확인: `grep -n lift_done_below ~/voss_ws/config/belt_servo_real.yaml` 결과 없음 또는 0, 기동 뒤 `ros2 param get /belt_servo z.lift_done_below_mm` → 없음/0.0 |
| **pose 짝 (필수 확인)** | `input.pose_lag_ms` **0** + gateway `pose_source:=joint_states`. gateway 로그에 `pose_source joint_states → service` 되돌림 또는 `거부` 줄이 **없어야** 한다(service 로 돌아가면 지연 전제가 깨져 착지가 z 하한 78 아래로 갈 수 있음). 있으면 시작하지 않는다 |
| 실기 yaml `~/voss_ws/config/belt_servo_real.yaml` | `grasp.close_time_max_s` **2.5** · `reach.x_max_mm` **550** · `gripper_timeout_s` **4.0** · `z.vision_cutoff_above_top_mm` 30 · `retry.max_attempts` 1 · `grasp.hold_width_max_mm` 44.0 · `input.pose_lag_ms` 0 · `z.profile` 없음(= p). 파일 sha256 앞 12 기록 |
| voss_config `belt.speed_cmps` | 블록마다 바꾼다(3절) — **블록마다 config_sha256 기록**. 고치기 전 백업 `voss_config.before_1014_s4.yaml` |
| box_tracker | `hand_eye … moving_verified=True pose_lag=15 ms` |
| sort_manager | **s4 블록 동안 띄우지 않는다**(send_goal 운전 — goal 이 두 곳에서 오지 않게) |
| 박스 | 3~5개, ID·"앞" 화살표·송장 정방향(180° 금지, #23), ℓ_k 측정표(5절) |

### belt_servo 기동 로그 확인 (블록마다 사진/복사)

| 줄 | p (블록 1~7) | 사다리꼴 (블록 8) |
|---|---|---|
| 첫 줄 | `z 프로파일: p — … 하강 예상 2.64 s · 들기 예상 2.79 s` | `z 프로파일: trapezoid — … 하강 예상 1.70 s · 들기 예상 1.74 s` |
| `config_version=… config_sha256=… params_sha256=…` | 블록마다 config_sha 바뀜 | 같은 FF 블록과 config_sha 같고 params_sha 다름 |
| `READY` · pose_lag 줄 | READY, joint_states 짝(0) | 같음 |
| `x 여유: … x_max 까지 N mm 이상` | 아래 표 | 아래 표 |
| `사각 체류 상한: … 3.44 s` | **3.44** | **2.50** |
| `재시도 x 여유: … 실패 TCP x ≤ M mm` | 아래 표 | 아래 표 |
| `후퇴 체류 상한: … 3.79 s` | **3.79** (3.785) | **2.74** |
| gripper_timeout (READY 줄에 없음) | `ros2 param get /belt_servo gripper_timeout_s` → **4.0** | 같음 |
| FF 확인 | `ros2 param get /belt_servo belt.speed_cmps` → 그 블록 값 | 같음 |

FF 별 x 여유 N / 재시도 실패 x 문턱 M (계산, ±1 mm 반올림):

| FF cm/s | p: N | p: M | 사다리꼴: N | 사다리꼴: M |
|---|---|---|---|---|
| 4.60 | 246 | 181 | 203 | 224 |
| 4.64 | 248 | 178 | 205 | 222 |
| 4.69 | 251 | 174 | 207 | 218 |
| 4.74 | 254 | 170 | 209 | 215 |
| 4.80 | 257 | 166 | 212 | 211 |

## 3. 절차

### 3.0 준비
1. 박스 3~5개: 윗면에 ID(1~5)와 "앞" 화살표(46 mm 변 방향). **ℓ_k 측정**: 송장 중심과 박스 중심의 벨트 방향 거리(자, + = 송장이 화살표 쪽) → 5절 표. 투입은 늘 화살표가 하류.
2. gateway·box_tracker 기동 확인(런북 T2·T7). OBSERVE 자세.
3. **벨트 정지 실측 ①**: 로봇 OBSERVE 정지, 박스 5개를 한 개씩 상류에서 흘림 →
   ```bash
   python3 ~/belt_sweep/belt_speed_live.py --setting h250
   ```
   평균·범위·sd 기록(10/12 4.73, sd 0.005 와 비교). ±0.03 넘게 다르면 0절 규칙대로 4.69 수준을 옮긴다.

### 3.1 FF 바꾸기 (블록 시작마다) — 방법은 현장 판단, 추천 2안

| 안 | 방법 | 장점 | 주의 |
|---|---|---|---|
| **1안(추천)** | 공유 `~/voss_ws/config/voss_config.yaml` 의 `belt.speed_cmps` 를 고친다 → **belt_servo 만 재기동**(FF 를 읽는 노드는 belt_servo 뿐, `speed_cmps` 를 쓰는 다른 노드 없음) | 설정 파일 하나, 10/12 s3 와 같은 방법 | gateway·sort_manager 의 config_sha 와 달라진다(런북 T7 "같은 sha" 확인은 이 블록 동안 예외로 기록). 끝나면 백업으로 되돌리고 sha 확인 |
| 2안 | FF 만 다른 사본 `voss_config.ff460.yaml` 등을 만들어 belt_servo launch 의 `config:=` 에만 준다 | 공유 파일을 안 건드림 | 규칙 5 의 "설정은 한 파일" 취지와 어긋남 — 1안이 안 될 때만 |

```bash
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=<레포>/data/servo
```
재기동 뒤 2절 확인 줄(특히 `belt.speed_cmps`·config_sha·x 여유 N) 을 본다.

### 3.2 회차 1번 (send_goal 운전)
1. 박스 1개를 화살표 하류로 상류 끝에 올린다. 박스 ID 를 소리 내어 말하고 기록.
2. track_id 확인(박스가 화면에 들어온 뒤):
   ```bash
   ros2 topic echo --once /voss/vision/box
   ```
   `track_id` 와 `position_base.x` 를 본다. **x 가 약 −90 mm 근처일 때** goal 을 보낸다(sort_manager 가 보내던 위치, 10/12 −88). 늦어도 x < −40.
3. goal:
   ```bash
   ros2 action send_goal --feedback /voss/servo/track_and_grasp voss_msgs/action/TrackAndGrasp "{track_id: <번호>}"
   ```
4. 결과 확인: `grasped: true, reason: OK` → 로봇이 들기 높이에서 박스를 쥔 채 정지(결과 뒤 자동 개방 없음 — U9-b 규칙이 여기선 장점).
   - 실패(OK 아님)면 4절 되돌림·중단 조건을 본다. 박스를 쥔 채 DEVICE_ERROR 면 사람이 빼기 전 학민과 확인(10/12 track 8 사례).
5. **자 측정**(1절 정지 상태 접근 규칙 ①~⑥): 자를 벨트 방향으로, 눈금이 하류로 커지게 박스·패드 옆면에 대고 네 점을 0.5 mm 단위로 읽는다 — 패드 앞끝 P_앞 · 패드 뒤끝 P_뒤 · 박스 앞끝 B_앞 · 박스 뒤끝 B_뒤. 자가 보이게 옆에서 사진 1장. **y = (P_앞 + P_뒤)/2 − (B_앞 + B_뒤)/2** (현장에서 바로 계산, 중단 규칙용).
6. 측정자가 물러난 뒤 놓기 + OBSERVE 복귀(하나의 명령, 그리퍼 개방 포함):
   ```bash
   ros2 service call /voss/robot/move_to_zone voss_msgs/srv/MoveToZone "{zone: HOLD, slot: 0, mode: ''}"
   ```
   `ok: true` 확인 → 트레이에서 박스 회수(로봇 정지 확인 뒤). 대안(트레이 이동이 불편하면): `ros2 service call /voss/robot/gripper voss_msgs/srv/Gripper "{width: 90.0, force: 14.0}"` 로 열고 사람이 박스를 받은 뒤 `"{zone: OBSERVE, slot: 0, mode: ''}"` 로 복귀.
7. 다음 회차는 box_tracker 가 새 track_id 를 낸 뒤.

### 3.3 블록별 주의
- **블록 3(4.60)**: 실기 첫 값. 정렬 x 가 약 105, 닫힘 x 약 320 으로 뒤로 간다(x_max 550 까지 여유 충분). 첫 회차 뒤 y 를 보고 계속.
- **중단 규칙(모든 블록)**: |y| > 7 mm 이면 그 블록 남은 회차를 가운데 쪽으로 0.05 cm/s 옮긴 값으로(4.60 → 4.65, 4.80 → 4.75). 예상 y(b_phys 0): 4.60 −2.9 · 4.64 −1.1 · 4.69 +1.3 · 4.74 +3.6 · 4.80 +6.3 mm.
- **블록 7 비스듬**: FF 4.69·p. 박스를 20·30·37° 돌려 올리고 **송장 변과 벨트 변이 함께 보이는 위 사진** 1장(각도 기록). 기대(확정 아님): 10/12 경주 전엔 19~37° 가 DESCEND LOST — cutoff 30 이면 LOST 없음이 기대, 닫힘이 3 s 를 넘을 수 있음(26° 3.08 s → gripper_timeout 4.0 안). 보고 폭이 44.0 을 넘으면 WIDTH_OUT → 개방·후퇴(정상 동작). 자 측정은 하되 분석에서 따로.
- **블록 8 사다리꼴**: 실기 yaml 에 `z: profile: trapezoid` 한 줄 → belt_servo 재기동 → 첫 줄 확인 + `z.lift_done_below_mm` 없음/0 다시 확인. **1회만** 돌리고 S2T14-run 3절 B 의 확인(착지 z ≥ 80 · DESCEND·LIFT 시간 · 핑거–벨트 접촉 없음)을 한 뒤 4회. 되돌림은 S2T14-run 5절.
- **s4b 의 C(폭 밖 후퇴, S2T14-run 3절 선택 C)는 생략한다** — "후퇴만 P" 후속 커밋이 `integ/1014-s4` 에 없으면(81dcc3e 기준 없음). 그 커밋이 들어간 체크아웃일 때만 주관 확인 뒤 1회.

### 3.4 끝
- **벨트 정지 실측 ③**(3.0 의 3번과 같게). ②는 블록 3 뒤.
- 원래 설정 복귀: voss_config 백업 복원(sha 확인), 실기 yaml `z.profile` 줄 제거(sha 가 블록 1 의 params_sha 로 돌아오는지), belt_servo 재기동.
- 로그 복사: `<레포>/data/servo/{ticks,attempts}/servo_*_20261014_*.jsonl`, 기록표, 사진 → 개인 PC 로(Drive/USB).

## 4. 되돌림·중단 조건

| 조건 | 할 일 |
|---|---|
| s4a 회차 실패(OK 아님) 1회 | 멈추고 원인 확인(reason·cause·영상). 4.69 블록에서 실패면 T29 판단(시연 FF·회귀) 먼저 — 나머지 블록 보류 |
| y_phys 절댓값 > 7 mm | 3.3 중단 규칙 |
| DESCEND_BLIND_TIMEOUT · RETREAT_TIMEOUT | 펜던트 속도 100 % 확인, 반복되면 중단 |
| 자 측정 중 로봇이 움직임 | **즉시 비상정지**, 접근 규칙·명령 이력 확인 전 재개 금지 |
| s4b 되돌림 | S2T14-run 5절 그대로(실패 1회·착지 < 80·사각/후퇴 timeout·REACH_Z_MIN·핑거–벨트 접촉) |
| 벨트 정지 실측 ②가 ①과 0.5 % 넘게 다름 | 기록하고 계속(분석에서 회차별 박스 속도로 보정), 1 % 넘으면 벨트 확인 |

## 5. 기록표 (measurements-1014 로 옮긴다)

**박스 송장 오프셋 ℓ_k** (+ = 송장 중심이 박스 앞쪽)

| 박스 ID | ℓ_k mm | 사진 |
|---|---|---|
| 1 | | |

**회차표**

| # | 시각 | 블록·FF | config_sha | goal 앞 8 | 박스 ID | goal 때 박스 x | 결과 | P_앞 | P_뒤 | B_앞 | B_뒤 | y_phys | 사진 | 메모(각도 등) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | 1 · 4.69 | | | | | | | | | | | | |

**벨트 정지 실측**

| 회 | 시각 | 박스 수 | 평균 cm/s | 범위 | sd | 10/12 4.73 대비 |
|---|---|---|---|---|---|---|
| ① 시작 | | 5 | | | | |
| ② 블록 3 뒤 | | 5 | | | | |
| ③ 끝 | | 5 | | | | |

## 6. 회신 양식 (현장 → 개인 PC/주관)

```
[S4 실기] 2026-10-14 HH:MM~HH:MM, 코드 <sha>, 실기 yaml <sha>, 벨트 정지 실측 ①/②/③ <cm/s>
s4a: FF 4.69 n/OK · 4.80 n/OK · 4.60 n/OK · 4.74 · 4.64 · 4.69(끝) — 실패 <건, reason>
y_phys 수준별 평균(범위): 4.60 … / 4.64 … / 4.69 … / 4.74 … / 4.80 …  (부호 + = TCP 하류)
ℓ_k: 박스 1 … 5
비스듬 20/30/37°: 결과·닫힘 s·보고 폭·사각 진입 직전 obs_rx_age
s4b: 1회 확인(착지 z·DESCEND·LIFT s) → 4회 결과 / 되돌림 여부
특이: 자 측정 가능 여부·대안 사용, 경고 로그, 사건
로그 파일: servo_ticks/attempts_20261014_*.jsonl, 사진 폴더
```
