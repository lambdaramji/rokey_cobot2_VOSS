# U9 실기 절차서 — T28 안정화 확인 (U9-c · U9-a · U9-b 공통)

- 이슈 #37 (T28) · 작성 2026-10-12 · 실행 10/12~13 로봇 시간 (09:30 스탠드업에서 남현지와 조정)
- 대상 코드: `feat/37-voss_servo-u9b-retry` 끝 커밋(U9-c 5604904 → U9-a f01750c → U9-b 위에 쌓임). 머지됐으면 main.
- 근거: [U9c-hld.md](U9c-hld.md) · [U9a-hld.md](U9a-hld.md) · [U9b-hld.md](U9b-hld.md) · docs/measurements-1010.md · docs/g1-gate.md
- **모든 명령은 사람이(박병후) 공용 PC 에서 비상정지 옆에서 실행한다.** Claude 는 실행하지 않는다(CLAUDE.md 규칙 6).
- 이 문서는 계획이다. 측정값은 measurements 에만 적는다(미측정 값을 확정처럼 쓰지 않는다).

## 0. 무엇을 확인하나 (한눈에)

| # | 시험 | 횟수 | 확인하는 단위 | 성공 기준 |
|---|---|---|---|---|
| A | 미니 게이트 (h250 정상 박스) | 5 | 세 단위 회귀 | **5/5 OK**, 각 회차 아래 U9-a 확인 3항목 |
| B | 의도 시험 — 비스듬히 3 · 늦은 goal 3 | 6 | U9-a (하강 중 LOST 경주) | 비스듬히: **DESCEND 중 LOST 0** (OK 또는 GRASP_FAILED), 늦은 goal: 10/10 과 같은 결과 |
| C | 빈 파지 유도 | 2~3 | **U9-b (안전 후퇴)** | 결과 GRASP_FAILED, **결과 전에 들기 높이(윗면 +48 이상)까지 후퇴**, 핑거가 벨트·박스에 안 닿음 |
| D | Kp 0 주행 (x 끝 종료) | 1 | U9-c (x_max 600) | x ≈ 600 에서 OUT_OF_REACH/REACH_X_MAX, z 처짐 없음 |
| E | OCR 비간섭 (남현지 동행) | A 와 함께 | 2단계 OCR | 2단계 크롭이 TRACK·DESCEND 중 들어온다, 추종에 영향 없음 |
| (선택) | 접근 높이에서 박스 치움 | 1 | U9-a | 0.5 s 뒤 LOST/BOX_MISSING |

- **재시도(2차 파지)는 현장 타이밍에서 일어나지 않는다**: 1차 실패 TCP x 가 225 mm 이하여야 재시도하는데, 현장 정렬 x 85~91 → 실패 x 293~328. 재시도 경로는 sim(`sim_check --case retry`)으로만 입증됐다(U9b-hld 1.2). C 에서는 "여유 없음 → 후퇴"를 본다.

## 1. 안전·동행 (시작 전 확인, 하나라도 ❌ 면 시작하지 않는다)

| 항목 | 기준 |
|---|---|
| 동행자 | 2명 이상. **비상정지 대기자 1명은 실행자와 다른 사람**(학민 또는 남현지) — 손이 비상정지 위에 있다 |
| 속도 제한 | 펜던트 속도 **100 %**(U9-a 사각 체류 상한 3.44 s 의 전제. 낮추면 정상 하강도 DEVICE_ERROR 가 날 수 있음), gateway `servo_max_speed_mm_s` 100 · `servo_acc` 100 그대로 |
| 작업 영역 | gateway 영역 리밋·펜던트 공간 제한 켜짐. belt_servo `reach.x_max_mm` 600 |
| 벨트 | h250(4.8 cm/s 설정, 10/10 실측 4.76). 증속 금지(범위 밖) |
| 사람 위치 | 벨트·트레이 쪽에 손 넣지 않는다. 박스는 벨트 상류 끝에서만 올린다 |
| "멈춰" | 음성/HMI 정지는 소프트웨어 정지(SR-NF-09). 위험하면 **비상정지가 먼저** |
| 개인 PC 사전 확인 | 이 브랜치에서 `sim_check --profile grasp` 8/8 통과 기록(10/12, 2절 표) |

## 2. 고정 조건 (시리즈 s2 — 기록한 뒤 시작, 바뀌면 멈추고 새 시리즈)

