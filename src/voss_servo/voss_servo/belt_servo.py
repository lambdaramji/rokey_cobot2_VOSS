"""belt_servo — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class BeltServoNode(Node):
    def __init__(self) -> None:
        super().__init__("belt_servo")
        self.get_logger().info("belt_servo started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BeltServoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
