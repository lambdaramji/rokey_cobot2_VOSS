# S2-T14 DD — 하강·들기 사다리꼴 z 속도 프로파일 (상세 설계)

> r3 (10/13): 최종 재검 반영 — N18 위치(test_z_profile), 시험 보강(바닥 상수·trap 노드 시도 로그·sim.launch `_wants_overrides`), 파일 수 정정.
> r2 (10/13): 독립 재검(Fable 5.1) 반영 — 로그 키 4→2, sim 판정 J13 양쪽 경계·J14 0.5 s·예상 시간은 기동 로그 파싱, sim.launch 덮어쓰기 조건, fail_retreat 닫힘 2.2, z_compare 집계 규칙(OK goal 만), "null" 문자열 처리, 시험 N6'·N13'·N19·N20 추가.

- HLD: design/S2T14-hld.md (D1~D7 사용자 승인 10/13). 이 문서는 함수·입출력·단위·키·검사·로그·시험 목록이다.
- 단위: 안에서는 m·m/s·m/s²·s(control.py 머리말 규칙). mm 는 yaml·로그 표시에만.
- **불변 조건 (회귀)**: `z.profile` 이 없거나 `p` 이면 모든 틱의 명령·전이·READY 계산값이 f9f1d28 과 같다. params_sha256 도 같다.

## 1. 파라미터 `z.profile`

| 항목 | 값 |
|---|---|
| 이름·종류 | `z.profile`, `str`, 단위 `-` |
| 필수 | **아니오**(선택 키). 없거나 null 이면 `p` |
| 허용 값 | `p` (P 제어, 지금과 같음) · `trapezoid` (DESCEND·LIFT 만 사다리꼴, HLD D2) |
| 검사 | 문자열이 아니거나 두 값이 아니면 invalid → READY 거부 ("p 또는 trapezoid 이어야 함") |
| params_sha256 | **`p` 와 "키 없음"을 같게** 만든다: `params_digest` 가 `z.profile == "p"` 이면 그 키를 빼고 계산한다. 그래서 10/12 실기 yaml(키 없음)·yaml 3종(`p` 명시)·f9f1d28 의 sha 가 같다. `trapezoid` 이면 키가 들어가 sha 가 달라진다 → 켠·끈 시도의 sha 가 다르다. gate_summary 는 한 시리즈 안에 sha 가 섞이면 "새 시리즈" 경고를 내므로 run.md 에서 s4a(p)·s4b(trapezoid) 로 나눈다(재검 m8) |
| yaml 3종 | `z:` 아래 `profile: p` 한 줄 + 주석(T-L12 키 집합 일치). real.yaml.example 주석: "되돌림 = p 한 줄, 켤 때 trapezoid. 절차 design/S2T14-run.md" |
| sim 덮어쓰기 | sim.launch 인자 `z_profile`(빈 값 = sim yaml), sim_check `--z-profile {p,trapezoid}` |
| "null" 문자열 (재검 m4) | `--params-file` 로 `profile: null` 이 오면 노드 값은 문자열 "null" 이다. check_params 는 None 으로 보지만 `self.values` 는 그대로라 digest 에 `"z.profile":"null"` 이 들어가고 로그도 "null" 이 된다 → `config_from_values` 와 `params_digest` 에서 null 문자열(`_is_null_string`)도 키 없음으로 처리. digest 는 `present.get("z.profile")` 로 읽는다 |

params.py 의 상수와 검사 함수:
- `Z_PROFILE_P = "p"`, `Z_PROFILE_TRAP = "trapezoid"`, `Z_PROFILES = (P, TRAP)` — control.py 가 import 한다(params 가 값의 주인).
- `_z_profile(v) -> str | None`: `v in Z_PROFILES` 가 아니면 이유 문자열.
- 교차 검사 `kp_z × descend_speed ≤ max_acc` 는 **두 모드 모두 유지**(PREPARE·TRACK 은 P, HLD D2). 새 교차 검사는 없다: a_dec = 0.8 × max_acc 라 max_acc 검사(≤ gateway 램프)가 a_dec 도 덮는다.

## 2. control.py

