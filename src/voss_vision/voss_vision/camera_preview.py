"""Read-only JPEG preview for the Web PC, using existing image and BoxTrack topics."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import cv2
import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from voss_msgs.msg import BoxTrack
from voss_vision.camera_frames import CameraFrames
from voss_vision.camera_render import load_seg_params, render_jpeg


def stamp_key(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


class CameraPreview(Node):
    def __init__(self):
        super().__init__("camera_preview")
        self.frames = CameraFrames()
        image_topic = self.declare_parameter("image_topic", "/camera/color/image_raw").value
        box_topic = self.declare_parameter("box_topic", "/voss/vision/box").value
        host = self.declare_parameter("host", "127.0.0.1").value
        port = self.declare_parameter("port", 8091).value
        # Fill % runs the box_tracker seg judgement once per served frame (about 5 Hz per open tab).
        fill_percent = self.declare_parameter("fill_percent", True).value
        seg_file = self.declare_parameter("seg_params_file", "").value or str(
            Path(get_package_share_directory("voss_vision")) / "config" / "box_tracker.yaml"
        )
        seg = load_seg_params(seg_file) if fill_percent else None
        self.create_subscription(Image, image_topic, self.on_image, qos_profile_sensor_data)
        self.create_subscription(BoxTrack, box_topic, self.on_box, qos_profile_sensor_data)
        frames = self.frames

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.split("?")[0] != "/frame.jpg":
                    self.send_error(404)
                    return
                snapshot = frames.snapshot()
                if snapshot is None:
                    self.send_error(503, "No fresh camera frame")
                    return
                try:
                    body = render_jpeg(*snapshot, seg=seg)
                except (ValueError, cv2.error):
                    self.send_error(503, "Camera frame cannot be decoded")
                    return
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.get_logger().info(
            f"Camera preview: http://{host}:{port}/frame.jpg, fill % "
            + (f"on ({seg_file})" if fill_percent else "off")
        )

    def on_image(self, message):
        self.frames.add_frame(stamp_key(message.header.stamp), message)

    def on_box(self, message):
        self.frames.add_box(stamp_key(message.stamp), message.track_id, message.bbox)

    def destroy_node(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CameraPreview()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
