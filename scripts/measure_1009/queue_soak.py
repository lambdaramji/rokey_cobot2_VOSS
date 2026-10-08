#!/usr/bin/env python3
"""T32(#41) 완료 기준 "move_line 큐 30분 무정지"(10/08 PL 승인, 원래 1시간) — MoveToZone 을 돌려 가며 gateway 큐를 지켜본다.

⚠ 로봇이 계속 움직인다. 실로봇: 사람이 비상정지 옆에서 끝까지. 두산은 부르지 않는다(robot_gateway 만 — 절대 규칙 3). 빈손.
실행 전제(18:26 사고, #123 리뷰 남현지):
  ① robot_gateway 가 #121(컨트롤러 TCP 확인·경로 이탈 정지)이 들어간 빌드, dry_run:=false, 관측 자세에서 시작
  ② 펜던트 활성 TCP = GripperDA_v1 (강제회수 → TCP 메뉴에서 GripperDA_v1 → 설정 → 제어권 반환)
  ③ gateway 기동 로그 `컨트롤러 TCP 등록 voss_config 와 같음` — 시작 때 RobotState.detail 로 다시 보고 아니면 거부
  ④ 펜던트 공간 제한 상태(켜짐/꺼짐·범위)를 기록해 둔다
순서: 새 계획·새 빌드는 반드시 `--minutes 5` 먼저 → 이상 없으면 본 시험.

    python3 queue_soak.py --minutes 5            # 필수 첫 단계
    python3 queue_soak.py --minutes 30           # 본 시험(T32), 5구역 13칸 전부(A·B·C 0~2, 재확인·보류 0~1) 차례로
    python3 queue_soak.py --plan "A:1, HOLD:1"   # 칸 고르기

칸마다: 관측 자세에서 RG2 닫기(39 mm·14 N, 박스를 든 것처럼) → MoveToZone PLACE(칸에서 90 mm 열기 → OBSERVE).
기록: ~/voss_data/<실행 MMDD>/soak/soak_HHMMSS.csv (호출마다) + 끝에 요약.
- 호출: 시각·구역·칸·닫기·ok·message·걸린 시간·그리퍼 최대 기울기, gateway MoveToZone 속도(zone_vel)
- /voss/robot/pose: 5 s 창마다 Hz, 수신 간격(창 경계를 넘는 간격 포함) 최대
- /voss/robot/state: ERROR·connected=False 로 바뀐 횟수
- 그리퍼 기울기: pose 자세에서 툴 z 축과 수직 아래의 각(°) — 이동 중 손목이 돌거나 기우는지
멈춤: 첫 실패(닫기 실패·응답 없음·ok=false)와 Ctrl+C 모두 /voss/robot/stop 을 부르고 응답을 찍는다(멱등).
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
from rcl_interfaces.srv import GetParameters
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_srvs.srv import Trigger

from voss_msgs.msg import RobotState
from voss_msgs.srv import Gripper, MoveToZone

ALL_SLOTS = "A:0,A:1,A:2,B:0,B:1,B:2,C:0,C:1,C:2,RECHECK:0,RECHECK:1,HOLD:0,HOLD:1"
TILT_WARN_DEG = 5.0
TCP_BAD = ("TCP 등록 없음", "TCP 등록 모름")  # #121 RobotState.detail — 핑거 끝 기준이 아님


def tilt_deg(q) -> float:
    """쿼터니언(x, y, z, w) 자세의 툴 z 축이 수직 아래(−Z)에서 기운 각(°)."""
    x, y, _z, _w = q
    zz = 1.0 - 2.0 * (x * x + y * y)  # 회전 행렬 R[2][2] = 툴 z 축의 베이스 z 성분
    return math.degrees(math.acos(max(-1.0, min(1.0, -zz))))


def parse_plan(text: str) -> list[tuple[str, int]]:
    """ "A:1, HOLD:1" → [("A", 1), ("HOLD", 1)] (공백 허용)."""
    out = []
    for item in text.split(","):
        zone, slot = item.strip().split(":")
        out.append((zone.strip().upper(), int(slot.strip())))
    return out


class Soak(Node):
    def __init__(self) -> None:
        super().__init__("queue_soak")
        self.mtz = self.create_client(MoveToZone, "/voss/robot/move_to_zone")
        self.stop = self.create_client(Trigger, "/voss/robot/stop")
        self.grip = self.create_client(Gripper, "/voss/robot/gripper")
        self.params = self.create_client(GetParameters, "/robot_gateway/get_parameters")
        self.lock = threading.Lock()
        self.n_win = 0  # 이번 창 수신 수
        self.gap_win = 0.0  # 이번 창 최대 간격 ms (직전 수신은 창과 관계없이 유지)
        self.last_rx: float | None = None
        self.windows: list[tuple[float, float]] = []  # (Hz, 최대 간격 ms)
        self.tilt_max = 0.0  # 이번 호출 중 최대 기울기
        self.state: RobotState | None = None
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
        now = time.monotonic()
        with self.lock:
            if self.last_rx is not None:
                self.gap_win = max(self.gap_win, (now - self.last_rx) * 1e3)
            self.last_rx = now
            self.n_win += 1
            self.tilt_max = max(self.tilt_max, t)

    def _on_state(self, m: RobotState) -> None:
        self.state = m
        key = f"{m.state}/{m.error_code}/{m.connected}"
        if key != self.last_state:
            if m.state == "ERROR" or not m.connected:
                self.state_bad += 1
                self.get_logger().warn(f"RobotState {key} ({m.detail})")
            self.last_state = key

    def _roll(self) -> None:
        now = time.monotonic()
        with self.lock:
            gap = self.gap_win
            if self.last_rx is not None:  # 창 끝까지 아무것도 안 왔으면 그 간격도 센다
                gap = max(gap, (now - self.last_rx) * 1e3)
            self.windows.append((self.n_win / 5.0, gap))
            self.n_win, self.gap_win = 0, 0.0

    @staticmethod
    def _wait(fut, timeout: float):
        end = time.monotonic() + timeout
        while not fut.done() and time.monotonic() < end:
            time.sleep(0.05)
        return fut.result() if fut.done() else None

    def halt(self, why: str) -> None:
        """/voss/robot/stop (멱등) — 응답 없는 MoveToZone 은 팔이 아직 움직이는 중일 수 있다."""
        r = self._wait(self.stop.call_async(Trigger.Request()), 6.0)
        print(f"{why} → /voss/robot/stop {r.message if r else 'NO_RESPONSE'}", flush=True)

    def zone_vel(self) -> str:
        """gateway 파라미터 zone_vel [선 mm/s, 각 deg/s] (기록용)."""
        req = GetParameters.Request()
        req.names = ["zone_vel"]
        r = self._wait(self.params.call_async(req), 3.0)
        if not r or not r.values:
            return "?"
        return "/".join(f"{v:g}" for v in r.values[0].double_array_value)

    def close(self):
        """박스를 든 것처럼 닫는다(빈손이라 보고 폭 ≈ 38~39). PLACE 가 칸에서 연다."""
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


def preflight(n: Soak) -> str:
    """시작 전 확인. 문제면 이유, 괜찮으면 ""."""
    for cli, name in ((n.mtz, "move_to_zone"), (n.stop, "stop"), (n.grip, "gripper")):
        if not cli.wait_for_service(timeout_sec=5.0):
            return f"/voss/robot/{name} 가 없다 — gateway 를 먼저 띄운다"
    end = time.monotonic() + 3.0
    while n.state is None and time.monotonic() < end:
        time.sleep(0.05)
    s = n.state
    if s is None:
        return "/voss/robot/state 를 3 s 동안 못 받음"
    if not s.connected or s.state not in ("READY", "STOPPED"):
        return f"RobotState {s.state} connected={s.connected} ({s.detail})"
    if any(b in s.detail for b in TCP_BAD):
        return (
            f"컨트롤러 TCP 가 GripperDA_v1 이 아님: {s.detail} — 펜던트에서 선택 후 gateway 재기동"
        )
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--plan", default=ALL_SLOTS, help="구역:칸, 쉼표로 (기본 13칸 전부)")
    a = ap.parse_args()
    plan = parse_plan(a.plan)

    # Ctrl+C 때 컨텍스트가 먼저 내려가면 stop 응답을 못 받는다 → 직접 처리(robot_gateway 와 같음)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    n = Soak()
    ex = MultiThreadedExecutor()
    ex.add_node(n)
    spin = threading.Thread(target=ex.spin, daemon=True)
    spin.start()
    rows, fail, tilts = 0, None, {}
    t0 = time.monotonic()
    path = None
    try:
        why = preflight(n)
        if why:
            print(f"시작 안 함: {why}")
        else:
            vel = n.zone_vel()
            out = Path.home() / "voss_data" / time.strftime("%m%d") / "soak"
            out.mkdir(parents=True, exist_ok=True)
            path = out / time.strftime("soak_%H%M%S.csv")
            end = t0 + a.minutes * 60.0
            print(
                f"{a.minutes:.0f} 분, zone_vel {vel}, {len(plan)}칸 {plan} 반복 → {path}"
                "  (Ctrl+C = /voss/robot/stop 후 종료)",
                flush=True,
            )
            with path.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["t_s", "zone", "slot", "close", "close_width", "ok", "message",
                            "dur_s", "tilt_max_deg", "zone_vel"])  # fmt: skip
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
                    w.writerow([f"{ts - t0:.1f}", zone, slot, g.message, f"{g.width_actual:.1f}",
                                ok, msg, f"{dur:.1f}", f"{tilt:.1f}", vel])  # fmt: skip
                    f.flush()
                    rows += 1
                    key = f"{zone}:{slot}"
                    tilts[key] = max(tilts.get(key, 0.0), tilt)
                    warn = f"  ⚠ 기울기 {tilt:.1f}°" if tilt > TILT_WARN_DEG else ""
                    print(
                        f"[{(ts - t0) / 60:5.1f} 분] 닫기 {g.width_actual:.1f} → {key} → {msg}"
                        f" {dur:.1f} s, 최대 기울기 {tilt:.1f}°{warn}",
                        flush=True,
                    )
                    if not ok:
                        fail = f"{key} {msg}"
                        break
                    i += 1
            if fail:
                n.halt(f"실패({fail})")
    except KeyboardInterrupt:
        fail = "사람이 멈춤(Ctrl+C)"
        n.halt("\nCtrl+C")

    if path is not None:
        win = [x for x in n.windows if x[0] > 0]
        mins = (time.monotonic() - t0) / 60.0
        print(f"\n요약: {mins:.1f} 분, 호출 {rows}번, 실패 {fail or '없음'}")
        if win:
            print(
                f"pose 5 s 창 {len(win)}개: 최저 {min(h for h, _ in win):.1f} Hz, "
                f"가장 긴 간격 {max(g for _, g in n.windows):.0f} ms (끊김 판정: 0 Hz 창 "
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
