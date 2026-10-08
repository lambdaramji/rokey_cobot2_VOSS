"""MoveToZone 경로 계획 (ROS·두산 import 없음). voss_msgs.md MoveToZone, measurements #6.

- 좌표는 voss_config 그대로 **플랜지** posx(mm·deg). 두산 move_line 은 펜던트 TCP(GripperDA_v1)가 걸린 상태라
  TCP posx 로 보내야 해서, gateway 가 보낼 때 flange_to_tcp 로 바꾼다.
- 경로(#51 MC-015, T35): 현재 x·y 에서 플랜지 z ≥ safe_z(446.6 = TCP z 200)까지 수직 상승 → 그 높이로 수평 이동
  → 목표 위에서 수직 하강. 목표가 safe_z 이상이면(관측 자세 450.2) 하강 없이 바로 간다.
- 격자(measurements #6): X(벨트 방향) 한 줄. 칸 오프셋 = offset + (col − (cols−1)/2) × pitch → A·B·C
  −60/0/+60. slot 0 이 −X 끝. rows > 1 이면 Y 도 같은 식(지금 설정은 모두 1). 먼 트레이(x ≈ 675)는 수직
  자세로 +X 쪽에 팔이 닿지 않아(10/08 ikin) offset 으로 칸을 −X 쪽에 둔다: 재확인 1칸 −60, 보류 −60/0.
"""

from __future__ import annotations

from collections.abc import Sequence

SAFE_Z_MM = 446.6  # 플랜지 z, TCP z 200 (measurements #6 홈 복귀)


def slot_offset(grid: Sequence[float], slot: int) -> tuple[float, float]:
    """grid = [cols, rows, pitch_mm(, offset_mm)] → (dx, dy) mm. offset_mm = 칸 줄 중심의 X 위치(트레이 중심
    기준, 먼 트레이에서 팔이 닿는 −X 쪽으로 당김 — 10/08). 범위 밖이면 ValueError."""
    cols, rows, pitch = int(grid[0]), int(grid[1]), float(grid[2])
    off = float(grid[3]) if len(grid) > 3 else 0.0
    if not 0 <= slot < cols * rows:
        raise ValueError(f"slot {slot} 는 0~{cols * rows - 1}")
    col, row = slot % cols, slot // cols
    return off + (col - (cols - 1) / 2.0) * pitch, (row - (rows - 1) / 2.0) * pitch


def slot_pose(zone_pose: Sequence[float], grid: Sequence[float], slot: int) -> list[float]:
    """구역 중심 플랜지 posx + 칸 오프셋 (자세 그대로)."""
    dx, dy = slot_offset(grid, slot)
    p = [float(v) for v in zone_pose]
    return [p[0] + dx, p[1] + dy, *p[2:]]


def plan_move(
    current: Sequence[float], target: Sequence[float], safe_z: float = SAFE_Z_MM, eps: float = 0.5
) -> list[tuple[str, list[float]]]:
    """현재 → 목표 플랜지 posx 경유점 [(이름, posx)]. safe_z = 수평 이동 높이(먼 구역은 gateway 가 낮춰 넘김).

    현재가 safe_z 보다 낮으면 그 x·y 에서 safe_z 까지만 수직 상승한다(목표가 더 높아도 — 먼 구역 위에서는
    더 높이 못 간다, 10/08 실기). 목표가 safe_z 이상이면(관측 자세) 거기서 목표로 바로 간다(비스듬히 상승).
    목표가 낮으면 safe_z 높이로 목표 위까지 수평 이동한 뒤 수직 하강한다. 이미 그 자리인 단계는 뺀다."""
    cur = [float(v) for v in current]
    tgt = [float(v) for v in target]
    hz = float(safe_z)
    steps: list[tuple[str, list[float]]] = []
    if cur[2] < hz - eps:
        steps.append(("rise", [cur[0], cur[1], hz, *cur[3:]]))
    last = steps[-1][1] if steps else cur
    over = list(tgt) if tgt[2] >= hz - eps else [tgt[0], tgt[1], hz, *tgt[3:]]
    moved = any(abs(a - b) > eps for a, b in zip(last[:3], over[:3], strict=True))
    turned = any(abs(a - b) > 0.05 for a, b in zip(last[3:], over[3:], strict=True))
    if moved or turned:
        steps.append(("over", over))
    if tgt[2] < hz - eps:
        steps.append(("descend", tgt))
    return steps
