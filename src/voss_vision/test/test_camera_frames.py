from types import SimpleNamespace

import cv2
import numpy as np
from voss_vision.camera_frames import CameraFrames
from voss_vision.camera_render import render_jpeg


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
