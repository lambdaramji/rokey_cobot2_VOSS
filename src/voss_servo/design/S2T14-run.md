# S2-T14 실기 절차서 — 사다리꼴 z 프로파일 켜기 전 5회 / 켠 뒤 5회 (T29 리허설 안)

- 작업 S2-T14 · 작성 2026-10-13 · 실행 10/14 T29 리허설과 같은 날(로봇 시간은 09:30 스탠드업에서 남현지와 조정).
- 대상 코드: `feat/S2-T14-voss_servo-z-trapezoid` 끝 커밋(U9 스택 c113534 → S2-T29 f9f1d28 위). 시연 라인(U9 + T29)은 `z.profile: p` 와 같다.
- 근거: [S2T14-hld.md](S2T14-hld.md) D1~D7·10.1 · [S2T14-dd.md](S2T14-dd.md) · [U9-run.md](U9-run.md)(공통 안전·기록 방식).
- **모든 명령은 사람이(박병후) 공용 PC 에서 비상정지 옆에서 실행한다.** Claude 는 실행하지 않는다(CLAUDE.md 규칙 6).
- 이 문서는 계획이다. 측정값은 measurements 에만 적는다. 아래 belt_servo 값(감속 0.08·바닥 5 mm/s·하한 +3 mm)은 **실측 전 제안값**이다.

## 0. 무엇을 확인하나

| # | 시험 | 횟수 | 시리즈 | 성공 기준 |
|---|---|---|---|---|
| A | 기준: `z.profile: p` (시연 라인 그대로) | 5 | **s4a** | 5/5 OK (T29 s4 회귀의 일부) |
| B | 사다리꼴: `z.profile: trapezoid` | 5 (**1회 → 확인 → 4회**) | **s4b** | 5/5 OK · 착지 z ≥ 80 mm · DESCEND·LIFT 가 A 보다 짧음 · err_along 이 A 와 비슷(\|값\| < 3 mm) |
| (선택) C | 사다리꼴 + 폭 밖(90° 박스) 1회 | 1 | 분모 밖 | 후퇴 RISING 이 끝 +48 mm 이상, 핑거가 박스·벨트에 안 닿음 (HLD D2 실기 확인) |

- 기대값(계산·sim, 확정 아님): DESCEND 2.60 → 약 1.6~1.7 s, LIFT 2.73 → 약 1.5~1.7 s, 총 11.4 → 약 9.3 s, 착지(목표 81.8 기준) P +1.8 → 사다리꼴 약 +0.8~+1.4 mm(pytest 지연 16~24 ms +1.2~1.4, 에뮬레이터 +0.83).
- **재시도는 이번 시험에서 일어나지 않는다**: max_attempts 1. 참고로 사다리꼴에서는 재시도 가능한 1차 실패 x 상한이 165.7 → **210.6 mm** 로 커진다. 10/12 현장 1차 실패 x 는 293~328 이라 여전히 밖이다. **T29 에서 max_attempts 를 2 이상으로 켜고 사다리꼴도 켜면, 실패 x ≤ 211 인 경우(정렬이 지금보다 약 80 mm 이른 박스)에 현장 첫 재시도가 실행된다** — 그 조합은 이 절차서 범위 밖이고 따로 sim·절차를 거친다.

## 1. 안전·동행 (하나라도 ❌ 면 시작하지 않는다)

| 항목 | 기준 |
|---|---|
| 동행자 | 2명 이상. 비상정지 대기자는 실행자와 다른 사람(학민 또는 남현지), 손이 비상정지 위에 |
| 펜던트 속도 | **100 %**. 사다리꼴에서는 로봇 실현 속도가 명령의 **약 48 %** 아래면 정상 하강도 DESCEND_BLIND_TIMEOUT(상한 2.50 s)이 난다(HLD D5) |
| gateway | `servo_max_speed_mm_s` 100 · `servo_acc` 100 · z 하한 78 그대로. READY 줄의 "z ≥ 78" 확인 |
| 작업 영역 | 영역 리밋·펜던트 공간 제한 켜짐, `reach.x_max_mm` 550 |
| 벨트 | h250. 증속 금지 |
| "멈춰" | 소프트웨어 정지(SR-NF-09). 위험하면 비상정지가 먼저 |
| 개인 PC 사전 확인 | 이 브랜치 sim_check grasp 두 모드 통과, 에뮬레이터 착지 확인 — 6절 표 |

