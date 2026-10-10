"""fake_box — 카메라·box_tracker 대신 /voss/vision/box 를 30 Hz 로 보내는 시험 노드 (sim 전용).

- 설계: design/U3-dd.md 4절, pseudo 3절.
- 박스 하나를 벨트 속도로 움직인다. 시나리오: normal · invalid_after_s(T 뒤 position_valid=false)
  · lost_after_s(T 뒤 발행 안 함 = 미검출) · two_boxes(다른 track_id 박스 하나 더).
- 계약(topics.md): BoxTrack position_base = 박스 윗면 중심(m, base_link), stamp = 촬영 시각 역할(발행 시각),
  발행 QoS best_effort·volatile·depth 1, 미검출 프레임은 발행하지 않는다.
- 벨트 속도·방향은 필수 파라미터다 (sim.launch 가 voss_config 에서 읽어 넘긴다 — 숫자를 여기 복사하지 않는다).
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import numpy as np
import rclpy
from geometry_msgs.msg import Point
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from voss_msgs.msg import BoxTrack

SCENARIOS = ("normal", "invalid_after_s", "lost_after_s", "two_boxes")
# 기본 시작 위치 (m): 카메라 유효 범위 상류 끝 x · 관측 자세 y · 벨트 면 73.8 + 박스 27 mm (U3-dd 4.1)
DEFAULT_START_M = (-0.100, -0.271, 0.1008)
DEFAULT_SECOND_OFFSET_M = (0.060, 0.040, 0.0)  # two_boxes 둘째: 60 mm 하류 · 40 mm 옆
# 발행 QoS: box_tracker 와 같은 계약 (topics.md QoS 표)
QOS_BOX_PUB = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


@dataclass(frozen=True)
class BoxSample:
    """한 틱에 보낼 박스 하나 (ROS 메시지로 바꾸기 전)."""

    track_id: int
    xyz: tuple[float, float, float]  # 윗면 중심 (m, base_link)
    valid: bool  # position_valid


@dataclass(frozen=True)
class FakeBoxConfig:
    """시나리오 계산에 필요한 값 (단위 m·m/s·s)."""

    scenario: str
    track_id: int
    start: tuple[float, float, float]  # 시작 위치 (m)
    vel: tuple[float, float, float]  # 벨트 속도 벡터 (m/s)
    invalid_after_s: float
    lost_after_s: float
    second_track_id: int
    second_offset: tuple[float, float, float]  # 둘째 박스 = 첫째 + 이만큼 (m)


def belt_velocity(speed_cmps: float, direction) -> tuple[float, float, float]:
    """벨트 속도 cm/s 와 방향 → 속도 벡터 m/s (방향은 길이 1 로 나눠 방향만 쓴다)."""
    d = np.asarray(direction, dtype=float)  # [x, y, z]
    n = float(np.linalg.norm(d))  # 방향 벡터 길이
    if d.shape != (3,) or n <= 1e-9:
        raise ValueError(f"direction_base 가 길이 3 의 0 아닌 벡터가 아님: {list(direction)}")
    v = float(speed_cmps) / 100.0 * d / n  # cm/s → m/s, 단위 방향
    return (float(v[0]), float(v[1]), float(v[2]))


def position_at(start, vel, t: float) -> tuple[float, float, float]:
    """등속 이동: 시작 + 속도 × 시간."""
    p = np.asarray(start, dtype=float) + np.asarray(vel, dtype=float) * float(t)
    return (float(p[0]), float(p[1]), float(p[2]))


def make_config(
    scenario: str,
    track_id: int,
    start,
    speed_cmps: float,
    direction,
    invalid_after_s: float,
    lost_after_s: float,
    second_track_id: int,
    second_offset,
) -> FakeBoxConfig:
    """파라미터 → FakeBoxConfig. 모르는 시나리오·잘못된 방향이면 ValueError."""
    if scenario not in SCENARIOS:
        raise ValueError(f"모르는 scenario: {scenario} (가능: {', '.join(SCENARIOS)})")
    return FakeBoxConfig(
        scenario=scenario,
        track_id=int(track_id),
        start=tuple(float(x) for x in start),
        vel=belt_velocity(speed_cmps, direction),
        invalid_after_s=float(invalid_after_s),
        lost_after_s=float(lost_after_s),
        second_track_id=int(second_track_id),
        second_offset=tuple(float(x) for x in second_offset),
    )


def samples_at(cfg: FakeBoxConfig, t: float) -> list[BoxSample]:
    """시작 뒤 t 초에 보낼 박스 목록 (design/U3-dd.md 4.2 표)."""
    p1 = position_at(cfg.start, cfg.vel, t)  # 첫째 박스 위치
    if cfg.scenario == "invalid_after_s":
        return [BoxSample(cfg.track_id, p1, t < cfg.invalid_after_s)]  # 위치는 계속 움직인다
    if cfg.scenario == "lost_after_s":
        return [BoxSample(cfg.track_id, p1, True)] if t < cfg.lost_after_s else []  # 미검출
    if cfg.scenario == "two_boxes":
        p2 = position_at(np.add(cfg.start, cfg.second_offset), cfg.vel, t)  # 같은 속도로 나란히
        return [BoxSample(cfg.track_id, p1, True), BoxSample(cfg.second_track_id, p2, True)]
    return [BoxSample(cfg.track_id, p1, True)]  # normal


class FakeBoxNode(Node):
    """samples_at 결과를 BoxTrack 으로 바꿔 rate_hz 로 발행한다."""

    def __init__(self) -> None:
        super().__init__("fake_box")
        free = ParameterDescriptor(dynamic_typing=True)  # 기본값 없는 필수 값 (정수·실수 모두 받음)
        p = self.declare_parameter
        scenario = p("scenario", "normal").value
        track_id = p("track_id", 1).value
        start = p("start_xyz_m", list(DEFAULT_START_M)).value
        speed = p("speed_cmps", None, free).value  # 필수 (voss_config belt.speed_cmps)
        direction = p("direction_base", None, free).value  # 필수 (voss_config belt.direction_base)
        rate = float(p("rate_hz", 30.0).value)
        invalid_after = p("invalid_after_s", 8.0).value
        lost_after = p("lost_after_s", 8.0).value
        second_id = p("second_track_id", 2).value
        second_offset = p("second_offset_m", list(DEFAULT_SECOND_OFFSET_M)).value
        if speed is None or direction is None:
            raise ValueError("speed_cmps·direction_base 필수 (sim.launch 가 voss_config 에서 넘김)")
        self.cfg = make_config(
            scenario,
            track_id,
            start,
            speed,
            direction,
            invalid_after,
            lost_after,
            second_id,
            second_offset,
        )  # 틀리면 ValueError → main 이 종료 코드 1
        self.pub = self.create_publisher(BoxTrack, "/voss/vision/box", QOS_BOX_PUB)
        self.t0 = time.monotonic()  # 시나리오 시계 시작 (노드 생성 시각)
        self.create_timer(1.0 / rate, self._tick)
        c = self.cfg
        self.get_logger().info(
            f"fake_box: scenario={c.scenario} track={c.track_id} "
            f"start_mm={[round(x * 1000, 1) for x in c.start]} "
            f"vel_mm_s={[round(x * 1000, 2) for x in c.vel]} rate={rate:g} Hz "
            f"invalid_after={c.invalid_after_s:g}s lost_after={c.lost_after_s:g}s"
        )

    def _tick(self) -> None:
        """한 틱: 지금 보낼 박스들을 BoxTrack 으로 발행."""
        t = time.monotonic() - self.t0  # 시작 뒤 경과 (s)
        for s in samples_at(self.cfg, t):
            msg = BoxTrack()
            msg.track_id = s.track_id
            msg.stamp = self.get_clock().now().to_msg()  # 촬영 시각 역할
            msg.position_base = Point(x=s.xyz[0], y=s.xyz[1], z=s.xyz[2])
            msg.position_valid = s.valid
            msg.position_source = BoxTrack.SOURCE_HAND_EYE
            msg.calib_version = "fake"  # u·v·bbox 는 기본값 0
            self.pub.publish(msg)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    try:
        node = FakeBoxNode()
    except ValueError as exc:  # 필수 값 없음·모르는 시나리오
        rclpy.logging.get_logger("fake_box").error(str(exc))
        rclpy.try_shutdown()
        sys.exit(1)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Ctrl+C·launch 종료
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
