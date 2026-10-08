"""/voss/robot/pose 소스 판단 (ROS·두산 import 없음). pose_source = service | joint_states (#118).

- joint_states: 컨트롤러 /dsr01/joint_states(100 Hz) 최신 관절 → 두산 fkin(등록 TCP posx) → 플랜지.
  get_current_tool_flange_posx 는 10/08 오후 값이 0.1 s 마다만 바뀌었다.
- fkin 은 **펜던트에 등록된 TCP** 기준이라 등록이 voss_config tcp_offset_mm 과 다르면 pose 가 조용히 틀어진다.
  그래서 쓰기 전에 서비스 플랜지(등록과 무관)와 비교해 확인한다(#118 리뷰 박병후 🔴1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

JOINT_NAMES = tuple(f"joint_{i}" for i in range(1, 7))


def joints_deg(names: Sequence[str], positions_rad: Sequence[float]) -> list[float] | None:
    """JointState(name·position rad) → joint_1..6 순서 deg. 이름이 모자라면 None."""
    pos = dict(zip(names, positions_rad, strict=False))
    if any(n not in pos for n in JOINT_NAMES):
        return None
    return [math.degrees(float(pos[n])) for n in JOINT_NAMES]


def fresh(now_ns: int, stamp_ns: int, max_age_s: float) -> bool:
    """stamp 가 max_age_s 안이면 True (미래 stamp 는 시계 차이로 보고 0.05 s 까지 허용)."""
    age = (now_ns - stamp_ns) * 1e-9
    return -0.05 <= age <= max_age_s


class StartupCheck:
    """joint_states+fkin 플랜지와 서비스 플랜지 비교. tol_mm 안이면 통과, fails 번 연속 벗어나면 실패.

    로봇이 움직이는 중이면 서비스 값이 묵어(0.1 s) 차이가 나므로 한 번 실패로 끊지 않는다.
    등록 TCP 가 다르면 차이가 늘 크게(오프셋만큼) 나와 연속 실패가 된다."""

    def __init__(self, tol_mm: float = 1.0, fails: int = 50) -> None:
        self.tol_mm = tol_mm
        self.fails = fails
        self.misses = 0
        self.last_diff_mm = float("nan")

    def feed(self, js_flange: Sequence[float], srv_flange: Sequence[float]) -> str:
        """'pass' | 'fail' | '' (아직 판단 못 함)."""
        self.last_diff_mm = math.dist(js_flange[:3], srv_flange[:3])
        if self.last_diff_mm <= self.tol_mm:
            return "pass"
        self.misses += 1
        return "fail" if self.misses >= self.fails else ""
