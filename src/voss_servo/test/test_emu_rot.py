"""S2-T18 에뮬레이터 직접 시험 도구 emu_rot 의 순수 함수 (ROS·에뮬레이터 없이)."""

import pytest

from voss_servo import emu_rot as er


def test_plans_match_run_md_modes() -> None:
    """모드별 지령: E3′ 30°/s 1 s, E8① 90°/s, E8② 30°/s 끝까지, E8③ 60→1, E8④ 40° 뒤 끊김, E5 60°/s 0.9 s."""
    assert er.make_plan("pure", 1) == er.Plan("pure", 30.0, 1.0, 0.0)
    assert er.make_plan("over", -1).w1 == -90.0
    lim = er.make_plan("limit", 1)
    assert lim.t1 is None and lim.w2 == 0.0
    crawl = er.make_plan("crawl", -1)
    assert (crawl.w1, crawl.w2) == (-60.0, -1.0)
    cut = er.make_plan("cut", 1)
    assert cut.until_rel == 40.0 and not cut.publish_after
    assert er.make_plan("brake", 1, stop=True).stop_call
    with pytest.raises(ValueError):
        er.make_plan("spin", 1)


def test_rel_angle_wraps_past_180() -> None:
    """− 방향은 −88.7 − 100 = −188.7° 로 ±180 을 넘는다 → 감아서 상대각 (재검 B8)."""
    assert er.rel_deg(-88.72, -88.72) == pytest.approx(0.0)
    assert er.rel_deg(171.3, -88.72) == pytest.approx(-99.98, abs=0.01)  # = −188.7 를 감은 값
    assert er.rel_deg(11.28, -88.72) == pytest.approx(100.0)
    assert er.wrap_deg(180.0) == pytest.approx(180.0) and er.wrap_deg(-180.0) == pytest.approx(
        180.0
    )


def test_guard_expectations_match_review_table() -> None:
    """gateway 감속 각 = v²/2α + v·watchdog → 30°/s 자름 ≈89·정지 ≈94, 60°/s 자름 ≈68·정지 ≈88 (재검 B8)."""
    c30 = er.guard_cut_rel(30.0, 90.0, 0.2, 100.0)
    assert c30 == pytest.approx(89.0)
    assert er.stop_rel_after_cut(30.0, 90.0, c30) == pytest.approx(94.0)
    c60 = er.guard_cut_rel(-60.0, 90.0, 0.2, 100.0)
    assert c60 == pytest.approx(68.0)
    assert er.stop_rel_after_cut(60.0, 90.0, c60) == pytest.approx(88.0)


def test_measured_w_and_crawl_switch() -> None:
    """값이 바뀐 두 pose 차분, 0.15 s 넘게 그대로면 0. crawl 은 측정이 지령의 80 % 아래면 전환."""
    assert er.measured_w(None, 1.0, 0.0) is None
    assert er.measured_w((0.0, 0.0), 0.6, 0.02) == pytest.approx(30.0)
    assert er.measured_w((10.0, 1.0), 10.0, 1.05) is None  # 그대로지만 아직 짧다
    assert er.measured_w((10.0, 1.0), 10.0, 1.2) == 0.0  # 오래 그대로 = 정지
    assert not er.crawl_switch(None, 60.0)
    assert not er.crawl_switch(55.0, 60.0) and er.crawl_switch(-40.0, -60.0)


def test_summary_tcp_shift_and_after_angle() -> None:
    """요약: TCP xy 이동(E3′), 상대각 최대, 지령 끝 뒤 더 돈 각(E5·E8 참고 기록)."""
    rows = [
        {"t": 0.0, "yaw_deg": -88.72, "w_dps": None, "x_mm": 0.0, "y_mm": 0.0},
        {"t": 1.0, "yaw_deg": -58.72, "w_dps": 30.0, "x_mm": 1.0, "y_mm": 3.0},
        {"t": 2.0, "yaw_deg": -55.72, "w_dps": 0.0, "x_mm": 1.5, "y_mm": 3.0},
    ]
    s = er.summarize(rows, -88.72, cmd_end_t=1.0)
    assert s["rel_peak_deg"] == pytest.approx(33.0) and s["rel_last_deg"] == pytest.approx(33.0)
    assert s["tcp_dxy_mm"] == pytest.approx((1.5**2 + 3.0**2) ** 0.5)
    assert s["after_cmd_deg"] == pytest.approx(3.0) and s["w_meas_max_dps"] == pytest.approx(30.0)
    assert er.summarize([], 0.0, None) == {"rows": 0}


def test_args_defaults() -> None:
    """기본값 = 관측 자세 −88.72°·한계 100°·α 90·watchdog 0.2 (gateway 기본과 같음)."""
    a = er.parse_args(["limit", "--dir", "-1"])
    assert (a.mode, a.dir, a.center_deg, a.limit_deg, a.alpha, a.watchdog) == (
        "limit",
        -1,
        -88.72,
        100.0,
        90.0,
        0.2,
    )
