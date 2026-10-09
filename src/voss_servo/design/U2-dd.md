# U2 제어 순수 함수 — Detail design

HLD: [U2-hld.md](U2-hld.md) (승인 10/08). 팀 계약은 docs/interfaces 가 우선이다. 이 문서의 제안값은 미측정 제안값이다(ADR-0012 승인 수치 목표의 범위 밖).

- 상태: **DD 승인(박병후, 10/08)**, r2 독립 재검 반영 승인(10/08). Pseudo code: [U2-pseudo.md](U2-pseudo.md)

## 0. 결정 요약 (HLD 6절 "DD 에서 정할 것"의 답)

| 항목 | 결정 | 이유 |
|---|---|---|
| dt | 실제 틱 간격 `now − 지난 계산 시각`. 첫 틱·0 이하면 `1/rate_hz`, `2/rate_hz` 보다 크면 `2/rate_hz` 로 자른다 | 가속 제한이 실제 시간에 맞아야 한다. executor 가 잠깐 멈춘 뒤 한 틱에 큰 속도 변화를 허용하지 않게 상한 |
| 가속 제한의 직전 속도 | **마지막으로 발행한 속도**(노드가 보관, goal 시작 때 0) | 0 유지·예외 경로의 0 도 포함해야 실제 명령 흐름과 맞다 |
| Z 속도 | `v_z = kp_z × (z_목표 − z_보정TCP)` 를 phase 별 상한으로 자른다. 내려갈 때 `descend_speed`, 올라갈 때 `lift_speed`. GRASP·VERIFY·LIFT 외 0 규칙 phase 는 0 | P 로 다가가면 목표 근처에서 저절로 느려져 부드럽게 닿는다. 상한으로 빠르기 제한 |
| 사각 판정의 TCP z | **보정 TCP z** 로 바꾼다 (U1 은 원본 pose z) | 모든 플래그(사각·높이 도달·영역)가 같은 TCP 를 보게. 하강 50 mm/s × 80 ms ≈ 4 mm 차이 (히스테리시스 5 mm 보다 작아 깜빡임 없음) |
| 관측 나이 | `now − 마지막 유효 관측 stamp`(촬영 시각 기준, 음수면 0) | 정보가 얼마나 묵었나는 촬영 시각이 기준. 정상 나이 = 카메라 → 발행 52~61 ms(p95, measurements-1008 #1·#8) + 틱 위상 0~33 ms = **52~94 ms** → 제안 0.15 s (7절) |
| 예측 지평 | `h = max(now − box_stamp, 0) + latency_offset`, 다시 `max(h, 0)`. 앞의 max 가 걸리면 `dt_clipped=True` | Δt 음수 결정(HLD 0절). offset 은 음수도 올 수 있다(튜닝) |
| 외삽 지평 | `h = max(now − pose_stamp, 0) + pose_lag`. 쓰는 지평 `h_used = min(h, extrap_max)`, `h > extrap_max` 면 `capped=True`(로그) | **상한에서 멈추는 외삽**(r2, 박병후 승인). 원본 pose 복귀는 가장 오래된 값이라 48 mm/s 에서 약 5.8 mm 계단 → P 속도 계단. 상한에서 멈추면 계단 없이 오차가 서서히 커지고, 길게 끊기면 U1 `pose_stale` 이 끝낸다. 지시서·CONTRACT("상한 초과 시 외삽 없음")와 다름 → 회신에 적음 |
| 오차 분해 | 벨트 방향 `d` = direction_base 의 xy 를 다시 정규화(z 버림). `along = e_xy · d`, `cross = ‖e_xy − along·d‖`. 비교는 `|along|` | direction_base 는 z = 0 이지만 정규화로 1 ± 0.01 오차도 흡수. 벨트 속도 벡터도 같은 `d` 로 만든다(`belt_v = speed × d`, z = 0) |
| **벨트 방향 기다리기** (재검 r2) | FF+P 결과의 벨트 방향 성분이 0 보다 작으면 그 성분만 0 으로 (`v -= min(v·d, 0)·d`). 가로 성분은 그대로 | 박스가 상류에 있을 때 P 가 상류로 돌진 → 가속 제한 때문에 못 멈춰 오버슈트·x_min 이탈(HLD 0절 시뮬레이션). FF 만일 때는 벨트 방향 성분 = 벨트 속도 > 0 이라 영향 없음 |
| PREPARE 안 보임 (재검 r2) | TRACK 과 같이 **FF** (유효 관측이 있을 때). 이전 안: 0 | ① 한 프레임 invalid 에 감속했다 다시 가속하는 덜컹임 ② 재시도로 PREPARE 복귀 때 xy 를 세우면 상승(약 1.8 s) 동안 박스가 약 84 mm 앞서 간다 |
| 정렬 높이 조건 | `|z_보정TCP − z_접근| ≤ height_tol` | HLD 3절 |
| clamp 0 예외 | 단계 규칙이 낸 속도가 **정확히 0 벡터**(`not np.any(v)`)일 때만 가속 제한 없이 0. LIFT 처음(xy 0, z 상승)은 0 벡터가 아니라 가속 제한을 받는다. 벡터 가속 제한이 xy 감속과 z 가속을 **나눠 쓰므로** Δv = (−48, 0, +80) mm/s → 약 28 틱(0.93 s)에 걸쳐 바뀌고 z 상승 시작도 그만큼 느리다 | 정지 = 즉시 0(HLD 승인). LIFT 의 xy 감속은 박스를 쥔 채 벨트와 같이 가다가 서서히 멈추는 것이라 오히려 안전. 첫 0.1 s 동안 박스가 벨트에 닿은 채 약 5 mm/s 상대 미끄럼(작음) — U8a 에서 확인, 문제면 LIFT 만 z 우선 clamp |
| 영역 판정 | 보정 TCP x, 경계값은 구간 안(`x_min ≤ x ≤ x_max` 이면 None). **x_max 는 유효값 620**(측정 구간 638 − gateway 감속 11.5 − 여유, r4) | gateway 가 `x + v²/2a ≥ 638` 에서 x 를 자르고 램프로 635~638 에 선다 → 638 이면 belt_servo 판정이 명령 외삽에 기대 확정적이지 않다 (PR #122 학민 리뷰, 박병후 결정) |
| **pose 값 갱신 0.1 s** (r4) | 외삽 기준 stamp = **위치 값이 바뀐 첫 메시지의 stamp**(`pose_value_stamp`). 같은 값이 반복되면 처음 stamp 유지. `pose_stale` 판정의 수신 시각은 메시지마다 따로 | gateway `pose_source: service` 는 50 Hz 로 보내지만 값은 0.1 s 마다만 바뀐다(ADR-0010 69행). 메시지 stamp 로 계산하면 값의 실제 나이 60~160 ms 중 60~80 ms 만 외삽 → 48 mm/s 에서 0~4.8 mm 톱니가 along 3 mm 허용치보다 크다. joint_states(20 ms 갱신)에서도 그대로 맞다 (PR #122 학민 리뷰 1안, 박병후 결정) |
| **파지 바닥 막힘** (r4) | 파지 도달 문턱(윗면 − 19 + height_tol) < gateway z 하한 78 + 1 mm 이면 reach = `Z_MIN` → OUT_OF_REACH(cause `REACH_Z_MIN`). x 가 먼저 | gateway 가 −z 를 자르면 `at_grasp_height` 가 영영 참이 안 되고 DESCEND 는 사각이라 LOST 도 없다. box_tracker 의 `position_base.z` 는 호모그래피 설정 상수 `plane_z_mm` 로 고정이라(box_tracker.py, ray–plane 교차) z 에는 프레임 잡음·핸드아이 오차가 없다 → `Z_MIN` 은 **plane_z 설정이 실제와 어긋날 때만** 걸리고, 걸리면 모든 goal 이 첫 관측 틱에 `REACH_Z_MIN` 으로 끝난다(설정 오류를 바로 드러냄). 판정식은 물리 조건 그대로 "at_grasp 문턱이 실제로 내려갈 수 있는 바닥 + 여유보다 낮음"(리뷰 원안 "목표 < 78 + tol" 보다 tol 만큼 느슨). 여유 1 mm 는 접근 끝 속도 kp_z × height_tol ≤ 약 10 mm/s 에서 성립(r4 재검: 4 mm/s 면 gateway 정지 ≈ 78.3 mm) |
| 새 파라미터 교차 검사 | 2절 표 (11개) | gateway #104 값·물리 조건 |
| 로그 | 틱 키 15개 추가(4절, 전환 플래그·dt 포함), 시도 키 변경 없음 | 게이트 집계(U6')에 영향 없게, "왜 하강 안 했나"를 로그로 바로 재현 |

## 1. control.py

모두 순수 함수. NumPy `np.ndarray` shape (3,), 단위 m·m/s·s. ROS·시계·파일을 쓰지 않는다. phase 이름은 `fsm` 상수를 import 해서 쓴다.

### 1.1 설정 묶음

```python
@dataclass(frozen=True)
class ControlConfig:            # 노드가 기동 때 한 번 만든다 (READY 일 때만)
    belt_dir_xy: np.ndarray     # 벨트 방향 단위벡터 (x, y, 0), direction_base 의 xy 를 다시 정규화
    belt_v: np.ndarray          # 벨트 속도 벡터 m/s = speed_cmps/100 × belt_dir_xy (z = 0)
    latency_offset_s: float     # timing.latency_offset_ms / 1000
    pose_lag_s: float           # input.pose_lag_ms / 1000
    pose_extrap_max_s: float    # input.pose_extrap_max_ms / 1000
    blind_entry_max_age_s: float
    kp_xy: float                # control.kp_per_s
    kp_z: float                 # control.kp_z_per_s
    align_along_m: float        # control.align_tol_along_mm / 1000
    align_cross_m: float        # control.align_tol_cross_mm / 1000
    v_max: float                # limits.max_speed_mps
    a_max: float                # limits.max_acc_mps2
    approach_dz: float          # + z.approach_above_top_mm / 1000
    grasp_dz: float             # − grasp.tcp_z_below_top_mm / 1000  (음수)
    lift_dz: float              # + z.lift_above_top_mm / 1000
    descend_speed: float        # z.descend_speed_mps
    lift_speed: float           # z.lift_speed_mps
    height_tol_m: float         # z.height_tol_mm / 1000
    x_min: float                # reach.x_min_mm / 1000
    x_max: float                # reach.x_max_mm / 1000
    dt_nominal: float           # 1 / rate_hz

def config_from_values(values: dict) -> ControlConfig   # mm·ms·cm/s → m·s·m/s 변환과 np.asarray(dtype=float)(ROS array.array 대응)는 여기 한 곳
```

### 1.2 기본 함수 (지시서 함수 목록)

| 함수 | 입력 | 출력 | 규칙 |
|---|---|---|---|
| `predict(p_obs, box_stamp, now, belt_v, latency_offset)` | 관측 위치 m, 촬영 시각 s, 지금 s, 벨트 속도 m/s, offset s | `(p_pred, horizon_s, dt_clipped)` | `p_obs + belt_v × h`, h 는 0절 |
| `pose_value_stamp(prev, position, stamp)` | 직전 (값, stamp), 새 위치, 새 stamp | (값, 그 값이 처음 온 stamp) | 같은 값이면 prev 그대로 (r4) |
| `grasp_floor_blocked(top_z, cfg)` | 박스 윗면 z, 설정 | bool | `top_z + grasp_dz + height_tol < z_min + 0.001` (r4) |
| `tcp_now(pose_xyz, pose_stamp, pose_lag, last_cmd_v, now, extrap_max)` | 원본 pose m, pose stamp s, lag s, 마지막 발행 속도 m/s, 지금, 상한 s | `(tcp, horizon_s, capped)` | `pose + last_cmd_v × min(h, 상한)`, h > 상한이면 capped=True. horizon_s 는 자르기 전 h(로그용) |
| `tcp_target(p_pred, z_target)` | 예측 박스 윗면 m, 목표 z m | TCP 목표 m | `(p_pred.x, p_pred.y, z_target)` |
| `split_error(e, dir_xy)` | 오차(목표 − TCP) m, 벨트 방향 | `(along, cross)` m | 0절 |
| `ff_p(e, belt_v, dir_xy, kp_xy, use_p)` | 오차, 벨트 속도, 벨트 방향, Kp, P 사용 여부 | xy 속도 (z = 0) | `v = belt_v_xy + (kp_xy × e_xy if use_p else 0)`, 그 뒤 벨트 방향 성분이 음수면 0 으로(기다리기, 0절) |
| `z_plan(phase, top_z, cfg)` | phase, 박스 윗면 z, 설정 | `(z_target or None, v_down_max, v_up_max)` | 1.3 표 |
| `z_speed(z_target, tcp_z, kp_z, v_down_max, v_up_max)` | | z 속도 | `kp_z × (z_target − tcp_z)` 를 `[−v_down_max, +v_up_max]` 로 |
| `clamp(v, prev_v, v_max, a_max, dt)` | 원하는 속도, 직전 발행 속도, 상한, dt | `(v_out, clamped)` | ① v 가 0 벡터면 `(0, False)` ② ‖v‖ > v_max 면 크기만 v_max ③ ‖v − prev‖ > a_max·dt 면 `prev + Δv × (a_max·dt/‖Δv‖)`. ②③ 중 하나라도 걸리면 clamped |
| `in_reach(tcp_x, x_min, x_max)` | | `None \| "X_MIN" \| "X_MAX"` | 경계값은 안 |
| `effective_dt(prev_calc, now, dt_nominal)` | | dt s | 0절 |
| `zero_cmd()` | | `np.zeros(3)` | |

- 지시서의 `tcp_target(position_base, grasp_dz)` 는 위처럼 "예측 박스 + phase 별 z" 로 일반화했다(파지 높이 = `top_z + grasp_dz`).
- 지시서의 `ff_p(target, tcp_now, belt_v_vec, kp_xy, kp_z)` 는 xy(`ff_p`)와 z(`z_speed`)로 나눴다. Z 는 FF 가 없고(벨트 z 성분 0) 상한이 phase 마다 달라서.

### 1.3 단계별 규칙 (HLD 3절을 함수 입력으로)

| phase | xy 규칙 (`xy_rule`) | z_plan → (목표, 내려갈 상한, 올라갈 상한) |
|---|---|---|
| PREPARE | 보이면 `FF_P`, 아니면 `FF` (재검 r2) | (top + approach_dz, descend_speed, lift_speed) |
| TRACK | 보이면 `FF_P`, 아니면 `FF` | (top + approach_dz, descend_speed, lift_speed) |
| DESCEND | 보이면 `FF_P`, 아니면 `FF` | (top + grasp_dz, descend_speed, 0) — 하강 중 위로는 안 감 |
| GRASP | `FF` | (None) → z 속도 0 |
| LIFT | `ZERO` | (top + lift_dz, 0, lift_speed) — 위로만 |
| VERIFY | `ZERO` | (None) → 0 |

- pose 가 없으면(geo 없음) 0 벡터 (`rule="ZERO_NO_POSE"`). 유효 관측이 한 번도 없으면(`top_z is None`) 0 벡터 (`rule="ZERO_NO_OBS"`).
- stopping 또는 terminal 이면 0 벡터 (`rule="ZERO_STOP"`), 다른 계산을 보지 않는다.
- PREPARE 에서 안 보이면 xy 는 FF(벨트와 같이), z 는 접근 높이로 간다. 재시도로 PREPARE 에 돌아왔을 때 박스와 같이 가면서 파지 높이(사각)에서 접근 높이로 올라가 다시 보게 하려는 것이다.
- `rule` 은 xy 규칙 이름이다. LIFT 는 rule = ZERO 지만 z 는 올라간다(로그 `cmd_vel_mps` 로 구분).

### 1.4 틱 입구 두 개

```python
@dataclass(frozen=True)
class Geometry:                 # ② 기하 계산 결과 (phase 와 무관한 값 + 플래그)
    tcp: np.ndarray             # 보정 TCP
    tcp_horizon_s: float        # 외삽 지평
    tcp_extrap_capped: bool     # 외삽 지평이 상한에서 잘렸나
    visible: bool               # 사각 아님 + 최신 메시지 valid
    has_obs: bool               # 유효 관측이 한 번이라도 있나
    p_pred: np.ndarray | None   # 예측 박스 윗면 중심
    pred_horizon_s: float | None
    dt_clipped: bool
    top_z: float | None         # 마지막 유효 관측 윗면 z
    obs_age_s: float | None     # 마지막 유효 관측 나이 (촬영 시각 기준)
    err_along: float | None     # 접근 높이 목표 기준 xy 오차의 벨트 방향 성분
    err_cross: float | None
    aligned: bool
    at_grasp_height: bool
    at_lift_height: bool
    reach: str | None

def geometry(tcp_est, obs_xyz, obs_stamp, visible, now, cfg) -> Geometry
    # tcp_est = 노드가 먼저 부른 tcp_now() 결과 (tcp, horizon, capped) — 사각 판정에도 같은 값을 쓰려고 노드가 먼저 계산한다(3절)
    # obs_* = 마지막 유효 관측 (없으면 None). visible 은 노드가 계산해 넘긴다

@dataclass(frozen=True)
class Command:                  # ⑤ 이번 틱 발행 속도
    vel: np.ndarray             # clamp 뒤
    rule: str                   # FF_P | FF | ZERO | ZERO_NO_POSE | ZERO_NO_OBS | ZERO_STOP
    tcp_target: np.ndarray | None
    error: np.ndarray | None    # tcp_target − tcp
    clamped: bool

def command(phase, stopping, terminal, geo, prev_v, dt, cfg) -> Command
```

- `aligned` = visible ∧ |err_along| ≤ align_along ∧ err_cross ≤ align_cross ∧ |tcp.z − (top + approach_dz)| ≤ height_tol ∧ obs_age ≤ blind_entry_max_age.
- `at_grasp_height` = has_obs ∧ tcp.z ≤ top + grasp_dz + height_tol.
- `at_lift_height` = has_obs ∧ tcp.z ≥ top + lift_dz − height_tol.
- 플래그는 phase 와 무관하게 계산하고, 어느 phase 에서 쓰는지는 FSM 이 정한다(U1 전이표).
- `visible` 은 노드가 계산해 넘긴 값을 그대로 저장만 한다(geometry 안에서 다시 판단하지 않음). 관측이 없으면 False.

**오차 두 개 — 어디에 쓰나**

| 값 | 기준 높이 | 쓰는 곳 |
|---|---|---|
| `Geometry.err_along`·`err_cross` | 접근 높이 목표 (xy 만 의미) | `aligned` 판정, 로그 `err_along_m`·`err_cross_m` |
| `Command.error` | 이번 phase 의 z 목표 | 속도 계산(P), 로그 `error_m` |

### 1.5 에러 경로

| 상황 | 처리 |
|---|---|
| pose 없음 | 노드가 `geometry` 를 부르지 않고 0 명령(`ZERO_NO_POSE`) + 플래그 기본값(False·None). pose 끊김은 U1 `pose_stale` 이 끝낸다 |
| 유효 관측 없음 | `has_obs=False`, 예측·오차·플래그 None·False, 명령 `ZERO_NO_OBS` |
| box stamp 가 미래 | 지평 0 으로 자름 + `dt_clipped=True` (로그) |
| pose stamp 가 미래 | 외삽 지평 = lag 만 |
| 외삽 상한 초과 | 상한까지만 외삽, `tcp_extrap_capped=True` (로그) |
| dt 0·음수·너무 큼 | `effective_dt` 로 정리 |
| NaN 입력 | box: U1 `_on_box` 에서 `position_valid=true` 라도 좌표에 NaN·inf 가 있으면 **invalid 로 취급**(마지막 유효 관측을 덮지 않음). pose: 변환 때 `np.isfinite` 검사, 아니면 pose 없음으로 본다 |

## 2. params.py 추가 (9개) — 이름은 브리핑 승인. 제안값의 근거·확정 시점은 7절

| 이름 | 타입·단위 | belt_servo.yaml 값 | 개별 검사 |
|---|---|---|---|
| `input.pose_lag_ms` | float, ms | **60** (measurements-1008 #6. gateway pose 방식이 바뀌면 재측정) | ≥ 0 |
| `input.pose_extrap_max_ms` | float, ms | null (제안 200) | > 0 |
| `input.blind_entry_max_age_s` | float, s | null (제안 0.15) | > 0 |
| `control.kp_z_per_s` | float, 1/s | null | > 0 (0 이면 높이를 못 바꾼다) |
| `control.align_tol_along_mm` | float, mm | null (제안 3) | > 0 |
| `control.align_tol_cross_mm` | float, mm | null (제안 5) | > 0 |
| `z.descend_speed_mps` | float, m/s | null (제안 0.05, 상한 약 0.06 — U4 에서 바닥 근처 정지 거리 확인) | > 0 |
| `z.lift_speed_mps` | float, m/s | null (제안 0.08 = v_max. 쥐는 힘 14 N 이면 0.1 m/s² 가속에서 미끄러질 위험은 작다 — 추정) | > 0 |
| `z.height_tol_mm` | float, mm | null (제안 2) | > 0 |

**교차 검사 (U1 `_cross_checks` 에 추가, 11개)**

| # | 검사 | 이유 |
|---|---|---|
| 1 | `limits.max_speed_mps < 0.1` | gateway 속도 자르기 100 mm/s(`servo_guard.py` `max_speed_mm_s`) 보다 **작게** — 같으면 어디서 잘렸는지 구분 불가 |
| 2 | `limits.max_acc_mps2 ≤ 0.1` | gateway 는 가속을 **자르지 않고** speedl 의 acc 인자(로봇 램프, `servo_acc` 100 mm/s²)로 넘긴다. belt_servo 가 이보다 급하게 바꾸면 로봇이 명령을 못 따라와 명령 ≠ 실제 → `tcp_now` 외삽(마지막 명령 속도 가정)이 틀린다 |
| 3 | `belt.speed_cmps / 100 < limits.max_speed_mps` | 벨트보다 느리면 따라갈 수 없다 (P 여유가 충분한지는 검사하지 않음 — 7절 주석) |
| 4 | `z.descend_speed_mps ≤ limits.max_speed_mps` | 어차피 잘리지만 설정 실수를 기동 때 잡는다 |
| 5 | `z.lift_speed_mps ≤ limits.max_speed_mps` | 같음 |
| 6 | `input.pose_extrap_max_ms ≥ input.pose_lag_ms + 120` (r4) | pose 값은 0.1 s 마다만 바뀔 수 있고(ADR-0010 69행) 바뀐 값의 첫 메시지는 최대 20 ms 늦게 온다 → 정상 지평 = lag ~ lag + 120. 작으면 정상 운전에서도 상한에 걸린다. 상수 `POSE_VALUE_PERIOD_MS = 100`·`POSE_PERIOD_MS = 20` |
| 7 | `control.align_tol_along_mm ≤ control.align_tol_cross_mm` | 벨트 방향이 더 엄격 (ADR-0009) |
| 8 | `control.align_tol_cross_mm ≤ 10` (확정, 박병후) | "cross 도 여유롭게 두지 않는다". 상수 `ALIGN_CROSS_MAX_MM = 10` — 그리퍼 가로 여유 24.5 mm 의 절반 아래 |
| 9 | `control.kp_z_per_s × z.descend_speed_mps ≤ limits.max_acc_mps2` | P 접근은 상한에서 벗어나는 순간(남은 거리 v/kp) 감속률 kp·v 가 필요하다. 남은 거리 안에 멈추려면 `kp·v ≤ 2·a_max` 면 되고(넘으면 파지 높이 아래로 지나침, 여유 8 mm), 여기서는 로봇 반응 지연(62 ms)을 생각해 **2배 여유**를 둔 `≤ a_max` |
| 10 | `z.height_tol_mm < z.approach_above_top_mm − (z.vision_cutoff_above_top_mm + 5)` | 접근 높이 도달 범위가 사각 이탈 높이(cutoff + 히스테리시스 5 mm) 아래로 내려가면 정렬 판정 중에 박스가 안 보일 수 있다 |
| 11 | `belt.direction_base` 의 수평(xy) 길이 ≥ 0.99 | 벨트는 수평. `[0, 0, 1]` 같은 값도 노름 검사(1 ± 0.01)는 통과하므로 따로 막는다(`belt_dir_xy` 정규화 0 나누기 방지) |

상수 `GATEWAY_MAX_SPEED_MPS = 0.1`·`GATEWAY_ACC_MPS2 = 0.1` 은 **gateway 파라미터 기본값의 사본**이다(`src/voss_robot/voss_robot/servo_guard.py`, #104 머지 `014a7b4`). 학민이 값을 바꾸면 함께 바꾼다(주석에 명시). bringup 이 같은 값을 넘기는 파라미터화는 G0 뒤 검토.

## 3. belt_servo.py 연결

| 위치 | 변경 |
|---|---|
| `__init__` | `self._last_cmd = np.zeros(3)` (마지막 발행 속도), `self._ctrl: ControlConfig \| None` (READY 일 때 `config_from_values`) |
| `GoalCtx` | `last_calc: float \| None = None` (dt 용), `geo: Geometry \| None`, `cmd: Command \| None` (로그용) |
| `_publish(vel)` | 발행 후 `self._last_cmd = vel` (0 유지·예외 경로 포함 모든 발행) |
| `_on_box` | `position_valid=true` 라도 좌표가 NaN·inf 면 invalid 로 취급 (1.5) |
| `_on_pose` (r4) | `_pose = (msg, 수신 시각)` 은 메시지마다(끊김 판정), `_pose_value = pose_value_stamp(...)` 는 값이 바뀔 때만 stamp 갱신. `_tcp_estimate` 는 `_pose_value` 로 외삽 |
| `_startup_check` (r4) | READY 면 "pose_lag_ms=60 — gateway pose_source: service 기준 측정" 로그 |
| `_build_event` | ① pose → `control.tcp_now` (pose 있을 때) ② **사각 판정에 보정 TCP z** ③ U1 `input_flags` 그대로 ④ visible = 사각 아님 ∧ entry 있음 ∧ 최신 valid ⑤ `control.geometry` → aligned·at_grasp_height·at_lift_height·reach 를 TickEvent 에 ⑥ goal 중 마지막 유효 관측의 `position_source` 가 바뀌면 WARN 로그 1회(리셋은 U9, HLD 4절 규칙 8) |
| `_tick_goal` | `vel = ZERO` 자리. 순서: ① `dt = effective_dt(ctx.last_calc, now, …)` ② `ctx.last_calc = now` ③ `cmd = control.command(tr.state.phase, tr.state.stopping, tr.terminal, geo, self._last_cmd, dt, cfg)` ④ `self._publish(cmd.vel)` |
| `_tick_values` | U2 키 채우기(4절) |
| `_snapshot_values` | U2 키 모두 null, 단 `cmd_rule = "ZERO_STOP"` (0 유지·예외 경로) |

- pose 가 없는 틱: geometry 를 부르지 않고 `command` 에 `geo=None` → `ZERO_NO_POSE`.
- stopping·terminal 은 `command` 첫 줄에서 0 (U1 회신 ⑤의 "항상 0" 유지).
- 메시지 → 숫자: `position_base` → `np.array([x, y, z])`, pose → `np.array([...])`, stamp → `stamp_s` (U1 함수).

## 4. log_schema.py — 틱 키 추가 15개

| 키 | 값 |
|---|---|
| `tcp_now_m` | 보정 TCP [x, y, z] (`tcp_pose_m` 은 원본 그대로) |
| `tcp_extrap_s` | 외삽 지평 |
| `tcp_extrap_capped` | bool (외삽 지평이 상한에서 잘림) |
| `predict_horizon_s` | 예측 지평 |
| `predict_dt_clipped` | bool |
| `obs_age_s` | 마지막 유효 관측 나이 |
| `visible` | bool |
| `err_along_m`·`err_cross_m` | 정렬 판정용 분해 오차 |
| `cmd_rule` | FF_P · FF · ZERO · ZERO_NO_POSE · ZERO_NO_OBS · ZERO_STOP |
| `aligned`·`at_grasp_height`·`at_lift_height`·`reach` | 이번 틱 전환 플래그 (재검 r2 — "왜 하강 안 했나" 재현, aligned 깜빡임 확인) |
| `dt_s` | `effective_dt` 값 (`clamped` 분석용) |

기존 `predicted_m`·`tcp_target_m`·`error_m`·`clamped` 를 채운다. 시도 키는 그대로.

## 5. 테스트 목록

**test_control.py (신규)** — 지시서 완료 기준 ↔ 테스트

| 완료 기준 | 테스트 |
|---|---|
| Δt 0·음수 | `test_predict_dt_zero_returns_obs` · `test_predict_negative_dt_clipped_and_flagged` · `test_predict_latency_offset_adds` · `test_predict_negative_offset_floor_zero` |
| tcp_now lag 0·60·외삽 상한 | `test_tcp_now_lag0_same_stamp_is_raw` · `test_tcp_now_lag60_moves_2_88mm_at_48mmps` · `test_tcp_now_over_max_caps_at_max` · `test_tcp_now_future_stamp_uses_lag_only` |
| 예측과 pose 시각 차 | `test_geometry_box_and_pose_different_stamps` (박스 stamp 와 pose stamp 가 다를 때 오차 = 각자 지금으로 옮긴 값의 차) |
| 영역 끝 OUT_OF_REACH | `test_in_reach_boundaries` (x_min·x_max 정확히 = None, 1 µm 밖 = X_MIN·X_MAX) · `test_geometry_reach_uses_corrected_tcp` |
| 속도·가속 포화 | `test_clamp_speed_keeps_direction` · `test_clamp_acc_limits_change` · `test_clamp_speed_and_acc_both` · `test_clamp_zero_is_immediate` · `test_clamp_under_limits_untouched` · `test_effective_dt_first_tick_and_caps` · `test_effective_dt_negative_is_nominal` |
| Kp 0 | `test_ff_p_kp0_is_belt_only` · `test_ff_p_no_p_when_not_used` |
| 기다리기 (재검 r2) | `test_ff_p_box_upstream_waits_along_zero` (상류 오차 → 벨트 방향 0, 가로는 P 유지) · `test_ff_p_box_downstream_adds` |
| z_plan 단계별 값 | `test_z_plan_each_phase` (6 phase 목표·상한) · `test_z_speed_caps_down_and_up` |
| 단계 규칙 (HLD 3절) | `test_command_prepare_visible_ff_p` · `test_command_prepare_not_visible_ff_xy_z_to_approach` · `test_command_track_visible_ff_p_and_z` · `test_command_track_not_visible_ff_only` · `test_command_descend_visible_ff_p_z_down` · `test_command_descend_blind_ff_only` · `test_command_grasp_ff_only_z_zero` · `test_command_lift_xy_zero_z_up` · `test_command_verify_zero` · `test_command_stopping_terminal_zero` · `test_command_no_obs_zero` · `test_command_no_pose_zero` |
| 전환 플래그 | `test_aligned_needs_all_five` (조건 하나씩 깨서 False) · `test_split_error_along_cross` · `test_at_grasp_and_lift_height` · `test_geometry_no_obs_still_reach` |
| 설정 변환 | `test_config_from_values_units` |
| r4 (PR #122 리뷰) | `test_pose_value_stamp_keeps_first_stamp_while_value_repeats` · `test_repeated_pose_value_extrapolates_by_real_age` · `test_grasp_floor_blocked_reach_z_min` · `test_reach_x_before_z_min` · (test_node) `test_pose_value_stamp_held_while_value_repeats` · `test_repeated_pose_value_extrapolates_until_pose_stale` · `test_nan_pose_value_gives_no_pose_zero` |

**test_params.py 추가**: 새 키 null → missing · `pose_lag_ms` 0 허용 · 교차 검사 11개 각각 거부 1건씩.

**test_log_schema.py**: 새 키 포함 확인(기존 "틱 키 전체" 테스트가 TICK_FIELDS 로 잡음).

**test_node.py·test_action_e2e.py 갱신**: READY_ARGS 에 새 키 9개. test_node 추가 1건 — `_on_box` NaN 좌표 valid 메시지는 invalid 로 저장(마지막 유효 관측 유지). e2e 추가 1건 — `test_prepare_with_visible_box_moves_then_cancel_zero`: 가짜 box(valid) + pose → PREPARE 에서 0 이 아닌 servo_cmd(x 성분 ≈ 벨트 방향) → 취소 → stop OK → CANCELED, 마지막 servo_cmd 0. 기존 "박스 없음 → 전부 0" 은 그대로 통과해야 한다.

## 6. 남는 것 (U2 밖)

- `aligned` 다음 DESCEND 중 오차가 커지면 중단할지 → U9(재시도·안정화).
- 외삽에 실제 속도 대신 명령 속도를 쓰는 한계 → U4 실기 검증. **belt_servo 는 gateway 의 자르기(속도·z 하한·x 구간)·거부를 모르고 `_last_cmd` 로 외삽한다** — gateway 가 자르거나 거부해 로봇이 선 동안에는 pose 값이 반복돼 외삽 지평이 상한까지 커지고 TCP 를 **최대 `pose_extrap_max × 마지막 명령 속도` = 0.2 s × 48 mm/s ≈ 9.6 mm** 앞서 본다(r4 재검). x 는 X_MAX(620), z 는 Z_MIN 이 대부분 덮지만, DESCEND 끝에서 z 만 잘리는 경계에서는 at_grasp 가 실제 도달보다 ≤ 1 mm 일찍 참이 될 수 있다 (PR #122 학민 리뷰)
- DESCEND 시간 상한 → U9 유지(r4 결정). 하강이 막히는 원인 중 z 하한은 `Z_MIN` 으로, x 끝은 X_MAX(유효 620)로 끝난다.
- 제안값 전부 → U4 실기 튜닝, measurements 기록 후 채움.
- `aligned` 연속 N 틱 유지 조건(DEC-05 의 "유지 시간") → U4 에서 틱 로그 `aligned` 깜빡임을 보고 필요하면 추가(U9). 지금은 한 틱 판정.
- `position_source` 가 바뀔 때 예측 리셋 → U9 (U2 는 경고 로그만).
- 외삽 상한 초과 처리는 **상한까지 외삽**으로 결정(10/08 박병후). 지시서·CONTRACT 문구와 달라 주관 세션에 회신.

## 7. 실기에서 정할 값 — 제안값의 근거와 확정 시점

**원칙.** 아래 값은 전부 **미측정 제안값**이다(ADR-0012 승인 수치 목표의 범위 밖 — ADR-0012 가 belt_servo acc·하강 속도 등을 명시적으로 제외). `belt_servo.yaml` 에는 null 로 두고 주석에만 제안값을 적는다(측정값인 `input.pose_lag_ms` 60 만 예외). 실기에서 정하면 ① `docs/measurements-10xx.md` 에 값·조건·원본 위치를 적고 ② 같은 PR 로 yaml 의 null 을 채우고 ③ 결정이면 DESIGN.md 카드·ADR 에 남긴다. null 이 남아 있으면 READY 거부이므로, 실기 시험(U4) 때는 시험값을 launch 인자로 넘기고 그 값을 measurements 에 "시험값"으로 기록한다.

**의존 연쇄.** 위가 바뀌면 아래도 다시 계산한다.

```
gateway #104 (max_speed_mm_s 100 = 속도 자르기 · servo_acc 100 = 로봇 램프, 가속은 자르지 않음)   ← 김학민, 머지 014a7b4. 100 mm/s 의 근거는 #104 본문 확인 필요
   └─ belt_servo limits.max_speed_mps 0.08 · limits.max_acc_mps2 0.1   ← 위 상한에 맞춘 제안값 (미측정)
        └─ z.descend_speed_mps · z.lift_speed_mps · control.kp_z_per_s  ← v_max·a_max 에서 계산한 제안값
```

### 7.1 U2 에서 추가·사용하는 값

| 키 | yaml | 제안값 | 근거 | 성격 | 정하는 단위 · 측정 방법 |
|---|---|---|---|---|---|
| `limits.max_acc_mps2` | null | 0.1 | speedl 실로봇 시험 acc 100 mm/s²: 시작 지연 acc 20 → 114 ms, acc 100 → 62 ms (measurements-1006 #3). gateway #104 `servo_acc` 100 은 로봇 speedl 램프 — gateway 는 가속을 **자르지 않는다**(`servo_guard.py`). 더 크게 주면 로봇이 못 따라와 명령 ≠ 실제가 되어 TCP 외삽이 틀린다 → 위쪽 한계(교차 검사 2). **그 시험은 5 mm/s·10 mm 이동뿐**이고, 추종 속도에서의 값은 ADR-0010 이 "T26·T27 실기에서 정한다"로 미뤘다 | 실로봇에서 동작 확인한 유일한 값 = gateway 상한. 추종 성능으로 고른 값 아님 | U4: 48 mm/s 추종에서 `clamped` 비율, 오차 수렴 시간, 정지 거리 |
| `limits.max_speed_mps` | null | 0.08 | 위쪽 경계 gateway 100 mm/s — 같은 값이면 belt_servo clamp 와 gateway 자르기가 겹쳐 어디서 잘렸는지 구분 불가 → 그 아래. 아래쪽 경계 벨트 48 mm/s(교차 검사 belt < v_max). 그 사이에서 P 따라잡기 여유 약 30 mm/s 를 더함(이 여유는 주석일 뿐 교차 검사로 보장하지 않음) | 판단값 (측정 근거 없음) | U4 (같은 기록) |
| `control.kp_per_s` | null | — | 실측 전 근거 없음 | — | U4: Kp 0(FF 만) → FF+P 단계적으로, 횡 오차 감소 확인 |
| `control.kp_z_per_s` | null | descend 0.05 이면 ≤ 2 /s, 0.06 이면 ≤ 1.7 /s | 교차 검사 9 `kp_z × descend_speed ≤ a_max`: 지나침(파지 높이 아래 여유 8 mm)이 생기는 경계는 `kp·v > 2·a_max` 이고, 반응 지연을 생각해 2배 여유를 둔 값(2절). **kp_z 가 사각 통과 시간을 정한다**: kp_z 2·상한 50 mm/s, 접근 +40 → 파지 −19 mm 에서 사각 진입 0.83 s, 파지 높이 도달 2.17 s → **사각 구간 FF 만 약 1.33 s**(30 Hz·가속 0.1 시뮬레이션, 10/08 재검 r2) | 계산 (a_max 0.1 전제) | U4: z 접근 오버슈트 기록 |
| `z.descend_speed_mps` | null | 0.05 (상한 약 0.06) | ① DESCEND 중 xy 에 벨트 FF 48 mm/s 가 같이 나가므로 z 몫 = √(80² − 48²) ≈ 64 mm/s (v_max 0.08 기준, P 가 xy 를 더 쓰면 줄어듦) ② 사각 구간 약 29 mm 를 FF 만으로 지나는 시간은 **상한이 아니라 kp_z 가 정한다** — P 접근이라 사각 구간 대부분이 상한 아래(감속 구간)다(위 kp_z 행: 약 1.33 s). 상한은 접근 높이에서 사각까지의 초반 구간만 줄인다. (이전 "30 mm/s ≈ 1 s, 60 mm/s ≈ 0.5 s" 는 등속 가정이라 정정) ③ 정지 시 더 가는 거리(추정) = 반응 62 ms × v + v²/(2a): 30 mm/s ≈ 6 mm, 60 mm/s ≈ 22 mm. P 접근이라 바닥 근처에서는 이미 느리고 gateway 에 z 하한 자르기가 있음. 위험한 경우는 하강 도중 watchdog·비상정지 | 계산 (v_max·a_max 전제) | U4·U8a: 바닥 근처 정지 거리, 하강 중 정지 시 z 최저점 |
| `z.lift_speed_mps` | null | 0.08 (= v_max) | LIFT 는 xy 0 이라 v_max 전부 사용 가능. 50 mm 상승 기준 가속 제한 0.1 m/s² 에서 최고속 √(a·d) ≈ 71 mm/s → 상한 0.08 이면 ≈ 1.41 s, 0.05 이면 ≈ 1.5 s (P 접근 감속 제외) — 차이가 작다. 쥐는 힘 14 N 이면 가벼운 박스가 0.1 m/s² 에서 미끄러질 위험은 작다 | 계산 + 추정 | U8a: 들기 중 미끄럼, VERIFY 결과 |
| `z.height_tol_mm` | null | 2 | 핸드아이 터치 오차 최대 2.44 mm(measurements-1008 #4), 파지 높이에서 핑거 끝–벨트 간격 8 mm 보다 충분히 작게 | 반쯤 근거 | U4·U8a: 도달 판정 시각과 실제 높이 |
| `control.align_tol_along_mm` | null | 3 | 이동 중 좌표 오차 최대 2.73 mm(measurements-1008 #5) → 3 보다 좁으면 잡음 때문에 정렬이 거의 성립 안 함. 벨트 방향 여유 0(ADR-0009) → T34 어긋남 시험 첫 단계 ±5 mm 보다 작게 | 측정 근거 | T34 어긋남 시험(0 / ±5 / ±10 mm) 결과 |
| `control.align_tol_cross_mm` | null | 5 (**상한 10 확정**, 교차 검사) | 가로 여유 24.5 mm 지만 "여유롭게 두지 말 것"(박병후) → along 의 약 2배 | 판단 | T34·U8b 실패 원인 분류 |
| `input.pose_extrap_max_ms` | null | **200** (r4, 이전 120) | 외삽 기준 = 값이 바뀐 첫 stamp → 지평 = 값 나이(최대 0.1 s 갱신 + 메시지 20 ms) + lag 60 ≈ 최대 180 ms, 여유 20 ms. 넘으면 상한까지만 외삽. **goal 시작 직후(로봇이 서 있던 동안 값이 안 바뀜)는 첫 틱부터 capped 가 정상** — capped 빈도를 볼 때 goal 시작 0.2 s 는 뺀다 | 계산 | U4: 틱 로그 `tcp_extrap_s` 분포, `tcp_extrap_capped=true` 빈도 |
| `input.blind_entry_max_age_s` | null | **0.15** (재검 r2, 이전 0.1) | 나이 = 지금 − 촬영 시각. 카메라 → 발행 p95 52~61 ms(measurements-1008 #1·#8) + 틱 위상 0~33 ms = 정상 52~94 ms. 0.1 이면 누락 0 회를 겨우 허용하고 위상이 뒤쪽인 정상 틱도 탈락 → 61 + 33 + 한 프레임 33 + 여유 ≈ 0.15 | 측정 근거 + 계산 | U4: 틱 로그 `obs_age_s` 분포 |
| `input.pose_lag_ms` | **60** | — | measurements-1008 #6 (10/08 김학민, 로봇 20 mm/s 이동 중 1회) | **측정값** | U4: "명령 → pose 반영 지연"으로 재검증. gateway pose 방식이 바뀌면 재측정 |

### 7.2 U1 에서 넘어온 미측정 값 (U2 제어에 영향)

| 키 | 제안값 | 근거·출처 | 정하는 단위 |
|---|---|---|---|
| `z.approach_above_top_mm` | (없음) | 사각 이탈 높이(cutoff + 5) 보다 커야 함(교차 검사). 비교안: 관측 자세 z 그대로(TCP 203.6 mm ≈ 윗면 + 103 mm, measurements-1008 #1) — 높으면 시야 넓지만 하강 시간·사각 직전 거리 증가 | U4 |
| `z.lift_above_top_mm` | (없음) | 들어 올린 뒤 벨트·다음 박스와 간섭 없는 높이 | U8a |
| `z.vision_cutoff_above_top_mm` | 10 | 카메라가 공구축 약 8 cm 옆 — 남현지 확인 필요 | U4 (틱 로그 `visible`) |
| `input.stale_timeout_s` | 0.3 | DESIGN DEC-03 | U4 |
| `input.lost_timeout_s` | 0.5 | 트래커 15 프레임 | U4 |
| `grasp.hold_width_min_mm`·`_max_mm` | 39.5 · 41.5 | measurements #8 | T34 |
| `timing.latency_offset_ms` (voss_config, bringup) | 0 | 보정 없음에서 시작 | U10 튜닝 |

### 7.3 gateway 값 의존 목록 (한쪽만 바뀌면 깨짐 — 학민이 바꿀 때 같이 알림, PR #122 리뷰)

| gateway 값 (`servo_guard.py`·launch) | 지금 | belt_servo 쪽 | 깨지는 경우 · 조치 |
|---|---|---|---|
| `max_speed_mm_s` (launch `servo_max_speed_mm_s`) | 100 | 상수 사본 `GATEWAY_MAX_SPEED_MPS` 0.1, 교차 검사 1 (`max_speed < 0.1`) | 같으면 어디서 잘렸는지 모름. 값이 바뀌면 사본도 |
| `lin_acc_mm_s2` (launch `servo_acc`) — 로봇 램프, 자르지 않음 | 100 | 사본 `GATEWAY_ACC_MPS2` 0.1, 교차 검사 2 (`max_acc ≤ 0.1`) | 더 급하면 명령 ≠ 실제 → 외삽 틀림 |
| `z_min_mm` | 78 | 사본 `GATEWAY_Z_MIN_MM` → `grasp_floor_blocked`(r4) | 파지 문턱 공칭 83.8 mm(plane_z 100.8), 여유 5.8 mm. plane_z 가 96 mm 보다 낮게 설정되면 모든 goal 이 `REACH_Z_MIN`. 여유 1 mm 성립 조건: kp_z × height_tol ≤ 약 10 mm/s (둘 다 U4 튜닝) |
| `x_range_mm` | (−107, 638) | `reach.x_max_mm` **유효 620**(r4), x_min −107 | gateway 는 `x + v²/2a ≥ 638` 에서 x 를 자르고 램프로 635~638 에 선다(48 mm/s, 감속 11.5 mm). 620 이면 belt_servo 가 먼저 OUT_OF_REACH(속도 ≤ 약 60 mm/s 일 때. 80 mm/s 면 gateway 가 600 mm 부터 먼저 자르지만 감속 중 X_MAX 가 605~615 에서 어차피 발화 → 종료는 확정적). 기다리기 규칙 때문에 x_min 쪽은 상류 이동이 없다 |
| `pose_latency_s` | 0.06 | `input.pose_lag_ms` 60 (box_tracker 도 60) | 측정은 service 소스 기준(measurements-1008 #6) |
| `pose_source` (#118) | `service` (값 0.1 s 갱신 가능) | `pose_value_stamp`(r4) 로 두 소스 모두 대응. `pose_lag_ms` 는 소스에 묶임 → 기동 로그 | `joint_states` 로 바꾸면 `pose_lag_ms` 를 다시 잰다(gateway 기본 지연 0.02 s). bringup 에서 같이 넘기는 것은 G0 뒤 |

공통 한계: belt_servo 는 gateway 의 자르기·거부를 모르고 `_last_cmd` 로 외삽한다(6절).

## 8. 변경 기록

| 날짜 | 변경 |
|---|---|
| 10/08 | 초안 |
| 10/08 | DD 승인 (박병후): cross 상한 10 mm 확정, 제안값 descend 0.03 → 0.05·lift 0.05 → 0.08, 교차 검사 `kp_z × descend ≤ a_max` 추가 |
| 10/08 | 7절 추가: 실기에서 정할 값의 제안값 근거·성격(측정/계산/판단)·의존 연쇄·확정 단위 (박병후 요청) |
| 10/08 | r2 독립 재검(Fable 5.1) 반영: 벨트 방향 기다리기, PREPARE 안 보임 → FF, blind_entry 0.15, gateway 가속 근거 정정·속도 검사 `<`, 교차 검사 11개(extrap ≥ lag+20, height_tol 에 히스테리시스, direction 수평 길이), kp_z 검사 근거(2배 여유)·사각 통과 시간 정정, 틱 키 15개(플래그·dt), ZERO_NO_POSE, `_on_box` NaN → invalid, position_source 변경 경고, gateway z 하한 의존(7.3), 테스트 추가. 외삽 상한 처리는 결정 대기(6절) |
| 10/08 | r2 승인(박병후). 외삽 상한 초과 → 상한까지 외삽(`min(h, extrap_max)`, `tcp_extrap_capped`) |
| 10/09 | r4 독립 재검(Fable 5.1) 반영: extrap 제안 200·교차 검사 lag + 120, Z_MIN 근거를 plane_z 상수로 정정, x_max 620 성립 속도 조건, 알려진 한계 수치(9.6 mm), goal 시작 capped 주석, 시험 교체(노드 경로)·NaN pose 시험, 중복 줄 정리 |
| 10/09 | r4 PR #122 학민 리뷰 반영(박병후 결정): pose 값 변경 stamp 기준 외삽(1안), `pose_extrap_max_ms` 제안 180·교차 검사 lag + 100, `Z_MIN` reach(문턱 < 78 + 1 mm — 리뷰 원안보다 느슨하게, 0절), x_max 유효 620, 7.3 gateway 의존 목록, 기동 로그 pose_lag 출처, 제안값 표기를 ADR-0012 범위 밖으로. DESCEND 시간 상한은 U9 유지 |
| 10/08 | r3 코드 재검(Fable 5.1) 반영: 7.3 gateway x 상한 의존 행, 틱 로그 `belt_vel_mps` = 제어에 쓴 `belt_v`, 시험 보강(관측 나이 단독 조건·높이 경계) |
| 10/08 | 구현 중 발견(U1 잠복 버그): `--params-file` 의 null 이 문자열 "null" 로 들어와 교차 검사의 숫자 덧셈에서 예외로 기동 실패 → `check_params` 첫 줄에서 null 문자열을 None 으로 한 번에 바꿈 + 시험 추가 |
