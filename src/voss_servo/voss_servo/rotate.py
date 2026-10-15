"""rotate — J6 회전 파지의 순수 함수 (S2-T18). ROS·시계·파일을 쓰지 않는다.

박스 yaw(BoxTrack.yaw_base)를 보고 공구(J6)를 미리 돌려, 기울어진 박스도 31 mm 폭 파지(46 mm 긴 옆면,
ADR-0009)로 잡게 한다. 설계: design/S2T18-hld.md(r2·r3 주석), S2T18-dd.md(12·13절), S2T18-pseudo.md(r2).
- 각은 내부에서 rad·rad/s·rad/s², 길이 m, 시각은 노드 시계 초. 파라미터·로그만 deg·mm.
- ψ(psi) = 공구 yaw(공구 x 축의 베이스 XY 각), θ = 박스 yaw, Δ = 벨트 방향 기준 상대각.
- belt_servo 는 베이스 Z 각속도(servo_cmd angular.z)만 낸다. 관절 부호·회전 중심 보정은 gateway 몫(topics.md).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

# ---------------------------------------------------------------- 하위 상태 (phase 와 별개)

COLLECT = "COLLECT"  # 목표 각을 정할 프레임을 모으는 중
ROTATING = "ROTATING"  # 목표 각으로 도는 중
SETTLING = "SETTLING"  # 목표에 닿아 멈춘 뒤 pose·비전이 따라오기를 기다림
DONE = "DONE"  # 회전 끝 (정렬 허용)
SKIP = "SKIP"  # 돌리지 않기로 함 (지금 방식으로 진행)
STOPPING = "STOPPING"  # 회전을 멈추라고 했고 실제로 멈추기를 기다림 (관성)
FALLBACK = "FALLBACK"  # 멈춘 각에서 지금 방식으로 진행
RETURNING = "RETURNING"  # LIFT·VERIFY 에서 원래 각으로 되돌리는 중
RETURNED = "RETURNED"  # 원래 각으로 돌아옴

READY_STATES = frozenset({SKIP, DONE, FALLBACK, RETURNING, RETURNED})  # TRACK→DESCEND 허용
HOLD_STATES = frozenset({ROTATING, STOPPING})  # z 하한(시야 보험)을 거는 상태

# ---------------------------------------------------------------- 원인 (rot_cause 로그)

NO_FIELD = "NO_FIELD"  # BoxTrack 에 yaw 필드가 없는 빌드
NO_POSE_YAW = "NO_POSE_YAW"  # 공구 자세 없음·기울어짐·pose 끊김
START_ROTATED = "START_ROTATED"  # goal 시작 때 공구가 기준 각에서 벗어나 있음
NO_YAW = "NO_YAW"  # 정해진 시간 안에 유효 yaw 프레임이 모자람
SPREAD = "SPREAD"  # yaw 프레임이 흩어짐
DOWNSTREAM = "DOWNSTREAM"  # 결정 때 박스가 이미 TCP 하류
SMALL = "SMALL"  # 돌릴 필요가 없을 만큼 작은 각
OUT_OF_RANGE = "OUT_OF_RANGE"  # 허용 상한보다 큰 각 (pending #27 a 안: 돌리지 않고 진행)
TIMEOUT = "TIMEOUT"  # 회전이 예상보다 오래 걸림
STALL = "STALL"  # 명령했는데 공구가 거의 안 돎 (T17 전 gateway, sim)
PHASE = "PHASE"  # 회전 중 phase 가 PREPARE·TRACK 을 벗어남 (안전망)
INTERNAL = "INTERNAL"  # 회전 계산 예외 (노드가 기록)
SETTLE_DRIFT = "SETTLE_DRIFT"  # 정착 중 목표에서 tol 밖으로 밀림 (쫓지 않음)
SETTLE_TIMEOUT = "SETTLE_TIMEOUT"  # 정착이 상한까지 안 됨
ACC_MISMATCH = "ACC_MISMATCH"  # 실제 회전 가속이 설정보다 느림 (경고)
STOP_UNCONFIRMED = "STOP_UNCONFIRMED"  # 측정 각속도가 STOP_CAP 동안 없어 정지 확인 없이 진행 (경고)
RETURN_STALL = "RETURN_STALL"  # 되돌리기 중 STALL
RETURN_TIMEOUT = "RETURN_TIMEOUT"  # 되돌리기 중 TIMEOUT
RETURN_INCOMPLETE = "RETURN_INCOMPLETE"  # goal 이 끝날 때 원래 각으로 못 돌아옴

# ---------------------------------------------------------------- 고정 판단값 (파라미터로 열지 않음)

TILT_MAX = math.radians(5.0)  # 공구가 아래를 본다고 믿는 한계 (관측 자세 0.93°)
STALL_MIN = math.radians(1.0)  # stall_s 동안 이만큼도 못 돌면 STALL
ACC_RATIO = 0.6  # 측정 α 가 설정의 이 비율 아래면 불일치
ACC_FLOOR = math.radians(5.0)  # α_eff 하한 (0 나누기 방지)
ACC_RAMP_TICKS = 2  # 지령이 가속 한도에 막혀 오르는 틱이 이만큼 이어져야 α 를 잰다
ACC_SLOPE_DT = 0.1  # α = 두 측정 각속도의 기울기, 두 표본 간격 하한 s (지연이 상쇄된다)
DEC_RATIO = 0.8  # 감속은 설정 α 의 80 % 로 계획 (S2-T14 사다리꼴 z 와 같은 비율)
TIMEOUT_K = 1.5  # TIMEOUT = 예상 시간 × 1.5 + 0.5 s
TIMEOUT_ADD = 0.5
STILL_TICKS = 2  # 정지 확인에 필요한 연속 틱
YAW_HOLD_MAX = 0.15  # yaw 값이 이보다 오래 그대로면 정지로 본다 s (service 갱신 0.1 s 보다 길게)
SETTLE_CAP = 1.0  # SETTLING 상한 s
# STOPPING: 마지막으로 "돈다"고 잰 뒤(또는 들어온 뒤) 측정 없이 이만큼 지나면 진행 s
# — 60°/s 를 α 90 으로 세우는 0.67 s + pose 정지 판정 여유. 돈다고 재는 동안은 끝없이 기다린다
STOP_CAP = 1.0
POSE_FRESH_FOR_ZERO = (
    0.05  # 기본값 — 실제 값은 rotate.pose_fresh_s (pose 주기의 2배 이상, 주관 검수 c)
)
YAW_SAME = 1e-6  # 같은 yaw 값으로 보는 차 rad

# ---------------------------------------------------------------- 자료형


@dataclass(frozen=True)
class RotCfg:
    """회전 설정 (내부 단위: rad·rad/s·rad/s²·m·s). params.rot_cfg_from_values 가 만든다."""

    deadband: float  # 데드밴드
    min_rot: float  # 이 각 이하는 돌리지 않음 (1단계 10°)
    max_rot: float  # 이 각 넘으면 돌리지 않음 (1단계 45°)
    tol: float  # 도달 허용
    start_tol: float  # goal 시작 자세 허용
    n_min: int  # 결정에 필요한 유효 프레임 수
    buffer_n: int  # 트랙별 yaw 버퍼 길이
    r_min: float  # 흩어짐 하한 (2θ 평균 벡터 길이)
    decide_max_s: float  # goal 뒤 결정 마감
    home_fixed: float | None  # 기준 공구 yaw 고정값 (없으면 노드 기동 뒤 첫 goal 값)
    w_max: float  # 각속도 상한
    w_floor: float  # 각속도 바닥 (끝에서 멈춰 버리지 않게)
    alpha: float  # 각가속 (gateway servo_acc[1] 이하여야 함)
    hold_dz: float  # 회전 중 z 하한 = 박스 윗면 + 이 값
    return_min_dz: float  # 되돌리기는 TCP 가 윗면 + 이 값 위일 때만
    settle_s: float  # 정착 시간
    stall_s: float  # STALL 판정 시간
    still: float  # 이 각속도 아래면 멈춘 것
    belt_yaw: float  # 벨트 진행 방향의 베이스 XY 각
    lag_s: float  # pose stamp 지연 (input.pose_lag_ms)
    extrap_max_s: float  # 외삽 지평 상한 (input.pose_extrap_max_ms)
    pose_fresh_s: float = POSE_FRESH_FOR_ZERO  # "값 그대로 = 정지" 를 믿는 pose 수신 나이 상한
    flip_above: float | None = (
        None  # + Δ 가 이보다 크면 Δ − π 로 반대 방향 회전 (10/15 U14 실기: + 회전 시야 나쁨). None = 끔
    )


@dataclass(frozen=True)
class RotState:
    """goal 하나의 회전 하위 상태 한 장 (매 틱 새로 만든다)."""

    state: str  # 하위 상태
    cause: str = ""  # 원인 (로그)
    t_goal: float = 0.0  # goal 수락 시각
    home: float | None = None  # 되돌아올 기준 공구 yaw
    box_target: float | None = None  # 결정한 박스 yaw (로그)
    target: float | None = None  # 목표 공구 yaw = home + Δ
    delta: float | None = None  # Δ
    n: int | None = None  # 결정에 쓴 프레임 수 (로그)
    rbar: float | None = None  # 결정 때 흩어짐 (로그)
    t_start: float | None = None  # 앞 회전 시작 시각
    psi_start: float | None = None  # 앞 회전 시작 공구 yaw
    t_done: float | None = None  # 앞 회전이 끝난 시각 (DONE·FALLBACK)
    alpha_eff: float | None = None  # 제동에 쓰는 각가속 (불일치면 측정값)
    ramp_n: int = 0  # 지령이 가속 한도에 막혀 오른 연속 틱
    acc_warned: bool = False  # α 불일치 경고를 냈나
    acc_t1: float | None = None  # α 기울기 첫 표본 시각
    acc_w1: float | None = None  # α 기울기 첫 표본 각속도
    still_since: float | None = None  # 멈춰 있기 시작한 시각 (SETTLING)
    settle_start: float | None = None  # SETTLING 진입 시각
    still_n: int = 0  # 정지 확인 연속 틱 (STOPPING)
    stop_move_t: float | None = None  # STOPPING 중 마지막으로 돈다고 잰 시각 (처음엔 들어온 시각)
    stall_psi: float | None = None  # STALL 이동 창 기준 공구 yaw (마지막으로 1° 움직인 자리)
    stall_t: float | None = None  # STALL 이동 창 기준 시각
    settle_drift: bool = False  # 정착 중 밀렸나
    ret_start: float | None = None  # 되돌리기 시작 시각
    ret_expected: float | None = None  # 되돌리기 예상 시간
    ret_tried: bool = False  # 되돌리기를 이미 시도했나 (1회만)


@dataclass(frozen=True)
class RotInputs:
    """노드가 매 틱 모아 넘기는 사실들."""

    now: float  # 노드 시계 초
    phase: str  # fsm phase (전이 전)
    retreat: bool  # 안전 후퇴 중인가
    hold_z: bool  # 개방 대기 중인가
    yaws: Sequence[float]  # 결정용 yaw 프레임 (COLLECT 때만 의미)
    has_field: bool | None  # BoxTrack 에 yaw 필드가 있나 (None = 아직 모름)
    home_ref: float | None  # 기준 공구 yaw (고정값 또는 첫 goal 값)
    psi_raw: float | None  # pose 의 공구 yaw (외삽 전)
    psi_est: float | None  # 지금으로 외삽한 공구 yaw
    tilt: float | None  # 공구 z 축의 기울기
    pose_ok: bool  # 자세가 유효하고 신선한가
    w_meas: float | None  # 측정 각속도 (모르면 None)
    wz_prev: float  # 직전에 발행한 각속도
    dt: float  # 이번 틱 dt
    err_along: float | None  # 접근 높이 오차의 벨트 방향 성분 m (+ = 박스가 하류)
    tcp_z: float | None  # 보정 TCP z m
    top_z: float | None  # 박스 윗면 z m


@dataclass(frozen=True)
class RotOut:
    """rot_step 결과."""

    state: RotState  # 다음 상태
    wz: float  # 발행할 베이스 Z 각속도 rad/s
    ready: bool  # TRACK→DESCEND 를 허용하나
    z_floor: float | None  # z 하한 m (없으면 None)
    warn: str | None  # 이번 틱 경고 원인 (ACC_MISMATCH)


@dataclass(frozen=True)
class Aggregate:
    """yaw 프레임 모음의 요약."""

    target: float  # 박스 yaw (접힌 값)
    rbar: float  # 2θ 평균 벡터 길이 (1 = 모두 같은 각)
    n: int  # 프레임 수


# ---------------------------------------------------------------- 작은 함수


def fold_half(a: float) -> float:
    """각을 (−π/2, π/2] 로 접는다 — 180° 대칭 (비전 tracker_logic.fold_yaw 와 같은 규칙)."""
    y = math.fmod(a, math.pi)  # −π < y < π
    if y <= -math.pi / 2:
        y += math.pi  # 아래쪽 반을 위로
    elif y > math.pi / 2:
        y -= math.pi  # 위쪽 반을 아래로
    return y


def wrap_pi(a: float) -> float:
    """각을 (−π, π] 로 감는다 — 공구 yaw 차이 (360° 대칭)."""
    y = math.fmod(a + math.pi, 2.0 * math.pi)  # (−2π, 2π)
    if y <= 0.0:
        y += 2.0 * math.pi  # (0, 2π]
    return y - math.pi


def tool_yaw(q: Sequence[float]) -> tuple[float, float] | None:
    """pose 쿼터니언 (x, y, z, w) → (공구 x 축의 베이스 XY 각, 공구 z 축이 −Z 에서 기운 각). 이상하면 None."""
    x, y, z, w = (float(v) for v in q)
    n = math.sqrt(x * x + y * y + z * z + w * w)  # 쿼터니언 길이
    if not math.isfinite(n) or n < 1e-9:
        return None  # 0 이거나 NaN — 자세를 모른다
    x, y, z, w = x / n, y / n, z / n, w / n  # 길이 1 로
    r00 = 1.0 - 2.0 * (y * y + z * z)  # 회전 행렬 (0,0): 공구 x 축의 베이스 x 성분
    r10 = 2.0 * (x * y + z * w)  # 회전 행렬 (1,0): 공구 x 축의 베이스 y 성분
    r22 = 1.0 - 2.0 * (x * x + y * y)  # 회전 행렬 (2,2): 공구 z 축의 베이스 z 성분
    yaw = math.atan2(r10, r00)  # 공구 x 축이 베이스 XY 에서 가리키는 각
    tilt = math.acos(min(1.0, max(-1.0, -r22)))  # 공구 z 축과 아래(−Z) 사이 각
    return yaw, tilt


def down_quat(psi: float) -> tuple[float, float, float, float]:
    """공구가 정확히 아래를 보고 yaw 가 psi 인 쿼터니언 (x, y, z, w) = Rz(ψ)·Rx(π). 시험·sim 용."""
    return (math.cos(psi / 2.0), math.sin(psi / 2.0), 0.0, 0.0)


def aggregate(yaws: Sequence[float]) -> Aggregate | None:
    """yaw 프레임들 → 2θ 공간 성분별 중앙값의 반각 + 흩어짐. 비면 None."""
    if not yaws:
        return None
    c = [math.cos(2.0 * t) for t in yaws]  # 각을 두 배로 → 원 위의 점 x
    s = [math.sin(2.0 * t) for t in yaws]  # 원 위의 점 y
    target = fold_half(0.5 * math.atan2(statistics.median(s), statistics.median(c)))  # 반각으로
    rbar = math.hypot(statistics.fmean(c), statistics.fmean(s))  # 평균 벡터 길이
    return Aggregate(target, rbar, len(yaws))


def expected_time(delta: float, w_max: float, alpha: float) -> float:
    """정지 → 정지 회전 시간 s (사다리꼴, 짧으면 삼각)."""
    th = abs(delta)  # 돌 각
    if th >= w_max * w_max / alpha:
        return th / w_max + w_max / alpha  # 최고 속도 구간이 있다
    return 2.0 * math.sqrt(th / alpha)  # 최고 속도에 못 닿는다


def law(err: float, w_max: float, w_floor: float, alpha_eff: float, tol: float) -> float:
    """√ 감속 법칙: 남은 각만큼 딱 멈출 수 있는 각속도 (S2-T14 사다리꼴 z 와 같은 모양)."""
    if abs(err) <= tol:
        return 0.0  # 도착
    v = math.sqrt(2.0 * DEC_RATIO * alpha_eff * (abs(err) - tol))  # 감속 곡선
    return math.copysign(min(w_max, max(w_floor, v)), err)  # 상한·바닥, 부호는 남은 각 쪽


def rate_limit(w: float, w_prev: float, alpha: float, dt: float) -> float:
    """한 틱에 각속도를 alpha·dt 보다 많이 바꾸지 않는다 (alpha 는 설정값)."""
    step = alpha * dt  # 이번 틱 최대 변화
    return w_prev + min(step, max(-step, w - w_prev))


def yaw_estimate(
    value: float, value_stamp: float, lag: float, wz_prev: float, now: float, extrap_max: float
) -> float:
    """늦게 온 공구 yaw → 지금 공구 yaw (control.tcp_now 와 같은 외삽)."""
    h = min(max(now - value_stamp, 0.0) + lag, extrap_max)  # 외삽 지평 (상한까지만)
    return value + wz_prev * h


def omega_meas(
    prev: tuple[float, float] | None,
    cur: tuple[float, float] | None,
    now: float,
    pose_rx_age: float,
    fresh_s: float = POSE_FRESH_FOR_ZERO,
) -> float | None:
    """(yaw, 그 값이 처음 온 stamp) 두 개 → 측정 각속도 rad/s. 모르면 None.

    fresh_s = 마지막 pose 수신이 이보다 최근이면 "값 그대로 = 정지" 로 본다 (rotate.pose_fresh_s).
    """
    if cur is None:
        return None  # pose 를 아직 못 받음
    if now - cur[1] > YAW_HOLD_MAX:
        # 값이 오래 그대로: 메시지가 오고 있으면 정지, 메시지가 끊겼으면 모름
        return 0.0 if pose_rx_age <= fresh_s else None
    if prev is None:
        return None  # 값이 하나뿐
    dt = cur[1] - prev[1]  # 두 값이 처음 온 시각 차
    if dt <= 0.0 or dt > YAW_HOLD_MAX:
        return None  # 시각 이상 또는 오래 멈췄던 값에서 처음 바뀜
    return wrap_pi(cur[0] - prev[0]) / dt


def alpha_slope(t1: float, w1: float, t2: float, w2: float) -> float | None:
    """두 측정 각속도의 기울기 = 실제 각가속. 간격이 짧으면 None (지연은 두 표본에 같이 들어 상쇄)."""
    if t2 - t1 < ACC_SLOPE_DT:
        return None
    return (abs(w2) - abs(w1)) / (t2 - t1)


# ---------------------------------------------------------------- 결정


def pre_checks(inp: RotInputs, cfg: RotCfg) -> str | None:
    """프레임 수와 무관하게 먼저 보는 검사. 원인 문자열, 기다림 "WAIT", 통과 None."""
    if inp.has_field is False:
        return NO_FIELD  # yaw 필드 없는 빌드
    if inp.has_field is None:
        return "WAIT"  # 박스 메시지를 아직 못 받음
    if inp.psi_raw is None or inp.tilt is None or inp.tilt > TILT_MAX:
        return NO_POSE_YAW  # 공구 자세를 믿을 수 없다
    if inp.home_ref is None:
        return (
            NO_POSE_YAW  # 유효한 pose 로 정한 기준 공구 yaw 가 없다 → 돌리지 않는다 (주관 검수 a)
        )
    if inp.home_ref is not None and abs(wrap_pi(inp.psi_raw - inp.home_ref)) > cfg.start_tol:
        return START_ROTATED  # 기준 각에서 벗어난 채 시작 → Δ 가 틀린다
    return None


def decide(agg: Aggregate, inp: RotInputs, cfg: RotCfg) -> tuple[str, float | None]:
    """모은 yaw → (원인 또는 "" , Δ). 원인이 ""면 돌린다 (판정표 위에서부터 첫 매치)."""
    if agg.rbar < cfg.r_min:
        return SPREAD, None  # 흩어져서 믿을 수 없다
    if inp.err_along is not None and inp.err_along > 0.0:
        return DOWNSTREAM, None  # 박스가 이미 TCP 하류 (시야 판정 근거 없음)
    delta = fold_half(agg.target - cfg.belt_yaw)  # 벨트 방향 기준 상대각 = 돌릴 양
    if cfg.flip_above is not None and delta > cfg.flip_above:
        # 180° 대칭: + 쪽 큰 각은 − 쪽으로 (예 +80° → −100°). + 회전은 카메라가 박스를 비스듬히 봐 LOST 가 잦다
        delta -= math.pi
    if abs(delta) <= max(cfg.deadband, cfg.min_rot):
        return SMALL, delta  # 작은 각 — 그리퍼가 스스로 맞춘다
    if abs(delta) > cfg.max_rot:
        return OUT_OF_RANGE, delta  # 상한 밖 — 돌리지 않고 진행 (pending #27 a 안)
    return "", delta


# ---------------------------------------------------------------- 상태별 한 틱

Step = tuple[RotState, float | None, str | None]  # (다음 상태, 원하는 각속도 또는 즉시 0, 경고)


def _law_to(goal: float, inp: RotInputs, rs: RotState, cfg: RotCfg) -> float:
    """목표 공구 yaw 로 가는 √ 법칙 각속도 (외삽한 공구 yaw 기준)."""
    psi = inp.psi_est if inp.psi_est is not None else inp.psi_raw  # 외삽값이 없으면 원값
    alpha = rs.alpha_eff if rs.alpha_eff is not None else cfg.alpha
    return law(wrap_pi(goal - psi), cfg.w_max, cfg.w_floor, alpha, cfg.tol)


def _collect(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """COLLECT: 검사 → 프레임이 차면 결정, 시간이 지나면 NO_YAW."""
    c = pre_checks(inp, cfg)
    if c is not None and c != "WAIT":
        return replace(rs, state=SKIP, cause=c), None, None  # 원인이 확실하면 바로 SKIP
    short = c == "WAIT" or len(inp.yaws) < cfg.n_min  # 아직 결정할 수 없다
    if short:
        if inp.now - rs.t_goal > cfg.decide_max_s:
            return replace(rs, state=SKIP, cause=NO_YAW), None, None  # 마감
        return rs, None, None  # 계속 모은다
    agg = aggregate(inp.yaws)
    assert agg is not None  # n_min ≥ 1 이라 비어 있지 않다
    cause, delta = decide(agg, inp, cfg)
    rs = replace(rs, n=agg.n, rbar=agg.rbar, box_target=agg.target, delta=delta)
    if cause:
        return replace(rs, state=SKIP, cause=cause), None, None
    assert delta is not None and rs.home is not None and inp.psi_raw is not None
    rs = replace(
        rs,
        state=ROTATING,
        target=rs.home + delta,  # 절대 목표 공구 yaw
        psi_start=inp.psi_raw,
        t_start=inp.now,
        alpha_eff=cfg.alpha,
        ramp_n=0,
    )
    return rs, _law_to(rs.target, inp, rs, cfg), None


def _rotating(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """ROTATING: 안전망·TIMEOUT·STALL → 도착(SETTLING) → 아니면 √ 법칙 + α 감시."""
    if inp.phase not in ("PREPARE", "TRACK"):
        return replace(rs, state=STOPPING, cause=PHASE, still_n=0), None, None
    if not inp.pose_ok or inp.psi_raw is None:
        return replace(rs, state=STOPPING, cause=NO_POSE_YAW, still_n=0), None, None
    assert rs.t_start is not None and rs.delta is not None and rs.target is not None
    el = inp.now - rs.t_start  # 회전 경과
    limit = TIMEOUT_K * expected_time(rs.delta, cfg.w_max, cfg.alpha) + TIMEOUT_ADD
    if el > limit:
        return replace(rs, state=STOPPING, cause=TIMEOUT, still_n=0), None, None
    stalled, rs = _stall_window(rs, inp, cfg)
    if stalled:
        return replace(rs, state=STOPPING, cause=STALL, still_n=0), None, None
    e = wrap_pi(rs.target - (inp.psi_est if inp.psi_est is not None else inp.psi_raw))
    if abs(e) <= cfg.tol and inp.w_meas is not None and abs(inp.w_meas) < cfg.still:
        return replace(rs, state=SETTLING, still_since=inp.now, settle_start=inp.now), None, None
    return _accel_watch(rs, inp, cfg, e)


def _stall_window(rs: RotState, inp: RotInputs, cfg: RotCfg) -> tuple[bool, RotState]:
    """이동 창 STALL: 계속 돌라고 했는데(|지령| ≥ ω 바닥) 최근 stall_s 동안 1° 도 못 돌았나.

    시작 각만 보면 1° 이상 돈 뒤 멈춘 것(gateway 자름·걸림)을 TIMEOUT 까지 모른다 (학민 #54 리뷰 5).
    1° 움직였거나 거의 0 을 지령하는 동안은 기준(각·시각)을 지금으로 옮긴다.
    """
    assert inp.psi_raw is not None
    ref_psi, ref_t = rs.stall_psi, rs.stall_t
    moved = ref_psi is None or abs(wrap_pi(inp.psi_raw - ref_psi)) >= STALL_MIN
    if moved or ref_t is None or abs(inp.wz_prev) < cfg.w_floor:
        return False, replace(rs, stall_psi=inp.psi_raw, stall_t=inp.now)  # 창 다시
    return inp.now - ref_t >= cfg.stall_s, rs


def _accel_watch(rs: RotState, inp: RotInputs, cfg: RotCfg, e: float) -> Step:
    """α 감시(두 표본 기울기) 뒤 √ 법칙 각속도. 지령이 가속 한도에 막혀 오를 때만 잰다."""
    alpha = rs.alpha_eff if rs.alpha_eff is not None else cfg.alpha
    want = law(e, cfg.w_max, cfg.w_floor, alpha, cfg.tol)
    rising = abs(want) > abs(inp.wz_prev) + 0.5 * cfg.alpha * inp.dt  # 한도까지 오르는 중
    ramp_n = rs.ramp_n + 1 if rising else 0
    t1, w1, warned, warn = rs.acc_t1, rs.acc_w1, rs.acc_warned, None
    if not rising:
        t1, w1 = None, None  # 램프가 끊기면 표본을 버린다
    elif not warned and ramp_n >= ACC_RAMP_TICKS and inp.w_meas is not None:
        # 로봇이 지령과 같은 방향으로 움직일 때만 잰다 — 출발 지연(아직 정지)·지나친 뒤
        # 되돌아올 때(아직 앞 방향으로 감속 중)는 기울기가 α 가 아니다 (최종 재검 권장 3)
        same_dir = abs(inp.w_meas) >= cfg.still and inp.w_meas * want > 0
        if not same_dir:
            t1, w1 = None, None
        elif t1 is None or w1 is None:
            t1, w1 = inp.now, inp.w_meas  # 첫 표본
        else:
            a = alpha_slope(t1, w1, inp.now, inp.w_meas)
            if a is not None and a < ACC_RATIO * cfg.alpha:
                alpha = max(a, ACC_FLOOR)  # 측정 가속으로 제동
                warned, warn = True, ACC_MISMATCH
                want = law(e, cfg.w_max, cfg.w_floor, alpha, cfg.tol)  # 새 α 로 다시
    rs = replace(rs, ramp_n=ramp_n, acc_t1=t1, acc_w1=w1, acc_warned=warned, alpha_eff=alpha)
    return rs, want, warn


def _settling(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """SETTLING: 멈춘 채 settle_s 지나면 DONE. 밀려도 쫓지 않는다. 상한 SETTLE_CAP."""
    assert rs.settle_start is not None
    if inp.now - rs.settle_start >= SETTLE_CAP:
        return replace(rs, state=DONE, cause=SETTLE_TIMEOUT, t_done=inp.now), None, None
    if inp.w_meas is None or abs(inp.w_meas) >= cfg.still:
        return replace(rs, still_since=inp.now), None, None  # 아직 움직임 — 시계를 다시
    assert rs.still_since is not None
    if inp.now - rs.still_since < cfg.settle_s:
        return rs, None, None  # 기다림
    drift = (
        rs.target is not None
        and inp.psi_raw is not None
        and abs(wrap_pi(rs.target - inp.psi_raw)) > cfg.tol
    )
    return replace(rs, state=DONE, t_done=inp.now, settle_drift=drift), None, None


def _stopping(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """STOPPING: 각속도 0 을 내고 실제로 멈춘 것이 2틱 이어지면 FALLBACK.

    측정 각속도가 STOP_CAP 동안 없으면(pose 지터·끊김) 경고와 함께 FALLBACK — TRACK 에 묶여 박스를
    흘려보내지 않게 (학민 #54 리뷰 4). "아직 돈다"고 재는 동안은 진행하지 않고 0 을 유지한 채 기다린다
    — 각가속이 느려 늦게 서는 손목으로 DESCEND 하지 않게 (재리뷰). 그동안 박스가 흘러가면 x 끝·LOST 가 끝낸다.
    """
    move_t = rs.stop_move_t if rs.stop_move_t is not None else inp.now  # 처음 = 들어온 시각
    moving = inp.w_meas is not None and abs(inp.w_meas) >= cfg.still
    if moving:
        move_t = inp.now  # 아직 돈다 → 상한 시계를 다시
    still = inp.w_meas is not None and abs(inp.w_meas) < cfg.still
    n = rs.still_n + 1 if still else 0
    warn = None
    if n < STILL_TICKS:
        if inp.now - move_t < STOP_CAP:
            return replace(rs, still_n=n, stop_move_t=move_t), None, None
        warn = STOP_UNCONFIRMED  # 측정 없이 상한 — 정지 확인 없이 진행
    t_done = rs.t_done
    if t_done is None and rs.t_start is not None:
        t_done = inp.now  # 앞 회전이 끝난 시각 (되돌리기 실패는 덮지 않는다)
    return replace(rs, state=FALLBACK, still_n=n, t_done=t_done, stop_move_t=None), None, warn


def return_ok(inp: RotInputs, cfg: RotCfg) -> bool:
    """되돌리기를 해도 되나: LIFT(개방 대기 후퇴 제외)·VERIFY 이고 TCP 가 윗면 + return_min_dz 위."""
    lift = (inp.phase == "LIFT" and not (inp.retreat and inp.hold_z)) or inp.phase == "VERIFY"
    high = (
        inp.tcp_z is not None
        and inp.top_z is not None
        and inp.tcp_z >= inp.top_z + cfg.return_min_dz
    )
    return lift and high


def _done_or_fallback(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """DONE·FALLBACK: 되돌리기 조건이 되면 한 번만 RETURNING 으로."""
    if rs.ret_tried or rs.home is None or inp.psi_raw is None or not return_ok(inp, cfg):
        return rs, None, None
    off = wrap_pi(rs.home - inp.psi_raw)  # 원래 각까지 남은 각
    if abs(off) <= cfg.tol:
        return rs, None, None  # 이미 제자리
    rs = replace(
        rs,
        state=RETURNING,
        ret_start=inp.now,
        stall_psi=None,  # STALL 이동 창은 되돌리기 첫 틱에 다시 잡는다
        ret_tried=True,
        ret_expected=expected_time(off, cfg.w_max, cfg.alpha),
    )
    return rs, _law_to(rs.home, inp, rs, cfg), None


def _returning(rs: RotState, inp: RotInputs, cfg: RotCfg) -> Step:
    """RETURNING: 조건이 깨지면 대기(시계 다시), TIMEOUT·STALL 감시, 도착하면 RETURNED."""
    if not return_ok(inp, cfg):
        # 대기 — 다시 움직일 때 STALL 을 잘못 내지 않게 기준 시각·각을 새로 잡는다
        return replace(rs, ret_start=inp.now, stall_psi=None), None, None
    if not inp.pose_ok or inp.psi_raw is None:
        return replace(rs, state=STOPPING, cause=NO_POSE_YAW, still_n=0), None, None
    assert rs.ret_start is not None and rs.ret_expected is not None and rs.home is not None
    el = inp.now - rs.ret_start
    if el > TIMEOUT_K * rs.ret_expected + TIMEOUT_ADD:
        return replace(rs, state=STOPPING, cause=RETURN_TIMEOUT, still_n=0), None, None
    stalled, rs = _stall_window(rs, inp, cfg)
    if stalled:
        return replace(rs, state=STOPPING, cause=RETURN_STALL, still_n=0), None, None
    psi = inp.psi_est if inp.psi_est is not None else inp.psi_raw
    if abs(wrap_pi(rs.home - psi)) <= cfg.tol:
        return replace(rs, state=RETURNED), None, None
    return rs, _law_to(rs.home, inp, rs, cfg), None


_HANDLERS = {
    COLLECT: _collect,
    ROTATING: _rotating,
    SETTLING: _settling,
    STOPPING: _stopping,
    DONE: _done_or_fallback,
    FALLBACK: _done_or_fallback,
    RETURNING: _returning,
}


def rot_step(rs: RotState, inp: RotInputs, cfg: RotCfg) -> RotOut:
    """회전 하위 상태 한 틱: 전이 + 각속도 + 정렬 허용 + z 하한 (pseudo r2 4절)."""
    if rs.home is None and inp.home_ref is not None:
        # 기준 공구 yaw 는 노드가 유효한 pose 로만 정한다 — 지금 자세로 대신하지 않는다 (주관 검수 a:
        # 되돌리기에 실패해 돌아간 손목을 기준으로 삼아 Δ 만큼 더 도는 길을 막는다)
        rs = replace(rs, home=inp.home_ref)
    handler = _HANDLERS.get(rs.state)
    want, warn = None, None  # SKIP·RETURNED: 즉시 0
    if handler is not None:
        rs, want, warn = handler(rs, inp, cfg)
    wz = 0.0 if want is None else rate_limit(want, inp.wz_prev, cfg.alpha, inp.dt)
    ready = rs.state in READY_STATES
    hold = rs.state in HOLD_STATES and inp.phase in ("PREPARE", "TRACK")
    z_floor = inp.top_z + cfg.hold_dz if hold and inp.top_z is not None else None
    return RotOut(rs, wz, ready, z_floor, warn)


def end_cause(rs: RotState, psi_raw: float | None, tol: float) -> str:
    """goal 끝 틱의 rot_cause: 원래 각으로 못 돌아왔으면 RETURN_INCOMPLETE."""
    if rs.state == RETURNING:
        return RETURN_INCOMPLETE
    rotated = (
        rs.state in (ROTATING, SETTLING, DONE, FALLBACK, STOPPING)  # 돌기 시작한 상태 (취소 포함)
        and rs.home is not None
        and psi_raw is not None
        and abs(wrap_pi(rs.home - psi_raw)) > tol
    )
    if rotated:
        return RETURN_INCOMPLETE
    if not rs.cause and rs.settle_drift:
        return SETTLE_DRIFT
    return rs.cause


# ---------------------------------------------------------------- 로그 값


def _deg(v: float | None) -> float | None:
    """rad → deg (None 이면 None)."""
    return None if v is None else math.degrees(v)


def log_values(
    rs: RotState | None,
    wz: float,
    w_meas: float | None,
    psi_raw: float | None,
    psi_est: float | None,
    terminal: bool,
    warn: str | None,
    tol: float,
) -> dict[str, Any]:
    """틱 로그의 회전 키 13개 (log_schema.ROT_KEYS 와 같은 이름). 회전이 꺼져 있으면 전부 None."""
    if rs is None:
        return dict.fromkeys(ROT_LOG_KEYS)
    if terminal:
        cause = end_cause(rs, psi_raw, tol)  # 끝 틱: 되돌리기 미완 판단
    else:
        cause = warn or rs.cause or (SETTLE_DRIFT if rs.settle_drift else "")
    goal = rs.home if rs.state in (RETURNING, RETURNED) else rs.target  # 지금 따르는 목표
    err = wrap_pi(goal - psi_raw) if goal is not None and psi_raw is not None else None
    t_rot = rs.t_done - rs.t_start if rs.t_done is not None and rs.t_start is not None else None
    # goal 끝 틱만: 손목이 기준 각에서 남은 각(공구 yaw − 기준, +·−). 되돌림 창(LIFT~VERIFY ≈ 0.8 s)보다 큰
    # 회전은 RETURN_INCOMPLETE 가 정상으로 찍히므로, 실제로 얼마나 남았는지는 이 값으로 본다 (10/15 U14 실기)
    left = (
        wrap_pi(psi_raw - rs.home)
        if terminal and psi_raw is not None and rs.home is not None
        else None
    )
    return {
        "rot_state": rs.state,
        "rot_cause": cause or None,
        "yaw_target_deg": _deg(rs.box_target),
        "rot_delta_deg": _deg(rs.delta),
        "tool_yaw_deg": _deg(psi_raw),
        "tool_yaw_est_deg": _deg(psi_est),
        "rot_err_deg": _deg(err),
        "wz_cmd_dps": math.degrees(wz),
        "wz_meas_dps": _deg(w_meas),
        "rot_n": rs.n,
        "rot_rbar": rs.rbar,
        "rot_time_s": t_rot,
        "rot_end_left_deg": _deg(left),
    }


ROT_LOG_KEYS = (
    "rot_state",
    "rot_cause",
    "yaw_target_deg",
    "rot_delta_deg",
    "tool_yaw_deg",
    "tool_yaw_est_deg",
    "rot_err_deg",
    "wz_cmd_dps",
    "wz_meas_dps",
    "rot_n",
    "rot_rbar",
    "rot_time_s",
    "rot_end_left_deg",
)
