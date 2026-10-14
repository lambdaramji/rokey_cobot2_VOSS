from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from voss_vision.camera_frames import CameraFrames
from voss_vision.camera_render import box_label, fill_by_track, load_seg_params, render_jpeg

CONFIG = Path(__file__).resolve().parents[1] / "config" / "box_tracker.yaml"


def test_boxes_only_match_their_own_frame():
    frames = CameraFrames()
    frames.add_frame(10, "first", now=0)
    frames.add_frame(11, "second", now=0.1)
    frames.add_box(10, 7, [1, 2, 3, 4])
    assert frames.snapshot(now=0.25) == ("first", {7: (1, 2, 3, 4)})
    assert frames.snapshot(now=0.35) == ("second", {})


def test_missing_and_stale_frames_are_not_shown():
    frames = CameraFrames()
    assert frames.snapshot(now=0) is None
    frames.add_frame(1, "frame", now=0)
    assert frames.snapshot(now=0.1) is None
    assert frames.snapshot(now=1.01) is None


def test_buffers_are_bounded_and_multiple_boxes_preserved():
    frames = CameraFrames(capacity=2)
    for i in range(3):
        frames.add_frame(i, i, now=0)
        frames.add_box(i, 1, [0, 0, 5, 5])
    frames.add_box(2, 2, [10, 10, 5, 5])
    assert len(frames.frames) == len(frames.boxes) == 2
    assert 0 not in frames.frames and 0 not in frames.boxes
    assert frames.snapshot(now=0.3) == (2, {1: (0, 0, 5, 5), 2: (10, 10, 5, 5)})


def test_default_buffer_keeps_ten_frames():
    frames = CameraFrames()
    for i in range(11):
        frames.add_frame(i, i, now=0)
    assert len(frames.frames) == 10
    assert 0 not in frames.frames


def test_preview_resizes_frame_and_matching_box_together():
    pixels = np.zeros((720, 1280, 3), dtype=np.uint8)
    message = SimpleNamespace(
        encoding="bgr8", height=720, width=1280, step=1280 * 3, data=pixels.tobytes()
    )
    jpeg = render_jpeg(message, {3: (200, 100, 200, 100)})
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (540, 960, 3)
    assert image[150, 225, 1] > 150  # bottom edge of the scaled matching box


def _belt_with_label():
    """Green belt with one white 160x100 label (40:25) at centre (640, 360)."""
    bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
    bgr[:] = (40, 160, 40)
    bgr[310:410, 560:720] = 255
    return bgr


def test_fill_percent_matches_the_label_under_the_track():
    seg = load_seg_params(CONFIG)
    bgr = _belt_with_label()
    fills = fill_by_track(bgr, {3: (548, 302, 184, 116), 4: (100, 100, 50, 50)}, seg)
    # a solid rectangle is ~1.0; contour vs rotated rect at downscale 2 can land a little above
    assert fills[3] == pytest.approx(1.0, abs=0.05)
    assert fills[4] is None  # no passing label near this track
    assert box_label(3, fills) == f"T3 {fills[3] * 100:.0f}%"
    assert box_label(4, fills) == "T4 -%"
    assert box_label(3, None) == "T3"


def test_preview_with_fill_percent_keeps_size_and_rgb_input():
    seg = load_seg_params(CONFIG)
    rgb = cv2.cvtColor(_belt_with_label(), cv2.COLOR_BGR2RGB)
    message = SimpleNamespace(
        encoding="rgb8", height=720, width=1280, step=1280 * 3, data=rgb.tobytes()
    )
    jpeg = render_jpeg(message, {3: (548, 302, 184, 116)}, seg=seg)
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (540, 960, 3)
    assert image[20, 20, 1] > image[20, 20, 0]  # belt stays green (RGB converted once)


def test_seg_params_follow_the_box_tracker_file():
    seg = load_seg_params(CONFIG)
    assert seg.fill_min == 0.8
    assert seg.area_min == 6000
    assert seg.belt_roi == "hull"
