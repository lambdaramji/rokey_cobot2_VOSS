#!/usr/bin/env python3
"""벨트 속도 측정 (읽기 전용) — /voss/vision/box 의 position_base 를 트랙별로 직선 맞춤해 cm/s 를 낸다.

아무것도 발행하지 않는다. 로봇이 서 있든 움직이든 position_base 는 베이스 좌표라 그대로 쓴다.
  python3 belt_speed.py --secs 60                          # 실시간: 박스를 벨트에 흘린다
  python3 belt_speed.py --bag ~/voss_data/1010/track_rehearsal_02   # 녹화에서
참고(measurements-1006 #1·1008 #10): h250 ≈ 4.77~4.89 cm/s, h500 ≈ 2.38~2.47 cm/s, voss_config belt.speed_cmps 4.8
"""

from __future__ import annotations

import argparse
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

MIN_POINTS = 30  # 1 s 이상 (30 Hz)
MIN_TRAVEL_MM = 30.0  # 이만큼 움직인 트랙만 (정지 박스 제외)


def report(tracks: dict[int, list[tuple[float, float, float]]]) -> None:
    found = False
    for tid, pts in sorted(tracks.items()):
        if len(pts) < MIN_POINTS:
            continue
        a = np.array(pts)  # t, x, y (s, mm, mm)
        t = a[:, 0] - a[0, 0]
        travel = math.hypot(a[-1, 1] - a[0, 1], a[-1, 2] - a[0, 2])
        if travel < MIN_TRAVEL_MM:
            print(f"트랙 {tid}: {len(pts)}점, 이동 {travel:.1f} mm — 거의 정지(벨트 꺼짐?)")
            continue
        vx, bx = np.polyfit(t, a[:, 1], 1)
        vy, by = np.polyfit(t, a[:, 2], 1)
        sp = math.hypot(vx, vy)
        ang = math.degrees(math.atan2(vy, vx))
        res = np.hypot(a[:, 1] - (vx * t + bx), a[:, 2] - (vy * t + by))
        guess = "h250" if 4.3 <= sp / 10 <= 5.3 else "h500" if 2.1 <= sp / 10 <= 2.8 else "?"
        print(f"트랙 {tid}: {len(pts)}점 {t[-1]:.1f} s, x {a[0, 1]:.0f}→{a[-1, 1]:.0f} mm | 속도 {sp / 10:.2f} cm/s "
              f"(방향 {ang:+.2f}°, 직선 잔차 최대 {res.max():.1f} mm) → {guess}")  # fmt: skip
        found = True
    if not found:
        print("움직이는 트랙이 없다 — 박스를 벨트에 흘리면서 다시")


def from_bag(path: Path) -> dict:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from voss_msgs.msg import BoxTrack

    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(path.expanduser())), rosbag2_py.ConverterOptions("", ""))
    r.set_filter(rosbag2_py.StorageFilter(topics=["/voss/vision/box"]))
    tracks = defaultdict(list)
    while r.has_next():
        _, data, _ = r.read_next()
        m = deserialize_message(data, BoxTrack)
        if m.position_valid:
            ts = m.stamp.sec + m.stamp.nanosec * 1e-9
            tracks[m.track_id].append((ts, m.position_base.x * 1e3, m.position_base.y * 1e3))
    return tracks


def live(secs: float) -> dict:
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from voss_msgs.msg import BoxTrack

    rclpy.init()
    n = rclpy.create_node("belt_speed_readonly")
    tracks = defaultdict(list)

    def cb(m) -> None:
        if m.position_valid:
            ts = m.stamp.sec + m.stamp.nanosec * 1e-9
            tracks[m.track_id].append((ts, m.position_base.x * 1e3, m.position_base.y * 1e3))

    n.create_subscription(BoxTrack, "/voss/vision/box", cb, qos_profile_sensor_data)
    end = time.time() + secs
    print(f"{secs:.0f} s 동안 /voss/vision/box 를 듣는다 — 박스를 벨트에 흘린다")
    while time.time() < end:
        rclpy.spin_once(n, timeout_sec=0.1)
    n.destroy_node()
    rclpy.try_shutdown()
    return tracks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bag", type=Path)
    ap.add_argument("--secs", type=float, default=60.0)
    a = ap.parse_args()
    report(from_bag(a.bag) if a.bag else live(a.secs))


if __name__ == "__main__":
    main()
