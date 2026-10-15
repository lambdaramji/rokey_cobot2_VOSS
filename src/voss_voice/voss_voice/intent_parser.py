"""intent_parser — /voss/voice/transcript → /voss/voice/intent (docs/interfaces/intent_json.md).

처리 흐름은 transcript_flow.TranscriptFlow (pytest 대상). 이 노드는 ROS 입출력만 맡는다.
- stop 키워드는 LLM·zone_map·앞 발화의 대기와 무관하게 즉시 발행한다.
- query_history 는 Intent 로 보내지 않고 Spring Boot /api/stats 를 조회해 직접 답한다.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
import uuid

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_msgs.msg import Intent, SortState, ZoneMap
from voss_voice import http_client
from voss_voice.command_delivery import attempt_stop
from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import CommandDeliveryError, TranscriptFlow

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
        self.declare_parameter("command_transport", "ros")
        self.declare_parameter("web_context_stream", False)
        self.declare_parameter("allow_update_zone_map", False)  # C 범위, G0 이후 결정

        self._command_transport = str(self.get_parameter("command_transport").value)
        if self._command_transport not in ("ros", "web_api"):
            raise ValueError("command_transport must be ros or web_api")
        self._api_base = str(self.get_parameter("api_base").value)
        self._text_seen: dict[str, float] = {}
        self._text_seen_lock = threading.Lock()
        self._last_state_at = 0.0
        self._state_source = ""
        self._zone_map_source = ""
        self._ros_view = None
        self._last_spoken_question: tuple[str, str, str] | None = None
        self._context_stop = threading.Event()

        self._pub_intent = self.create_publisher(Intent, "/voss/voice/intent", QOS_EVENTS)
        self._pub_say = self.create_publisher(String, "/voss/voice/say", QOS_EVENTS)
        self._pub_text_reply = self.create_publisher(String, "/voss/voice/text/reply", QOS_EVENTS)

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
        self.create_subscription(
            String, "/voss/voice/text", self._on_text_command, QOS_EVENTS, callback_group=group
        )
        if bool(self.get_parameter("web_context_stream").value):
            self.create_timer(1.0, self._expire_state)
            threading.Thread(target=self._stream_web_context, daemon=True).start()
        self.get_logger().info("intent_parser ready (zone_map 대기 중)")

    def _on_zone_map(self, msg: ZoneMap) -> None:
        self._flow.view = ZoneMapView.from_entries(
            [(e.dong, e.zone, list(e.aliases)) for e in msg.entries], msg.version
        )
        self._ros_view = self._flow.view
        self.get_logger().info(f"zone_map v{msg.version}: {', '.join(self._flow.view.dongs)}")
        self._zone_map_source = "ros"

    def _on_state(self, msg: SortState) -> None:
        self._flow.state, self._flow.box_id = msg.state, msg.box_id
        self._state_source = "ros"
        self._last_state_at = time.monotonic()

    def _expire_state(self) -> None:
        if self._last_state_at and time.monotonic() - self._last_state_at > 3.0:
            self._flow.state, self._flow.box_id = "", ""
            self._last_state_at = 0.0
            self._last_spoken_question = None

    def _stream_web_context(self) -> None:
        """Web backend SSE에서 구역 지도와 질문 상태를 받아 PC 간 ROS 누락을 보완한다."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = f"{self._api_base}/api/stream"
        while not self._context_stop.is_set():
            try:
                with opener.open(url, timeout=8) as response:
                    event, data = "", ""
                    for raw in response:
                        if self._context_stop.is_set():
                            return
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data = line[5:].strip()
                        elif not line:
                            self._on_web_context_event(event, data)
                            event, data = "", ""
            except (
                urllib.error.URLError,
                http.client.HTTPException,
                TimeoutError,
                OSError,
                ValueError,
            ) as error:
                self.get_logger().warn(f"웹 문맥 스트림 끊김 ({type(error).__name__}); 재연결")
            self._invalidate_web_context()
            self._context_stop.wait(1.0)

    def _invalidate_web_context(self) -> None:
        """SSE 단절 뒤 웹에서만 받은 질문·구역 지도를 재사용하지 않는다."""
        if getattr(self, "_state_source", "") == "web":
            self._flow.state, self._flow.box_id = "", ""
            self._last_state_at = 0.0
            self._last_spoken_question = None
            self._state_source = ""
        if getattr(self, "_zone_map_source", "") == "web":
            self._flow.view = getattr(self, "_ros_view", None)
            self._zone_map_source = ""

    def _on_web_context_event(self, event: str, data: str) -> None:
        if event not in ("zone_map", "state") or len(data) > 65536:
            return
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                return
            if event == "zone_map":
                entries = parsed["entries"]
                view = ZoneMapView.from_entries(
                    [(e["dong"], e["zone"], e["aliases"]) for e in entries],
                    str(parsed.get("version", "")),
                )
                if view.dongs:
                    self._flow.view = view
                    self._zone_map_source = "web"
            elif isinstance(parsed.get("state"), str) and isinstance(parsed.get("box_id"), str):
                self._flow.state, self._flow.box_id = parsed["state"], parsed["box_id"]
                self._state_source = "web"
                self._last_state_at = time.monotonic()
                question = parsed.get("pending_question")
                if (
                    parsed["state"] == "ASKING"
                    and parsed["box_id"]
                    and isinstance(question, str)
                    and 0 < len(question.strip()) <= 512
                ):
                    key = (str(parsed.get("session_id", "")), parsed["box_id"], question)
                    if key != self._last_spoken_question:
                        self._last_spoken_question = key
                        self._pub_say.publish(String(data=question))
                else:
                    self._last_spoken_question = None
        except (KeyError, TypeError, ValueError):
            return

    def destroy_node(self) -> bool:
        self._context_stop.set()
        return super().destroy_node()

    def _on_transcript(self, msg: String) -> None:
        kind, ms = self._flow.handle(msg.data)
        if kind != "empty":
            self.get_logger().info(f"{kind} '{msg.data.strip()}' {ms:.0f} ms")

    def _on_text_command(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            request_id = data["request_id"]
            text = data["text"]
            if (
                not isinstance(request_id, str)
                or str(uuid.UUID(request_id)) != request_id
                or not isinstance(text, str)
                or not 1 <= len(text.strip()) <= 240
            ):
                return
        except (ValueError, KeyError, TypeError):
            return

        # 운영/웹 브리지 양쪽에서 같은 MQTT 요청이 전달돼도 한 번만 실행한다.
        with self._text_seen_lock:
            now = time.monotonic()
            self._text_seen = {
                key: stamp for key, stamp in self._text_seen.items() if now - stamp < 600.0
            }
            if request_id in self._text_seen:
                return
            self._text_seen[request_id] = now

        def reply(message: str) -> None:
            payload = {"request_id": request_id, "message": message}
            self._pub_text_reply.publish(String(data=json.dumps(payload, ensure_ascii=False)))

        kind, ms = self._flow.handle(text, report=reply)
        self.get_logger().info(f"text {kind} {ms:.0f} ms")

    def _publish(self, fields: dict) -> None:
        if self._command_transport == "web_api":
            if fields["type"] == "stop":
                ros_sent, web_accepted = attempt_stop(
                    lambda: self._publish_ros(fields),
                    lambda: http_client.post_command(fields, base=self._api_base),
                )
                if not ros_sent:
                    self.get_logger().error("ROS stop 발행 실패; 웹 경로는 별도로 시도함")
                if not web_accepted:
                    raise CommandDeliveryError("stop web API acceptance unconfirmed")
                return
            if not http_client.post_command(fields, base=self._api_base):
                raise CommandDeliveryError("POST /api/commands was not accepted")
            return
        self._publish_ros(fields)

    def _publish_ros(self, fields: dict) -> None:
        m = Intent()
        m.type, m.dong, m.zone = fields["type"], fields["dong"], fields["zone"]
        m.count, m.raw_text, m.box_id = fields["count"], fields["raw_text"], fields["box_id"]
        m.route = list(fields.get("route", []))  # palletize 경로 (Sprint 2), 그 밖은 []
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
