# S2-T18 J6 회전 파지 — Pseudo code · r2

[S2T18-dd.md](S2T18-dd.md)(사용자 승인 10/14, 12절 r1 변경 포함)의 함수별 의사코드. 베이스 = main e8547a7 + T16(68cc35f).
`rotate.py`·`fsm.py`·`control.py`·`params.py`·`log_schema.py` 는 ROS·시계·파일을 쓰지 않는다. 시각은 노드 시계 초.
내부 각은 rad, 파라미터·로그는 deg. 최종은 코드가 기준이다.

- 상태: **pseudo r2 — 사용자 승인(10/14), real code 반영** — r1 = Opus 재검(필수 10·권장 12) 반영(11절), r2 = Fable 5.1 전 과정 독립 재검(16건 중 15건 채택, 세션이 재현·확인) 반영(12절).
- 이름 규칙: 상태·원인 문자열은 rotate.py 상수(대문자). ψ(psi) = 공구 yaw, θ = 박스 yaw, Δ = 벨트 기준 상대각.
- 분기 규칙: 모든 "상태별" 블록은 **위에서부터 첫 매치 한 줄만 실행하고 그 상태 블록을 끝낸다**(r1-17).
- 0 지령 규칙(r1-10): **law 가 낸 값만 rate_limit 을 거친다. STOPPING·대기·PHASE 이탈·종료의 0 은 즉시 0** — 선속도 clamp 의 "0 은 즉시"(control.py:301)와 같고, 감속 램프는 gateway speedl acc 가 한다.

---

## 1. rotate.py — 상수·자료형

```text
# 하위 상태
COLLECT, ROTATING, SETTLING, DONE, SKIP, STOPPING, FALLBACK, RETURNING, RETURNED   # OFF 없음 — off 면 ctx.rot = None (r2-14)
READY_STATES = {SKIP, DONE, FALLBACK, RETURNING, RETURNED}   # 이 상태면 TRACK→DESCEND 허용
HOLD_STATES  = {ROTATING, STOPPING}                                # 이 상태면 z 하한(시야 보험)

# 원인 (rot_cause 로그)
NO_FIELD, NO_POSE_YAW, START_ROTATED, NO_YAW, SPREAD, DOWNSTREAM, SMALL, OUT_OF_RANGE,
TIMEOUT, STALL, PHASE, INTERNAL, SETTLE_DRIFT, SETTLE_TIMEOUT, ACC_MISMATCH,
RETURN_STALL, RETURN_TIMEOUT, RETURN_INCOMPLETE

# 고정 상수 (판단값, 파라미터로 열지 않음)
TILT_MAX = 5°                 # 공구가 아래를 본다고 믿는 한계
STALL_MIN = 1°                # stall_s 동안 이만큼도 못 돌면 STALL
ACC_RATIO = 0.6               # 측정 α 가 설정의 이 비율 아래면 불일치
ACC_FLOOR = 5°/s²             # α_eff 하한
ACC_RAMP_TICKS = 2            # 지령이 rate_limit 으로 막혀 오르는 틱이 이만큼 이어질 때만 α 를 잰다 (r1-6)
ACC_SLOPE_DT = 0.1 s          # α = 두 측정 각속도의 기울기, 두 표본 간격 하한 (r2-1: 지연이 상쇄된다)
DEC_RATIO = 0.8               # α_dec = 0.8 × α_eff
TIMEOUT_K, TIMEOUT_ADD = 1.5, 0.5 s
STILL_TICKS = 2               # 정지 확인 연속 틱
YAW_HOLD_MAX = 0.15 s         # yaw 값이 이보다 오래 그대로면 회전 정지로 본다 (r2-5: service 갱신 0.1 s 보다 길게)
SETTLE_CAP = 1.0 s            # SETTLING 상한 — 넘으면 DONE + SETTLE_TIMEOUT (r2-7)
POSE_FRESH_FOR_ZERO = 0.05 s  # 그 판단은 pose 메시지가 이 안에 왔을 때만 (끊김과 구별, r1-14)
YAW_SAME = 1e-6 rad           # 같은 yaw 값으로 보는 차 (wrap_pi 로 비교, r1-22)

RotCfg (frozen): deadband, min_rot, max_rot, tol, start_tol (rad) · n_min, buffer_n (int) · r_min ·
                 decide_max_s · home_fixed (rad | None) · w_max, w_floor (rad/s) · alpha (rad/s²) ·
                 hold_dz, return_min_dz (m) · settle_s, stall_s · still (rad/s) · belt_yaw (rad) ·
                 lag_s, extrap_max_s

RotState (frozen):
    state, cause="", t_goal=0.0, home=None,
    box_target=None, target=None, delta=None, n=None, rbar=None,            # 결정 (r1-20 box_target)
    t_start=None, psi_start=None, t_expected=None, t_done=None,             # 앞 회전
    alpha_eff=None, ramp_n=0, acc_warned=False, acc_t1=None, acc_w1=None,   # α 기울기 첫 표본 (r2-1)
    still_since=None, settle_start=None, still_n=0, settle_drift=False,
    ret_start=None, ret_psi_start=None, ret_expected=None, ret_tried=False  # 되돌리기 전용 (r1-7·19)

RotInputs (frozen): now, phase, retreat, hold_z, yaws(목록 rad), has_field(True | False | None), home_ref(rad | None),
                    psi_raw, psi_est, tilt, pose_ok, w_meas, wz_prev, dt, err_along, tcp_z, top_z

RotOut (frozen): state(RotState), wz(rad/s), ready(bool), z_floor(m | None), warn(str | None)
```