### 2.1 상수 (판단값, HLD D1·D7 계산 근거 — 실측 전 제안값)
| 이름 | 값 | 뜻 |
|---|---|---|
| `TRAP_DECEL_RATIO` | 0.8 | 감속 a_dec = 이 값 × max_acc (명령 감속을 로봇 램프보다 낮게) |
| `TRAP_V_FLOOR_MPS` | 0.005 | 조준점 직전 최소 속도 (멈춰 버리지 않게) |
| `Z_MIN_MARGIN_TRAP_M` | 0.003 | 사다리꼴 모드 파지 목표 ≥ z_min + 이 값 (최악 착지 −2.2 mm, τ100) |
| `Z_LAW_P`·`Z_LAW_TRAP` | "P"·"TRAP" | z_law 반환값(내부용) |
| `TRAP_PHASES` | (DESCEND, LIFT) | 사다리꼴을 쓰는 phase. ~~후퇴 RISING 도 phase 가 LIFT 라 자동 포함(HLD D2 결정의 코드 자취)~~ — **10/13 후속: 후퇴는 z_law 의 retreat 로 뺌(10절)** |

### 2.2 ControlConfig 필드 추가
- `z_profile: str` — `values.get("z.profile") or "p"`
- `a_dec: float` — `TRAP_DECEL_RATIO × a_max` (m/s²)
- 기존 필드는 그대로. config_from_values 는 두 줄만 추가.

### 2.3 함수
| 함수 | 입력 → 출력 | 내용 |
|---|---|---|
| `z_plan` (그대로) | phase, top_z, cfg, hold_z → (목표 z \| None, v_down, v_up) | 바꾸지 않는다(P 회귀 보장) |
| `z_law(phase, cfg)` **새** | → "P" \| "TRAP" | `cfg.z_profile == trapezoid` 이고 phase ∈ TRAP_PHASES 이면 TRAP, 아니면 P |
| `z_speed` (그대로) | 목표, tcp_z, kp_z, v_down, v_up → vz | P 법칙 |
| `z_speed_trap(z_target, tcp_z, a_dec, tol, v_floor, v_down, v_up)` **새** | → vz m/s | e = 목표 − z; 방향 상한 lim = v_up(e>0) / v_down(e<0); lim ≤ 0 또는 e = 0 이면 0. 조준 거리 dd = max(\|e\| − tol, 0); 크기 = min(lim, max(v_floor, √(2·a_dec·dd))); 부호는 e 쪽. 바깥이 min(lim, …) 이라 **v_floor 도 lim 을 넘지 않는다** |
| `z_command(z_t, v_down, v_up, phase, tcp_z, cfg)` **새** | → vz | command 가 이미 부른 z_plan 결과를 받는다(z_plan 을 두 번 부르지 않게, 재검 NIT). 목표 None 이면 0. law = z_law(phase, cfg). P 면 z_speed, TRAP 면 z_speed_trap |
| `command` (수정 1줄 + 반환) | 그대로 | `v[2] = …` 줄을 `z_command` 로 바꾸고 Command 에 z_v_req(= clamp 전 vz)를 넣는다. clamp 는 그대로(가속·속도 상한은 마지막에 한 번) |
| `Command` 필드 추가 | `z_v_req: float \| None = None` | 기본값이 있어 0 명령 생성 4곳은 그대로 |
| `z_move_time_s(dist_m, v, cfg, law)` **새** | → s | law TRAP 이면 `grip.trap_time_s(dist, v, a_max, a_dec, tol)`, 아니면 `grip.descend_time_s(dist, v, a_max, kp_z, tol)` |
| `descend_blind_max_s` | 그대로 서명 | 예상 시간 = `z_move_time_s(…, z_law(DESCEND, cfg))` + 1.0 |
| `lift_max_s` | 그대로 서명 | 예상 = `z_move_time_s(…, z_law(LIFT, cfg))` + 1.0 |
| `retry_need_s` | 그대로 서명 | 재상승은 **PREPARE 법칙** = `z_move_time_s(…, z_law(PREPARE, cfg))`(항상 P, HLD D2·D6) |
| `grasp_floor_blocked` | 그대로 서명 | P: 지금 식(문턱 < z_min + 1 mm). TRAP(DESCEND 법칙이 TRAP): **목표 top+grasp_dz < z_min + 3 mm** 이면 막힘 |
| `grasp_room_need_s(cfg, close_time_max_s)` **새** | → s | 하강 예상(`z_move_time_s(접근→파지, descend_speed, cfg, z_law(DESCEND))`) + 닫힘 상한. belt_servo `_grasp_room_need` 의 계산부를 순수 함수로 옮긴 것(테스트 가능하게). 로그·반환은 노드가 그대로 |

