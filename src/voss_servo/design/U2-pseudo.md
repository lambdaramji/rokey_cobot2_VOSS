# U2 제어 순수 함수 — Pseudo code

[U2-dd.md](U2-dd.md)(승인 10/08)의 함수별 의사코드. `control.py` 는 ROS·시계·파일을 쓰지 않는다. 벡터는 NumPy 길이 3, 단위 m·m/s·s. 최종은 코드가 기준이다.

- 상태: **pseudo 확정(박병후, 10/08)** — r2 독립 재검 반영

## 1. control.py — 상수·설정

```text
XY 규칙 이름:  FF_P = "FF_P"   FF = "FF"   ZERO = "ZERO"
명령 이름(틱 로그 cmd_rule): 위 셋 + ZERO_NO_POSE(pose 없음) + ZERO_NO_OBS(유효 관측 없음) + ZERO_STOP(멈추는 중·끝)

함수 config_from_values(values):                 # 단위 변환은 여기 한 곳
    d = np.asarray(values["belt.direction_base"], dtype=float)   # ROS array.array 도 받음
    dir_xy = (d.x, d.y, 0) / 그 길이                        # 벨트 방향 수평 단위벡터 (길이 ≥ 0.99 는 params 가 보장)
    belt_v = values["belt.speed_cmps"] / 100 × dir_xy      # cm/s → m/s, z = 0
    반환 ControlConfig(
        dir_xy, belt_v,
        latency_offset_s  = timing.latency_offset_ms / 1000,
        pose_lag_s        = input.pose_lag_ms / 1000,
        pose_extrap_max_s = input.pose_extrap_max_ms / 1000,
        blind_entry_max_age_s,
        kp_xy = control.kp_per_s,  kp_z = control.kp_z_per_s,
        align_along_m = align_tol_along_mm / 1000,  align_cross_m = align_tol_cross_mm / 1000,
        v_max = limits.max_speed_mps,  a_max = limits.max_acc_mps2,
        approach_dz = + z.approach_above_top_mm / 1000,
        grasp_dz    = − grasp.tcp_z_below_top_mm / 1000,         # 윗면보다 아래 → 음수
        lift_dz     = + z.lift_above_top_mm / 1000,
        descend_speed, lift_speed,
        height_tol_m = z.height_tol_mm / 1000,
        x_min = reach.x_min_mm / 1000,  x_max = reach.x_max_mm / 1000,
        dt_nominal = 1 / rate_hz)
```

## 2. control.py — 기본 함수

