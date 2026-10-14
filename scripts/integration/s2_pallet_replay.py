"""S2-T08: PalletState 재생기 — ROS /voss/pallet/state → hmi_bridge → MQTT → SSE → React 3D 팔레트.
입력: pallet_fsm 이 만든 PalletState 열(기본 docker/web/frontend/test/fixtures/pallet_s1.json).
출력: 상태마다 `SENT <키> <epoch ms>` 와 끝의 `SENT_JSON=[...]`(s2_pallet_dom_observer.js 의 vossPalletReport 입력).
계약: docs/interfaces/voss_msgs.md PalletState, mqtt.md voss/pallet/state, web_api.md pallet_state.
전제: Sprint 2 voss_msgs(PalletState)가 빌드된 워크스페이스. 로봇·벨트·그리퍼 명령은 발행하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from voss_msgs.msg import PalletState

TOPIC = "/voss/pallet/state"
DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "docker/web/frontend/test/fixtures/pallet_s1.json"
)
DISCOVERY_WAIT_S = 1.5
# sort_manager 와 같은 QoS — hmi_bridge 가 transient_local 로 구독해서 volatile 발행은 연결되지 않는다
QOS = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)

# 실행 없음 (voss_msgs.md PalletState, 칸 배열 16 고정)
EMPTY = dict(
    run_id="",
    state="",
    route=[],
    dongs=[],
    load=[],
    overflow=[],
    excluded=[],
    overflow_warning=False,
    total=0,
    done=0,
    failed=0,
    box_id="",
    slot_state=["EMPTY"] * 16,
    slot_box_id=[""] * 16,
    slot_dong=[""] * 16,
)


def pallet_key(st: dict) -> str:
    """docker/web/frontend/src/pallet.ts palletKey 와 같은 형식."""
    letters = "".join(s[0] for s in st["slot_state"])
    return "|".join(
        [st["run_id"], st["state"], str(st["done"]), str(st["failed"]), st["box_id"], letters]
    )


def check_isolated(node: Node) -> None:
    """sort_manager 나 다른 PalletState 발행자가 있으면 진짜 배치도를 덮지 않게 멈춘다."""
    if any("sort_manager" in name for name in node.get_node_names()):
        raise RuntimeError("sort_manager 실행 중: 재생하지 않습니다.")
    for info in node.get_publishers_info_by_topic(TOPIC):
        if info.node_name != node.get_name():
            raise RuntimeError(f"기존 PalletState 발행자({info.node_name})가 있어 중단합니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--interval", type=float, default=1.0, help="상태 사이 초 (기본 1.0)")
    parser.add_argument(
        "--keep", action="store_true", help="끝 상태를 남긴다(기본은 빈 상태로 되돌림)"
    )
    args = parser.parse_args()
    states = json.loads(args.fixture.read_text(encoding="utf-8"))["states"]
    # "실행 없음" 상태는 화면이 이미 그 상태라 DOM 이 바뀌지 않는다 → 관측에서 미수신이 되므로 보내지 않는다
    states = [st for st in states if st["run_id"]]

    rclpy.init()
    node = Node("voss_s2_pallet_replay")
    try:
        time.sleep(DISCOVERY_WAIT_S)
        check_isolated(node)
        pub = node.create_publisher(PalletState, TOPIC, QOS)
        for _ in range(30):
            if pub.get_subscription_count() > 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("hmi_bridge 의 /voss/pallet/state 구독자가 없습니다.")

        sent = []
        print(f"START: {len(states)} states, interval={args.interval}s")
        for st in states:
            check_isolated(node)  # 도중에 manager 가 올라오면 바로 멈춘다
            pub.publish(PalletState(**st))
            key, ms = pallet_key(st), time.time_ns() // 1_000_000
            sent.append([key, ms])
            print(f"SENT {key} {ms}")
            time.sleep(args.interval)
        if not args.keep:
            # retained voss/pallet/state 에 재생 값이 남지 않게 빈 상태(실행 없음)로 되돌린다
            pub.publish(PalletState(**EMPTY))
            time.sleep(0.5)
        print("SENT_JSON=" + json.dumps(sent, ensure_ascii=False))
        print("DONE: 브라우저 콘솔에서 vossPalletReport(<위 SENT_JSON 의 배열>) 를 실행하세요.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
