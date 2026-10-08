#!/usr/bin/env python3
"""T32(#41) 완료 기준 "move_line 큐 1시간 무정지" — MoveToZone 을 돌려 가며 gateway 큐를 1시간 지켜본다.

⚠ 로봇이 계속 움직인다. 실로봇: 사람이 비상정지 옆에서 끝까지(1시간). robot_gateway 를 dry_run:=false 로
먼저 띄우고 관측 자세에서 시작. 두산은 부르지 않는다(robot_gateway 만 — 절대 규칙 3). 빈손으로 한다.

    python3 queue_soak.py                       # 60 분, A:1 → B:1 → RECHECK:0 PLACE 반복
    python3 queue_soak.py --minutes 5            # 짧게 먼저
    python3 queue_soak.py --plan A:1,HOLD:1      # 칸 바꾸기 (PLACE 는 OBSERVE 복귀까지 한 번)

기록: ~/voss_data/1009/soak/soak_HHMMSS.csv (호출마다) + 끝에 요약.
- 호출: 시각·구역·칸·ok·message·걸린 시간
- /voss/robot/pose: 5 s 창마다 Hz·가장 긴 간격 → 큐가 move_line 동안 pose 조회를 막지 않았는지
- /voss/robot/state: ERROR·connected=False 로 바뀐 횟수
첫 실패(ok=false)에서 멈춘다(무정지 기준). Ctrl+C 면 /voss/robot/stop 을 부르고 끝낸다.
"""

from __future__ import annotations

import argparse
import csv
import threading
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger

from voss_msgs.msg import RobotState
from voss_msgs.srv import MoveToZone

OUT = Path.home() / "voss_data" / "1009" / "soak"


class Soak(Node):
    def __init__(self) -> None:
        super().__init__("queue_soak")
        self.mtz = self.create_client(MoveToZone, "/voss/robot/move_to_zone")
        self.stop = self.create_client(Trigger, "/voss/robot/stop")
        self.lock = threading.Lock()
        self.pose_t: list[float] = []  # 이번 창의 수신 시각
        self.windows: list[tuple[float, float]] = []  # (Hz, 최대 간격 ms)
        self.state_bad = 0
        self.last_state = ""
        self.create_subscription(
            PoseStamped,
            "/voss/robot/pose",
            self._on_pose,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
        )
        self.create_subscription(
            RobotState,
            "/voss/robot/state",
            self._on_state,
            QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.create_timer(5.0, self._roll)

    def _on_pose(self, _m: PoseStamped) -> None:
        with self.lock:
            self.pose_t.append(time.monotonic())

    def _on_state(self, m: RobotState) -> None:
        key = f"{m.state}/{m.error_code}/{m.connected}"
        if key != self.last_state:
            if m.state == "ERROR" or not m.connected:
                self.state_bad += 1
                self.get_logger().warn(f"RobotState {key} ({m.detail})")
            self.last_state = key

    def _roll(self) -> None:
        with self.lock:
            t, self.pose_t = self.pose_t, []
        gaps = [(b - a) * 1e3 for a, b in zip(t, t[1:], strict=False)]
        self.windows.append((len(t) / 5.0, max(gaps) if gaps else float("inf")))

    def call(self, zone: str, slot: int, timeout: float = 120.0):
        req = MoveToZone.Request()
        req.zone, req.slot, req.mode = zone, slot, ""
        fut = self.mtz.call_async(req)
        end = time.monotonic() + timeout
        while not fut.done() and time.monotonic() < end:
            time.sleep(0.05)
        return fut.result() if fut.done() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--plan", default="A:1,B:1,RECHECK:0", help="구역:칸, 쉼표로")
    a = ap.parse_args()
    plan = [(z.split(":")[0].upper(), int(z.split(":")[1])) for z in a.plan.split(",")]

    rclpy.init()
    n = Soak()
    ex = MultiThreadedExecutor()
    ex.add_node(n)
    threading.Thread(target=ex.spin, daemon=True).start()
    if not n.mtz.wait_for_service(timeout_sec=5.0):
        print("/voss/robot/move_to_zone 이 없다 — gateway 를 먼저 띄운다")
        rclpy.shutdown()
        return

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / time.strftime("soak_%H%M%S.csv")
    t0 = time.monotonic()
    end = t0 + a.minutes * 60.0
    rows, fail = 0, None
    print(
        f"{a.minutes:.0f} 분, {plan} 반복 → {path}  (Ctrl+C = /voss/robot/stop 후 종료)", flush=True
    )
    try:
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "zone", "slot", "ok", "message", "dur_s"])
            i = 0
            while time.monotonic() < end:
                zone, slot = plan[i % len(plan)]
                ts = time.monotonic()
                r = n.call(zone, slot)
                dur = time.monotonic() - ts
                ok = bool(r and r.ok)
                msg = r.message if r else "NO_RESPONSE(120 s)"
                w.writerow([f"{ts - t0:.1f}", zone, slot, ok, msg, f"{dur:.1f}"])
                f.flush()
                rows += 1
                print(f"[{(ts - t0) / 60:5.1f} 분] {zone}:{slot} → {msg} {dur:.1f} s", flush=True)
                if not ok:
                    fail = f"{zone}:{slot} {msg}"
                    break
                i += 1
    except KeyboardInterrupt:
        fut = n.stop.call_async(Trigger.Request())
        for _ in range(60):
            if fut.done():
                break
            time.sleep(0.05)
        print(f"\nCtrl+C → /voss/robot/stop {fut.result().message if fut.done() else 'TIMEOUT'}")
        fail = "사람이 멈춤"

    win = [x for x in n.windows if x[0] > 0]
    mins = (time.monotonic() - t0) / 60.0
    print(f"\n요약: {mins:.1f} 분, 호출 {rows}번, 실패 {fail or '없음'}")
    if win:
        print(
            f"pose 5 s 창 {len(win)}개: 최저 {min(h for h, _ in win):.1f} Hz, "
            f"가장 긴 간격 {max(g for _, g in win):.0f} ms (끊김 판정: 0 Hz 창 "
            f"{sum(1 for h, _ in n.windows if h == 0)}개)"
        )
    print(f"RobotState ERROR·끊김 전환 {n.state_bad}번")
    print(f"기록: {path}")
    ex.shutdown()
    n.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
