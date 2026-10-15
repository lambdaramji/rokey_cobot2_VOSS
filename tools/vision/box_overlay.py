"""box_tracker 시각화 — 카메라 화면에 송장 후보·버린 이유·발행된 BoxTrack·OCR 결과를 덧그린다. 사람이 실행, 구독만(로봇과 무관).

목적(T21 #30): 하강 중 Box LOST 원인 찾기. 언제 발행이 끊겼는지(BoxTrack)와 그 프레임에서 송장 후보를 왜 버렸는지
(`box_detect.detect_candidates`: 면적·가장자리·비율·채움)를 한 화면에서 본다. 판정은 box_tracker 와 같은 함수·같은
seg 파라미터(`src/voss_vision/config/box_tracker.yaml`)다.

녹화 재생(주) — G1 bag(g0-runbook 3절 녹화 명령의 토픽). voss_msgs 가 빌드된 워크스페이스를 source 한다:
  source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash
  python3 tools/vision/box_overlay.py ~/voss_data/1010/g1_s1_clips/g1_s1_t26_170050 [--start 12 --end 30] [--out t26.mp4] [--csv t26.csv] [--show]
  (잘라낸 bag 은 액션 feedback·status 의 message definition 이 비어 있을 수 있다 — 이 도구는 설치된 voss_msgs 로 읽어 상관없다)
실시간 — 공용 PC, 10/11 통합부터. 게이트 측정 중에는 띄우지 않는다(영상 구독이 하나 더 붙어 부하가 는다):
  python3 tools/vision/box_overlay.py --live [--candidates] [--hz 10] [--out live.mp4]

화면: 초록 = 발행된 BoxTrack bbox와 위 가운데 `BOX<번호> <채움 %>`(+ OCR 결과). 번호 = sort_manager box_id 끝 순번
(`/voss/sort/state`·`/voss/sort/result` 의 box_id ↔ track_id, OCR 판정 때 발급) — 아직 없으면 번호 없이 `BOX`. 번호는 지금
세션 것만(새 start 면 버림, 트랙이 새로 나타나면 — box_tracker 재시작으로 같은 track_id 가 다시 쓰여도 — 버림). 노랑 = 각도 `yaw +45°`·송장 긴 축, 송장 후보 사각형(흰 = 통과, 빨강 = 가장자리, 주황 = 비율,
보라 = 채움, 회색 = 면적), 빨간 선 = 가장자리 판정선(border_px), 왼쪽 위 = 시각·단계·TCP 높이(박스 윗면 기준).
채움 % = 그 트랙과 짝지은 송장 후보의 채움(윤곽 면적 / 회전 사각형 면적 = box_detect score, fill_min 80 % 이상만 통과).
학습 모델의 신뢰도가 아니라 seg 판정값이다. 짝이 없으면 `-%`, 실시간 --no-score 면 % 를 안 쓴다. 각도 숫자는 BoxTrack 에 yaw 필드가 있는 빌드(S2-T16 v15)에서만 — 베이스 +X 기준,
반시계 +, (−90, 90], 1° 단위(벨트 기준과는 약 0.7° 차). 노란 선은 같은 프레임 송장 후보의 긴 축(픽셀)이라 yaw 필드가 없어도 그린다.
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
T_RESULT = "/voss/sort/result"
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
ANGLE = (0, 230, 255)  # 노랑 — 각도만 (의석 제안 10/14: bbox·글자는 초록, 각도는 노랑)
MATCH_PX = 40  # 트랙 중심과 송장 후보 중심이 이 안이면 같은 박스
# 이만큼 안 보이다 다시 나온 track_id 는 새 트랙 — box_tracker 는 max_missed 15 프레임(0.5 s) 못 본 트랙을 지운다
NEW_GAP_NS = 600_000_000
# 그보다 짧게 끊겼다 나온 같은 track_id 는 앞 관측의 속도로 예측한 자리에서 이만큼 벗어나면 다른 박스(빠른 재시작).
# 끊김이 이보다 짧으면(3 프레임 안) 보지 않는다 — 그리퍼 카메라가 움직이는 동안의 큰 픽셀 이동으로 잘못 버리지 않게
JUMP_PX = 80
JUMP_MIN_GAP_NS = 100_000_000
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


def match_candidate(t, cands) -> Candidate | None:
    """발행된 트랙과 같은 프레임의 통과 후보 중 중심이 가장 가까운 것(MATCH_PX 안) — 채움 %·긴 축용."""
    best, best_d = None, MATCH_PX
    for c in cands:
        if c.det is None:
            continue
        d = float(np.hypot(c.det.u - t.u, c.det.v - t.v))
        if d <= best_d:
            best, best_d = c, d
    return best


def box_seq(box_id: str) -> int | None:
    """sort_manager box_id `<session_id>-<3자리 순번>` → 순번(int). 형식이 아니면 None."""
    tail = box_id.rsplit("-", 1)[-1] if box_id else ""
    return int(tail) if tail.isdigit() else None


class BoxNumbers:
    """track_id → sort_manager 순번. 번호는 지금 세션 것만 쓴다 — 세션이 바뀌면(새 start) 앞 세션 번호를 버린다.

    box_tracker 를 다시 띄우면 track_id 가 1 부터 다시 매겨져 앞 박스 번호가 새 박스에 붙을 수 있다(#49 리뷰). 번호는
    트랙이 보이는 동안 OCR 판정으로 발급되므로, 새 트랙이 가진 번호는 앞 트랙 것이다 — 그래서 아래 경우 번호를 버린다.
    - restart(): box_tracker 가 바뀌었다(실시간: /voss/vision/box 발행자 GID 가 바뀜) → 전부. 재시작 간격과 무관
    - 처음 보거나 NEW_GAP_NS 넘게 안 보이다 나온 track_id (tracker 가 이미 지웠을 트랙)
    - JUMP_MIN_GAP_NS~NEW_GAP_NS 끊겼다 나왔는데 예측 자리에서 JUMP_PX 넘게 벗어난 track_id (녹화 재생의 빠른 재시작)
    지금 처리 중인 박스는 SortState(0.4 s 주기)가 곧 다시 붙인다(가려졌다 나온 PICKING 트랙)."""

    def __init__(self) -> None:
        self.session = ""
        self.no: dict[int, int] = {}
        self.seen: dict[int, tuple] = {}  # track_id → (촬영 시각 ns, u, v, du/ns, dv/ns)

    def restart(self) -> None:
        """box_tracker 가 바뀌었다 — 모든 track_id 의 번호와 관측을 버린다."""
        self.no.clear()
        self.seen.clear()

    def sort_msg(self, box_id: str, track_id: int, session_id: str = "") -> None:
        """SortState·SortResult 한 건. session_id 가 없는 옛 빌드는 box_id 앞부분(`<session_id>-`)으로 안다."""
        seq = box_seq(box_id)
        session = session_id or (box_id.rsplit("-", 1)[0] if seq is not None else "")
        if session and session != self.session:
            self.session = session
            self.no.clear()
        if seq is not None and track_id >= 0:
            self.no[track_id] = seq

    def tracks(self, t_ns: int, tracks) -> None:
        """이 촬영 시각에 발행된 트랙들(track_id·u·v)."""
        for t in tracks:
            tid, last = t.track_id, self.seen.get(t.track_id)
            du = dv = 0.0
            if last is None or t_ns - last[0] > NEW_GAP_NS:
                self.no.pop(tid, None)
            else:
                dt = t_ns - last[0]
                miss = np.hypot(t.u - (last[1] + last[3] * dt), t.v - (last[2] + last[4] * dt))
                if dt > JUMP_MIN_GAP_NS and miss > JUMP_PX:
                    self.no.pop(tid, None)
                elif dt > 0:
                    du, dv = (t.u - last[1]) / dt, (t.v - last[2]) / dt
            self.seen[tid] = (t_ns, t.u, t.v, du, dv)

    def label(self, track_id: int) -> str:
        """초록 글자의 앞부분 — sort_manager 순번이 있으면 BOX7, 아직 없으면(판독 전·manager 없음) BOX."""
        n = self.no.get(track_id)
        return f"BOX{n}" if n is not None else "BOX"


def yaw_text(t) -> str | None:
    """BoxTrack yaw(S2-T16 v15 필드) → 'yaw +45.0°'. 필드가 없거나 무효면 None."""
    if not getattr(t, "yaw_valid", False):
        return None
    d = (np.degrees(t.yaw_base) + 90.0) % 180.0 - 90.0
    return f"yaw {round(90.0 if d == -90.0 else d):+d}°"


def decode(msg, compressed: bool) -> np.ndarray:
    if compressed:
        return cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
    buf = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)[:, : msg.width * 3]
    bgr = buf.reshape(msg.height, msg.width, 3)
    return cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else bgr.copy()


class Painter:
    """축소한 화면에 도형을 그리고, 글자는 모아 한 번에(한글 폰트가 있으면 PIL, 없으면 OpenCV 영문)."""

    def __init__(self, scale: float, font_px: int = 14) -> None:
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

    def render(
        self,
        bgr,
        cands,
        p: SegParams,
        tracks,
        labels,
        header: list[str],
        score_cands=None,
        box_no: BoxNumbers | None = None,
        score: bool = True,
    ) -> np.ndarray:
        """score_cands: 채움 %·긴 축을 찾을 후보(기본 = cands). 실시간에서 후보는 그리지 않고 % 만 볼 때 따로 준다.
        box_no: sort_manager 순번. score=False(실시간 --no-score)면 % 를 쓰지 않는다 — `-%` 는 판정은 했는데 짝이 없을 때만."""
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
            c = match_candidate(t, cands if score_cands is None else score_cands)
            line = box_no.label(t.track_id) if box_no is not None else "BOX"
            if score:
                line += f" {c.fill * 100:.0f}%" if c is not None else " -%"
            if not t.position_valid:
                line += " 무효"
            lab = labels.get(t.track_id)
            if lab is not None:
                line += f"  {lab.code} {lab.dong} {lab.confidence:.2f}"
            cx_txt = int((x + w / 2) * s)  # bbox 위 가운데 정렬
            texts.append((cx_txt, max(0, int(y * s) - self.font_px - 4), line, TRACK, True))
            if c is not None and c.rot is not None:  # 송장 긴 축 (노랑)
                (cx, cy), (rw, rh), ang = c.rot
                a = np.radians(ang if rw >= rh else ang + 90.0)
                half = 0.6 * max(rw, rh)
                dx, dy = half * np.cos(a), half * np.sin(a)
                cv2.line(img, (int((cx - dx) * s), int((cy - dy) * s)),
                         (int((cx + dx) * s), int((cy + dy) * s)), ANGLE, 2)  # fmt: skip
            yt = yaw_text(t)
            if yt is not None:
                # 초록 줄 바로 위, 가운데 정렬 — 오른쪽은 레일 후보 글자와 겹친다
                texts.append((cx_txt, max(0, int(y * s) - 2 * (self.font_px + 4)), yt, ANGLE, True))
        box_h = (self.font_px + 6) * len(header) + 6
        cv2.rectangle(img, (0, 0), (int(min(w_img * s, 760)), box_h), (0, 0, 0), -1)
        for i, line in enumerate(header):
            texts.append((6, 4 + i * (self.font_px + 6), line, (255, 255, 255)))
        return self._texts(img, texts)

    def _texts(self, img, texts):
        """texts: (x, y, 글자, 색[, 가운데]) — 가운데면 x 가 글자 가운데."""
        if self.font is None:
            for x, y, t, col, *center in texts:
                ascii_t = t.encode("ascii", "replace").decode()
                if center and center[0]:
                    x = max(0, x - cv2.getTextSize(ascii_t, 0, self.font_px / 30, 1)[0][0] // 2)
                cv2.putText(img, ascii_t, (x, y + self.font_px), 0, self.font_px / 30, col, 1)
            return img
        from PIL import Image, ImageDraw

        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(pil)
        for x, y, t, col, *center in texts:
            if center and center[0]:
                x = max(0, int(x - self.font.getlength(t) / 2))
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

    side = [T_BOX, T_LABEL, T_POSE, T_STATE, T_RESULT, T_FB]
    r, types = open_reader(bag, side)
    missing = [t for t in (T_BOX, T_POSE, T_FB) if t not in types]
    if missing:
        print(f"⚠ bag 에 없는 토픽: {missing} — 그 칸은 비워 둔다")
    cls = {t: get_message(types[t]) for t in side if t in types}
    boxes: dict[int, list] = {}
    labels, state, phase = Series(), Series(), Series()
    numbering = Series()  # (box_id, track_id, session_id) — 그 시각부터 BoxNumbers 에 넣는다
    pose_t, pose_z = [], []
    bad: dict[
        str, int
    ] = {}  # 설치된 voss_msgs 와 정의가 다른 옛 녹화(예: 10/12 SortResult) — 건너뛴다
    while cls and r.has_next():  # 하나도 없으면 필터가 비어 영상까지 읽으므로 건너뛴다
        topic, data, t_recv = r.read_next()
        try:
            m = deserialize_message(data, cls[topic])
        except Exception:  # rclpy 는 RMWError 를 낸다
            bad[topic] = bad.get(topic, 0) + 1
            continue
        if topic == T_BOX:
            boxes.setdefault(ns(m.stamp), []).append(m)
        elif topic == T_LABEL:
            labels.add(t_recv, m)
        elif topic == T_POSE:
            pose_t.append(ns(m.header.stamp))
            pose_z.append(m.pose.position.z * 1000.0)
        elif topic in (T_STATE, T_RESULT):
            if topic == T_STATE:
                state.add(t_recv, (m.state, m.track_id))
            numbering.add(t_recv, (m.box_id, m.track_id, getattr(m, "session_id", "")))
        elif topic == T_FB:
            phase.add(t_recv, m.feedback.phase)
    for t, n in bad.items():
        print(f"⚠ {t} {n}건 못 읽음(설치된 voss_msgs 와 녹화 당시 정의가 다름) — 그 칸은 비워 둔다")
    for s in (labels, state, phase, numbering):
        s.sort()
    order = np.argsort(pose_t)
    pose = (np.asarray(pose_t)[order], np.asarray(pose_z)[order])
    return boxes, labels, state, phase, numbering, *pose


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

    boxes, labels, state, phase, numbering, pose_t, pose_z = read_side(args.bag)
    box_no = BoxNumbers()  # 이 프레임까지 받은 SortState·SortResult 로 정한 번호
    n_num = 0
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
        while n_num < len(numbering.t) and numbering.t[n_num] <= t_recv:
            box_no.sort_msg(*numbering.v[n_num])
            n_num += 1
        box_no.tracks(t_cam, tracks)
        out = painter.render(
            bgr, cands, p, tracks, latest_labels(labels, t_recv), header, box_no=box_no
        )
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
    from voss_msgs.msg import BoxTrack, LabelRead, SortResult, SortState

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
            self.box_no = BoxNumbers()
            self.box_pubs: set[bytes] = set()  # box 발행자 GID — 바뀌면 tracker 재시작
            self.pose_z = None
            self.state = ("-", -1)
            self.phase = ("-", 0.0)
            self.painter = Painter(args.scale)
            self.writer = None
            self.frames = 0
            self.n_box = self.n_sync = 0  # 박스가 보일 때 그린 프레임 / 그중 BoxTrack 과 같은 시각
            self.lag_ms: list[float] = []  # 그린 영상이 최신 영상보다 늦은 정도
            self.quit = False
            self.create_subscription(CompressedImage if self.compressed else Image, topic,
                                     lambda m: self.images.append(m), be)  # fmt: skip
            self.create_subscription(BoxTrack, T_BOX, self.on_box, be)
            self.create_subscription(
                LabelRead, T_LABEL, lambda m: self.labels.__setitem__(m.track_id, m), be
            )
            self.create_subscription(PoseStamped, T_POSE,
                                     lambda m: setattr(self, "pose_z", m.pose.position.z * 1000.0), be)  # fmt: skip
            self.create_subscription(SortState, T_STATE, self.on_state, be)
            self.create_subscription(SortResult, T_RESULT, self.on_numbered, be)
            self.create_subscription(TrackAndGrasp.Impl.FeedbackMessage, T_FB,
                                     lambda m: setattr(self, "phase", (m.feedback.phase, time.monotonic())), be)  # fmt: skip
            self.create_timer(1.0 / args.hz, self.tick)
            self.create_timer(0.1, self.check_tracker)
            self.get_logger().info(
                f"{topic} 구독, {args.hz} Hz 그리기, 후보 {'표시' if args.candidates else '끔'}, "
                f"채움 % {'끔' if args.no_score and not args.candidates else '표시'} — q 로 끝"
            )

        def on_numbered(self, m) -> None:
            """SortState·SortResult 의 box_id 끝 순번을 그 track_id 에 붙인다(sort_manager 와 같은 번호)."""
            self.box_no.sort_msg(m.box_id, m.track_id, getattr(m, "session_id", ""))

        def on_state(self, m: SortState) -> None:
            self.state = (m.state, m.track_id)
            self.on_numbered(m)

        def check_tracker(self) -> None:
            """box_tracker 가 다시 떴으면(발행자 GID 가 바뀜) 번호를 모두 버린다. 발행자가 없는 동안은 앞 값을 둔다."""
            gids = {bytes(i.endpoint_gid) for i in self.get_publishers_info_by_topic(T_BOX)}
            if gids and gids != self.box_pubs:
                if self.box_pubs:
                    self.get_logger().info("box_tracker 가 바뀜(발행자 GID) — BOX 번호를 모두 버림")
                    self.box_no.restart()
                self.box_pubs = gids

        def on_box(self, m: BoxTrack) -> None:
            t = ns(m.stamp)
            last = self.box_no.seen.get(m.track_id)
            if m.track_id in self.box_no.no and (last is None or t - last[0] > JUMP_MIN_GAP_NS):
                self.check_tracker()  # 번호 있는 트랙이 끊겼다 나오면 타이머(0.1 s)를 기다리지 않고 바로 확인
            self.boxes.setdefault(t, []).append(m)
            self.box_no.tracks(t, (m,))
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
            newest = ns(self.images[-1].header.stamp)
            if self.last_box_t and newest - self.last_box_t < 1_000_000_000:
                self.n_box += 1
                self.n_sync += t == self.last_box_t
                self.lag_ms.append((newest - t) / 1e6)
            bgr = decode(msg, self.compressed)
            # 채움 % 를 내려면 같은 판정이 필요하다 — 후보 사각형은 --candidates 일 때만 그린다
            score = args.candidates or not args.no_score
            scored = detect_candidates(bgr, p)[1] if score else []
            cands = scored if args.candidates else []
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
            out = self.painter.render(
                bgr, cands, p, tracks, self.labels, header, score_cands=scored,
                box_no=self.box_no, score=score,
            )  # fmt: skip
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
        if node.n_box:
            lag = np.asarray(node.lag_ms)
            print(f"그린 프레임 {node.frames}, 박스가 보일 때 {node.n_box} 중 BoxTrack 과 같은 촬영 시각 "
                  f"{node.n_sync} ({100 * node.n_sync / node.n_box:.0f} %), 최신 영상보다 늦음 "
                  f"중앙 {np.median(lag):.0f} ms · 최대 {lag.max():.0f} ms")  # fmt: skip
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
    ap.add_argument(
        "--no-score",
        action="store_true",
        help="실시간: 채움 %%·긴 축 끄기 (판정을 안 돌려 CPU 를 덜 쓴다)",
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