파라미터가 바뀌므로 g1-gate s1 의 고정 조건(params_sha256 `215e6274f074`)과 다르다 → **새 시리즈 `s2`** 로 기록한다. G1 판정(20/20, ADR-0002)은 다시 재지 않는다.

| 항목 | 값 · 확인 방법 |
|---|---|
| 코드 | `git rev-parse --short HEAD` (브랜치 끝 또는 main) |
| 실기 yaml (레포 밖, 공용 PC) | 아래 값으로 고친 뒤 sha 기록: `z.vision_cutoff_above_top_mm` **30**(U9-a, 지금 10) · `reach.x_max_mm` **600**(U9-c) · `grasp.close_time_max_s` **2.3**(U9-c) · `retry.max_attempts` **1 그대로** · `grasp.hold_width_max_mm` 44.0 · `input.pose_lag_ms` 0 |
| belt_servo 기동 로그 | `READY` + `params_sha256` · "사각 체류 상한: … **3.44 s**" · "재시도 x 여유: … **실패 TCP x ≤ 225 mm**" · "후퇴 체류 상한: … **3.78 s**" · "x 여유: … 247 mm" — 다섯 줄을 사진/복사로 남긴다 |
| gateway | `pose_source:=joint_states`, `dry_run` 아님, #139·#147 반영 커밋 |
| box_tracker | `pose_lag_ms` 15, cutoff 관련 변경 없음 |
| 벨트 | 설정 h250, 시작 때 10 s 왕복 실측 1회(cm/s) |
| 개인 PC sim 결과(참고) | retry: 1차 실패 x 190 → 재정렬 316 → 2차 OK(attempts 2) · fail_retreat: 실패 x 291 → 후퇴 2.6 s → 윗면 +48.0 mm · wide: 개방 1.03 s 뒤 상승 · empty: 윗면 +48.0 mm |

기동 (공용 PC, 사람이 비상정지 옆에서):
```bash
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=<레포>/data/servo
```

## 3. 시험 절차

### A. 미니 게이트 5회 (s2)
1. sort_manager 로 박스 1개씩 정상 운전(지금 G1 과 같은 방식). 회차마다 g1-gate 3절 기록표 1행.
2. 회차마다 틱 로그에서 U9-a 확인 3항목:
   - 사각 진입 z ≈ 윗면 +30(약 130.8 mm)
   - 사각 진입 직전 박스 수신 나이 `obs_rx_age_s` < 0.2 s
   - GRASP 진입 `err_along_m` 약 −2 mm (|값| < 3)
3. 각 GOAL_END 행: `retreat` null, `retry_room_ok` null, 경고 "들기 체류 … > 상한" **없음**(있으면 펜던트 속도·로봇 속도 확인 — 정상 LIFT 는 끊지 않고 경고만 한다).
- 성공: 5/5 OK. 1건이라도 실패하면 원인 코드를 적고 멈춘다 → PL 과 20회 재측정 여부 판단.

### B. 의도 시험 6회 (분모 밖)
- 비스듬히 3회(박스를 벨트 방향에서 약 15~30° 돌려 올림): **DESCEND 중 LOST 0**. 결과가 GRASP_FAILED(NOT_DETECTED·WIDTH_OUT)이면 C 의 후퇴 확인 항목도 같이 본다.
- 늦은 goal 3회(박스가 x 300 근처를 지날 때 goal): 10/10 과 같은 결과(정렬 순간 x 여유 부족 → OUT_OF_REACH/REACH_GRASP_ROOM 또는 OK). 접근 높이에서 끝나는 OUT_OF_REACH 는 후퇴 대상이 아니다(이미 윗면 +40).