```text
함수 zero_cmd():
    반환 (0, 0, 0)

함수 effective_dt(prev_calc, now, dt_nominal):
    prev_calc 가 없으면 반환 dt_nominal               # goal 첫 틱
    dt = now − prev_calc
    dt ≤ 0 이면 반환 dt_nominal                         # 시계가 같거나 뒤로 감
    반환 min(dt, 2 × dt_nominal)                        # 오래 멈췄다 와도 한 틱 변화량을 키우지 않음

함수 predict(p_obs, box_stamp, now, belt_v, latency_offset):
    raw = now − box_stamp                               # 사진 찍은 뒤 지난 시간
    clipped = raw < 0                                   # 미래 stamp (시계 차이)
    h = max(raw, 0) + latency_offset
    h = max(h, 0)                                       # 음수 offset 이 커도 과거로 되돌리지 않음
    반환 (p_obs + belt_v × h, h, clipped)

함수 pose_value_stamp(prev, position, stamp):           # r4: pose 값이 0.1 s 마다만 바뀌는 gateway 대응
    prev 가 있고 prev.값 == position 이면 반환 prev      # 같은 값 반복 → 처음 stamp 유지
    반환 (position, stamp)                              # 값이 바뀐 첫 메시지

함수 grasp_floor_blocked(top_z, cfg):                 # r4: gateway z 하한 때문에 파지 문턱에 못 닿나
    반환 top_z + grasp_dz + height_tol < z_min + 0.001

함수 tcp_now(pose, pose_stamp, pose_lag, last_cmd_v, now, extrap_max):   # pose_stamp = 값이 처음 온 stamp
    h = max(now − pose_stamp, 0) + pose_lag             # pose 가 실제로 찍힌 시각부터 지금까지
    capped = h > extrap_max                             # 너무 오래된 pose 인가
    h_used = min(h, extrap_max)                         # 상한까지만 외삽 (원본으로 돌아가면 TCP 추정이 튄다)
    반환 (pose + last_cmd_v × h_used, h, capped)       # h 는 자르기 전 값 (로그용)

함수 tcp_target(p_pred, z_target):
    반환 (p_pred.x, p_pred.y, z_target)                 # 박스 윗면 중심 바로 위·아래, 높이만 phase 별

함수 split_error(e, dir_xy):
    e_xy = (e.x, e.y, 0)
    along = e_xy · dir_xy                               # 벨트 방향 성분 (부호 있음)
    cross = ‖e_xy − along × dir_xy‖                     # 가로 성분 크기
    반환 (along, cross)

함수 ff_p(e, belt_v, dir_xy, kp_xy, use_p):
    v = (belt_v.x, belt_v.y, 0)                         # FF: 벨트만큼 같이 감
    use_p 면 v = v + kp_xy × (e.x, e.y, 0)               # P: 남은 xy 오차를 메움
    along = v · dir_xy                                  # 벨트 방향 성분
    along < 0 이면 v = v − along × dir_xy               # 기다리기: 상류로는 가지 않는다 (가로 성분은 그대로)
    반환 v

함수 z_plan(phase, top_z, cfg):                      # → (목표 z 또는 없음, 내려갈 상한, 올라갈 상한)
    PREPARE·TRACK → (top_z + approach_dz, descend_speed, lift_speed)
    DESCEND       → (top_z + grasp_dz,    descend_speed, 0)          # 하강 중 위로 안 감
    LIFT          → (top_z + lift_dz,     0,             lift_speed) # 위로만
    GRASP·VERIFY  → (없음, 0, 0)                                      # z 속도 0

함수 z_speed(z_target, tcp_z, kp_z, v_down_max, v_up_max):
    v = kp_z × (z_target − tcp_z)                       # 멀면 빠르게, 가까우면 느리게
    반환 v 를 [−v_down_max, +v_up_max] 안으로 자른 값

함수 clamp(v, prev_v, v_max, a_max, dt):
    not np.any(v) 이면 반환 (0 벡터, False)                      # 정지는 즉시 (가속 제한 없음). FF 규칙은 belt_v ≠ 0 이라 해당 없음
    clamped = False
    n = ‖v‖
    n > v_max 이면: v = v × (v_max / n), clamped = True          # 방향 유지, 길이만 줄임
    dv = v − prev_v
    m = ‖dv‖, lim = a_max × dt
    m > lim 이면: v = prev_v + dv × (lim / m), clamped = True    # 한 틱 변화량 제한
    반환 (v, clamped)

함수 in_reach(tcp_x, x_min, x_max):
    tcp_x < x_min 이면 "X_MIN"
    tcp_x > x_max 이면 "X_MAX"
    아니면 없음                                         # 경계값은 구간 안

함수 xy_rule(phase, visible):
    PREPARE·TRACK·DESCEND → visible 이면 FF_P, 아니면 FF   # 안 보여도 박스와 같이 간다 (재검 r2)
    GRASP          → FF                                 # 정렬은 끝났다고 보고 벨트만 따라감
    LIFT·VERIFY    → ZERO
```

## 3. control.py — 틱 입구 두 개