## 2. rotate.py — 작은 함수

```text
fold_half(a):                              # (−π/2, π/2] — tracker_logic.fold_yaw 와 같은 규칙
    y ← fmod(a, π)
    y ≤ −π/2 이면 y += π
    y >  π/2 이면 y −= π
    반환 y

wrap_pi(a):                                # (−π, π]
    y ← fmod(a + π, 2π);  y ≤ 0 이면 y += 2π      # 결과 (0, 2π]
    반환 y − π

tool_yaw(q = x, y, z, w):
    n ← √(x²+y²+z²+w²);  n 이 0 이거나 유한하지 않으면 None
    x,y,z,w 를 n 으로 나눔
    r00 ← 1 − 2(y²+z²);  r10 ← 2(xy + zw);  r22 ← 1 − 2(x²+y²)
    yaw ← atan2(r10, r00)                  # 공구 x 축의 베이스 XY 각
    tilt ← acos(clip(−r22, −1, 1))         # 공구 z 축이 −Z(아래)에서 기운 각
    반환 (yaw, tilt)
    # 시험용 역함수: down_quat(ψ) = (x = cos ψ/2, y = sin ψ/2, z = 0, w = 0) = Rz(ψ)·Rx(π) (r1-9)

aggregate(yaws):
    yaws 가 비면 None
    c ← [cos 2θ], s ← [sin 2θ]
    target ← fold_half(½ · atan2(median(s), median(c)))
    rbar ← ‖(mean(c), mean(s))‖
    반환 (target, rbar, len(yaws))

expected_time(delta, w_max, alpha):
    θ ← |delta|
    θ ≥ w_max²/alpha 이면 θ/w_max + w_max/alpha, 아니면 2·√(θ/alpha)

law(err, w_max, w_floor, alpha_eff, tol):  # √ 감속
    |err| ≤ tol 이면 0
    v ← √(2 · DEC_RATIO·alpha_eff · (|err| − tol))
    반환 sign(err) · min(w_max, max(w_floor, v))

rate_limit(w, w_prev, alpha, dt):          # alpha 는 언제나 설정값 cfg.alpha (r1-5)
    step ← alpha · dt
    반환 w_prev + clip(w − w_prev, −step, +step)

yaw_estimate(value, value_stamp, lag, wz_prev, now, extrap_max):   # control.tcp_now 와 같은 모양
    h ← min(max(now − value_stamp, 0) + lag, extrap_max)
    반환 value + wz_prev · h

omega_meas(prev, cur, now, pose_rx_age):   # prev·cur = (yaw, 그 값이 처음 온 stamp)
    cur 없음 → None
    now − cur.stamp > YAW_HOLD_MAX:
        pose_rx_age ≤ POSE_FRESH_FOR_ZERO 이면 0     # 메시지는 오는데 값이 그대로 = 정지
        아니면 None                                   # 메시지 자체가 끊김 = 모름 (r1-14)
    prev 없음 → None
    dt ← cur.stamp − prev.stamp;  dt ≤ 0 또는 dt > YAW_HOLD_MAX → None
    반환 wrap_pi(cur.yaw − prev.yaw) / dt

alpha_slope(t1, w1, t2, w2):               # 두 측정 각속도의 기울기 (r2-1) — 명령·측정 지연이 상쇄된다
    t2 − t1 < ACC_SLOPE_DT → None
    반환 (|w2| − |w1|) / (t2 − t1)
```

## 3. rotate.py — 결정 전 검사·decide

```text
pre_checks(inp, rs, cfg) → cause | None | "WAIT":          # 프레임 수와 무관하게 매 COLLECT 틱 먼저 (r1-12)
    inp.has_field is False                         → NO_FIELD
    inp.has_field is None                          → "WAIT"        # 박스 메시지를 아직 못 받음
    inp.psi_raw 없음 또는 tilt > TILT_MAX           → NO_POSE_YAW
    inp.home_ref 있고 |wrap_pi(psi_raw − home_ref)| > start_tol → START_ROTATED
        # home_ref = 고정값(rotate.home_tool_yaw_deg) 또는 노드 기동 뒤 첫 goal 의 ψ0 (r2-3)
    → None

decide(agg, inp, rs, cfg) → (verdict, cause, delta, box_target):   # agg.n ≥ n_min 일 때만
    agg.rbar < r_min                              → SKIP, SPREAD
    inp.err_along 있고 > 0                         → SKIP, DOWNSTREAM      # 하류 = + (control.py:201)
    delta ← fold_half(agg.target − cfg.belt_yaw)
    |delta| ≤ max(deadband, min_rot)              → SKIP, SMALL
    |delta| > max_rot                             → SKIP, OUT_OF_RANGE
    → ROTATE, "", delta, agg.target
```

