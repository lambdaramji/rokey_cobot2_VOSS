"""Bounded, timestamp-matched preview storage. No ROS dependencies."""

import time
from collections import OrderedDict
from threading import Lock


class CameraFrames:
    def __init__(self, capacity=10, stale_s=1.0, delay_s=0.2):
        self.capacity, self.stale_s, self.delay_s = capacity, stale_s, delay_s
        self.frames = OrderedDict()
        self.boxes = OrderedDict()
        self.lock = Lock()

    def add_frame(self, stamp, frame, now=None):
        with self.lock:
            self.frames[stamp] = (time.monotonic() if now is None else now, frame)
            while len(self.frames) > self.capacity:
                self.frames.popitem(last=False)

    def add_box(self, stamp, track_id, bbox):
        with self.lock:
            self.boxes.setdefault(stamp, {})[track_id] = tuple(bbox)
            while len(self.boxes) > self.capacity:
                self.boxes.popitem(last=False)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            # Short delay gives detection time to arrive; never overlay a different frame.
            for stamp, (received, frame) in reversed(self.frames.items()):
                age = now - received
                if self.delay_s <= age <= self.stale_s:
                    return frame, dict(self.boxes.get(stamp, {}))
        return None
