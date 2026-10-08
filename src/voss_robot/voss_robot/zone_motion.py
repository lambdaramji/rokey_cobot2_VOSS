"""MoveToZone 경로 계획 (ROS·두산 import 없음). voss_msgs.md MoveToZone, measurements #6.

- 좌표는 voss_config 그대로 **플랜지** posx(mm·deg). 두산 move_line 은 펜던트 TCP(GripperDA_v1)가 걸린 상태라
  TCP posx 로 보내야 해서, gateway 가 보낼 때 flange_to_tcp 로 바꾼다.
- 경로(#51 MC-015, T35): 현재 x·y 에서 플랜지 z ≥ safe_z(446.6 = TCP z 200)까지 수직 상승 → 그 높이로 수평 이동
  → 목표 위에서 수직 하강. 목표가 safe_z 이상이면(관측 자세 450.2) 하강 없이 바로 간다.
- 격자(measurements #6): X(벨트 방향) 한 줄. 칸 오프셋 = (col − (cols−1)/2) × pitch → A·B·C −60/0/+60,
  재확인·보류 ±30. slot 0 이 −X 끝. rows > 1 이면 Y 도 같은 식(지금 설정은 모두 1).
"""

from __future__ import annotations

from collections.abc import Sequence

SAFE_Z_MM = 446.6  # 플랜지 z, TCP z 200 (measurements #6 홈 복귀)


def slot_offset(grid: Sequence[float], slot: int) -> tuple[float, float]:
    """grid = [cols, rows, pitch_mm] → (dx, dy) mm. 범위 밖이면 ValueError."""
    cols, rows, pitch = int(grid[0]), int(grid[1]), float(grid[2])
    if not 0 <= slot < cols * rows:
        raise ValueError(f"slot {slot} 는 0~{cols * rows - 1}")
    col, row = slot % cols, slot // cols
    return (col - (cols - 1) / 2.0) * pitch, (row - (rows - 1) / 2.0) * pitch


def slot_pose(zone_pose: Sequence[float], grid: Sequence[float], slot: int) -> list[float]:
    """구역 중심 플랜지 posx + 칸 오프셋 (자세 그대로)."""
    dx, dy = slot_offset(grid, slot)
    p = [float(v) for v in zone_pose]
    return [p[0] + dx, p[1] + dy, *p[2:]]


def plan_move(
    current: Sequence[float], target: Sequence[float], safe_z: float = SAFE_Z_MM, eps: float = 0.5
) -> list[tuple[str, list[float]]]:
    """현재 → 목표 플랜지 posx 경유점 [(이름, posx)]. 이미 그 자리인 단계는 뺀다."""
    cur = [float(v) for v in current]
    tgt = [float(v) for v in target]
    hz = max(safe_z, tgt[2])  # 수평 이동 높이
    steps: list[tuple[str, list[float]]] = []
    if cur[2] < hz - eps:
        steps.append(("rise", [cur[0], cur[1], hz, *cur[3:]]))
    over = [tgt[0], tgt[1], hz, *tgt[3:]]
    last = steps[-1][1] if steps else cur
    if abs(last[0] - over[0]) > eps or abs(last[1] - over[1]) > eps or abs(last[2] - over[2]) > eps:
        steps.append(("over", over))
    elif any(abs(a - b) > 0.05 for a, b in zip(last[3:], over[3:], strict=True)):
        steps.append(("over", over))  # 같은 자리에서 자세만 바꿈
    if tgt[2] < hz - eps:
        steps.append(("descend", tgt))
    return steps
