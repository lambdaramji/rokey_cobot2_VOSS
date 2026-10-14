"""belt_servo 제어 계산 (순수 모듈 — ROS·시계·파일을 쓰지 않는다).

- 벡터는 NumPy 길이 3, 단위는 안에서 m·m/s·s 하나. mm·ms·cm/s 변환은 config_from_values 한 곳.
- 예측: 촬영 시각 관측 + 벨트 속도 × 경과 시간 (DESIGN.md DEC-03). position_base 는 box_tracker 가
  이미 pose 지연을 보정한 값이라 여기서 다시 보정하지 않는다 (measurements-1008 #6, 이중 보정 금지).
- 현재 TCP: pose + 마지막 발행 속도 × (지금 − (stamp − pose_lag)), 외삽 지평은 상한에서 멈춘다.
- 속도: FF(벨트 속도) + P(남은 오차 × Kp) (DEC-04). 벨트 방향으로는 상류로 가지 않는다(기다리기).
- 설계: src/voss_servo/design/U2-{hld,dd,pseudo}.md
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from voss_servo import fsm, grip
from voss_servo.params import (
    BLIND_DWELL_MARGIN_S,
    GATEWAY_Z_MIN_MM,
    NULL_STRINGS,
    RETREAT_CLEAR_MM,
    Z_PROFILE_P,
    Z_PROFILE_TRAP,
)

# --- xy 규칙 이름 (틱 로그 cmd_rule 에도 그대로 쓴다) ---
FF_P = "FF_P"  # 벨트 속도 + Kp × 오차
FF = "FF"  # 벨트 속도만
ZERO = "ZERO"  # xy 0
# --- 0 명령의 이유 ---
ZERO_NO_POSE = "ZERO_NO_POSE"  # pose 가 없다
ZERO_NO_OBS = "ZERO_NO_OBS"  # 이 트랙의 유효 관측이 한 번도 없다
ZERO_STOP = "ZERO_STOP"  # 멈추는 중(stopping) 또는 goal 끝(terminal)

Vec = Sequence[float] | np.ndarray  # 길이 3 벡터로 받을 수 있는 것
# 파지 높이 도달 문턱(목표 + height_tol)이 gateway z 하한보다 이만큼은 위에 있어야 도달할 수 있다
Z_MIN_MARGIN_M = 0.001
# --- 사다리꼴 z (S2-T14, z.profile trapezoid). 판단값 — 계산 근거 design/S2T14-hld.md D1·D7, 실측 전 제안값 ---
# 감속 = 이 값 × max_acc. 로봇 램프(= max_acc)보다 낮게 → 착지가 P 와 0.5 mm 차
TRAP_DECEL_RATIO = 0.8
TRAP_V_FLOOR_MPS = 0.005  # 조준점 바로 앞 최소 속도 (√ 꼬리에서 멈춰 버리지 않게)
# 사다리꼴: 파지 목표 ≥ gateway z 하한 + 이 값 (최악 착지 −2.2 mm, 지연 100 ms)
Z_MIN_MARGIN_TRAP_M = 0.003
Z_LAW_P = "P"  # z 속도 법칙: kp_z × 오차
Z_LAW_TRAP = "TRAP"  # z 속도 법칙: 사다리꼴
# 사다리꼴을 쓰는 phase. 안전 후퇴 RISING 도 phase 가 LIFT 지만 z_law 의 retreat 로 뺀다
# (10/12 실기로 확인된 P 그대로 — HLD 12.1 (나)). PREPARE·TRACK 은 접근 높이에 "머물러야" 해서 P (떨림 방지)
TRAP_PHASES = (fsm.DESCEND, fsm.LIFT)


@dataclass(frozen=True, eq=False)
class ControlConfig:
    """제어 설정 묶음. 노드가 READY 일 때 config_from_values 로 한 번 만든다 (단위 m·m/s·s)."""

    belt_dir_xy: np.ndarray  # 벨트 방향 수평 단위벡터 (x, y, 0)
    belt_v: np.ndarray  # 벨트 속도 벡터 m/s (z = 0)
    latency_offset_s: float  # 예측을 더 앞당기는 시간 (튜닝, 0 = 보정 없음)
    pose_lag_s: float  # pose stamp 가 실제보다 늦은 시간
    pose_extrap_max_s: float  # TCP 외삽 지평 상한
    blind_entry_max_age_s: float  # 하강 시작 때 마지막 유효 관측 나이 상한
    kp_xy: float  # xy P 게인 1/s
    kp_z: float  # z P 게인 1/s
    align_along_m: float  # 벨트 방향 정렬 허용치
    align_cross_m: float  # 가로 정렬 허용치
    v_max: float  # 속도 크기 상한 m/s
    a_max: float  # 가속 크기 상한 m/s²
    approach_dz: float  # 접근 높이 = 박스 윗면 + 이 값
    grasp_dz: float  # 파지 높이 = 박스 윗면 + 이 값 (음수)
    lift_dz: float  # 들기 높이 = 박스 윗면 + 이 값
    descend_speed: float  # z 내려가는 속도 상한 m/s
    lift_speed: float  # z 올라가는 속도 상한 m/s
    height_tol_m: float  # "높이에 도달" 허용치
    x_min: float  # 추종 가능 구간 TCP x 하한
    x_max: float  # 추종 가능 구간 TCP x 상한
    dt_nominal: float  # 1 / rate_hz
    z_min: float  # gateway TCP z 하한 (사본, m)
    z_profile: str  # "p" | "trapezoid" (S2-T14)
    a_dec: float  # 사다리꼴 감속 m/s² = TRAP_DECEL_RATIO × a_max


def vec3(v: Vec) -> np.ndarray:
    """길이 3 float 배열로 바꾼다 (list·tuple·array.array 모두)."""
    return np.asarray(v, dtype=float).reshape(3)


def config_from_values(values: dict[str, Any]) -> ControlConfig:
    """파라미터 값 묶음(params.py 이름) → ControlConfig. 단위 변환은 여기 한 곳."""
    d = vec3(values["belt.direction_base"])  # 벨트 방향 (길이 1 ± 0.01)
    xy = np.array([d[0], d[1], 0.0])  # 수평 성분만 (벨트는 수평)
    dir_xy = xy / np.linalg.norm(xy)  # 다시 길이 1 로 (수평 길이 ≥ 0.99 는 params 가 보장)
    belt_mps = values["belt.speed_cmps"] / 100.0  # cm/s → m/s
    return ControlConfig(
        belt_dir_xy=dir_xy,
        belt_v=belt_mps * dir_xy,  # 벨트 속도 벡터, z = 0
        latency_offset_s=values["timing.latency_offset_ms"] / 1000.0,
        pose_lag_s=values["input.pose_lag_ms"] / 1000.0,
        pose_extrap_max_s=values["input.pose_extrap_max_ms"] / 1000.0,
        blind_entry_max_age_s=float(values["input.blind_entry_max_age_s"]),
        kp_xy=float(values["control.kp_per_s"]),
        kp_z=float(values["control.kp_z_per_s"]),
        align_along_m=values["control.align_tol_along_mm"] / 1000.0,
        align_cross_m=values["control.align_tol_cross_mm"] / 1000.0,
        v_max=float(values["limits.max_speed_mps"]),
        a_max=float(values["limits.max_acc_mps2"]),
        approach_dz=values["z.approach_above_top_mm"] / 1000.0,
        grasp_dz=-values["grasp.tcp_z_below_top_mm"] / 1000.0,  # 윗면보다 아래 → 음수
        lift_dz=values["z.lift_above_top_mm"] / 1000.0,
        descend_speed=float(values["z.descend_speed_mps"]),
        lift_speed=float(values["z.lift_speed_mps"]),
        height_tol_m=values["z.height_tol_mm"] / 1000.0,
        x_min=values["reach.x_min_mm"] / 1000.0,
        x_max=values["reach.x_max_mm"] / 1000.0,
        dt_nominal=1.0 / values["rate_hz"],
        z_min=GATEWAY_Z_MIN_MM / 1000.0,
        z_profile=profile_or_p(values.get("z.profile")),  # 선택 키: 없으면 p
        a_dec=TRAP_DECEL_RATIO * float(values["limits.max_acc_mps2"]),
    )


def profile_or_p(raw: Any) -> str:
    """z.profile 값 → 프로파일 이름. 없음·None·"null" 문자열(--params-file) 이면 p (S2T14-dd 1절)."""
    if raw is None or (isinstance(raw, str) and raw.strip() in NULL_STRINGS):
        return Z_PROFILE_P  # 키를 안 넣은 옛 yaml = P = 시연 라인
    return str(raw)  # 값 검사는 params.check_params 가 이미 했다


# ---------------------------------------------------------------------- 기본 함수


def zero_cmd() -> np.ndarray:
    """속도 0 벡터."""
    return np.zeros(3)


def effective_dt(prev_calc: float | None, now: float, dt_nominal: float) -> float:
    """가속 제한에 쓸 틱 간격. 첫 틱·시계 역행은 공칭값, 너무 길면 공칭값의 2배로 자른다."""
    if prev_calc is None:
        return dt_nominal  # goal 첫 틱
    dt = now - prev_calc
    if dt <= 0.0:
        return dt_nominal  # 시계가 같거나 뒤로 감
    return min(dt, 2.0 * dt_nominal)  # 오래 멈췄다 와도 한 틱 변화량을 키우지 않는다


def predict(
    p_obs: Vec, box_stamp: float, now: float, belt_v: Vec, latency_offset: float
) -> tuple[np.ndarray, float, bool]:
    """촬영 시각 관측 → 지금 박스 위치. (예측 위치, 지평 s, Δt 음수였나)."""
    raw = now - box_stamp  # 사진 찍은 뒤 지난 시간
    clipped = raw < 0.0  # 미래 stamp (시계 차이)
    h = max(raw, 0.0) + latency_offset  # 음수 Δt 는 0 으로 자른 뒤 offset 을 더한다
    h = max(h, 0.0)  # 음수 offset 이 커도 과거로 되돌리지 않는다
    return vec3(p_obs) + vec3(belt_v) * h, h, clipped


def pose_value_stamp(
    prev: tuple[tuple[float, float, float], float] | None,
    position: tuple[float, float, float],
    stamp: float,
) -> tuple[tuple[float, float, float], float]:
    """(위치 값, 그 값이 처음 온 stamp) 갱신. 같은 값이 반복되면 처음 stamp 를 유지한다.

    gateway pose_source: service 는 50 Hz 로 보내지만 값은 0.1 s 마다만 바뀐다 (ADR-0010 69행).
    stamp 를 메시지마다 쓰면 값의 실제 나이(최대 0.1 s 더)를 모르고 TCP 추정이 톱니처럼 뒤처진다.
    """
    if prev is not None and prev[0] == position:
        return prev  # 같은 값 반복 → 그 값이 처음 온 시각 그대로
    return position, stamp  # 값이 바뀐 첫 메시지


def tcp_now(
    pose: Vec,
    pose_stamp: float,
    pose_lag: float,
    last_cmd_v: Vec,
    now: float,
    extrap_max: float,
) -> tuple[np.ndarray, float, bool]:
    """늦게 온 pose → 지금 TCP 추정. (TCP, 자르기 전 지평 s, 상한에서 잘렸나)."""
    h = max(now - pose_stamp, 0.0) + pose_lag  # pose 가 실제로 찍힌 시각부터 지금까지
    capped = h > extrap_max  # 너무 오래된 pose 인가
    h_used = min(h, extrap_max)  # 상한까지만 외삽 (원본 pose 로 돌아가면 추정이 튄다)
    return vec3(pose) + vec3(last_cmd_v) * h_used, h, capped


def tcp_target(p_pred: Vec, z_target: float) -> np.ndarray:
    """예측 박스 윗면 중심 바로 위·아래 → TCP 목표. 높이만 phase 별로 다르다."""
    p = vec3(p_pred)
    return np.array([p[0], p[1], z_target])


def split_error(e: Vec, dir_xy: Vec) -> tuple[float, float]:
    """오차의 수평 성분을 (벨트 방향 성분, 가로 성분 크기) 로 나눈다."""
    e = vec3(e)
    d = vec3(dir_xy)
    e_xy = np.array([e[0], e[1], 0.0])  # 높이 오차는 뺀다
    along = float(e_xy @ d)  # 벨트 방향 성분 (하류 = 양수)
    cross = float(np.linalg.norm(e_xy - along * d))  # 남은 것 = 가로 성분
    return along, cross


def ff_p(e: Vec, belt_v: Vec, dir_xy: Vec, kp_xy: float, use_p: bool) -> np.ndarray:
    """xy 속도 = 벨트 속도(FF) [+ Kp × xy 오차(P)]. 벨트 방향 성분은 0 아래로 내려가지 않는다."""
    b = vec3(belt_v)
    v = np.array([b[0], b[1], 0.0])  # FF: 벨트만큼 같이 간다
    if use_p:
        e = vec3(e)
        v = v + kp_xy * np.array([e[0], e[1], 0.0])  # P: 남은 xy 오차를 메운다
    d = vec3(dir_xy)
    along = float(v @ d)  # 벨트 방향 성분
    if along < 0.0:
        v = v - along * d  # 기다리기: 상류로는 가지 않는다 (가로 성분은 그대로)
    return v


def z_plan(
    phase: str, top_z: float, cfg: ControlConfig, hold_z: bool = False
) -> tuple[float | None, float, float]:
    """phase → (목표 z 또는 None, 내려가는 속도 상한, 올라가는 속도 상한).

    hold_z = 개방 응답을 기다리는 동안 높이 유지 (폭 밖 후퇴, U9b-dd 3절).
    """
    if hold_z:
        return None, 0.0, 0.0  # z 속도 0 (GRASP 와 같음)
    if phase in (fsm.PREPARE, fsm.TRACK):
        return top_z + cfg.approach_dz, cfg.descend_speed, cfg.lift_speed  # 접근 높이로
    if phase == fsm.DESCEND:
        return top_z + cfg.grasp_dz, cfg.descend_speed, 0.0  # 하강 중 위로는 안 간다
    if phase == fsm.LIFT:
        return top_z + cfg.lift_dz, 0.0, cfg.lift_speed  # 위로만
    return None, 0.0, 0.0  # GRASP·VERIFY: z 속도 0 (벨트를 누르지 않게)


def z_speed(
    z_target: float, tcp_z: float, kp_z: float, v_down_max: float, v_up_max: float
) -> float:
    """z 속도 = kp_z × 높이 오차, [−내려가는 상한, +올라가는 상한] 안으로."""
    v = kp_z * (z_target - tcp_z)  # 멀면 빠르게, 가까우면 느리게
    return min(max(v, -v_down_max), v_up_max)


def z_law(phase: str, cfg: ControlConfig, retreat: bool = False) -> str:
    """이 phase 의 z 속도 법칙. trapezoid 이고 DESCEND·LIFT 이고 후퇴가 아니면 사다리꼴, 아니면 P.

    retreat 이면 phase 와 무관하게 P (fsm 에서 후퇴는 LIFT 뿐).

    후퇴 RISING 은 xy 감속(윗면 +10 에서 48 → 0)과 가속 예산을 나눠 써서 사다리꼴 꼬리가 30 mm/s 로
    남는다 → P 유지 (HLD 12.1 (나), 10/13 학민 리뷰).
    """
    if cfg.z_profile == Z_PROFILE_TRAP and phase in TRAP_PHASES and not retreat:
        return Z_LAW_TRAP
    return Z_LAW_P


def z_speed_trap(
    z_target: float,
    tcp_z: float,
    a_dec: float,
    tol: float,
    v_floor: float,
    v_down_max: float,
    v_up_max: float,
) -> float:
    """사다리꼴 z 속도: "목표 + tol" 에서 멈출 만큼만 남기고 최고 속도로 간다 (HLD D1 (a)).

    크기 = min(방향 상한, max(최소 속도, √(2 × 감속 × 조준 거리))). 가속 쪽은 clamp 가 자른다.
    감속 a_dec = 0.8 × max_acc 라 30 Hz 꼬리에서도 틱당 감속 요구(2.9~3.2 mm/s)가 clamp 한도 3.33 아래다.
    """
    e = z_target - tcp_z  # 남은 높이 (양수 = 올라가야 함)
    if e == 0.0:
        return 0.0  # 이미 목표
    lim = v_up_max if e > 0.0 else v_down_max  # 그 방향 속도 상한
    if lim <= 0.0:
        return 0.0  # 그 방향으로는 가지 않는다 (예: DESCEND 중 위로)
    aim = max(abs(e) - tol, 0.0)  # 조준점(목표 + tol)까지 남은 거리
    speed = min(lim, max(v_floor, math.sqrt(2.0 * a_dec * aim)))  # 감속 곡선 · 바닥 · 상한
    return speed if e > 0.0 else -speed  # 부호는 남은 높이 쪽


def z_command(
    z_t: float | None,
    v_down: float,
    v_up: float,
    phase: str,
    tcp_z: float,
    cfg: ControlConfig,
    retreat: bool = False,
) -> float:
    """z_plan 결과 → 이번 틱 z 속도 (clamp 전). 목표가 없으면 0 (GRASP·VERIFY·hold_z)."""
    if z_t is None:
        return 0.0
    if z_law(phase, cfg, retreat) == Z_LAW_TRAP:
        return z_speed_trap(
            z_t, tcp_z, cfg.a_dec, cfg.height_tol_m, TRAP_V_FLOOR_MPS, v_down, v_up
        )  # 사다리꼴 (S2-T14)
    return z_speed(z_t, tcp_z, cfg.kp_z, v_down, v_up)  # P — f9f1d28 과 같은 식·같은 인자


def z_move_time_s(dist_m: float, v: float, cfg: ControlConfig, law: str) -> float:
    """z 로 dist_m 움직이는 예상 시간 s (정지 출발, 해석식). 법칙에 따라 식을 고른다."""
    if law == Z_LAW_TRAP:
        return grip.trap_time_s(dist_m, v, cfg.a_max, cfg.a_dec, cfg.height_tol_m)
    return grip.descend_time_s(dist_m, v, cfg.a_max, cfg.kp_z, cfg.height_tol_m)


def clamp(v: Vec, prev_v: Vec, v_max: float, a_max: float, dt: float) -> tuple[np.ndarray, bool]:
    """속도 크기·가속 크기 상한. (자른 속도, 잘렸나). 0 벡터는 가속 제한 없이 바로 0."""
    v = vec3(v)
    if not np.any(v):
        return zero_cmd(), False  # 정지는 즉시 (ADR-0010: 끊기면 계속 간다 → 멈출 때는 바로 0)
    clamped = False
    n = float(np.linalg.norm(v))
    if n > v_max:
        v = v * (v_max / n)  # 방향은 그대로, 길이만 줄인다
        clamped = True
    prev = vec3(prev_v)
    dv = v - prev  # 한 틱 동안의 속도 변화
    m = float(np.linalg.norm(dv))
    lim = a_max * dt  # 한 틱에 허용하는 변화량
    if m > lim:
        v = prev + dv * (lim / m)  # 같은 방향으로 허용량만큼만 바꾼다
        clamped = True
    return v, clamped


def in_reach(tcp_x: float, x_min: float, x_max: float) -> str | None:
    """추종 가능 구간 판정. 경계값은 구간 안."""
    if tcp_x < x_min:
        return "X_MIN"
    if tcp_x > x_max:
        return "X_MAX"
    return None


def grasp_floor_blocked(top_z: float, cfg: ControlConfig) -> bool:
    """gateway z 하한 때문에 파지 높이 도달 문턱(목표 + height_tol)에 닿을 수 없는가.

    gateway 는 z 가 하한(78 mm)에 닿으면 -z 를 자른다. 문턱이 하한 + 여유보다 낮으면 at_grasp_height 가
    영영 참이 안 되고, DESCEND 는 사각이라 LOST 도 없이 FF 로 x 끝까지 간다 (PR #122 학민 리뷰).
    """
    if z_law(fsm.DESCEND, cfg) == Z_LAW_TRAP:
        # 사다리꼴은 끝 속도가 빨라 목표보다 최대 약 2.2 mm 더 내려갈 수 있다 → 목표 자체에 여유 (HLD D7)
        return top_z + cfg.grasp_dz < cfg.z_min + Z_MIN_MARGIN_TRAP_M
    threshold = top_z + cfg.grasp_dz + cfg.height_tol_m  # at_grasp_height 문턱
    return threshold < cfg.z_min + Z_MIN_MARGIN_M


def descend_blind_max_s(cutoff_m: float, cfg: ControlConfig) -> float:
    """DESCEND 에서 사각에 들어간 뒤 파지 높이까지 걸릴 시간의 상한 s (U9a-dd 2.2).

    예상 하강 시간은 정지 출발 가정이라 이미 내려가는 실제보다 길다 = 안전 쪽.
    예: cutoff 0.030, grasp_dz −0.019 → P 2.439 + 1.0 = 3.44 s (실측 체류 2.10~2.16 s)
        / trapezoid 1.502 + 1.0 = 2.50 s (sim 체류 약 1.13 s, S2T14-hld D5).
    """
    dist = cutoff_m - cfg.grasp_dz  # 사각 진입 높이 → 파지 높이 거리 (grasp_dz 는 음수라 더해진다)
    expect = z_move_time_s(dist, cfg.descend_speed, cfg, z_law(fsm.DESCEND, cfg))
    return expect + BLIND_DWELL_MARGIN_S  # 여유를 더한 상한


def retry_need_s(cfg: ControlConfig, room_need_s: float) -> float:
    """GRASP 실패 순간부터 재시도 1회를 끝낼 시간 s = 재상승 예상 + (하강 + 닫힘 상한) (U9b-dd 1절).

    재상승은 PREPARE(항상 P) 법칙이다 (S2T14-hld D2·D6).
    예: 재상승 59 mm → 2.66 s + room_need 5.14 s = 7.80 s (trapezoid 면 room_need 4.20 → 6.86 s).
    """
    dist = cfg.approach_dz - cfg.grasp_dz  # 파지 높이 → 접근 높이 (grasp_dz 는 음수)
    rise = z_move_time_s(dist, cfg.lift_speed, cfg, z_law(fsm.PREPARE, cfg))
    return rise + room_need_s  # 다시 올라가서, 내려가고, 닫는다


def lift_max_s(cfg: ControlConfig) -> float:
    """후퇴 상승 체류 상한 s = 파지 → 들기 높이 예상 + 여유 (U9b-dd 1절). 정상 LIFT 는 경고에만 쓴다.

    후퇴는 두 모드 모두 P 라 상한도 P 식 (HLD 12.1 (나)). 예: 69 mm → 2.785 + 1.0 = 3.78 s
    (실측 후퇴 RISING 2.27~2.30 s). 사다리꼴 정상 LIFT(≈1.6 s)에는 경고 문턱으로만 쓰여 느슨하다.
    """
    dist = cfg.lift_dz - cfg.grasp_dz  # 파지 높이 → 들기 높이
    expect = z_move_time_s(dist, cfg.lift_speed, cfg, z_law(fsm.LIFT, cfg, retreat=True))
    return expect + BLIND_DWELL_MARGIN_S  # U9-a S 와 같은 여유


def grasp_room_need_s(cfg: ControlConfig, close_time_max_s: float) -> float:
    """정렬 뒤 하강 + 닫힘에 걸릴 시간 s (x 여유 검사, HLD D6 · S2T14-dd 2.3).

    예: P 2.639 + 2.5 = 5.14 s / trapezoid 1.702 + 2.5 = 4.20 s.
    """
    dist = cfg.approach_dz - cfg.grasp_dz  # 접근 높이 → 파지 높이 (grasp_dz 는 음수)
    t_desc = z_move_time_s(dist, cfg.descend_speed, cfg, z_law(fsm.DESCEND, cfg))
    return t_desc + close_time_max_s  # 그동안 벨트를 따라간다


def retry_room_ok(
    tcp_x: float | None,
    need_s: float | None,
    belt_speed: float,
    cfg: ControlConfig,
    margin_m: float,
) -> bool:
    """지금 TCP x 에서 재시도 1회를 끝낼 x 여유가 있나. 모르면 없음 = 후퇴 (안전 쪽, U9b-dd 3절)."""
    if tcp_x is None or need_s is None:
        return False  # TCP·필요 시간을 모른다
    return grip.grasp_room_ok(tcp_x, cfg.x_max, belt_speed, need_s, margin_m)


def retreat_xy(tcp: Vec, top_z: float, cfg: ControlConfig) -> str:
    """후퇴 중 xy 규칙: 윗면을 넘기 전엔 박스와 같이(FF), 넘었거나 x 끝이면 0 = 수직 (U9b-dd 3절)."""
    t = vec3(tcp)
    below = float(t[2]) < top_z + RETREAT_CLEAR_MM / 1000.0  # 핑거 끝이 아직 윗면 + 10 mm 아래
    inside = float(t[0]) < cfg.x_max  # x 끝 가드 (후퇴는 x 끝 검사로 끊지 않으므로 여기서 막는다)
    return FF if (below and inside) else ZERO


def xy_rule(phase: str, visible: bool) -> str:
    """phase 와 박스가 보이는지 → xy 규칙 (HLD 3절)."""
    if phase in (fsm.PREPARE, fsm.TRACK, fsm.DESCEND):
        return FF_P if visible else FF  # 안 보여도 박스와 같이 간다
    if phase == fsm.GRASP:
        return FF  # 정렬은 끝났다고 보고 벨트만 따라간다
    return ZERO  # LIFT(수직만)·VERIFY


# ---------------------------------------------------------------------- 틱 입구


@dataclass(frozen=True, eq=False)
class Geometry:
    """한 틱의 기하 계산 결과 (phase 와 무관한 값 + 전환 플래그)."""

    tcp: np.ndarray  # 보정 TCP
    tcp_horizon_s: float  # 외삽 지평 (자르기 전)
    tcp_extrap_capped: bool  # 외삽 지평이 상한에서 잘렸나
    visible: bool  # 사각 아님 + 최신 메시지 valid (노드가 계산)
    has_obs: bool  # 유효 관측이 한 번이라도 있나
    p_pred: np.ndarray | None  # 예측 박스 윗면 중심
    pred_horizon_s: float | None  # 예측 지평
    dt_clipped: bool  # 박스 stamp 가 미래였나
    top_z: float | None  # 마지막 유효 관측 윗면 z
    obs_age_s: float | None  # 마지막 유효 관측 나이 (촬영 시각 기준)
    err_along: float | None  # 접근 높이 목표 기준 오차의 벨트 방향 성분
    err_cross: float | None  # 같은 오차의 가로 성분 크기
    aligned: bool  # TRACK → DESCEND 조건
    at_grasp_height: bool  # DESCEND → GRASP 조건
    at_lift_height: bool  # LIFT → VERIFY 조건
    reach: str | None  # None | X_MIN | X_MAX | Z_MIN


def geometry(
    tcp_est: tuple[np.ndarray, float, bool],
    obs_xyz: Vec | None,
    obs_stamp: float | None,
    visible: bool,
    now: float,
    cfg: ControlConfig,
) -> Geometry:
    """예측·오차·전환 플래그. tcp_est 는 노드가 먼저 부른 tcp_now() 결과."""
    tcp, tcp_h, capped = tcp_est
    tcp = vec3(tcp)
    reach = in_reach(float(tcp[0]), cfg.x_min, cfg.x_max)  # 관측 없이도 계산 (x 가 먼저)
    if obs_xyz is None or obs_stamp is None:
        return Geometry(
            tcp=tcp,
            tcp_horizon_s=tcp_h,
            tcp_extrap_capped=capped,
            visible=False,  # 관측이 없으면 보일 수 없다
            has_obs=False,
            p_pred=None,
            pred_horizon_s=None,
            dt_clipped=False,
            top_z=None,
            obs_age_s=None,
            err_along=None,
            err_cross=None,
            aligned=False,
            at_grasp_height=False,
            at_lift_height=False,
            reach=reach,
        )
    p_pred, pred_h, clipped = predict(obs_xyz, obs_stamp, now, cfg.belt_v, cfg.latency_offset_s)
    top_z = float(vec3(obs_xyz)[2])  # 벨트 z 속도 0 → 예측해도 높이는 같다
    obs_age = max(now - obs_stamp, 0.0)  # 관측이 얼마나 묵었나
    approach_z = top_z + cfg.approach_dz
    e = tcp_target(p_pred, approach_z) - tcp  # 접근 높이 기준 오차
    along, cross = split_error(e, cfg.belt_dir_xy)
    aligned = (
        visible
        and abs(along) <= cfg.align_along_m  # 벨트 방향 (엄격)
        and cross <= cfg.align_cross_m  # 가로
        and abs(float(tcp[2]) - approach_z) <= cfg.height_tol_m  # 접근 높이에 있다
        and obs_age <= cfg.blind_entry_max_age_s  # 사각 진입 직전 관측이 신선하다
    )
    at_grasp = float(tcp[2]) <= top_z + cfg.grasp_dz + cfg.height_tol_m
    if reach is None and grasp_floor_blocked(top_z, cfg):
        reach = "Z_MIN"  # 파지 높이에 닿을 수 없다 → OUT_OF_REACH (cause REACH_Z_MIN)
    at_lift = float(tcp[2]) >= top_z + cfg.lift_dz - cfg.height_tol_m
    return Geometry(
        tcp=tcp,
        tcp_horizon_s=tcp_h,
        tcp_extrap_capped=capped,
        visible=visible,
        has_obs=True,
        p_pred=p_pred,
        pred_horizon_s=pred_h,
        dt_clipped=clipped,
        top_z=top_z,
        obs_age_s=obs_age,
        err_along=along,
        err_cross=cross,
        aligned=aligned,
        at_grasp_height=at_grasp,
        at_lift_height=at_lift,
        reach=reach,
    )


@dataclass(frozen=True, eq=False)
class Command:
    """이번 틱에 발행할 속도와 그 이유."""

    vel: np.ndarray  # clamp 뒤 속도 m/s
    rule: str  # FF_P | FF | ZERO | ZERO_NO_POSE | ZERO_NO_OBS | ZERO_STOP
    tcp_target: np.ndarray | None  # 이번 phase 의 TCP 목표
    error: np.ndarray | None  # tcp_target − TCP
    clamped: bool  # 속도·가속 상한으로 잘렸나
    z_v_req: float | None = None  # clamp 전 z 속도 요구값 (목표 z 가 없으면 None, S2-T14 로그)


def command(
    phase: str,
    stopping: bool,
    terminal: bool,
    geo: Geometry | None,
    prev_v: Vec,
    dt: float,
    cfg: ControlConfig,
    retreat: bool = False,
    hold_z: bool = False,
    z_floor: float | None = None,
) -> Command:
    """새 phase 기준 속도. stopping·terminal·pose 없음·관측 없음이면 0.

    retreat = 안전 후퇴 중 (xy 는 retreat_xy), hold_z = 개방 기다리며 높이 유지 (U9b).
    z_floor = J6 회전 중 z 하한 m (시야 보험, S2-T18). None 이면 지금과 같다.
    """
    if stopping or terminal:
        return Command(zero_cmd(), ZERO_STOP, None, None, False)  # 항상 0 (U1 회신 ⑤)
    if geo is None:
        return Command(zero_cmd(), ZERO_NO_POSE, None, None, False)
    if not geo.has_obs or geo.p_pred is None or geo.top_z is None:
        return Command(zero_cmd(), ZERO_NO_OBS, None, None, False)
    rule = retreat_xy(geo.tcp, geo.top_z, cfg) if retreat else xy_rule(phase, geo.visible)
    z_t, v_down, v_up = z_plan(phase, geo.top_z, cfg, hold_z)
    if z_t is not None and z_floor is not None:
        z_t = max(z_t, z_floor)  # 회전 중에는 이 높이 아래로 내려가지 않는다 (S2-T18 D2-2)
    target = tcp_target(geo.p_pred, z_t if z_t is not None else float(geo.tcp[2]))
    e = target - geo.tcp  # z 목표가 없으면 높이 오차 0
    if rule == ZERO:
        v = zero_cmd()
    else:
        v = ff_p(e, cfg.belt_v, cfg.belt_dir_xy, cfg.kp_xy, use_p=(rule == FF_P))
    vz = z_command(z_t, v_down, v_up, phase, float(geo.tcp[2]), cfg, retreat)  # 후퇴는 P
    v[2] = vz
    v, clamped = clamp(v, prev_v, cfg.v_max, cfg.a_max, dt)
    return Command(v, rule, target, e, clamped, vz if z_t is not None else None)


def finite_vec(v: Vec) -> np.ndarray | None:
    """길이 3 벡터, NaN·inf 가 있으면 None."""
    a = vec3(v)
    return a if all(math.isfinite(x) for x in a) else None


# ---------------------------------------------------------------------- 벨트 속도 추정 (U9-c, 로그 전용)


def belt_speed_fit(
    samples: Sequence[tuple[float, Vec]],
    dir_xy: Vec,
    max_points: int,
    min_points: int,
    min_span_s: float,
) -> tuple[float | None, float | None]:
    """관측열 (촬영 stamp, 위치) → 벨트 방향 속도 m/s 와 시간 폭 s. 모르면 None.

    박스 위치를 벨트 방향 거리 s 로 바꿔 시각 t 에 직선 s = a + v·t 를 맞춘 기울기 v (최소제곱).
    제어(FF)에는 쓰지 않는다 — 실기 정확도 확인 뒤 결정 (10/12, design/U9c-dd.md 4.3·10절).
    """
    pts = list(samples)[-max_points:]  # 최근 점만
    if len(pts) < min_points:
        return None, None  # 점이 모자람
    t0 = float(pts[0][0])
    t = np.array([float(p[0]) - t0 for p in pts])  # 첫 점 기준 시각 (큰 수를 빼 계산 오차 줄임)
    d = vec3(dir_xy)
    s = np.array([float(vec3(p[1])[:2] @ d[:2]) for p in pts])  # 벨트 방향 거리 (가로·높이 무시)
    span = float(t[-1] - t[0])  # 맞춤에 쓴 시간 폭
    if span < min_span_s:
        return None, span  # 시간 폭이 짧음
    tc = t - t.mean()  # 평균을 뺀 시각
    den = float(tc @ tc)
    if den <= 0.0:
        return None, span  # 모든 stamp 가 같음 (방어)
    v = float(tc @ (s - s.mean())) / den  # 최소제곱 기울기
    return (v if math.isfinite(v) else None), span