## 2. 고정 조건 (기록한 뒤 시작)

| 항목 | 값 · 확인 |
|---|---|
| 코드 | `git rev-parse --short HEAD` |
| 실기 yaml | T29 s4 값(close 2.5·x_max 550, FF 는 PL 결정 값) + 이 단위의 `z.profile` 한 줄. `input.pose_lag_ms` 0(gateway `pose_source:=joint_states`) — HLD 계산의 전제 |
| belt_servo 기동 로그 다섯 줄 | 사진/복사로 남긴다. **s4a**: `z 프로파일: p — … 하강 예상 2.64 s · 들기 예상 2.79 s` / x 여유 257 mm / 사각 3.44 s / 재시도 실패 x ≤ 166 mm / 후퇴 3.79 s. **s4b**: `z 프로파일: trapezoid — DESCEND·LIFT 사다리꼴(감속 0.080 m/s², 최소 5 mm/s) … 하강 예상 1.70 s · 들기 예상 1.74 s` / 212 mm / **2.50 s** / ≤ 211 mm / **2.74 s** (벨트 4.8 기준 — FF 4.68 이면 x 값이 조금 바뀐다) |
| params_sha256 | s4a·s4b 두 값을 기록. **s4a 의 sha 는 z.profile 키를 넣기 전과 같다**(p = 키 없음, DD 1절) |
| 박스 | h250 정상 박스, 송장 정방향(FIELD-1012 ④) |

## 3. 절차

켜기·끄기는 **실기 yaml 의 `z.profile` 한 줄 + belt_servo 재기동**이다(파라미터는 기동 때만 읽는다).
```bash
ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=<레포>/data/servo
```

### A. s4a — p 5회
1. yaml `z: profile: p`(또는 키 없음) → 기동 → 기동 로그 첫 줄 `z 프로파일: p` 확인.
2. 정상 운전 5회(G1 과 같은 방식). 회차마다 GOAL_END 를 확인하고 실패 1회면 멈춘다(T29 판단).

### B. s4b — trapezoid 1회 → 확인 → 4회
1. yaml `z: profile: trapezoid` → belt_servo 재기동 → 첫 줄 `z 프로파일: trapezoid` 와 다섯 줄 값 확인.
2. **1회만** 돌리고 바로 틱 로그를 본다(5회를 한꺼번에 돌리지 않는다):
   - GRASP 중 `tcp_pose_m[2]` 최소 = 착지 z → **≥ 80 mm**(목표 81.8, 하한 78)
   - DESCEND 의 `z_v_cmd_mps`(요구) vs `cmd_vel_mps[2]`(발행): 감속 구간에서 발행이 요구를 따라가는지(clamp 틱 수)
   - DESCEND·LIFT 시간(`phase_t_*`)이 A 보다 짧은지
   - 영상: 착지 때 핑거가 벨트에 닿지 않음
3. 괜찮으면 나머지 4회. 회차마다 같은 항목을 `z_compare` 로 본다(4절).

### (선택) C. 폭 밖 1회 (s4b 통과 뒤)
- U9-run C-1 과 같다(박스 90°). 확인: WIDTH_OUT → OPENING → RISING, 끝 TCP z ≥ 윗면 +48, RISING 시간 기록(P 2.27 s → 사다리꼴 sim 약 1.4 s), RETREAT_TIMEOUT 없음.

## 4. 판정 · 기록

```bash
ros2 run voss_servo z_compare <log.dir>/attempts --ticks <log.dir>/ticks
```
- 한 표에 p·trapezoid 열이 나란히 나온다: 단계 6개 시간(중앙값·최소·최대)·총 시간·착지 − 목표·착지 z·착지 < 80 건수·GRASP 진입 err_along·DESCEND clamp 틱 수. 단계 시간·착지는 OK goal 만 센다.
- 게이트 형식 표는 시리즈별로 따로: `gate_summary <attempts> --series s4a` / `--series s4b` (한 시리즈에 sha 가 섞이면 gate_summary 가 경고한다).
- measurements(10/14)에 남길 것: 2절 고정 조건 표, z_compare 표, 기준 대비(10/10 11.4 s·10/12 DESCEND 2.60·LIFT 2.73·착지 +1.75~1.89 mm), C 결과.

