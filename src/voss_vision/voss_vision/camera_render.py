"""JPEG rendering without ROS dependencies, using boxes from the same frame."""

import cv2
import numpy as np

MAX_PREVIEW_WIDTH = 960
MAX_PREVIEW_HEIGHT = 540


def render_jpeg(message, boxes):
    if message.encoding not in ("rgb8", "bgr8"):
        raise ValueError("Preview requires rgb8 or bgr8")
    frame = np.frombuffer(message.data, dtype=np.uint8).reshape(message.height, message.step)
    frame = frame[:, : message.width * 3].reshape(message.height, message.width, 3)
    scale = min(1.0, MAX_PREVIEW_WIDTH / message.width, MAX_PREVIEW_HEIGHT / message.height)
    width = max(1, round(message.width * scale))
    height = max(1, round(message.height * scale))
    frame = (
        cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        if scale < 1
        else frame.copy()
    )
    if message.encoding == "rgb8":
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
            f"T{track_id}",
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
