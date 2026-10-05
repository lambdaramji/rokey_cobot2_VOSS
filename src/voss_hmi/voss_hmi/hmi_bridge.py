"""hmi_bridge — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class HmiBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("hmi_bridge")
        self.get_logger().info("hmi_bridge started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HmiBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