### 2.4 grip.py
| 함수 | 내용 |
|---|---|
| `descend_time_s` (그대로) | P 해석식 |
| `trap_time_s(dist_m, v, a, a_dec, tol)` **새** | 조준 거리 S = dist − tol (≤ 0 이면 0). s_a = v²/2a, s_d = v²/2a_dec. S ≥ s_a + s_d: T = v/a + v/a_dec + (S − s_a − s_d)/v. 아니면 v_p = √(S/(1/2a + 1/2a_dec)), T = v_p/a + v_p/a_dec. 입력 ≤ 0 이면 ValueError(기동 검사가 먼저 막음). 예: (0.059, 0.05, 0.1, 0.08, 0.002) → 1.702 s · (0.069, 0.08, …) → 1.736 s · (0.049, 0.05, …) → 1.502 s. sim(1.60)보다 길다 = 안전 쪽 |

## 3. belt_servo.py

### 3.1 READY 로그 (주관 요청 1 — 다섯 줄을 한눈에)
지금 READY 뒤에 x 여유·사각 상한·재시도·후퇴 상한 4줄이 나온다. 그 앞에 **프로파일 줄 1줄**을 넣고, 4줄은 계산이 프로파일을 따르게 바뀐다(문구 형식 유지):
```
z 프로파일: trapezoid — DESCEND·LIFT 사다리꼴(감속 0.080 m/s², 최소 5 mm/s), PREPARE·TRACK 은 P. 하강 예상 1.70 s · 들기 예상 1.74 s (되돌림: z.profile: p)
x 여유: 하강 예상 1.70 s + 닫힘 2.50 s → 정렬 때 x_max 까지 212 mm 이상 남아야 DESCEND
사각 체류 상한: DESCEND 사각이 2.50 s 넘으면 DEVICE_ERROR (하강 예상 1.50 + 여유 1)
재시도 x 여유: 실패 때 x_max 까지 339 mm 이상 남아야 재시도 (실패 TCP x ≤ 211 mm, 아니면 안전 후퇴)   ← 로그는 정수 반올림, 문서 계산값 210.6
후퇴 체류 상한: 후퇴 상승이 2.74 s 넘으면 DEVICE_ERROR (정상 들기는 경고만)   ← 10/13 후속(10절): 두 모드 3.78 s
```
P 모드 첫 줄: `z 프로파일: p — 모든 phase P(kp_z 1.5). 하강 예상 2.64 s · 들기 예상 2.78 s (켜기: z.profile: trapezoid)`. 나머지 4줄은 지금과 글자까지 같다.
- 함수: `_z_profile_line() -> str` (로그 문구만, 값은 control 함수에서). sim_check 가 이 줄의 "하강 예상 x.xx s · 들기 예상 y.yy s" 를 파싱하므로 형식을 바꾸면 N19 가 깨진다.

### 3.2 틱·시도 로그 키 (주관 요청 2, 재검 m3 로 4키 → 2키)
| 키 | 위치 | 값 |
|---|---|---|
| `z_profile` | TICK·ATTEMPT (공통 값, `_common_values`) | "p" \| "trapezoid" (READY 아니면 null). 시도 레코드만으로 켠·끈 시리즈를 가른다 |
| `z_v_cmd_mps` | TICK (`_control_values`) | clamp **전** z 속도 요구값(법칙이 낸 값). 실제 발행값은 기존 `cmd_vel_mps[2]` — 둘을 비교하면 clamp 가 감속을 잘랐는지 보인다. 목표 z 가 없으면(GRASP·VERIFY·hold_z) null |
- **새 키를 만들지 않는 것 (같은 값이 이미 있다)**: "남은 거리" = 기존 `error_m[2]`(command 에서 목표 z = z_t 라 항상 같음, 목표가 없으면 0). "이 틱의 법칙" = `z_profile` 이 trapezoid 이고 phase 가 DESCEND·LIFT 이면 TRAP, 아니면 P 로 유도된다. 주관 요청의 `z_remaining_m` 은 `error_m[2]` 로 대신한다고 회신에 적는다.
- 스냅샷 경로(0 유지·예외)는 `z_v_cmd_mps` 를 null(SNAPSHOT_NULL_KEYS 에 추가). `z_profile` 은 공통 값이라 채운다.
- `_control_values` 는 `cmd` 가 None 인 틱이 있으므로 `cmd.z_v_req if cmd else None` 으로 쓴다(재검 m10).
- 단계별 시간은 기존 `phase_t_*_s` 6키(U9-c)를 쓴다. 새 키 없음.
- 키 개수: TICK 74 → 76, ATTEMPT 34 → 35 (test_log_schema 의 개수 단언 갱신).
- `Command` 에 `z_v_req: float | None = None` 하나만 추가.

