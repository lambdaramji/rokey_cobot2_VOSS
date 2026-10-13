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

import math
from collections.abc import Sequence

SAFE_Z_MM = 446.6  # 플랜지 z, TCP z 200 (measurements #6 홈 복귀)
ARC_STEP_DEG = 40.0  # 베이스 뒤를 피해 도는 수평 이동의 한 구간 각도


def _layers(grid: Sequence[float]) -> tuple[int, float]:
    """grid 5·6번째 = (layers, layer_mm). 없으면 1층(voss_config.md grid layers)."""
    return (int(grid[4]), float(grid[5])) if len(grid) > 5 else (1, 0.0)


def slot_offset(grid: Sequence[float], slot: int) -> tuple[float, float]:
    """grid = [cols, rows, pitch_mm(, offset_mm(, layers, layer_mm(, pitch_y_mm(, col_dy × cols))))] → (dx, dy) mm.
    offset_mm = 칸 줄 중심의 X 위치(트레이 중심 기준, 먼 트레이에서 팔이 닿는 −X 쪽으로 당김 — 10/08). pitch_y_mm =
    Y 줄 간격(없으면 pitch_mm). row 0 = +Y 줄. col_dy = 열마다 Y 보정(10/12 팔레트 +X 끝 열 1206 에 +10 을 시도 — 모자라 트레이를 +Y 80 mm 옮김).
    2층부터는 1층 칸 위치를 다시 쓴다. 범위 밖이면 ValueError."""
    cols, rows, pitch = int(grid[0]), int(grid[1]), float(grid[2])
    pitch_y = float(grid[6]) if len(grid) > 6 else pitch
    off = float(grid[3]) if len(grid) > 3 else 0.0
    per = cols * rows
    layers, _ = _layers(grid)
    if not 0 <= slot < per * layers:
        raise ValueError(f"slot {slot} 는 0~{per * layers - 1}")
    col, row = (slot % per) % cols, (slot % per) // cols
    dy = float(grid[7 + col]) if len(grid) >= 7 + cols else 0.0
    # row 0 = +Y 줄(작업자가 보는 위쪽: 왼쪽 위부터 0·1·2, 아래 3·4·5 — 10/12 실기 요청), 1줄이면 0
    return off + (col - (cols - 1) / 2.0) * pitch, ((rows - 1) / 2.0 - row) * pitch_y + dy


def slot_pose(zone_pose: Sequence[float], grid: Sequence[float], slot: int) -> list[float]:
    """구역 중심 플랜지 posx + 칸 오프셋 + 층 높이 (자세 그대로)."""
    dx, dy = slot_offset(grid, slot)
    _, layer_mm = _layers(grid)
    dz = (slot // (int(grid[0]) * int(grid[1]))) * layer_mm
    p = [float(v) for v in zone_pose]
    return [p[0] + dx, p[1] + dy, p[2] + dz, *p[3:]]


def row_stage_slot(grid: Sequence[float], slot: int) -> int:
    """트레이 안 이동의 출입구 칸 = slot 과 같은 Y 줄의 −X 끝 칸(1층). C 칸 2 → 0, 칸 5 → 3 (10/12 실기 요청)."""
    cols, rows = int(grid[0]), int(grid[1])
    return (slot % (cols * rows)) // cols * cols


def pick_pose(slot_flange: Sequence[float], dz_mm: float) -> list[float]:
    """PICK 파지 자세 = 놓기 칸 자세 + dz. 놓기 자세는 쥔 박스 밑면 +5 mm(10/06 교시)라 핑거 끝은 바닥 약 +13 mm
    *(추정)* → 10/11 실기로 dz 기본 −8(핑거 끝 ≈ 박스 밑면 +5, voss_msgs.md MoveToZone PICK)."""
    p = [float(v) for v in slot_flange]
    return [p[0], p[1], p[2] + float(dz_mm), *p[3:]]


def pick_grip_ok(ok: bool, detected: bool, width_mm: float, lo: float, hi: float) -> str:
    """PICK 닫힘 결과 판정. 통과면 "", 아니면 이유(GRIP_FAIL 메시지 뒤에 붙인다).
    성공 = 닫힘 완료 + grip_detected + 보고폭이 [lo, hi] (voss_msgs.md MoveToZone PICK, belt_servo 와 같은 기준)."""
    if not ok:
        return "닫힘 응답 실패"
    if not detected:
        return f"grip 없음(폭 {width_mm:.1f} mm)"
    if not lo <= width_mm <= hi:
        return f"폭 {width_mm:.1f} mm 가 {lo:.1f}~{hi:.1f} 밖"
    return ""


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
        steps += front_arc(last, over, hz)
        steps.append(("over", over))
    if tgt[2] < hz - eps:
        steps.append(("descend", tgt))
    return steps


def crosses_back(a: Sequence[float], b: Sequence[float]) -> bool:
    """x·y 선분 a→b 가 베이스 뒤(−X 반직선, y = 0·x < 0)를 지나는지 — J1 이 ±180° 를 넘는다."""
    (x1, y1), (x2, y2) = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
    if (y1 > 0) == (y2 > 0) or y1 == y2:
        return False
    return x1 + (x2 - x1) * (-y1) / (y2 - y1) < 0.0


def front_arc(
    start: Sequence[float], end: Sequence[float], z: float, step_deg: float = ARC_STEP_DEG
) -> list[tuple[str, list[float]]]:
    """수평 이동이 베이스 뒤를 지나면(OBSERVE ↔ 팔레트, 10/12 실기: 뒤로 돌다 축 가까이서 느려져 TIMEOUT) 앞쪽
    (트레이 쪽, +X)으로 도는 경유점 [("arcN", posx)]. 각도는 atan2 그대로 이어 ±180° 를 넘지 않게, 반지름은
    양 끝 사이를 고르게, 높이 z, 자세는 end. 뒤를 안 지나면 []."""
    if not crosses_back(start, end):
        return []
    ts, te = math.atan2(start[1], start[0]), math.atan2(end[1], end[0])
    rs, re = math.hypot(start[0], start[1]), math.hypot(end[0], end[1])
    n = max(2, math.ceil(abs(math.degrees(te - ts)) / step_deg))
    out = []
    for k in range(1, n):
        t = k / n
        a, r = ts + (te - ts) * t, rs + (re - rs) * t
        out.append(
            (f"arc{k}", [r * math.cos(a), r * math.sin(a), float(z), *[float(v) for v in end[3:]]])
        )
    return out
