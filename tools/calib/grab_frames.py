"""현장용: Enter 를 누를 때마다 /camera/color/image_raw 한 장을 PNG 로 저장 (ADR-0003 절차 4).

로봇을 움직이지 않는다. 카메라 노드만 떠 있으면 된다.
  source /opt/ros/jazzy/setup.bash
  python3 tools/calib/grab_frames.py --out ~/voss_calib --names C1 C2 C3 C4 C5 C6 V1 V2 V3
"""

import argparse
import threading
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def to_bgr(msg: Image) -> np.ndarray:
    """sensor_msgs/Image(rgb8·bgr8) → OpenCV BGR. cv_bridge 없이 동작."""
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    img = img[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else img.copy()


class Grabber(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("calib_grab_frames")
        self.latest: Image | None = None
        self.create_subscription(Image, topic, self._cb, qos_profile_sensor_data)

    def _cb(self, msg: Image) -> None:
        self.latest = msg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path.home() / "voss_calib")
    # voss_bringup 이 camera_namespace:='' 로 띄운다(#47). 기본 런치면 /camera/camera/color/image_raw
    ap.add_argument("--topic", default="/camera/color/image_raw")
    ap.add_argument("--width", type=int, default=1920, help="운용 해상도 폭 (MC-032: 1920x1080)")
    ap.add_argument(
        "--names", nargs="+", default=[f"C{i}" for i in range(1, 7)] + ["V1", "V2", "V3"]
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = Grabber(args.topic)
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    try:
        for name in args.names:
            input(f"[{name}] 박스를 {name} 자리에 놓고 Enter ")
            msg = node.latest
            if msg is None:
                print("  ! 아직 영상이 안 들어왔다. 카메라 노드·토픽 이름 확인")
                continue
            img = to_bgr(msg)
            path = args.out / f"{name}.png"
            cv2.imwrite(str(path), img)
            print(f"  저장 {path} ({img.shape[1]}x{img.shape[0]})")
            if img.shape[1] != args.width:
                print(
                    f"  ! 폭이 {args.width} 이 아니다 — 운용 해상도(1920x1080)와 같게 다시 띄울 것"
                )
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
