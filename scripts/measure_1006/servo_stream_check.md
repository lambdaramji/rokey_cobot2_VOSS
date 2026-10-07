# #3 서보 스트리밍 현장 절차서 (U7 · T25 #34, 박병후)

`docs/measurements-1006.md` #3 의 "실측 필요" 칸과 pending #8 을 채우기 위한 실로봇 시험 절차.
소스 조사 결과와 근거(파일:줄)는 measurements #3 절, 결정 초안은 `docs/adr/0009-doosan-servo-command-path.md`.

확인 순서: **① speedl_stream → ② servol_stream → (둘 다 안 되면) ③ move_line ASYNC**.
"토픽이 있다"는 #55(김학민 10/07)로 확인됐다. 여기서는 **명령을 실제로 받아 움직이는지, 끊기면 멈추는지**를 잰다.

| 파일 | 로봇을 움직이나 |
|---|---|
| `servo_stream_inspect.py` | 아니오. 그래프(토픽·QoS)와 조회 서비스만 |
| `servo_stream_trial.py speedl / servol` | **예.** 한 축 ±10 mm 이내, 5 mm/s 이하 |
| `servo_stream_trial.py analyze <CSV>` | 아니오. 저장된 CSV 요약 |

## 0. 안전 (모두 확인 전에는 시작하지 않는다)
- [ ] **2인 1조**: 실행 = 박병후, 비상정지 앞 = 김학민(브링업 담당 #41). 실행자는 키보드, 동행자는 비상정지에서 손을 떼지 않는다.
- [ ] **robot_gateway·다른 두산 호출 프로그램을 모두 끈다** (CLAUDE.md 규칙 3, measure_1006 README §0: 동시에 부르면 `dsr_controller2` 가 멈춘다). 스크립트도 `/voss` 노드가 보이면 거부한다.
- [ ] **속도·이동 제한**(스크립트 머리 상수, 바꾸려면 PR): 5 mm/s 이하, 시작점에서 한 방향 10 mm 이하, TF 편차 14 mm 넘으면 자동 소프트 정지. 끊김 시험은 0.6 s 움직이고 1.0 s 관찰한다(계속 가도 +5 mm).
- [ ] **작업 영역**: 시작 TCP x 가 −77 ~ 608 mm(#6 추종 구간 안쪽 30 mm). 시작 z ≥ `--z-min`. **`--z-min` 값은 학민과 현장에서 정해 아래 기록 칸에 적는다** (제안: 관측 자세 높이에서 시작하고 `--z-min 300`).
- [ ] 시작 자세 제안: 관측 자세(홈, 플랜지 `[-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]`, measure_1006 README). 벨트·트레이와 떨어져 있고 x 이동 ±10 mm 로 닿을 것이 없다. 학민 확인.
- [ ] 펜던트: AUTONOMOUS 모드, 상태 STANDBY, 속도 오버라이드 낮게(펜던트 기본값 유지). 그리퍼는 열어 둔다(움직이지 않음).
- [ ] "멈춰" = 터미널 Ctrl+C(스크립트가 move_stop 소프트 정지를 부른다). 반응이 없으면 **즉시 비상정지**.

## 1. 준비 (공용 PC, 5분)
- 공용 PC doosan-robot2 커밋이 `31750d6`(measurements #2)인지 확인한다. 소스 줄 번호는 개인 PC 사본(`4d5657f`) 기준이므로 다르면 #3 절에 "공용 PC 커밋으로 재확인" 결과를 적는다.
```bash
git -C ~/cobot2_ws/src/doosan-robot2 log -1 --oneline
```
- 레포를 이 브랜치로 맞춘다.
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS && git fetch && git switch docs/34-voss_servo-servo-stream-check
```

## 2. 브링업 (터미널 1, 사람이 실행)
```bash
source ~/cobot2_ws/install/setup.bash && ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100 port:=12345 model:=m0609
```
- 로그에 `Configured and activated dsr_controller2` 가 보일 때까지 기다린다. 브링업 패키지 위치는 #55 김학민 댓글(공용 PC 는 `~/cobot2_ws`, 별칭 `s`).

## 3. 읽기 전용 점검 (터미널 2) — 로봇 안 움직임
```bash
source ~/cobot2_ws/install/setup.bash && cd ~/voss_ws/src/rokey_cobot2_VOSS/scripts/measure_1006 && python3 servo_stream_inspect.py
```
확인할 것 → 기록 칸 A
- speedl_stream · servol_stream: `OK`, 구독자 `/dsr01/dsr_controller2` 의 QoS(예상 reliable, depth 10 / 20)
- robot_gateway: `없음`
- system=real, mode=AUTONOMOUS, state=STANDBY, TCP posx
- joint_states Hz, TF base_link→link_6 OK (OK 가 아니면 시험 중 편차 감시가 시간 제한에만 의존한다 — 진행 여부를 학민과 정한다)

## 4. speedl 시험 (터미널 2) — ⚠ 로봇이 움직임
로봇을 시작 자세로 옮긴 뒤(펜던트) 실행한다. 스크립트가 시작 posx·계획을 보여 주고 `MOVE` 입력을 기다린다.
```bash
python3 servo_stream_trial.py speedl --z-min <학민과 정한 값>
```
- 결과 요약을 기록 칸 B 에 옮긴다. 정상이라면: 10 mm 나갔다 돌아오고, 끊김 시험에서 짧게 움직인 뒤 멈춘 다음 원위치로 돌아온다.
- **브링업 로그(터미널 1)의 알람**을 기록 칸 C 에 옮긴다. 에뮬레이터에서는 아래 두 개가 나왔다. 실로봇에서도 같은지가 핵심이다.
  - 1216 `[SpeedL] Time adjusted automatically considering acceleration limit you set. (t= 0.0000-> 0.2500 [s] ...)` → `time` 은 가속(도달) 시간이고 가속도 한계가 우선한다
  - 1215 `[SpeedL] speedl() generates time-out error if it is called for 0.1 [sec]` → 0.1 s 안에 다음 명령이 없으면 컨트롤러가 멈춘다 (끊김 시험 때)
- 위가 정상일 때만 이어서 `time`·`acc` 를 바꿔 본다. 동작이 다르면(예: 한 틱만 움직이고 멈춤, 끊겨도 계속 감) 그대로 기록하고 멈춘다.
```bash
python3 servo_stream_trial.py speedl --z-min <값> --time 0.1
```
```bash
python3 servo_stream_trial.py speedl --z-min <값> --acc 100
```

## 5. servol 시험 — speedl 결과와 비교 (또는 speedl 이 안 될 때)
```bash
python3 servo_stream_trial.py servol --z-min <값>
```
- servol 의 `vel`·`acc` 는 상한(10 mm/s · 20 mm/s²)이다. 목표 위치는 스크립트가 시작점 + v·Δt 로 만든다.
- ⚠ 관측 자세는 ry ≈ −179° 로 ZYZ 표현이 퇴화하는 근처다. 에뮬레이터(ry = 0)에서 이전 표현의 rx·rz 로 목표를 보낸 1회는 움직이지 않았다(measurements #3 주의점 9). 스크립트는 시작 직전 posx 를 목표 자세로 쓰지만, 움직이지 않으면 그 사실과 알람을 기록하고 다시 한 번만 돌린다.
- servol 은 끊어도 마지막 목표점까지는 간다(에뮬레이터 1.8 mm). `drift_after_cut_mm` 는 "따라잡기"이지 폭주가 아니다.

## 6. 둘 다 움직이지 않으면
- 멈추고 기록한다. `move_line` ASYNC(③) 시험은 이 절차에 없다 — 결과를 주관 세션·학민과 보고 별도 단위로 정한다.
- 브링업 로그의 경고·에러(`dsr_controller2`, `Drfl`)를 그대로 복사해 기록 칸 C 에 붙인다.

## 7. 끝
- 터미널 2 결과의 `저장:` 경로(`~/voss_ws/measure_1006_data/servo_stream_*.csv`, `*.posx.csv`)를 확인한다. 데이터는 레포에 커밋하지 않는다(값만 measurements #3 에).
- 브링업은 사람이 Ctrl+C 로 내린다. robot_gateway 를 다시 켤 때는 학민에게 알린다.

---

## 기록 칸 (현장에서 채운 뒤 measurements #3 의 "2부 실측 기록" 표로 옮긴다)
- 날짜·시각: / 실행: 박병후 / 비상정지: / `--z-min`: / 시작 posx:
- 공용 PC doosan-robot2 커밋: / DRCF: 

**A. 점검 (inspect)**
| 항목 | 값 |
|---|---|
| speedl 구독 QoS | |
| servol 구독 QoS | |
| joint_states Hz / TF | |

**B. 시험 (trial 요약 그대로)**
| 항목 | speedl time=0 | speedl time=0.1 | speedl acc=100 | servol |
|---|---|---|---|---|
| 움직였나 (out/back) | | | | |
| `start_latency_ms` | | | | |
| `out_travel_mm_actual` / 지령 10 | | | | |
| `back_travel_mm_actual` | | | | |
| `cut_travel_mm_actual` / 지령 3 | | | | |
| `stop_after_cut_ms` · `still_moving_at_silent_end` | | | | |
| 알람 1215 / 1216 | | | | |
| `drift_after_cut_mm` | | | | |
| `cmd_period_ms_mean` / `max` | | | | |

**C. 로그·관찰** (경고·에러, 소리·떨림, 펜던트 표시)
