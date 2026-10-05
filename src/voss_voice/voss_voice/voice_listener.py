"""voice_listener — 인터페이스는 docs/interfaces/topics.md 참조. 아직 골격만 있다."""

import rclpy
from rclpy.node import Node


class VoiceListenerNode(Node):
    def __init__(self) -> None:
        super().__init__("voice_listener")
        self.get_logger().info("voice_listener started (skeleton)")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceListenerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
