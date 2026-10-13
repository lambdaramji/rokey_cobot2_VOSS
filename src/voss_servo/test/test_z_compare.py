"""z_compare 순수 함수 시험 (DD 7절 N16, 재검 M4)."""

import pytest

from voss_servo import z_compare as zc

T0 = 1000.0


def goal_end(gid: str, profile, reason="OK", attempt=1, desc=2.6, **over) -> dict:
    """GOAL_END 행: PREPARE 0 → TRACK 1 → DESCEND 4 → GRASP 4+desc → LIFT +1.7 → VERIFY +2.7 → 끝 +0.2."""
    t = T0
    g = t + 4.0 + desc
    row = {
        "kind": "attempt",
        "event": "GOAL_END",
        "goal_id": gid,
        "reason": reason,
        "attempt": attempt,
        "phase_t_prepare_s": t,
        "phase_t_track_s": t + 1.0,
        "phase_t_descend_s": t + 4.0,
        "phase_t_grasp_s": g,
        "phase_t_lift_s": g + 1.7,
        "phase_t_verify_s": g + 4.4,
        "t_calc_s": g + 4.6,
    }
    if profile is not None:
        row["z_profile"] = profile
    row.update(over)
    return row


def test_phase_durations_and_missing_phase() -> None:
    d = zc.phase_durations(goal_end("a", "p"))
    assert d["PREPARE"] == pytest.approx(1.0) and d["DESCEND"] == pytest.approx(2.6)
    assert d["LIFT"] == pytest.approx(2.7) and d["VERIFY"] == pytest.approx(0.2)
    lost = zc.phase_durations(
        goal_end("b", "p", phase_t_grasp_s=None, phase_t_lift_s=None, phase_t_verify_s=None)
    )
    assert lost["GRASP"] is None and lost["DESCEND"] == pytest.approx(2.6 + 4.6)  # 끝까지


def test_summarize_ok_only_and_old_rows_are_p() -> None:
    rows = [
        goal_end("a", None),  # 옛 로그 = p
        goal_end("b", "p", reason="LOST", desc=0.3),  # 실패는 단계 시간에 안 섞인다
        goal_end("c", "trapezoid", desc=1.6),
    ]
    st = zc.summarize(rows, None)
    assert st["p"].goals == 2 and st["p"].ok == 1 and st["p"].reasons["LOST"] == 1
    assert st["p"].phase_s["DESCEND"] == [pytest.approx(2.6)]
    assert st["trapezoid"].phase_s["DESCEND"] == [pytest.approx(1.6)]


def test_total_uses_first_attempt_start() -> None:
    first = {"event": "ATTEMPT_END", "goal_id": "r", "phase_t_prepare_s": T0 - 5.0}
    end = goal_end("r", "p", attempt=2)  # 마지막 시도 PREPARE = T0
    st = zc.summarize([first, end], None)
    assert st["p"].total_s == [pytest.approx(end["t_calc_s"] - (T0 - 5.0))]
    assert st["p"].retried == 1


def test_landing_and_table() -> None:
    ticks = {
        "c": [
            {
                "kind": "tick",
                "goal_id": "c",
                "phase": "DESCEND",
                "tcp_target_m": [0, 0, 0.0818],
                "t_calc_s": 1,
            },
            {
                "kind": "tick",
                "goal_id": "c",
                "phase": "GRASP",
                "tcp_pose_m": [0, 0, 0.0795],
                "err_along_m": -0.002,
                "t_calc_s": 2,
            },
        ]
    }
    assert zc.landing(ticks["c"]) == (pytest.approx(79.5), pytest.approx(81.8))
    st = zc.summarize([goal_end("a", "p"), goal_end("c", "trapezoid", desc=1.6)], ticks)
    assert st["trapezoid"].land_mm == [pytest.approx(-2.3)]
    md = zc.format_md(st)
    assert "| DESCEND s | 2.60 [2.60~2.60] | 1.60 [1.60~1.60] | -1.00 |" in md
    assert "| 착지 z < 80 mm (되돌림) | 0 | 1 |" in md
