# U13 도구 `design/tools/along_extract.py` — DD · 의사코드

HLD(승인 10/13): 순수 파이썬 + numpy, 읽기 전용, 파일 하나에 작은 함수 5묶음(읽기·사건·재구성·합치기·요약). 결정 D1~D6 은 U13-belt-along.md 5절·세션 기록. 부호 **y = TCP − 박스 중심(벨트 방향), + = TCP 하류**.

## 1. 단위·상수

| 이름 | 값 | 뜻 |
|---|---|---|
| 내부 단위 | mm · s · mm/s | 로그의 m·m/s 는 읽을 때 ×1000 |
| `BELT_DIR_DEFAULT` | (0.99992, −0.01292) | 로그 `belt_vel_mps` 가 없을 때의 벨트 방향(voss_config belt.direction_base) |
| `K_LAST_OBS` | 20 | 박스 절편에 쓰는 사각 직전 관측 수 |
| `MIN_OBS` | 5 | 절편에 필요한 최소 관측 |
| `TRACK_SETTLE_S` | 1.5 | 추종 중 박스 속도 맞춤: TRACK 시작 + 1.5 s 이후 관측만 |
| `MIN_TRACK_OBS` | 10 | 추종 중 박스 속도에 필요한 최소 관측 |
| `CONTACT_LEAD_S` | 0.15 | 접촉 ≈ 닫기 응답 rx − 0.15 s (U13 2.3) |
| `--kp` | 1.0 /s | 정렬 띠 꼬리 예측용 Kp(`control.kp_per_s`, 로그에 없음) |

## 2. 함수 목록 (입력 → 출력)

| 묶음 | 함수 | 입력 | 출력 | 실패 때 |
|---|---|---|---|---|
| 읽기 | `load_goals(path)` | JSONL 경로 | {goal8: [행…]} (파일 순서) | 깨진 줄은 건너뜀 |
| 읽기 | `belt_dir(rows)` | 행들 | 단위 벡터 (x, y) | 기본값 |
| 읽기 | `along_mm(p, d)` | [x, y, …] m, 방향 | mm | — |
| 사건 | `find_events(rows)` | 한 goal 행들 | `Events` 또는 None + 이유 | CLOSE rx 없음 / 사각 진입 없음 → 이유 문자열 |
| 재구성 | `obs_series(rows, t_end, d)` | 행들, 사각 진입 시각 | (t[], s[]) box_stamp 중복 제거, valid·사각 아님·t < t_end | 빈 배열 |
| 재구성 | `pose_series(rows, d)` | 행들 | (t[], s[]) pose_stamp 중복 제거 | 빈 배열 |
| 재구성 | `fit_line(t, s)` | 배열 | (기울기, t[-1] 에서의 값, rms) | 점 < 2 → None |
| 재구성 | `box_intercept(t, s, slope)` | 마지막 K 관측, 기울기 | t[-1] 에서의 박스 위치 | — |
| 재구성 | `band_tail_pred(e_align, dv, t_vis, kp)` | mm, mm/s, s, /s | 사각 진입 예측 y = e_ss + (e_align − e_ss)·e^(−kp·t_vis), e_ss = dv/kp | — |
| 재구성 | `reconstruct(rows, ev, refs, kp)` | 행들, 사건, 기준 속도 목록 | dict(회차 1행) | 관측 부족 → y 칸 None |
| 합치기 | `read_manual(path)` | CSV(goal, box, p_front, p_back, b_front, b_back, y, note) | {goal8: dict} — y 없으면 네 점으로 계산 | 칸 비면 None |
| 합치기 | `manual_y(pf, pb, bf, bb)` | mm | (pf + pb)/2 − (bf + bb)/2 | 하나라도 None → None |
| 합치기 | `read_boxes(path)` | CSV(box, ell) | {box: ℓ mm} | — |
| 합치기 | `attach_manual(rec, manual, boxes)` | 회차 dict | y_phys·b_phys(= y_phys − y_con)·ℓ·b0(= b_phys − ℓ) 추가 | 없으면 None |
| 요약 | `ols(x, y)` | 배열 | (절편, 기울기, se 절편, se 기울기, 잔차 sd, n) | n < 3 → None |
| 요약 | `level_table(recs)` | 회차 목록 | FF 수준별 n·평균·sd(y_con, y_phys, b_phys) | — |
| 요약 | `fit_table(recs)` | 회차 목록 | 회귀 3개: y_con ~ Δv(로그), y_phys ~ Δv(손), 사각 진입 y ~ 꼬리 예측(모형 검증 b·k — 사각 뒤 구간은 정의상 Δv·시간이라 검증 대상 아님) | n < 3 → 줄 생략 |
| 출력 | `print_*` · `write_csv(recs, path)` | — | 마크다운 표 · CSV | — |
| 출력 | `main(argv)` | CLI | 종료 코드 0 / 2(입력 오류) | — |

