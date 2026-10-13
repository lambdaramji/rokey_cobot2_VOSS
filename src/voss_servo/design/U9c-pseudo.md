# U9-c pseudo — `lost_cause` · `belt_speed_fit`

DD 3절(D1 채택 규칙, 10/12 사용자 승인)·4.3절을 그대로 옮긴다. r2(10/12)는 독립 재검 반영분이다(F1·F2·F4·F6·F7·F13, DD 8절).
나머지 세 함수(measured_velocity·stall_count·speed_warn_step)는 DD 4절 식이 곧 코드라 pseudo 를 생략한다.

## 1. `diagnose.lost_cause`

```
함수 lost_cause(
    pub_count,       # /voss/vision/box 발행자 수 (LOST 틱에 1회 조회, 조회 실패면 None)
    my_rx,           # 내 트랙 마지막 수신 시각 (없으면 None)
    other_rx,        # 이 goal 동안 다른 트랙 마지막 수신 시각 (없으면 None)
    stall_n,         # 지금까지의 연속 정지 틱 수
) -> VISION_DOWN | ROBOT_STALLED | None:

    # ① 비전 노드 자체가 없다
    만약 pub_count 가 0 이면:
        돌려줌 VISION_DOWN
        # None(조회 실패)은 0 으로 치지 않는다 — 모르면 비전 탓을 하지 않는다

    # ② 다른 트랙이 내 트랙과 같은 순간에 끊겼다 = 카메라 프레임이 통째로 끊김 (D1)
    #    (r2: "다른 트랙도 lost_timeout 넘게 끊김" 조건 삭제 — LOST 틱이면 이미 함의되고,
    #     id 순 발행 1 ms 차로 경계에서 놓친다, DD 3절 F2)
    만약 other_rx 가 있고 my_rx 가 있고 |other_rx − my_rx| ≤ SIMUL_LOSS_S 이면:   # 0.2 s
        돌려줌 VISION_DOWN

    # ③ 명령은 나가는데 로봇이 안 움직였다
    만약 stall_n ≥ STALL_TICKS_N 이면:                     # 10틱 ≈ 0.33 s
        돌려줌 ROBOT_STALLED

    # ④ 특정 원인 없음 → 호출 쪽이 fsm cause 를 그대로 둔다 (r2, F7 변형)
    돌려줌 None
```

경계: `동시` 는 `≤ 0.2` 이면 참(같으면 동시), stall 은 `≥ 10`. 인자에서 `now`·`lost_timeout` 은 빠졌다(r2 — ② 에서 더 이상 쓰지 않음).

### 호출 쪽 (belt_servo `_diagnose` 안, 한 곳 — 전체 try/except)
```
함수 _diagnose(ctx, tr, now) -> tr:
    시도:
        만약 ctx.phase_t_next 있음: ctx.phase_t = ctx.phase_t_next; ctx.phase_t_next = 없음   # F1 예약 교체
        new_obs = 관측열 갱신(ctx)                              # 2절 호출 쪽
        v_meas = measured_velocity(_pose_prev_value, _pose_value, now, POSE_HOLD_MAX_S)
        ctx.stall_n = stall_count(ctx.stall_n, |_last_cmd|, |v_meas| 또는 None)
        속도 추정·WARN (2절 호출 쪽)
        단계 시각 기록:
            만약 tr.state.phase ≠ ctx.phase_seen: ctx.phase_t[tr.state.phase] 가 없으면 = now
            만약 tr.attempt_ended:                              # 재시도 — 이 틱 로그는 끝난 시도 시각 그대로
                ctx.phase_t_next = {PREPARE: now}
                ctx.obs_hist 비움; ctx.speed_run = 0           # F13 (speed_warned 는 goal 단위라 유지)
            ctx.phase_seen = tr.state.phase
        ctx.diag.cause_fsm = tr.cause                            # 매 틱 보관
        만약 tr.reason == LOST:
            pub_count = 안전하게(count_publishers("/voss/vision/box"))   # 예외면 None
            ctx.diag.pub_count = pub_count
            진단 = lost_cause(pub_count, 내 entry.rx, ctx.other_rx, ctx.stall_n)
            만약 진단 있음: tr = replace(tr, cause=진단)          # fsm.py 그대로, frozen 값 복사
    예외 e:
        ctx.diag = 비움(null)                                    # 진단 값만 버린다
        만약 이 goal 에서 처음이면: error 로그 "진단 예외 …"       # goal 은 계속
    돌려줌 tr
```
⚠ 재시도 틱의 단계 시각 기록 순서: 그 틱의 `tr.state.phase` 는 PREPARE 지만 `ctx.phase_t` 에는 이미 끝난 시도의 PREPARE 시각이 있다. 그래서 "없으면 = now"가 덮어쓰지 않는다. 새 PREPARE 시각은 `phase_t_next` 로만 들어간다.

## 2. `control.belt_speed_fit`

```
함수 belt_speed_fit(
    samples,       # [(촬영 stamp s, [x, y, z] m), ...] 시간순
    dir_xy,        # 벨트 방향 단위벡터 (xy, z=0) — 제어 FF 와 같은 방향
    max_points,    # 90
    min_points,    # 15
    min_span_s,    # 0.5
) -> (속도 m/s 또는 None, 시간 폭 s 또는 None):

    pts = samples 의 마지막 max_points 개                   # 오래된 점은 버린다
    만약 pts 가 min_points 개보다 적으면:
        돌려줌 (None, None)                                 # 점 부족

    t0 = pts[0] 의 stamp
    t_i = 각 점 stamp − t0                                  # 큰 수(1.79e9)를 빼서 계산 오차 줄임
    s_i = dir_xy · (x_i, y_i, 0)                            # 벨트 방향으로 간 거리 (가로·높이 무시)
    span = t_마지막 − t_처음

    만약 span < min_span_s 이면:
        돌려줌 (None, span)                                 # 시간 폭 부족 (폭은 로그용으로 준다)

    t평균, s평균 = t_i 평균, s_i 평균
    분모 = Σ (t_i − t평균)²
    만약 분모 ≤ 0 이면:                                     # 모든 stamp 같음 (방어)
        돌려줌 (None, span)
    v = Σ (t_i − t평균)(s_i − s평균) / 분모                 # 최소제곱 직선 기울기
    만약 v 가 유한수가 아니면: 돌려줌 (None, span)
    돌려줌 (v, span)
```

### 호출 쪽 (belt_servo `_diagnose` 안)
```
obs = 내 트랙의 마지막 유효 관측
new_obs = 거짓
만약 obs 있음 이고 (obs_hist 비었음 또는 obs.stamp > obs_hist 마지막 stamp):
    obs_hist 에 (obs.stamp, obs 좌표) 추가                  # deque(maxlen=90), 시도마다 새로 (F13)
    new_obs = 참
est, span = belt_speed_fit(obs_hist, cfg 벨트 방향, 90, 15, 0.5)
run, fire = speed_warn_step(ctx.speed_run, ctx.speed_warned, est, 설정 벨트 속도, span, new_obs, SPEED_WARN_RATIO)  # F4, B안 10 %
ctx.speed_run = run
만약 fire: WARN 1줄, ctx.speed_warned = 참
# est 는 로그에만 — control.command 에는 넘기지 않는다
# terminal 틱이면: INFO 1줄 = speed_note(est, 설정 속도, span, len(obs_hist))   # r3, B안 — 2 % 이상이면 표시
```
