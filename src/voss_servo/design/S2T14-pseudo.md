# S2-T14 의사코드 (pseudo code)

DD: design/S2T14-dd.md (10/13 승인, r2 = 독립 재검 반영). r2 에서 바뀐 곳은 ★ 표시. 함수마다 한국어 의사코드. `→` 는 반환, `#` 는 이유.
불변 조건: z.profile 이 없거나 p 이면 결과가 f9f1d28 과 같다(N5).

## 1. params.py

```
상수 Z_PROFILE_P = "p", Z_PROFILE_TRAP = "trapezoid", Z_PROFILES = (P, TRAP)

함수 _z_profile(v):                       # 값 검사 (모양 검사 "str" 를 통과한 뒤 불린다)
    v 가 Z_PROFILES 안이면 → None
    아니면 → "p 또는 trapezoid 이어야 함"

PARAM_SPECS 에 한 줄 추가 (z.height_tol_mm 바로 뒤):
    ParamSpec("z.profile", "str", "-", required=False, check=_z_profile)
    # 선택 키: 없으면 None → check_params 가 missing 에 넣지 않는다 (spec.required 가 False)

함수 params_digest(values):               # 바뀌는 곳 한 줄
    present = 값이 None 아니고 DIGEST_EXCLUDE 밖인 키들
    ★ present.get("z.profile") 가 "p" 이거나 null 문자열("null"·"~")이면 그 키를 지운다
      # "p"·"null"·"키 없음" 을 같은 sha 로 (DD 1절, 재검 m4)
    (나머지 그대로: 이름순 JSON → sha256)
```

## 2. grip.py

```
함수 trap_time_s(dist_m, v, a, a_dec, tol):     # 사다리꼴 예상 시간 (HLD D4 식)
    v·a·a_dec·tol 중 하나라도 ≤ 0 이면 ValueError   # 기동 검사가 먼저 막는다 (방어)
    S = dist_m − tol                              # 조준 거리: "목표 + tol" 까지 (D1 (a))
    S ≤ 0 이면 → 0.0
    s_a = v² / (2a)                               # 0 → v 가속에 드는 거리
    s_d = v² / (2·a_dec)                          # v → 0 감속에 드는 거리
    만약 s_a + s_d ≤ S:                            # 최고 속도에 닿는다 (사다리꼴)
        → v/a + v/a_dec + (S − s_a − s_d)/v       # 가속 + 감속 + 등속
    아니면:                                        # 못 닿는다 (삼각형)
        v_p = √( S / (1/(2a) + 1/(2·a_dec)) )     # 가속·감속 거리 합 = S 가 되는 꼭짓점 속도
        → v_p/a + v_p/a_dec
```

## 3. control.py