`Events` 필드: `t_track`, `t_descend`, `t_blind`, `t_grasp`, `close_sent`, `close_rx`, `width_mm`, `grip`, `reason`, `grasped`, `ff_mmps`, `config_sha`, `params_sha`, `e_align_mm`(첫 DESCEND 행 −err_along), `align_x_mm`(그 행 TCP x), `start_box_x_mm`(첫 유효 관측 x).

회차 dict 열(출력 순서): goal · ff(cm/s) · config_sha · reason · grasped · start_box_x · align_x · t_vis · blind→rx · close_s · width · v_box_track · v_tcp_blind · dv · e_align · y_blind · y_blind_pred · y_cmd · **y_con** · y_rx (기준 = 회차별 추종 중 박스 속도) · `y_con@<v>` (각 `--v-ref`) · box · ℓ · y_phys · b_phys · b0 · note.

## 3. 에러 경로

| 상황 | 동작 |
|---|---|
| 파일 없음 · 읽을 수 없음 | stderr 한 줄, 종료 코드 2 |
| goal 에 CLOSE rx 없음(LOST·OUT_OF_REACH 등) | 회차표에 reason 만, y 칸 비움, 요약 제외 |
| 사각 진입 없음 | 같음 + 이유 "no blind entry" |
| 관측 < 5 | y 칸 비움, 이유 "obs < 5" |
| 추종 중 관측 < 10 | v_box_track 비움 → y 기준은 `--v-ref` 첫 값, 없으면 비움 |
| 손 CSV 의 goal 이 로그에 없음 | stderr 경고(어느 goal), 계속 |
| grasped false 회차 | 회차표에는 나오고 요약(수준표·회귀)에서는 빠짐 |

## 4. 테스트 목록 (`design/tools/test_along_extract.py`, pytest)

| ID | 내용 | 기대 |
|---|---|---|
| T1 | `along_mm` 부호·크기 | 하류로 +, (1 m, 0) → 999.92 |
| T2 | `fit_line` 정확한 직선 | 기울기·끝값 그대로, rms 0 |
| T3 | `manual_y` | (10+40)/2 − (8+54)/2 = −6.0 / None 전파 |
| T4 | 가짜 goal 재구성 (박스 46.9 mm/s, TCP 는 사각 전 +2.0 mm 하류·사각 뒤 48.0 mm/s, 닫힘 rx 9.3) | y_con = 2.0 + 1.1 × (9.15 − 5.5) = **6.015 ± 0.01**, v_box_track 46.9, e_align·t_vis 값 |
| T5 | CLOSE rx 없는 goal | 이유 문자열, 예외 없음 |
| T6 | `ols` 정확한 직선 | 절편·기울기 복원, 잔차 0 |
| T7 | 손 측정 합치기 | b_phys = y_phys − y_con, b0 = b_phys − ℓ |
| T8 | **10/12 재현**(원본 없으면 skip) | `--v-ref 46.95` 의 y_con 평균: s2 6회 **+6.26**, s3 5회 **+3.02** (±0.05) — Fable recon/check 와 같음 |

colcon test 가 이 파일을 모아도 깨지지 않게: 원본 경로가 없으면 T8 skip, import 는 테스트 파일 위치 기준.

## 5. 의사코드

