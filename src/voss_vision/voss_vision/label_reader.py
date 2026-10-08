"""label_reader — 송장 판독. LabelCrop → 송장 찾기·펴기 → PaddleOCR → 퍼지 매칭 → 트랙별 다수결 → /voss/vision/label.

T19 1차(G0): stage 1(입구 관측)만 읽는다. stage 2(추종 중)·3(재확인, /voss/vision/read_label)은 T19 2차·T23.
- 후보(동·코드·별칭)는 `/voss/sort/zone_map` 에서만 받는다(규칙 5). 받기 전 크롭은 버린다.
- OCR 은 작업 스레드 하나에서 돈다. 트랙마다 가장 최근 크롭 한 장만 기다리게 하고(오래된 크롭은 교체),
  이미 확실해진 트랙의 크롭은 더 읽지 않는다 → OCR 이 느려도 밀리지 않는다.
- `/voss/vision/label` 발행자는 엔진 예열과 zone_map 수신이 끝난 뒤에 만든다. sort_manager 는 발행자 존재로
  OCR 준비를 보므로, 모델을 읽는 몇 초 동안 준비로 잘못 보이지 않는다.

실행은 사람이 한다 (호스트 G0 는 PaddleOCR 가 든 venv 로):
  ros2 launch voss_vision label_reader.launch.py python:=$HOME/.venvs/voss_ocr/bin/python
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict

import cv2
import numpy as np
import rclpy
import yaml
from builtin_interfaces.msg import Time
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

from voss_msgs.msg import LabelCrop, LabelRead, ZoneMap
from voss_vision.label_match import Candidate, Match
from voss_vision.label_preprocess import crop_upright, find_label_in_crop
from voss_vision.label_vote import Read, TrackReads, Vote
from voss_vision.ocr_engine import read_label

DEFAULT_CONFIG_PATH = os.path.join(
    os.environ.get("VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/config")),
    "voss_config.yaml",
)
STAGE_OBSERVE = 1


def image_to_bgr(msg: Image) -> np.ndarray:
    """sensor_msgs/Image(bgr8·rgb8) → BGR 배열. 행 끝 여백(step)도 처리한다."""
    if msg.encoding not in ("rgb8", "bgr8"):
        raise ValueError(f"인코딩 {msg.encoding} 미지원 — rgb8/bgr8")
    buf = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)
    img = buf[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else img.copy()


def _ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


def _time(ns: int) -> Time:
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


class Stats:
    """주기 로그용 카운터. 콜백·작업 스레드가 같이 쓰므로 노드의 lock 안에서만 고친다."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.crops = {1: 0, 2: 0, 3: 0}
        self.not_ready = 0  # 엔진·zone_map 준비 전에 와서 버린 크롭
        self.superseded = 0  # 기다리는 동안 같은 트랙의 새 크롭으로 바뀜
        self.enough = 0  # 이미 확실한 트랙이라 건너뜀
        self.done = 0
        self.no_label = 0  # 크롭 안에서 송장을 못 찾음
        self.no_text = 0  # OCR·매칭 결과 없음 (180° 다시 읽기 뒤에도)
        self.flipped = 0  # 180° 돌려 읽어서 판정됨 (박스를 거꾸로 올림)
        self.ocr_ms: list[float] = []

    def summary(self, pending: int) -> str:
        def pct(q: float) -> str:
            return f"{np.percentile(self.ocr_ms, q):.0f}" if self.ocr_ms else "-"

        return (
            f"crop 입력 s1 {self.crops[1]}·s2 {self.crops[2]}·s3 {self.crops[3]}, 판독 {self.done}"
            f"(송장 못 찾음 {self.no_label}, 글자 없음 {self.no_text}, 180° {self.flipped}), 교체 {self.superseded}, "
            f"확실해서 건너뜀 {self.enough}, 준비 전 버림 {self.not_ready}, "
            f"OCR 중앙값 {pct(50)}·p95 {pct(95)} ms, 대기 {pending}"
        )


