"""intent_parser — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class IntentParserNode(Node):
    def __init__(self) -> None:
        super().__init__("intent_parser")
        self.get_logger().info("intent_parser started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = IntentParserNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
