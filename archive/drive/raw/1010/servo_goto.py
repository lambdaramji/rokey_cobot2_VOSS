#!/usr/bin/env python3
"""TCP 를 목표점까지 servo_cmd(속도)로 옮긴다 — 10/10 VERIFY 벤치용 현장 도구 (⚠ 로봇이 움직인다).

robot_gateway 의 /voss/robot/servo_cmd 만 쓴다(두산 직접 호출 없음, CLAUDE.md 규칙 3). 자세는 그대로(각속도 0).
사람이 비상정지 옆에서 실행한다(규칙 6). 뒤에 gateway 안전(TCP z ≥ 78 자름, x −107~638, watchdog 200 ms)과
펜던트 공간 제한(벨트 위 z 77)이 있다. servo_f04.py 와 같은 QoS·stamp·stop 방식.

  python3 servo_goto.py --x -94.8 --y -276.0 --speed 20   # 지금 높이 그대로 수평 이동
  python3 servo_goto.py --z 81.8 --speed 10               # 지금 x·y 그대로 수직 이동

안전: 목표 z ≥ 80. 출발·목표 중 하나라도 z < 140 이면 수평 이동 ≤ 3 mm(박스 근처는 수직만). 한 번에 ≤ 150 mm,
속도 ≤ 30 mm/s. 직선 경로에서 5 mm 넘게 벗어남 · pose 0.3 s 끊김 · 1.5 s 동안 안 움직임 · 시간 초과면
/voss/robot/stop 을 부르고 끝낸다. Ctrl-C 도 stop. 도착(오차 ≤ 0.2 mm) → 0 속도 0.5 s → 발행 중단(gateway 가 move_stop).
종료 코드: 0 도착 · 1 중단(stop 부름) 또는 시작 안 함 · 2 거부(움직이지 않음).
기록: ~/voss_data/<MMDD>/goto/goto_HHMMSS.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import threading
import time
from pathlib import Path

import rclpy
import rclpy.executors
from geometry_msgs.msg import PoseStamped, TwistStamped
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger

RATE_HZ = 30.0
KP = 2.0  # 1/s — 남은 거리(mm) × KP = 속도(mm/s)
V_MIN = 1.0  # mm/s — 목표 근처에서 너무 느려 서지 않게
TOL_MM = 0.2  # 도착 판정
MIN_Z = 80.0  # 목표 z 하한 (gateway 78·공간 제한 77 보다 위)
NEAR_Z = 140.0  # 이 아래에서는 수평 이동 ≤ NEAR_XY_MM
NEAR_XY_MM = 3.0
MAX_DIST = 150.0
MAX_SPEED = 30.0
OFF_PATH_MM = 5.0
POSE_STALE_S = 0.3
OUT = Path.home() / "voss_data" / time.strftime("%m%d") / "goto"


class Goto(Node):
    def __init__(self) -> None:
        super().__init__("servo_goto")
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)  # topics.md servo_cmd QoS
        self.pub = self.create_publisher(TwistStamped, "/voss/robot/servo_cmd", qos)
        self.create_subscription(PoseStamped, "/voss/robot/pose", self._pose, qos)
        self.stop_cli = self.create_client(Trigger, "/voss/robot/stop")
        self.lock = threading.Lock()
        self.pose: tuple[float, float, float, float] | None = None  # (mono, x, y, z) mm

    def _pose(self, m: PoseStamped) -> None:
        p = m.pose.position
        with self.lock:
            self.pose = (time.monotonic(), p.x * 1e3, p.y * 1e3, p.z * 1e3)

    def last(self):
        with self.lock:
            return self.pose

    def send(self, v_mm_s) -> None:
        m = TwistStamped()
        m.header.stamp = self.get_clock().now().to_msg()
        m.header.frame_id = "base_link"
        m.twist.linear.x, m.twist.linear.y, m.twist.linear.z = (c / 1e3 for c in v_mm_s)
        self.pub.publish(m)

    def call_stop(self) -> str:
        if not self.stop_cli.wait_for_service(timeout_sec=1.0):
            return "no service"
        fut = self.stop_cli.call_async(Trigger.Request())
        end = time.monotonic() + 3.0
        while not fut.done() and time.monotonic() < end:
            time.sleep(0.01)
        r = fut.result() if fut.done() else None
        return "no response" if r is None else f"success={r.success} {r.message}"


def off_path(p, a, b) -> float:
    """점 p 와 선분 a→b 사이 거리 (mm)."""
    ab = [b[i] - a[i] for i in range(3)]
    n2 = sum(c * c for c in ab)
    t = 0.0 if n2 == 0 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n2))
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])


def main() -> int:
    ap = argparse.ArgumentParser(description="TCP 를 목표점까지 servo_cmd 로 옮긴다 (⚠ 로봇이 움직인다)")
    ap.add_argument("--x", type=float, help="목표 TCP x mm (생략 = 지금 값)")
    ap.add_argument("--y", type=float, help="목표 TCP y mm (생략 = 지금 값)")
    ap.add_argument("--z", type=float, help="목표 TCP z mm (생략 = 지금 값)")
    ap.add_argument("--speed", type=float, default=10.0, help=f"최대 속도 mm/s (≤ {MAX_SPEED:g})")
    a = ap.parse_args()
    if a.x is None and a.y is None and a.z is None:
        sys.exit("--x · --y · --z 중 하나는 줘야 한다")
    if not 0 < a.speed <= MAX_SPEED:
        sys.exit(f"속도 0 < speed ≤ {MAX_SPEED:g} mm/s")

    rclpy.init()
    node = Goto()
    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    try:
        return run(node, a)
    finally:  # spin 스레드를 먼저 끝내야 종료 때 C++ terminate(core dump)가 나지 않는다
        executor.shutdown()
        spin.join(timeout=2.0)
        node.destroy_node()
        rclpy.try_shutdown()


def run(node: Goto, a) -> int:
    t_wait = time.monotonic() + 3.0
    while node.last() is None and time.monotonic() < t_wait:
        time.sleep(0.05)
    first = node.last()
    if first is None:
        print("거부: /voss/robot/pose 가 안 들어온다 — robot_gateway 확인")
        return 2
    s = list(first[1:])
    tgt = [s[0] if a.x is None else a.x, s[1] if a.y is None else a.y, s[2] if a.z is None else a.z]
    dist0 = math.dist(s, tgt)
    dxy = math.hypot(tgt[0] - s[0], tgt[1] - s[1])
    print(f"지금 TCP ({s[0]:.1f}, {s[1]:.1f}, {s[2]:.1f}) → 목표 ({tgt[0]:.1f}, {tgt[1]:.1f}, {tgt[2]:.1f}) mm")
    print(f"거리 {dist0:.1f} mm (수평 {dxy:.1f}), 최대 {a.speed:g} mm/s, 예상 {dist0 / a.speed + 1.5:.0f} s")
    refuse = None
    if tgt[2] < MIN_Z:
        refuse = f"목표 z {tgt[2]:.1f} < {MIN_Z:g} mm"
    elif dist0 > MAX_DIST:
        refuse = f"한 번에 {MAX_DIST:g} mm 까지 (지금 {dist0:.1f}) — 나눠서 옮긴다"
    elif min(s[2], tgt[2]) < NEAR_Z and dxy > NEAR_XY_MM:
        refuse = f"z < {NEAR_Z:g} 에서는 수평 이동 ≤ {NEAR_XY_MM:g} mm (박스 근처는 수직만) — 먼저 올린다"
    if refuse:
        print(f"거부: {refuse} (움직이지 않음)")
        return 2
    if dist0 <= TOL_MM:
        print("이미 목표에 있다 (움직이지 않음)")
        return 0
    try:
        if input("⚠ 로봇이 움직인다. 비상정지 옆인가? 시작 [y/N] ").strip().lower() != "y":
            return 1
    except (KeyboardInterrupt, EOFError):
        print()
        return 1

    rows: list[tuple] = []
    t0 = time.monotonic()
    t_limit = 2.0 * dist0 / a.speed + 5.0
    ok_n, t_print, why = 0, 0.0, None
    try:
        while True:
            p = node.last()
            now = time.monotonic()
            cur = list(p[1:])
            d = math.dist(cur, tgt)
            if now - p[0] > POSE_STALE_S:
                why = f"pose {now - p[0]:.2f} s 끊김"
            elif off_path(cur, s, tgt) > OFF_PATH_MM:
                why = f"경로에서 {off_path(cur, s, tgt):.1f} mm 벗어남"
            elif cur[2] < MIN_Z - 0.5:
                why = f"z {cur[2]:.1f} < {MIN_Z - 0.5:g}"
            elif now - t0 > 1.5 and dist0 > 2.0 and dist0 - d < 0.5:
                why = "1.5 s 동안 안 움직임 — gateway 가 servo_cmd 를 받는지(BUSY·STOPPED·거부) T2 로그 확인"
            elif now - t0 > t_limit:
                why = f"시간 초과 {t_limit:.0f} s"
            if why:
                break
            if d <= TOL_MM:
                ok_n += 1
                v = [0.0, 0.0, 0.0]
                if ok_n >= 3:
                    break
            else:
                ok_n = 0
                spd = min(max(KP * d, V_MIN), a.speed)
                v = [(tgt[i] - cur[i]) / d * spd for i in range(3)]
            node.send(v)
            rows.append((round(now - t0, 4), *(round(c, 3) for c in cur), *(round(c, 2) for c in v)))
            if now - t_print >= 0.5:
                t_print = now
                print(f"  [{now - t0:5.1f} s] ({cur[0]:.1f}, {cur[1]:.1f}, {cur[2]:.1f})  남은 {d:.1f} mm")
            time.sleep(1.0 / RATE_HZ)
    except KeyboardInterrupt:
        why = "Ctrl-C"

    if why:
        print(f"⚠ 중단: {why} → /voss/robot/stop: {node.call_stop()}")
    else:
        end = time.monotonic() + 0.5  # 0 속도를 잠깐 더 보낸 뒤 끊는다 (gateway watchdog → move_stop)
        while time.monotonic() < end:
            node.send([0.0, 0.0, 0.0])
            time.sleep(1.0 / RATE_HZ)
    time.sleep(0.6)
    fin = node.last()
    err = math.dist(fin[1:], tgt)
    print(f"{'중단' if why else '도착'}: TCP ({fin[1]:.2f}, {fin[2]:.2f}, {fin[3]:.2f}) mm, 목표와 차 {err:.2f} mm, "
          f"{time.monotonic() - t0:.1f} s")  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / time.strftime("goto_%H%M%S.csv")
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "x_mm", "y_mm", "z_mm", "vx_mm_s", "vy_mm_s", "vz_mm_s"])
        w.writerows(rows)
    print(f"저장 {path}")
    return 1 if why else 0


if __name__ == "__main__":
    sys.exit(main())