```text
함수 geometry(tcp_est, obs_xyz, obs_stamp, visible, now, cfg):
    (tcp, tcp_h, capped) = tcp_est                # 노드가 먼저 부른 tcp_now 결과
    reach = in_reach(tcp.x, cfg.x_min, cfg.x_max)
    obs_xyz 가 없으면:                                    # 유효 관측이 아직 없음
        반환 Geometry(tcp, tcp_h, capped, visible=False, has_obs=False,   # reach 는 관측 없이도 계산
                      p_pred=없음, pred_h=없음, dt_clipped=False, top_z=없음, obs_age=없음,
                      err_along=없음, err_cross=없음,
                      aligned=False, at_grasp=False, at_lift=False, reach)
    (p_pred, pred_h, clipped) = predict(obs_xyz, obs_stamp, now, cfg.belt_v, cfg.latency_offset_s)
    top_z = obs_xyz.z                                   # 벨트 z 속도 0 → 예측해도 높이는 같음
    obs_age = max(now − obs_stamp, 0)
    approach_z = top_z + cfg.approach_dz
    e = tcp_target(p_pred, approach_z) − tcp
    (along, cross) = split_error(e, cfg.dir_xy)
    aligned = visible
              그리고 |along| ≤ cfg.align_along_m
              그리고 cross ≤ cfg.align_cross_m
              그리고 |tcp.z − approach_z| ≤ cfg.height_tol_m
              그리고 obs_age ≤ cfg.blind_entry_max_age_s       # 사각 진입 직전 관측이 신선한가
    at_grasp = tcp.z ≤ top_z + cfg.grasp_dz + cfg.height_tol_m
    at_lift  = tcp.z ≥ top_z + cfg.lift_dz − cfg.height_tol_m
    반환 Geometry(tcp, tcp_h, capped, visible, has_obs=True, p_pred, pred_h, clipped,
                  top_z, obs_age, along, cross, aligned, at_grasp, at_lift, reach)

함수 command(phase, stopping, terminal, geo, prev_v, dt, cfg):
    stopping 또는 terminal 이면 반환 Command(0 벡터, ZERO_STOP, 없음, 없음, False)   # U1 회신 ⑤: 항상 0
    geo 가 없으면(pose 없음) 반환 Command(0 벡터, ZERO_NO_POSE, 없음, 없음, False)
    geo.has_obs 가 거짓이면   반환 Command(0 벡터, ZERO_NO_OBS, 없음, 없음, False)
    rule = xy_rule(phase, geo.visible)
    (z_t, down, up) = z_plan(phase, geo.top_z, cfg)
    target = tcp_target(geo.p_pred, z_t 가 있으면 z_t, 없으면 geo.tcp.z)   # z 없음 = 높이 오차 0
    e = target − geo.tcp
    rule == FF_P 이면 v = ff_p(e, cfg.belt_v, cfg.dir_xy, cfg.kp_xy, use_p=참)
    rule == FF   이면 v = ff_p(e, cfg.belt_v, cfg.dir_xy, cfg.kp_xy, use_p=거짓)
    rule == ZERO 이면 v = 0 벡터
    v.z = z_t 가 있으면 z_speed(z_t, geo.tcp.z, cfg.kp_z, down, up), 없으면 0
    (v, clamped) = clamp(v, prev_v, cfg.v_max, cfg.a_max, dt)
    반환 Command(v, rule, target, e, clamped)
```

- `rule` 은 xy 규칙이다. LIFT 는 rule = ZERO 지만 z 는 올라간다 (로그에서 `cmd_vel_mps` 로 구분).
- PREPARE·안 보임: rule = FF, z 는 접근 높이로 (DD 1.3, 재시도 때 박스와 같이 가며 사각에서 올라와 다시 보기).

## 4. params.py 추가

