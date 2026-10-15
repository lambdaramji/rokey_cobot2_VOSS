"""JPEG rendering without ROS dependencies, using boxes from the same frame."""

from pathlib import Path

import cv2
import numpy as np
import yaml

from voss_vision.box_detect import SegParams, detect_candidates

MAX_PREVIEW_WIDTH = 960
MAX_PREVIEW_HEIGHT = 540
# A track and a passing label candidate within this many source pixels are the same box
# (same value as tools/vision/box_overlay.py).
MATCH_PX = 40
SEG_KEYS = tuple(SegParams.__dataclass_fields__)


def load_seg_params(path):
    """box_tracker seg.* from its parameter file, so fill % is judged as the tracker does."""
    params = yaml.safe_load(Path(path).read_text())["box_tracker"]["ros__parameters"]
    seg = params.get("seg", {})
    base = SegParams()
    return SegParams(
        **{k: type(getattr(base, k))(seg[k]) for k in SEG_KEYS if k in seg and k != "box_scale"}
    )


def fill_by_track(bgr, boxes, seg):
    """track_id -> label fill (contour / rotated rect area, box_detect score), None if unmatched.

    This is the seg pass/fail value (fill_min), not a learned confidence."""
    passed = [c for c in detect_candidates(bgr, seg)[1] if c.det is not None]
    fills = {}
    for track_id, (x, y, w, h) in boxes.items():
        u, v = x + w / 2, y + h / 2
        best, best_d = None, MATCH_PX
        for c in passed:
            d = float(np.hypot(c.det.u - u, c.det.v - v))
            if d <= best_d:
                best, best_d = c, d
        fills[track_id] = None if best is None else best.fill
    return fills


def box_label(track_id, fills):
    if fills is None:
        return f"T{track_id}"
    fill = fills.get(track_id)
    return f"T{track_id} " + ("-%" if fill is None else f"{fill * 100:.0f}%")


def render_jpeg(message, boxes, seg=None):
    """seg: SegParams to print each box's fill %, None to draw track numbers only."""
    if message.encoding not in ("rgb8", "bgr8"):
        raise ValueError("Preview requires rgb8 or bgr8")
    frame = np.frombuffer(message.data, dtype=np.uint8).reshape(message.height, message.step)
    frame = frame[:, : message.width * 3].reshape(message.height, message.width, 3)
    fills = None
    if seg is not None:
        # Detection thresholds are in source pixels, so judge the full-size frame.
        if message.encoding == "rgb8":
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        fills = fill_by_track(frame, boxes, seg) if boxes else {}
    scale = min(1.0, MAX_PREVIEW_WIDTH / message.width, MAX_PREVIEW_HEIGHT / message.height)
    width = max(1, round(message.width * scale))
    height = max(1, round(message.height * scale))
    frame = (
        cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        if scale < 1
        else frame.copy()
    )
    if message.encoding == "rgb8" and seg is None:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    scale_x = width / message.width
    scale_y = height / message.height
    for track_id, (x, y, w, h) in boxes.items():
        left, top = max(0, round(x * scale_x)), max(0, round(y * scale_y))
        right = min(width - 1, round((x + w) * scale_x))
        bottom = min(height - 1, round((y + h) * scale_y))
        if w <= 0 or h <= 0 or right <= left or bottom <= top:
            continue
        cv2.rectangle(frame, (left, top), (right, bottom), (70, 230, 100), 2)
        cv2.putText(
            frame,
            box_label(track_id, fills),
            (left, max(16, top - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (70, 230, 100),
            2,
        )
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return jpeg.tobytes()
