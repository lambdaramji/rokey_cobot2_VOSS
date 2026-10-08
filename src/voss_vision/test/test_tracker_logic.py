"""tracker_logic — LabelCrop stage, 보류 트랙, 관측 자세 판정, 크롭 창, 전송 간격."""

import numpy as np
from voss_vision.belt_plane import rot_zyz_deg
from voss_vision.hand_eye import make_t
from voss_vision.tracker_logic import (
    CropGate,
    LoopStats,
    crop_window,
    hold_track_id,
    label_stage,
    near_observe,
    sharpness,
)


def test_label_stage_follows_sort_state_only_for_current_track() -> None:
    assert label_stage(7, "PICKING", 7) == 2
    assert label_stage(7, "RECHECK", 7) == 3
    assert label_stage(8, "PICKING", 7) == 1  # 다른 트랙
    assert label_stage(7, "RUNNING", 7) == 1
    assert label_stage(7, "", -1) == 1  # 상태 수신 전


def test_hold_only_while_picking() -> None:
    assert hold_track_id("PICKING", 7) == 7
    assert hold_track_id("RUNNING", 7) == -1
    assert hold_track_id("RECHECK", 7) == -1


def test_near_observe_tolerances() -> None:
    obs = make_t(rot_zyz_deg(85.25, -179.07, -6.03), [-14.49, -276.54, 203.58])
    assert near_observe(obs, obs)
    moved = obs.copy()
    moved[:3, 3] += [0.6, 0.6, 0.0]  # 0.85 mm
    assert near_observe(moved, obs)
    moved[:3, 3] += [0.5, 0.0, 0.0]  # 1.3 mm
    assert not near_observe(moved, obs)
    tilted = obs.copy()
    tilted[:3, :3] = obs[:3, :3] @ rot_zyz_deg(0, 0.8, 0)  # 공구축 0.8°
    assert not near_observe(tilted, obs)
    spun = obs.copy()
    spun[:3, :3] = obs[:3, :3] @ rot_zyz_deg(10, 0, 0)  # 공구축 둘레 회전은 축 방향 그대로
    assert near_observe(spun, obs)


def test_crop_window_margin_and_clipping() -> None:
    assert crop_window((100, 200, 100, 200), (1080, 1920, 3), 0.1) == (90, 180, 210, 420)
    assert crop_window((1900, 1000, 100, 200), (1080, 1920, 3), 0.1) == (1890, 980, 1920, 1080)
    assert crop_window((5000, 5000, 10, 10), (1080, 1920, 3)) is None


def test_sharpness_prefers_edges() -> None:
    flat = np.full((60, 60), 128, np.uint8)
    edges = flat.copy()
    edges[:, 30:] = 255
    assert sharpness(edges) > sharpness(flat)


def test_crop_gate_period_count_and_sharpness() -> None:
    g = CropGate(period_s=0.2, max_per_stage={1: 2, 2: 100}, min_sharpness=5.0)
    assert g.accept(1, 1, 0.0, 10.0)
    assert not g.accept(1, 1, 0.1, 10.0)  # 간격 안 됨
    assert not g.accept(1, 1, 0.3, 1.0)  # 흐림
    assert g.accept(1, 1, 0.3, 10.0)
    assert not g.due(1, 1, 1.0)  # stage 1 은 2장까지
    assert g.accept(1, 2, 1.0, 10.0)  # 단계가 바뀌면 따로 센다
    g.forget({2})
    assert g.due(1, 1, 1.0)  # 폐기된 트랙은 기록이 지워진다


def test_loop_stats_summary() -> None:
    s = LoopStats()
    assert s.summary(5.0) == "영상 0 프레임"
    for _ in range(150):
        s.add_frame(2.0, 5.0, 40.0)
    s.add_box("homography", True)
    s.add_box("none", False)
    text = s.summary(5.0)
    assert text.startswith("30.0 Hz") and "무효 1" and "homography 1" in text


def test_loop_stats_pose_lookup_counts() -> None:
    s = LoopStats()
    s.add_frame(2.0, 5.0, 40.0)
    s.add_pose(0.0)  # 보간
    s.add_pose(35.0)  # 35 ms 외삽
    s.add_pose(None)  # 실패
    text = s.summary(5.0)
    assert "pose 2·외삽 1(최대 35 ms)·실패 1" in text
    s.reset()
    s.add_frame(2.0, 5.0, 40.0)
    assert "pose" not in s.summary(5.0)  # pose 이력이 없으면(재생·관측 가정) 표시 안 함
