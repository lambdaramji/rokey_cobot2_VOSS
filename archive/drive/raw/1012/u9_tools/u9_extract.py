#!/usr/bin/env python3
"""U9 실기 s2 — belt_servo 로그에서 회차(goal)별 확인값을 뽑는다 (읽기 전용).

사용: python3 -I u9_extract.py [로그폴더=data/servo] [--file servo_ticks_X.jsonl] [--last N] [--goal 앞8자리]
가이드 4절의 값: 사각 진입 z(윗면 기준)·직전 obs_rx_age·GRASP 진입 err_along·후퇴·개방 응답·주기·벨트 추정.
"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path


def load(path):
    rows = []
    if path and path.exists():
        for line in path.open():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def mm(v):
    return None if v is None else round(v * 1000.0, 1)


def ts(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "-"


def summarize(gid, ticks, end_row):
    t0, t1 = ticks[0]["t_calc_s"], ticks[-1]["t_calc_s"]
    out = {"goal": gid[:8], "start": ts(t0), "end": ts(t1), "dur_s": round(t1 - t0, 2)}
    src = end_row or ticks[-1]
    for k in ("reason", "cause", "cause_fsm", "grasped", "attempt", "phase",
              "retreat_reason", "retreat_done", "retry_room_ok"):
        out[k] = src.get(k)
    # 윗면 z = 마지막 유효 관측의 박스 윗면 z
    top = None
    for r in ticks:
        p = r.get("position_base_m")
        if r.get("position_valid") and p:
            top = p[2]
    out["top_z_mm"] = mm(top)
    # 정렬(TRACK→DESCEND) 때 TCP x
    al = next((r for r in ticks if r.get("phase") == "DESCEND"), None)
    out["align_tcp_x_mm"] = mm(al["tcp_now_m"][0]) if al and al.get("tcp_now_m") else None
    # 사각 진입: vision_blind false→true
    for i in range(1, len(ticks)):
        if ticks[i].get("vision_blind") and not ticks[i - 1].get("vision_blind"):
            z = ticks[i]["tcp_now_m"][2] if ticks[i].get("tcp_now_m") else None
            out["blind_enter_tcp_z_mm"] = mm(z)
            out["blind_enter_above_top_mm"] = mm(z - top) if z is not None and top is not None else None
            out["blind_prev_obs_rx_age_s"] = ticks[i - 1].get("obs_rx_age_s")
            out["blind_phase"] = ticks[i].get("phase")
            break
    # DESCEND 중 LOST?
    out["lost_in_descend"] = any(r.get("box_lost") and r.get("phase") == "DESCEND" for r in ticks)
    # GRASP 진입 err_along
    g = next((i for i, r in enumerate(ticks) if r.get("phase") == "GRASP"), None)
    if g is not None:
        out["grasp_enter_err_along_mm"] = mm(ticks[g].get("err_along_m") or ticks[g - 1].get("err_along_m"))
        out["grasp_enter_tcp_mm"] = [mm(v) for v in ticks[g]["tcp_now_m"]] if ticks[g].get("tcp_now_m") else None
    # 단계별 시간
    phases = {}
    for r in ticks:
        phases.setdefault(r.get("phase"), [r["t_calc_s"], r["t_calc_s"]])[1] = r["t_calc_s"]
    out["phase_s"] = {k: round(v[1] - v[0], 2) for k, v in phases.items() if k}
    # 후퇴
    rt = [r for r in ticks if r.get("retreat")]
    if rt:
        withpos = [r for r in ticks if r.get("tcp_now_m")]
        z_end = withpos[-1]["tcp_now_m"][2]
        out["retreat_states"] = sorted({r["retreat"] for r in rt})
        out["retreat_s"] = round(withpos[-1]["t_calc_s"] - rt[0]["t_calc_s"], 2)
        out["fail_tcp_mm"] = [mm(v) for v in rt[0]["tcp_now_m"]] if rt[0].get("tcp_now_m") else None
        ris = [r for r in rt if r["retreat"] == "RISING"]
        out["opening_s"] = round(ris[0]["t_calc_s"] - rt[0]["t_calc_s"], 2) if ris and rt[0]["retreat"] == "OPENING" else 0.0
        out["rising_s"] = round(withpos[-1]["t_calc_s"] - ris[0]["t_calc_s"], 2) if ris else None
        out["retreat_xy_move_mm"] = [mm(withpos[-1]["tcp_now_m"][i] - rt[0]["tcp_now_m"][i]) for i in (0, 1)] if rt[0].get("tcp_now_m") else None
        out["min_z_after_fail_mm"] = mm(min(r["tcp_now_m"][2] for r in rt if r.get("tcp_now_m")))
        out["retreat_end_z_mm"] = mm(z_end)
        out["retreat_end_above_top_mm"] = mm(z_end - top) if top is not None else None
    # 그리퍼 호출 (kind·latency·폭)
    calls = {}
    for r in ticks:
        gr = r.get("gripper")
        if isinstance(gr, dict) and gr.get("latency_s") is not None:
            calls[(gr.get("kind"), gr.get("seq"))] = (round(gr["latency_s"], 3), gr.get("width_actual_mm"), gr.get("grip_detected"), gr.get("ok"))
    out["gripper"] = {f"{k[0]}#{k[1]}": v for k, v in calls.items()}
    # 끝 근처 TRACK (D: x 끝·z 처짐)
    tr = [r for r in ticks if r.get("phase") == "TRACK" and r.get("tcp_now_m") and r.get("tcp_target_m")]
    if tr:
        last = tr[-1]
        out["last_track_tcp_x_mm"] = mm(last["tcp_now_m"][0])
        out["last_track_z_err_mm"] = mm(last["tcp_now_m"][2] - last["tcp_target_m"][2])
    out["reach"] = next((r["reach"] for r in reversed(ticks) if r.get("reach")), None)
    # 주기
    dts = [b["t_calc_s"] - a["t_calc_s"] for a, b in zip(ticks, ticks[1:])]
    if dts:
        out["period_ms"] = {"median": round(statistics.median(dts) * 1000, 1),
                            "max": round(max(dts) * 1000, 1),
                            "out_of_30_36": sum(1 for d in dts if not 0.0303 <= d <= 0.0363)}
    out["belt_speed_est_mps"] = src.get("belt_speed_est_mps")
    out["stall_ticks_max"] = max((r.get("stall_ticks") or 0) for r in ticks)
    return out


def main(argv):
    base = Path("data/servo")
    file = None
    last = 3
    goal = None
    it = iter(argv)
    for a in it:
        if a == "--file":
            file = next(it)
        elif a == "--last":
            last = int(next(it))
        elif a == "--goal":
            goal = next(it)
        else:
            base = Path(a)
    tick_files = sorted((base / "ticks").glob("servo_ticks_*.jsonl"))
    tf = (base / "ticks" / file) if file else (tick_files[-1] if tick_files else None)
    if not tf:
        print("틱 로그 없음")
        return
    af = base / "attempts" / tf.name.replace("servo_ticks_", "servo_attempts_")
    ticks, atts = load(tf), load(af)
    ends = {r["goal_id"]: r for r in atts if r.get("event") == "GOAL_END"}
    goals = {}
    for r in ticks:
        if r.get("goal_id"):
            goals.setdefault(r["goal_id"], []).append(r)
    ids = list(goals)
    if goal:
        ids = [g for g in ids if g.startswith(goal)]
    else:
        ids = ids[-last:]
    print(f"# {tf.name}  (attempts: {'있음' if atts else '없음'}, goals {len(goals)})")
    for gid in ids:
        print(json.dumps(summarize(gid, goals[gid], ends.get(gid)), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
