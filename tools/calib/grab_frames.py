"""현장용: Enter 를 누를 때마다 /camera/color/image_raw 한 장을 PNG 로 저장 (ADR-0003 절차 4).

로봇을 움직이지 않는다. 카메라 노드만 떠 있으면 된다.
  source /opt/ros/jazzy/setup.bash
  python3 tools/calib/grab_frames.py --out ~/voss_calib --names C1 C2 C3 C4 C5 C6 V1 V2 V3

- Enter 를 누른 **뒤에** 들어온 프레임만 저장한다(박스를 옮기기 전 장면이 저장되지 않게).
- 영상이 안 오면 건너뛰지 않고 같은 이름을 다시 묻는다.
- 첫 camera_info 를 camera_info.yaml 로 저장한다(fit_belt_homography.py 가 왜곡 보정에 쓴다).
- q + Enter 또는 Ctrl+C 로 끝낸다.
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
import yaml
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image

WAIT_S = 2.0  # Enter 뒤 새 프레임을 기다리는 시간


def to_bgr(msg: Image) -> np.ndarray:
    """sensor_msgs/Image(rgb8·bgr8) → OpenCV BGR. cv_bridge 없이 동작."""
    if msg.encoding not in ("rgb8", "bgr8"):
        raise ValueError(f"인코딩 {msg.encoding} 미지원 — rgb8/bgr8 로 띄울 것")
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    img = img[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else img.copy()


class Grabber(Node):
    def __init__(self, topic: str, info_topic: str) -> None:
        super().__init__("calib_grab_frames")
        self.latest: Image | None = None
        self.seq = 0  # 받은 프레임 수. Enter 이후 새 프레임인지 가르는 데 쓴다
        self.info: CameraInfo | None = None
        self.create_subscription(Image, topic, self._cb, qos_profile_sensor_data)
        self.create_subscription(CameraInfo, info_topic, self._info_cb, qos_profile_sensor_data)

    def _cb(self, msg: Image) -> None:
        self.latest = msg
        self.seq += 1

    def _info_cb(self, msg: CameraInfo) -> None:
        if self.info is None:
            self.info = msg

    def wait_new_frame(self, timeout_s: float) -> Image | None:
        """지금부터 2장째 들어온 프레임을 돌려준다(1장째는 Enter 전에 이미 전송 중이었을 수 있다)."""
        start_seq, deadline = self.seq, time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.seq >= start_seq + 2:
                return self.latest
        return None


def save_camera_info(info: CameraInfo, path: Path) -> None:
    data = {
        "width": info.width,
        "height": info.height,
        "distortion_model": info.distortion_model,
        "k": [float(v) for v in info.k],
        "d": [float(v) for v in info.d],
        "frame_id": info.header.frame_id,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path.home() / "voss_calib")
    # voss_bringup 이 camera_namespace:='' 로 띄운다(#47). 기본 런치면 /camera/camera/color/image_raw
    ap.add_argument("--topic", default="/camera/color/image_raw")
    ap.add_argument("--info-topic", default="/camera/color/camera_info")
    ap.add_argument("--width", type=int, default=1920, help="운용 해상도 폭 (MC-032: 1920x1080)")
    ap.add_argument(
        "--names", nargs="+", default=[f"C{i}" for i in range(1, 7)] + ["V1", "V2", "V3"]
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = Grabber(args.topic, args.info_topic)
    info_saved = False
    try:
        i = 0
        while i < len(args.names):
            name = args.names[i]
            if input(f"[{name}] 박스를 {name} 자리에 놓고 Enter (q 끝) ").strip() == "q":
                break
            msg = node.wait_new_frame(WAIT_S)
            if msg is None:
                print(
                    f"  ! {WAIT_S:.0f} 초 동안 새 영상이 없다. 카메라 노드·토픽({args.topic}) 확인 후 다시"
                )
                continue  # 같은 이름을 다시 묻는다
            img = to_bgr(msg)
            path = args.out / f"{name}.png"
            cv2.imwrite(str(path), img)
            print(f"  저장 {path} ({img.shape[1]}x{img.shape[0]})")
            if img.shape[1] != args.width:
                print(f"  ! 폭이 {args.width} 이 아니다 — 운용 해상도(1920x1080)로 다시 띄울 것")
            if not info_saved and node.info is not None:
                save_camera_info(node.info, args.out / "camera_info.yaml")
                info_saved = True
                print(f"  저장 {args.out / 'camera_info.yaml'}")
            i += 1
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        if not info_saved:
            print(f"! camera_info 를 못 받았다 ({args.info_topic}) — 왜곡 보정 없이 계산된다")
        node.destroy_node()
        rclpy.try_shutdown()  # 스핀 스레드 없이 끝내 종료 시 코어 덤프가 나지 않게


if __name__ == "__main__":
    main()