## 4. rotate.py — rot_step

```text
rot_step(rs, inp, cfg) → RotOut:
    rs.home 없음 이면 rs.home ← inp.home_ref 있으면 그것, 아니면 inp.psi_raw (없으면 None 그대로)   # r2-3
    want ← None   # None = 즉시 0 (rate_limit 없음). 숫자 = law 출력 (rate_limit 을 거침)
    warn ← None

    COLLECT:                                       # 첫 매치 한 줄
        c ← pre_checks(inp, rs, cfg)
        c 가 원인                → rs ← SKIP(c)
        now − t_goal > decide_max_s 이고 (c == "WAIT" 또는 len(yaws) < n_min) → rs ← SKIP(NO_YAW)
        c == "WAIT" 또는 len(yaws) < n_min → (계속 모음)
        그 밖:
            agg ← aggregate(yaws);  v, cause, delta, box ← decide(agg, inp, rs, cfg)
            rs.n, rs.rbar, rs.box_target ← agg.n, agg.rbar, box
            v == SKIP   → rs ← SKIP(cause)
            v == ROTATE → rs ← ROTATING(target = home + delta, delta, psi_start = psi_raw, t_start = now,
                                         alpha_eff = cfg.alpha, ramp_n = 0,
                                         t_expected = expected_time(delta, w_max, cfg.alpha))
                          want ← law(wrap_pi(target − psi_est), …, alpha_eff)

    ROTATING:                                      # 첫 매치 한 줄
        phase ∉ {PREPARE, TRACK}                    → rs ← STOPPING(PHASE)
        pose_ok 아님                                → rs ← STOPPING(NO_POSE_YAW)
        el ← now − t_start
        el > TIMEOUT_K·expected_time(delta, w_max, cfg.alpha) + TIMEOUT_ADD → rs ← STOPPING(TIMEOUT)   # cfg.alpha (r2-8)
        el ≥ stall_s 이고 |wrap_pi(psi_raw − psi_start)| < STALL_MIN       → rs ← STOPPING(STALL)
        e ← wrap_pi(target − psi_est)
        |e| ≤ tol 이고 w_meas 있고 |w_meas| < still → rs ← SETTLING(still_since = now, settle_start = now)
        그 밖:
            # α 감시 — 지령이 rate_limit 에 막혀 오르는 틱이 이어질 때만 (√ 감속 구간 제외, r1-6)
            rising ← |law(e,…)| > |wz_prev| + ½·cfg.alpha·dt     # 다음 지령이 한도까지 오른다
            ramp_n ← ramp_n + 1 if rising else 0
            acc_warned 아님 이고 ramp_n ≥ ACC_RAMP_TICKS 이고 w_meas 있음:          # r2-1 두 표본 기울기
                acc_t1 없음 → acc_t1, acc_w1 ← now, w_meas
                아니면 a ← alpha_slope(acc_t1, acc_w1, now, w_meas)
                       a 있고 a < ACC_RATIO·cfg.alpha → alpha_eff ← max(a, ACC_FLOOR), acc_warned ← 참, warn ← ACC_MISMATCH
            rising 아님 → acc_t1, acc_w1 ← None   # 램프가 끊기면 표본을 버린다
            want ← law(e, w_max, w_floor, alpha_eff, tol)

    SETTLING:
        now − settle_start ≥ SETTLE_CAP → rs ← DONE(cause SETTLE_TIMEOUT), t_done ← now   # r2-7 상한
        w_meas 없음 또는 |w_meas| ≥ still → still_since ← now
        아니고 now − still_since ≥ settle_s:
            |wrap_pi(target − psi_raw)| > tol → settle_drift ← 참 (쫓지 않음)
            rs ← DONE, t_done ← now

    STOPPING:
        w_meas 있고 |w_meas| < still → still_n += 1, 아니면 still_n ← 0
        still_n ≥ STILL_TICKS → rs ← FALLBACK (cause 유지), t_done ← now (t_start 있고 t_done 이 None 일 때만, r2-6)

    DONE · FALLBACK:                               # SKIP 은 되돌리지 않는다 (r1-18)
        ret_tried 아님 이고 return_ok(inp, cfg) 이고 home 있고 psi_raw 있고 |wrap_pi(home − psi_raw)| > tol:
            rs ← RETURNING(ret_start = now, ret_psi_start = psi_raw, ret_tried = 참,
                           ret_expected = expected_time(wrap_pi(home − psi_raw), w_max, cfg.alpha))
            want ← law(wrap_pi(home − psi_est), …)

    RETURNING:                                     # 첫 매치 한 줄
        return_ok 아님                              → (상태 유지, want None = 즉시 0, 대기)
        pose_ok 아님                                → rs ← STOPPING(NO_POSE_YAW)
        el ← now − ret_start
        el > TIMEOUT_K·ret_expected + TIMEOUT_ADD   → rs ← STOPPING(RETURN_TIMEOUT)
        el ≥ stall_s 이고 |wrap_pi(psi_raw − ret_psi_start)| < STALL_MIN → rs ← STOPPING(RETURN_STALL)
        e ← wrap_pi(home − psi_est)
        |e| ≤ tol                                   → rs ← RETURNED
        그 밖 → want ← law(e, …)
        # STOPPING 뒤 FALLBACK 이 되어도 ret_tried 가 참이라 다시 되돌리지 않는다 (r1-19)

    SKIP · RETURNED · OFF: (want None)

    wz ← 0 if want is None else rate_limit(want, inp.wz_prev, cfg.alpha, inp.dt)
    ready ← rs.state ∈ READY_STATES
    z_floor ← (rs.state ∈ HOLD_STATES 이고 phase ∈ {PREPARE, TRACK} 이고 top_z 있음) 이면 top_z + hold_dz, 아니면 None
    반환 RotOut(rs, wz, ready, z_floor, warn)

return_ok(inp, cfg):                          # LIFT·VERIFY (r2-4: 사다리꼴 LIFT 만으로는 45° 회귀 시간이 모자람)
    lift ← (phase == LIFT 이고 (retreat 아님 또는 hold_z 아님)) 또는 phase == VERIFY
    high ← tcp_z·top_z 있고 tcp_z ≥ top_z + return_min_dz
    반환 lift 이고 high

end_cause(rs, psi_raw, tol):                  # goal 끝 틱 로그용
    rs.state == RETURNING → RETURN_INCOMPLETE
    rs.state ∈ {DONE, FALLBACK, STOPPING} 이고 home·psi_raw 있고 |wrap_pi(home − psi_raw)| > tol → RETURN_INCOMPLETE
    아니면 rs.cause (settle_drift 이고 cause 비었으면 SETTLE_DRIFT)
```

