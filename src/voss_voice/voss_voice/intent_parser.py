"""intent_parser — /voss/voice/transcript → /voss/voice/intent (docs/interfaces/intent_json.md).

처리 흐름은 transcript_flow.TranscriptFlow (pytest 대상). 이 노드는 ROS 입출력만 맡는다.
- stop 키워드는 LLM·zone_map·앞 발화의 대기와 무관하게 즉시 발행한다.
- query_history 는 Intent 로 보내지 않고 Spring Boot /api/stats 를 조회해 직접 답한다.
"""

from __future__ import annotations

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_msgs.msg import Intent, SortState, ZoneMap
from voss_voice import http_client
from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import TranscriptFlow

QOS_EVENTS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
QOS_ZONE_MAP = QoSProfile(
    depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL
)


class IntentParserNode(Node):
    def __init__(self) -> None:
        super().__init__("intent_parser")
        self.declare_parameter("ai_base", http_client.AI_BASE)
        self.declare_parameter("api_base", http_client.API_BASE)
        self.declare_parameter("llm_timeout_s", 3.0)
        self.declare_parameter("allow_update_zone_map", False)  # C 범위, G0 이후 결정

        self._pub_intent = self.create_publisher(Intent, "/voss/voice/intent", QOS_EVENTS)
        self._pub_say = self.create_publisher(String, "/voss/voice/say", QOS_EVENTS)

        ai_base = self.get_parameter("ai_base").value
        api_base = self.get_parameter("api_base").value
        timeout = float(self.get_parameter("llm_timeout_s").value)
        self._flow = TranscriptFlow(
            post_intent=lambda t, a: http_client.post_intent(t, a, base=ai_base, timeout_s=timeout),
            get_stats=lambda q: http_client.get_stats(q, base=api_base),
            publish=self._publish,
            say=lambda s: self._pub_say.publish(String(data=s)),
            allow_update_zone_map=bool(self.get_parameter("allow_update_zone_map").value),
        )

        # 모두 Reentrant: transcript 가 LLM 을 기다리는 중에도 다음 transcript(정지)와
        # state·zone_map 이 처리된다. LLM·REST 직렬화는 TranscriptFlow 의 잠금이 맡는다.
        group = ReentrantCallbackGroup()
        self.create_subscription(
            ZoneMap, "/voss/sort/zone_map", self._on_zone_map, QOS_ZONE_MAP, callback_group=group
        )
        self.create_subscription(
            SortState, "/voss/sort/state", self._on_state, QOS_EVENTS, callback_group=group
        )
        self.create_subscription(
            String, "/voss/voice/transcript", self._on_transcript, QOS_EVENTS, callback_group=group
        )
        self.get_logger().info("intent_parser ready (zone_map 대기 중)")

    def _on_zone_map(self, msg: ZoneMap) -> None:
        self._flow.view = ZoneMapView.from_entries(
            [(e.dong, e.zone, list(e.aliases)) for e in msg.entries], msg.version
        )
        self.get_logger().info(f"zone_map v{msg.version}: {', '.join(self._flow.view.dongs)}")

    def _on_state(self, msg: SortState) -> None:
        self._flow.state, self._flow.box_id = msg.state, msg.box_id

    def _on_transcript(self, msg: String) -> None:
        kind, ms = self._flow.handle(msg.data)
        if kind != "empty":
            self.get_logger().info(f"{kind} '{msg.data.strip()}' {ms:.0f} ms")

    def _publish(self, fields: dict) -> None:
        m = Intent()
        m.type, m.dong, m.zone = fields["type"], fields["dong"], fields["zone"]
        m.count, m.raw_text, m.box_id = fields["count"], fields["raw_text"], fields["box_id"]
        self._pub_intent.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = IntentParserNode()
    executor = MultiThreadedExecutor(num_threads=4)  # LLM 대기 2건 + stop + state·zone_map
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