## 4. 비교 도구 `z_compare` (주관 요청 2)
- 모듈 `voss_servo/z_compare.py`, console_scripts `z_compare`(setup.py 한 줄, gate_summary 와 같은 방식). 순수 함수 + 얇은 main. 재검 m7 은 "gate_summary 에 열 추가"를 권했지만, gate_summary 는 G1 게이트 문서 형식이라 건드리지 않고 별도 도구로 둔다(주관이 요청한 스크립트, 함수 5개).
- 입력: attempts jsonl(필수), ticks jsonl(선택 — 착지 z·err_along 용).
- **집계 규칙 (재검 M4)**: 단계 시간·착지·err_along 은 **reason OK 인 goal 만**. 실패 goal 은 건수·reason 별 개수만 센다(실패까지의 시간이 단계 중앙값에 섞이지 않게). 총 시간 = GOAL_END t_calc − **같은 goal 의 첫 ATTEMPT_END 행의 phase_t_prepare_s**(= 첫 시도 PREPARE 진입 = goal 시작. GOAL_END 의 phase_t 는 마지막 시도 값이라 재시도 goal 에서 틀린다). 단계 시간은 마지막 시도 phase_t 로 계산하고 attempts > 1 인 goal 은 표에 따로 표시.
- 출력: z_profile 별 표(마크다운) — 건수, OK 수, 실패 reason 별 수, **단계 시간 중앙값·최소·최대**(PREPARE/TRACK/DESCEND/GRASP/LIFT/VERIFY, 다음 단계 진입 − 이 단계 진입, VERIFY 는 goal 끝 t_calc − 진입), 총 시간, 틱이 있으면 착지 z(GRASP 중 `tcp_pose_m` z 최소, mm)·목표 대비(mm)·GRASP 진입 err_along(mm)·DESCEND clamp 틱 수, 착지 < 80 mm 건수(run.md 되돌림 조건).
- z_profile 이 없는 옛 행(10/12 이전)은 "p" 로 본다.
- 함수: `load_rows(paths)`, `phase_durations(row)`, `landing(goal_ticks)`, `summarize(ends, ticks_by_goal)`, `format_md(stats)`, `main(argv)`.
- run.md 명령 한 줄: `ros2 run voss_servo z_compare <log.dir>/attempts --ticks <log.dir>/ticks` (개인 PC 는 앞에 voss-ros).

## 5. sim.launch.py · sim_check.py
- sim.launch: 인자 `z_profile`(기본 "") → `_write_overrides` 에 `z: {profile: <값>}` 추가(값이 있을 때만). **덮어쓰기 파일을 만드는 조건 `if arg("kp") or arg("max_attempts")` 에 `or arg("z_profile")` 추가**(재검 m5 — 빠지면 trapezoid 가 조용히 무시된다). 시작 로그 줄에 `z_profile=…`.
- sim_check: `--z-profile`(기본 None = sim yaml), `launch_extra(case, z_profile)` 가 `z_profile:=…` 전달.
- **예상 시간은 다시 계산하지 않고 belt_servo 기동 로그를 읽는다**(재검 m6): launch.log 의 `z 프로파일: <이름> — … 하강 예상 x.xx s · 들기 예상 y.yy s` 줄을 정규식으로 파싱 → 노드가 실제로 쓴 값·모드로 판정한다(gateway 줄 파싱과 같은 방식). 줄이 없으면 J14 UNKNOWN. `sim_values` 는 바꾸지 않는다.
- 새 판정(정상 OK 경로가 있는 case — normal·descend_lost 에만):
  - **J13 착지**: `judge_landing(progress)` — 목표 = DESCEND 마지막 틱 `tcp_target_m` z, 착지 = GRASP 틱 `tcp_pose_m` z 최소. PASS 조건: **착지 − 목표 ∈ [−1, +4] mm**(재검 M1: 아래는 지나침, 위는 멈춤 실패·조기 정지를 잡는다). ⚠ dry_run 은 가속을 무시하고(voss_robot doosan.py:84) sim pose_lag 60 으로 착지가 늘 목표 위(+1.9~2.2)에 오므로, J13 은 "법칙이 의도대로 멈추는지" 확인일 뿐 지나침 입증이 아니다. 지나침 근거는 N6'(지연 + 램프 모델 pytest)와 에뮬레이터(검증 단계 필수, run.md 앞에 표).
  - **J14 z 시간**: `judge_z_times(progress, terminal, expect_desc_s, expect_lift_s, margin_s=0.5)` — DESCEND·LIFT 실제 시간(phase_t 차) ≤ 기동 로그 예상 + **0.5 s**(재검 M3: sim 추정 앞섬·dry_run 지연으로 사다리꼴 DESCEND ≈1.77~1.95 s 라 0.3 이면 흔들림). 사다리꼴인데 P 로 돌면 2.6 > 2.2 라 FAIL.
  - 표 끝에 "z 단계 시간" 한 줄(프로파일·DESCEND·LIFT s·착지 mm) 출력 → 두 모드 결과를 나란히 붙여 "사다리꼴 < P" 를 확인한다(완료 기준 3).