```text
GATEWAY_MAX_SPEED_MPS = 0.1    # gateway 속도 자르기 기본값 사본 (servo_guard.py max_speed_mm_s 100, #104 014a7b4). 바뀌면 함께
GATEWAY_ACC_MPS2      = 0.1    # gateway → speedl 램프 기본값 사본 (servo_acc 100 mm/s²). gateway 는 가속을 자르지 않는다
ALIGN_CROSS_MAX_MM    = 10.0   # 가로 정렬 허용치 상한 (DD 승인 10/08, 박병후)
POSE_VALUE_PERIOD_MS  = 100.0  # pose 값 갱신 간격 최악값 (gateway service, ADR-0010 69행)
GATEWAY_Z_MIN_MM      = 78.0   # gateway z 하한 사본 (servo_guard.py z_min_mm)
DIRECTION_XY_MIN      = 0.99   # 벨트 방향의 수평 길이 하한

PARAM_SPECS 에 추가 (DD 2절 표, 순서 = 묶음별):
    ("input.pose_lag_ms",            float, ms,  필수, ≥ 0)
    ("input.pose_extrap_max_ms",     float, ms,  필수, > 0)
    ("input.blind_entry_max_age_s",  float, s,   필수, > 0)
    ("control.kp_z_per_s",           float, 1/s, 필수, > 0)
    ("control.align_tol_along_mm",   float, mm,  필수, > 0)
    ("control.align_tol_cross_mm",   float, mm,  필수, > 0)
    ("z.descend_speed_mps",          float, m/s, 필수, > 0)
    ("z.lift_speed_mps",             float, m/s, 필수, > 0)
    ("z.height_tol_mm",              float, mm,  필수, > 0)

_cross_checks 에 추가 (값이 모두 있고 개별 검사를 통과한 것만, U1 have() 그대로) — DD 2절 1~11:
 1  max_speed ≥ GATEWAY_MAX_SPEED_MPS            → invalid (limits.max_speed_mps, "gateway 속도 상한 0.1 보다 작아야 함")
 2  max_acc > GATEWAY_ACC_MPS2                   → invalid (limits.max_acc_mps2, "로봇 램프 0.1 이하")
 3  belt.speed_cmps / 100 ≥ max_speed            → invalid (limits.max_speed_mps, "벨트 속도보다 커야 함")
 4  descend_speed > max_speed                    → invalid (z.descend_speed_mps, "max_speed 이하")
 5  lift_speed > max_speed                       → invalid (z.lift_speed_mps, "max_speed 이하")
 6  pose_extrap_max_ms < pose_lag_ms + POSE_VALUE_PERIOD_MS + POSE_PERIOD_MS(20)
                                                 → invalid (input.pose_extrap_max_ms, "pose_lag_ms + 120 이상")
 7  align_tol_along_mm > align_tol_cross_mm      → invalid (control.align_tol_along_mm, "cross 이하")
 8  align_tol_cross_mm > ALIGN_CROSS_MAX_MM      → invalid (control.align_tol_cross_mm, "10 mm 이하")
 9  kp_z × descend_speed > max_acc               → invalid (control.kp_z_per_s, "kp_z × descend_speed ≤ max_acc")
10  height_tol_mm ≥ approach_above_top_mm − (vision_cutoff_above_top_mm + BLIND_EXIT_MARGIN_MM)
                                                 → invalid (z.height_tol_mm, "접근 높이 − 사각 이탈 높이보다 작아야 함")
11  √(direction_base.x² + direction_base.y²) < DIRECTION_XY_MIN
                                                 → invalid (belt.direction_base, "수평 성분 길이 0.99 이상")
```

## 5. log_schema.py

```text
TICK_FIELDS 에서 "tcp_pose_m" 뒤에:  "tcp_now_m", "tcp_extrap_s", "tcp_extrap_capped"
              "predicted_m" 뒤에:  "predict_horizon_s", "predict_dt_clipped", "obs_age_s", "visible"
              "error_m" 뒤에:      "err_along_m", "err_cross_m"
              "clamped" 뒤에:      "cmd_rule", "dt_s", "aligned", "at_grasp_height", "at_lift_height", "reach"
ATTEMPT_FIELDS: 그대로
```

## 6. belt_servo.py 연결

