"""label_reader — 송장 판독. LabelCrop → 송장 찾기·펴기 → PaddleOCR → 퍼지 매칭 → 트랙별 다수결 → /voss/vision/label.

T19 1차(G0): stage 1(입구 관측). T23: stage 3(재확인 구역 정지 재판독, 서비스 `/voss/vision/read_label`).
stage 2(추종 중)는 T19 2차.
- 후보(동·코드·별칭)는 `/voss/sort/zone_map` 에서만 받는다(규칙 5). 받기 전 크롭은 버린다.
- OCR 은 작업 스레드 하나에서 돈다. 트랙마다 가장 최근 크롭 한 장만 기다리게 하고(오래된 크롭은 교체),
  이미 확실해진 트랙의 크롭은 더 읽지 않는다 → OCR 이 느려도 밀리지 않는다. 재판독 요청은 크롭보다 먼저 읽는다.
- `/voss/vision/label` 발행자와 `read_label` 서비스는 엔진 예열과 zone_map 수신이 끝난 뒤에 만든다. sort_manager 는
  발행자 존재로 OCR 준비를 보고, 서비스가 없으면 NO_SERVICE 로 질문 경로에 간다 → 모델을 읽는 몇 초 동안
  준비로 잘못 보이지 않는다.
- 재판독(stage 3): 요청이 오면 그때만 카메라 영상을 구독해 max_frames 장(기본 5)을 timeout_s(기본 2 s) 안에 모은다.
  box_tracker 크롭은 초록 벨트 전제라 트레이에서는 못 쓴다 → `label_view` 가 전체 화면에서 송장을 찾는다.
  응답까지 걸리는 시간 = 프레임 모으기(≤ timeout_s) + OCR(선명한 것부터 view.max_ocr 장, CPU 장당 약 1.7 s).

실행은 사람이 한다 (호스트 G0 는 PaddleOCR 가 든 venv 로):
  ros2 launch voss_vision label_reader.launch.py python:=$HOME/.venvs/voss_ocr/bin/python
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import rclpy
import yaml
from builtin_interfaces.msg import Time
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

from voss_msgs.msg import LabelCrop, LabelRead, ZoneMap
from voss_msgs.srv import ReadLabel
from voss_vision.label_match import Candidate, Match
from voss_vision.label_preprocess import crop_upright, find_label_in_crop
from voss_vision.label_view import ViewResult, read_view
from voss_vision.label_vote import Read, TrackReads, Vote
from voss_vision.ocr_engine import read_label

DEFAULT_CONFIG_PATH = os.path.join(
    os.environ.get("VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/config")),
    "voss_config.yaml",
)
STAGE_OBSERVE = 1
STAGE_RECHECK = 3


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


class Grab:
    """재판독 요청 동안만 쓰는 카메라 구독 콜백 — n 장 모이면 done."""

    def __init__(self, n: int) -> None:
        self.n, self.frames, self.bad = n, [], ""
        self.lock = threading.Lock()
        self.done = threading.Event()

    def add(self, msg: Image) -> None:
        with self.lock:
            if len(self.frames) >= self.n:
                return
            try:
                self.frames.append((image_to_bgr(msg), _ns(msg.header.stamp)))
            except ValueError as e:
                self.bad = str(e)
                return
            if len(self.frames) >= self.n:
                self.done.set()


@dataclass
class ViewJob:
    """서비스 콜백 → 작업 스레드. 작업 스레드가 result 를 채우고 done 을 켠다."""

    frames: list
    max_ocr: int
    finder: dict  # find_labels_in_view 인자 (칸을 지정하면 그 칸의 roi)
    done: threading.Event = field(default_factory=threading.Event)
    result: ViewResult | None = None
    cancelled: bool = False  # 서비스가 기다리다 포기함 → 작업 스레드는 건너뛴다


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
        # 재판독(stage 3). 송장 크기(px)·영역은 재확인 VIEW 자세 사진으로 정한다 — 그 전엔 넓게
        self.view_topic = p("view.image_topic", "/camera/color/image_raw").value
        self.view_frames = p("view.max_frames", 5).value  # 요청 max_frames=0 일 때
        self.view_window_s = p("view.timeout_s", 2.0).value  # 요청 timeout_s=0 일 때
        self.view_max_ocr = p("view.max_ocr", 3).value  # 모은 것 중 선명한 순 OCR 최대 장수
        self.view_min_agree = p("view.min_agree", 2).value
        self.view_ocr_wait_s = p("view.ocr_wait_s", 10.0).value  # OCR 결과 대기 한도
        roi = list(p("view.roi", [0, 0, 0, 0]).value)  # x0 y0 x1 y1 (px), 전부 0 = 전체 화면
        self.view_finder = {
            "v_min": self.v_min,
            "s_max": self.s_max,
            "close_px": self.close_px,
            "area_min_px": p("view.area_min_px", 4000).value,
            "area_max_px": p("view.area_max_px", 300_000).value,
            "fill_min": p("view.fill_min", 0.75).value,
            "aspect_tol": p("view.aspect_tol", 0.5).value,
            "roi": tuple(roi) if any(roi) else None,
        }
        # 칸별 화면 영역 [x0 y0 x1 y1] × 칸 수 (평평한 목록). ReadLabel.slot ≥ 0 이면 그 칸 영역만 본다
        flat = list(p("view.slot_rois", [0, 0, 0, 0]).value)
        self.slot_rois = [
            tuple(flat[i : i + 4])
            for i in range(0, len(flat) - len(flat) % 4, 4)
            if any(flat[i : i + 4])
        ]

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
        self.srv = None
        self.jobs: deque[ViewJob] = deque()  # 재판독 — 크롭보다 먼저 읽는다
        self.stopping = False
        self.srv_group = MutuallyExclusiveCallbackGroup()  # 서비스 콜백은 결과까지 기다린다
        self.img_group = MutuallyExclusiveCallbackGroup()  # 그동안 카메라 콜백이 돌아야 한다

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
            self.srv = self.create_service(
                ReadLabel,
                "/voss/vision/read_label",
                self._on_read_label,
                callback_group=self.srv_group,
            )
            self.get_logger().info(
                "판독 준비 완료 — /voss/vision/label 발행, /voss/vision/read_label 서비스 시작"
            )

    def _log_stats(self) -> None:
        with self.lock:
            text = self.stats.summary(len(self.pending))
            self.stats.reset()
            gone = self.tracks.forget(time.monotonic(), self.forget_s)
        if gone:
            text += f", 지운 트랙 {gone}"
        self.get_logger().info(text)

    # ------------------------------------------------------------ 재판독 서비스 (stage 3)

    def _on_read_label(self, req: ReadLabel.Request, res: ReadLabel.Response) -> ReadLabel.Response:
        """재확인 구역 위(VIEW)에서 정지 화면 몇 장 → 다수결. sort_manager 가 VIEW 이동 완료 뒤 부른다."""
        n = int(req.max_frames) or self.view_frames
        slot = int(req.slot)
        if slot >= len(self.slot_rois) or slot < -1:
            self.get_logger().error(
                f"재판독 칸 {slot}: view.slot_rois 에 없음({len(self.slot_rois)}칸)"
            )
            res.ok, res.message = False, "bad_slot"
            res.label = LabelRead(track_id=req.track_id, stage=STAGE_RECHECK)
            return res
        finder = self.view_finder if slot < 0 else {**self.view_finder, "roi": self.slot_rois[slot]}
        window = float(req.timeout_s) or self.view_window_s
        t0 = time.perf_counter()
        grab = Grab(n)
        sub = self.create_subscription(
            Image,
            self.view_topic,
            grab.add,
            QoSProfile(depth=2, reliability=ReliabilityPolicy.BEST_EFFORT),
            callback_group=self.img_group,
        )
        try:
            grab.done.wait(window)
        finally:
            self.destroy_subscription(sub)
        with grab.lock:
            frames, bad = list(grab.frames), grab.bad
        t_grab = time.perf_counter() - t0
        if bad and not frames:
            self.get_logger().error(f"재판독 영상 변환 실패: {bad}")
        job = ViewJob(frames, min(self.view_max_ocr, n), finder)
        with self.cv:
            self.stats.crops[STAGE_RECHECK] += 1
            self.jobs.append(job)
            self.cv.notify()
        if not job.done.wait(self.view_ocr_wait_s):
            job.cancelled = True
            r = ViewResult(None, "timeout", 0)
            note = f"OCR {self.view_ocr_wait_s:.0f} s 초과"
        else:
            r = job.result
            note = f"OCR {r.ocr_runs} 장"
        res.ok = r.vote is not None and not r.reason
        res.message = r.reason
        res.label = (
            self._label_msg(req.track_id, STAGE_RECHECK, r.vote)
            if r.vote is not None
            else LabelRead(track_id=req.track_id, stage=STAGE_RECHECK)
        )
        if res.ok:
            self.pub.publish(res.label)
        lb = res.label
        self.get_logger().info(
            f"재판독 track {req.track_id} 칸 {slot}: ok={res.ok} {r.reason or '-'} {lb.code or '-'} {lb.dong or '-'} "
            f"{lb.confidence:.2f} (alt {lb.dong_alt or '-'} {lb.confidence_alt:.2f}) — 프레임 {len(frames)}/{n} "
            f"{t_grab:.1f} s, {note}, 전체 {time.perf_counter() - t0:.1f} s"
        )
        return res

    def _run_view(self, eng, job: ViewJob, cands: list[Candidate]) -> None:
        t0 = time.perf_counter()
        try:
            r = read_view(
                eng,
                job.frames,
                cands,
                finder=job.finder,
                scale=self.scale,
                max_ocr=job.max_ocr,
                conf_min=self.conf_min,
                min_agree=self.view_min_agree,
            )
        except Exception as e:  # 실패해도 서비스가 기다리다 끝나지 않게 결과는 채운다
            self.get_logger().error(f"재판독 실패: {e}")
            r = ViewResult(None, "no_text", 0)
        if self.save_dir and job.frames:
            img, stamp = job.frames[0]
            cv2.imwrite(os.path.join(self.save_dir, f"view_s3_{stamp}.png"), img)
        with self.lock:
            self.stats.done += r.ocr_runs > 0
            if r.ocr_runs:
                self.stats.ocr_ms.append((time.perf_counter() - t0) * 1000 / r.ocr_runs)
        job.result = r
        job.done.set()

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
                while not self.pending and not self.jobs and not self.stopping:
                    self.cv.wait(0.5)
                if self.stopping:
                    return
                cands = list(self.cands)
                job = self.jobs.popleft() if self.jobs else None
                if job is None:
                    track_id, msg = self.pending.popitem(last=False)
                    if self.tracks.enough(track_id, msg.stage, self.conf_min, self.enough_agree):
                        self.stats.enough += 1  # 기다리는 사이 앞 판독으로 확실해졌다
                        continue
            if job is not None:
                if not job.cancelled:
                    self._run_view(eng, job, cands)
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
        self.pub.publish(self._label_msg(track_id, stage, v))

    @staticmethod
    def _label_msg(track_id: int, stage: int, v: Vote) -> LabelRead:
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
        return out

    def stop(self) -> None:
        with self.cv:
            self.stopping = True
            self.cv.notify_all()
        self.worker.join(timeout=2.0)


def main(args=None) -> None:
    # Ctrl+C 를 파이썬 KeyboardInterrupt 로 받아 spin 도중 컨텍스트가 먼저 닫히는 경합을 피한다
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = LabelReaderNode()
    # 재판독 서비스 콜백이 결과를 기다리는 동안 카메라·크롭·zone_map 콜백이 돌아야 한다
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.stop()
        executor.shutdown(timeout_sec=1.0)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
