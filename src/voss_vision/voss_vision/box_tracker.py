"""box_tracker — /camera/color/image_raw → /voss/vision/box (BoxTrack) + /voss/vision/label_crop.

계약: docs/interfaces/topics.md·voss_msgs.md(BoxTrack·LabelCrop), calibration.md(좌표).
- 검출 detector=seg(voss_vision.box_detect, ADR-0004). yolo 는 pending #17 결정 뒤에 붙인다.
- 추적 voss_vision.box_track: track_id 규칙, min_hits 확정, PICKING 중 현재 트랙 보류, 미검출 프레임은 발행 안 함.
- 좌표: 관측 자세(1 mm·0.5°) = 호모그래피(SOURCE_OBSERVE_HOMOGRAPHY), 그 밖 = 핸드아이(SOURCE_HAND_EYE,
  촬영 시각 pose 보간). 핸드아이는 moving_verified 전이면 position_valid=false. 깊이는 쓰지 않는다.
- 재생: playback:=<bag 폴더> 면 카메라 대신 녹화를 읽는다(로봇 없이 개발). pose 토픽이 없는 녹화는
  관측 자세에 멈춰 있던 것으로 본다(assume_observe).
판단 로직은 tracker_logic.py(pytest), 이 파일은 ROS 입출력만 맡는다.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import PoseStamped
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import CameraInfo, CompressedImage, Image

from voss_msgs.msg import BoxTrack, LabelCrop, SortState
from voss_vision import tracker_logic as tl
from voss_vision.belt_plane import flange_to_tcp, pixel_to_base_xy, rot_zyz_deg
from voss_vision.box_detect import SegParams, detect_boxes
from voss_vision.box_track import Tracker
from voss_vision.hand_eye import interpolate_pose, make_t, pixel_to_plane, pose_msg_to_t

QOS_BOX = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)  # topics.md QoS 표
QOS_CROP = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE)
QOS_STATE = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
# pose 는 depth 1 로 발행되지만, 영상 처리 중 밀린 것도 보간에 쓰려고 받는 쪽은 10 으로 둔다
QOS_POSE = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

SEG_KEYS = ("downscale", "v_min", "s_max", "close_px", "area_min", "area_max", "aspect_tol",
            "fill_min", "border_px", "belt_green_frac", "belt_margin_px")  # fmt: skip
HOMO_HE_WARN_MM = 3.0  # 관측 자세에서 두 방식 차이가 이보다 크면 경고 (calibration.md)
SRC_NAME = {
    BoxTrack.SOURCE_NONE: "none",
    BoxTrack.SOURCE_OBSERVE_HOMOGRAPHY: "homography",
    BoxTrack.SOURCE_HAND_EYE: "hand_eye",
}


def stamp_s(t) -> float:
    return t.sec + t.nanosec * 1e-9


def image_to_bgr(msg: Image) -> np.ndarray:
    """sensor_msgs/Image(rgb8·bgr8) → BGR. cv_bridge 없이."""
    if msg.encoding not in ("rgb8", "bgr8"):
        raise ValueError(f"인코딩 {msg.encoding} 미지원 — rgb8/bgr8")
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    img = img[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else img.copy()


def bgr_to_image(img: np.ndarray, header) -> Image:
    m = Image()
    m.header = header
    m.height, m.width = img.shape[:2]
    m.encoding, m.step = "bgr8", img.shape[1] * 3
    m.data = np.ascontiguousarray(img).tobytes()
    return m


def load_yaml(path: str) -> dict | None:
    p = Path(path).expanduser()
    return yaml.safe_load(p.read_text()) if path and p.is_file() else None


class BoxTrackerNode(Node):
    def __init__(self) -> None:
        super().__init__("box_tracker")
        p = self.declare_parameter
        self.detector = p("detector", "seg").value
        if self.detector != "seg":
            raise RuntimeError(
                f"detector={self.detector} 는 아직 없다 — seg 만 (yolo 는 pending #17 뒤)"
            )
        base = SegParams()
        self.seg = SegParams(
            **{k: type(getattr(base, k))(p(f"seg.{k}", getattr(base, k)).value) for k in SEG_KEYS}
        )
        self.tracker = Tracker(
            max_missed=p("max_missed", 15).value,
            gate_px=float(p("gate_px", 120.0).value),
            min_hits=p("min_hits", 5).value,
        )
        self.playback = p("playback", "").value
        self.playback_rate = float(p("playback_rate", 1.0).value)
        self.assume_observe = bool(p("assume_observe", bool(self.playback)).value)
        self.pose_max_gap = float(p("pose_max_gap_s", 0.04).value)
        # /voss/robot/pose stamp 는 실제 로봇 상태보다 늦다(10/08 약 60 ms) → 촬영 시각 + lag 의 pose 를 쓴다.
        # 그 pose 가 아직 없으면 최근 속도로 max_extrap 까지만 앞으로 외삽(calibration.md)
        self.pose_lag = float(p("pose_lag_ms", 60.0).value) / 1000.0
        self.pose_max_extrap = float(p("pose_max_extrap_ms", 80.0).value) / 1000.0
        self.hz_warn = float(p("hz_warn", 25.0).value)
        self.obs_tol_mm = float(p("observe_tol_mm", 1.0).value)
        self.obs_tol_deg = float(p("observe_tol_deg", 0.5).value)
        self.crop_margin = float(p("crop_margin", 0.15).value)
        self.gate = tl.CropGate(
            period_s=float(p("crop_period_s", 0.2).value),
            max_per_stage={1: p("crop_max_stage1", 10).value, 2: 100000, 3: 100000},
            min_sharpness=float(p("crop_min_sharpness", 0.0).value),
        )
        self.stats_period = float(p("stats_period_s", 5.0).value)
        image_topic = p("image_topic", "/camera/color/image_raw").value
        self.frame_id = "camera_color_optical_frame"

        # 캘리브레이션 (읽기 전용 마운트 config/). 평면 높이는 호모그래피 파일 하나에서만 읽는다
        self.homo = load_yaml(p("homography_path", "").value)
        self.he = load_yaml(p("hand_eye_path", "").value)
        self.T_obs = None
        self.plane_z = None
        if self.homo:
            obs = np.asarray(self.homo["observe_pose"], float)
            self.T_obs = make_t(
                rot_zyz_deg(*obs[3:6]), flange_to_tcp(obs, np.asarray(self.homo["tcp_offset_mm"]))
            )
            self.plane_z = float(self.homo["plane_z_mm"])
        if self.he:
            self.he_T = np.asarray(self.he["T_tcp_camera"], float)
            self.he_k = np.asarray(self.he["camera"]["k"], float).reshape(3, 3)
            self.he_d = np.asarray(self.he["camera"].get("d") or [0.0] * 5, float)
            self.he_verified = bool(self.he.get("moving_verified", False))
        self.homo_ok = self.homo is not None  # camera_info 로 다시 확인
        self.he_ok = self.he is not None and self.plane_z is not None

        self._lock = threading.Lock()
        self._state, self._sort_track = "", -1
        self._poses: deque[tuple[float, np.ndarray]] = deque(maxlen=200)
        self.stats = tl.LoopStats()
        self._stats_lock = threading.Lock()  # 영상 스레드·로그 타이머가 같이 쓴다
        self.done = False
        self.stopping = (
            False  # 종료 때 재생 스레드를 먼저 멈춘다(bag 리더가 살아 있으면 프로세스가 죽는다)
        )
        self.player: threading.Thread | None = None

        self.pub_box = self.create_publisher(BoxTrack, "/voss/vision/box", QOS_BOX)
        self.pub_crop = self.create_publisher(LabelCrop, "/voss/vision/label_crop", QOS_CROP)
        side = (
            MutuallyExclusiveCallbackGroup()
        )  # pose·state 는 영상 처리와 따로 돈다(보간 이력 유지)
        self.create_subscription(
            PoseStamped, "/voss/robot/pose", self._on_pose, QOS_POSE, callback_group=side
        )
        self.create_subscription(
            SortState, "/voss/sort/state", self._on_state, QOS_STATE, callback_group=side
        )
        self.create_timer(self.stats_period, self._log_stats, callback_group=side)
        if self.playback:
            self.player = threading.Thread(target=self._run_playback, daemon=True)
            self.player.start()
        else:
            self.create_subscription(CameraInfo, "/camera/color/camera_info", self._on_info,
                                     qos_profile_sensor_data, callback_group=side)  # fmt: skip
            self.create_subscription(Image, image_topic, self._on_image, qos_profile_sensor_data)
        self._info_checked = False
        self.get_logger().info(
            f"box_tracker started: detector={self.detector} min_hits={self.tracker.min_hits} "
            f"homography={'v' + str(self.homo.get('created')) if self.homo else '없음'} "
            f"hand_eye={self._he_label()} pose_lag={self.pose_lag * 1000:.0f} ms "
            f"input={'playback ' + self.playback if self.playback else image_topic}"
        )

    def _he_label(self) -> str:
        if not self.he:
            return "없음"
        return f"{self.he.get('created')} moving_verified={self.he_verified}"

    # ---------------- 입력 ----------------
    def _on_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        t = pose_msg_to_t([p.x, p.y, p.z], [q.x, q.y, q.z, q.w])
        with self._lock:
            self._poses.append((stamp_s(msg.header.stamp), t))

    def _on_state(self, msg: SortState) -> None:
        with self._lock:
            self._state, self._sort_track = msg.state, msg.track_id

    def _on_info(self, msg: CameraInfo) -> None:
        if self._info_checked:
            return
        self._info_checked = True
        size = [msg.width, msg.height]
        if self.homo and list(self.homo.get("image_size", size)) != size:
            self.homo_ok = False
            self.get_logger().error(
                f"영상 {size} ≠ 호모그래피 {self.homo['image_size']} — 관측 좌표 무효"
            )
        if self.he:
            ref = (self.he.get("camera_factory") or self.he["camera"])["k"]
            if (
                list(self.he.get("image_size", size)) != size
                or np.max(np.abs(np.asarray(msg.k) - ref)) > 1.0
            ):
                self.he_ok = False
                self.get_logger().error(
                    "camera_info 가 핸드아이 촬영 때와 다르다 — 이동 중 좌표 무효"
                )

    def _on_image(self, msg: Image) -> None:
        self.process(image_to_bgr(msg), msg.header.stamp, live=True)

    def _run_playback(self) -> None:
        """녹화(mcap) 를 촬영 시각 간격대로(playback_rate 배) 읽어 같은 처리를 한다."""
        import rosbag2_py
        from rclpy.serialization import deserialize_message

        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(Path(self.playback).expanduser())),
                    rosbag2_py.ConverterOptions("", ""))  # fmt: skip
        types = {t.name: t.type for t in reader.get_all_topics_and_types()}
        t_wall0 = t_bag0 = None
        n = 0
        while rclpy.ok() and not self.stopping and reader.has_next():
            topic, data, t_bag = reader.read_next()
            kind = types.get(topic, "")
            if kind == "geometry_msgs/msg/PoseStamped" and topic.endswith("/voss/robot/pose"):
                self._on_pose(deserialize_message(data, PoseStamped))
                continue
            if kind == "sensor_msgs/msg/CameraInfo":
                self._on_info(deserialize_message(data, CameraInfo))
                continue
            if kind == "sensor_msgs/msg/CompressedImage":
                m = deserialize_message(data, CompressedImage)
                img = cv2.imdecode(np.frombuffer(m.data, np.uint8), cv2.IMREAD_COLOR)
            elif kind == "sensor_msgs/msg/Image":
                m = deserialize_message(data, Image)
                img = image_to_bgr(m)
            else:
                continue
            if t_bag0 is None:
                t_wall0, t_bag0 = time.monotonic(), t_bag
            wait = (t_bag - t_bag0) * 1e-9 / self.playback_rate - (time.monotonic() - t_wall0)
            if wait > 0:
                time.sleep(wait)
            self.process(img, m.header.stamp, live=False)
            n += 1
        self.get_logger().info(f"재생 끝: 영상 {n} 프레임 ({self.playback})")
        self._log_stats()
        self.done = True

    # ---------------- 처리 ----------------
    def process(self, bgr: np.ndarray, stamp, live: bool) -> None:
        t0 = time.perf_counter()
        dets = detect_boxes(bgr, self.seg)
        t_det = time.perf_counter()
        with self._lock:
            state, sort_tid = self._state, self._sort_track
        tracks = self.tracker.update(dets, hold_id=tl.hold_track_id(state, sort_tid))
        ts = stamp_s(stamp)
        pose_t, at_obs = self._pose_at(ts)
        for t in tracks:
            m = BoxTrack(
                track_id=t.id,
                u=float(t.u),
                v=float(t.v),
                bbox=[int(b) for b in t.bbox],
                stamp=stamp,
            )
            self._fill_position(m, t.u, t.v, pose_t, at_obs)
            self.pub_box.publish(m)
            with self._stats_lock:
                self.stats.add_box(SRC_NAME[m.position_source], m.position_valid)
            self._maybe_crop(bgr, t, stamp, ts, label_stage=tl.label_stage(t.id, state, sort_tid))
        self.gate.forget(set(self.tracker.tracks))
        t1 = time.perf_counter()
        age = (self.get_clock().now().nanoseconds * 1e-9 - ts) * 1000 if live else None
        with self._stats_lock:
            self.stats.add_frame((t_det - t0) * 1000, (t1 - t0) * 1000, age)

    def _pose_at(self, ts: float) -> tuple[np.ndarray | None, bool]:
        """촬영 시각의 TCP pose 와 관측 자세 여부. pose 를 받은 적 없으면 assume_observe 를 따른다."""
        with self._lock:
            hist = list(self._poses)
        if not hist:
            return (
                (self.T_obs, True)
                if self.assume_observe and self.T_obs is not None
                else (None, False)
            )
        tq = ts + self.pose_lag
        stamps = [h[0] for h in hist]
        t = interpolate_pose(
            tq, stamps, [h[1] for h in hist], self.pose_max_gap, self.pose_max_extrap
        )
        with self._stats_lock:
            self.stats.add_pose(None if t is None else max(0.0, tq - stamps[-1]) * 1000)
        if t is None:
            return None, False
        at_obs = self.T_obs is not None and tl.near_observe(
            t, self.T_obs, self.obs_tol_mm, self.obs_tol_deg
        )
        return t, at_obs

    def _fill_position(self, m: BoxTrack, u: float, v: float, pose_t, at_obs: bool) -> None:
        m.position_source, m.position_valid = BoxTrack.SOURCE_NONE, False
        he_xyz = None
        if pose_t is not None and self.he_ok:
            xyz, ok = pixel_to_plane(
                pose_t @ self.he_T, self.he_k, self.he_d, [[u, v]], self.plane_z
            )
            he_xyz = xyz[0] if ok[0] else None
        if pose_t is not None and at_obs and self.homo:
            xy, ok = pixel_to_base_xy(self.homo, np.array([[u, v]], float))
            m.position_base.x, m.position_base.y = xy[0, 0] / 1000.0, xy[0, 1] / 1000.0
            m.position_base.z = self.plane_z / 1000.0
            m.position_valid = bool(ok[0]) and self.homo_ok
            m.position_source = BoxTrack.SOURCE_OBSERVE_HOMOGRAPHY
            m.calib_version = f"homography {self.homo.get('created')}"
            # 관측 자세에서 두 방식 차이를 로그로 남긴다(calibration.md). 호모그래피 유효 영역 밖은
            # 외삽이라 비교하지 않는다
            if he_xyz is not None and m.position_valid:
                d = float(np.hypot(he_xyz[0] - xy[0, 0], he_xyz[1] - xy[0, 1]))
                with self._stats_lock:
                    self.stats.homo_vs_he_mm = max(self.stats.homo_vs_he_mm, d)
        elif he_xyz is not None:
            m.position_base.x, m.position_base.y, m.position_base.z = (
                float(c) / 1000.0 for c in he_xyz
            )
            m.position_valid = self.he_verified  # 이동 중 검증 전에는 쓰지 않는다
            m.position_source = BoxTrack.SOURCE_HAND_EYE
            m.calib_version = f"hand_eye {self.he.get('created')}"

    def _maybe_crop(self, bgr: np.ndarray, t, stamp, ts: float, label_stage: int) -> None:
        if not self.gate.due(t.id, label_stage, ts):
            return
        win = tl.crop_window(t.bbox, bgr.shape, self.crop_margin)
        if win is None:
            return
        x0, y0, x1, y1 = win
        crop = bgr[y0:y1, x0:x1]
        sharp = tl.sharpness(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
        if not self.gate.accept(t.id, label_stage, ts, sharp):
            return
        m = LabelCrop(track_id=t.id, stage=label_stage, sharpness=sharp)
        m.header.stamp, m.header.frame_id = stamp, self.frame_id
        m.image = bgr_to_image(crop, m.header)
        self.pub_crop.publish(m)
        with self._stats_lock:
            self.stats.crops += 1

    def _log_stats(self) -> None:
        with self._stats_lock:
            text = self.stats.summary(self.stats_period)
            diff = self.stats.homo_vs_he_mm
            hz = self.stats.frames / self.stats_period
            self.stats.reset()
        self.get_logger().info(text)
        if not self.playback and hz < self.hz_warn:
            # sort_manager 는 노드 존재만 보므로 카메라가 멈춰도 VISION 준비로 남는다 → 사람이 보게 경고
            self.get_logger().warn(
                f"영상 {hz:.1f} Hz < {self.hz_warn:.0f} — 카메라 USB·카메라 노드 확인 (10/08 USB 끊김 사례)"
            )
        if diff > HOMO_HE_WARN_MM:
            self.get_logger().warn(
                f"관측 자세에서 호모그래피와 핸드아이가 {diff:.1f} mm 다르다 (> {HOMO_HE_WARN_MM} mm)"
            )


def main(args=None) -> None:
    # Ctrl+C 를 파이썬 KeyboardInterrupt 로 받아, 재생 스레드를 멈춘 뒤 닫는다
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = BoxTrackerNode()
    executor = MultiThreadedExecutor(num_threads=2)  # 영상 1 + pose·state·통계 1
    executor.add_node(node)
    try:
        while rclpy.ok() and not node.done:
            executor.spin_once(timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.stopping = True
        if node.player is not None:
            node.player.join(timeout=2.0)
        executor.shutdown(timeout_sec=1.0)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
