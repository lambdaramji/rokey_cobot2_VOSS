"""robot_gateway 가 쓰는 좌표 계산 (순수 함수, ROS·두산 import 없음).

단위: 두산 posx = [x, y, z, rx, ry, rz] mm·deg, 자세는 ZYZ 오일러 (R = Rz(rx)·Ry(ry)·Rz(rz)).
voss_config 의 zones·observe_pose 는 플랜지 기준, /voss/robot/pose·servo_cmd 는 TCP 기준이다 (#53 MC-010).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Pose = list[float]  # [x, y, z, rx, ry, rz] mm·deg


def _rz(a: float) -> list[list[float]]:
    """z 축 회전 행렬 (a: rad)."""
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _ry(a: float) -> list[list[float]]:
    """y 축 회전 행렬 (a: rad)."""
    c, s = math.cos(a), math.sin(a)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """3×3 행렬 곱."""
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def zyz_to_matrix(rx: float, ry: float, rz: float) -> list[list[float]]:
    """두산 ZYZ 오일러(deg) → 회전 행렬."""
    r = map(math.radians, (rx, ry, rz))
    a, b, c = r
    return _matmul(_matmul(_rz(a), _ry(b)), _rz(c))


def zyz_to_quaternion(rx: float, ry: float, rz: float) -> tuple[float, float, float, float]:
    """두산 ZYZ 오일러(deg) → 쿼터니언 (x, y, z, w). geometry_msgs 순서."""
    m = zyz_to_matrix(rx, ry, rz)
    tr = m[0][0] + m[1][1] + m[2][2]
    # 대각합 부호에 따라 수치적으로 안정한 식을 고른다
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w, x = 0.25 * s, (m[2][1] - m[1][2]) / s
        y, z = (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        w, x = (m[2][1] - m[1][2]) / s, 0.25 * s
        y, z = (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        w, x = (m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s
        y, z = 0.25 * s, (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        w, x = (m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s
        y, z = (m[1][2] + m[2][1]) / s, 0.25 * s
    if w < 0.0:  # w ≥ 0 으로 부호를 맞춰 같은 자세가 같은 값으로 나오게 한다
        x, y, z, w = -x, -y, -z, -w
    return (x, y, z, w)


def _wrap_deg(a: float) -> float:
    """각도를 (−180, 180] 으로."""
    a = math.fmod(a, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def normalize_down_pose(pose: Sequence[float], tol_deg: float = 0.5) -> Pose:
    """수직 아래 자세(ry ≈ ±180°)의 rx·rz 를 (rx − rz, 180, 0) 한 가지로 맞춘다.

    ry = ±180° 에서는 Rz(a)·Ry(180)·Rz(c) = Rz(a − c)·Ry(180) 이라 rx − rz 만 의미가 있다.
    측정값마다 rx/rz 가 제각각(35/−54, 159/70 …)이라 그대로 movel 하면 보간 중 손목이 돈다
    (measurements #6). 수직이 아니면 그대로 돌려준다.
    """
    x, y, z, rx, ry, rz = (float(v) for v in pose)
    if abs(abs(ry) - 180.0) > tol_deg:
        return [x, y, z, rx, ry, rz]  # 수직 아래가 아니면 손대지 않는다
    return [x, y, z, _wrap_deg(rx - rz), 180.0, 0.0]


def flange_to_tcp(pose: Sequence[float], tcp_offset_mm: Sequence[float]) -> Pose:
    """플랜지 posx → TCP posx. 툴 회전은 0 이라 자세는 같고 위치만 R·offset 만큼 옮긴다."""
    x, y, z, rx, ry, rz = (float(v) for v in pose)
    m = zyz_to_matrix(rx, ry, rz)
    d = [sum(m[i][k] * tcp_offset_mm[k] for k in range(3)) for i in range(3)]
    return [x + d[0], y + d[1], z + d[2], rx, ry, rz]


def tcp_to_flange(pose: Sequence[float], tcp_offset_mm: Sequence[float]) -> Pose:
    """TCP posx → 플랜지 posx (flange_to_tcp 의 역)."""
    x, y, z, rx, ry, rz = (float(v) for v in pose)
    m = zyz_to_matrix(rx, ry, rz)
    d = [sum(m[i][k] * tcp_offset_mm[k] for k in range(3)) for i in range(3)]
    return [x - d[0], y - d[1], z - d[2], rx, ry, rz]


def flange_to_ros_pose(
    flange: Sequence[float], tcp_offset_mm: Sequence[float]
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """플랜지 posx(mm·deg) → /voss/robot/pose 값: TCP 위치(m), 쿼터니언(x, y, z, w)."""
    tcp = flange_to_tcp(flange, tcp_offset_mm)
    pos = (tcp[0] / 1000.0, tcp[1] / 1000.0, tcp[2] / 1000.0)  # mm → m
    return pos, zyz_to_quaternion(tcp[3], tcp[4], tcp[5])


def grid_slot_offset_mm(cols: int, rows: int, pitch_mm: float, slot: int) -> tuple[float, float]:
    """격자 칸 번호 → 구역 중심 기준 (dx, dy) mm. cols = X(벨트 방향), 행 우선 번호.

    A·B·C 3×1 → slot 0/1/2 = X −60/0/+60, 재확인·보류 2×1 → slot 0/1 = X −30/+30 (#57).
    """
    if cols < 1 or rows < 1:
        raise ValueError(f"grid 크기 오류: cols={cols}, rows={rows}")
    if not 0 <= slot < cols * rows:
        raise ValueError(f"slot {slot} 이 범위 밖 (0~{cols * rows - 1})")
    col, row = slot % cols, slot // cols
    dx = (col - (cols - 1) / 2.0) * pitch_mm  # 가운데 칸이 0 이 되도록
    dy = (row - (rows - 1) / 2.0) * pitch_mm
    return (dx, dy)


def slot_pose(zone_pose: Sequence[float], cols: int, rows: int, pitch_mm: float, slot: int) -> Pose:
    """구역 중심 자세 + 격자 오프셋 → 놓을 자세. 트레이 긴 변 = 베이스 X(벨트 −0.74°, 무시)."""
    dx, dy = grid_slot_offset_mm(cols, rows, pitch_mm, slot)
    p = [float(v) for v in zone_pose]
    p[0] += dx
    p[1] += dy
    return p


def clamp_speed(v: Sequence[float], vmax: float) -> list[float]:
    """속도 벡터의 크기가 vmax 를 넘으면 방향은 두고 크기만 줄인다."""
    n = math.sqrt(sum(c * c for c in v))
    if vmax < 0.0:
        raise ValueError("vmax 는 0 이상")
    if n <= vmax or n == 0.0:
        return [float(c) for c in v]
    k = vmax / n
    return [c * k for c in v]


def in_box(xyz: Sequence[float], lo: Sequence[float], hi: Sequence[float]) -> bool:
    """점이 축 정렬 상자 [lo, hi] 안에 있는가 (작업 영역 리밋)."""
    return all(lo[i] <= xyz[i] <= hi[i] for i in range(3))
