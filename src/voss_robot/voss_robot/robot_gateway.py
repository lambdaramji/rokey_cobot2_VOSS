"""robot_gateway — 인터페이스는 docs/interfaces/topics.md 참조.

두산 서비스는 SerialCallQueue 하나로만 부른다(CLAUDE.md 절대 규칙 3). dry_run 이면 두산·RG2 에
연결하지 않고 로그만 남긴다(개인 PC 개발용). 서비스·pose 발행은 다음 단계(T32 STEP 2)에서 붙인다.
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from voss_robot.call_queue import SerialCallQueue


class RobotGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("robot_gateway")
        # dry_run 기본값 true: 실수로 띄워도 로봇이 움직이지 않게 한다
        self.dry_run = self.declare_parameter("dry_run", True).value
        self.queue = SerialCallQueue()  # 두산 서비스 호출은 전부 이 큐 하나로
        mode = "dry_run (두산·RG2 연결 안 함)" if self.dry_run else "real"
        self.get_logger().info(f"robot_gateway started: {mode}")

    def destroy_node(self) -> None:
        self.queue.close()  # 대기 작업을 버리고 작업 스레드를 끝낸다
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RobotGatewayNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Ctrl-C·launch 종료는 정상 종료
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
