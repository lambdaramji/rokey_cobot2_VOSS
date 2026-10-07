#!/usr/bin/env python3
"""U7 #34 — 서보 스트리밍 읽기 전용 점검 (로봇을 움직이지 않는다).

measurements-1006 #3 · pending #8 의 근거를 모은다. 두산 조회 서비스만 하나씩 차례로 부른다.

    # 공용 PC, 브링업이 떠 있는 상태 (robot_gateway 는 끈다)
    python3 servo_stream_inspect.py              # 보고서 출력 + JSON 저장
    python3 servo_stream_inspect.py --no-call    # 서비스 호출 없이 그래프(토픽·QoS)만

보는 것
1. 스트리밍 토픽(speedl → servol) 이름·타입, 컨트롤러 쪽 구독 QoS(reliable/best_effort, depth)
2. 필요한 서비스(move_line, move_stop, get_current_posx, RT 연결) 존재
3. robot_gateway 가 떠 있는지 (떠 있으면 2부 시험을 하지 않는다 — CLAUDE.md 규칙 3)
4. 로봇 시스템(real/virtual)·모드·상태, 현재 TCP posx
5. /dsr01/joint_states 주기, TF base_link → link_6 가능 여부 (시험 중 위치 관찰용)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

# ── 설정 (record_pose.py 와 같은 접두·저장 위치) ──────────────────────────
PREFIX = "/dsr01/dsr_controller2/"  # #55 김학민 10/07 실로봇 확인, record_pose.py PREFIX 와 같음
DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))
STREAM_TOPICS = [  # 확인 순서: ① speedl ② servol (DESIGN.md DEC-02)
    ("speedl_stream", "dsr_msgs2/msg/SpeedlStream"),
    ("servol_stream", "dsr_msgs2/msg/ServolStream"),
]
NEEDED_SERVICES = [
    "motion/move_line",  # ③ ASYNC 폴백
    "motion/move_stop",  # 정지 수단
    "aux_control/get_current_posx",  # 위치 조회
    "realtime/connect_rt_control",  # RT 경로 (비 RT 후보에는 불필요 예측)
]
JOINT_TOPIC = "/dsr01/joint_states"
TF_PARENT, TF_CHILD = "base_link", "link_6"  # 플랜지 링크 (m0609 xacro)
ROBOT_SYSTEM = {0: "real", 1: "virtual"}
ROBOT_MODE = {0: "MANUAL", 1: "AUTONOMOUS", 2: "RECOVERY", 3: "BACKDRIVE", 4: "MEASURE"}
ROBOT_STATE = {0: "INITIALIZING", 1: "STANDBY", 2: "MOVING", 3: "SAFE_OFF", 4: "TEACHING",
               5: "SAFE_STOP", 6: "EMERGENCY_STOP", 7: "HOMMING"}  # fmt: skip


def qos_text(info) -> str:
    """구독/퍼블리셔 QoS 를 'reliable/depth 10' 같은 짧은 글로 만든다."""
    from rclpy.qos import ReliabilityPolicy

    q = info.qos_profile  # 그래프에서 읽은 상대방 QoS
    rel = "reliable" if q.reliability == ReliabilityPolicy.RELIABLE else "best_effort"
    return f"{rel}/depth {q.depth}"


def graph_report(node) -> dict:
    """토픽·서비스·노드 목록을 읽기만 한다 (아무것도 보내지 않는다)."""
    topics = dict(node.get_topic_names_and_types())  # {이름: [타입...]}
    services = {n for n, _ in node.get_service_names_and_types()}  # 서비스 이름 집합
    nodes = node.get_node_names_and_namespaces()  # [(이름, 네임스페이스)]
    out = {"topics": {}, "services": {}, "gateway_nodes": []}
    for short, want in STREAM_TOPICS:
        name = PREFIX + short  # 예: /dsr01/dsr_controller2/speedl_stream
        subs = node.get_subscriptions_info_by_topic(name)  # 컨트롤러 쪽 구독 정보
        out["topics"][short] = {
            "name": name,
            "types": topics.get(name, []),  # 없으면 빈 목록
            "type_ok": want in topics.get(name, []),
            "subscribers": [f"{s.node_namespace}/{s.node_name} {qos_text(s)}" for s in subs],
        }
    for short in NEEDED_SERVICES:
        out["services"][short] = (PREFIX + short) in services
    # robot_gateway 가 두산을 함께 부르면 시험이 섞인다 → 이름으로 찾는다
    out["gateway_nodes"] = [
        f"{ns}/{n}" for n, ns in nodes if "robot_gateway" in n or ns.startswith("/voss")
    ]
    return out


def call_once(node, srv_type, name: str, timeout: float = 3.0, **kw):
    """두산 조회 서비스를 한 번 부른다. 앞 호출이 끝나야 다음을 부른다(직렬)."""
    import rclpy

    cli = node.create_client(srv_type, PREFIX + name)
    if not cli.wait_for_service(timeout_sec=timeout):  # 서비스가 없으면 None
        return None
    fut = cli.call_async(srv_type.Request(**kw))
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    node.destroy_client(cli)
    res = fut.result() if fut.done() else None
    return res if res is not None and getattr(res, "success", True) else None


def robot_report(node) -> dict:
    """로봇 시스템·모드·상태·현재 posx 를 차례로 조회한다 (움직이지 않는다)."""
    from dsr_msgs2.srv import GetCurrentPosx, GetRobotMode, GetRobotState, GetRobotSystem

    out = {}
    r = call_once(node, GetRobotSystem, "system/get_robot_system")
    out["robot_system"] = ROBOT_SYSTEM.get(r.robot_system, "?") if r else None
    r = call_once(node, GetRobotMode, "system/get_robot_mode")
    out["robot_mode"] = ROBOT_MODE.get(r.robot_mode, "?") if r else None
    r = call_once(node, GetRobotState, "system/get_robot_state")
    out["robot_state"] = ROBOT_STATE.get(r.robot_state, "?") if r else None
    r = call_once(node, GetCurrentPosx, "aux_control/get_current_posx", ref=0)  # 0 = DR_BASE
    out["posx_tcp"] = [round(v, 2) for v in r.task_pos_info[0].data[:6]] if r else None
    return out


def joint_rate(node, sec: float = 2.0) -> dict:
    """joint_states 를 sec 초 듣고 주기(Hz)와 stamp 가 채워졌는지 본다."""
    import rclpy
    from sensor_msgs.msg import JointState

    got: list[tuple[float, float]] = []  # (수신 시각, 메시지 stamp 초)
    sub = node.create_subscription(
        JointState,
        JOINT_TOPIC,
        lambda m: got.append(
            (time.monotonic(), m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
        ),
        10,
    )
    end = time.monotonic() + sec
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.05)
    node.destroy_subscription(sub)
    if len(got) < 2:
        return {"topic": JOINT_TOPIC, "hz": 0.0, "stamp_nonzero": None}
    hz = (len(got) - 1) / (got[-1][0] - got[0][0])  # 받은 간격으로 계산
    return {"topic": JOINT_TOPIC, "hz": round(hz, 1), "stamp_nonzero": got[-1][1] > 0}


def tf_check(node, sec: float = 2.0) -> dict:
    """TF base_link → link_6 를 받을 수 있는지 본다 (시험 중 위치 관찰에 쓴다)."""
    import rclpy
    from rclpy.time import Time
    from tf2_ros import Buffer, TransformListener

    buf = Buffer()
    _listener = TransformListener(buf, node)  # 변수로 잡아 둬야 구독이 유지된다
    end = time.monotonic() + sec
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.05)
        if buf.can_transform(TF_PARENT, TF_CHILD, Time()):
            t = buf.lookup_transform(TF_PARENT, TF_CHILD, Time()).transform.translation
            return {
                "ok": True,
                "xyz_mm": [round(t.x * 1000, 1), round(t.y * 1000, 1), round(t.z * 1000, 1)],
            }
    return {"ok": False, "xyz_mm": None}


def print_report(rep: dict) -> None:
    """사람이 읽는 판정 요약."""
    g = rep["graph"]
    print("\n== 1. 스트리밍 토픽 (확인 순서 speedl → servol) ==")
    for t in g["topics"].values():
        mark = "OK" if t["type_ok"] else "없음/타입 다름"
        print(f"  {t['name']}: {mark} {t['types']}")
        for s in t["subscribers"] or ["(구독자 없음 — dsr_controller2 가 active 인지 확인)"]:
            print(f"    구독: {s}")
    print(
        "  ※ 구독이 reliable 이면 best_effort 퍼블리셔와 연결되지 않는다 (gateway 는 reliable 로)"
    )
    print("\n== 2. 서비스 ==")
    for short, ok in g["services"].items():
        print(f"  {PREFIX}{short}: {'OK' if ok else '없음'}")
    print("\n== 3. robot_gateway ==")
    if g["gateway_nodes"]:
        print(f"  ⚠ 떠 있음: {g['gateway_nodes']} → 2부 시험 전에 끈다 (두산 호출이 섞임)")
    else:
        print("  없음 (시험 가능)")
    r = rep.get("robot")
    if r is not None:
        print("\n== 4. 로봇 ==")
        print(f"  system={r['robot_system']} mode={r['robot_mode']} state={r['robot_state']}")
        print(f"  TCP posx (base, mm·deg) = {r['posx_tcp']}")
        if r["robot_system"] == "virtual":
            print("  ⚠ virtual(에뮬레이터) 값이다. 실측이 아니다")
    j, tf = rep["joint"], rep["tf"]
    print("\n== 5. 관찰 수단 ==")
    print(f"  {j['topic']}: {j['hz']} Hz, stamp 채움={j['stamp_nonzero']}")
    print(
        f"  TF {TF_PARENT}→{TF_CHILD}: {'OK ' + str(tf['xyz_mm']) + ' mm' if tf['ok'] else '없음'}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-call", action="store_true", help="두산 서비스 호출 없이 그래프만 본다")
    args = ap.parse_args(argv)

    import rclpy

    rclpy.init()
    node = rclpy.create_node("voss_servo_stream_inspect")
    try:
        time.sleep(1.0)  # DDS 발견(discovery) 이 끝날 시간을 준다
        rep = {
            "stamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "target": os.environ.get("VOSS_DSR_TARGET", "unknown"),  # 래퍼가 emulator 로 넣는다
            "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
            "graph": graph_report(node),
            "robot": None if args.no_call else robot_report(node),
            "joint": joint_rate(node),
            "tf": tf_check(node),
        }
    finally:
        node.destroy_node()
        rclpy.shutdown()

    print_report(rep)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"servo_stream_inspect_{rep['stamp'].replace(':', '')}.json"
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
