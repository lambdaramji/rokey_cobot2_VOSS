"""실제 USB 장치 없이 C270 캡처 부하·재연결·JPEG 재사용을 확인한다."""

import threading
from types import SimpleNamespace

from voss_vision import usb_camera_preview as preview


def test_capture_skips_decode_between_preview_frames(monkeypatch) -> None:
    stop = threading.Event()

    class Camera:
        grabs = 0
        retrieves = 0
        released = False
        settings = []

        def isOpened(self):
            return True

        def set(self, key, value):
            self.settings.append((key, value))
            return True

        def grab(self):
            self.grabs += 1
            if self.grabs == 4:
                stop.set()
            return True

        def retrieve(self):
            self.retrieves += 1
            return True, object()

        def release(self):
            self.released = True

    camera = Camera()
    threads, encoded = [], []
    monkeypatch.setattr(preview.cv2, "VideoCapture", lambda *_: camera)
    monkeypatch.setattr(preview.cv2, "setNumThreads", threads.append)
    monkeypatch.setattr(
        preview.cv2, "imencode", lambda *_: (True, SimpleNamespace(tobytes=lambda: b"jpeg"))
    )
    monkeypatch.setattr(preview.time, "monotonic", lambda: camera.grabs * 0.04)
    frames = SimpleNamespace(update=encoded.append)

    preview.capture("/dev/video-test", frames, stop)
    assert camera.grabs == 4 and camera.retrieves == 2
    assert encoded == [b"jpeg", b"jpeg"] and camera.released
    assert (preview.cv2.CAP_PROP_FPS, 10) in camera.settings
    assert threads == [1]


def test_capture_retries_unavailable_camera(monkeypatch) -> None:
    stop = threading.Event()
    opened = []

    class Camera:
        def isOpened(self):
            return False

        def release(self):
            opened.append("released")
            stop.set()

    monkeypatch.setattr(preview.cv2, "VideoCapture", lambda *_: Camera())
    monkeypatch.setattr(preview.cv2, "setNumThreads", lambda *_: None)
    preview.capture("/dev/video-test", preview.Frames(), stop)
    assert opened == ["released"]


def test_frames_reuse_latest_jpeg_until_stale(monkeypatch) -> None:
    clock = [10.0]
    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    frames = preview.Frames()
    assert frames.snapshot() is None
    frames.update(b"frame")
    assert frames.snapshot() == frames.snapshot() == b"frame"
    clock[0] = 12.1
    assert frames.snapshot() is None
