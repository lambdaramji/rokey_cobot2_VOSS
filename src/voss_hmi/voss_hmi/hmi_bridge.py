"""hmi_bridge: ROS 상태를 MQTT로 내보내고 웹 명령을 ROS 서비스로 전달한다.

입력: /voss/sort/state·result·zone_map, /voss/robot/state, /voss/log/status,
      MQTT voss/command.
출력: MQTT voss/state·result·zone_map·robot·log_status·command/ack,
      /voss/sort/command 호출.
계약: docs/interfaces/mqtt.md, docs/interfaces/voss_msgs.md.
"""

from __future__ import annotations

import json
import os
import queue
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_hmi.mqtt_logic import CommandError, parse_command_json
from voss_msgs.msg import RobotState, SortResult, SortState, ZoneMap
from voss_msgs.srv import Command


MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = "bridge"
MQTT_PASSWORD_ENV = "VOSS_MQTT_BRIDGE_PASSWORD"
MQTT_COMMAND_TOPIC = "voss/command"
MQTT_ACK_TOPIC = "voss/command/ack"
COMMAND_CACHE_TTL_S = 600.0
COMMAND_QUEUE_MAX = 100
COMMAND_DRAIN_PERIOD_S = 0.05
KST = timezone(timedelta(hours=9))

QOS_RELIABLE_10 = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)
QOS_TRANSIENT_1 = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)
QOS_ROBOT = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)


