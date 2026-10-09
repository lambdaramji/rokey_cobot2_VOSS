#!/usr/bin/env python3
"""T34(#43) 완료 기준 "찌그러짐 없는 파지 10회" + ADR-0009 회전 박스(15°·30°) 파지 기록.

⚠ RG2 가 움직인다 — 사람이 비상정지 옆에서 실행(CLAUDE.md 규칙 6, 그리퍼도 대상).
RG2 만 움직인다(/voss/robot/gripper — robot_gateway 경유, 두산·RG2 직접 호출 없음). 로봇 팔은 움직이지 않는다.
박스는 사람이 핑거 사이에 둔다(손을 핑거 밖으로 뺀 뒤 Enter). 로봇 위치는 펜던트로 미리 정한다
(10/08: 벨트 12 V 끔, 박스를 관측 자세 아래 벨트 위에, 핑거 끝 TCP z ≈ 82 — measurements-1008 #14).

    python3 grip_check.py                       # 10회, 39 mm·14 N (ADR-0009 값), 각도 0
    python3 grip_check.py --angle 15 --n 5      # 핑거 닫힘축에 대해 박스를 15° 돌려 둔 회차
    python3 grip_check.py --angle 30 --n 5
    python3 grip_check.py --offset 10 --n 3    # 박스 중심을 핑거 중심에서 벨트 방향(X)으로 10 mm 어긋나게 둔 회차

회차마다: Enter → 닫기(width·force) → 보고 폭·grip_detected → 사람이 찌그러짐·미끄러짐 입력 → 90 mm 열기.
기록: ~/voss_data/<실행 MMDD>/grip/grip_HHMMSS.csv. 판정 기준(ADR-0009·measurements-1006 #8·measurements-1008 #14): grip_detected=True,
보고 폭 40~44 mm(박스 31 mm 면 → 보고 40.7~43.0, 10/08), 찌그러짐·미끄러짐 없음.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import rclpy

from voss_msgs.srv import Gripper

OUT = Path.home() / "voss_data" / time.strftime("%m%d") / "grip"
OPEN_MM = 90.0
OK_WIDTH = (
    40.0,
    44.0,
)  # 보고값 mm — 빈손 38~39 와 가르게. 박스 31 mm 면 → 보고 40.7~43.0 (10/08 #14)


def call(node, cli, width: float, force: float) -> Gripper.Response | None:
    req = Gripper.Request()
    req.width, req.force = float(width), float(force)
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=10.0)
    return fut.result() if fut.done() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--width", type=float, default=39.0)
    ap.add_argument("--force", type=float, default=14.0)
    ap.add_argument(
        "--angle", type=float, default=0.0, help="박스를 닫힘축에 대해 돌린 각도(기록용)"
    )
    ap.add_argument(
        "--offset",
        type=float,
        default=0.0,
        help="박스 중심의 벨트 방향 어긋남 mm(기록용, ADR-0009)",
    )
    a = ap.parse_args()
    if not 5.0 <= a.force <= 20.0:
        raise SystemExit("힘은 5~20 N (종이 박스, measurements #8)")

    rclpy.init()
    node = rclpy.create_node("grip_check")
    cli = node.create_client(Gripper, "/voss/robot/gripper")
    if not cli.wait_for_service(timeout_sec=5.0):
        raise SystemExit("/voss/robot/gripper 가 없다 — gateway 를 먼저 띄운다")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / time.strftime("grip_%H%M%S.csv")
    r = call(node, cli, OPEN_MM, a.force)
    print(f"시작 열기 → {r.message if r else 'NO_RESPONSE'}, 기록 {path}")
    if not (r and r.ok):
        node.destroy_node()
        rclpy.shutdown()
        raise SystemExit("시작 열기 실패 — gateway·RG2 확인 뒤 다시")
    good = done = 0
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trial", "angle_deg", "offset_mm", "width_cmd", "force", "ok", "message", "width_actual",
                    "grip_detected", "close_s", "dent", "slip", "note"])  # fmt: skip
        for i in range(1, a.n + 1):
            if (
                input(
                    f"\n[{i}/{a.n}] 박스를 {a.angle:.0f}°·벨트 방향 {a.offset:+.0f} mm 로 두고 손을 뺀 뒤 Enter (q 끝): "
                ).strip()
                == "q"
            ):
                break
            t = time.monotonic()
            r = call(node, cli, a.width, a.force)
            dt = time.monotonic() - t
            if r is None:
                print("응답 없음 — 멈춘다")
                break
            in_range = OK_WIDTH[0] <= r.width_actual <= OK_WIDTH[1]
            print(f"  닫기 → {r.message}, 보고 폭 {r.width_actual:.1f} mm, grip {r.grip_detected}, {dt:.1f} s"
                  + ("" if in_range else "  ⚠ 폭 범위 밖"))  # fmt: skip
            dent = input("  찌그러짐? (y/N): ").strip().lower() == "y"
            slip = input("  박스를 살짝 당겼을 때 미끄러짐? (y/N): ").strip().lower() == "y"
            note = input("  메모(없으면 Enter): ").strip()
            o = call(node, cli, OPEN_MM, a.force)
            print(f"  열기 → {o.message if o else 'NO_RESPONSE'}")
            ok = r.ok and r.grip_detected and in_range and not dent and not slip
            good += ok
            done += 1
            w.writerow([i, a.angle, a.offset, a.width, a.force, r.ok, r.message, f"{r.width_actual:.1f}",
                        r.grip_detected, f"{dt:.2f}", dent, slip, note])  # fmt: skip
            f.flush()
    print(
        f"\n요약: 각도 {a.angle:.0f}°·어긋남 {a.offset:+.0f} mm, 성공 {good}/{done} (grip_detected·폭 범위·찌그러짐 없음·미끄러짐 없음)"
    )
    print(f"기록: {path}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