```
상수 TRAP_DECEL_RATIO = 0.8, TRAP_V_FLOOR_MPS = 0.005, Z_MIN_MARGIN_TRAP_M = 0.003
상수 Z_LAW_P = "P", Z_LAW_TRAP = "TRAP", TRAP_PHASES = (fsm.DESCEND, fsm.LIFT)

ControlConfig 에 필드 2개: z_profile(str), a_dec(float)

config_from_values(values):               # 두 줄 추가
    raw = values.get("z.profile")
    ★ z_profile = raw 가 None·null 문자열이면 "p", 아니면 raw   # None·없음·"null" → p (재검 m4)
    a_dec     = TRAP_DECEL_RATIO × max_acc

함수 z_law(phase, cfg):
    cfg.z_profile == trapezoid 이고 phase ∈ TRAP_PHASES 이면 → "TRAP"
    → "P"                                          # PREPARE·TRACK 은 항상 P (HLD D2)

함수 z_speed_trap(z_target, tcp_z, a_dec, tol, v_floor, v_down, v_up):
    e = z_target − tcp_z                           # 양수 = 올라가야 함
    e == 0 이면 → 0.0
    lim = v_up (e > 0) / v_down (e < 0)            # 그 방향 속도 상한
    lim ≤ 0 이면 → 0.0                              # 예: DESCEND 중 위로는 안 간다
    dd = max(|e| − tol, 0)                         # 조준점 = 목표 + tol 까지 남은 거리
    크기 = min(lim, max(v_floor, √(2·a_dec·dd)))   # 감속 곡선, 바닥 5 mm/s, 상한 lim
    → 부호(e) × 크기

함수 z_command(z_t, v_down, v_up, phase, tcp_z, cfg):   # ★ → vz (z_plan 결과를 받는다)
    z_t 가 None 이면 → 0.0                          # GRASP·VERIFY·hold_z: z 0
    z_law(phase, cfg) == P   → z_speed(z_t, tcp_z, cfg.kp_z, v_down, v_up)          # 지금 식 그대로
    z_law(phase, cfg) == TRAP → z_speed_trap(z_t, tcp_z, cfg.a_dec, cfg.height_tol_m,
                                             TRAP_V_FLOOR_MPS, v_down, v_up)

★ Command 에 필드 1개 추가(기본 None): z_v_req

command(...):                              # 바뀌는 곳
    (위쪽 0 명령 경로 4개 그대로 — 새 필드는 기본 None)
    z_t, v_down, v_up = z_plan(...)          # 지금처럼 한 번만 부른다
    ...target·e·xy 계산 그대로...
    vz = 0.0 if z_t is None else z_command(z_t, v_down, v_up, phase, tcp z, cfg)
    v[2] = vz                                # 옛 줄 "v[2] = 0 if z_t is None else z_speed(...)" 대체
    v, clamped = clamp(...)                  # 그대로
    → Command(v, rule, target, e, clamped, z_v_req = vz if z_t is not None else None)
    # p 모드: z_command 가 옛 줄과 같은 z_speed 를 같은 인자로 부른다 → 벡터 비트까지 동일 (N5)

함수 z_move_time_s(dist_m, v, cfg, law):
    law == TRAP → grip.trap_time_s(dist_m, v, cfg.a_max, cfg.a_dec, cfg.height_tol_m)
    → grip.descend_time_s(dist_m, v, cfg.a_max, cfg.kp_z, cfg.height_tol_m)

함수 grasp_room_need_s(cfg, close_time_max_s):     # belt_servo 에서 옮김
    dist = approach_dz − grasp_dz
    → z_move_time_s(dist, cfg.descend_speed, cfg, z_law(DESCEND, cfg)) + close_time_max_s

descend_blind_max_s(cutoff_m, cfg):        # expect 계산만 바뀜
    expect = z_move_time_s(cutoff_m − grasp_dz, descend_speed, cfg, z_law(DESCEND, cfg))
    → expect + BLIND_DWELL_MARGIN_S

lift_max_s(cfg):
    expect = z_move_time_s(lift_dz − grasp_dz, lift_speed, cfg, z_law(LIFT, cfg))
    → expect + BLIND_DWELL_MARGIN_S

retry_need_s(cfg, room_need_s):
    rise = z_move_time_s(approach_dz − grasp_dz, lift_speed, cfg, z_law(PREPARE, cfg))  # 항상 P
    → rise + room_need_s

grasp_floor_blocked(top_z, cfg):
    z_law(DESCEND, cfg) == TRAP 이면:
        → (top_z + grasp_dz) < z_min + Z_MIN_MARGIN_TRAP_M      # 목표가 하한 + 3 mm 아래 (D7)
    → (top_z + grasp_dz + height_tol) < z_min + Z_MIN_MARGIN_M  # 지금 식
```

## 4. log_schema.py

```
★ TICK_FIELDS: "cmd_rule" 다음에 "z_v_cmd_mps" 추가, 공통 값 구역("config_version" 앞)에 "z_profile" 추가  (74 → 76)
ATTEMPT_FIELDS: "params_sha256" 앞에 "z_profile" 추가      (34 → 35, 부분집합 assert 는 그대로 통과)
```

## 5. belt_servo.py

```
★ SNAPSHOT_NULL_KEYS 에 "z_v_cmd_mps" 추가   # 0 유지·예외 행은 null

_control_values(ctx, ev):                  # ★ 한 키 추가
    "z_v_cmd_mps": _as_float(cmd.z_v_req) if cmd else None     # cmd 가 None 인 틱이 있다 (재검 m10)
    # 남은 거리는 기존 error_m[2], 법칙은 z_profile + phase 로 유도 (재검 m3)

_common_values():                          # 한 키 추가
    "z_profile": self._ctrl.z_profile (READY 아니면 None)

__init__ READY 계산 순서 (지금 순서 앞에 한 줄):
    self._ctrl = config_from_values(...)
    self.get_logger().info(self._z_profile_line())          # 새 첫 줄
    self._room_need_s = self._grasp_room_need() ... (그대로)

_z_profile_line():                         # 문구만, 값은 control 함수에서
    desc = z_move_time_s(접근→파지, descend_speed, cfg, z_law(DESCEND))
    lift = z_move_time_s(파지→들기, lift_speed, cfg, z_law(LIFT))
    trapezoid → "z 프로파일: trapezoid — DESCEND·LIFT 사다리꼴(감속 {a_dec:.3f} m/s², 최소 5 mm/s),
                 PREPARE·TRACK 은 P. 하강 예상 {desc:.2f} s · 들기 예상 {lift:.2f} s (되돌림: z.profile: p)"
    p         → "z 프로파일: p — 모든 phase P(kp_z {kp_z:g}). 하강 예상 {desc:.2f} s ·
                 들기 예상 {lift:.2f} s (켜기: z.profile: trapezoid)"

_grasp_room_need():                        # 계산부만 순수 함수로
    need_s = control.grasp_room_need_s(cfg, close_time_max)
    t_desc = need_s − close_time_max
    (로그 문구·need_m 계산·반환 그대로)
```

