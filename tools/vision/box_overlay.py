"""box_tracker 시각화 — 카메라 화면에 송장 후보·버린 이유·발행된 BoxTrack·OCR 결과를 덧그린다. 사람이 실행, 구독만(로봇과 무관).

목적(T21 #30): 하강 중 Box LOST 원인 찾기. 언제 발행이 끊겼는지(BoxTrack)와 그 프레임에서 송장 후보를 왜 버렸는지
(`box_detect.detect_candidates`: 면적·가장자리·비율·채움)를 한 화면에서 본다. 판정은 box_tracker 와 같은 함수·같은
seg 파라미터(`src/voss_vision/config/box_tracker.yaml`)다.

녹화 재생(주) — G1 bag(g0-runbook 3절 녹화 명령의 토픽). voss_msgs 가 빌드된 워크스페이스를 source 한다:
  source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
  python3 tools/vision/box_overlay.py ~/voss_data/1010/g1_s1_clips/t26 [--start 12 --end 30] [--out t26.mp4] [--csv t26.csv] [--show]
  (잘라낸 bag 은 액션 feedback·status 의 message definition 이 비어 있을 수 있다 — 이 도구는 설치된 voss_msgs 로 읽어 상관없다)
실시간 — 공용 PC, 10/11 통합부터. 게이트 측정 중에는 띄우지 않는다(영상 구독이 하나 더 붙어 부하가 는다):
  python3 tools/vision/box_overlay.py --live [--candidates] [--hz 10] [--out live.mp4]

화면: 초록 = 발행된 BoxTrack bbox·track_id·OCR 결과, 송장 후보 사각형(흰 = 통과, 빨강 = 가장자리, 주황 = 비율,
보라 = 채움, 회색 = 면적), 빨간 선 = 가장자리 판정선(border_px), 왼쪽 위 = 시각·단계·TCP 높이(박스 윗면 기준).
녹화 재생은 끝에 "발행 끊김"(트랙이 사라진 프레임의 단계·높이·후보 판정)을 찍는다. CSV 는 프레임마다 같은 값.
"""

import argparse
import bisect
import csv
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "voss_vision"))
from voss_vision.box_detect import Candidate, SegParams, detect_candidates  # noqa: E402

T_BOX = "/voss/vision/box"
T_LABEL = "/voss/vision/label"
T_POSE = "/voss/robot/pose"
T_STATE = "/voss/sort/state"
T_FB = "/voss/servo/track_and_grasp/_action/feedback"
IMG_TOPICS = ("/camera/color/image_raw/compressed", "/camera/color/image_raw")

# BGR. 판정 이유별 색과 화면 글자
COLOR = {
    "": (255, 255, 255),
    "border": (0, 0, 255),
    "aspect": (0, 165, 255),
    "fill": (255, 0, 200),
    "area": (150, 150, 150),
}
NAME = {"": "통과", "border": "가장자리", "aspect": "비율", "fill": "채움", "area": "면적"}
TRACK = (0, 230, 0)
SRC = {0: "-", 1: "H", 2: "HE"}  # BoxTrack.position_source: 호모그래피·핸드아이
FONTS = (
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def ns(t) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


def seg_params(path: Path) -> SegParams:
    p = yaml.safe_load(path.read_text())["box_tracker"]["ros__parameters"].get("seg", {})
    return SegParams(**p)


def relevant(c: Candidate, p: SegParams, h_img: int) -> bool:
    """송장일 수 있는 후보만 — 반사 점(작은 면적)과 벨트 열 양옆 바닥 띠(위아래 끝에 닿는 세로 띠)는 뺀다."""
    return c.area >= p.area_min / 2 and c.rect[3] < 0.9 * h_img


def decode(msg, compressed: bool) -> np.ndarray:
    if compressed:
        return cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
    buf = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)[:, : msg.width * 3]
    bgr = buf.reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else bgr.copy()


