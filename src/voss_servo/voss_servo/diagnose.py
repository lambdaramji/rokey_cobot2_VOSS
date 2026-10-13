"""belt_servo 진단 계산 (순수 모듈 — ROS·시계·파일을 쓰지 않는다).

- 로그·경고만 만든다. 제어 출력과 FSM 전이에는 쓰지 않는다 (U9-c).
- LOST 의 세부 원인: VISION_DOWN(비전 전체 끊김 추정) / ROBOT_STALLED(명령은 나갔는데 로봇 정지).
  특정 원인이 없으면 None → 노드는 fsm 이 낸 cause(BOX_MISSING 등)를 그대로 둔다.
- 측정 TCP 속도: pose 값이 바뀐 시점끼리의 차분 (service pose 의 0.1 s 계단 대응).
- 벨트 속도 경고: 추정값과 설정값 차이가 커진 채 새 관측이 이어질 때 goal 당 한 번.
- 설계: src/voss_servo/design/U9c-{hld,dd,pseudo}.md
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# ---------------------------------------------------------------------- 상수 (모두 제안값, 실측 전)
# 30 Hz 서보 루프 기준. 근거는 design/U9c-dd.md 4.5절

# pose 값이 이 시간보다 오래 그대로면 "로봇이 멈췄다"로 본다.
# service pose 는 0.1 s 계단 + 메시지 간격 0.02 s → 계단 한 칸으로는 멈춤이 되지 않게 약 2배
POSE_HOLD_MAX_S = 0.2
# 이보다 작은 명령에서는 정지 판단을 하지 않는다 (정상 추종 명령 ≈ 0.048 m/s = 벨트 FF)
STALL_CMD_MIN_MPS = 0.01
# 측정 속도가 명령의 이 비율보다 작으면 "안 움직임" 한 틱
STALL_RATIO = 0.25
# 그런 틱이 이만큼 연속이면 ROBOT_STALLED (10틱 ≈ 0.33 s).
# 재검 램프 시뮬 최대 6틱(service pose), 10/10 로그 재생 0틱(joint_states). lost_timeout 0.5 s 보다 짧다
STALL_TICKS_N = 10
# 내 트랙과 다른 트랙의 마지막 수신 차가 이 안이면 "같은 순간에 끊김" = 카메라 프레임 끊김으로 본다.
# 한 프레임의 트랙은 id 순으로 몇 ms 안에 연달아 발행된다 (box_tracker.py:300~309)
SIMUL_LOSS_S = 0.2
# 벨트 속도 직선 맞춤: 최근 90점(≈3 s). 잡음 σ 1 mm 가정 시 기울기 σ 0.12 mm/s (0.25 %)
FIT_MAX_POINTS = 90
FIT_MIN_POINTS = 15  # 0.5 s 분량보다 적으면 맞추지 않는다
FIT_MIN_SPAN_S = 0.5  # 시간 폭이 이보다 짧으면 맞추지 않는다
# 경고는 시간 폭이 이 이상일 때만 (2.0 s = 60점 → 기울기 σ 0.46 %)
WARN_MIN_SPAN_S = 2.0
# goal 끝 INFO 줄에 "차이 큼" 표시 문턱 — 10/12 결정의 "2 % 이상이면 추정 FF 후보" (판단은 로그로 오프라인)
SPEED_INFO_RATIO = 0.02
# WARN 문턱 (B안, 10/12 사용자) — 10/12 결정의 "10 % 이상이면 goal 거부" 단계와 같은 값. 지금은 경고만
SPEED_WARN_RATIO = 0.10
# 차이가 큰 새 관측이 이만큼 연속이면 WARN (15회 ≈ 0.5 s, 한두 번 튐 무시)
SPEED_WARN_TICKS_M = 15

# --- LOST 세부 원인 (cause 문자열) ---
VISION_DOWN = "VISION_DOWN"  # 비전 전체가 끊긴 것으로 추정
ROBOT_STALLED = "ROBOT_STALLED"  # 명령은 나가는데 로봇이 안 움직임

PoseValue = tuple[Sequence[float], float]  # (위치 [x, y, z] m, 그 값이 처음 온 stamp s)


def measured_velocity(
    prev: PoseValue | None, cur: PoseValue | None, now: float, hold_max_s: float
) -> list[float] | None:
    """pose 값 차분 → TCP 속도 [x, y, z] m/s. 모르면 None."""
    if cur is None:
        return None  # pose 를 아직 못 받음
    if now - cur[1] > hold_max_s:
        return [0.0, 0.0, 0.0]  # 값이 오래 그대로 = 로봇이 멈춰 있다
    if prev is None:
        return None  # 값이 하나뿐이라 차분을 못 한다
    dt = cur[1] - prev[1]  # 두 값이 처음 온 시각의 차
    if dt <= 0.0:
        return None  # 시각이 같거나 뒤로 감 (방어)
    if dt > hold_max_s:
        return (
            None  # 오래 멈춰 있던 값에서 처음 바뀜 → 이 구간 속도는 모른다 (goal 전 정지, 재검 R1)
        )
    return [(c - p) / dt for c, p in zip(cur[0], prev[0], strict=True)]  # 축별 Δ위치 / Δ시간


def speed_of(v: Sequence[float] | None) -> float | None:
    """벡터 크기 (None 이면 None)."""
    if v is None:
        return None
    return math.sqrt(sum(x * x for x in v))


def stall_count(prev_n: int, cmd_speed: float, meas_speed: float | None) -> int:
    """'명령은 나가는데 로봇이 안 움직임' 연속 틱 수를 갱신한다."""
    if meas_speed is None:
        return 0  # 측정을 모르면 멈췄다고 하지 않는다
    if cmd_speed >= STALL_CMD_MIN_MPS and meas_speed < STALL_RATIO * cmd_speed:
        return prev_n + 1  # 이번 틱도 안 움직임
    return 0  # 움직였거나 명령이 작음 → 처음부터


def lost_cause(
    pub_count: int | None, my_rx: float | None, other_rx: float | None, stall_n: int
) -> str | None:
    """LOST 틱의 세부 원인. 특정 원인이 없으면 None (노드는 fsm cause 를 그대로 둔다)."""
    if pub_count == 0:
        return VISION_DOWN  # box_tracker 발행자가 없다. None(조회 실패)은 0 으로 치지 않는다
    if other_rx is not None and my_rx is not None and abs(other_rx - my_rx) <= SIMUL_LOSS_S:
        return VISION_DOWN  # 다른 트랙도 같은 순간에 끊김 = 카메라 프레임이 통째로 끊긴 것으로 추정
    if stall_n >= STALL_TICKS_N:
        return ROBOT_STALLED  # 로봇이 멈춰 있는 동안 박스가 시야 밖으로 흘러감
    return None  # 내 트랙만 사라짐 (박스 1개일 때도 여기 — D1 한계)


def speed_warn_step(
    run: int,
    warned: bool,
    est: float | None,
    set_speed: float,
    span: float | None,
    new_obs: bool,
    ratio: float,
) -> tuple[int, bool]:
    """벨트 속도 경고 카운터 한 걸음 → (새 run, 지금 WARN 을 낼까)."""
    if not new_obs:
        return run, False  # 새 관측이 없으면 세지 않는다 (사각 뒤 같은 추정값으로 채우지 않게)
    if est is None or span is None or span < WARN_MIN_SPAN_S or set_speed <= 0.0:
        return 0, False  # 추정이 아직 믿을 만하지 않다
    differs = abs(est - set_speed) / set_speed >= ratio  # 설정과 얼마나 다른가
    run = run + 1 if differs else 0
    return run, (not warned) and run >= SPEED_WARN_TICKS_M  # goal 당 한 번만


def speed_note(est: float | None, set_speed: float | None, span: float | None, n: int) -> str:
    """goal 끝 INFO 한 줄 (cm/s 표기). 2 % 이상 차이면 표시를 붙인다."""
    if est is None or set_speed is None or set_speed <= 0.0:
        return f"벨트 속도 추정 없음 (관측 {n}점) — 로그 전용"
    diff = (est - set_speed) / set_speed  # 부호 있는 비율
    mark = f" ≥ {SPEED_INFO_RATIO * 100:.0f} %" if abs(diff) >= SPEED_INFO_RATIO else ""
    return (
        f"벨트 속도 추정 {est * 100:.2f} cm/s (설정 {set_speed * 100:.2f}, "
        f"{diff * 100:+.1f} %{mark}, 폭 {span or 0.0:.1f} s, {n}점) — 로그 전용, FF 는 설정값"
    )


def speed_warn_text(est: float, set_speed: float, span: float) -> str:
    """벨트 속도 WARN 한 줄."""
    diff = (est - set_speed) / set_speed
    return (
        f"벨트 속도 추정 {est * 100:.2f} cm/s ≠ 설정 {set_speed * 100:.2f} cm/s "
        f"({diff * 100:+.1f} %, 새 관측 {SPEED_WARN_TICKS_M}회 연속, 폭 {span:.1f} s) — "
        "FF 는 설정값 그대로, 벨트 속도 설정 확인"
    )