## 6. z_compare.py (새)

```
PHASES = (PREPARE, TRACK, DESCEND, GRASP, LIFT, VERIFY)

함수 load_rows(paths):  jsonl 파일·폴더 → dict 목록 (gate_summary 의 입력 규칙 재사용)
함수 goal_ends(rows):   event == GOAL_END 인 행만
함수 first_start(rows, goal_id):   ★ 같은 goal 의 첫 ATTEMPT_END 행 phase_t_prepare_s (없으면 GOAL_END 의 값)

함수 phase_durations(row):                 # GOAL_END 한 행 → 단계별 시간 (마지막 시도 기준)
    t = [row[phase_t_<단계>_s] for 단계 in PHASES]
    각 단계 i: 다음으로 값이 있는 단계의 진입 시각 − t[i]   (마지막 단계는 row.t_calc_s − t[i])
    진입 안 한 단계 → None

함수 landing(goal_ticks):                  # → (착지 z mm, 목표 z mm) 또는 (None, None)
    목표 = DESCEND 마지막 틱 tcp_target_m z
    착지 = GRASP 틱들의 tcp_pose_m z 최소
    → (착지×1000, 목표×1000)

함수 summarize(rows, ticks_by_goal):        # → {z_profile: Stats}
    z_profile 이 None 인 옛 행은 "p" 로 본다      # 10/12 이전 로그 = P
    프로파일마다:
        건수, reason 별 수
        ★ OK goal 만: 단계별 [중앙값, 최소, 최대], 착지 z 최소·중앙값, 목표 대비, 착지 < 80 mm 건수,
                      GRASP 진입 틱 err_along_m 중앙값(mm), DESCEND clamped 틱 수 합
        ★ 총 시간 = GOAL_END.t_calc_s − first_start(goal)   (OK goal 만)
        ★ attempts > 1 인 goal 수 (따로 표시)

함수 format_md(stats):  마크다운 표 (행 = 항목, 열 = p · trapezoid · 차이)
함수 main(argv):  인자 inputs(+), --ticks(선택) → print(format_md(...)), 종료 코드 0
```

## 7. sim.launch.py · sim_check.py

```
sim.launch: args 에 ("z_profile", "", "z.profile 덮어쓰기 (비우면 sim yaml)") 추가
    ★ 덮어쓰기 조건: if arg("kp") or arg("max_attempts") or arg("z_profile")   (재검 m5)
    _write_overrides(folder, kp, max_attempts, z_profile=""):
        z_profile 값이 있으면 params["z"] = {"profile": z_profile}
    시작 로그 줄에 "z_profile=…" 추가

sim_check:
    parse_args: --z-profile (choices p·trapezoid, 기본 None)
    launch_extra(case, z_profile=None): z_profile 값이 있으면 "z_profile:=<값>" 추가
    ★ CASES["fail_retreat"].grip_close_s 1.7 → 2.2        # 사다리꼴에서 재시도 문턱 여유 28 → 52 mm (재검 M2)
    ★ SERVO_PROFILE = 정규식 r"z 프로파일: (\w+) — .* 하강 예상 ([\d.]+) s · 들기 예상 ([\d.]+) s"
    ★ 함수 parse_profile(lines):  → (이름, 하강 예상, 들기 예상) 또는 None    # 노드가 실제로 쓴 값 (재검 m6)
    함수 judge_landing(progress):                       # J13
        목표 = DESCEND 마지막 틱 tcp_target_m z, 착지 = GRASP 틱 tcp_pose_m z 최소
        없으면 UNKNOWN
        ★ → PASS if −1 mm ≤ 착지 − 목표 ≤ +4 mm     (양쪽 경계, 재검 M1)  detail: 착지·목표·차이 mm
    함수 judge_z_times(progress, terminal, expect, margin_s=0.5):   # J14 ★ 0.5 (재검 M3)
        expect 가 None(프로파일 줄 없음)이면 UNKNOWN
        DESCEND 시간 = phase_t_grasp − phase_t_descend, LIFT = phase_t_verify − phase_t_lift (마지막 틱 값)
        하나라도 없으면 UNKNOWN
        → PASS if DESCEND ≤ 하강 예상 + 0.5 이고 LIFT ≤ 들기 예상 + 0.5
    judge_case: case.name ∈ (normal, descend_lost) 이면 J13·J14 추가 (expect = parse_profile(launch.log))
    main 끝: 프로파일 이름과 normal case 의 "DESCEND x.xx s · LIFT x.xx s · 착지 ±x.x mm" 한 줄 출력
```