```
main(argv):
  인자: ticks 파일들, --goals(앞8 쉼표), --manual, --boxes, --v-ref(여러 번), --kp, --csv
  recs = []
  각 파일:
    goals = load_goals(파일)                         # goal8 → 행들
    각 goal8, rows:
      goals 필터에 없으면 건너뜀
      ev, why = find_events(rows)
      rec = reconstruct(rows, ev, refs, kp) if ev else {goal, reason, note: why}
      recs 에 추가
  손 CSV 가 있으면 각 rec 에 attach_manual
  회차표 출력 → 수준표 출력 → 회귀표 출력 → --csv 면 CSV 쓰기

find_events(rows):
  CLOSE = 행들 중 gripper.kind == CLOSE 이고 rx_s 있는 마지막 것   # 재시도면 마지막 시도
  없으면 (None, "no CLOSE rx")
  t_blind = vision_blind 가 false→true 로 바뀐 첫 행의 t_calc_s
  없으면 (None, "no blind entry")
  각 phase 첫 시각, 마지막 행의 reason·grasped, belt_speed_mps×1000, sha 들
  첫 DESCEND 행: e_align = −err_along×1000 (TCP − 박스), align_x = tcp_now x×1000
  첫 유효 관측: start_box_x
  Events 반환

reconstruct(rows, ev, refs, kp):
  d = belt_dir(rows)
  ot, os = obs_series(rows, ev.t_blind, d)
  pt, ps = pose_series(rows, d)
  관측 < MIN_OBS 또는 pose < 2 → y 칸 None
  v_box_track = fit_line(TRACK+1.5 s 뒤 관측) 의 기울기 (관측 ≥ 10)
  v_tcp_blind = fit_line(t_blind ≤ pose ≤ rx) 기울기
  dv = v_tcp_blind − v_box_track
  tl, sl = 마지막 K 관측
  y_at(t, v) = interp(pt, ps, t) − (box_intercept(tl, sl, v) + v·(t − tl[-1]))
  기준 v0 = v_box_track (없으면 refs[0])
  y_cmd, y_con, y_rx = y_at(close_sent, v0), y_at(close_rx − 0.15, v0), y_at(close_rx, v0)
  y_blind = y_at(t_blind, v0)
  y_blind_pred = band_tail_pred(e_align, ff − v0, t_blind − t_descend, kp)
  각 v in refs: y_con@v = y_at(close_rx − 0.15, v)
  회차 dict 반환

fit_table(recs):   (grasped 회차만)
  ① y_con ~ dv            → b, c (로그 좌표)
  ② y_phys ~ dv           → b, c (자 측정, 있으면)
  ③ y_blind ~ 꼬리예측(e_align, FF − v0, t_vis, kp) → b, k (모형 검증; k≈1, b≈0 이면 정렬 띠 꼬리로 설명됨.
     사각 뒤는 TCP=FF·박스=기준 외삽이라 정의상 Δv·시간 → 검증 대상 아님, 세션 code 단계에서 바로잡음)
```

## 6. 2부 변경 (10/14, 1부 재검 #3·#10·#18 + 2부 판정 B)

| 변경 | 내용 | 시험 |
|---|---|---|
| 기준 박스 속도 | 기본 v0 = **설정 묶음(config_sha, params_sha) 중앙값** 추종 중 속도 — 시간상 떨어진 블록(예: 10/13 블록 1·6, A·7)도 한 묶음. U13 6.1 의 '블록'(연속 회차)과 다름. 회차 값은 `v_box_track`·`y_con_run` 진단 열, 중앙값에서 0.2 mm/s 넘게 벗어나면 note. `--v0 run` 이면 옛 동작 | T9 |
| 재시도 회차 | 마지막 행 `attempt` ≥ 2 → note `retry`, 요약(수준표·회귀)에서 뺌 | T10 |
| 회귀 ④⑤ | ④ b_phys ~ Δv (기울기 = −L: 접촉이 가정보다 L 초 이름) · ⑤ b_phys ~ Δv·닫기 시간 (미끄러짐·접촉 지연이면 닫힘이 길수록 커짐) | T11 |
| 접촉 시각 | `--contact rx`(기본, 응답 − 0.15 s — 10/13 기록과 같은 정의) / `--contact sent`(명령 + 1.38 s — 2부 판정 B) | T12 |
| main | 2 패스: 1차로 묶음 중앙값, 2차로 재구성 | 10/13 원본 재현(U13 6.0), 2패스 자동 시험은 없음 |
| 이상치 note | retry 표시에 덧붙임(덮지 않음) | — |

시험 12개(T1~T12), ruff 통과.
