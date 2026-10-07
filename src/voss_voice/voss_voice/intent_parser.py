"""intent_parser — /voss/voice/transcript → /voss/voice/intent (docs/interfaces/intent_json.md).

- stop 키워드는 LLM·zone_map 을 기다리지 않고 즉시 발행한다.
- 나머지는 FastAPI /ai/intent 로 해석한 뒤 intent_logic.decide 로 다시 검증한다.
- query_history 는 Intent 로 보내지 않고 Spring Boot /api/stats 를 조회해 직접 답한다.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_msgs.msg import Intent, SortState, ZoneMap
from voss_voice import http_client
from voss_voice.intent_logic import (
    SayDeduper,
    ZoneMapView,
    decide,
    is_stop,
    stats_sentence,
    stop_decision,
)

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

        self._view: ZoneMapView | None = None
        self._state = ""
        self._box_id = ""
        self._dedup = SayDeduper()

        self._pub_intent = self.create_publisher(Intent, "/voss/voice/intent", QOS_EVENTS)
        self._pub_say = self.create_publisher(String, "/voss/voice/say", QOS_EVENTS)

        # 상태·zone_map 은 HTTP 대기 중에도 갱신되게 별도 그룹, transcript 는 한 번에 하나씩
        fast = ReentrantCallbackGroup()
        self.create_subscription(
            ZoneMap, "/voss/sort/zone_map", self._on_zone_map, QOS_ZONE_MAP, callback_group=fast
        )
        self.create_subscription(
            SortState, "/voss/sort/state", self._on_state, QOS_EVENTS, callback_group=fast
        )
        self.create_subscription(
            String,
            "/voss/voice/transcript",
            self._on_transcript,
            QOS_EVENTS,
            callback_group=MutuallyExclusiveCallbackGroup(),
        )
        self.get_logger().info("intent_parser ready (zone_map 대기 중)")

    def _on_zone_map(self, msg: ZoneMap) -> None:
        self._view = ZoneMapView.from_entries(
            [(e.dong, e.zone, list(e.aliases)) for e in msg.entries], msg.version
        )
        self.get_logger().info(f"zone_map v{msg.version}: {', '.join(self._view.dongs)}")

    def _on_state(self, msg: SortState) -> None:
        self._state, self._box_id = msg.state, msg.box_id

    def _on_transcript(self, msg: String) -> None:
        text = msg.data.strip()
        if not text:
            return
        t0 = time.monotonic()
        # 발화 시점의 질문 상태를 먼저 잡아 둔다 (늦은 답이 다음 질문에 붙지 않게)
        state, box_id = self._state, self._box_id

        if is_stop(text):  # 안전: LLM·zone_map 대기 없음
            self._publish(stop_decision(text).intent)
            self.get_logger().info(f"stop (local keyword) {1000 * (time.monotonic() - t0):.0f} ms")
            return

        llm = None
        if self._view is not None:
            llm = http_client.post_intent(
                text,
                self._view.llm_allowed(),
                base=self.get_parameter("ai_base").value,
                timeout_s=float(self.get_parameter("llm_timeout_s").value),
            )
        d = decide(
            llm,
            text,
            self._view,
            state,
            box_id,
            bool(self.get_parameter("allow_update_zone_map").value),
        )

        if d.kind == "publish":
            self._publish(d.intent)
        elif d.kind == "query":
            resp = http_client.get_stats(d.query, base=self.get_parameter("api_base").value)
            self._say(stats_sentence(d.query, resp))
        else:
            self._say(d.say)
        self.get_logger().info(
            f"{d.kind} {d.intent or d.query or d.say} {1000 * (time.monotonic() - t0):.0f} ms"
        )

    def _publish(self, fields: dict) -> None:
        m = Intent()
        m.type, m.dong, m.zone = fields["type"], fields["dong"], fields["zone"]
        m.count, m.raw_text, m.box_id = fields["count"], fields["raw_text"], fields["box_id"]
        self._pub_intent.publish(m)

    def _say(self, text: str) -> None:
        if text and self._dedup.allow(text, time.monotonic()):
            self._pub_say.publish(String(data=text))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = IntentParserNode()
    executor = MultiThreadedExecutor(num_threads=3)
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