## 8. yaml 3종

```
z: 아래 height_tol_mm 다음 줄
    profile: p    # P 제어(기본, 시연 라인). trapezoid = DESCEND·LIFT 사다리꼴(S2-T14). 되돌림은 p 한 줄.
                  # 선택 키 — 없어도 p. 절차·되돌림 조건: design/S2T14-run.md
```

## 9. 시험 (DD 7절 N1~N20 의 구현 메모)

```
폐루프 도우미 (test_control 안, 순수): run_z(cfg, phase, z0, top, n_ticks, robot)
    매 틱: control.command 가 쓰는 것과 같은 z_command + clamp, TCP 추정 = 로봇 위치(외삽 없음)
    전이: DESCEND 는 at_grasp(TCP ≤ 목표 + tol) 뒤 GRASP 로 바꿔 z 요구 0 → clamp 램프로 멈출 때까지 진행
    로봇 모델:
        ideal         : 위치 += 명령 × dt
        ★ delay_ramp(τ): 명령을 τ 만큼 늦게 받고(대기열), 자기 속도를 0.1 m/s² 램프로 명령 쪽으로 바꾼다
                          (HLD 0.3 의 B 모델, 재검 M1 — /tmp 의 zsim.py 를 레포 시험으로 옮김)
    반환: 시각·실제 z·명령 목록, 착지 = GRASP 동안 실제 z 최소
N5 회귀: 같은 입력으로 (a) 새 command (b) 옛 식을 재현한 참조 함수(지금 command 본문 복사 — z_speed 사용)
         를 phase 6종 × hold_z × retreat × visible 조합과 하강 폐루프 90틱에서 비교 → 모든 성분 정확히 같음
★ N6': delay_ramp τ 0.024/0.060/0.100 → 사다리꼴 착지 − 목표 ≥ −0.5/−1.0/−2.5 mm, P 는 ≥ +1 mm
★ N19: fail_retreat·retry 의 x 기하 = 정렬 x + 48 mm/s × (모드별 하강 + 닫힘) 을 DD 5절 표 값으로 단언
N9: trap_time_s ≥ 폐루프(ideal) 도달 시간, 차 ≤ 0.15 s (DESCEND 59 mm·LIFT 69 mm)
```

## 10. 후속 (DD 10절, 10/13 — 후퇴만 P)

```
control.py
    TRAP_PHASES 주석: "후퇴는 z_law 의 retreat 인자로 뺀다 (HLD 12.1 (나))"

    함수 z_law(phase, cfg, retreat=False):
        cfg.z_profile == trapezoid 이고 phase ∈ TRAP_PHASES 이고 retreat 가 아니면 → "TRAP"
        → "P"                       # 후퇴 RISING 은 10/12 실기로 확인된 P 그대로

    함수 z_command(z_t, v_down, v_up, phase, tcp_z, cfg, retreat=False):
        z_t 가 None 이면 → 0.0
        z_law(phase, cfg, retreat) == TRAP → z_speed_trap(...)      # 그대로
        → z_speed(...)                                              # 그대로

    command(...):                    # 한 줄
        vz = z_command(z_t, v_down, v_up, phase, tcp z, cfg, retreat)   # 받은 retreat 를 넘긴다

    lift_max_s(cfg):
        expect = z_move_time_s(lift_dz − grasp_dz, lift_speed, cfg, z_law(LIFT, cfg, retreat=True))  # 항상 P
        → expect + BLIND_DWELL_MARGIN_S          # 두 모드 3.785 s (docstring 예시도 정정)

belt_servo.py
    _z_profile_line (trapezoid 문구): "…), PREPARE·TRACK·후퇴는 P. {times} (되돌림: z.profile: p)"
```