## 5. 되돌림 조건 → `z.profile: p` 한 줄 + 재기동

아래 하나라도 나오면 즉시 p 로 되돌리고 시연은 시연 라인(p)으로 간다:
| 조건 | 이유 |
|---|---|
| s4b 실패 1회 (어떤 reason 이든) | 완료 기준 "G1 수준 성공률 유지" |
| 착지 z < 80 mm | 하한 78 여유 2 mm 미만 (HLD D1·D7) |
| DESCEND_BLIND_TIMEOUT 또는 RETREAT_TIMEOUT 1회 | 상한이 짧아졌으므로(3.44 → 2.50, 3.78 → 2.74) 새로 생길 수 있는 오판 신호. 펜던트 속도(실현 속도 48 % 아래)부터 확인 |
| goal 결과 OUT_OF_REACH / cause REACH_Z_MIN | 사다리꼴은 파지 목표 ≥ 하한 + 3 mm(81.0) 를 요구 — 목표 81.8 이 바뀐 것(박스·캘리브레이션) |
| 핑거가 벨트에 닿음(영상) · err_along \|값\| ≥ 3 mm 반복 | 착지·정렬 품질 저하 |
- 되돌리면 sha 가 s4a 값으로 돌아오는지 확인. 코드는 그대로 둔다(p 는 f9f1d28 과 틱 단위로 같다 — 시험 N5).

## 6. 개인 PC 사전 확인 결과 (실기 전 첨부)

| 확인 | 결과 |
|---|---|
| pytest (지연 + 램프 로봇 모델 N6′) | 사다리꼴 착지 − 목표: 지연 16 ms +1.42 · 24 ms +1.16 · 60 ms −0.08 · 100 ms −2.01 mm / P +1.83 · +1.84 · +1.72 · +1.61 mm (*계산*) |
| sim_check grasp, p (10/13, 도메인 76) | **8/8** 종료 코드 0. normal: DESCEND 2.70 · LIFT 2.87 s · 착지 − 목표 +2.13 mm. fail_retreat 실패 x 314 → 후퇴 |
| sim_check grasp, trapezoid | **8/8** 종료 코드 0. normal: DESCEND **1.73** · LIFT **1.80** s · 착지 +2.08 mm. fail_retreat 실패 x 267(재시도 문턱 210.6, 여유 56) → 후퇴. ⚠ dry_run 은 가속을 무시해 착지가 늘 목표 위 — 지나침 근거 아님 |
| 에뮬레이터(두산 가상 모드, gateway real + rg2_dry_run, pose_source joint_states, pose_lag 0) | 두 모드 모두 OK(U-E 판정 8/8, 두산 알람 0, 거부·자름 0). **p: DESCEND 2.73 · LIFT 2.90 s · 착지 83.6 mm(목표 +1.84 — 10/12 실측 +1.75~1.89 와 같음)** / **trapezoid: DESCEND 1.67 · LIFT 1.80 s · 착지 82.6 mm(목표 +0.83, 하한 78 까지 4.6)**. TRACK·총 시간 차이는 goal 시점의 박스 위치 차(우연)라 비교하지 않는다. 이 PC 의 에뮬레이터 주기·지연은 의미 없음 — 움직임·착지만 본다. **10/13 15:23 각 1회 실행값**, 같은 날 16:0x 독립 재현(Opus 서브에이전트, 도메인 78, 에뮬레이터 재기동 뒤 깨끗한 쌍): p DESCEND 2.73 · LIFT 2.87 s · 착지 +1.84 mm / trapezoid 1.73 · 1.77 s · **+0.88 mm(82.7 mm)** — 두 실행 일치, z_compare 값과 직접 추출값 일치. 재현 중 호스트 과부하(load 20+)로 gateway watchdog 이 goal 도중 로봇을 세운 오염 실행 4회는 제외(이 PC 의 에뮬레이터 특성, U-E-run §4 ①). 재현: `ROS_DOMAIN_ID=<대역> voss-dsr-virtual-up` → U-E 의 `emu_case.sh normal`(도메인·워크트리·`pose_source:=joint_states`·`PARAMS=<pose_lag 0 + z.profile 사본 yaml>` 로 고친 사본) → `voss-dsr-virtual-down` |
