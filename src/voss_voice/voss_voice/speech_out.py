"""speech_out — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class SpeechOutNode(Node):
    def __init__(self) -> None:
        super().__init__("speech_out")
        self.get_logger().info("speech_out started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SpeechOutNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