```
test_z_profile.py
    Robot 에 pose 지연 추가:
        __init__(..., pose_lag=0.0)        # 실제 pose 지연 (추정이 이만큼 옛 위치를 본다)
        step 의 서브스텝마다 (시각, z) 기록을 남긴다    ★ 틱마다면 실효 지연이 66.7 ms 가 된다 (재검)
        seen(t):
            pose_lag == 0 이면 → 현재 z                  ★ 시각 비교 부동소수로 기존 시험이 바뀌지 않게
            → 시각 t − pose_lag 이하 마지막 기록 z (처음엔 z0)
    run_z(cfg, ..., robot, cfg_lag=0.0):
        추정 z = robot.seen(t) + 마지막 명령 z × cfg_lag      # control.tcp_now 와 같은 규칙 (지평 = 설정 lag)
        (robot.pose_lag 0 · cfg_lag 0 이면 지금과 같음 — 기존 시험 결과 불변)

    F1 test_z_law_retreat_is_p:
        z_law(LIFT, TRAP, retreat=True) == P, z_law(LIFT, TRAP) == TRAP, z_law(DESCEND, TRAP) == TRAP
        # 정의상 retreat 이면 phase 와 무관하게 P. fsm 에서 후퇴는 LIFT 뿐이라 DESCEND·retreat 조합은 단언하지 않는다
    F2 test_trap_retreat_equals_p_retreat:
        a = run_z(TRAP, LIFT, TARGET, xy_ff=True), b = run_z(P, LIFT, TARGET, xy_ff=True)
        len 같고 모든 cmds[i].vel 이 np.array_equal
    run_z(..., coast_ticks=0):  ★ LIFT 도달 뒤 0 명령(VERIFY·후퇴 끝과 같음)으로 coast_ticks 틱 더 돌려 최고 z 를 잰다
        반환 top = 도달 뒤까지 포함한 실제 z 최고값 (coast_ticks 0 이면 지금처럼 도달까지)
    F3 (N7 교체) test_lift_tail_command:
        정상 LIFT: trap = run_z(TRAP, LIFT, TARGET), p = run_z(P, …)
            |trap.cmds[-1].vel[2]| ≤ 0.006, trap.t_reach < p.t_reach − 0.5, dv_max ≤ a·dt
        후퇴: 두 모드 |cmds[-1].vel[2]| ≤ 0.006
        (cmds[-1] = 도달 판정 직전 틱의 발행 명령 — run_z 가 도달 틱에서 끊으므로)
        ★ 진짜 지나침: 지연+램프 τ24, coast_ticks 20 → 정상 LIFT·후퇴 모두 top ≤ LIFT_Z + 0.002
    F4 (N10 수정): lift_max_s(TRAP) == 3.785
    F6 (N6′ 추가) test_trap_landing_uncorrected_pose_lag:
        실제 60 ms · 설정 0 · τ60 · 램프 → 착지 − 목표 ∈ [−3.5, −2.5] mm   # HLD 12.2 의 78.8 (−3.0)
        실제 60 ms · 설정 60 · τ60 · 램프 → 착지 − 목표 ≥ −1.0 mm           # 보정되면 −0.5
        ★ 현장형: 실제 20 ms · 설정 0 · τ24 · 램프 → 착지 − 목표 ≥ 0.0 mm     # +0.5 (HLD 12.2)

test_node.py
    F5: trap_node _lift_max_s == 3.785, _z_profile_line() 에 "PREPARE·TRACK·후퇴는 P"
    F7 ★ 튜플 전체: p 노드 parse_profile([f"[belt_servo]: {line}"]) == ("p", round(하강 예상, 2), round(들기 예상, 2))
        trap 노드 == ("trapezoid", 1.70, 1.74) — 예상값은 control.z_move_time_s 로 계산
        (from voss_servo import sim_check as sc)
```
- 1D 하네스의 pose 지연은 2축 분석(fu_sim.py)과 수치가 조금 다를 수 있다 → F6 범위는 구현 뒤 실제 값을 보고 HLD 12.2 와 함께 적는다(범위를 결과에 맞춰 넓히지 않는다 — 다르면 원인부터 본다).