class Painter:
    """축소한 화면에 도형을 그리고, 글자는 모아 한 번에(한글 폰트가 있으면 PIL, 없으면 OpenCV 영문)."""

    def __init__(self, scale: float, font_px: int = 18) -> None:
        self.scale = scale
        self.font = None
        try:
            from PIL import ImageFont

            for f in FONTS:
                if Path(f).exists():
                    self.font = ImageFont.truetype(f, font_px)
                    break
        except ImportError:
            pass
        self.font_px = font_px

    def render(self, bgr, cands, p: SegParams, tracks, labels, header: list[str]) -> np.ndarray:
        s = self.scale
        img = (
            cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            if s != 1
            else bgr.copy()
        )
        h_img, w_img = bgr.shape[:2]
        texts = []  # (x, y, 글자, 색)
        b = p.border_px
        cv2.rectangle(img, (int(b * s), int(b * s)), (int((w_img - b) * s), int((h_img - b) * s)),
                      (0, 0, 200), 1)  # fmt: skip
        for c in cands:
            if not relevant(c, p, h_img):
                continue
            col = COLOR[c.reason]
            x, y, w, h = c.rect
            if c.rot is not None:
                pts = cv2.boxPoints(c.rot) * s
                cv2.polylines(img, [np.int32(pts)], True, col, 2)
            else:
                cv2.rectangle(
                    img, (int(x * s), int(y * s)), (int((x + w) * s), int((y + h) * s)), col, 2
                )
            note = NAME[c.reason]
            if c.reason == "aspect":
                note += f" {c.aspect:.2f}"
            elif c.reason == "fill":
                note += f" {c.fill:.2f}"
            elif c.reason == "area":
                note += f" {c.area / 1000:.0f}k"
            tx, ty = int(x * s), int((y + h) * s) + 2
            # 화면 아래 끝 후보(하강 LOST 의 그 경우)는 오른쪽에 쓴다 — 위쪽은 트랙 글자 자리
            if ty > img.shape[0] - self.font_px - 4:
                tx, ty = int((x + w) * s) + 4, int(y * s)
            texts.append((tx, ty, f"{note}  아래끝 v{y + h}", col))
        for t in tracks:
            x, y, w, h = t.bbox
            cv2.rectangle(
                img, (int(x * s), int(y * s)), (int((x + w) * s), int((y + h) * s)), TRACK, 2
            )
            line = f"id{t.track_id} {SRC.get(t.position_source, '?')}{'' if t.position_valid else ' 무효'}"
            lab = labels.get(t.track_id)
            if lab is not None:
                line += f"  {lab.code} {lab.dong} {lab.confidence:.2f}"
            texts.append((int(x * s), max(0, int(y * s) - self.font_px - 4), line, TRACK))
        box_h = (self.font_px + 6) * len(header) + 6
        cv2.rectangle(img, (0, 0), (int(min(w_img * s, 760)), box_h), (0, 0, 0), -1)
        for i, line in enumerate(header):
            texts.append((6, 4 + i * (self.font_px + 6), line, (255, 255, 255)))
        return self._texts(img, texts)

    def _texts(self, img, texts):
        if self.font is None:
            for x, y, t, col in texts:
                ascii_t = t.encode("ascii", "replace").decode()
                cv2.putText(img, ascii_t, (x, y + self.font_px), 0, self.font_px / 30, col, 1)
            return img
        from PIL import Image, ImageDraw

        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(pil)
        for x, y, t, col in texts:
            d.text((x, y), t, font=self.font, fill=(col[2], col[1], col[0]),
                   stroke_width=2, stroke_fill=(0, 0, 0))  # fmt: skip
        return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def summarize(cands, p: SegParams, h_img: int) -> tuple[dict[str, int], int | None]:
    """후보 판정 개수(이유별)와 가장 큰 후보의 아래 끝 v."""
    rel = [c for c in cands if relevant(c, p, h_img)]
    count = {r: sum(c.reason == r for c in rel) for r in ("", "border", "aspect", "fill", "area")}
    big = max(rel, key=lambda c: c.area, default=None)
    return count, None if big is None else big.rect[1] + big.rect[3]


def count_text(count: dict[str, int]) -> str:
    return " · ".join(f"{NAME[r]} {n}" for r, n in count.items() if n) or "후보 없음"


# ───────────────────────────── 녹화 재생 ─────────────────────────────


class Series:
    """(시각 ns, 값) 목록 — 어떤 시각 이전의 마지막 값."""

    def __init__(self) -> None:
        self.t: list[int] = []
        self.v: list = []

    def add(self, t: int, v) -> None:
        self.t.append(t)
        self.v.append(v)

    def sort(self) -> None:
        order = sorted(range(len(self.t)), key=self.t.__getitem__)
        self.t = [self.t[i] for i in order]
        self.v = [self.v[i] for i in order]

    def last(self, t: int, max_age_ns: int | None = None):
        i = bisect.bisect_right(self.t, t) - 1
        if i < 0 or (max_age_ns is not None and t - self.t[i] > max_age_ns):
            return None
        return self.v[i]