## 5. fsm.py · control.py

```text
fsm.TickEvent 끝에:  rot_ready: bool = True       # 기본 = 회전 없음과 같다
fsm._advance:        TRACK 이고 ev.aligned 이고 ev.rot_ready 이면 → (기존 grasp_room 검사) → DESCEND

control.command(…, z_floor = None):
    기존 z_t, v_down, v_up ← z_plan(…)
    z_t 있고 z_floor 있으면 z_t ← max(z_t, z_floor)
```

## 6. params.py · launch_params · yaml

```text
_kind_error 에 kind "bool": isinstance(v, bool) (r1-2)
PARAM_SPECS 끝에 (모두 required=False):
    rotate.enable (bool) · rotate.home_tool_yaw_deg (float — yaml 에 적지 않는 선택 키, 없으면 goal 수락 때 공구 yaw)
    rotate.deadband_deg, min_deg, max_deg, r_min, decide_max_s, start_tol_deg, omega_max_dps, alpha_dps2,
    tol_deg, omega_floor_dps, hold_dz_mm, settle_s, stall_s, still_dps, return_min_dz_mm (float)
    rotate.n_min, buffer_n (int)
ROTATE_REQUIRED = 위 목록에서 enable·home_tool_yaw_deg 를 뺀 것

rotate_on(values): values.get("rotate.enable") is True          # bool True 만 (r1-20)

check_params:
    rotate_on 이면 ROTATE_REQUIRED 중 None 인 키를 missing 에
_cross_checks (rotate_on 이고 관련 키가 bad 아님 일 때만):
    hold_dz_mm ≤ z.approach_above_top_mm             → invalid("rotate.hold_dz_mm", "접근 높이보다 커야 함")
    hold_dz_mm < z.vision_cutoff_above_top_mm + 5    → invalid("rotate.hold_dz_mm", "사각 높이 + 5 이상")
    not (deadband ≤ min_deg < max_deg ≤ 90)           → invalid("rotate.min_deg", "deadband ≤ min < max ≤ 90")
    n_min > buffer_n                                   → invalid("rotate.n_min", "buffer_n 이하")
    tol_deg ≥ deadband_deg                             → invalid("rotate.tol_deg", "데드밴드보다 작아야 함")
    input.pose_lag_ms ≠ 0                              → invalid("input.pose_lag_ms",
                                                         "rotate 는 pose_source joint_states(pose_lag 0) 전제")
params_digest:
    rotate_on(values) 아니면 "rotate." 로 시작하는 키를 present 에서 모두 뺀다
rot_cfg_from_values(values, belt_dir_xy, pose_lag_s, extrap_max_s) → RotCfg (deg → rad, mm → m)
rotate_line(values) → "rotate off" | "rotate on · deadband … · max … · ω … · α … · home goal|<deg>"

yaml (T-L12 키 집합 일치, r1-4):
    config/belt_servo.yaml · belt_servo_real.yaml.example: rotate: {enable: false, 나머지 null} (home 키는 적지 않음)
    config/belt_servo_sim.yaml: rotate: {enable: false, 제안값 전부} (home 키 없음 → T-L13 dropped 없음)
```

## 7. log_schema.py

