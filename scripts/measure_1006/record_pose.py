#!/usr/bin/env python3
"""10/06 실측 #6 — 로봇 자세 기록기 (읽기 전용) + 분석.

로봇을 움직이지 않는다. 두산 조회 서비스만 하나씩 차례로 부른다.
로봇은 사람이 펜던트·직접교시로 옮기고, 자리에 오면 Enter 로 기록한다.

    # 터미널 1 (사람): 브링업
    ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100
    # 터미널 2
    python3 record_pose.py walk              # 계획된 라벨을 순서대로 안내하며 기록
    python3 record_pose.py snap zone_A       # 한 점만 기록
    python3 record_pose.py analyze           # 벨트 축·높이·구역 좌표 요약 + voss_config 조각

주의
- 두산 서비스는 동시에 부르면 드라이버가 멈춘다(전 프로젝트 실측). 이 스크립트가 도는 동안
  다른 사람이 get_current_posx 등을 부르는 스크립트(캘리브레이션 등)를 같이 돌리지 않는다.
- 기록은 '플랜지 posx'와 '현재 TCP posx'를 둘 다 남긴다. 분석은 플랜지 값으로 한다
  (TCP 등록은 브링업마다 풀리므로 기준이 흔들리지 않게).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import math
import os
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))
CSV_PATH = DATA_DIR / "poses.csv"
PREFIX = "/dsr01/dsr_controller2/"  # doosan-robot2 31750d6 소스 기준. 실기에서 다르면 --prefix
FIELDS = (
    ["stamp", "label", "robot_system", "robot_mode", "tool", "tcp"]
    + [f"flange_{k}" for k in ("x", "y", "z", "rx", "ry", "rz")]
    + [f"tcp_{k}" for k in ("x", "y", "z", "rx", "ry", "rz")]
    + [f"j{i}" for i in range(1, 7)]
    + ["note"]
)

BOX_H_MM = 27.0  # 박스 높이
REACH_MM = 900.0  # M0609 리치

# walk 모드 순서. (라벨, 안내문)
PLAN = [
    ("tip_table", "그리퍼 닫고 수직(B≈180) 아래로. 핑거 끝을 로봇 가까운 작업대 면에 살짝 댄다"),
    (
        "tip_belt_up",
        "그리퍼 닫고 수직. 벨트 중앙선 위 '상류 쪽 닿는 끝'에 핑거 끝을 살짝 댄다 (벨트 정지 상태)",
    ),
    ("tip_belt_mid", "그리퍼 닫고 수직. 벨트 중앙선 가운데쯤에 핑거 끝을 댄다"),
    ("tip_belt_down", "그리퍼 닫고 수직. 벨트 중앙선 위 '하류 쪽 닿는 끝'에 핑거 끝을 댄다"),
    ("box_on_table", "박스(46 mm 면)를 쥔 채 수직. 박스 밑면이 작업대에 막 닿게 내린다"),
    (
        "zone_A",
        "박스를 쥔 채, A(역삼동) 구역 중심에 밑면이 막 닿게. 핑거 닫힘축은 벨트에서 집을 때와 같은 방향",
    ),
    ("zone_B", "같은 방법으로 B(대치동) 구역 중심"),
    ("zone_C", "같은 방법으로 C(청담동) 구역 중심"),
    ("zone_recheck", "같은 방법으로 재확인 구역 중심"),
    ("zone_hold", "같은 방법으로 보류 구역 중심"),
    (
        "observe",
        "관측 자세 후보: 카메라가 벨트 상류 약 20 cm 구간을 보는 자세(카메라 높이 15~20 cm). 남현지·박병후와 같이 본다",
    ),
    ("safe", "구역 사이를 오갈 때 지나갈 안전 자세(위로 충분히 든 자세)"),
]


# ---------------------------------------------------------------- 순수 계산 (ROS 없이 시험 가능)
def rot_zyz(a_deg: float, b_deg: float, c_deg: float) -> list[list[float]]:
    """두산 posx 자세(A, B, C) = Rz(A)·Ry(B)·Rz(C)."""
    a, b, c = (math.radians(v) for v in (a_deg, b_deg, c_deg))
    ca, sa, cb, sb, cc, sc = (
        math.cos(a),
        math.sin(a),
        math.cos(b),
        math.sin(b),
        math.cos(c),
        math.sin(c),
    )
    return [
        [ca * cb * cc - sa * sc, -ca * cb * sc - sa * cc, ca * sb],
        [sa * cb * cc + ca * sc, -sa * cb * sc + ca * cc, sa * sb],
        [-sb * cc, sb * sc, cb],
    ]


def tilt_from_down_deg(pose6: list[float]) -> float:
    """툴 z축이 베이스 -z(수직 아래)에서 기울어진 각도."""
    r = rot_zyz(*pose6[3:6])
    return math.degrees(math.acos(max(-1.0, min(1.0, -r[2][2]))))


def apply_tcp(flange6: list[float], tcp_xyz: list[float]) -> list[float]:
    """플랜지 posx + TCP 오프셋(툴 좌표) → TCP 위치 (x, y, z)."""
    r = rot_zyz(*flange6[3:6])
    return [flange6[i] + sum(r[i][k] * tcp_xyz[k] for k in range(3)) for i in range(3)]


def axis_label(dx: float, dy: float) -> str:
    """벨트 진행 방향 벡터 → voss_config belt.direction_axis 후보 ('x', '-y' ...)."""
    if abs(dx) >= abs(dy):
        return "x" if dx > 0 else "-x"
    return "y" if dy > 0 else "-y"


def analyze_rows(rows: list[dict], clearance_mm: float = 5.0) -> dict:
    """기록된 점 → 벨트 축·높이, 파지 오프셋, 구역 중심 놓기 자세(플랜지 기준). 마지막 기록이 우선.

    구역 자세는 구역 중심이다. 2×2 격자 슬롯은 중심 ± pitch/2 로 robot_gateway 가 계산한다(제안).
    """
    pts: dict[str, dict] = {}
    for r in rows:
        pts[r["label"]] = r

    def fl(label):
        r = pts.get(label)
        if r is None:
            return None
        return [float(r[f"flange_{k}"]) for k in ("x", "y", "z", "rx", "ry", "rz")]

    out: dict = {"warnings": [], "points": {}}
    for label in pts:
        p = fl(label)
        tilt = tilt_from_down_deg(p)
        reach = math.hypot(p[0], p[1])
        out["points"][label] = {"flange": p, "tilt_deg": tilt, "reach_xy_mm": reach}
        if (
            label.startswith("tip_") or label.startswith("zone_") or label == "box_on_table"
        ) and tilt > 2.0:
            out["warnings"].append(f"{label}: 수직에서 {tilt:.1f}° 기울어짐 (2° 이내로 다시)")
        if reach > REACH_MM - 50:
            out["warnings"].append(
                f"{label}: 베이스 축에서 {reach:.0f} mm — 리치 900 mm 끝에 가깝다"
            )
    tcps = {pts[k]["tcp"] for k in pts}
    if len(tcps) > 1:
        out["warnings"].append(
            f"기록마다 활성 TCP 가 다르다: {sorted(tcps)} (플랜지 값으로 분석하므로 영향 없음)"
        )

    up, down, table = fl("tip_belt_up"), fl("tip_belt_down"), fl("tip_table")
    if up and down:
        dx, dy = down[0] - up[0], down[1] - up[1]
        length = math.hypot(dx, dy)
        belt = {
            "direction_unit": [dx / length, dy / length] if length else [0.0, 0.0],
            "angle_from_base_x_deg": math.degrees(math.atan2(dy, dx)),
            "direction_axis": axis_label(dx, dy),
            "reachable_length_mm": length,
            "z_drop_mm": down[2] - up[2],
        }
        mid = fl("tip_belt_mid")
        if mid and length:
            # 중앙점이 up-down 직선에서 얼마나 벗어났는지 (벨트 직진성/기록 실수 확인)
            cross = ((mid[0] - up[0]) * dy - (mid[1] - up[1]) * dx) / length
            belt["mid_offset_mm"] = cross
        if length < 500:
            out["warnings"].append(f"벨트 추종 구간 {length:.0f} mm < 500 mm (SR-HW-01 미달)")
        if (
            abs(belt["angle_from_base_x_deg"] % 90) > 3
            and abs(belt["angle_from_base_x_deg"] % 90) < 87
        ):
            out["warnings"].append(
                f"벨트가 베이스 축과 {belt['angle_from_base_x_deg']:.1f}° — 축 하나('x' 등)로 쓰면 오차. "
                "direction_unit 벡터를 belt_servo 에 같이 넘기자고 제안"
            )
        if table:
            belt["belt_above_table_mm"] = (up[2] + down[2]) / 2 - table[2]
        out["belt"] = belt
    box = fl("box_on_table")
    if box and table:
        # 박스를 쥐고 밑면이 작업대에 닿을 때 플랜지가 핑거끝-작업대 접촉보다 얼마나 높은지
        grasp = box[2] - table[2]
        out["grasp_offset_mm"] = grasp
        # 참고값(폭 보정 안 됨): 닫힌 핑거와 벌린 핑거의 끝 높이가 같다고 가정한다
        out["finger_below_box_top_mm"] = BOX_H_MM - grasp
        if up and down:
            belt_flange_z = (up[2] + down[2]) / 2
            out["grasp_flange_z_on_belt"] = belt_flange_z + grasp
    zones = {}
    for z in ("A", "B", "C", "recheck", "hold"):
        p = fl(f"zone_{z}")
        if p:
            q = list(p)
            q[2] += clearance_mm
            zones[z] = [round(v, 2) for v in q]
    out["zones_place_flange"] = zones
    names = list(zones)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            d = math.hypot(zones[a][0] - zones[b][0], zones[a][1] - zones[b][1])
            if d < 130:
                out["warnings"].append(
                    f"구역 {a}–{b} 중심 사이 {d:.0f} mm — 2×2 격자(60 mm)+박스 46 mm 면 약 106 mm 폭이라 겹칠 수 있다"
                )
    for k in ("observe", "safe"):
        if fl(k):
            out[k] = [round(v, 2) for v in fl(k)]
    return out


def config_snippet(res: dict) -> str:
    lines = [
        "# 플랜지 기준 posx (TCP 미적용), 구역 pose = 구역 중심. 기준을 바꾸면 다시 계산한다",
        "zones:",
    ]
    for z, p in res.get("zones_place_flange", {}).items():
        grid = "" if z in ("recheck", "hold") else ", grid: {cols: 2, rows: 2, pitch_mm: 60}"
        lines.append(f"  {z + ':':9}{{pose: {p}{grid}}}")
    if "observe" in res:
        lines.append(f"observe_pose: {res['observe']}")
    if "belt" in res:
        lines += [
            "belt:",
            "  speed_cmps: <#1 실측>",
            f'  direction_axis: "{res["belt"]["direction_axis"]}"',
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------- ROS 조회
class Reader:
    def __init__(self, timeout: float = 2.0, retries: int = 2, prefix: str = PREFIX):
        import rclpy
        from dsr_msgs2.srv import (
            GetCurrentPosj,
            GetCurrentPosx,
            GetCurrentTcp,
            GetCurrentTool,
            GetCurrentToolFlangePosx,
            GetRobotMode,
            GetRobotSystem,
        )

        self.rclpy = rclpy
        rclpy.init()
        self.node = rclpy.create_node("voss_record_pose")
        self.timeout, self.retries = timeout, retries
        spec = {
            "system": (GetRobotSystem, "system/get_robot_system"),
            "mode": (GetRobotMode, "system/get_robot_mode"),
            "tool": (GetCurrentTool, "tool/get_current_tool"),
            "tcp": (GetCurrentTcp, "tcp/get_current_tcp"),
            "posx": (GetCurrentPosx, "aux_control/get_current_posx"),
            "flange": (GetCurrentToolFlangePosx, "aux_control/get_current_tool_flange_posx"),
            "posj": (GetCurrentPosj, "aux_control/get_current_posj"),
        }
        self.types = {k: t for k, (t, _) in spec.items()}
        self.cli = {k: self.node.create_client(t, prefix + n) for k, (t, n) in spec.items()}
        deadline = time.monotonic() + 10.0
        missing = [
            c.srv_name
            for c in self.cli.values()
            if not c.wait_for_service(timeout_sec=max(0.1, deadline - time.monotonic()))
        ]
        if missing:
            raise SystemExit(
                f"서비스 연결 안 됨: {missing}\n브링업이 떠 있는지, ROS_DOMAIN_ID 가 같은지 확인"
            )

    def call(self, key: str, **kw):
        req = self.types[key].Request(**kw)
        for _ in range(self.retries + 1):
            fut = self.cli[key].call_async(req)  # 앞 호출이 끝난 뒤에만 다음을 부른다 (직렬)
            self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=self.timeout)
            if fut.done() and fut.result() is not None and fut.result().success:
                return fut.result()
        raise RuntimeError(f"{key} 조회 실패 (시간초과 또는 success=false)")

    def snap(self) -> dict:
        r = {
            "robot_system": {0: "real", 1: "virtual"}.get(self.call("system").robot_system, "?"),
            "robot_mode": {0: "manual", 1: "auto"}.get(self.call("mode").robot_mode, "?"),
            "tool": self.call("tool").info,
            "tcp": self.call("tcp").info,
        }
        posx = list(self.call("posx", ref=0).task_pos_info[0].data[:6])
        flange = list(self.call("flange", ref=0).pos)
        posj = list(self.call("posj").pos)
        for i, k in enumerate(("x", "y", "z", "rx", "ry", "rz")):
            r[f"flange_{k}"] = round(flange[i], 3)
            r[f"tcp_{k}"] = round(posx[i], 3)
        for i in range(6):
            r[f"j{i + 1}"] = round(posj[i], 3)
        return r

    def close(self):
        self.node.destroy_node()
        self.rclpy.shutdown()


def append(row: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def show(row: dict) -> None:
    f = [row[f"flange_{k}"] for k in ("x", "y", "z", "rx", "ry", "rz")]
    t = [row[f"tcp_{k}"] for k in ("x", "y", "z", "rx", "ry", "rz")]
    print(
        f"  [{row['label']}] {row['robot_system']}/{row['robot_mode']} tool='{row['tool']}' tcp='{row['tcp']}'"
    )
    print(f"    flange posx: {f}  (수직에서 {tilt_from_down_deg(f):.1f}°)")
    print(f"    TCP    posx: {t}")
    if row["robot_system"] != "real":
        print("    ⚠ virtual 모드 값이다. 실측이 아니다")


def record(reader: Reader, label: str, note: str) -> None:
    row = reader.snap()
    row.update(stamp=datetime.datetime.now().isoformat(timespec="seconds"), label=label, note=note)
    append(row)
    show(row)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prefix", default=PREFIX, help=f"두산 서비스 접두 (기본 {PREFIX})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snap", help="한 점 기록")
    s.add_argument("label")
    s.add_argument("--note", default="")
    w = sub.add_parser(
        "walk", help="계획된 라벨 순서대로 기록 (s=건너뛰기, r=같은 라벨 다시, q=끝)"
    )
    w.add_argument("--start", default=None, help="이 라벨부터 시작")
    a = sub.add_parser("analyze", help="기록 요약")
    a.add_argument("--clearance", type=float, default=5.0, help="놓기 높이 여유 [mm] (기본 5)")
    a.add_argument("--csv", default=str(CSV_PATH))
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        with open(args.csv, newline="") as f:
            res = analyze_rows(list(csv.DictReader(f)), args.clearance)
        import json

        print(
            json.dumps(
                {k: v for k, v in res.items() if k != "points"}, ensure_ascii=False, indent=2
            )
        )
        print("\n# --- voss_config.yaml 후보 ---")
        print(config_snippet(res))
        return 0

    reader = Reader(prefix=args.prefix)
    try:
        if args.cmd == "snap":
            record(reader, args.label, args.note)
            return 0
        plan = PLAN
        if args.start:
            plan = PLAN[[p[0] for p in PLAN].index(args.start) :]
        print(
            f"기록 파일: {CSV_PATH}\n로봇을 자리로 옮긴 뒤 Enter. 메모를 쓰고 Enter 하면 note 로 남는다."
        )
        try:
            for label, guide in plan:
                while True:
                    ans = input(
                        f"\n▶ {label}: {guide}\n  [Enter=기록 / s=건너뛰기 / q=끝] 메모> "
                    ).strip()
                    if ans == "q":
                        return 0
                    if ans == "s":
                        break
                    record(reader, label, ans)
                    if input("  다시 찍을까? [r=다시 / Enter=다음] ").strip() != "r":
                        break
        except (EOFError, KeyboardInterrupt):
            print("\n중단. 여기까지 기록됐다. 이어서: python3 record_pose.py walk --start <라벨>")
            return 0
        print("\n끝. python3 record_pose.py analyze 로 요약을 본다")
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
