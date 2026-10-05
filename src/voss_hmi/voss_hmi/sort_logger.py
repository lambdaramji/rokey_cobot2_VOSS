"""sort_logger — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class SortLoggerNode(Node):
    def __init__(self) -> None:
        super().__init__("sort_logger")
        self.get_logger().info("sort_logger started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SortLoggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