```text
ROT_KEYS = (rot_state, rot_cause, yaw_target_deg, rot_delta_deg, tool_yaw_deg, tool_yaw_est_deg,
            rot_err_deg, wz_cmd_dps, wz_meas_dps, rot_n, rot_rbar, rot_time_s)
TICK_FIELDS 끝 쪽(진단 키 뒤)에 ROT_KEYS
ATTEMPT_FIELDS 에: rot_state, rot_cause, rot_delta_deg, rot_time_s
```

## 8. belt_servo.py

```text
__init__ (READY 뒤):
    self._rot_on ← params.rotate_on(values)
    self._rot_cfg ← rot_cfg_from_values(…) if _rot_on else None
    self._yaw_hist ← {}            # track_id → deque(maxlen buffer_n) of (stamp, yaw)
    self._yaw_field ← None          # BoxTrack 에 yaw 필드가 있나 (None = 아직 모름)
    self._yaw_value, self._yaw_prev ← None, None   # (yaw, 그 값이 처음 온 stamp)
    self._home_ref ← 고정값(rad) if rotate.home_tool_yaw_deg 있으면, 아니면 None   # r2-3
    self._tilt ← None
    self._last_wz ← 0.0
    기동 로그에 rotate_line 한 줄

_on_box(msg) 끝에 (기존 처리 뒤, 같은 try 안):
    self._yaw_field ← hasattr(msg, "yaw_valid")
    _rot_on 이고 yaw_field 이고 msg.yaw_valid 이고 valid(같은 메시지의 position 판정) 이고 yaw 유한:
        _yaw_hist[track_id] (없으면 deque 생성) 에 (stamp_s(msg.stamp), float(msg.yaw_base)) 추가
        (같은 트랙에서 stamp 가 앞 것 이하면 넣지 않음)

_prune_boxes: 지우는 트랙의 _yaw_hist 도 지움

_on_pose(msg) 끝에:
    _rot_on 이면:
        r ← rotate.tool_yaw(쿼터니언)
        r 없음 → _tilt ← None (값은 그대로)
        r 있음 → yaw, tilt ← r; _tilt ← tilt
                  _yaw_value 있고 |wrap_pi(yaw − _yaw_value.yaw)| < YAW_SAME → 그대로(처음 stamp 유지)
                  아니면 _yaw_prev ← _yaw_value; _yaw_value ← (yaw, pose stamp)

goal 수락 (GoalCtx 생성 자리):
    _rot_on 이고 _home_ref 없음 이고 _yaw_value 있고 tilt ≤ TILT_MAX:
        _home_ref ← _yaw_value.yaw; 로그 "회전 기준 공구 yaw = … (노드 기동 뒤 첫 goal)"   # r2-3
    ctx.rot ← RotState(COLLECT, t_goal = now) if _rot_on else None
    ctx.rot_dead ← False;  ctx.rot_still_n ← 0;  ctx.wz ← 0.0;  ctx.rot_floor ← None

_build_event 끝 (TickEvent 만들기 전):
    ready, ctx.rot_floor ← True, None
    _rot_on 이고 ctx.rot 있음:
        ctx.rot_dead 이면:                                 # 예외로 끈 goal (r1-8)
            ctx.wz ← 0;  w ← omega_meas(…)
            ctx.rot_still_n ← ctx.rot_still_n + 1 if (w 있고 |w| < still) else 0
            ready ← ctx.rot_still_n ≥ STILL_TICKS          # 노드가 정지를 확인하면 진행 허용
        아니면:
            try:
                out ← rotate.rot_step(ctx.rot, self._rot_inputs(ctx, ctx.geo, now), cfg)
                ctx.rot, ctx.wz, ready, ctx.rot_floor ← out.state, out.wz, out.ready, out.z_floor
                out.warn 있으면 경고 1회 ("회전 가속이 설정보다 느림 α_meas … → 그 값으로 제동")
            except 예외:
                에러 로그 1회 ("회전 예외 — 이 goal 의 회전을 끄고 정지 확인 뒤 진행")
                ctx.rot_dead ← 참; ctx.rot ← replace(ctx.rot, cause = INTERNAL); ctx.wz ← 0; ready ← False
    TickEvent(…, rot_ready = ready)

_rot_inputs(ctx, geo, now):                              # geo None 이면 기하 값 None (r1-8)
    hist ← _yaw_hist 의 내 트랙 yaw 목록 (COLLECT 일 때만, 아니면 빈 목록)
    psi_raw, stamp ← _yaw_value (없으면 None)
    psi_est ← yaw_estimate(psi_raw, stamp, lag, _last_wz, now, extrap_max) (psi_raw 있을 때)
    pose_rx_age ← now − self._pose[1] (pose 없으면 ∞)
    pose_ok ← psi_raw 있음 이고 _tilt ≤ TILT_MAX 이고 pose_rx_age ≤ input.pose_extrap_max (r1-13)
    w_meas ← omega_meas(_yaw_prev, _yaw_value, now, pose_rx_age)
    dt ← control.effective_dt(ctx.last_calc, now, dt_nominal)        # 이번 틱 dt (r1-16)
    반환 RotInputs(now, ctx.state.phase, is_retreat(ctx.state), ctx.state.hold_z, hist, _yaw_field, _home_ref,
                   psi_raw, psi_est, _tilt, pose_ok, w_meas, _last_wz, dt,
                   geo.err_along if geo else None, geo.tcp[2] if geo else None, geo.top_z if geo else None)

_tick_goal (fsm.step 다음, command 전):
    tr.terminal 또는 tr.state.stopping 이면 ctx.wz ← 0          # 즉시 0
    ctx.cmd ← control.command(…, z_floor = ctx.rot_floor)
    t_pub ← self._publish(vel, ctx.wz)

_publish(vel, wz = 0.0):
    (기존) linear ← vel
    msg.twist.angular.z ← wz                 # 기본 0 — 0 유지·_safe_zero·예외 경로는 인자를 주지 않는다
    self._last_wz ← wz

_tick_values: _rot_values(ctx, tr) 를 합친다
_rot_values(ctx, tr):
    _rot_on 아님 또는 ctx.rot 없음 → ROT_KEYS 전부 None
    rs ← ctx.rot
    cause ← end_cause(rs, psi_raw, tol) if tr.terminal else (rs.cause 또는 이번 틱 warn)
    rot_time_s ← rs.t_done − rs.t_start (둘 다 있을 때, 앞 회전만)
    yaw_target_deg ← degrees(rs.box_target), rot_delta_deg ← degrees(rs.delta)
    rot_err_deg ← 지금 상태의 목표(앞 회전 = target, 되돌리기 = home)와 psi_raw 의 차
    tool_yaw_deg, tool_yaw_est_deg, wz_cmd_dps = degrees(ctx.wz), wz_meas_dps, rot_n, rot_rbar
_last_goal 스냅샷(goal 끝)에 "rot": _rot_values 결과를 저장                     (r1-1)
_snapshot_values 에 **{k: (g.get("rot") or {}).get(k) for k in ROT_KEYS}      # 0 유지·예외 GOAL_END 행 (r1-1)
```