- **기존 case 의 두 모드 x 기하 (재검 M2)** — sim 정렬 x ≈ 72(kp 1), 사다리꼴 sim DESCEND ≈1.77 s, P ≈2.7 s:

| case | 값 | P | 사다리꼴 | 문턱 P / 사다리꼴 | 여유 |
|---|---|---|---|---|---|
| `fail_retreat` (닫힘 1.7) | 1차 실패 x ≈ 72 + 48 × (하강 + 닫힘) | ≈ 283 | ≈ 239 | 재시도 x ≤ 165.7 / 210.6 | 117 / **28** (얇음) |
| `fail_retreat` (닫힘 **2.2**로 변경) | 같은 식 | ≈ 307 | ≈ 263 | 같음 | 141 / **52** |
| `retry` (kp 3, 시작 −250, 닫힘 0.5) | 1차 실패 x ≈ −2 + 48 × (하강 + 0.5) | ≈ 152 | ≈ 107 | 재시도 x ≤ 165.7 / 210.6 | 14 / 103 |
| `retry` 재정렬 x | 1차 실패 x + ≈123 | ≈ 275 | ≈ 230 | 정렬 x ≤ 293.3 / 338.3 | 18 / 108 |
→ `fail_retreat` 의 가짜 닫힘 지연을 1.7 → **2.2 s** 로 바꾼다(close_time_max 2.5·gripper_timeout 3.0 안, 기대 결과 GRASP_FAILED·후퇴는 그대로). `retry` 는 P 쪽 여유 14·18 mm 가 기존 값이라 그대로 둔다(S2-T29 에서 이미 sim 확인). 위 표의 x 계산은 순수 시험으로 고정(N19).
- 기존 J1~J12·case 기대 결과(status·reason·phases)는 두 모드 모두 그대로(grasp 8/8).

## 6. 상태 전이·에러 경로
- fsm.py 는 고치지 않는다. 전이 조건(at_grasp_height = TCP ≤ 목표 + tol, at_lift_height = TCP ≥ 목표 − tol)은 두 모드에서 같다.
- DESCEND 사각 체류 상한·후퇴 상한·재시도 여유는 READY 때 한 번 계산(지금처럼). 모드가 goal 중에 바뀌는 일은 없다(파라미터 재설정 없음).
| 상황 | 결과 |
|---|---|
| `z.profile` 오타·숫자 | READY 거부, 로그 `invalid=[z.profile: p 또는 trapezoid 이어야 함]`, 액션 서버 미생성 |
| 사다리꼴인데 파지 목표 < z_min + 3 mm | OUT_OF_REACH / REACH_Z_MIN (P 는 지금 문턱) |
| 로봇이 느림(r < 약 0.48) | 지금처럼 DEVICE_ERROR / DESCEND_BLIND_TIMEOUT (상한 2.50 s) |
| 들기 2.74 s 초과 (10/13 후속: 3.78 s) | 정상 LIFT 는 경고만, 후퇴면 DEVICE_ERROR / RETREAT_TIMEOUT (지금 규칙) |

