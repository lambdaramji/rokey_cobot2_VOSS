"""현장용 핸드아이 촬영: Enter 마다 영상 1장 + 그 순간의 TCP pose(/voss/robot/pose 평균)를 저장한다.

로봇을 움직이지 않고 두산 서비스도 부르지 않는다(규칙 3). 로봇은 김학민이 펜던트 저속·직접교시로 옮긴다.
robot_gateway·카메라 노드(1920x1080, 노출 6 ms)가 떠 있어야 한다.
  source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
  python3 tools/calib/handeye_capture.py --out ~/voss_data/1008/handeye

- Enter 뒤 새 영상 1장과 0.5 초 동안의 pose 를 모은다. pose 가 0.2 mm·0.05° 넘게 흔들리면(로봇이 아직 움직임)
  저장하지 않고 다시 묻는다.
- 보드(기본 내부 코너 10x7, 25 mm)가 안 보이면 저장하지 않는다. 보이면 카메라-보드 거리·공구 기울기를 보여 줘서
  자세를 고르게 퍼뜨리는 데 쓴다(기울기 15~25°, 공구축 회전 ±60°, 거리 35~50 cm).
- 게이트웨이가 없으면 --manual-pose: 펜던트 TCP 값(x y z rx ry rz)을 직접 입력한다.
- 결과: HE_01.png …, poses.csv, camera_info.yaml → tools/calib/fit_hand_eye.py
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.qos import qos_profile_sensor_data

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from grab_frames import WAIT_S, Grabber, save_camera_info, to_bgr  # noqa: E402
from voss_vision.hand_eye import (  # noqa: E402
    board_pose,
    mean_pose,
    pose_msg_to_t,
    posx_to_t,
    rot_angle_deg,
    rot_to_quat,
    spread,
)

POSE_WINDOW_S = 0.5
STILL_MM, STILL_DEG = 0.2, 0.05
FIELDS = ["name", "image_stamp", "x_mm", "y_mm", "z_mm", "qx", "qy", "qz", "qw", "n_pose", "jitter_mm",
          "jitter_deg", "source"]  # fmt: skip


class Capture(Grabber):
    def __init__(self, topic: str, info_topic: str, pose_topic: str) -> None:
        super().__init__(topic, info_topic)
        self.poses: list[tuple[float, np.ndarray]] = []
        self.create_subscription(PoseStamped, pose_topic, self._pose_cb, qos_profile_sensor_data)

    def _pose_cb(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self.poses.append((t, pose_msg_to_t([p.x, p.y, p.z], [q.x, q.y, q.z, q.w])))

    def collect_poses(self, window_s: float) -> list[np.ndarray]:
        self.poses.clear()
        deadline = time.monotonic() + window_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.02)
        return [t for _, t in self.poses]


def tool_tilt_deg(t_base_tcp: np.ndarray) -> float:
    """공구 z 축과 수직 아래(-z) 사이 각."""
    return float(np.degrees(np.arccos(np.clip(-t_base_tcp[2, 2], -1.0, 1.0))))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--topic", default="/camera/color/image_raw")
    ap.add_argument("--info-topic", default="/camera/color/camera_info")
    ap.add_argument("--pose-topic", default="/voss/robot/pose")
    ap.add_argument("--board", type=int, nargs=2, default=[10, 7], help="내부 코너 (가로 세로)")
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--count", type=int, default=40, help="최대 장수 (24장 + 추가 촬영 여유)")
    ap.add_argument(
        "--manual-pose", action="store_true", help="게이트웨이 없이 펜던트 TCP 값을 입력"
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "poses.csv"
    new_file = not csv_path.exists()
    done = sum(1 for _ in csv.DictReader(csv_path.open())) if not new_file else 0

    rclpy.init()
    node = Capture(args.topic, args.info_topic, args.pose_topic)
    info_saved = (args.out / "camera_info.yaml").exists()
    first: np.ndarray | None = None
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        try:
            i = done + 1
            while i <= args.count:
                name = f"HE_{i:02d}"
                if input(f"[{name}] 로봇이 멈춘 뒤 Enter (q 끝) ").strip() == "q":
                    break
                msg = node.wait_new_frame(WAIT_S)
                if msg is None:
                    print(f"  ! 새 영상 없음 — 카메라 토픽({args.topic}) 확인 후 다시")
                    continue
                if args.manual_pose:
                    vals = input("  펜던트 TCP x y z rx ry rz: ").split()
                    if len(vals) != 6:
                        print("  ! 숫자 6개가 아니다 — 다시")
                        continue
                    t_tcp, n, jit_mm, jit_deg, src = (
                        posx_to_t([float(v) for v in vals]),
                        1,
                        0.0,
                        0.0,
                        "pendant",
                    )
                else:
                    samples = node.collect_poses(POSE_WINDOW_S)
                    if len(samples) < 5:
                        print(
                            f"  ! pose {len(samples)}개 — 게이트웨이({args.pose_topic}) 확인 후 다시"
                        )
                        continue
                    jit_mm, jit_deg = spread(samples)
                    if jit_mm > STILL_MM or jit_deg > STILL_DEG:
                        print(
                            f"  ! 로봇이 아직 움직인다({jit_mm:.2f} mm, {jit_deg:.3f}°) — 멈춘 뒤 다시"
                        )
                        continue
                    t_tcp, n, src = mean_pose(samples), len(samples), "voss_robot_pose"
                img = to_bgr(msg)
                if node.info is None:
                    print("  ! camera_info 를 아직 못 받았다 — 다시")
                    continue
                k = np.array(node.info.k, dtype=float).reshape(3, 3)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                ok, corners = cv2.findChessboardCornersSB(gray, tuple(args.board))
                if not ok:
                    print(
                        "  ! 보드 코너를 못 찾았다(보드 전체가 화면 안·초점·반사 확인) — 자세 바꿔 다시"
                    )
                    continue
                t_cb, err = board_pose(corners, tuple(args.board), args.square_mm, k, node.info.d)
                cv2.imwrite(str(args.out / f"{name}.png"), img)
                q = rot_to_quat(t_tcp[:3, :3])
                stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
                w.writerow({"name": name, "image_stamp": f"{stamp:.6f}",
                            "x_mm": f"{t_tcp[0, 3]:.3f}", "y_mm": f"{t_tcp[1, 3]:.3f}", "z_mm": f"{t_tcp[2, 3]:.3f}",
                            "qx": f"{q[0]:.8f}", "qy": f"{q[1]:.8f}", "qz": f"{q[2]:.8f}", "qw": f"{q[3]:.8f}",
                            "n_pose": n, "jitter_mm": f"{jit_mm:.3f}", "jitter_deg": f"{jit_deg:.4f}",
                            "source": src})  # fmt: skip
                f.flush()
                first = t_tcp if first is None else first
                spin = rot_angle_deg(first[:3, :3], t_tcp[:3, :3])
                print(
                    f"  저장 {name}: 보드 거리 {np.linalg.norm(t_cb[:3, 3]) / 10:.0f} cm, "
                    f"공구 기울기 {tool_tilt_deg(t_tcp):.0f}°, 첫 자세와 회전 차 {spin:.0f}°, "
                    f"코너 재투영 {err:.2f} px, pose {n}개"
                )
                if not info_saved:
                    save_camera_info(node.info, args.out / "camera_info.yaml")
                    info_saved = True
                i += 1
        except (KeyboardInterrupt, EOFError):
            print()
        finally:
            node.destroy_node()
            rclpy.try_shutdown()
    print(f"끝: {csv_path} — 다음: python3 tools/calib/fit_hand_eye.py --data {args.out}")


if __name__ == "__main__":
    main()
