#!/usr/bin/env python3
"""닫힘 순간 벨트 방향 오프셋 y 를 belt_servo 틱 로그에서 회차별로 뽑는다 (U13 #31, 읽기 전용).

y = TCP − 박스 중심 (벨트 방향, mm). + = TCP 가 하류(박스 앞쪽을 잡음).
설계: design/U13-tools-dd.md · 측정 설계: design/U13-belt-along.md. ROS 없이 python3 + numpy.

사용: python3 along_extract.py <servo_ticks_*.jsonl …> [--goals 앞8,앞8] [--manual 자측정.csv]
      [--boxes 박스.csv] [--v-ref 47.3 …] [--kp 1.0] [--csv 출력.csv]
      [--contact rx|sent] [--v0 block|run]
기준 박스 속도(--v0 block)는 같은 설정 묶음(config_sha, params_sha — 시간상 떨어진 블록도 한 묶음)의 중앙값.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BELT_DIR_DEFAULT = (0.99992, -0.01292)  # voss_config belt.direction_base (로그에 없을 때)
K_LAST_OBS = 20  # 박스 절편에 쓰는 사각 직전 관측 수
MIN_OBS = 5  # 절편에 필요한 최소 관측 수
TRACK_SETTLE_S = 1.5  # 추종 중 박스 속도: TRACK 시작 + 이 시간 뒤 관측만
MIN_TRACK_OBS = 10  # 추종 중 박스 속도에 필요한 최소 관측 수
CONTACT_LEAD_S = (
    0.15  # 접촉 ≈ 닫기 응답 rx − 0.15 s (U13 2.3, 1부 가정 — 기본값 유지: 10/13 기록과 같은 정의)
)
CONTACT_FROM_SENT_S = (
    1.38  # 접촉 ≈ 닫기 명령 + 1.38 s (U13 2부 B: RG2 무부하 개방 37회 속도로 49.5 mm 행정)
)
V_OFF_FLAG = 0.2  # 회차 박스 속도가 블록 중앙값에서 이만큼(mm/s) 넘게 벗어나면 표시 (1부 재검 #3)


# ───────────────────────── 읽기 ─────────────────────────


def load_goals(path: Path) -> dict[str, list[dict]]:
    """JSONL 틱 로그 → {goal_id 앞 8자리: 행 목록(파일 순서)}. 깨진 줄은 건너뛴다."""
    goals: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()  # 빈 줄·줄바꿈 제거
            if not line:
                continue
            try:
                row = json.loads(line)  # 한 줄 = 한 틱
            except json.JSONDecodeError:
                continue  # 쓰다 끊긴 마지막 줄 등
            gid = row.get("goal_id")
            if gid:
                goals.setdefault(gid[:8], []).append(row)  # goal 별로 모은다
    return goals


def belt_dir(rows: list[dict]) -> tuple[float, float]:
    """벨트 방향 단위 벡터 (x, y). 로그의 belt_vel_mps(제어에 쓴 FF 벡터)에서, 없으면 기본값."""
    for row in rows:
        v = row.get("belt_vel_mps")
        if v and math.hypot(v[0], v[1]) > 0:
            n = math.hypot(v[0], v[1])  # 수평 크기
            return (v[0] / n, v[1] / n)
    return BELT_DIR_DEFAULT


def along_mm(p: list[float], d: tuple[float, float]) -> float:
    """베이스 좌표 점(m) 의 벨트 방향 성분 (mm). 하류로 갈수록 커진다."""
    return (p[0] * d[0] + p[1] * d[1]) * 1000.0


# ───────────────────────── 사건 ─────────────────────────


@dataclass
class Events:
    """한 goal 의 시각·결과 (s, mm, mm/s)."""

    t_track: float | None
    t_descend: float | None
    t_blind: float
    t_grasp: float | None
    close_sent: float
    close_rx: float
    width_mm: float | None
    grip: bool | None
    reason: str | None
    grasped: bool | None
    attempt: int | None  # 마지막 시도 번호 (1 = 첫 시도, 2 이상 = 재시도)
    ff_mmps: float | None
    config_sha: str | None
    params_sha: str | None
    e_align_mm: float | None  # 첫 DESCEND 행의 TCP − 박스 (= −err_along)
    align_x_mm: float | None  # 그 행의 TCP x
    start_box_x_mm: float | None  # 첫 유효 관측의 박스 x


def first_time(rows: list[dict], phase: str) -> float | None:
    """그 phase 가 처음 나온 행의 t_calc_s."""
    return next((r["t_calc_s"] for r in rows if r.get("phase") == phase), None)


def last_close(rows: list[dict]) -> dict | None:
    """응답(rx)이 있는 마지막 CLOSE 그리퍼 기록 (재시도면 마지막 시도)."""
    found = None
    for r in rows:
        g = r.get("gripper")
        if isinstance(g, dict) and g.get("kind") == "CLOSE" and g.get("rx_s"):
            found = g  # 뒤에 나온 것이 이긴다
    return found


def blind_entry(rows: list[dict]) -> float | None:
    """vision_blind 가 false → true 로 바뀐 첫 시각 (사각 진입)."""
    for prev, cur in zip(rows, rows[1:], strict=False):
        if cur.get("vision_blind") and not prev.get("vision_blind"):
            return cur["t_calc_s"]
    return None


def find_events(rows: list[dict]) -> tuple[Events | None, str]:
    """한 goal 의 사건을 찾는다. 재구성에 필요한 것이 없으면 (None, 이유)."""
    close = last_close(rows)
    if close is None:
        return None, "no CLOSE rx"  # LOST·OUT_OF_REACH 등 닫기 전에 끝남
    t_blind = blind_entry(rows)
    if t_blind is None:
        return None, "no blind entry"
    last = rows[-1]  # 결과가 실린 마지막 행
    desc = next((r for r in rows if r.get("phase") == "DESCEND"), None)  # 정렬 순간
    obs = next((r for r in rows if r.get("position_valid") and r.get("position_base_m")), None)
    speed = last.get("belt_speed_mps")
    ev = Events(
        t_track=first_time(rows, "TRACK"),
        t_descend=first_time(rows, "DESCEND"),
        t_blind=t_blind,
        t_grasp=first_time(rows, "GRASP"),
        close_sent=close["sent_s"],
        close_rx=close["rx_s"],
        width_mm=close.get("width_actual_mm"),
        grip=close.get("grip_detected"),
        reason=last.get("reason"),
        grasped=last.get("grasped"),
        attempt=last.get("attempt"),
        ff_mmps=speed * 1000.0 if speed is not None else None,  # m/s → mm/s
        config_sha=last.get("config_sha256"),
        params_sha=last.get("params_sha256"),
        e_align_mm=(-desc["err_along_m"] * 1000.0)
        if desc and desc.get("err_along_m") is not None
        else None,  # 로그는 박스 − TCP → 부호 반전
        align_x_mm=desc["tcp_now_m"][0] * 1000.0 if desc and desc.get("tcp_now_m") else None,
        start_box_x_mm=obs["position_base_m"][0] * 1000.0 if obs else None,
    )
    return ev, ""


# ───────────────────────── 재구성 ─────────────────────────


def obs_series(rows: list[dict], t_end: float, d) -> tuple[np.ndarray, np.ndarray]:
    """사각 진입 전 유효 관측 (촬영 시각 s, 벨트 방향 mm). 같은 BoxTrack 은 한 번만."""
    pts: dict[float, float] = {}
    for r in rows:
        stamp = r.get("box_stamp_s")
        ok = r.get("position_valid") and not r.get("vision_blind") and r.get("position_base_m")
        if ok and stamp and r["t_calc_s"] < t_end:
            pts[stamp] = along_mm(r["position_base_m"], d)  # 같은 stamp 는 덮어써도 같은 값
    t = np.array(sorted(pts))
    return t, np.array([pts[k] for k in t])


def pose_series(rows: list[dict], d) -> tuple[np.ndarray, np.ndarray]:
    """수신 TCP pose (pose stamp s, 벨트 방향 mm). 같은 pose 는 한 번만."""
    pts: dict[float, float] = {}
    for r in rows:
        stamp = r.get("pose_stamp_s")
        if stamp and r.get("tcp_pose_m"):
            pts[stamp] = along_mm(r["tcp_pose_m"], d)
    t = np.array(sorted(pts))
    return t, np.array([pts[k] for k in t])


def fit_line(t: np.ndarray, s: np.ndarray) -> tuple[float, float, float] | None:
    """최소제곱 직선 s = 끝값 + 기울기·(t − t[-1]) → (기울기, t[-1] 에서의 값, rms)."""
    if len(t) < 2:
        return None
    x = t - t[-1]  # 끝 시각 기준 (큰 epoch 값으로 정밀도 잃지 않게)
    slope, end = np.polyfit(x, s, 1)
    rms = float(np.sqrt(np.mean((s - (end + slope * x)) ** 2)))  # 직선에서 벗어난 정도
    return float(slope), float(end), rms


def box_intercept(t: np.ndarray, s: np.ndarray, slope: float) -> float:
    """기울기를 고정했을 때 t[-1] 시각의 박스 위치 (점들의 평균 절편)."""
    return float(np.mean(s - slope * (t - t[-1])))


def band_tail_pred(e_align: float, dv: float, t_vis: float, kp: float) -> float:
    """사각 진입 순간 y 예측: 정렬 띠에서 출발해 Kp 로 e_ss 쪽으로 줄어든 값 (U13 2.2)."""
    e_ss = dv / kp  # 정상상태 오차 (FF 가 빠르면 + = TCP 하류)
    return e_ss + (e_align - e_ss) * math.exp(-kp * t_vis)


def track_speed(ot: np.ndarray, os_: np.ndarray, ev: Events) -> float | None:
    """추종 중 박스 속도 mm/s: TRACK 이 자리 잡은 뒤 ~ 사각 전 (카메라가 박스를 따라감 → 스케일 편향 작음)."""
    if len(ot) == 0:
        return None
    t0 = (ev.t_track or ot[0]) + TRACK_SETTLE_S
    m = ot > t0
    fit = fit_line(ot[m], os_[m]) if m.sum() >= MIN_TRACK_OBS else None
    return fit[0] if fit else None


def goal_track_speed(rows: list[dict], ev: Events) -> float | None:
    """한 goal 의 추종 중 박스 속도 (블록 중앙값을 먼저 구할 때 쓴다)."""
    ot, os_ = obs_series(rows, ev.t_blind, belt_dir(rows))
    return track_speed(ot, os_, ev)


def block_key(ev: Events) -> tuple:
    """같은 설정으로 돈 회차 묶음(블록) = (config_sha, params_sha)."""
    return (ev.config_sha, ev.params_sha)


def reconstruct(
    rows: list[dict],
    ev: Events,
    refs: list[float],
    kp: float,
    v0_block: float | None = None,
    contact: str = "rx",
) -> dict:
    """한 goal → 회차 1행 dict. 관측이 모자라면 y 칸은 None 이고 note 에 이유.

    기준 박스 속도 v0 = 블록 중앙값(v0_block, 기본) → 없으면 회차 값 → 없으면 refs[0].
    회차 값으로 본 y 는 진단 열 y_con_run 에 남긴다 (1부 재검 #3: 회차 값은 이상치에 약하다).
    """
    d = belt_dir(rows)
    rec = base_record(rows, ev)
    ot, os_ = obs_series(rows, ev.t_blind, d)  # 사각 전 박스
    pt, ps = pose_series(rows, d)  # TCP
    if len(ot) < MIN_OBS or len(pt) < 2:
        rec["note"] = f"obs < {MIN_OBS}"
        return rec
    v_box = track_speed(ot, os_, ev)  # 이 회차의 추종 중 박스 속도
    # 사각 진입 ~ 닫기 응답 동안의 TCP 속도 (FF 만으로 가는 구간)
    mb = (pt >= ev.t_blind) & (pt <= ev.close_rx)
    tcp_fit = fit_line(pt[mb], ps[mb]) if mb.sum() >= 3 else None
    v_tcp = tcp_fit[0] if tcp_fit else None
    rec.update(v_box_track=v_box, v_tcp_blind=v_tcp)
    tl, sl = ot[-K_LAST_OBS:], os_[-K_LAST_OBS:]  # 사각 직전 관측

    def y_at(t: float, v: float) -> float:
        """시각 t 의 TCP − 박스 (박스는 기울기 v 로 외삽)."""
        box = box_intercept(tl, sl, v) + v * (t - tl[-1])
        return float(np.interp(t, pt, ps)) - box

    v0 = v0_block if v0_block is not None else v_box  # 기준 속도: 블록 중앙값 우선
    if v0 is None:
        v0 = refs[0] if refs else None
    if v0 is None:
        rec["note"] = "no box speed"
        return rec
    rec["v0"] = v0
    rec["dv"] = v_tcp - v0 if v_tcp is not None else None  # 회귀에 쓰는 Δv 도 같은 기준
    if v_box is not None and v0_block is not None and abs(v_box - v0_block) > V_OFF_FLAG:
        flag = f"v_box {v_box - v0_block:+.2f} off block median"  # 이상치 표시
        rec["note"] = (rec["note"] + " " + flag).strip()  # retry 표시를 덮지 않게
    if contact == "sent":  # 접촉 = 명령 + 1.38 s (2부 판정)
        t_con = ev.close_sent + CONTACT_FROM_SENT_S
    else:  # 접촉 = 응답 − 0.15 s (1부 가정, 기본)
        t_con = ev.close_rx - CONTACT_LEAD_S
    if v_box is not None:
        rec["y_con_run"] = y_at(t_con, v_box)  # 진단: 회차 값 기준
    rec.update(
        y_cmd=y_at(ev.close_sent, v0),
        y_con=y_at(t_con, v0),
        y_rx=y_at(ev.close_rx, v0),
        y_blind=y_at(ev.t_blind, v0),
        t_blind_con=t_con - ev.t_blind,  # 사각 진입 → 접촉
    )
    if ev.e_align_mm is not None and ev.t_descend is not None and ev.ff_mmps is not None:
        t_vis = ev.t_blind - ev.t_descend  # 정렬 → 사각 (P 가 꼬리를 줄이는 시간)
        rec["y_blind_pred"] = band_tail_pred(ev.e_align_mm, ev.ff_mmps - v0, t_vis, kp)
    for v in refs:
        rec[f"y_con@{v:g}"] = y_at(t_con, v)  # 다른 기준 속도로 본 같은 회차
    return rec


def base_record(rows: list[dict], ev: Events) -> dict:
    """재구성 전 공통 칸 (사건에서 바로 나오는 값)."""
    t_vis = ev.t_blind - ev.t_descend if ev.t_descend is not None else None
    return {
        "goal": rows[0]["goal_id"][:8],
        "ff_cmps": ev.ff_mmps / 10.0 if ev.ff_mmps is not None else None,  # mm/s → cm/s
        "config_sha": ev.config_sha,
        "params_sha": ev.params_sha,
        "reason": ev.reason,
        "grasped": ev.grasped,
        "start_box_x": ev.start_box_x_mm,
        "align_x": ev.align_x_mm,
        "e_align": ev.e_align_mm,
        "t_vis": t_vis,
        "blind_rx": ev.close_rx - ev.t_blind,
        "close_s": ev.close_rx - ev.close_sent,
        "width": ev.width_mm,
        "attempt": ev.attempt,
        "note": "retry" if (ev.attempt or 1) > 1 else "",  # 재시도 회차는 요약에서 뺀다 (재검 #18)
    }


# ───────────────────────── 합치기 (손 측정) ─────────────────────────


def to_float(v: str | None) -> float | None:
    """CSV 칸 → float. 비었으면 None."""
    if v is None or str(v).strip() == "":
        return None
    return float(v)


def manual_y(pf, pb, bf, bb) -> float | None:
    """자 네 점 → y = 패드 중심 − 박스 중심 (자 눈금이 하류로 커질 때)."""
    if None in (pf, pb, bf, bb):
        return None
    return (pf + pb) / 2.0 - (bf + bb) / 2.0


def read_manual(path: Path) -> dict[str, dict]:
    """자 측정 CSV (goal, box, p_front, p_back, b_front, b_back, y, note) → {goal8: dict}."""
    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = (row.get("goal") or "").strip()[:8]
            if not gid:
                continue
            pts = [to_float(row.get(k)) for k in ("p_front", "p_back", "b_front", "b_back")]
            y = to_float(row.get("y"))
            out[gid] = {
                "box": (row.get("box") or "").strip(),
                "y_phys": y if y is not None else manual_y(*pts),  # y 칸이 우선
                "mnote": (row.get("note") or "").strip(),
            }
    return out


def read_boxes(path: Path) -> dict[str, float]:
    """박스 CSV (box, ell) → {박스 ID: 송장 오프셋 mm (+ = 송장이 박스 앞쪽)}."""
    with open(path, newline="", encoding="utf-8") as f:
        return {
            r["box"].strip(): float(r["ell"])
            for r in csv.DictReader(f)
            if r.get("box") and to_float(r.get("ell")) is not None
        }


def attach_manual(rec: dict, manual: dict[str, dict], boxes: dict[str, float]) -> None:
    """회차 dict 에 y_phys · b_phys(= y_phys − y_con) · ℓ · b0(= b_phys − ℓ) 를 붙인다."""
    m = manual.get(rec["goal"])
    if not m:
        return
    rec["box"] = m["box"]
    rec["y_phys"] = m["y_phys"]
    if m["mnote"]:
        rec["note"] = (rec.get("note", "") + " " + m["mnote"]).strip()
    if m["y_phys"] is not None and rec.get("y_con") is not None:
        rec["b_phys"] = m["y_phys"] - rec["y_con"]  # 로그가 못 보는 상수 (핸드아이·송장·패드)
        ell = boxes.get(m["box"])
        rec["ell"] = ell
        if ell is not None:
            rec["b0"] = rec["b_phys"] - ell  # 송장 성분을 뺀 나머지


# ───────────────────────── 요약 ─────────────────────────


def ols(x, y) -> dict | None:
    """y = 절편 + 기울기·x 최소제곱 + 표준오차. 점 < 3 이면 None."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 3 or np.ptp(x) == 0:
        return None
    a = np.vstack([np.ones(n), x]).T
    beta, *_ = np.linalg.lstsq(a, y, rcond=None)
    resid = y - a @ beta
    s2 = float(resid @ resid) / (n - 2)  # 잔차 분산
    cov = s2 * np.linalg.inv(a.T @ a)
    return {
        "b": float(beta[0]),
        "k": float(beta[1]),
        "se_b": math.sqrt(cov[0, 0]),
        "se_k": math.sqrt(cov[1, 1]),
        "sd": math.sqrt(s2),
        "n": n,
    }


def ok_recs(recs: list[dict]) -> list[dict]:
    """요약에 쓰는 회차: 쥐었고 y 가 계산됐고 첫 시도인 것."""
    return [
        r
        for r in recs
        if r.get("grasped") and r.get("y_con") is not None and (r.get("attempt") or 1) <= 1
    ]


def mean_sd(vals: list[float]) -> str:
    """'평균 ± 모표준편차' 문자열 (값 없으면 '-')."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return "-"
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return f"{statistics.mean(vals):+.2f} ± {sd:.2f}"


def level_table(recs: list[dict]) -> list[list[str]]:
    """FF 수준별 n · y_con · y_phys · b_phys · b0."""
    levels: dict[float, list[dict]] = {}
    for r in ok_recs(recs):
        levels.setdefault(round(r["ff_cmps"], 2), []).append(r)
    rows = []
    for ff in sorted(levels):
        rs = levels[ff]
        rows.append(
            [
                f"{ff:.2f}",
                str(len(rs)),
                mean_sd([r["y_con"] for r in rs]),
                mean_sd([r.get("y_phys") for r in rs]),
                mean_sd([r.get("b_phys") for r in rs]),
                mean_sd([r.get("b0") for r in rs]),
                mean_sd([r.get("v_box_track") for r in rs]),
            ]
        )
    return rows


def fit_table(recs: list[dict]) -> list[list[str]]:
    """회귀: ① 로그 y ~ Δv ② 자 y ~ Δv ③ 사각 진입 y ~ 정렬 띠 꼬리 예측(모형 검증)
    ④ b_phys ~ Δv (접촉 시각) ⑤ b_phys ~ Δv·닫기 시간 (미끄러짐/접촉 지연 구분).

    사각 뒤 구간은 TCP 가 FF 로, 박스가 기준 속도로 외삽되므로 정의상 Δv·시간이 더해질 뿐이다.
    로그로 검증할 수 있는 것은 사각 진입까지(정렬 띠 꼬리) — ③ 이 k ≈ 1, 절편 ≈ 0 이면 맞다.
    """
    rs = [r for r in ok_recs(recs) if r.get("dv") is not None]
    out = []
    lines = [
        ("① y_con ~ Δv (로그)", [r["dv"] for r in rs], [r["y_con"] for r in rs], "c s"),
        (
            "② y_phys ~ Δv (자)",
            [r["dv"] for r in rs if r.get("y_phys") is not None],
            [r["y_phys"] for r in rs if r.get("y_phys") is not None],
            "c s",
        ),
        (
            "③ 사각 y ~ 꼬리 예측 (모형 검증)",
            [r["y_blind_pred"] for r in rs if r.get("y_blind_pred") is not None],
            [r["y_blind"] for r in rs if r.get("y_blind_pred") is not None],
            "k",
        ),
    ]
    bp = [r for r in rs if r.get("b_phys") is not None]
    lines += [
        # 접촉이 가정(rx − 0.15)보다 L 초 이르면 b_phys = 상수 − L·Δv → 기울기 = −L (재검 #10)
        ("④ b_phys ~ Δv (접촉 시각)", [r["dv"] for r in bp], [r["b_phys"] for r in bp], "−L s"),
        # 닫힘이 길수록 커지는 효과(미끄러짐·접촉 지연)면 Δv·닫힘 시간에 더 잘 맞는다
        (
            "⑤ b_phys ~ Δv·닫기 s",
            [r["dv"] * r["close_s"] for r in bp],
            [r["b_phys"] for r in bp],
            "k",
        ),
    ]
    for name, x, y, kname in lines:
        f = ols(x, y)
        if f:
            out.append(
                [
                    name,
                    str(f["n"]),
                    f"{f['b']:+.2f} ± {f['se_b']:.2f}",
                    f"{kname} {f['k']:.2f} ± {f['se_k']:.2f}",
                    f"{f['sd']:.2f}",
                ]
            )
    return out


# ───────────────────────── 출력 ─────────────────────────

RUN_COLS = [
    ("goal", "goal", "{}"),
    ("ff_cmps", "FF", "{:.2f}"),
    ("reason", "결과", "{}"),
    ("start_box_x", "시작 박스 x", "{:.0f}"),
    ("align_x", "정렬 x", "{:.0f}"),
    ("t_vis", "t_vis", "{:.2f}"),
    ("blind_rx", "사각→rx", "{:.2f}"),
    ("close_s", "닫기 s", "{:.2f}"),
    ("width", "폭", "{:.1f}"),
    ("v_box_track", "v_box", "{:.2f}"),
    ("v0", "v0", "{:.2f}"),
    ("dv", "Δv", "{:+.2f}"),
    ("e_align", "정렬 y", "{:+.2f}"),
    ("y_blind", "사각 y", "{:+.2f}"),
    ("y_blind_pred", "사각 y 예측", "{:+.2f}"),
    ("y_cmd", "y_cmd", "{:+.2f}"),
    ("y_con", "**y_con**", "{:+.2f}"),
    ("y_rx", "y_rx", "{:+.2f}"),
    ("y_con_run", "y_con(회차 v)", "{:+.2f}"),
    ("box", "박스", "{}"),
    ("y_phys", "y_phys", "{:+.1f}"),
    ("b_phys", "b_phys", "{:+.2f}"),
    ("ell", "ℓ", "{:+.1f}"),
    ("b0", "b0", "{:+.2f}"),
    ("note", "메모", "{}"),
]


def fmt(v, spec: str) -> str:
    """None·빈 값은 '-', 아니면 형식대로."""
    if v is None or v == "":
        return "-"
    try:
        return spec.format(v)
    except (ValueError, TypeError):
        return str(v)


def md_table(head: list[str], rows: list[list[str]]) -> str:
    """마크다운 표 문자열."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def run_table(recs: list[dict], refs: list[float]) -> str:
    """회차표 (기준 속도 열 포함)."""
    cols = list(RUN_COLS)
    at = [c[0] for c in cols].index("y_con") + 1  # y_con 바로 뒤에 기준 속도 열
    cols[at:at] = [(f"y_con@{v:g}", f"y_con@{v:g}", "{:+.2f}") for v in refs]
    head = [c[1] for c in cols]
    rows = [[fmt(r.get(k), spec) for k, _, spec in cols] for r in recs]
    return md_table(head, rows)


def write_csv(recs: list[dict], path: Path) -> None:
    """회차 dict 전부를 CSV 로 (2부·measurements 용)."""
    keys: list[str] = []
    for r in recs:
        keys += [k for k in r if k not in keys]  # 처음 나온 순서
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(recs)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령줄 인자."""
    p = argparse.ArgumentParser(description="닫힘 순간 벨트 방향 오프셋 (y + = TCP 하류)")
    p.add_argument("ticks", nargs="+", type=Path, help="servo_ticks_*.jsonl")
    p.add_argument("--goals", default="", help="goal_id 앞 8자리, 쉼표로 (비우면 전부)")
    p.add_argument("--manual", type=Path, help="자 측정 CSV")
    p.add_argument("--boxes", type=Path, help="박스 송장 오프셋 CSV")
    p.add_argument("--v-ref", type=float, action="append", default=[], help="기준 박스 속도 mm/s")
    p.add_argument("--kp", type=float, default=1.0, help="control.kp_per_s (꼬리 예측용)")
    p.add_argument(
        "--contact",
        choices=("rx", "sent"),
        default="rx",
        help="접촉 시각: rx = 응답 − 0.15 s(기본, 10/13 기록 정의) | sent = 명령 + 1.38 s(2부 판정)",
    )
    p.add_argument(
        "--v0",
        choices=("block", "run"),
        default="block",
        help="기준 박스 속도: 블록 중앙값|회차 값",
    )
    p.add_argument("--csv", type=Path, help="회차표 CSV 출력 경로")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """회차표 · 수준표 · 회귀표를 출력한다. 입력 오류면 2."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    wanted = {g.strip()[:8] for g in args.goals.split(",") if g.strip()}
    recs: list[dict] = []
    found: list[tuple] = []  # (goal8, rows, ev 또는 None, 이유)
    try:
        for path in args.ticks:
            for gid, rows in load_goals(path).items():
                if wanted and gid not in wanted:
                    continue
                ev, why = find_events(rows)
                found.append((gid, rows, ev, why))
        # 1차: 블록(같은 설정)별 추종 중 박스 속도 중앙값
        speeds: dict[tuple, list[float]] = {}
        for _, rows, ev, _ in found:
            v = goal_track_speed(rows, ev) if ev and (ev.attempt or 1) <= 1 else None
            if v is not None:
                speeds.setdefault(block_key(ev), []).append(v)
        median = {k: statistics.median(v) for k, v in speeds.items()}
        # 2차: 블록 중앙값을 기준으로 재구성 (--v0 run 이면 회차 값)
        for gid, rows, ev, why in found:
            if ev is None:
                recs.append({"goal": gid, "reason": rows[-1].get("reason"), "note": why})
                continue
            v0b = median.get(block_key(ev)) if args.v0 == "block" else None
            recs.append(reconstruct(rows, ev, args.v_ref, args.kp, v0b, args.contact))
        manual = read_manual(args.manual) if args.manual else {}
        boxes = read_boxes(args.boxes) if args.boxes else {}
    except OSError as exc:
        print(f"입력 파일 오류: {exc}", file=sys.stderr)
        return 2
    for gid in sorted(set(manual) - {r["goal"] for r in recs}):
        print(f"경고: 자 측정 goal {gid} 가 로그에 없음", file=sys.stderr)
    for r in recs:
        attach_manual(r, manual, boxes)
    basis = "블록 중앙값" if args.v0 == "block" else "회차 값"
    print(f"## 회차 (y + = TCP 하류, mm · 기준 v0 = 추종 중 박스 속도 {basis})\n")
    print(run_table(recs, args.v_ref))
    print("\n## FF 수준별 (쥔 회차만)\n")
    head = ["FF cm/s", "n", "y_con", "y_phys", "b_phys", "b0", "v_box mm/s"]
    print(md_table(head, level_table(recs)))
    fits = fit_table(recs)
    if fits:
        print("\n## 회귀\n")
        print(md_table(["식", "n", "절편 mm", "기울기", "잔차 sd"], fits))
    if args.csv:
        write_csv(recs, args.csv)
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