class LabelReaderNode(Node):
    def __init__(self, engine_factory=None) -> None:
        super().__init__("label_reader")
        p = self.declare_parameter
        self.config_path = p("config_path", DEFAULT_CONFIG_PATH).value
        self.device = p("ocr_device", "cpu").value
        self.mkldnn = p("ocr_enable_mkldnn", False).value
        self.scale = p("upright_scale", 3.0).value
        self.v_min = p("label.v_min", 200).value
        self.s_max = p("label.s_max", 90).value
        self.close_px = p("label.close_px", 21).value
        self.enough_agree = p("stage1_enough", 2).value
        self.forget_s = p("track_forget_s", 30.0).value
        self.save_dir = p("debug_save_dir", "").value
        stats_period_s = p("stats_period_s", 5.0).value

        with open(self.config_path, "rb") as f:
            raw = f.read()
        cfg = yaml.safe_load(raw)
        self.conf_min = float(cfg["ocr"]["confidence_min"])  # 확실해진 트랙을 더 읽지 않는 기준
        self.get_logger().info(
            f"voss_config {self.config_path} version {cfg.get('version')} "
            f"sha256 {hashlib.sha256(raw).hexdigest()[:12]}, confidence_min {self.conf_min}, "
            f"OCR {self.device}, stage1_enough {self.enough_agree}"
        )
        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)

        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.pending: OrderedDict[int, LabelCrop] = (
            OrderedDict()
        )  # track_id → 가장 최근 stage 1 크롭
        self.cands: list[Candidate] = []
        self.tracks = TrackReads()
        self.stats = Stats()
        self.engine = None
        self.pub = None
        self.stopping = False

        self.create_subscription(
            LabelCrop,
            "/voss/vision/label_crop",
            self._on_crop,
            QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE),
        )
        self.create_subscription(
            ZoneMap,
            "/voss/sort/zone_map",
            self._on_zone_map,
            QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.create_timer(0.5, self._maybe_create_pub)
        self.create_timer(stats_period_s, self._log_stats)
        self.worker = threading.Thread(target=self._work, args=(engine_factory,), daemon=True)
        self.worker.start()

    # ------------------------------------------------------------ 입력 (executor 스레드)

    def _on_zone_map(self, msg: ZoneMap) -> None:
        cands = [Candidate(e.dong, e.code, tuple(e.aliases)) for e in msg.entries]
        with self.lock:
            self.cands = cands
        self.get_logger().info(
            f"zone_map v{msg.version} 후보 " + ", ".join(f"{c.code or '?'} {c.dong}" for c in cands)
        )

    def _on_crop(self, msg: LabelCrop) -> None:
        with self.cv:
            st = self.stats
            st.crops[msg.stage] = st.crops.get(msg.stage, 0) + 1
            if msg.stage != STAGE_OBSERVE:
                return  # 2단계(추종 중)는 T19 2차, 3단계(재확인)는 T23
            if self.pub is None:
                st.not_ready += 1
                return
            if self.tracks.enough(msg.track_id, msg.stage, self.conf_min, self.enough_agree):
                st.enough += 1
                return
            if msg.track_id in self.pending:
                st.superseded += 1
            self.pending[msg.track_id] = msg  # 이미 있으면 자리는 그대로, 크롭만 최신으로
            self.cv.notify()

    def _maybe_create_pub(self) -> None:
        if self.pub is not None:
            return
        with self.lock:
            ready = self.engine is not None and bool(self.cands)
        if ready:
            self.pub = self.create_publisher(
                LabelRead,
                "/voss/vision/label",
                QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
            )
            self.get_logger().info("판독 준비 완료 — /voss/vision/label 발행 시작")

    def _log_stats(self) -> None:
        with self.lock:
            text = self.stats.summary(len(self.pending))
            self.stats.reset()
            gone = self.tracks.forget(time.monotonic(), self.forget_s)
        if gone:
            text += f", 지운 트랙 {gone}"
        self.get_logger().info(text)

    # ------------------------------------------------------------ 판독 (작업 스레드)

    def _work(self, engine_factory) -> None:
        t0 = time.perf_counter()
        try:
            if engine_factory is None:
                from voss_vision.ocr_engine import PaddleEngine

                eng = PaddleEngine(self.device, enable_mkldnn=self.mkldnn)
            else:
                eng = engine_factory()
            eng.read(np.full((96, 320, 3), 255, np.uint8))  # 예열: 첫 호출이 가장 느리다
        except Exception as e:  # 어떤 실패든 로그로 남기고 발행자를 만들지 않는다
            self.get_logger().error(f"OCR 엔진 준비 실패 ({self.device}): {e}")
            return
        self.get_logger().info(f"OCR 엔진 준비 {self.device} {time.perf_counter() - t0:.1f} s")
        with self.lock:
            self.engine = eng
        while True:
            with self.cv:
                while not self.pending and not self.stopping:
                    self.cv.wait(0.5)
                if self.stopping:
                    return
                track_id, msg = self.pending.popitem(last=False)
                cands = list(self.cands)
                if self.tracks.enough(track_id, msg.stage, self.conf_min, self.enough_agree):
                    self.stats.enough += 1  # 기다리는 사이 앞 판독으로 확실해졌다
                    continue
            try:
                self._read_one(eng, track_id, msg, cands)
            except Exception as e:  # 크롭 하나의 실패로 스레드가 죽지 않게
                self.get_logger().error(f"track {track_id} 판독 실패: {e}")

    def _read_one(self, eng, track_id: int, msg: LabelCrop, cands: list[Candidate]) -> None:
        stamp = _ns(msg.header.stamp)
        img = image_to_bgr(msg.image)
        rect = find_label_in_crop(img, self.v_min, self.s_max, self.close_px)
        ocr_ms, flipped = None, False
        if rect is None:
            m = Match("", "", 0.0, reason="NO_LABEL")
        else:
            up = crop_upright(img, rect, scale=self.scale)
            m, ocr_ms, flipped = read_label(eng, up, cands)
            if self.save_dir:
                cv2.imwrite(
                    os.path.join(self.save_dir, f"t{track_id:05d}_s{msg.stage}_{stamp}.png"), up
                )

        with self.lock:
            v = self.tracks.add(
                track_id, msg.stage, Read(m, stamp, msg.sharpness), time.monotonic()
            )
            st = self.stats
            st.done += 1
            st.no_label += rect is None
            st.no_text += rect is not None and not m.dong
            st.flipped += flipped
            if ocr_ms is not None:
                st.ocr_ms.append(ocr_ms)
        self._publish(track_id, msg.stage, v)
        self.get_logger().info(
            f"track {track_id} s{msg.stage}: {m.code or '-'} {m.dong or '-'} {m.confidence:.2f} {m.reason}"
            + (" (180° 뒤집힘)" if flipped else "")
            + f" → 투표 {v.match.dong or '-'} {v.match.confidence:.2f} ({v.agree}/{v.picked}, 처리 {v.total})"
            + (f", OCR {ocr_ms:.0f} ms" if ocr_ms is not None else "")
        )

    def _publish(self, track_id: int, stage: int, v: Vote) -> None:
        m = v.match
        out = LabelRead(
            track_id=track_id,
            code=m.code,
            dong=m.dong,
            confidence=float(m.confidence),
            stage=stage,
            raw_text=m.raw_text,
            dong_alt=m.dong_alt,
            confidence_alt=float(m.confidence_alt),
        )
        out.stamp = _time(v.stamp_ns)
        self.pub.publish(out)

    def stop(self) -> None:
        with self.cv:
            self.stopping = True
            self.cv.notify_all()
        self.worker.join(timeout=2.0)


def main(args=None) -> None:
    # Ctrl+C 를 파이썬 KeyboardInterrupt 로 받아 spin 도중 컨텍스트가 먼저 닫히는 경합을 피한다
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = LabelReaderNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
