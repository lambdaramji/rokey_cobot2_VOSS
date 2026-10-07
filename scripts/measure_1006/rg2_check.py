#!/usr/bin/env python3
"""10/06 실측 #4·#8 — RG2 Modbus TCP 직접 확인과 파지력 시험.

status 는 읽기만 한다. move / open / grip 은 그리퍼를 움직인다 → 사람이 비상정지 옆에서 실행.
로봇 팔은 움직이지 않는다.

    python3 rg2_check.py status                 # 폭·상태비트·핑거 오프셋 (읽기 전용)
    python3 rg2_check.py status --watch 10      # 10초 동안 5 Hz 로 폭 감시 (읽기 전용)
    python3 rg2_check.py open --width 90        # 사전 개방 90 mm
    python3 rg2_check.py grip --force 5         # 박스를 핑거 사이에 두고 5 N 으로 쥔다 → 결과 기록
    python3 rg2_check.py summary                # 파지 기록 요약

레지스터(OnRobot RG, unit 65): 0 목표 힘(0.1 N) · 1 목표 폭(0.1 mm) · 2 제어(16=grip_w_offset)
258 핑거 오프셋 · 267 폭 · 268 상태 · 275 폭(오프셋 반영). 수업 코드 onrobot.py 와 같은 값.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))
LOG = DATA_DIR / "rg2_grip.csv"
UNIT = 65
MAX_WIDTH_MM, MAX_FORCE_N = 110.0, 40.0
STATUS_BITS = [
    "busy",
    "grip_detected",
    "s1_pushed",
    "s1_trig",
    "s2_pushed",
    "s2_trig",
    "safety_err",
]
LOG_FIELDS = [
    "stamp", "force_n", "target_mm", "width_mm", "width_off_mm", "grip_detected",
    "time_s", "dent", "slip", "note",
]  # fmt: skip


def decode_status(word: int) -> dict:
    return {name: bool(word >> i & 1) for i, name in enumerate(STATUS_BITS)}


class RG2:
    def __init__(self, ip: str, port: int):
        from pymodbus.client import ModbusTcpClient

        self.c = ModbusTcpClient(ip, port=port, timeout=1)
        if not self.c.connect():
            raise SystemExit(
                f"{ip}:{port} 연결 실패. ping {ip} → 같은 서브넷(192.168.1.x) 유선인지, 툴체인저 전원 확인"
            )

    def _kw(self):
        # pymodbus 3.6 은 slave=, 3.9+ 는 device_id=
        import inspect

        params = inspect.signature(self.c.read_holding_registers).parameters
        return {"device_id": UNIT} if "device_id" in params else {"slave": UNIT}

    def read(self, addr: int) -> int:
        r = self.c.read_holding_registers(addr, count=1, **self._kw())
        if r.isError():
            raise RuntimeError(f"레지스터 {addr} 읽기 실패: {r}")
        return r.registers[0]

    def snapshot(self) -> dict:
        off = self.read(258)
        off = off - 65536 if off > 32767 else off  # signed
        return {
            "fingertip_offset_mm": off / 10,
            "width_mm": self.read(267) / 10,
            "width_off_mm": self.read(275) / 10,
            **decode_status(self.read(268)),
        }

    def move(self, width_mm: float, force_n: float, timeout: float = 6.0) -> tuple[dict, float]:
        if not (0 <= width_mm <= MAX_WIDTH_MM and 0 <= force_n <= MAX_FORCE_N):
            raise SystemExit(f"범위 밖: 폭 0~{MAX_WIDTH_MM} mm, 힘 0~{MAX_FORCE_N} N")
        r = self.c.write_registers(0, [round(force_n * 10), round(width_mm * 10), 16], **self._kw())
        if r.isError():
            raise RuntimeError(f"명령 쓰기 실패: {r}")
        t0 = time.monotonic()
        time.sleep(0.15)  # busy 비트가 올라올 시간
        while time.monotonic() - t0 < timeout:
            s = self.snapshot()
            if not s["busy"]:
                return s, time.monotonic() - t0
            time.sleep(0.05)
        return self.snapshot(), timeout


def confirm(msg: str, yes: bool) -> None:
    if yes:
        return
    if input(f"{msg}\n그리퍼가 움직인다. 손가락 조심. 계속? [y/N] ").strip().lower() != "y":
        raise SystemExit("취소")


def print_snap(s: dict) -> None:
    flags = [k for k in STATUS_BITS if s[k]]
    print(
        f"폭 {s['width_mm']:.1f} mm (오프셋 반영 {s['width_off_mm']:.1f}) · "
        f"핑거 오프셋 {s['fingertip_offset_mm']:.1f} mm · 상태 {flags or ['정상']}"
    )


def log_row(row: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def summarize(rows: list[dict]) -> list[str]:
    """힘별로 묶어 '찌그러짐 없음 + 미끄러짐 없음 + grip 감지' 비율을 낸다."""
    by: dict[float, list[dict]] = {}
    for r in rows:
        by.setdefault(float(r["force_n"]), []).append(r)
    out = [
        "| 힘 N | 시도 | grip 감지 | 찌그러짐 | 미끄러짐 | 쥔 폭 mm (평균) |",
        "|---|---|---|---|---|---|",
    ]
    for force in sorted(by):
        rs = by[force]
        widths = [float(r["width_off_mm"]) for r in rs]
        out.append(
            f"| {force:g} | {len(rs)} | {sum(r['grip_detected'] == 'True' for r in rs)} | "
            f"{sum(r['dent'] == 'y' for r in rs)} | {sum(r['slip'] == 'y' for r in rs)} | "
            f"{sum(widths) / len(widths):.1f} |"
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ip", default="192.168.1.1")
    ap.add_argument("--port", type=int, default=502)
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="읽기 전용")
    st.add_argument("--watch", type=float, default=0, help="N초 동안 5 Hz 감시")
    mv = sub.add_parser("move", help="폭·힘 지정 이동")
    mv.add_argument("--width", type=float, required=True)
    mv.add_argument("--force", type=float, default=10.0)
    mv.add_argument("--yes", action="store_true")
    op = sub.add_parser("open", help="벌리기 (기본 90 mm = 사전 개방)")
    op.add_argument("--width", type=float, default=90.0)
    op.add_argument("--yes", action="store_true")
    gp = sub.add_parser("grip", help="박스 파지 시험 1회 + 결과 기록")
    gp.add_argument("--force", type=float, required=True, help="목표 힘 N (RG2 3~40)")
    gp.add_argument(
        "--target",
        type=float,
        default=40.0,
        help="목표 폭 mm. 박스 46 mm 보다 작게 둬야 힘으로 멈춘다",
    )
    gp.add_argument("--yes", action="store_true")
    sub.add_parser("summary", help="기록 요약 (연결 안 함)")
    args = ap.parse_args(argv)

    if args.cmd == "summary":
        with LOG.open(newline="") as f:
            print("\n".join(summarize(list(csv.DictReader(f)))))
        return 0

    g = RG2(args.ip, args.port)
    if args.cmd == "status":
        end = time.monotonic() + args.watch
        while True:
            print_snap(g.snapshot())
            if time.monotonic() >= end:
                return 0
            time.sleep(0.2)
    if args.cmd in ("move", "open"):
        force = getattr(args, "force", 10.0)
        confirm(f"폭 {args.width} mm, 힘 {force} N 으로 이동", args.yes)
        s, dt = g.move(args.width, force)
        print_snap(s)
        print(f"{dt:.2f} s")
        return 0
    # grip
    confirm(
        f"박스를 핑거 사이(46 mm 면)에 두었나? 힘 {args.force} N, 목표 폭 {args.target} mm",
        args.yes,
    )
    s, dt = g.move(args.target, args.force)
    print_snap(s)
    if not s["grip_detected"]:
        print("⚠ grip 감지 안 됨 — 목표 폭까지 닫혔다 (박스를 놓쳤거나 목표 폭이 박스보다 크다)")
    dent = input("박스가 찌그러졌나? [y/n] ").strip().lower()
    slip = input("손으로 살짝 당기거나 흔들 때 미끄러졌나? [y/n] ").strip().lower()
    note = input("메모 (Enter=없음)> ").strip()
    log_row(
        {
            "stamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "force_n": args.force,
            "target_mm": args.target,
            "width_mm": s["width_mm"],
            "width_off_mm": s["width_off_mm"],
            "grip_detected": s["grip_detected"],
            "time_s": round(dt, 2),
            "dent": dent,
            "slip": slip,
            "note": note,
        }
    )
    print(f"기록: {LOG}. 다음 시도 전에: python3 rg2_check.py open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
