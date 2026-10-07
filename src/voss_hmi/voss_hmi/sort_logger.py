"""sort_logger — /voss/sort/result 1건 → PostgreSQL sort_log 1행 (topics.md, voss_msgs.md).

이 노드는 ROS 입출력만 맡는다.
- 저장 흐름(바로 DB → 실패하면 스풀 → 재전송)은 result_store.py
- 메시지 → 행 변환·상태 판정·스풀 파일은 log_logic.py
- DB 접근은 db_writer.py

읽는 순서: main() → SortLoggerNode.__init__ → _on_result(결과 수신) → _on_tick(1초 주기)
"""

from __future__ import annotations

import os

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_hmi.db_writer import DbWriter
from voss_hmi.log_logic import Spool, result_to_row
from voss_hmi.result_store import ResultStore
from voss_msgs.msg import SortResult

QOS_RESULT = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)  # topics.md QoS 표
QOS_STATUS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)

DEFAULT_SPOOL_PATH = "/var/lib/voss/spool/sort_log.jsonl"  # SRD: durable 볼륨
STATUS_PERIOD_S = 1.0  # topics.md: /voss/log/status 1 Hz


def sort_result_to_dict(msg: SortResult) -> dict:
    """ROS 메시지 → log_logic.result_to_row 가 받는 dict (시각은 (sec, nanosec))."""
    return {
        "box_id": msg.box_id,
        "session_id": msg.session_id,
        "track_id": msg.track_id,
        "code": msg.code,
        "dong": msg.dong,
        "confidence": float(msg.confidence),
        "decided_by": msg.decided_by,
        "zone": msg.zone,
        "outcome": msg.outcome,
        "reason": msg.reason,
        "raw_text": msg.raw_text,
        "dong_alt": msg.dong_alt,
        "rule_version": msg.rule_version,
        "attempts": msg.attempts,
        "stamp": (msg.stamp.sec, msg.stamp.nanosec),
        "started_at": (msg.started_at.sec, msg.started_at.nanosec),
    }


class SortLoggerNode(Node):
    def __init__(self) -> None:
        super().__init__("sort_logger")
        self.declare_parameter("db_host", "127.0.0.1")
        self.declare_parameter("db_port", 5432)
        self.declare_parameter("db_name", "voss")
        self.declare_parameter("db_user", "voss_logger")
        self.declare_parameter("db_timeout_s", 2.0)
        self.declare_parameter("spool_path", DEFAULT_SPOOL_PATH)

        # 비밀번호는 파라미터·YAML 에 두지 않고 환경 변수로만 받는다(docker/db/.env 와 같은 값)
        password = os.getenv("VOSS_DB_LOGGER_PASSWORD", "")
        if not password:
            self.get_logger().warn(
                "VOSS_DB_LOGGER_PASSWORD 가 비어 있다 — DB 연결이 실패할 수 있다"
            )

        self._writer = DbWriter(
            host=self.get_parameter("db_host").value,
            port=int(self.get_parameter("db_port").value),
            dbname=self.get_parameter("db_name").value,
            user=self.get_parameter("db_user").value,
            password=password,
            timeout_s=float(self.get_parameter("db_timeout_s").value),
        )
        spool_path = self.get_parameter("spool_path").value
        log = self.get_logger()
        self._store = ResultStore(
            writer=self._writer,
            spool=Spool(spool_path),
            rejected=Spool(spool_path + ".rejected"),  # DB 가 거부한 행 (사람이 확인)
            log_info=log.info,
            log_warn=log.warn,
            log_error=log.error,
        )
        self._last_status = ""

        self._pub_status = self.create_publisher(String, "/voss/log/status", QOS_STATUS)
        self.create_subscription(SortResult, "/voss/sort/result", self._on_result, QOS_RESULT)
        self.create_timer(STATUS_PERIOD_S, self._on_tick)

        log.info(f"sort_logger started — spool={spool_path}")
        self._on_tick()  # 시작하자마자 DB 연결을 시도하고 첫 상태를 낸다

    def _on_result(self, msg: SortResult) -> None:
        row = result_to_row(sort_result_to_dict(msg))
        self._store.save(row)
        self._publish_status()  # DB_ERROR 로 바뀌었으면 1초를 기다리지 않고 바로 알린다

    def _on_tick(self) -> None:
        self._store.tick()
        self._publish_status(always=True)

    def _publish_status(self, always: bool = False) -> None:
        status = self._store.status()
        changed = status != self._last_status
        if changed:
            self.get_logger().info(f"/voss/log/status: {self._last_status or '-'} → {status}")
            self._last_status = status
        if changed or always:
            self._pub_status.publish(String(data=status))

    def destroy_node(self) -> None:
        self._writer.close()
        super().destroy_node()


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