def open_reader(bag: Path, topics: list[str] | None = None):
    import rosbag2_py

    r = rosbag2_py.SequentialReader()
    r.open(
        rosbag2_py.StorageOptions(uri=str(bag.expanduser())), rosbag2_py.ConverterOptions("", "")
    )
    types = {t.name: t.type for t in r.get_all_topics_and_types()}
    if topics is not None:
        r.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
    return r, types


def read_side(bag: Path):
    """영상 말고 작은 토픽을 먼저 다 읽는다. BoxTrack 은 촬영 stamp 로, 나머지는 bag 수신 시각으로 맞춘다."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    side = [T_BOX, T_LABEL, T_POSE, T_STATE, T_FB]
    r, types = open_reader(bag, side)
    missing = [t for t in (T_BOX, T_POSE, T_FB) if t not in types]
    if missing:
        print(f"⚠ bag 에 없는 토픽: {missing} — 그 칸은 비워 둔다")
    cls = {t: get_message(types[t]) for t in side if t in types}
    boxes: dict[int, list] = {}
    labels, state, phase = Series(), Series(), Series()
    pose_t, pose_z = [], []
    while cls and r.has_next():  # 하나도 없으면 필터가 비어 영상까지 읽으므로 건너뛴다
        topic, data, t_recv = r.read_next()
        m = deserialize_message(data, cls[topic])
        if topic == T_BOX:
            boxes.setdefault(ns(m.stamp), []).append(m)
        elif topic == T_LABEL:
            labels.add(t_recv, m)
        elif topic == T_POSE:
            pose_t.append(ns(m.header.stamp))
            pose_z.append(m.pose.position.z * 1000.0)
        elif topic == T_STATE:
            state.add(t_recv, (m.state, m.track_id))
        elif topic == T_FB:
            phase.add(t_recv, m.feedback.phase)
    for s in (labels, state, phase):
        s.sort()
    order = np.argsort(pose_t)
    return boxes, labels, state, phase, np.asarray(pose_t)[order], np.asarray(pose_z)[order]


def latest_labels(labels: Series, t: int) -> dict:
    """t 까지 받은 LabelRead 중 트랙별 마지막(최근 60 s 만 훑는다)."""
    out = {}
    i = bisect.bisect_right(labels.t, t)
    j = bisect.bisect_left(labels.t, t - 60_000_000_000)
    for m in labels.v[j:i]:
        out[m.track_id] = m
    return out


def run_bag(args, p: SegParams, plane_z: float) -> None:
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    boxes, labels, state, phase, pose_t, pose_z = read_side(args.bag)
    _, types = open_reader(args.bag)
    img_topic = args.image_topic or next((t for t in IMG_TOPICS if t in types), None)
    if img_topic is None:
        sys.exit(f"영상 토픽 없음: {sorted(types)}")
    compressed = types[img_topic].endswith("CompressedImage")
    img_cls = get_message(types[img_topic])
    r, _ = open_reader(args.bag, [img_topic])
    print(
        f"영상 {img_topic}, BoxTrack 프레임 {len(boxes)}, pose {len(pose_t)}, 단계 {len(phase.t)}, 평면 z {plane_z} mm"
    )

    painter = Painter(args.scale)
    writer = None
    rows, cuts = [], []
    prev_ids: set[int] = set()
    open_cut: dict[int, dict] = {}  # 사라진 트랙 → 끊김 기록(다시 나오면 프레임 수를 채운다)
    t0 = None
    paused = False
    n = 0
    while r.has_next():
        _, data, t_recv = r.read_next()
        msg = deserialize_message(data, img_cls)
        t_cam = ns(msg.header.stamp)
        t0 = t_cam if t0 is None else t0
        rel_s = (t_cam - t0) / 1e9
        if rel_s < args.start:
            continue
        if args.end is not None and rel_s > args.end:
            break
        bgr = decode(msg, compressed)
        _, cands = detect_candidates(bgr, p)
        tracks = boxes.get(t_cam, [])
        ids = {m.track_id for m in tracks}
        ph = phase.last(t_recv, 2_000_000_000) or "-"
        st = state.last(t_recv) or ("-", -1)
        h_mm = None
        if len(pose_t):
            i = int(np.searchsorted(pose_t, t_cam))
            if 0 < i < len(pose_t) and pose_t[i] - pose_t[i - 1] < 100_000_000:
                a = (t_cam - pose_t[i - 1]) / (pose_t[i] - pose_t[i - 1])
                h_mm = float(pose_z[i - 1] + a * (pose_z[i] - pose_z[i - 1])) - plane_z
        count, bottom_v = summarize(cands, p, bgr.shape[0])
        h_txt = "-" if h_mm is None else f"{h_mm:+.1f} mm"
        for tid in list(open_cut):  # 앞서 사라진 트랙: 다시 나왔으면 빠진 프레임 수를 적고 닫는다
            if tid in ids:
                ev = open_cut.pop(tid)
                ev["back"] = ev["missing"]
            else:
                open_cut[tid]["missing"] += 1
        for tid in prev_ids - ids:
            ev = {"id": tid, "t": rel_s, "h": h_txt, "phase": ph, "cands": count_text(count),
                  "bottom_v": bottom_v, "missing": 1, "back": None}  # fmt: skip
            cuts.append(ev)
            open_cut[tid] = ev
        prev_ids = ids
        rows.append([f"{rel_s:.3f}", ph, st[0], st[1], "" if h_mm is None else f"{h_mm:.1f}",
                     " ".join(map(str, sorted(ids))), count[""], count["border"], count["aspect"],
                     count["fill"], count["area"], "" if bottom_v is None else bottom_v])  # fmt: skip
        header = [
            f"t {rel_s:7.3f} s   단계 {ph}   상태 {st[0]} (트랙 {st[1]})",
            f"TCP 윗면 {h_txt}   발행 {sorted(ids) or '없음'}",
            f"후보: {count_text(count)}   가장 큰 후보 아래끝 v {bottom_v if bottom_v is not None else '-'} / {bgr.shape[0]}",
        ]
        out = painter.render(bgr, cands, p, tracks, latest_labels(labels, t_recv), header)
        if args.out:
            if writer is None:
                writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), 30.0,
                                         (out.shape[1], out.shape[0]))  # fmt: skip
            writer.write(out)
        if args.show:
            cv2.imshow("box_overlay", out)
            k = cv2.waitKey(0 if paused else 1) & 0xFF  # 멈춤 중이면 아무 키 = 한 프레임
            if k == ord("q"):
                break
            if k == ord(" "):
                paused = not paused
        n += 1
    if writer is not None:
        writer.release()
        print(f"저장 {args.out} ({n}프레임)")
    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "phase", "state", "state_track", "tcp_above_top_mm", "published_ids",
                        "pass", "border", "aspect", "fill", "area", "big_bottom_v"])  # fmt: skip
            w.writerows(rows)
        print(f"저장 {args.csv}")
    print(f"\n발행 끊김 {len(cuts)}건 (트랙이 앞 프레임엔 있었고 이 프레임엔 없음)")
    for ev in cuts:
        back = (f"끝까지 안 나옴({ev['missing']}프레임)" if ev["back"] is None
                else f"{ev['back']}프레임 뒤 다시 나옴")  # fmt: skip
        print(f"  id{ev['id']}  t {ev['t']:.3f} s  단계 {ev['phase']}  TCP 윗면 {ev['h']}  "
              f"후보 {ev['cands']}  가장 큰 후보 아래끝 v {ev['bottom_v']}  → {back}")  # fmt: skip


# ───────────────────────────── 실시간 ─────────────────────────────


def run_live(args, p: SegParams, plane_z: float) -> None:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import CompressedImage, Image

    from voss_msgs.action import TrackAndGrasp
    from voss_msgs.msg import BoxTrack, LabelRead, SortState

    # best_effort 구독은 reliable 발행자와도 맞는다
    be = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

    class Live(Node):
        def __init__(self) -> None:
            super().__init__("box_overlay")
            topic = args.image_topic or IMG_TOPICS[0]
            self.compressed = topic.endswith("compressed")
            self.images: deque = deque(maxlen=15)  # 디코드 안 한 최근 영상(약 0.5 s)
            self.boxes: dict[int, list] = {}
            self.last_box_t = 0
            self.labels: dict[int, LabelRead] = {}
            self.pose_z = None
            self.state = ("-", -1)
            self.phase = ("-", 0.0)
            self.painter = Painter(args.scale)
            self.writer = None
            self.frames = 0
            self.quit = False
            self.create_subscription(CompressedImage if self.compressed else Image, topic,
                                     lambda m: self.images.append(m), be)  # fmt: skip
            self.create_subscription(BoxTrack, T_BOX, self.on_box, be)
            self.create_subscription(
                LabelRead, T_LABEL, lambda m: self.labels.__setitem__(m.track_id, m), be
            )
            self.create_subscription(PoseStamped, T_POSE,
                                     lambda m: setattr(self, "pose_z", m.pose.position.z * 1000.0), be)  # fmt: skip
            self.create_subscription(SortState, T_STATE,
                                     lambda m: setattr(self, "state", (m.state, m.track_id)), be)  # fmt: skip
            self.create_subscription(TrackAndGrasp.Impl.FeedbackMessage, T_FB,
                                     lambda m: setattr(self, "phase", (m.feedback.phase, time.monotonic())), be)  # fmt: skip
            self.create_timer(1.0 / args.hz, self.tick)
            self.get_logger().info(
                f"{topic} 구독, {args.hz} Hz 그리기, 후보 {'표시' if args.candidates else '끔'} — q 로 끝"
            )

        def on_box(self, m: BoxTrack) -> None:
            t = ns(m.stamp)
            self.boxes.setdefault(t, []).append(m)
            self.last_box_t = max(self.last_box_t, t)
            for old in [k for k in self.boxes if k < t - 1_000_000_000]:
                del self.boxes[old]

        def tick(self) -> None:
            if not self.images:
                return
            # 마지막 BoxTrack 과 같은 촬영 시각의 영상이 있으면 그것(박스와 화면이 맞는다), 없으면 최신 영상
            msg = next(
                (m for m in self.images if ns(m.header.stamp) == self.last_box_t), self.images[-1]
            )
            t = ns(msg.header.stamp)
            bgr = decode(msg, self.compressed)
            cands = detect_candidates(bgr, p)[1] if args.candidates else []
            tracks = self.boxes.get(t, [])
            ph = self.phase[0] if time.monotonic() - self.phase[1] < 2.0 else "-"
            h_txt = "-" if self.pose_z is None else f"{self.pose_z - plane_z:+.1f} mm"
            header = [
                f"단계 {ph}   상태 {self.state[0]} (트랙 {self.state[1]})   TCP 윗면 {h_txt}",
                f"발행 {sorted(m.track_id for m in tracks) or '없음'}"
                + (
                    f"   후보: {count_text(summarize(cands, p, bgr.shape[0])[0])}"
                    if args.candidates
                    else ""
                ),
            ]
            out = self.painter.render(bgr, cands, p, tracks, self.labels, header)
            if args.out:
                if self.writer is None:
                    self.writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"),
                                                  float(args.hz), (out.shape[1], out.shape[0]))  # fmt: skip
                self.writer.write(out)
            self.frames += 1
            if not args.no_window:
                cv2.imshow("box_overlay", out)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.quit = True

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = Live()
    try:
        while rclpy.ok() and not node.quit:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if node.writer is not None:
            node.writer.release()
            print(f"저장 {args.out} ({node.frames}프레임)")
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.try_shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bag", type=Path, nargs="?", help="녹화 폴더 (--live 면 생략)")
    ap.add_argument("--live", action="store_true", help="실시간 토픽 구독")
    ap.add_argument("--image-topic", help=f"기본: {IMG_TOPICS[0]} (녹화는 있는 것)")
    ap.add_argument("--params", type=Path, default=REPO / "src/voss_vision/config/box_tracker.yaml",
                    help="seg 파라미터 — box_tracker 와 같은 파일")  # fmt: skip
    ap.add_argument("--homography", type=Path, default=REPO / "config/belt_homography.yaml",
                    help="plane_z_mm(박스 윗면 z) — TCP 높이를 윗면 기준으로 보인다")  # fmt: skip
    ap.add_argument("--scale", type=float, default=0.5, help="화면·영상 크기 (기본 1/2)")
    ap.add_argument("--out", type=Path, help="mp4 로 저장")
    ap.add_argument("--start", type=float, default=0.0, help="녹화 재생: 첫 영상 기준 시작 s")
    ap.add_argument("--end", type=float, help="녹화 재생: 끝 s")
    ap.add_argument("--csv", type=Path, help="녹화 재생: 프레임별 값")
    ap.add_argument(
        "--show",
        action="store_true",
        help="녹화 재생: 창으로 보기 (스페이스 멈춤·한 프레임씩, q 끝)",
    )
    ap.add_argument(
        "--candidates", action="store_true", help="실시간: 후보·버린 이유도 (CPU 를 더 쓴다)"
    )
    ap.add_argument("--hz", type=float, default=10.0, help="실시간: 그리는 주기")
    ap.add_argument(
        "--no-window", action="store_true", help="실시간: 창 없이 --out 녹화만 (화면 없는 곳)"
    )
    args = ap.parse_args()
    p = seg_params(args.params)
    plane_z = float(yaml.safe_load(args.homography.read_text())["plane_z_mm"])
    if args.live:
        run_live(args, p, plane_z)
    elif args.bag is None:
        ap.error("녹화 폴더를 주거나 --live")
    else:
        run_bag(args, p, plane_z)


if __name__ == "__main__":
    main()