## 9. fake_box.py · sim.launch.py · sim_check.py

```text
fake_box:
    파라미터 yaw_deg(0.0)   # yaw_mode 없음 (r2-15: NO_YAW 는 단위·e2e 시험으로)
    BoxSample 에 yaw(rad) = fold_half(atan2(belt_dir) + radians(yaw_deg))
    메시지: yaw_base ← yaw, yaw_valid ← 참
    (off 노드는 읽지 않으므로 기존 케이스 결과 불변 — 재검 확인)

sim.launch:
    인자 rotate(""), box_yaw_deg("0")
    _write_overrides(…, rotate): rotate 가 "true" 면 {"rotate": {"enable": True}, "input": {"pose_lag_ms": 0.0}}
        # rotate 는 joint_states 전제(교차 검사). sim 의 pose_lag 0 은 rotate 케이스에만 — 기존 케이스 x 기준과 다르다 (r1-3)
    _wants_overrides(kp, max_attempts, z_profile, rotate) 에 rotate 추가 (S2-T14 m5 함정)
    fake_box parameters 에 yaw_deg

sim_check:
    Case 에 rotate: bool = False, box_yaw_deg: float = 0.0
    launch_extra: rotate 면 rotate:=true, box_yaw_deg:=…
    CASES 에 rotate_stall(30°), rotate_small(3°)
    PROFILE_CASES["rotate"] = (rotate_stall, rotate_small)
    EXPECT[("rotate", …)] = OK·SUCCEEDED, PHASES
    J-rot: 틱 rot_state 순서·마지막 rot_cause (STALL | SMALL)
           rotate_stall: gateway 5 s 통계 줄 "자름 {…'angular': N…}" 의 N > 0 을 "예상"으로 표시 (r1-21, warn 줄은 throttle)
           그 밖 케이스: angular N = 0 (자름이 있으면 실패)
```

## 10. 시험 (DD 9절 번호, r1 에서 바뀐 것)

