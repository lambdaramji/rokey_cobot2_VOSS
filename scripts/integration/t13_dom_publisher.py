"""T13: ROS SortState → MQTT → SSE → React DOM 지연 시험용 발행기.
입력: 비구동 시험용 IDLE 상태를 12회 발행한다.
출력: PC 시계 오프셋/불확실도와 시험 메시지 ID.
계약: docs/interfaces/mqtt.md, web_api.md (#54 MC-031).
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from urllib.error import URLError

import rclpy
from rclpy.node import Node
from voss_msgs.msg import SortState

API_URL = "http://127.0.0.1:8080/api/sessions/current"
STATE_TOPIC = "/voss/sort/state"
MARKER = "T13DOM"
SAMPLE_COUNT = 12
SAMPLE_INTERVAL_S = 1.0
DISCOVERY_WAIT_S = 1.5
MAX_CLOCK_UNCERTAINTY_MS = 200.0
MAX_ABS_CLOCK_OFFSET_MS = 200.0


def estimate_server_clock() -> tuple[float, float]:
    """Web PC 응답 시계를 Nodes PC와 비교한다. 실패하면 시험을 중단한다."""
    clock_samples = []
    for _ in range(5):
        started_ms = time.time_ns() / 1_000_000
        with urllib.request.urlopen(API_URL, timeout=5) as response:
            body = json.load(response)
        finished_ms = time.time_ns() / 1_000_000
        server_time = datetime.fromisoformat(body["as_of"])
        server_ms = server_time.timestamp() * 1000
        midpoint_ms = (started_ms + finished_ms) / 2
        clock_samples.append(
            (finished_ms - started_ms, server_ms - midpoint_ms)
        )
    best_rtt_ms, offset_ms = min(clock_samples)
    return offset_ms, best_rtt_ms / 2


def check_ros_is_isolated(node: Node) -> None:
    """sort_manager 또는 기존 상태 발행자가 있다면 오염 방지를 위해 중단한다."""
    names = node.get_node_names()
    if any("sort_manager" in name for name in names):
        raise RuntimeError("sort_manager 실행 중: 상태 메시지를 발행하지 않습니다.")
    for publisher_info in node.get_publishers_info_by_topic(STATE_TOPIC):
        if publisher_info.node_name != node.get_name():
            raise RuntimeError("기존 SortState 발행자가 있어 중단합니다.")


def make_message(sequence: int, offset_ms: float, uncertainty_ms: float) -> SortState:
    """DOM에서 읽을 시험 시각을 IDLE 상태 pending_question에 넣는다."""
    message = SortState()
    message.state = "IDLE"
    message.box_id = ""
    message.pending_question = (
        f"{MARKER}|{sequence}|{time.time_ns() // 1_000_000}"
        f"|{offset_ms:.1f}|{uncertainty_ms:.1f}"
    )
    message.track_id = -1
    message.ready = False
    message.not_ready = ["ROBOT"]
    message.session_id = ""
    return message


def main() -> None:
    """Web PC 시계와 ROS 구독자를 확인한 후 12회 상태를 송신한다."""
    try:
        offset_ms, uncertainty_ms = estimate_server_clock()
    except (URLError, OSError, ValueError, KeyError) as error:
        raise SystemExit(f"FAIL: Web 시계 조회 실패: {type(error).__name__}") from error

    print(f"CLOCK server_minus_node={offset_ms:.1f}ms uncertainty=±{uncertainty_ms:.1f}ms")
    if uncertainty_ms > MAX_CLOCK_UNCERTAINTY_MS:
        raise SystemExit("FAIL: RTT 불확실도가 커서 DOM 지연을 판정할 수 없습니다.")
    if abs(offset_ms) > MAX_ABS_CLOCK_OFFSET_MS:
        raise SystemExit("FAIL: PC 시계 차이가 200ms보다 큽니다. 시계 동기화가 필요합니다.")

    rclpy.init()
    node = Node("voss_t13_dom_publisher")
    try:
        time.sleep(DISCOVERY_WAIT_S)
        check_ros_is_isolated(node)
        publisher = node.create_publisher(SortState, STATE_TOPIC, 10)
        for _ in range(20):
            if publisher.get_subscription_count() > 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("hmi_bridge 상태 구독자가 없습니다.")

        print(f"START: {SAMPLE_COUNT} samples, interval={SAMPLE_INTERVAL_S}s")
        for sequence in range(1, SAMPLE_COUNT + 1):
            # 도중에 manager가 올라오면 즉시 발행을 그만둔다.
            check_ros_is_isolated(node)
            message = make_message(sequence, offset_ms, uncertainty_ms)
            publisher.publish(message)
            print(f"SENT {sequence}/{SAMPLE_COUNT}")
            time.sleep(SAMPLE_INTERVAL_S)

        # 화면에 시험 질문 문구가 남지 않도록 빈 값으로 초기화한다.
        clear_message = make_message(0, offset_ms, uncertainty_ms)
        clear_message.pending_question = ""
        publisher.publish(clear_message)
        time.sleep(0.5)
        print("DONE: DOM 관측 창의 12회 결과를 확인하세요.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
