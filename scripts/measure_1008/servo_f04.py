#!/usr/bin/env python3
"""F-04 — robot_gateway servo_cmd watchdog·stop·z 하한 실측 (⚠ 로봇이 움직인다, ADR-0010).

belt_servo 대신 /voss/robot/servo_cmd(TwistStamped, m/s, base_link)를 30 Hz 로 보내고 /voss/robot/pose 로
실제 움직임을 기록한다. 두산은 부르지 않는다(robot_gateway 만 부름 — 절대 규칙 3).
실로봇: 사람이 비상정지 옆에서. robot_gateway 는 dry_run:=false 로 먼저 띄운다. 시작은 관측 자세.

    python3 servo_f04.py cut    # +x 5 mm/s 2 s → 퍼블리시 중단 → watchdog 정지까지 시간·초과 이동
    python3 servo_f04.py zero   # +x 2 s → 0 명령 0.5 s → 중단 (belt_servo 정상 종료 모양)
    python3 servo_f04.py stop   # +x 2 s 중 /voss/robot/stop → stop 이전 stamp 3개(무시돼야) → 새 stamp 로 −x 2 s(다시 움직여야)
    python3 servo_f04.py zmin   # −z 5 mm/s 최대 4 s (gateway servo_z_min_mm 에서 멈춰야. 하한은 gateway 파라미터로 정함)
    python3 servo_f04.py exit   # +x 스트리밍 중 사람이 gateway 를 Ctrl-C → 종료 정지까지 시간·초과 이동
    공통: --speed 5 (≤ 10 mm/s) --secs 2 (이동 ≤ 10 mm) --axis x|y|z  · 결과 CSV·요약은 ~/voss_data/1008/f04/
    --fast: 추종 속도 확인용(cut·zero 만) — 속도 ≤ 50 mm/s, 스트리밍 이동 ≤ 40 mm, 이탈 한도 80 mm.
      예) python3 servo_f04.py cut --fast --speed 48 --secs 1.0   (가속 0.48 s + 정속, 끊긴 뒤 약 21 mm 예상)
안전: 시작점에서 20 mm 넘게 벗어나면 /voss/robot/stop 을 부르고 끝낸다. 각 시나리오 뒤 반대로 되돌리지 않는다
(다음 시나리오 전에 사람이 touch_verify.py obs 로 관측 자세 복귀).
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
from rclpy.time import Time
from std_srvs.srv import Trigger

RATE_HZ = 30.0
MAX_SPEED = 10.0  # mm/s
MAX_TRAVEL = 12.0  # mm (speed × secs)
ABORT_DEV = 20.0  # mm
STILL_MM_S = 0.3  # 이보다 느리면 멈춘 것으로 본다 (0.1 s 창)
OUT = Path.home() / "voss_data/1008/f04"


class F04(Node):
    def __init__(self) -> None:
        super().__init__("servo_f04")
        qos = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.BEST_EFFORT
        )  # topics.md servo_cmd QoS
        self.pub = self.create_publisher(TwistStamped, "/voss/robot/servo_cmd", qos)
        self.create_subscription(PoseStamped, "/voss/robot/pose", self._pose, qos)
        self.stop_cli = self.create_client(Trigger, "/voss/robot/stop")
        self.poses: list[tuple[float, float, float, float]] = []  # (mono, x, y, z) mm
        self.events: list[tuple[float, str]] = []
        self.lock = threading.Lock()

    def _pose(self, m: PoseStamped) -> None:
        p = m.pose.position
        with self.lock:
            self.poses.append((time.monotonic(), p.x * 1e3, p.y * 1e3, p.z * 1e3))

    def last(self):
        with self.lock:
            return self.poses[-1] if self.poses else None

    def ev(self, what: str) -> None:
        self.events.append((time.monotonic(), what))
        print(f"  [{time.monotonic() - T0:6.2f} s] {what}")

    def send(self, v_mm_s, stamp: Time | None = None) -> None:
        m = TwistStamped()
        m.header.stamp = (stamp or self.get_clock().now()).to_msg()
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


T0 = time.monotonic()


def stream(node: F04, v, secs: float, start) -> bool:
    """secs 동안 30 Hz 로 v 를 보낸다. 시작점 이탈 시 stop 하고 False."""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        node.send(v)
        p = node.last()
        if p and math.dist(p[1:], start[1:]) > ABORT_DEV:
            node.ev(f"⚠ 시작점에서 {ABORT_DEV} mm 이탈 → stop: {node.call_stop()}")
            return False
        time.sleep(1.0 / RATE_HZ)
    return True


def stopped_after(node: F04, t_from: float, timeout: float = 3.0):
    """t_from 이후 움직임이 멈춘 시각과 그때까지의 이동 거리(mm)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        time.sleep(0.05)
    with node.lock:
        ps = [p for p in node.poses if p[0] >= t_from - 0.05]
    if len(ps) < 3:
        return None, None
    base = ps[0]
    for i in range(len(ps)):
        win = [q for q in ps[i:] if q[0] - ps[i][0] <= 0.25]
        # 창 0.2 s 이상: pose 값이 0.1 s 마다만 바뀌는 때가 있어(같은 값 5번, 10/08 오후) 짧은 창은 '멈춤'으로 보인다
        if len(win) >= 3 and win[-1][0] - win[0][0] >= 0.2:
            spd = math.dist(win[-1][1:], win[0][1:]) / (win[-1][0] - win[0][0])
            if spd < STILL_MM_S:
                return ps[i][0] - t_from, math.dist(ps[i][1:], base[1:])
    return None, math.dist(ps[-1][1:], base[1:])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["cut", "zero", "stop", "zmin", "exit"])
    ap.add_argument("--speed", type=float, default=5.0)
    ap.add_argument("--secs", type=float, default=2.0)
    ap.add_argument("--axis", choices=["x", "y", "z"], default="x")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--fast", action="store_true", help="추종 속도(≤ 50 mm/s) cut·zero")
    a = ap.parse_args()
    global MAX_SPEED, MAX_TRAVEL, ABORT_DEV
    if a.fast:
        if a.scenario not in ("cut", "zero"):
            sys.exit("--fast 는 cut·zero 만")
        MAX_SPEED, MAX_TRAVEL, ABORT_DEV = 50.0, 40.0, 80.0
    if not 0 < a.speed <= MAX_SPEED or a.speed * a.secs > MAX_TRAVEL:
        sys.exit(f"속도 ≤ {MAX_SPEED} mm/s, 이동(속도×시간) ≤ {MAX_TRAVEL} mm")
    axis = {"x": 0, "y": 1, "z": 2}["z" if a.scenario == "zmin" else a.axis]
    sign = -1.0 if a.scenario == "zmin" else 1.0
    v = [0.0, 0.0, 0.0]
    v[axis] = sign * a.speed
    secs = 4.0 if a.scenario == "zmin" else a.secs
    if a.scenario == "zmin" and a.speed * secs > 25.0:
        sys.exit("zmin 은 최대 25 mm 이동까지")

    rclpy.init()
    node = F04()
    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    t_wait = time.monotonic() + 3.0
    while node.last() is None and time.monotonic() < t_wait:
        time.sleep(0.05)
    start = node.last()
    if start is None:
        sys.exit("/voss/robot/pose 가 안 들어온다 — robot_gateway 확인")
    print(
        f"시작 TCP ({start[1]:.2f}, {start[2]:.2f}, {start[3]:.2f}) mm, 시나리오 {a.scenario}, v {v} mm/s"
    )
    if (
        not a.yes
        and input("⚠ 로봇이 움직인다. 비상정지 옆인가? 시작 [y/N] ").strip().lower() != "y"
    ):
        return 1
    global T0
    T0 = time.monotonic()
    res: dict = {"scenario": a.scenario, "speed": a.speed, "axis": "xyz"[axis], "fast": a.fast}

    if a.scenario in ("cut", "zero"):
        node.ev(f"스트리밍 시작 {v} mm/s")
        if stream(node, v, secs, start):
            if a.scenario == "zero":
                node.ev("0 명령 0.5 s")
                stream(node, [0.0, 0.0, 0.0], 0.5, start)
            t_cut = time.monotonic()
            node.ev("퍼블리시 중단")
            dt, dist = stopped_after(node, t_cut)
            res.update(stop_s=dt, overshoot_mm=dist)
            when = (
                "이미 멈춰 있음"
                if dt is not None and dt <= 0
                else f"멈춤까지 {dt if dt is None else round(dt, 3)} s"
            )
            node.ev(f"{when}, 중단 뒤 이동 {dist and round(dist, 2)} mm")
    elif a.scenario == "stop":
        node.ev(f"스트리밍 시작 {v} mm/s")
        if stream(node, v, secs, start):
            t_stop = time.monotonic()
            before = node.get_clock().now()
            node.ev(f"/voss/robot/stop → {node.call_stop()}")
            dt, dist = stopped_after(node, t_stop, 1.5)
            res.update(stop_s=dt, overshoot_mm=dist)
            node.ev(
                f"stop 뒤 멈춤까지 {dt if dt is None else round(dt, 3)} s, 이동 {dist and round(dist, 2)} mm"
            )
            p0 = node.last()
            for _ in range(3):  # stop 이전 stamp → gateway 가 버려야 한다
                node.send(v, stamp=before)
                time.sleep(1.0 / RATE_HZ)
            time.sleep(0.5)
            moved_old = math.dist(node.last()[1:], p0[1:])
            res["moved_by_old_stamp_mm"] = moved_old
            node.ev(f"stop 이전 stamp 3개 보낸 뒤 이동 {moved_old:.2f} mm (≈0 이어야)")
            p1 = node.last()
            back = [-c for c in v]
            node.ev(f"새 stamp 로 {back} mm/s {secs} s (move_stop 뒤 speedl 재수신 확인)")
            stream(node, back, secs, start)
            moved_new = math.dist(node.last()[1:], p1[1:])
            res["moved_after_restart_mm"] = moved_new
            node.ev(f"재수신 이동 {moved_new:.2f} mm (≈ {a.speed * secs:.0f} 이어야)")
            t_cut = time.monotonic()
            dt2, d2 = stopped_after(node, t_cut)
            node.ev(
                f"중단 뒤 멈춤까지 {dt2 if dt2 is None else round(dt2, 3)} s, {d2 and round(d2, 2)} mm"
            )
    elif a.scenario == "zmin":
        node.ev(f"−z 스트리밍 {a.speed} mm/s 최대 {secs} s (gateway z 하한에서 멈춰야)")
        stream(node, v, secs, start)
        t_cut = time.monotonic()
        dt, dist = stopped_after(node, t_cut)
        z_end = node.last()[3]
        res.update(z_start=start[3], z_end=z_end)
        node.ev(f"z {start[3]:.2f} → {z_end:.2f} mm (gateway servo_z_min_mm 근처에서 멈췄나)")
    elif a.scenario == "exit":
        limit_s = min(
            secs, MAX_TRAVEL / a.speed
        )  # 이동 한도 안에서만 (10/08 첫 시도는 5 s·24.5 mm 를 감)
        node.ev(f"스트리밍 시작 {v} mm/s — 지금 gateway 터미널에서 Ctrl-C (최대 {limit_s:.1f} s)")
        t_end = time.monotonic() + limit_s
        gone = None
        while time.monotonic() < t_end:
            if node.count_publishers("/voss/robot/pose") == 0:
                gone = time.monotonic()
                node.ev("gateway 사라짐(pose 퍼블리셔 0)")
                break
            p = node.last()
            if p and math.dist(p[1:], start[1:]) > ABORT_DEV:
                node.ev(f"⚠ 시작점에서 {ABORT_DEV} mm 이탈 → stop: {node.call_stop()}")
                break
            node.send(v)
            time.sleep(1.0 / RATE_HZ)
        if gone is None:
            node.ev("시간 안에 gateway 가 안 꺼짐 → 스트리밍 중단 (watchdog 이 멈춘다)")
        res["gateway_gone"] = gone is not None
        node.ev(
            "이후 이동은 pose 가 없어 여기서 못 잼 — 눈으로 멈췄는지 확인, gateway 로그의 '종료 중 servo 활성' 확인"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    tag = time.strftime("%H%M%S")
    with (OUT / f"{a.scenario}_{tag}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "x_mm", "y_mm", "z_mm"])
        with node.lock:
            for p in node.poses:
                if p[0] >= T0 - 0.5:
                    w.writerow([f"{p[0] - T0:.4f}", f"{p[1]:.3f}", f"{p[2]:.3f}", f"{p[3]:.3f}"])
    with (OUT / f"{a.scenario}_{tag}_events.txt").open("w") as f:
        for t, e in node.events:
            f.write(f"{t - T0:.3f}\t{e}\n")
        f.write(f"result\t{res}\n")
    print(f"결과 {res}\n저장 {OUT}/{a.scenario}_{tag}.csv")
    executor.shutdown()  # 스핀 스레드를 먼저 끝낸 뒤 정리 (안 그러면 종료 때 core dump)
    spin.join(timeout=2.0)
    node.destroy_node()
    rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
