#!/usr/bin/env python3
"""goal 별 단계(PREPARE→TRACK→DESCEND→GRASP) TCP↔박스 중심 오차와 DESCEND 속도 분해 (읽기 전용).

박스 중심 = predicted_m (지금 시각으로 외삽한 박스 윗면 중심), TCP = tcp_now_m.
오차 = 박스 − TCP 를 벨트 방향(along, + = 박스가 하류/앞)·가로(cross, + = 베이스 +y 쪽)로 분해.
속도: 총 = cmd_vel_mps, FF = belt_vel_mps, P = 총 − FF (가속·속도 제한 효과 포함). 측정 = tcp_vel_meas_mps.
사용: phase_err.py <ticks.jsonl> [--series 4.73] [--ts 앞8자리]  (--ts 는 DESCEND 시계열 출력 goal)
"""
import json
import math
import statistics
import sys

D = (0.99992, -0.01292)
C = (-D[1], D[0])  # along 에 수직(+y 쪽)


def comp(v):
    return v[0] * D[0] + v[1] * D[1], v[0] * C[0] + v[1] * C[1]


def mm(x):
    return x * 1000.0


def load(path):
    goals = {}
    for line in open(path):
        r = json.loads(line)
        if r.get("goal_id") and r.get("tcp_now_m") and r.get("predicted_m"):
            goals.setdefault(r["goal_id"][:8], []).append(r)
    return goals


def tick_vals(r):
    box, tcp = r["predicted_m"], r["tcp_now_m"]
    e = (box[0] - tcp[0], box[1] - tcp[1])
    ea, ec = comp(e)
    out = {"t": r["t_calc_s"], "phase": r["phase"], "along": mm(ea), "cross": mm(ec),
           "dist": mm(math.hypot(*e)), "z_above_top": mm(tcp[2] - box[2]),
           "blind": bool(r.get("vision_blind")), "log_along": mm(r["err_along_m"]) if r.get("err_along_m") is not None else None}
    cmd, ff = r.get("cmd_vel_mps"), r.get("belt_vel_mps")
    if cmd and ff:
        ca, cc = comp(cmd)
        fa, fc = comp(ff)
        out.update(cmd_a=mm(ca), cmd_c=mm(cc), ff_a=mm(fa), ff_c=mm(fc), p_a=mm(ca - fa), p_c=mm(cc - fc), cmd_z=mm(cmd[2]))
    meas = r.get("tcp_vel_meas_mps")
    if meas:
        ma, mc = comp(meas)
        out.update(meas_a=mm(ma), meas_c=mm(mc))
    return out


def phase_table(gid, rows):
    vals = [tick_vals(r) for r in rows]
    print(f"\n### goal {gid}  (오차 mm: along +=박스가 TCP 보다 하류, cross +=+y 쪽, dist = xy 거리)")
    print("| 단계 | 시간 s | along 시작→끝 | cross 시작→끝 | dist 시작→끝 | |along| 최대 | 메모 |")
    print("|---|---|---|---|---|---|---|")
    for ph in ("PREPARE", "TRACK", "DESCEND", "GRASP"):
        v = [x for x in vals if x["phase"] == ph]
        if not v:
            continue
        memo = ""
        if ph == "DESCEND":
            b = next((x for x in v if x["blind"]), None)
            if b:
                memo = f"사각 진입 {b['t'] - v[0]['t']:.2f} s 뒤, z 윗면+{b['z_above_top']:.1f}"
        if ph in ("PREPARE", "TRACK"):
            memo = f"z 윗면+{v[0]['z_above_top']:.0f}→+{v[-1]['z_above_top']:.0f}"
        print(f"| {ph} | {v[-1]['t'] - v[0]['t']:.2f} | {v[0]['along']:+.1f} → {v[-1]['along']:+.1f} | "
              f"{v[0]['cross']:+.1f} → {v[-1]['cross']:+.1f} | {v[0]['dist']:.1f} → {v[-1]['dist']:.1f} | "
              f"{max(abs(x['along']) for x in v):.1f} | {memo} |")
    return vals


def descend_summary(gid, vals):
    v = [x for x in vals if x["phase"] == "DESCEND" and "cmd_a" in x]
    seen = [x for x in v if not x["blind"]]
    blind = [x for x in v if x["blind"]]

    def m(lst, k):
        return statistics.mean(x[k] for x in lst) if lst else float("nan")

    return {"goal": gid, "n": len(v),
            "ff_a": m(v, "ff_a"), "p_a_seen": m(seen, "p_a"), "p_a_blind": m(blind, "p_a"),
            "cmd_a": m(v, "cmd_a"), "meas_a": m([x for x in v if "meas_a" in x], "meas_a"),
            "p_c": m(v, "p_c"), "cmd_c": m(v, "cmd_c"), "along_start": v[0]["along"], "along_end": v[-1]["along"],
            "cross_start": v[0]["cross"], "cross_end": v[-1]["cross"]}


def descend_series(gid, vals, step=3):
    v = [x for x in vals if x["phase"] == "DESCEND"]
    t0 = v[0]["t"]
    print(f"\n### DESCEND 시계열 — goal {gid} (약 0.1 s 간격, 속도 mm/s, 오차 mm)")
    print("| t s | z 윗면+ | 보임 | along 오차 | cross 오차 | FF along | P along | **총 along** | 측정 along | P cross | 총 cross | 총 z |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, x in enumerate(v):
        if i % step and i != len(v) - 1:
            continue
        print(f"| {x['t'] - t0:.2f} | {x['z_above_top']:.1f} | {'사각' if x['blind'] else '봄'} | {x['along']:+.2f} | {x['cross']:+.2f} | "
              f"{x.get('ff_a', float('nan')):.2f} | {x.get('p_a', float('nan')):+.2f} | **{x.get('cmd_a', float('nan')):.2f}** | "
              f"{x.get('meas_a', float('nan')):.2f} | {x.get('p_c', float('nan')):+.2f} | {x.get('cmd_c', float('nan')):+.2f} | {x.get('cmd_z', float('nan')):+.1f} |")


def main(argv):
    path = argv[0]
    ts = argv[argv.index("--ts") + 1] if "--ts" in argv else None
    only = argv[argv.index("--goals") + 1].split(",") if "--goals" in argv else None
    goals = load(path)
    sums = []
    for gid, rows in goals.items():
        if only and gid not in only:
            continue
        if rows[-1].get("reason") not in (None, "OK") and not any(r["phase"] == "GRASP" for r in rows):
            continue
        vals = phase_table(gid, rows)
        sums.append(descend_summary(gid, vals))
        if ts and gid.startswith(ts):
            descend_series(gid, vals)
    print("\n### DESCEND 속도 분해 평균 (mm/s) — 총 = FF + P")
    print("| goal | FF along | P along (보일 때) | P along (사각) | 총 along | 측정 along | P cross | 총 cross | along 오차 시작→끝 | cross 오차 시작→끝 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in sums:
        print(f"| {s['goal']} | {s['ff_a']:.2f} | {s['p_a_seen']:+.2f} | {s['p_a_blind']:+.2f} | {s['cmd_a']:.2f} | {s['meas_a']:.2f} | "
              f"{s['p_c']:+.2f} | {s['cmd_c']:+.2f} | {s['along_start']:+.2f} → {s['along_end']:+.2f} | {s['cross_start']:+.2f} → {s['cross_end']:+.2f} |")


if __name__ == "__main__":
    main(sys.argv[1:])
