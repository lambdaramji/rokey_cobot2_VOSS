"""sort_logger — /voss/sort/result 1건 → PostgreSQL sort_log 1행 (topics.md, voss_msgs.md).
Sprint 2(S2-T07, BRD v1.5): /voss/pallet/result 1건 → pallet_log 1행(싣지 않은 박스 포함), 서비스 /voss/log/list_placements.

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
from voss_hmi.log_logic import (
    Spool,
    list_placements_reply,
    pallet_result_to_row,
    result_to_row,
    worst_status,
)
from voss_hmi.result_store import ResultStore
from voss_msgs.msg import PalletResult, Placement, SortResult
from voss_msgs.srv import ListPlacements

QOS_RESULT = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)  # topics.md QoS 표
QOS_STATUS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)

DEFAULT_SPOOL_PATH = "/var/lib/voss/spool/sort_log.jsonl"  # SRD: durable 볼륨
DEFAULT_PALLET_SPOOL_PATH = "/var/lib/voss/spool/pallet_log.jsonl"
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
        "slot": msg.slot,
    }


def pallet_result_to_dict(msg: PalletResult) -> dict:
    """ROS 메시지 → log_logic.pallet_result_to_row 가 받는 dict."""
    fields = ("run_id", "session_id", "box_id", "dong", "route_index", "zone", "slot", "pallet_slot",
              "pallet_col", "pallet_lane", "pallet_layer", "outcome", "reason", "attempts")  # fmt: skip
    out = {name: getattr(msg, name) for name in fields}
    out["stamp"] = (msg.stamp.sec, msg.stamp.nanosec)
    return out


class _PalletTable:
    """ResultStore 가 쓰는 writer 모양(insert·check)으로 pallet_log 를 잇는다."""

    def __init__(self, writer: DbWriter) -> None:
        self._writer = writer

    def insert(self, row: dict) -> bool:
        return self._writer.insert_pallet(row)

    def check(self) -> None:
        self._writer.check()


class SortLoggerNode(Node):
    def __init__(self) -> None:
        super().__init__("sort_logger")
        self.declare_parameter("db_host", "127.0.0.1")
        self.declare_parameter("db_port", 5432)
        self.declare_parameter("db_name", "voss")
        self.declare_parameter("db_user", "voss_logger")
        self.declare_parameter("db_timeout_s", 2.0)
        self.declare_parameter("spool_path", DEFAULT_SPOOL_PATH)
        self.declare_parameter("pallet_spool_path", DEFAULT_PALLET_SPOOL_PATH)

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
        pallet_spool_path = self.get_parameter("pallet_spool_path").value
        self._pallet_spool = Spool(pallet_spool_path)
        self._pallet_store = ResultStore(
            writer=_PalletTable(self._writer),
            spool=self._pallet_spool,
            rejected=Spool(pallet_spool_path + ".rejected"),
            log_info=log.info,
            log_warn=log.warn,
            log_error=log.error,
            log_prefix="pallet_log ",
        )
        self._sort_spool = self._store._spool
        self._last_status = ""
        self._schema_warned = ""

        self._pub_status = self.create_publisher(String, "/voss/log/status", QOS_STATUS)
        self.create_subscription(SortResult, "/voss/sort/result", self._on_result, QOS_RESULT)
        self.create_subscription(PalletResult, "/voss/pallet/result", self._on_pallet, QOS_RESULT)
        self.create_service(ListPlacements, "/voss/log/list_placements", self._on_list_placements)
        self.create_timer(STATUS_PERIOD_S, self._on_tick)

        log.info(f"sort_logger started — spool={spool_path}, pallet_spool={pallet_spool_path}")
        self._on_tick()  # 시작하자마자 DB 연결을 시도하고 첫 상태를 낸다

    def _on_result(self, msg: SortResult) -> None:
        row = result_to_row(sort_result_to_dict(msg))
        self._store.save(row)
        self._publish_status()  # DB_ERROR 로 바뀌었으면 1초를 기다리지 않고 바로 알린다

    def _on_pallet(self, msg: PalletResult) -> None:
        self._pallet_store.save(pallet_result_to_row(pallet_result_to_dict(msg)))
        self._publish_status()

    def _on_list_placements(
        self, req: ListPlacements.Request, res: ListPlacements.Response
    ) -> ListPlacements.Response:
        """팔레타이징 대상 조회 (TR-PAL-03). 스풀에 DB 미반영 결과가 있으면 칸 기록이 빠진 채 계획하지 않게 거부한다."""
        pending = self._sort_spool.count() + self._pallet_spool.count()
        res.ok, res.message, items = list_placements_reply(
            req.session_id, pending, self._writer.list_placements
        )
        for it in items:
            p = Placement(box_id=it["box_id"], dong=it["dong"], zone=it["zone"], slot=it["slot"],
                          palletized=it["palletized"])  # fmt: skip
            p.stamp.sec, p.stamp.nanosec = it["stamp"]
            res.placements.append(p)
        log = self.get_logger()
        if res.ok:
            log.info(
                f"ListPlacements {req.session_id}: {len(items)}건 (이미 팔레트 {sum(i['palletized'] for i in items)})"
            )
        else:
            log.warn(f"ListPlacements {req.session_id!r} 거부: {res.message}")
        return res

    def _on_tick(self) -> None:
        self._store.tick()
        self._pallet_store.tick()
        warn = self._writer.schema_warning
        if warn != self._schema_warned:
            if warn:
                self.get_logger().warn(
                    warn
                )  # 마이그레이션 전 DB — slot 없이 쓰고 팔레타이징 조회는 실패한다
            self._schema_warned = warn
        self._publish_status(always=True)

    def _publish_status(self, always: bool = False) -> None:
        status = worst_status(self._store.status(), self._pallet_store.status())
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
