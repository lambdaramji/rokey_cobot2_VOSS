#!/usr/bin/env python3
"""T32(#41) 완료 기준 "move_line 큐 1시간 무정지" — MoveToZone 을 돌려 가며 gateway 큐를 1시간 지켜본다.

⚠ 로봇이 계속 움직인다. 실로봇: 사람이 비상정지 옆에서 끝까지(1시간). robot_gateway 를 dry_run:=false 로
먼저 띄우고 관측 자세에서 시작. 두산은 부르지 않는다(robot_gateway 만 — 절대 규칙 3). 빈손으로 한다.

    python3 queue_soak.py                       # 60 분, 5구역 13칸 전부(A·B·C 0~2, 재확인·보류 0~1) 차례로
    python3 queue_soak.py --minutes 5            # 짧게 먼저
    python3 queue_soak.py --plan A:1,HOLD:1      # 칸 고르기 (PLACE 는 OBSERVE 복귀까지 한 번)

칸마다: 관측 자세에서 RG2 닫기(39 mm·14 N, 박스를 든 것처럼) → MoveToZone PLACE(칸에서 90 mm 열기 → OBSERVE).

기록: ~/voss_data/1009/soak/soak_HHMMSS.csv (호출마다) + 끝에 요약.
- 호출: 시각·구역·칸·ok·message·걸린 시간
- /voss/robot/pose: 5 s 창마다 Hz·가장 긴 간격 → 큐가 move_line 동안 pose 조회를 막지 않았는지
- /voss/robot/state: ERROR·connected=False 로 바뀐 횟수
- 그리퍼 기울기: pose 자세에서 툴 z 축과 수직 아래의 각(°), 호출마다 최대 — 이동 중 손목이 돌거나 기우는지
첫 실패(ok=false)에서 멈춘다(무정지 기준). Ctrl+C 면 /voss/robot/stop 을 부르고 끝낸다.
"""

from __future__ import annotations

import argparse
import csv
import math
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
from voss_msgs.srv import Gripper, MoveToZone

OUT = Path.home() / "voss_data" / "1009" / "soak"
ALL_SLOTS = "A:0,A:1,A:2,B:0,B:1,B:2,C:0,C:1,C:2,RECHECK:0,RECHECK:1,HOLD:0,HOLD:1"
TILT_WARN_DEG = 5.0


def tilt_deg(q) -> float:
    """쿼터니언(x, y, z, w) 자세의 툴 z 축이 수직 아래(−Z)에서 기운 각(°)."""
    x, y, z, w = q
    zz = 1.0 - 2.0 * (x * x + y * y)  # 회전 행렬 R[2][2] = 툴 z 축의 베이스 z 성분
    return math.degrees(math.acos(max(-1.0, min(1.0, -zz))))


class Soak(Node):
    def __init__(self) -> None:
        super().__init__("queue_soak")
        self.mtz = self.create_client(MoveToZone, "/voss/robot/move_to_zone")
        self.stop = self.create_client(Trigger, "/voss/robot/stop")
        self.grip = self.create_client(Gripper, "/voss/robot/gripper")
        self.tilt_max = 0.0  # 이번 호출 중 최대 기울기
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

    def _on_pose(self, m: PoseStamped) -> None:
        o = m.pose.orientation
        t = tilt_deg((o.x, o.y, o.z, o.w))
        with self.lock:
            self.pose_t.append(time.monotonic())
            self.tilt_max = max(self.tilt_max, t)

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

    @staticmethod
    def _wait(fut, timeout: float):
        end = time.monotonic() + timeout
        while not fut.done() and time.monotonic() < end:
            time.sleep(0.05)
        return fut.result() if fut.done() else None

    def close(self):
        """박스를 든 것처럼 닫는다(빈손이라 보고 폭 ≈ 39). PLACE 가 칸에서 연다."""
        req = Gripper.Request()
        req.width, req.force = 39.0, 14.0
        return self._wait(self.grip.call_async(req), 10.0)

    def call(self, zone: str, slot: int, timeout: float = 120.0):
        req = MoveToZone.Request()
        req.zone, req.slot, req.mode = zone, slot, ""
        with self.lock:
            self.tilt_max = 0.0
        r = self._wait(self.mtz.call_async(req), timeout)
        with self.lock:
            return r, self.tilt_max


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--plan", default=ALL_SLOTS, help="구역:칸, 쉼표로 (기본 13칸 전부)")
    a = ap.parse_args()
    plan = [(z.split(":")[0].upper(), int(z.split(":")[1])) for z in a.plan.split(",")]

    rclpy.init()
    n = Soak()
    ex = MultiThreadedExecutor()
    ex.add_node(n)
    spin = threading.Thread(target=ex.spin, daemon=True)
    spin.start()
    if not n.mtz.wait_for_service(timeout_sec=5.0):
        print("/voss/robot/move_to_zone 이 없다 — gateway 를 먼저 띄운다")
        rclpy.shutdown()
        return

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / time.strftime("soak_%H%M%S.csv")
    t0 = time.monotonic()
    end = t0 + a.minutes * 60.0
    rows, fail, tilts = 0, None, {}
    print(
        f"{a.minutes:.0f} 분, {plan} 반복 → {path}  (Ctrl+C = /voss/robot/stop 후 종료)", flush=True
    )
    try:
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "zone", "slot", "close", "close_width", "ok", "message", "dur_s",
                        "tilt_max_deg"])  # fmt: skip
            i = 0
            while time.monotonic() < end:
                zone, slot = plan[i % len(plan)]
                g = n.close()
                if not (g and g.ok):
                    fail = f"그리퍼 닫기 {g.message if g else 'NO_RESPONSE'}"
                    break
                ts = time.monotonic()
                r, tilt = n.call(zone, slot)
                dur = time.monotonic() - ts
                ok = bool(r and r.ok)
                msg = r.message if r else "NO_RESPONSE(120 s)"
                w.writerow([f"{ts - t0:.1f}", zone, slot, g.message, f"{g.width_actual:.1f}", ok,
                            msg, f"{dur:.1f}", f"{tilt:.1f}"])  # fmt: skip
                f.flush()
                rows += 1
                key = f"{zone}:{slot}"
                tilts[key] = max(tilts.get(key, 0.0), tilt)
                warn = f"  ⚠ 기울기 {tilt:.1f}°" if tilt > TILT_WARN_DEG else ""
                print(
                    f"[{(ts - t0) / 60:5.1f} 분] 닫기 {g.width_actual:.1f} → {key} → {msg} {dur:.1f} s,"
                    f" 최대 기울기 {tilt:.1f}°{warn}",
                    flush=True,
                )
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
    if tilts:
        print("칸별 최대 기울기(°): " + ", ".join(f"{k} {v:.1f}" for k, v in tilts.items()))
    print(f"기록: {path}")
    ex.shutdown()
    spin.join(
        timeout=2.0
    )  # 실행 스레드가 끝나기 전에 노드를 없애면 C++ 쪽이 abort 한다(10/08 5 분 시험)
    n.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