```text
test_rotate.py
  rot_sim(cfg, robot_alpha, robot_lag = 0.024, delta, steps):   # 가짜 로봇 적분기 (시험 안)
      로봇 각속도는 지령을 lag 만큼 늦게, robot_alpha 램프로 따라간다. 30 Hz 로 rot_step 반복.
  #9  α 일치(90), Δ45° → SETTLING 진입 1.40~1.60 s, DONE = SETTLING + settle_s, 끝 오차 ≤ tol, 지나침 ≤ tol (r1-15)
  #9b α 일치, Δ 10.5·12·15·20·30·45·90°, 명령 지연 24·45 ms 두 경우 → ACC_MISMATCH 경고 0, α_eff = cfg (r1-6·r2-1 오경보 회귀)
  #10b robot_alpha 45 → 경고, α_eff 45 ± 5 (두 표본 기울기)
  #10 robot_alpha 10, 설정 90, Δ 15·20·45° → 경고 1회, 끝 DONE 또는 STOPPING(TIMEOUT)→FALLBACK, 지나침 ≤ 3°
  #11 로봇이 안 돎 → stall_s 뒤 STOPPING → STILL_TICKS 뒤 FALLBACK, 그동안 ready 거짓, STOPPING 의 wz 는 즉시 0 (r1-10)
  #12 0 지령 뒤 robot_alpha 로 감속하는 관성 → 멈출 때까지 STOPPING
  #13 SETTLING drift → DONE + settle_drift, wz 0
  #14 되돌리기: LIFT·VERIFY·높이 조건, SKIP 은 안 되돌림, RETURN_STALL 뒤 다시 안 되돌림, RETURNING 필드로 rot_time_s 불변 (r1-7·18·19)
  #15 COLLECT: START_ROTATED 가 프레임 부족보다 먼저, has_field None 이면 계속 모음 (r1-12)
  #16 omega_meas: 값 그대로 0.15 s + 메시지 신선 → 0, 메시지 끊김 → None, service 계단(0.1 s 마다 값 변화)에서 0 오판 없음 (r1-14·r2-5)
  #18 home_ref: 고정값 없음 → 첫 goal ψ0 를 기억, 다음 goal 이 start_tol 밖에서 시작하면 START_ROTATED (r2-3)
  #19 SETTLING 상한 → DONE + SETTLE_TIMEOUT, TIMEOUT 은 α_eff 와 무관 (r2-7·8)
  #20 되돌리기 실패 뒤에도 rot_time_s 불변 (r2-6)
  #17 down_quat(ψ) ↔ tool_yaw 왕복 (ψ = −180~180, tilt 0)
test_log_schema.py: ROT_KEYS ⊆ TICK, 시도 4 키 ⊆ 시도, 개수 단언 갱신
test_node.py / test_action_e2e.py: 0 유지 틱·예외 GOAL_END 행이 off 에서도 써진다 (r1-1 회귀)
test_launch_params.py: T-L12·T-L13 그대로 통과 (r1-4)
test_params.py: bool kind, rotate_on(True 만), 조건부 필수, 교차 검사 6줄, 지문(off·키 없음 같음)
test_action_e2e.py:
  FakeClient(rotate = True, robot_alpha, lag): angular.z 를 램프·지연으로 적분해 down_quat(ψ) 로 발행. 시작 ψ = −88.72°.
  박스는 TCP 보다 60 mm 상류에서 시작, BoxTrack yaw_base·yaw_valid (r1-9)
  #23 회전 성공 → OK, DESCEND 진입 틱 |rot_err| ≤ tol, LIFT·VERIFY 에서 RETURNED, angular ≠ 0 은 PREPARE·TRACK·LIFT·VERIFY 틱에서만
  #24 각속도 적분 없음 → STALL → FALLBACK → OK
  #25 rotate off 회귀: angular 전부 0, rot 키 null, 결과·phase 순서 동일, 0 유지 행 있음
  #26 ROTATING 중 취소 → 다음 발행부터 angular 0
```

## 11. 재검 반영표 (r1)

| # | 지적 | 반영 |
|---|---|---|
| 필수 1 | 스냅샷 경로 rot 키 누락 → off 에서도 0 유지·예외 GOAL_END 행 사라짐 | 7·8절 ROT_KEYS, `_last_goal["rot"]`, `_snapshot_values` |
| 필수 2 | bool·float_or_null kind 없음, normalize | `bool` kind 하나 추가, home 은 `float` 선택 키(yaml 에 안 적음) |
| 필수 3 | sim rotate 가 pose_lag 60 에 걸림, `_wants_overrides` | 9절 덮어쓰기에 pose_lag 0, 함수 인자 추가 |
| 필수 4 | T-L12·T-L13 | 6절 yaml 3종 키 일치, home 키 제외 |
| 필수 5 | rate_limit 에 α_eff → 지나침 | rate_limit 은 cfg.alpha 만 |
| 필수 6 | α 감시 오경보(Δ 10~20°) | 램프 상승 중 2틱 연속일 때만 |
| 필수 7 | RETURNING 이 delta·t_start 재사용 | ret_* 전용 필드 |
| 필수 8 | 예외 반복 시 TRACK 고착, geo None | rot_dead + 노드 정지 확인, geo None 방어 |
| 필수 9 | e2e 박스 하류 시작, 쿼터니언 식 | 60 mm 상류, down_quat = Rz(ψ)·Rx(π) |
| 필수 10 | 0 을 rate_limit 으로 줄임 → VERIFY 각속도 ≠ 0 | want None = 즉시 0 |
| 권장 11 | HLD↔DD 차(STALL 식, VERIFY 되돌리기) | DD 기준 명시(HLD r3 주석), VERIFY 는 0 |
| 권장 12 | COLLECT 원인 순서, has_field None | pre_checks 먼저, None = 대기 |
| 권장 13 | pose_ok 나이 0.3 → 0.2 | pose_extrap_max |
| 권장 14 | omega_meas 끊김과 정지 구별 | pose_rx_age ≤ 0.05 |
| 권장 15 | 시험 #9 시간 정의 | SETTLING 진입 1.40~1.60, DONE = + settle |
| 권장 16 | dt 가 지난 틱 값 | effective_dt 로 이번 틱 |
| 권장 17 | 분기 모호 | 첫 매치 한 줄 규칙 |
| 권장 18 | SKIP 되돌리기 | 제외 |
| 권장 19 | 되돌리기 반복 | ret_tried 1회 |
| 권장 20 | box_target 필드, rotate_on 문자열 | 필드 추가, True 만 |
| 권장 21 | sim 자름 판정 | gateway 5 s 통계 줄 파싱 |
| 권장 22 | yaw 같은 값 비교 | wrap_pi 차 |

