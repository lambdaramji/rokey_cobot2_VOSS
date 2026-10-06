#!/usr/bin/env python3
"""10/06 실측 #1 — 벨트 속도: 아두이노 설정값별 cm/s 표.

방법(권장 순): 휴대폰 영상 프레임 → 스톱워치. 벨트 프레임에 테이프로 두 표시(A, B)를 붙이고
그 사이 거리 D 를 줄자로 잰다(권장 800 mm). 박스 앞 모서리가 A → B 를 지나는 시간을 잰다.

    python3 measure_belt_speed.py trial --setting 300 --distance 800
        → 시도마다 '8.12'(초) 또는 'f487@60'(프레임@fps) 입력, 빈 줄로 끝
    python3 measure_belt_speed.py video clip.mp4 --setting 300 --distance 800
        → 영상에서 A·B 통과 프레임을 키로 찍는다 (a/d ±1, j/l ±10, 1=A, 2=B, s=저장, q=끝)
    python3 measure_belt_speed.py table [--target 5]
        → 설정값-속도 표(마크다운)와 추천 설정값
    python3 measure_belt_speed.py serial --port /dev/ttyACM0
        → 아두이노 시리얼 터미널 (보내는 줄·받는 줄 모두 로그). 프로토콜 확인용

판정: 평균 ≤ 10 cm/s, 시도 간 편차 ±5% 이내 (SR-HW-04).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import statistics
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))
CSV_PATH = DATA_DIR / "belt_speed.csv"
FIELDS = ["stamp", "setting", "distance_mm", "seconds", "method", "cmps", "note"]
LIMIT_CMPS, TOL = 10.0, 0.05


def parse_trial(text: str) -> tuple[float, str]:
    """'8.12' → (8.12, 'stopwatch'), 'f487@60' → (487/60, 'frames')."""
    t = text.strip().lower()
    if t.startswith("f"):
        frames, fps = t[1:].split("@")
        return float(frames) / float(fps), "frames"
    return float(t), "stopwatch"


def speed_cmps(distance_mm: float, seconds: float) -> float:
    return distance_mm / seconds / 10.0


def stats(speeds: list[float]) -> dict:
    m = statistics.fmean(speeds)
    dev = max(abs(s - m) / m for s in speeds) if m else 0.0
    return {
        "n": len(speeds),
        "mean": m,
        "sd": statistics.stdev(speeds) if len(speeds) > 1 else 0.0,
        "max_dev": dev,
        "ok_limit": m <= LIMIT_CMPS,
        "ok_stable": dev <= TOL,
    }


def table_lines(rows: list[dict], target: float | None = None) -> list[str]:
    by: dict[str, list[float]] = {}
    for r in rows:
        by.setdefault(r["setting"], []).append(float(r["cmps"]))

    def key(s):
        try:
            return (0, float(s))
        except ValueError:
            return (1, s)

    out = [
        "| 아두이노 설정값 | 실측 cm/s (평균) | 시도 | 최대 편차 | 비고 |",
        "|---|---|---|---|---|",
    ]
    best = None
    for s in sorted(by, key=key):
        st = stats(by[s])
        note = []
        if not st["ok_limit"]:
            note.append("10 cm/s 초과")
        if not st["ok_stable"]:
            note.append("편차 ±5% 초과")
        if st["n"] < 3:
            note.append("3회 미만")
        out.append(
            f"| {s} | {st['mean']:.2f} | {st['n']} | ±{st['max_dev'] * 100:.1f}% | {', '.join(note)} |"
        )
        if target is not None and st["ok_limit"] and st["ok_stable"]:
            if best is None or abs(st["mean"] - target) < abs(best[1] - target):
                best = (s, st["mean"])
    if target is not None:
        out.append("")
        out.append(
            f"목표 {target} cm/s 에 가장 가까운 합격 설정값: {best[0]} ({best[1]:.2f} cm/s)"
            if best
            else "합격(≤10 cm/s, ±5%) 설정값이 아직 없다"
        )
    return out


def append(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def report(setting: str, rows: list[dict]) -> None:
    if not rows:
        return
    st = stats([r["cmps"] for r in rows])
    print(
        f"\n설정값 {setting}: 평균 {st['mean']:.2f} cm/s, sd {st['sd']:.2f}, 최대 편차 ±{st['max_dev'] * 100:.1f}% "
        f"→ {'≤10 OK' if st['ok_limit'] else '10 초과'} / {'±5% OK' if st['ok_stable'] else '±5% 초과'}"
    )


def make_row(setting, distance, seconds, method, note="") -> dict:
    return {
        "stamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "setting": setting,
        "distance_mm": distance,
        "seconds": round(seconds, 4),
        "method": method,
        "cmps": round(speed_cmps(distance, seconds), 3),
        "note": note,
    }


def cmd_trial(a) -> int:
    rows = []
    print(
        f"설정값 {a.setting}, 거리 {a.distance} mm. 시도 입력 ('8.12' 또는 'f487@60'), 빈 줄로 끝"
    )
    while True:
        t = input(f"  시도 {len(rows) + 1}> ").strip()
        if not t:
            break
        try:
            sec, method = parse_trial(t)
        except ValueError:
            print("  형식: 8.12  또는  f487@60")
            continue
        rows.append(make_row(a.setting, a.distance, sec, method, a.note))
        print(f"    {rows[-1]['cmps']:.2f} cm/s")
    append(rows)
    report(a.setting, rows)
    return 0


def cmd_video(a) -> int:
    import cv2

    cap = cv2.VideoCapture(a.file)
    if not cap.isOpened():
        raise SystemExit(f"영상을 못 연다: {a.file}")
    fps = a.fps or cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"{a.file}: {n} 프레임, {fps:.3f} fps (휴대폰 가변 fps 면 --fps 로 고정값을 준다)")
    print("a/d ±1  j/l ±10  ,/. ±100  1=A 통과  2=B 통과  s=시도 저장  q=끝")
    i, mark_a, mark_b, rows = 0, None, None, []
    win = "belt"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok:
            txt = f"frame {i}/{n - 1}  A={mark_a}  B={mark_b}  saved={len(rows)}"
            cv2.putText(frame, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            cv2.imshow(win, frame)
        k = cv2.waitKey(0) & 0xFF
        step = {
            ord("a"): -1,
            ord("d"): 1,
            ord("j"): -10,
            ord("l"): 10,
            ord(","): -100,
            ord("."): 100,
        }
        if k in step:
            i = min(max(0, i + step[k]), n - 1)
        elif k == ord("1"):
            mark_a = i
        elif k == ord("2"):
            mark_b = i
        elif k == ord("s") and mark_a is not None and mark_b is not None and mark_b > mark_a:
            sec = (mark_b - mark_a) / fps
            rows.append(
                make_row(
                    a.setting, a.distance, sec, f"video{fps:.2f}", f"{a.file}:{mark_a}-{mark_b}"
                )
            )
            print(
                f"  시도 {len(rows)}: {mark_b - mark_a} 프레임 = {sec:.3f} s → {rows[-1]['cmps']:.2f} cm/s"
            )
            mark_a = mark_b = None
        elif k == ord("q"):
            break
    cv2.destroyAllWindows()
    append(rows)
    report(a.setting, rows)
    return 0


def cmd_table(a) -> int:
    with CSV_PATH.open(newline="") as f:
        print("\n".join(table_lines(list(csv.DictReader(f)), a.target)))
    return 0


def cmd_serial(a) -> int:
    import threading

    import serial

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = (DATA_DIR / f"arduino_{datetime.datetime.now():%H%M%S}.log").open("a")
    try:
        port = serial.Serial(a.port, a.baud, timeout=0.2)
    except serial.SerialException as e:
        raise SystemExit(f"{e}\n권한 문제면: sudo usermod -aG dialout $USER 후 다시 로그인") from e
    print(f"{a.port} @ {a.baud}. 줄 입력 → 전송, Ctrl+C 로 끝. 로그: {log.name}")
    print("주의: 포트를 열면 보드가 리셋될 수 있다(벨트가 멈추거나 기본 속도로 돌아감)")
    stop = threading.Event()

    def rx():
        while not stop.is_set():
            line = port.readline()
            if line:
                s = line.decode(errors="replace").rstrip()
                print(f"< {s}")
                log.write(f"{datetime.datetime.now():%H:%M:%S.%f} < {s}\n")
                log.flush()

    threading.Thread(target=rx, daemon=True).start()
    try:
        while True:
            s = input()
            port.write((s + a.eol).encode())
            log.write(f"{datetime.datetime.now():%H:%M:%S.%f} > {s}\n")
            log.flush()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        port.close()
        log.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trial")
    t.add_argument("--setting", required=True, help="아두이노 설정값 (그대로 문자열로 기록)")
    t.add_argument("--distance", type=float, default=800.0, help="표시 A–B 거리 mm")
    t.add_argument("--note", default="")
    v = sub.add_parser("video")
    v.add_argument("file")
    v.add_argument("--setting", required=True)
    v.add_argument("--distance", type=float, default=800.0)
    v.add_argument("--fps", type=float, default=None)
    tb = sub.add_parser("table")
    tb.add_argument("--target", type=float, default=None, help="개발 기준 속도 cm/s (예: 5)")
    s = sub.add_parser("serial")
    s.add_argument("--port", default="/dev/ttyACM0")
    s.add_argument("--baud", type=int, default=115200)
    s.add_argument("--eol", default="\n", help="줄 끝 문자 (아두이노 스케치에 맞춘다)")
    a = ap.parse_args(argv)
    return {"trial": cmd_trial, "video": cmd_video, "table": cmd_table, "serial": cmd_serial}[
        a.cmd
    ](a)


if __name__ == "__main__":
    sys.exit(main())