```text
__init__:
    self._last_cmd = (0, 0, 0)                          # 마지막 발행 속도 (외삽·가속 제한 입력)
    ... (U1 그대로) ...
    self._ctrl = READY 면 control.config_from_values(values), 아니면 없음

GoalCtx 에 추가:  last_calc = 없음,  geo = 없음,  cmd = 없음,  dt = 없음,  source = 없음(마지막 유효 관측 출처)

_on_pose(msg):                                         # r4
    self._pose = (msg, 수신 시각)                       # 끊김 판정용, 메시지마다
    self._pose_value = control.pose_value_stamp(self._pose_value, msg 위치, stamp_s(msg stamp))

_on_box(msg):                                          # U1 에서 한 줄 바뀜
    valid = msg.position_valid 그리고 vec(msg.position_base) 가 있음   # NaN·inf 좌표면 valid 메시지라도 invalid 로
    (나머지 U1 그대로: last_valid 는 valid 일 때만 갱신)

함수 vec(msg_point):                                   # Point → 배열, 하나라도 NaN·inf 면 없음
    a = (x, y, z)
    모두 유한하면 반환 a, 아니면 없음

_publish(vel):
    (U1 그대로 발행)
    self._last_cmd = vel                                # 0 유지·예외 경로 포함 모든 발행
    반환 발행 시각

_build_event(ctx, now):
    cfg = self._ctrl
    entry = 내 track_id 의 BoxEntry
    tcp_est = 없음
    self._pose_value 가 있고 그 값이 유한하면:                # r4: 값이 처음 온 stamp 기준
        (위치, 값 stamp) = self._pose_value
        tcp_est = control.tcp_now(위치, 값 stamp, cfg.pose_lag_s,
                                  self._last_cmd, now, cfg.pose_extrap_max_s)
    obs = entry.last_valid (entry 없으면 없음)
    obs_xyz = vec(obs.position_base) (obs 없으면 없음)
    tcp_z = tcp_est 의 tcp.z (없으면 없음)                 # ← U1 의 원본 pose z 를 보정 TCP z 로
    blind = fsm.is_vision_blind(phase, tcp_z, obs_xyz.z 또는 없음, cutoff, ctx.blind)
    (사각 → 보임이면 ctx.vision_since = now, ctx.blind = blind — U1 그대로)
    (box_lost, box_stale, pose_stale) = fsm.input_flags(...)   # U1 그대로
    visible = (not blind) 그리고 entry 있음 그리고 (not entry.latest_invalid) 그리고 obs_xyz 있음
    obs 가 있고 ctx.source 가 있고 obs.position_source ≠ ctx.source 이면
        WARN "goal 중 position_source 변경 {ctx.source}→{새 값} — 예측 리셋은 U9"
    obs 가 있으면 ctx.source = obs.position_source
    ctx.geo = tcp_est 가 있으면 control.geometry(tcp_est, obs_xyz, stamp_s(obs.stamp), visible, now, cfg)
              아니면 없음
    반환 TickEvent(U1 항목들,
                   aligned         = ctx.geo.aligned         (geo 없으면 거짓),
                   at_grasp_height = ctx.geo.at_grasp_height (geo 없으면 거짓),
                   at_lift_height  = ctx.geo.at_lift_height  (geo 없으면 거짓),
                   reach           = ctx.geo.reach           (geo 없으면 없음))

_tick_goal(ctx, now):
    ev = _build_event(ctx, now)
    tr = fsm.step(...)                                  # U1 그대로
    ctx.state = tr.state
    _handle_actions(...)
    dt = control.effective_dt(ctx.last_calc, now, cfg.dt_nominal)   # ① dt 먼저
    ctx.last_calc = now                                             # ② 그 다음 갱신
    ctx.dt = dt
    ctx.cmd = control.command(tr.state.phase, tr.state.stopping, tr.terminal,
                              ctx.geo, self._last_cmd, dt, cfg)   # ← 여기가 U1 의 vel = ZERO 자리
    t_pub = _publish(ctx.cmd.vel)
    (feedback·틱 로그·시도 로그·종료 처리 — U1 그대로)

_tick_values(ctx, ev, tr, now, t_pub, vel):           # U2 키 채우기 (geo·cmd 없으면 null)
    predicted_m        = geo.p_pred
    tcp_target_m       = cmd.tcp_target
    error_m            = cmd.error
    clamped            = cmd.clamped
    cmd_rule           = cmd.rule
    tcp_now_m          = geo.tcp
    tcp_extrap_s       = geo.tcp_horizon_s
    tcp_extrap_capped  = geo.tcp_extrap_capped
    predict_horizon_s  = geo.pred_horizon_s
    predict_dt_clipped = geo.dt_clipped
    obs_age_s          = geo.obs_age_s
    visible            = geo.visible
    err_along_m        = geo.err_along
    err_cross_m        = geo.err_cross
    dt_s               = ctx.dt
    aligned · at_grasp_height · at_lift_height · reach = 이번 틱 TickEvent 값
    (배열은 list 로, 모르는 값은 null — NaN 금지)

_snapshot_values(...):                                 # 0 유지·예외 경로
    U2 키 전부 null, cmd_rule = "ZERO_STOP"
```

