#!/usr/bin/env python3
"""읽기 전용: /voss/vision/box 에서 track_id > --min 인 유효 트랙이 처음 보이면 --delay 초 뒤 그 번호를 출력한다.
goal 대기용. --x-min 을 주면 박스가 그 x 를 지난 뒤에 낸다 (ros2 topic echo | awk 는 파이프 버퍼 때문에 출력이 늦게 나온다)."""
import argparse, sys, time
import rclpy
from rclpy.qos import qos_profile_sensor_data
from voss_msgs.msg import BoxTrack

ap = argparse.ArgumentParser()
ap.add_argument("--min", type=int, required=True, help="이 번호보다 큰 트랙만")
ap.add_argument("--delay", type=float, default=1.0, help="처음 본 뒤 기다릴 초")
ap.add_argument("--timeout", type=float, default=120.0)
ap.add_argument("--x-min", type=float, default=None, help="박스 중심 x(mm)가 이 값 이상이 된 뒤에 낸다 (화면 가운데쯤에서 goal)")
a = ap.parse_args()
rclpy.init()
n = rclpy.create_node("wait_track_readonly")
seen = {}
n.create_subscription(BoxTrack, "/voss/vision/box",
                      lambda m: seen.setdefault(m.track_id, time.monotonic()) if m.position_valid and m.track_id > a.min and (a.x_min is None or m.position_base.x * 1000.0 >= a.x_min) else None,
                      qos_profile_sensor_data)
print(f"track_id > {a.min} 를 기다린다 (벨트를 켠다)", file=sys.stderr)
end = time.monotonic() + a.timeout
tid = None
while time.monotonic() < end:
    rclpy.spin_once(n, timeout_sec=0.05)
    if seen:
        tid, t0 = min(seen.items())
        if time.monotonic() - t0 >= a.delay:
            break
n.destroy_node(); rclpy.try_shutdown()
if tid is None:
    sys.exit("시간 초과 — 새 트랙이 안 나왔다")
print(f"track_id={tid}", file=sys.stderr)
print(tid)
