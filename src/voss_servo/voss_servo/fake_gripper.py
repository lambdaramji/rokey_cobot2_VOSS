"""fake_gripper — sim 전용 가짜 RG2. 계획표대로 빈손·쥠·폭 밖을 응답한다 (design/U9b-dd.md 6.1).

- 왜: gateway dry_run 의 가짜 RG2 는 물체 폭이 기동 때 고정이라 "1차 빈손 → 2차 쥠"(재시도)을 못 만든다.
- 서비스 `/voss/sim/gripper` (voss_msgs/Gripper). sim.launch 가 `gripper:=fake` 일 때 belt_servo 의
  `/voss/robot/gripper` 를 이 이름으로 바꿔 잇는다(SetRemap). 인터페이스(서비스 형식)는 그대로다.
- 판정 규칙(순수 함수 fake_reply): 요청 폭 ≥ 60 mm = 개방 / 이미 닫혀 있는데 또 닫기 = 확인 재닫힘(VERIFY,
  결과 유지·계획 소비 안 함) / 그 밖 = 계획표의 다음 값. 계획을 다 쓰면 마지막 값을 반복한다.
- 지연은 콜백 안에서 sleep 으로 흉내 낸다 (이 노드 전용 프로세스, 요청은 한 번에 하나 — belt_servo 와 무관).
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from voss_msgs.srv import Gripper

SERVICE = "/voss/sim/gripper"  # sim.launch 가 belt_servo 의 /voss/robot/gripper 를 여기로 remap
OPEN_MIN_MM = 60.0  # 요청 폭이 이 이상이면 개방 (사전 개방 90, 닫기 39)
# 계획 값 → 보고 폭 mm (빈손 실측 38.0~38.7, 쥠 40.6~41.5 — measurements-1008 #14, 폭 밖 > hold_max 44.0)
WIDTH = {"empty": 38.4, "held": 41.0, "wide": 46.5}
GRIP = {"empty": False, "held": True, "wide": True}  # 계획 값 → 물체 감지 비트
OPEN, CLOSE, VERIFY = "open", "close", "verify"  # 요청 종류 (지연을 고르는 데 쓴다)


@dataclass(frozen=True)
class FakeGripState:
    """가짜 그리퍼 상태: 닫기 몇 번 했나 + 지금 닫혀 있으면 그 결과."""

    n_close: int = 0  # 계획표에서 쓴 닫기 수
    closed: str | None = None  # 마지막 닫힘 결과 (열려 있으면 None)


@dataclass(frozen=True)
class FakeReply:
    """Gripper 응답 값 (ROS 메시지로 바꾸기 전)."""

    ok: bool
    width_mm: float  # 보고 폭
    grip_detected: bool  # 물체 감지
    message: str  # 응답 코드


def parse_plan(text: str) -> tuple[str, ...]:
    """'empty,held' → ('empty', 'held'). 비었거나 모르는 값이 있으면 ValueError."""
    plan = tuple(p.strip().lower() for p in text.split(",") if p.strip())  # 빈 칸은 버린다
    if not plan:
        raise ValueError("fake_gripper plan 이 비었다 (예: empty,held)")
    bad = [p for p in plan if p not in WIDTH]
    if bad:
        raise ValueError(f"fake_gripper plan 에 모르는 값 {bad} (허용: {sorted(WIDTH)})")
    return plan


def fake_reply(
    state: FakeGripState, plan: tuple[str, ...], width_req_mm: float, pre_open_mm: float
) -> tuple[FakeGripState, FakeReply, str]:
    """요청 하나 → (새 상태, 응답, 종류). ROS·시계를 쓰지 않는다."""
    if width_req_mm >= OPEN_MIN_MM:  # 개방: 열고 결과를 지운다
        return replace(state, closed=None), FakeReply(True, pre_open_mm, False, "OK"), OPEN
    if state.closed is not None:  # 이미 닫혀 있는데 또 닫기 = VERIFY (결과 유지, 계획 소비 안 함)
        r = state.closed
        return state, FakeReply(True, WIDTH[r], GRIP[r], "OK"), VERIFY
    r = plan[min(state.n_close, len(plan) - 1)]  # 계획표 다음 (다 쓰면 마지막 반복)
    nxt = FakeGripState(n_close=state.n_close + 1, closed=r)
    return nxt, FakeReply(True, WIDTH[r], GRIP[r], "OK"), CLOSE


class FakeGripperNode(Node):
    """계획표대로 응답하는 가짜 RG2 서비스."""

    def __init__(self) -> None:
        super().__init__("fake_gripper")
        p = self.declare_parameter
        self.plan = parse_plan(str(p("plan", "held").value))  # 틀리면 ValueError → main 이 종료 1
        self.delay = {
            OPEN: float(p("open_s", 1.0).value),  # 개방 지연 (미측정, 판단값)
            CLOSE: float(p("close_s", 1.7).value),  # 닫힘 지연 (10/10 실측 1.6~2.1)
            VERIFY: float(p("verify_s", 0.2).value),  # 확인 재닫힘 지연 (실측 0.17)
        }
        self.pre_open_mm = float(p("pre_open_mm", 90.0).value)  # 개방 보고 폭
        self.state = FakeGripState()
        self.create_service(Gripper, SERVICE, self._on_request)
        self.get_logger().info(
            f"fake_gripper: {SERVICE} plan={list(self.plan)} 지연 {self.delay} (sim 전용)"
        )

    def _on_request(self, req: Gripper.Request, resp: Gripper.Response) -> Gripper.Response:
        """요청 하나: 판정 → 지연 → 응답."""
        state, r, kind = fake_reply(self.state, self.plan, float(req.width), self.pre_open_mm)
        time.sleep(self.delay[kind])  # RG2 가 움직이는 시간 흉내
        self.state = state
        resp.ok = r.ok
        resp.width_actual = float(r.width_mm)
        resp.grip_detected = r.grip_detected
        resp.message = r.message
        self.get_logger().info(
            f"fake_gripper {kind} 요청 {req.width:.1f} mm → 폭 {r.width_mm} grip {r.grip_detected} "
            f"(닫기 {state.n_close}번째)"
        )
        return resp


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    try:
        node = FakeGripperNode()
    except ValueError as exc:  # 모르는 plan
        rclpy.logging.get_logger("fake_gripper").error(str(exc))
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