## 7. 시험 목록 (새 ≥ 8, 기존 371 전부 유지)
| # | 파일 | 시험 | 확인 |
|---|---|---|---|
| N1 | test_control | `z_speed_trap` 멀면 상한(−0.05 / +0.08), 부호 | 포화 |
| N2 | test_control | 감속 구간 크기 = √(2·a_dec·(d−tol)), d 가 줄면 단조 감소 | 단조 |
| N3 | test_control | 조준점 근처 최소 속도 5 mm/s, e = 0 → 0, 반대 방향 상한 0 → 0, floor 가 lim 을 넘지 않음 | 끝 처리 |
| N4 | test_control | `z_law`: trapezoid 에서 DESCEND·LIFT = TRAP, PREPARE·TRACK = P / p 에서 전부 P | 범위 D2 |
| N5 | test_control | **P 회귀**: p 모드 `command` 가 phase·hold_z·retreat 조합 전부에서 옛 식(z_speed 직접)과 같은 벡터 + 30 Hz 폐루프 하강 궤적 틱 단위 동일 | 불변 조건 |
| N6 | test_control | 30 Hz 폐루프(이상 로봇) 사다리꼴 DESCEND: 지나침 ≤ 1 mm(GRASP 램프 포함), 매 틱 \|Δv\| ≤ a·dt + ε, \|v\| ≤ v_max, P 보다 짧음 | 지나침·가속 예산 |
| N7 | test_control | 같은 폐루프 LIFT·후퇴 RISING(xy FF): 시간 < P, 위로 지나침 무해(≤ tol) | LIFT |
| N8 | test_grip | `trap_time_s` 세 예(1.702·1.736·1.502), S ≤ 0 → 0, 입력 ≤ 0 → ValueError | 해석식 |
| N9 | test_control | 해석식 ≥ 폐루프 시간(안전 쪽), 차 ≤ 0.15 s | 해석 vs sim |
| N10 | test_control | trapezoid: descend_blind_max_s 2.50 · lift_max_s 2.736(10/13 후속: 3.785) · retry_need_s(room 4.202) 6.862 · grasp_room_need_s 4.202 / p: 기존 값 그대로 | 종속 수치 D4 |
| N11 | test_control | grasp_floor_blocked: TRAP 목표 z_min+2.9 막힘·+3.1 통과, P 는 기존 경계 | D7 |
| N12 | test_params | z.profile 없음·p·trapezoid → READY / "trap"·1·"" → invalid | 검사 |
| N13 | test_params | digest: 없음 == p ≠ trapezoid | sha 규칙 |
| N14 | test_control | config_from_values: a_dec = 0.08, 기본 profile p | 설정 |
| N15 | test_log_schema | 새 키 2개 TICK(z_profile·z_v_cmd_mps), z_profile ATTEMPT, z_v_cmd_mps 스냅샷 null | 로그 |
| N16 | test_z_compare | phase_durations·landing·summarize·format_md (손으로 만든 행) + 실패 goal 은 단계 시간에서 빠짐·재시도 goal 총 시간은 첫 틱 기준 | 비교 도구 (M4) |
| N17 | test_sim_check | judge_landing([−1, +4] 양쪽)·judge_z_times(margin 0.5) PASS/FAIL/UNKNOWN | sim 판정 |
| N18 | test_z_profile | 사다리꼴에서도 사각 진입(+30) 시각이 P 와 같은 틱(가속 제한 출발). sim_check J12 로도 두 모드 사각 진입 +29.3/+29.4 mm | 비전 D8 |
| N6' | test_control | **지연 + 램프 로봇 모델**(명령 ZOH 를 τ 지연, 로봇 자체 램프 0.1 m/s², 재검 M1) 폐루프 사다리꼴 DESCEND: 착지 − 목표 ≥ −0.5 / −1.0 / −2.5 mm (τ 24 / 60 / 100 ms), P 모드는 ≥ +1 mm. HLD D1 표를 레포 시험으로 고정 | 지나침 근거 |
| N13' | test_params | digest·config: "null" 문자열 = 키 없음 = p | m4 |
| N19 | test_sim_check | `fail_retreat`·`retry` 의 모드별 x 기하(위 5절 표 식)가 문턱과 ≥ 50 / 기존 여유를 유지 + `launch_extra(z_profile=…)` 인자 + `judge_landing` 양쪽 경계 + 기동 로그 예상 시간 파싱 | M2·m5·m6 |
| N20 | test_node | READY 뒤 프로파일 줄이 나오고(p 문구), GOAL_END 행 `z_profile == "p"` | 로그 |
- T-L12(yaml 3종 키 일치)는 기존 시험이 새 키를 자동으로 본다. N15 는 키 개수 단언(76, 35) 갱신 포함.

