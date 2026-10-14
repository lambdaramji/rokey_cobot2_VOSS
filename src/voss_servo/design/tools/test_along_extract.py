"""along_extract 시험 (design/U13-tools-dd.md 4절 T1~T8). 실행: python3 -m pytest design/tools -q"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # 패키지 밖 도구 — 이 폴더에서 바로 import

import along_extract as ax  # noqa: E402

DATA = Path.home() / "cobot2/cobot2_voss_data/1012/ticks"  # 10/12 원본 (git 밖)
S2 = "37533e04 42279412 b095639f bc8927ae d37042c0 1b4cc5c7".split()  # 반듯한 박스 6회
S3 = "e89ef368 d1327f74 9ea23ba7 63344faa dc5f7141".split()

D = (1.0, 0.0)  # 시험용 벨트 방향 = +x


def fake_goal(v_box=46.9, v_ff=48.0, lead=2.0, close=True) -> list[dict]:
    """가짜 goal: 박스 v_box mm/s, TCP 는 사각 전 lead mm 하류·사각 뒤 v_ff mm/s.

    TRACK 0 s · DESCEND 5.0 s · 사각 5.5 s · CLOSE 명령 7.6 s · 응답 9.3 s · 끝 10.0 s.
    """
    rows = []
    t_blind = 5.5
    box0 = -88.0  # 시작 박스 x mm
    for i in range(301):
        t = i / 30.0  # 30 Hz
        box = box0 + v_box * t  # 박스 mm
        if t < t_blind:
            tcp = box + lead  # 사각 전: 박스보다 lead 만큼 하류
        else:
            tcp = box0 + v_box * t_blind + lead + v_ff * (t - t_blind)  # 사각 뒤: FF 로만
        phase = "TRACK" if t < 5.0 else "DESCEND" if t < 7.6 else "GRASP"
        blind = t >= t_blind
        row = {
            "goal_id": "abcdef0123",
            "t_calc_s": t,
            "phase": phase,
            "vision_blind": blind,
            "position_valid": not blind,
            "box_stamp_s": t if not blind else None,
            "position_base_m": [box / 1000.0, 0.0, 0.1008] if not blind else None,
            "pose_stamp_s": t,
            "tcp_pose_m": [tcp / 1000.0, 0.0, 0.14],
            "tcp_now_m": [tcp / 1000.0, 0.0, 0.14],
            "err_along_m": -lead / 1000.0,  # 로그 부호 = 박스 − TCP
            "belt_vel_mps": [v_ff / 1000.0, 0.0, 0.0],
            "belt_speed_mps": v_ff / 1000.0,
            "gripper": None,
            "reason": None,
            "grasped": None,
        }
        if close and abs(t - 9.3) < 1e-9:  # 닫기 응답 행
            row["gripper"] = {"kind": "CLOSE", "sent_s": 7.6, "rx_s": 9.3, "width_actual_mm": 40.9}
        rows.append(row)
    rows[-1].update(reason="OK", grasped=True)
    return rows


def test_t1_along_sign():
    """T1: 하류로 +, 기본 방향 크기."""
    assert ax.along_mm([1.0, 0.0], ax.BELT_DIR_DEFAULT) == pytest.approx(999.92)
    assert ax.along_mm([0.1, 0.0], D) > ax.along_mm([0.0, 0.0], D)


def test_t2_fit_line_exact():
    """T2: 정확한 직선은 그대로 복원."""
    t = ax.np.array([0.0, 1.0, 2.0, 3.0])
    slope, end, rms = ax.fit_line(t, 5.0 + 2.0 * t)
    assert slope == pytest.approx(2.0)
    assert end == pytest.approx(11.0)
    assert rms == pytest.approx(0.0, abs=1e-9)
    assert ax.fit_line(t[:1], t[:1]) is None


def test_t3_manual_y():
    """T3: 네 점 → y, 빈 칸 전파."""
    assert ax.manual_y(10.0, 40.0, 8.0, 54.0) == pytest.approx(-6.0)
    assert ax.manual_y(10.0, None, 8.0, 54.0) is None


def test_t4_reconstruct_fake_goal():
    """T4: 사각 전 +2.0, 사각 뒤 Δv 1.1 × (9.15 − 5.5) → y_con 6.015."""
    rows = fake_goal()
    ev, why = ax.find_events(rows)
    assert ev is not None, why
    rec = ax.reconstruct(rows, ev, refs=[46.9], kp=1.0)
    assert rec["v_box_track"] == pytest.approx(46.9, abs=1e-6)
    assert rec["v_tcp_blind"] == pytest.approx(48.0, abs=1e-6)
    assert rec["y_con"] == pytest.approx(2.0 + 1.1 * (9.15 - 5.5), abs=0.01)
    assert rec["y_cmd"] == pytest.approx(2.0 + 1.1 * (7.6 - 5.5), abs=0.01)
    assert rec["y_blind"] == pytest.approx(2.0, abs=0.01)
    assert rec["e_align"] == pytest.approx(2.0)
    assert rec["t_vis"] == pytest.approx(0.5, abs=0.04)  # 틱 양자화
    assert rec["y_con@46.9"] == pytest.approx(rec["y_con"], abs=1e-6)


def test_t5_no_close():
    """T5: 닫기 응답이 없는 goal 은 이유만."""
    ev, why = ax.find_events(fake_goal(close=False))
    assert ev is None
    assert why == "no CLOSE rx"


def test_t6_ols_exact():
    """T6: 정확한 직선 회귀."""
    f = ax.ols([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 5.0, 7.0])
    assert f["b"] == pytest.approx(1.0)
    assert f["k"] == pytest.approx(2.0)
    assert f["sd"] == pytest.approx(0.0, abs=1e-9)
    assert ax.ols([0.0, 1.0], [1.0, 2.0]) is None


def test_t7_attach_manual(tmp_path):
    """T7: b_phys = y_phys − y_con, b0 = b_phys − ℓ."""
    man = tmp_path / "m.csv"
    man.write_text("goal,box,p_front,p_back,b_front,b_back,y,note\nabcdef01,2,10,40,8,54,,\n")
    boxes = tmp_path / "b.csv"
    boxes.write_text("box,ell\n2,1.5\n")
    rec = {"goal": "abcdef01", "y_con": 3.0, "note": ""}
    ax.attach_manual(rec, ax.read_manual(man), ax.read_boxes(boxes))
    assert rec["y_phys"] == pytest.approx(-6.0)
    assert rec["b_phys"] == pytest.approx(-9.0)
    assert rec["b0"] == pytest.approx(-10.5)


@pytest.mark.skipif(not DATA.exists(), reason="10/12 원본 로그 없음 (개인 PC 전용)")
def test_t8_reproduce_1012():
    """T8: 기준 46.95 mm/s 의 y_con 평균 — s2 +6.26, s3 +3.02 (Fable 재구성)."""
    out = {}
    for name, fn, ids in (
        ("s2", "servo_ticks_20261012_180722.jsonl", S2),
        ("s3", "servo_ticks_20261012_190046.jsonl", S3),
    ):
        goals = ax.load_goals(DATA / fn)
        ys = []
        for gid in ids:
            ev, _ = ax.find_events(goals[gid])
            ys.append(ax.reconstruct(goals[gid], ev, refs=[46.95], kp=1.0)["y_con@46.95"])
        out[name] = sum(ys) / len(ys)
    assert out["s2"] == pytest.approx(6.26, abs=0.05)
    assert out["s3"] == pytest.approx(3.02, abs=0.05)


def test_t9_block_median_basis():
    """T9: 블록 중앙값을 주면 그 속도로 외삽하고, 회차 값은 진단 열·이상치 표시로 남는다."""
    rows = fake_goal(v_box=46.9)
    ev, _ = ax.find_events(rows)
    rec = ax.reconstruct(rows, ev, refs=[], kp=1.0, v0_block=47.3)
    assert rec["v0"] == pytest.approx(47.3)
    assert rec["y_con_run"] == pytest.approx(6.015, abs=0.01)  # 회차 값(46.9) 기준
    # 기울기 고정 절편은 마지막 20 관측의 평균 시각(끝 164/30 s − 19/60 s) 기준 → 외삽 길이 3.367 s
    t_mid = 164 / 30 - 19 / 60
    assert rec["y_con"] == pytest.approx(6.015 - 0.4 * (9.15 - t_mid), abs=0.01)
    assert rec["dv"] == pytest.approx(48.0 - 47.3, abs=1e-6)
    assert "off block median" in rec["note"]


def test_t10_retry_excluded():
    """T10: 재시도(attempt ≥ 2) 회차는 표시되고 요약에서 빠진다."""
    rows = fake_goal()
    rows[-1]["attempt"] = 2
    ev, _ = ax.find_events(rows)
    rec = ax.reconstruct(rows, ev, refs=[], kp=1.0)
    assert rec["note"].startswith("retry")
    assert ax.ok_recs([rec]) == []


def test_t11_contact_lead_regression():
    """T11: b_phys = 3 − 0.3·Δv 이면 ④ 의 절편 +3.00, 기울기 −0.30 (접촉이 0.3 s 이름)."""
    recs = []
    for i, dv in enumerate([-1.2, -0.9, 0.0, 0.6, 1.1]):
        recs.append(
            {
                "goal": f"g{i}",
                "grasped": True,
                "attempt": 1,
                "y_con": 1.0,
                "dv": dv,
                "close_s": 1.7,
                "b_phys": 3.0 - 0.3 * dv,
            }
        )
    rows = {r[0]: r for r in ax.fit_table(recs)}
    assert rows["④ b_phys ~ Δv (접촉 시각)"][2].startswith("+3.00")
    assert "-0.30" in rows["④ b_phys ~ Δv (접촉 시각)"][3]


def test_t12_contact_from_sent():
    """T12: --contact sent 이면 접촉 = 명령 7.6 + 1.38 = 8.98 s → y = 2.0 + 1.1 × (8.98 − 5.5)."""
    rows = fake_goal()
    ev, _ = ax.find_events(rows)
    rec = ax.reconstruct(rows, ev, refs=[], kp=1.0, contact="sent")
    assert rec["y_con"] == pytest.approx(2.0 + 1.1 * (7.6 + 1.38 - 5.5), abs=0.01)
