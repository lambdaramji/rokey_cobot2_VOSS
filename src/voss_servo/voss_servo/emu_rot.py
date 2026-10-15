"""emu_rot — 두산 에뮬레이터에서 gateway 각속도 경로를 직접 시험한다 (S2-T18 run.md 2절 E3′·E5·E8).

belt_servo 대신 `/voss/robot/servo_cmd`(TwistStamped, 선속도 0, angular.z rad/s)를 30 Hz 로 보내고
`/voss/robot/pose` 의 공구 yaw·TCP xy 를 기록한다. 두산은 부르지 않는다(robot_gateway 만 — 절대 규칙 3).
**에뮬레이터 전용 — 실로봇 방어**: ROS_DOMAIN_ID 가 비었거나 30(실로봇 도메인)이거나, 로봇 유선망(192.168.1.x)
인터페이스가 있으면 시작하지 않는다(voss-ros 래퍼와 같은 조건 — 도메인을 잘못 export 한 공용 PC 도 막는다).
**실험 전제(방어가 아님)**: 시작 자세가 관측 자세(공구 yaw −88.7° ± 3°)여야 한다 — 실로봇도 관측 자세에 있을 수
있으므로 이것은 안전장치가 아니다. 판정은 명령 내용(gateway 통계·기동 줄)으로 하고, 여기 수치는 기록이다(ADR-0010 결과 6).

    voss-ros python3 -m voss_servo.emu_rot pure  --dir +1   # E3′ 30°/s 1.0 s (≈30°) → TCP xy 이동
    voss-ros python3 -m voss_servo.emu_rot over  --dir +1   # E8① 90°/s 0.5 s → 실제 각속도 ≤ 60
    voss-ros python3 -m voss_servo.emu_rot limit --dir +1   # E8② 30°/s 계속 → 한계 앞 자름·정지 각
    voss-ros python3 -m voss_servo.emu_rot crawl --dir +1   # E8③ 60°/s → 자름(감속) 뒤 1°/s 재지령
    voss-ros python3 -m voss_servo.emu_rot cut   --dir +1   # E8④ 60°/s 로 40° 돈 뒤 발행 중단(watchdog)
    voss-ros python3 -m voss_servo.emu_rot brake --dir +1   # E5(i) 60°/s 0.9 s → 0 지령 유지
    voss-ros python3 -m voss_servo.emu_rot brake --dir +1 --stop  # E5(ii) 같은데 /voss/robot/stop
    공통: --out <폴더>(CSV·요약 JSON), --center-deg -88.72(관측 자세 공구 yaw), --limit-deg 100(gateway 값)
안전: 기준 각에서 |상대각| > 한계 + 5° 면 /voss/robot/stop 을 부르고 끝낸다. 각 모드 뒤 사람이(Claude 가)
관측 자세로 되돌린다(run.md 2.0 의 move_joint) — 이 스크립트는 되돌리지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass

RATE_HZ = 30.0  # belt_servo 와 같은 발행 주기
OBSERVE_TOL_DEG = 3.0  # 시작 자세 허용 (rotate.start_tol_deg 와 같은 값)
ABORT_MARGIN_DEG = 5.0  # 한계 + 이만큼 넘으면 stop
STILL_DPS = 2.0  # 측정 각속도가 이보다 작으면 멈춘 것 (rotate.still_dps sim 값)
SETTLE_S = 1.0  # 지령 끝 뒤 이만큼 멈춰 있으면 기록 끝
MAX_RUN_S = 8.0  # 한 모드 상한
YAW_SAME_DEG = 1e-4  # 같은 yaw 로 보는 차
HOLD_S = 0.15  # 값이 이보다 오래 그대로면 정지 (rotate.YAW_HOLD_MAX)


@dataclass(frozen=True)
class Plan:
    """한 모드의 지령 계획 (deg/s, s)."""

    mode: str
    w1: float  # 첫 지령 각속도 deg/s (부호 포함)
    t1: float | None  # 첫 지령 시간 s (None = 조건이 될 때까지)
    w2: float | None = None  # 두 번째 지령 (crawl 1°/s, brake 0)
    until_rel: float | None = None  # 상대각이 이만큼이면 첫 지령을 끝냄 (cut)
    stop_call: bool = False  # 첫 지령 뒤 /voss/robot/stop (brake --stop)
    publish_after: bool = True  # 첫 지령 뒤에도 발행을 이어가나 (cut 은 False = watchdog)


def make_plan(mode: str, sign: int, stop: bool = False) -> Plan:
    """모드 이름 → 지령 계획. sign = +1 / −1 (회전 방향)."""
    s = 1.0 if sign > 0 else -1.0
    if mode == "pure":
        return Plan(mode, 30.0 * s, 1.0, 0.0)  # ≈30° 돌고 0 유지
    if mode == "over":
        return Plan(mode, 90.0 * s, 0.5, 0.0)  # 상한 60 으로 잘려야
    if mode == "limit":
        return Plan(mode, 30.0 * s, None, 0.0)  # 30°/s 를 멈출 때까지 (gateway 가 자른다) → 0
    if mode == "crawl":
        return Plan(mode, 60.0 * s, None, 1.0 * s)  # 자름(감속 시작) 뒤 1°/s
    if mode == "cut":
        return Plan(mode, 60.0 * s, None, until_rel=40.0 * s, publish_after=False)
    if mode == "brake":
        return Plan(mode, 60.0 * s, 0.9, 0.0, stop_call=stop)
    raise ValueError(f"모르는 모드 {mode}")


def robot_net(ipv4_lines: list[str]) -> bool:
    """`ip -4 -o addr` 줄들 중 로봇 유선망(192.168.1.x) 주소가 있나 (voss-ros 래퍼와 같은 조건)."""
    return any(" 192.168.1." in line for line in ipv4_lines)


def refuse_reason(domain: str | None, ipv4_lines: list[str]) -> str | None:
    """실로봇 환경이면 거부 사유, 아니면 None."""
    if domain in (None, "", "30"):
        return "ROS_DOMAIN_ID 가 비었거나 30(실로봇) — 에뮬레이터 도메인을 명시하라"
    if robot_net(ipv4_lines):
        return "로봇 유선망(192.168.1.x)에 연결되어 있음"
    return None


def wrap_deg(a: float) -> float:
    """각을 (−180, 180] 로 감는다."""
    a = math.fmod(a + 180.0, 360.0)
    if a <= 0.0:
        a += 360.0
    return a - 180.0


def rel_deg(yaw_deg: float, center_deg: float) -> float:
    """기준 각(관측 자세 공구 yaw)에서 잰 상대각 — −방향은 ±180 을 넘으므로 감아서 (재검 B8)."""
    return wrap_deg(yaw_deg - center_deg)


def guard_cut_rel(w_dps: float, alpha_dps2: float, watchdog_s: float, limit_deg: float) -> float:
    """gateway yaw_limit 가 이 각속도를 0 으로 자르는 상대각 (servo_guard: 한계 − (v²/2α + v·watchdog))."""
    v = abs(w_dps)
    return limit_deg - (v * v / (2.0 * alpha_dps2) + v * watchdog_s)


def stop_rel_after_cut(w_dps: float, alpha_dps2: float, cut_rel: float) -> float:
    """자른 뒤 speedl 0 감속(α)으로 서는 상대각 (참고 — 에뮬레이터 정지량은 근거가 아님)."""
    return cut_rel + w_dps * w_dps / (2.0 * alpha_dps2)


def measured_w(prev: tuple[float, float] | None, yaw_deg: float, t: float) -> float | None:
    """측정 각속도 deg/s: 값이 바뀐 두 pose 의 차분, 값이 HOLD_S 넘게 그대로면 0 (rotate.omega_meas 와 같은 생각)."""
    if prev is None:
        return None
    d = wrap_deg(yaw_deg - prev[0])
    dt = t - prev[1]
    if abs(d) > YAW_SAME_DEG:
        return d / dt if dt > 0 else None
    return 0.0 if dt > HOLD_S else None


def crawl_switch(w_meas_dps: float | None, w_cmd_dps: float) -> bool:
    """crawl: 측정 각속도가 지령의 80 % 아래로 떨어지면(gateway 가 잘라 감속 중) 1°/s 로 바꿀 때."""
    return w_meas_dps is not None and abs(w_meas_dps) < 0.8 * abs(w_cmd_dps)


def summarize(rows: list[dict], center_deg: float, cmd_end_t: float | None) -> dict:
    """기록 → 요약: 상대각 처음·최대·마지막, TCP xy 이동, 측정 각속도 최대, 지령 끝 뒤 더 돈 각."""
    if not rows:
        return {"rows": 0}
    rels = [rel_deg(r["yaw_deg"], center_deg) for r in rows]
    first, last = rows[0], rows[-1]
    dxy = math.hypot(last["x_mm"] - first["x_mm"], last["y_mm"] - first["y_mm"])
    w = [abs(r["w_dps"]) for r in rows if r.get("w_dps") is not None]
    after = None
    if cmd_end_t is not None:
        at_end = [rel for r, rel in zip(rows, rels, strict=True) if r["t"] <= cmd_end_t]
        if at_end:
            after = rels[-1] - at_end[-1]  # 지령 끝 뒤 더 돈 각 (부호 포함)
    peak = max(rels, key=abs)
    return {
        "rows": len(rows),
        "rel_first_deg": rels[0],
        "rel_peak_deg": peak,
        "rel_last_deg": rels[-1],
        "tcp_dxy_mm": dxy,
        "w_meas_max_dps": max(w) if w else None,
        "after_cmd_deg": after,
    }


# ------------------------------------------------------------------ ROS 노드 (얇게)


def _node_main(args: argparse.Namespace) -> int:  # pragma: no cover - 에뮬레이터에서만
    import subprocess

    import rclpy
    import rclpy.executors
    from geometry_msgs.msg import PoseStamped, TwistStamped
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from std_srvs.srv import Trigger

    from voss_servo import rotate

    try:  # 주소 목록을 못 읽으면 안전하게 거부한다
        lines = subprocess.run(
            ["ip", "-4", "-o", "addr"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ip addr 실패 — 거부: {exc}", file=sys.stderr)
        return 3
    why = refuse_reason(os.environ.get("ROS_DOMAIN_ID"), lines)
    if why:
        print(why, file=sys.stderr)
        return 3
    plan = make_plan(args.mode, args.dir, args.stop)
    rclpy.init()
    node = Node("emu_rot")
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)  # topics.md servo_cmd QoS
    pub = node.create_publisher(TwistStamped, "/voss/robot/servo_cmd", qos)
    stop_cli = node.create_client(Trigger, "/voss/robot/stop")
    rows: list[dict] = []
    lock = threading.Lock()
    t0 = time.monotonic()
    prev: list = [None]  # (yaw_deg, t) — 값이 바뀐 첫 시각 (rotate.omega_meas 와 같은 규칙)

    def on_pose(m: PoseStamped) -> None:
        o, p = m.pose.orientation, m.pose.position
        r = rotate.tool_yaw((o.x, o.y, o.z, o.w))
        if r is None:
            return
        yaw = math.degrees(r[0])
        t = time.monotonic() - t0
        w = None
        w = measured_w(prev[0], yaw, t)
        if prev[0] is None or abs(wrap_deg(yaw - prev[0][0])) > YAW_SAME_DEG:
            prev[0] = (yaw, t)  # 값이 바뀐 첫 시각만 남긴다
        with lock:
            rows.append(
                {
                    "t": t,
                    "yaw_deg": yaw,
                    "w_dps": w,
                    "x_mm": p.x * 1e3,
                    "y_mm": p.y * 1e3,
                    "z_mm": p.z * 1e3,
                    "cmd_dps": cur_cmd[0],
                }
            )

    cur_cmd = [0.0]
    node.create_subscription(PoseStamped, "/voss/robot/pose", on_pose, qos)
    ex = rclpy.executors.SingleThreadedExecutor()
    ex.add_node(node)
    th = threading.Thread(target=ex.spin, daemon=True)
    th.start()

    def last() -> dict | None:
        with lock:
            return rows[-1] if rows else None

    def send(w_dps: float) -> None:
        cur_cmd[0] = w_dps
        m = TwistStamped()
        m.header.stamp = node.get_clock().now().to_msg()
        m.header.frame_id = "base_link"
        m.twist.angular.z = math.radians(w_dps)
        pub.publish(m)

    def call_stop(why: str) -> None:
        print(f"  stop: {why}")
        if stop_cli.wait_for_service(timeout_sec=1.0):
            stop_cli.call_async(Trigger.Request())

    end = time.monotonic() + 3.0
    while last() is None and time.monotonic() < end:
        time.sleep(0.05)
    first = last()
    if first is None:
        print("pose 없음 — gateway 를 먼저 띄운다", file=sys.stderr)
        return 2
    rel0 = rel_deg(first["yaw_deg"], args.center_deg)
    if abs(rel0) > OBSERVE_TOL_DEG:
        print(f"관측 자세가 아님(상대각 {rel0:.1f}°) — move_joint 로 OBSERVE 먼저", file=sys.stderr)
        return 2
    period = 1.0 / RATE_HZ
    t_start = time.monotonic()
    cmd_end_t = None
    phase = 1
    aborted = False
    while time.monotonic() - t_start < MAX_RUN_S:
        cur = last()
        rel = rel_deg(cur["yaw_deg"], args.center_deg) if cur else 0.0
        if abs(rel) > args.limit_deg + ABORT_MARGIN_DEG:
            call_stop(f"상대각 {rel:.1f}° > 한계 + {ABORT_MARGIN_DEG}")
            aborted = True
            break
        el = time.monotonic() - t_start
        if phase == 1:
            done = (
                (plan.t1 is not None and el >= plan.t1)
                or (plan.until_rel is not None and abs(rel) >= abs(plan.until_rel))
                or (plan.mode == "crawl" and el > 0.5 and crawl_switch(cur.get("w_dps"), plan.w1))
            )
            if not done:
                send(plan.w1)
            else:
                cmd_end_t = time.monotonic() - t0  # 기록 시계(t0 기준)
                phase = 2
                if plan.stop_call:
                    call_stop("brake --stop")
        if phase == 2:
            if not plan.publish_after:
                cur_cmd[0] = 0.0  # 발행 중단 → gateway watchdog
            elif plan.w2 is not None:
                send(plan.w2)
            moving = cur and cur.get("w_dps") is not None and abs(cur["w_dps"]) >= STILL_DPS
            since_end = (time.monotonic() - t0) - cmd_end_t  # 지령 끝 뒤 경과
            if plan.mode != "crawl" and not moving and since_end > SETTLE_S:
                break
        if plan.mode == "limit" and phase == 1 and el > 1.0:
            w = cur.get("w_dps") if cur else None
            if w is not None and abs(w) < STILL_DPS:  # 자름 뒤 멈춤
                cmd_end_t, phase = time.monotonic() - t0, 2
        time.sleep(period)
    if not aborted and plan.publish_after:
        for _ in range(15):  # 0 유지 0.5 s (belt_servo 끝과 같은 모양)
            send(0.0)
            time.sleep(period)
    time.sleep(0.5)
    with lock:
        data = list(rows)
    summ = summarize(data, args.center_deg, cmd_end_t)
    lim = args.limit_deg
    exp = {}
    if plan.mode in ("limit", "crawl", "cut"):
        cut = guard_cut_rel(plan.w1, args.alpha, args.watchdog, lim)
        exp = {"cut_rel_deg": cut, "stop_rel_deg": stop_rel_after_cut(plan.w1, args.alpha, cut)}
    out = {
        "plan": asdict(plan),
        "center_deg": args.center_deg,
        "limit_deg": lim,
        "aborted": aborted,
        "summary": summ,
        "expected": exp,
    }
    os.makedirs(args.out, exist_ok=True)
    stem = f"{plan.mode}_{'p' if args.dir > 0 else 'm'}{'_stop' if args.stop else ''}"
    with open(os.path.join(args.out, stem + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0].keys()) if data else ["t"])
        w.writeheader()
        w.writerows(data)
    with open(os.path.join(args.out, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ex.shutdown(timeout_sec=1.0)  # 스핀 스레드를 먼저 세우고 (그 전에 컨텍스트를 닫으면 abort)
    th.join(timeout=2.0)
    node.destroy_node()
    rclpy.try_shutdown()
    return 1 if aborted else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """명령줄 인자."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["pure", "over", "limit", "crawl", "cut", "brake"])
    ap.add_argument("--dir", type=int, choices=[1, -1], default=1, help="회전 방향 +1/−1")
    ap.add_argument("--stop", action="store_true", help="brake: 0 지령 대신 /voss/robot/stop")
    ap.add_argument("--out", default=os.path.expanduser("~/cobot2/cobot2_voss_data/emu_rot"))
    ap.add_argument("--center-deg", type=float, default=-88.72, help="관측 자세 공구 yaw")
    ap.add_argument("--limit-deg", type=float, default=100.0, help="gateway servo_yaw_limit_deg")
    ap.add_argument("--alpha", type=float, default=90.0, help="gateway 각가속 deg/s² (예상 계산)")
    ap.add_argument(
        "--watchdog", type=float, default=0.2, help="gateway servo_watchdog_s (예상 계산)"
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - 에뮬레이터에서만
    return _node_main(parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