## 12. Fable 5.1 독립 재검 반영표 (r2)

재검 16건을 세션이 하나씩 확인(재검 스크립트 재실행·코드 대조)한 뒤 15건 채택, 1건 기각.
| # | 지적 | 세션 확인 | 처리 |
|---|---|---|---|
| 1 필수 | α 감시가 α 일치에서도 매번 경고(α_eff 42, 45° DONE 1.80→2.13 s) | f3_pseudo_sim 재실행: 지연 24·35 ms 모두 경고 재현. "두 표본 기울기"는 일치 경고 0, α45·10 정확 검출 | 채택 — `alpha_slope` |
| 2 | HLD 회전 시간표가 pseudo 법칙과 다름 | f3b 'off': SETTLING 0.83/1.20/1.47/1.73/2.23 s, DONE +0.33 | 채택 — HLD r3 주석에 표 |
| 3 | home = goal ψ0 는 "매 goal 전 OBSERVE" 임시 규칙에 기댐 | sort_fsm "G0 임시 규칙" 확인 | 채택 — home_ref = 고정값 또는 노드 기동 뒤 첫 goal ψ0, 매 goal START_ROTATED 검사 |
| 4 | 사다리꼴 LIFT 에서 되돌리기 시간 부족 | LIFT ≈1.77 s, +10 뒤 ≈0.9 s < 45° 1.47 s | 채택 — VERIFY 포함(D0 초안 수정 요청) |
| 5 | pose_lag 0 검사는 yaml 짝 검사일 뿐, YAW_HOLD 0.1 이 service 에서 오판 | runbook·gateway 자동 복귀 확인 | 채택 — 문구 "yaml 짝 검사", YAW_HOLD_MAX 0.15 |
| 6 | 되돌리기 실패가 t_done 을 덮음 | pseudo 줄 확인 | 채택 |
| 7 | SETTLING 상한 없음 | 확인 | 채택 — 1.0 s 뒤 DONE + SETTLE_TIMEOUT |
| 8 | TIMEOUT 이 α_eff 로 늘어남(최대 19 s) | 식 확인 | 채택 — cfg.alpha 기준 |
| 9 | 지시서 (i)(k) 와 다른 점 | D9 보정식 삭제, D11 자체 모델 — T16 도구 교차값 일치(0.3 mm) | 채택 — 회신에 명시, HLD D11 한 줄 |
| 10 | 측정 ② 파트 B 가 30 mm 상류만 | 정렬 직전은 바로 위 | 채택 — 가이드에 "바로 위" 정지점 |
| 11 | HLD 11절 인용 출처 | 인수인계 §3-5 와 지시서 (i) 대조 | 채택 — 출처를 지시서로 |
| 12 | deadband·min_deg 중복 | — | **기각** — 1단계(min 10)→5단계(min = 데드밴드)를 yaml 만으로 바꾸려면 둘 다 필요, tol < deadband 검사의 기준도 deadband |
| 13 | "한 줄도 동작 안 함" 문구 | `_yaw_field` 는 off 에서도 실행 | 채택 — "기존 열 값·경로·sha 동일" |
| 14 | OFF 상태 미사용 | off 면 ctx.rot None | 채택 — 삭제 |
| 15 | rotate_invalid 가 rotate_small 과 같은 배관 | NO_YAW 는 단위·e2e 로 확인 가능 | 채택 — sim 케이스·fake_box yaw_mode 삭제 |
| 16 | yawlog 워크트리 없음 | `git worktree list` 확인(원격 브랜치·PR #43 은 있음) | 기록만 갱신 |

## 13. 코드 반영 메모 (real code, 10/14 — pseudo 와 다르게 정한 작은 점)
- RETURNING 에서 되돌리기 조건이 깨져 대기할 때 `ret_start`·`ret_psi_start` 를 다시 잡는다 — 대기 뒤 다시 돌 때 STALL·TIMEOUT 이 대기 시간을 잘못 세지 않게.
- COLLECT 에서 SKIP 으로 끝나도(SMALL·OUT_OF_RANGE) 계산한 Δ·n·r̄ 를 로그에 남긴다.
- goal 전에 버퍼가 n_min 이상 차 있으면 goal 첫 틱에 결정하므로 틱 로그에 COLLECT 가 남지 않을 수 있다(A 안의 기대 동작) — sim_check J-rot·e2e 는 COLLECT 를 있어도 없어도 되게 본다.
- 기준 공구 yaw(home_ref)는 goal 수락 때 노드가 정한다(고정값이 없으면 그 goal 의 공구 yaw, 기울기 ≤ 5° 일 때만). rot_step 의 `rs.home` 은 그 값을 받는다.
- 회전 로그 키 12개는 `rotate.ROT_LOG_KEYS` 와 `log_schema.ROT_KEYS` 가 같은 순서(시험으로 고정).
