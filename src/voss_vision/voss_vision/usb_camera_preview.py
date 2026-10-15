"""Nodes PC C270 USB 영상의 최신 JPEG를 localhost:8092로 제공한다 (음성 캡처 없음)."""

from __future__ import annotations

import argparse
import glob
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


def c270_device() -> str:
    matches = sorted(glob.glob("/dev/v4l/by-id/*C270*video-index0"))
    if not matches:
        raise RuntimeError("C270 영상 장치를 찾지 못했습니다 (/dev/v4l/by-id/*C270*video-index0)")
    return matches[0]


class Frames:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jpeg: bytes | None = None
        self.updated = 0.0

    def update(self, jpeg: bytes) -> None:
        with self.lock:
            self.jpeg = jpeg
            self.updated = time.monotonic()

    def snapshot(self) -> bytes | None:
        with self.lock:
            return self.jpeg if time.monotonic() - self.updated < 2.0 else None


def capture(device: str, frames: Frames, stop: threading.Event) -> None:
    cv2.setNumThreads(1)  # Nodes PC의 서보·비전 작업과 CPU 스레드를 경쟁하지 않게 한다.
    while not stop.is_set():
        camera = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not camera.isOpened():
            camera.release()
            stop.wait(2)
            continue
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_FPS, 10)  # 장치가 거부해도 grab/retrieve로 디코딩을 10 Hz 이하로 제한한다.
        next_encode = 0.0
        try:
            while not stop.is_set():
                ok = camera.grab()
                if not ok:
                    break
                now = time.monotonic()
                if now < next_encode:
                    continue
                ok, frame = camera.retrieve()
                if not ok:
                    break
                next_encode = now + 0.1
                encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
                if encoded:
                    frames.update(jpeg.tobytes())
        finally:
            camera.release()
        stop.wait(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=None, help="기본값: C270 video-index0 경로")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    device = args.device or c270_device()
    frames = Frames()
    stop = threading.Event()
    worker = threading.Thread(target=capture, args=(device, frames, stop), daemon=True)
    worker.start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/frame.jpg":
                self.send_error(404)
                return
            jpeg = frames.snapshot()
            if jpeg is None:
                self.send_error(503, "No fresh C270 frame")
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(jpeg)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"C270 preview: http://127.0.0.1:{args.port}/frame.jpg ({device})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    main()
