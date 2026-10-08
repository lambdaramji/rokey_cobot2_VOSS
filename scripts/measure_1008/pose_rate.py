#!/usr/bin/env python3
"""/voss/robot/pose 의 '값이 바뀌는 간격' 측정 (로봇을 움직이지 않는다).

메시지는 50 Hz 로 와도 값이 0.1 s 마다만 바뀌는 회차가 있었다(10/08 F-04). 로봇이 움직이는 동안
(추종·move_to_zone 중) 띄워 두면, 값이 바뀐 간격의 중앙값·최대를 낸다.
    python3 pose_rate.py            # 20 s
    python3 pose_rate.py --secs 60
"""

import argparse
import statistics
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import JointState


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=20.0)
    a = ap.parse_args()
    rclpy.init()
    n = rclpy.create_node("pose_rate")
    msgs, changes, last = [0], [], [None]

    def cb(m: PoseStamped) -> None:
        msgs[0] += 1
        p = m.pose.position
        v = (round(p.x, 6), round(p.y, 6), round(p.z, 6))
        if v != last[0]:
            changes.append(time.monotonic())
            last[0] = v

    n.create_subscription(
        PoseStamped,
        "/voss/robot/pose",
        cb,
        QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
    )
    # 비교: 두산 joint_states (컨트롤러가 직접 발행) 값 변화 간격
    jmsgs, jchanges, jlast = [0], [], [None]

    def jcb(m: JointState) -> None:
        jmsgs[0] += 1
        v = tuple(round(x, 6) for x in m.position)
        if v != jlast[0]:
            jchanges.append(time.monotonic())
            jlast[0] = v

    n.create_subscription(JointState, "/dsr01/joint_states", jcb, qos_profile_sensor_data)
    t0 = time.monotonic()
    end = t0 + a.secs
    print(
        f"측정 중… 최대 {a.secs:.0f} s (지금 로봇을 움직이세요. Ctrl+C 로 일찍 끝내도 결과를 냅니다)",
        flush=True,
    )
    try:
        while time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    a.secs = max(time.monotonic() - t0, 0.1)  # 실제 잰 시간으로 Hz 계산
    gaps = [(b - c) * 1000 for c, b in zip(changes, changes[1:], strict=False) if b - c < 0.5]
    print(f"메시지 {msgs[0] / a.secs:.1f} Hz, 값 변화 {len(changes)}번")
    if gaps:
        print(
            f"움직이는 동안 값이 바뀐 간격: 중앙값 {statistics.median(gaps):.0f} ms, 최대 {max(gaps):.0f} ms "
            "(20 ms 면 정상, 100 ms 면 0.1 s 갱신 문제)"
        )
    else:
        print("값이 거의 안 바뀜 — 로봇이 움직이는 동안 다시 재기")
    jg = [(b - c) * 1000 for c, b in zip(jchanges, jchanges[1:], strict=False) if b - c < 0.5]
    print(
        f"[비교] /dsr01/joint_states {jmsgs[0] / a.secs:.1f} Hz, 값 변화 {len(jchanges)}번"
        + (f", 간격 중앙값 {statistics.median(jg):.0f} ms·최대 {max(jg):.0f} ms" if jg else "")
    )
    n.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