## 8. 바뀌는 파일
control.py(docstring 예시 값 갱신 포함) · grip.py · params.py(BLIND_DWELL_MARGIN_S 주석 "약 62 %" → 모드별 62/48 % 갱신 포함, 재검 m9) · belt_servo.py(READY 1줄·로그 키·`_grasp_room_need` 가 순수 함수 호출) · log_schema.py · z_compare.py(새) · setup.py(console_scripts 1줄) · sim_check.py(fail_retreat 닫힘 2.2) · launch/sim.launch.py · config/belt_servo.yaml·belt_servo_sim.yaml·belt_servo_real.yaml.example · test 5개 파일(새 test_z_profile·test_z_compare, 추가 test_node·test_sim_check·test_log_schema) · design/S2T14-{pseudo,run}.md. fsm.py·fake_*·gate_summary 는 고치지 않는다.

## 9. 범위 밖 · 후속
- PREPARE·TRACK 사다리꼴/고 kp 혼합(HLD D2, (b) k 3 은 교차 검사 완화 필요) — 별도 과제.
- gate_summary 에 z_profile 열 — 지금은 params_sha 로 구별되므로 z_compare 로 충분. 필요하면 후속.
- DESIGN r8.1 변경점(DEC-04 z 법칙·DEC-17 실패 자세 시간): 최종 회신에 목록으로.

## 10. 후속 (10/13, HLD 12절 — 사용자 선택 (나) 후퇴만 P)