class HmiBridgeNode(Node):
    """ROS와 MQTT 사이 계약 변환만 담당하는 브리지 노드다."""

    def __init__(self) -> None:
        super().__init__("hmi_bridge")

        self._command_queue: queue.Queue[str] = queue.Queue(maxsize=COMMAND_QUEUE_MAX)
        self._command_cache: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()

        self._command_client = self.create_client(Command, "/voss/sort/command")

        self.create_subscription(
            SortState,
            "/voss/sort/state",
            self._on_state,
            QOS_RELIABLE_10,
        )
        self.create_subscription(
            SortResult,
            "/voss/sort/result",
            self._on_result,
            QOS_RELIABLE_10,
        )
        self.create_subscription(
            ZoneMap,
            "/voss/sort/zone_map",
            self._on_zone_map,
            QOS_TRANSIENT_1,
        )
        self.create_subscription(
            RobotState,
            "/voss/robot/state",
            self._on_robot,
            QOS_ROBOT,
        )
        self.create_subscription(
            String,
            "/voss/log/status",
            self._on_log_status,
            QOS_RELIABLE_10,
        )

        self._mqtt = self._create_mqtt_client()
        self._mqtt.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self._mqtt.loop_start()

        self.create_timer(COMMAND_DRAIN_PERIOD_S, self._drain_commands)
        self.get_logger().info("hmi_bridge started")

    def destroy_node(self) -> bool:
        """MQTT 루프를 먼저 끝낸 뒤 ROS 노드를 정리한다."""

        try:
            self._mqtt.disconnect()
            self._mqtt.loop_stop()
        finally:
            destroy_result = super().destroy_node()
        return destroy_result

    def _create_mqtt_client(self) -> mqtt.Client:
        """bridge 전용 계정으로 Mosquitto 클라이언트를 만든다."""

        password = os.environ.get(MQTT_PASSWORD_ENV)
        if not password:
            raise RuntimeError(f"{MQTT_PASSWORD_ENV} is required")

        client = mqtt.Client(client_id="voss-hmi-bridge", protocol=mqtt.MQTTv311)
        client.username_pw_set(MQTT_USERNAME, password)
        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        return client

    def _on_mqtt_connect(self, client, userdata, flags, rc) -> None:
        """브로커 연결 후 command 토픽 하나만 구독한다."""

        del userdata, flags
        if rc != 0:
            self.get_logger().error(f"MQTT connect failed rc={rc}")
            return

        client.subscribe(MQTT_COMMAND_TOPIC, qos=1)
        self.get_logger().info("MQTT connected")

    def _on_mqtt_disconnect(self, client, userdata, rc) -> None:
        """브로커 연결 종료를 로그로 남긴다."""

        del client, userdata
        self.get_logger().warning(f"MQTT disconnected rc={rc}")

    def _on_mqtt_message(self, client, userdata, message) -> None:
        """MQTT 스레드에서는 payload를 큐에 넣기만 한다."""

        del client, userdata
        if message.topic != MQTT_COMMAND_TOPIC:
            return

        try:
            payload = message.payload.decode("utf-8")
        except UnicodeDecodeError:
            self.get_logger().warning("MQTT command is not UTF-8")
            return

        try:
            self._command_queue.put_nowait(payload)
        except queue.Full:
            self.get_logger().error("MQTT command queue full")

    def _on_state(self, message: SortState) -> None:
        """SortState를 voss/state JSON으로 발행한다."""

        payload = {
            "state": message.state,
            "box_id": message.box_id,
            "pending_question": message.pending_question,
            "track_id": int(message.track_id),
            "ready": bool(message.ready),
            "not_ready": list(message.not_ready),
            "session_id": message.session_id,
        }
        self._publish_json("voss/state", payload, qos=1, retain=False)

    def _on_result(self, message: SortResult) -> None:
        """SortResult를 필드 이름 그대로 voss/result로 발행한다."""

        payload = {
            "box_id": message.box_id,
            "code": message.code,
            "dong": message.dong,
            "confidence": float(message.confidence),
            "decided_by": message.decided_by,
            "zone": message.zone,
            "outcome": message.outcome,
            "stamp": _ros_time_to_iso(message.stamp),
            "session_id": message.session_id,
            "track_id": int(message.track_id),
            "started_at": _ros_time_to_iso(message.started_at),
            "raw_text": message.raw_text,
            "dong_alt": message.dong_alt,
            "rule_version": message.rule_version,
            "reason": message.reason,
            "attempts": int(message.attempts),
        }
        self._publish_json("voss/result", payload, qos=1, retain=False)

    def _on_zone_map(self, message: ZoneMap) -> None:
        """ZoneMap을 retained voss/zone_map으로 발행한다."""

        entries = []
        for entry in message.entries:
            entries.append(
                {
                    "dong": entry.dong,
                    "zone": entry.zone,
                    "code": entry.code,
                    "aliases": list(entry.aliases),
                }
            )

        payload = {"version": message.version, "entries": entries}
        self._publish_json("voss/zone_map", payload, qos=1, retain=True)

    def _on_robot(self, message: RobotState) -> None:
        """RobotState를 voss/robot JSON으로 발행한다."""

        payload = {
            "connected": bool(message.connected),
            "state": message.state,
            "action": message.action,
            "gripper_width_mm": float(message.gripper_width_mm),
            "error_code": message.error_code,
            "detail": message.detail,
            "stamp": _ros_time_to_iso(message.header.stamp),
        }
        self._publish_json("voss/robot", payload, qos=0, retain=False)

    def _on_log_status(self, message: String) -> None:
        """logger 상태를 retained voss/log_status로 발행한다."""

        payload = {"status": message.data, "stamp": _now_iso()}
        self._publish_json("voss/log_status", payload, qos=1, retain=True)

    def _drain_commands(self) -> None:
        """MQTT 큐의 명령을 ROS executor 스레드에서 처리한다."""

        self._prune_command_cache()

        for _ in range(COMMAND_QUEUE_MAX):
            try:
                payload = self._command_queue.get_nowait()
            except queue.Empty:
                return
            self._process_command(payload)

    def _process_command(self, payload: str) -> None:
        """명령을 검증하고 중복 억제 후 sort_manager 서비스로 전달한다."""

        now = datetime.now(KST)
        try:
            command = parse_command_json(payload, now)
        except CommandError as error:
            command_id = _best_effort_command_id(payload)
            self._publish_ack(command_id, False, error.code)
            return

        cached = self._command_cache.get(command.command_id)
        if cached is not None:
            _, ack = cached
            if ack is not None:
                self._publish_json(MQTT_ACK_TOPIC, ack, qos=1, retain=False)
            return

        self._command_cache[command.command_id] = (time.monotonic(), None)

        if not self._command_client.service_is_ready():
            self._finish_command(command.command_id, False, "SERVICE_UNAVAILABLE")
            return

        request = Command.Request()
        request.command = command.command
        request.arg = command.arg

        future = self._command_client.call_async(request)
        future.add_done_callback(
            lambda completed, command_id=command.command_id: self._on_command_done(
                command_id, completed
            )
        )

    def _on_command_done(self, command_id: str, future) -> None:
        """sort_manager의 접수 응답을 MQTT ack로 변환한다."""

        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().error(f"sort command failed: {exc}")
            self._finish_command(command_id, False, "SERVICE_UNAVAILABLE")
            return

        self._finish_command(command_id, bool(response.ok), response.message)

    def _finish_command(self, command_id: str, ok: bool, message: str) -> None:
        """ack를 캐시에 저장하고 한 번 발행한다."""

        ack = {
            "command_id": command_id,
            "ok": ok,
            "message": message,
            "acked_at": _now_iso(),
        }
        self._command_cache[command_id] = (time.monotonic(), ack)
        self._publish_json(MQTT_ACK_TOPIC, ack, qos=1, retain=False)

    def _publish_ack(self, command_id: str, ok: bool, message: str) -> None:
        """bridge 자체 검증 실패 ack를 발행한다."""

        ack = {
            "command_id": command_id,
            "ok": ok,
            "message": message,
            "acked_at": _now_iso(),
        }
        self._publish_json(MQTT_ACK_TOPIC, ack, qos=1, retain=False)

    def _publish_json(self, topic: str, payload: dict, qos: int, retain: bool) -> None:
        """UTF-8 JSON 한 건을 MQTT로 발행한다."""

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        info = self._mqtt.publish(topic, body, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().warning(f"MQTT publish failed topic={topic} rc={info.rc}")

    def _prune_command_cache(self) -> None:
        """10분이 지난 command_id 기록을 제거한다."""

        cutoff = time.monotonic() - COMMAND_CACHE_TTL_S
        while self._command_cache:
            command_id, (seen_at, _) = next(iter(self._command_cache.items()))
            if seen_at >= cutoff:
                return
            self._command_cache.pop(command_id)


def _ros_time_to_iso(stamp) -> str | None:
    """ROS Time을 +09:00 ISO 문자열로 바꾸고 0 시각은 null로 둔다."""

    sec = int(stamp.sec)
    nanosec = int(stamp.nanosec)
    if sec == 0 and nanosec == 0:
        return None

    timestamp = sec + nanosec / 1_000_000_000
    return datetime.fromtimestamp(timestamp, tz=KST).isoformat()


def _now_iso() -> str:
    """공용 PC 현재 시각을 +09:00 ISO 문자열로 만든다."""

    return datetime.now(KST).isoformat()


def _best_effort_command_id(payload: str) -> str:
    """파싱 실패 ack도 가능한 경우 원래 command_id와 연결한다."""

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""

    if not isinstance(data, dict):
        return ""

    command_id = data.get("command_id")
    if isinstance(command_id, str):
        return command_id
    return ""


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
