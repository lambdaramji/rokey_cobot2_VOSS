"""box_tracker — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class BoxTrackerNode(Node):
    def __init__(self) -> None:
        super().__init__("box_tracker")
        self.get_logger().info("box_tracker started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BoxTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