### 10.1 바뀌는 것
| 위치 | 지금 (#30) | 후속 |
|---|---|---|
| `control.z_law(phase, cfg)` | trapezoid 이고 phase ∈ (DESCEND, LIFT) 이면 TRAP | **`z_law(phase, cfg, retreat=False)`**: 위 조건 **이고 retreat 가 아닐 때만** TRAP. 후퇴(phase LIFT + retreat)는 P |
| `control.z_command(z_t, v_down, v_up, phase, tcp_z, cfg)` | z_law(phase, cfg) | 인자 `retreat: bool = False` 를 끝에 추가해 z_law 에 넘긴다 |
| `control.command(..., retreat, hold_z)` | z_command 에 retreat 를 안 넘김 | `z_command(..., cfg, retreat)` — 이미 받는 retreat 를 그대로 전달 (belt_servo 는 고칠 것 없음: belt_servo.py:521 이 `fsm.is_retreat(state)` 를 넘기고 있다) |
| `control.lift_max_s(cfg)` | 예상 = z_move_time_s(…, z_law(LIFT)) → trap 1.736 + 1.0 = 2.736 s | **예상 = z_move_time_s(…, z_law(LIFT, cfg, retreat=True))** = 항상 P 식 → 2.785 + 1.0 = **3.785 s**(두 모드 같음). 이 값은 후퇴 RISING 상한이고, 정상 LIFT 에는 경고에만 쓴다(belt_servo.py:547) → 사다리꼴 정상 LIFT(≈1.6 s)의 경고 문턱이 2.74 → 3.78 s 로 느슨해진다(경고만이라 동작 영향 없음, 지금 P 와 같은 값) |
| `TRAP_PHASES` 주석 | "후퇴 RISING 도 phase 가 LIFT 라 함께 들어간다" | "후퇴는 z_law 의 retreat 인자로 뺀다(HLD 12.1 (나))" |
| belt_servo `_z_profile_line` (trapezoid) | "…, PREPARE·TRACK 은 P." | "…, PREPARE·TRACK·후퇴는 P." (sim_check SERVO_PROFILE 정규식은 `— .*하강 예상` 이라 그대로 맞음) |
| READY "후퇴 체류 상한" 줄 | trap 2.74 s | 두 모드 **3.78 s** |
- 바뀌지 않는 것: p 모드 전부(틱 동일 유지), 사다리꼴 DESCEND·정상 LIFT, x 여유·사각 상한·재시도 상한, 로그 키, params, yaml.

### 10.2 시험 (새·수정)
| # | 파일 | 내용 |
|---|---|---|
| F1 | test_z_profile | `z_law(LIFT, TRAP, retreat=True) == P`, `z_law(LIFT, TRAP) == TRAP`, `z_law(DESCEND, TRAP) == TRAP`. 정의상 retreat 이면 phase 와 무관하게 P(fsm 에서 후퇴는 LIFT 뿐이라 DESCEND·retreat 조합은 단언하지 않음 — 재검 MINOR 로 pseudo 와 맞춤) |
| F2 | test_z_profile | **사다리꼴 후퇴 = P 후퇴 틱 단위 동일**: run_z(TRAP, LIFT, xy_ff=True) 와 run_z(P, …) 의 명령 벡터 전부 `np.array_equal` |
| F3 | test_z_profile (N7 교체) | 도달 직전 틱 z 명령: 정상 LIFT 사다리꼴 ≤ 6 mm/s, 후퇴(두 모드) ≤ 6 mm/s, 정상 LIFT 사다리꼴이 P 보다 0.5 s 넘게 짧음. **+ 진짜 지나침(재검 MINOR)**: run_z 가 LIFT 도달 뒤에도 0 명령으로 20틱 더 돌려(관성) 최고 z 를 잰다 — 지연+램프 τ24 에서 정상 LIFT·후퇴 모두 최고 z ≤ 들기 목표 + 2 mm. 기존 `top <= LIFT_Z + 0.002`(항상 통과) 삭제 |
| F4 | test_z_profile (N10 수정) | `lift_max_s(TRAP) == 3.785`(= P) |
| F5 | test_node (수정) | trap_node `_lift_max_s` = P 식 고정값(READY_ARGS kp_z 2.0 → **3.260**, 현장 kp_z 1.5 면 3.785; 재검 m2 — 같은 함수 재호출 비교 금지), 프로파일 줄에 "후퇴는 P" |
| F6 | test_z_profile (N6′ 추가) | 로봇 도우미에 pose 지연(실제 L, 설정 L_cfg) 추가 — **기록은 서브스텝마다**(틱마다면 실효 지연이 66.7 ms 가 되어 −3.34), **L = 0 이면 현재 z 를 바로 돌려준다**(시각 비교 부동소수 때문에 기존 시험이 바뀌지 않게, 재검 MINOR). 실제 60·설정 0·τ60 → 착지 − 목표 ∈ [−3.5, −2.5] mm(78.8 재현), 실제 60·설정 60·τ60 → ≥ −1.0 mm, **현장형 실제 20·설정 0·τ24 → ≥ 0.0 mm(+0.5)** |
| F7 | test_node (학민 4번) | `sc.parse_profile([f"[belt_servo]: {n._z_profile_line()}"])` **튜플 전체**: p 노드 ("p", 하강 예상, 들기 예상), trap 노드 ("trapezoid", 1.70, 1.74) — 예상값은 control.z_move_time_s 로 계산해 비교(재검 MINOR) |
- 기존 470 은 F3·F4·F5 가 바꾸는 단언 3곳 외 그대로 통과해야 한다(p 모드·사다리꼴 DESCEND 불변).

### 10.3 문서
- test_sim_check.py 의 trapezoid 프로파일 줄 사본(:326 근처)을 새 문구("PREPARE·TRACK·후퇴는 P")로 맞춘다.
- 경고 문턱 완화(사다리꼴 정상 LIFT 2.74 → 3.78 s)는 진단 감도가 떨어진다는 점을 HLD 12.1 에 한 줄.
- run.md: **필수 행 추가 (HLD 12.2·12.5)** — ① trapezoid 면 `z.lift_done_below_mm` 없음/0 ② s4b 체크아웃 해시에 이 후속 커밋 포함 ③ 회차마다 gateway 로그에 `pose_source joint_states → service` · `pose_source joint_states 거부` 없음. 0절 C 행 "HLD D2 실기 확인" → "후퇴는 P(12.1 (나)) — 10/12 와 같은 동작 확인", 5절 "3.78 → 2.74" 정정. 그리고 2절 고정 조건 표에 **필수** 행 "pose 지연 보정: `input.pose_lag_ms 0` + gateway `pose_source:=joint_states` 확인 — 아니면 trapezoid 금지(HLD 12.2: 보정 안 된 60 ms 면 τ100 착지 76.8 < 78)", s4b 다섯 줄의 후퇴 상한 2.74 → 3.78, C(선택)의 RISING 기대 시간 사다리꼴 1.4 s → P 와 같음, 되돌림 조건의 "RETREAT_TIMEOUT" 이유 문구 정리.
- HLD: D2 표의 "안전 후퇴 RISING 적용" 행에 "→ 12.1 (나)로 변경(10/13)" 표시, D4 표 후퇴 상한 행 갱신 표시.