### C. 빈 파지 유도 2~3회 (U9-b)
"박스 없이 goal" 은 트랙이 없어 LOST 로 끝나므로 쓸 수 없다. 아래 중 PL 과 정해 쓴다(현장 판단):
- **C-1 폭 밖(WIDTH_OUT)**: 박스를 90° 돌려 46 mm 변이 벨트를 가로지르게 올린다. 사전 개방(실제 약 80 mm)은 46 mm 를 넘으므로 핑거가 내려갈 수 있고, 닫힘 보고 폭이 hold_width_max 44.0 을 넘으면 WIDTH_OUT → **먼저 열고(OPENING) 연 뒤 상승(RISING)**. ⚠ 보고 폭이 44.0 안이면 OK 로 집는다 — 그 회차는 그냥 성공으로 둔다.
- **C-2 빈손(NOT_DETECTED)**: 윗면이 같은 모양이고 폭이 좁은(가로 약 20 mm 이하) 모형 박스. 닫힘 39 mm(보고값)로도 안 잡혀 NOT_DETECTED → **닫힌 채 바로 상승**.
- 각 회차 확인:
  - result `GRASP_FAILED`, attempts 1, cause NOT_DETECTED 또는 WIDTH_OUT
  - GOAL_END 행 `retreat_reason` GRASP_FAILED · `retreat_done` **true** · `retry_room_ok` **false**(현장 x 에서는 여유 없음이 정상) · phase LIFT
  - 끝 틱 TCP z ≥ 윗면 +48 mm, 후퇴 시간(LIFT 진입 → 끝) 약 2.6 s(sim), 3.78 s 를 넘지 않음
  - 영상: 후퇴 중 핑거가 박스·벨트에 닿지 않음, 윗면을 넘을 때까지 박스와 같이 이동한 뒤 수직 상승
  - C-1 은 그리퍼 로그에서 **개방(OPEN) 응답 시간**을 기록 — 개방 시간은 미측정이었다(U9b-hld P3). 2.3 s 를 넘으면 응답 전에 올라간다(설계)
- 끝난 뒤: sort_manager 는 PAUSED(지금 규칙). 로봇은 들기 높이에 있으므로 다음 박스가 핑거에 닿지 않는다 — 사람이 확인한 뒤 resume.

### D. Kp 0 주행 1회 (U9-c)
- 실기 yaml 사본에서 `control.kp_per_s: 0.0` 으로 한 번만 기동(이 회차는 별도 sha, s2 밖). FF 만이라 TCP 가 박스를 못 따라잡고 x 끝까지 간다.
- 확인: x ≈ 600 에서 OUT_OF_REACH/REACH_X_MAX, 그 직전 TRACK z 가 접근 높이(목표 ±2 mm) — 10/10 의 x 600~618 처짐(−4 mm)이 없어야 한다. 특이점 안내(3205/3206) 없음.
- 끝나면 Kp 원래 값으로 되돌리고 sha 가 s2 값으로 돌아왔는지 확인.

### E. OCR 비간섭 (남현지 동행, A 와 함께)
- A 의 각 회차에서 2단계 크롭(LabelCrop stage 2)이 TRACK·DESCEND 동안 들어오는지 box_tracker·label_reader 로그로 센다(남현지).
- 확인: 크롭 수 ≥ 1/회차, belt_servo 주기 33.3 ± 3 ms 유지, A 성공 기준에 영향 없음.

### (선택) 접근 높이에서 박스 치움 1회
- TRACK 중(접근 높이 +40) 박스를 손이 아니라 집게로 들어낸다. 0.5 s 뒤 LOST/BOX_MISSING.

## 4. 판정 · 기록

- 측정이 끝나면 gate_summary 로 표를 만든다(U6-run.md 방법, `--series s2`). C·D·의도 시험은 `--exclude` 로 분모 밖.
- measurements-1012(또는 해당 날짜) 에 남길 것: 2절 고정 조건 표 · A 5행 · B·C·D 결과와 위 확인 항목 수치 · 개방 응답 시간 · 경고 로그 유무.
- 회신: 주관 세션에 결과 요약, PL 에 s2 결과 공유(Slack).

## 5. 실패 시 되돌릴 값

| 증상 | 되돌릴 것 | 단위 |
|---|---|---|
| 정상 하강인데 DEVICE_ERROR/DESCEND_BLIND_TIMEOUT | 펜던트 속도 100 % 확인 → 그래도 나면 실기 yaml cutoff 30 → **10**(U9-a 이전) | U9-a |
| x 400~600 에서 OUT_OF_REACH 가 늘어남 | `reach.x_max_mm` 600 → **620**, `close_time_max_s` 2.3 → **2.1** | U9-c |
| 후퇴가 이상함(핑거가 닿음·안 올라감·RETREAT_TIMEOUT) | 코드를 U9-a 끝 커밋 **f01750c** 로 (후퇴 없음 = 실패 때 파지 높이 정지 — 그때는 실패 뒤 사람이 바로 비상정지·수동 상승) | U9-b |
| 정상 LIFT 경고 반복 | 동작 영향 없음. 펜던트 속도·로봇 상태 확인 후 기록만 | U9-b |

되돌리면 sha 가 바뀌므로 시리즈 번호를 새로(s3) 쓴다.