## 7. 테스트 의사코드 (대표 몇 개 — 전체 목록은 DD 5절)

```text
cfg = 테스트용 설정 (belt 0.048 m/s +x, kp_xy 2, kp_z 2, v_max 0.08, a_max 0.1,
                    approach 40 mm, lift 50 mm, grasp −19 mm, descend 0.05, lift 0.08, tol 2 mm,
                    along 3 mm, cross 5 mm, lag 60 ms, extrap_max 200 ms, blind_entry 0.15 s)

test_tcp_now_lag60_moves_2_88mm_at_48mmps:
    (tcp, h, capped) = tcp_now(pose=(0,0,0.2), stamp=10.0, lag=0.06, last_v=(0.048,0,0), now=10.0, max=0.12)
    tcp.x ≈ 0.00288, h ≈ 0.06, capped 거짓

test_tcp_now_over_max_caps_at_max:
    now = 10.07 → h = 0.13 > 0.12 → tcp.x ≈ 0.048 × 0.12 = 0.00576 (상한에서 멈춤), h ≈ 0.13, capped 참

test_predict_negative_dt_clipped_and_flagged:
    predict(p, stamp=10.05, now=10.0, …) → p_pred == p (offset 0), clipped 참

test_clamp_zero_is_immediate:
    clamp(0 벡터, prev=(0.05,0,0), …) → (0 벡터, 거짓)

test_clamp_acc_limits_change:
    clamp((0.05,0,0), prev=0, v_max 0.08, a_max 0.1, dt 1/30) → x ≈ 0.00333, clamped 참

test_ff_p_box_upstream_waits_along_zero:
    e = (−0.05, 0.004, 0), kp 2 → FF+P 의 벨트 방향 = 0.048 − 0.1 < 0 → 결과 벨트 방향 성분 0, 가로 = 2 × 0.004 그대로

test_command_grasp_ff_only_z_zero:
    geo: visible 거짓, 오차 (0.004, 0.002) → command(GRASP, …, prev=belt_v) → vel == (0.048·dir, 0), rule FF

test_aligned_needs_all_five:
    다섯 조건 모두 참 → aligned 참; 하나씩 깨서(안 보임 / along 3.1 mm / cross 5.1 mm / 높이 2.1 mm / 나이 0.16 s) 각각 거짓
```

## 8. 구현 메모 (초급자가 막히기 쉬운 곳)

- 0 벡터 판정은 `not np.any(v)`. 부동소수 비교(`== 0.0`)를 여러 줄로 쓰지 않는다.
- 오차가 두 개다: `Geometry.err_along/err_cross`(접근 높이 기준, 정렬 판정·로그) vs `Command.error`(이번 phase z 기준, P·로그 `error_m`). DD 1.4 표.
- `visible` 은 노드가 계산해 넘긴다. geometry 안에서 다시 판단하지 않는다.
- `_tick_goal` 순서: dt 계산 → `last_calc = now` → `command` → 발행 → `_last_cmd` 갱신(`_publish` 안).
- `array.array`(ROS double 배열) → `np.asarray(…, dtype=float)` 는 `config_from_values` 한 곳에서.
- 로그에 넣을 때 NumPy 배열은 `list(map(float, a))` 로, NaN 이 없게(log_schema 규칙).

## 9. 변경 기록

| 날짜 | 변경 |
|---|---|
| 10/08 | 초안 |
| 10/08 | 확정(박병후): r2 + 외삽 상한 초과 → 상한까지 외삽 |
| 10/09 | r4 PR #122 학민 리뷰: pose_value_stamp, grasp_floor_blocked(reach Z_MIN), POSE_VALUE_PERIOD_MS, _on_pose |
| 10/08 | r2 독립 재검(Fable 5.1) 반영: ff_p 기다리기, PREPARE 안 보임 FF, ZERO_NO_POSE, belt_v = speed × dir_xy, 교차 검사 11개, 로그 키 15개, `_on_box` NaN, position_source 경고, dt 순서, 구현 메모(8절) |
