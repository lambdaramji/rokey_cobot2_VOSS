"""영상-pose 지연(box_tracker `pose_lag_ms`)과 이동 중 좌표 오차를 녹화 하나로 잰다. 사람이 실행, 로봇과 무관(오프라인).

녹화 조건(10/10 체크리스트 2번, measurements): 박스 1개를 벨트 위에 세워 두고(벨트 정지) 로봇만 움직인다.
- 이동 전후마다 관측 자세에서 **약 3 s 정지** — 정지 프레임이 기준점(핸드아이 고정 오차)을 잡는다
- +x 한 방향이면 충분하다(왕복 불필요). 속도 둘(예 20·48 mm/s) — 오차가 속도에 비례하는 부분만 지연이다
- 토픽: `/camera/color/image_raw/compressed`(또는 `image_raw`), `/camera/color/camera_info`, `/voss/robot/pose`

계산은 box_tracker 와 같다: 분할 검출(SegParams 기본값 = box_tracker.yaml) → 트래커 → 촬영 시각 + lag 의 pose 보간
(80 ms 까지 외삽) → `T_tcp_camera` → 박스 윗면 평면(z = belt_homography `plane_z_mm`) 교점. 순수 계산은
`voss_vision/pose_lag.py`(pytest).

  source /opt/ros/jazzy/setup.bash
  python3 tools/calib/pose_lag_eval.py ~/voss_data/1010/pose_lag_js_01 \
      --hand-eye config/hand_eye.yaml --homography config/belt_homography.yaml [--lags=-20:150:5] [--csv out.csv]

출력: lag 별 이동 프레임 RMS·최대, 고른 lag, 기울기로 추정한 남은 지연, pose 값 갱신 간격(0.1 s 면 service 계단, #118),
판정(이동 중 최대 ≤ 5 mm, calibration.md). 결과는 measurements 와 box_tracker `pose_lag_ms` 결정에 쓴다.
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from voss_vision.box_detect import SegParams, detect_boxes  # noqa: E402
from voss_vision.box_track import Tracker  # noqa: E402
from voss_vision.hand_eye import pose_msg_to_t  # noqa: E402
from voss_vision.pose_lag import (  # noqa: E402
    MOVING_MAX_MM,
    Frame,
    best,
    classify,
    positions,
    sweep,
    value_update_interval_s,
)

POSE_TOPIC = "/voss/robot/pose"


def stamp_s(t) -> float:
    return t.sec + t.nanosec * 1e-9


def read_bag(path: Path, image_topic: str | None):
    """(이미지 [(t, bgr)] 생성기용 목록, pose stamps, pose T 목록). 이미지는 메모리를 아끼려고 검출까지 바로 한다."""
    import rosbag2_py
    from geometry_msgs.msg import PoseStamped
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import CompressedImage, Image

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path.expanduser())), rosbag2_py.ConverterOptions("", "")
    )
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    if image_topic is None:
        cands = [
            n for n, k in types.items() if k == "sensor_msgs/msg/CompressedImage" and "color" in n
        ]
        cands += [n for n, k in types.items() if k == "sensor_msgs/msg/Image" and "color" in n]
        if not cands:
            sys.exit(f"영상 토픽 없음: {sorted(types)}")
        image_topic = cands[0]
    if POSE_TOPIC not in types:
        sys.exit(f"{POSE_TOPIC} 없음: {sorted(types)}")
    print(f"영상 {image_topic} ({types[image_topic]}), pose {POSE_TOPIC}")
    stamps, poses, images = [], [], []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic == POSE_TOPIC:
            m = deserialize_message(data, PoseStamped)
            p, q = m.pose.position, m.pose.orientation
            stamps.append(stamp_s(m.header.stamp))
            poses.append(pose_msg_to_t([p.x, p.y, p.z], [q.x, q.y, q.z, q.w]))
        elif topic == image_topic:
            if types[topic] == "sensor_msgs/msg/CompressedImage":
                m = deserialize_message(data, CompressedImage)
                bgr = cv2.imdecode(np.frombuffer(m.data, np.uint8), cv2.IMREAD_COLOR)
            else:
                m = deserialize_message(data, Image)
                buf = np.frombuffer(m.data, np.uint8).reshape(m.height, m.step)[:, : m.width * 3]
                bgr = buf.reshape(m.height, m.width, 3)
                if m.encoding == "rgb8":
                    bgr = cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)
            images.append((stamp_s(m.header.stamp), bgr))
    order = np.argsort(stamps)
    return images, [stamps[i] for i in order], [poses[i] for i in order]


def track_frames(images, seg: SegParams) -> tuple[list[Frame], int]:
    """box_tracker 와 같은 검출·트래커로 가장 오래 이어진 트랙 하나의 프레임 목록(그 프레임에 검출된 것만)."""
    tracker = Tracker(max_missed=15, gate_px=120.0, min_hits=5)
    per_track: dict[int, list[Frame]] = {}
    for t, bgr in sorted(images, key=lambda x: x[0]):
        for tr in tracker.update(detect_boxes(bgr, seg)):
            if tr.missed == 0:
                per_track.setdefault(tr.id, []).append(Frame(t, float(tr.u), float(tr.v)))
    if not per_track:
        return [], 0
    main = max(per_track.values(), key=len)
    return main, len(per_track)


def parse_lags(text: str) -> list[float]:
    a, b, s = (float(x) for x in text.split(":"))
    return [float(x) for x in np.arange(a, b + s / 2, s)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bag", type=Path)
    ap.add_argument("--hand-eye", type=Path, default=Path("config/hand_eye.yaml"))
    ap.add_argument("--homography", type=Path, default=Path("config/belt_homography.yaml"),
                    help="plane_z_mm(박스 윗면 평면) 을 여기서 읽는다")  # fmt: skip
    ap.add_argument("--plane-z", type=float, help="박스 윗면 평면 z(mm), 주면 --homography 대신")
    ap.add_argument("--image-topic")
    ap.add_argument(
        "--lags",
        default="-20:150:5",
        help="시작:끝:간격 (ms). 음수로 시작하면 --lags=-20:150:5 처럼 = 로 붙인다",
    )
    ap.add_argument("--csv", type=Path, help="고른 lag 의 프레임별 좌표")
    args = ap.parse_args()

    he = yaml.safe_load(args.hand_eye.read_text())
    t_tcp_cam = np.asarray(he["T_tcp_camera"], float)
    k = np.asarray(he["camera"]["k"], float).reshape(3, 3)
    d = np.asarray(he["camera"].get("d") or [0.0] * 5, float)
    plane_z = args.plane_z
    if plane_z is None:
        plane_z = float(yaml.safe_load(args.homography.read_text())["plane_z_mm"])

    images, stamps, poses = read_bag(args.bag, args.image_topic)
    if len(stamps) < 10 or not images:
        sys.exit(f"pose {len(stamps)}개·영상 {len(images)}장 — 너무 적다")
    frames, n_tracks = track_frames(images, SegParams())
    del images
    dur = stamps[-1] - stamps[0]
    upd = value_update_interval_s(stamps, poses)
    print(f"영상 {len(frames)}장(트랙 {n_tracks}개 중 가장 긴 것), pose {len(stamps)}개 "
          f"{len(stamps) / dur:.1f} Hz, 값 갱신 간격 중앙값 "
          f"{'-' if upd is None else f'{upd * 1000:.0f} ms'}, 평면 z {plane_z} mm")  # fmt: skip
    if upd is not None and upd > 0.05:
        print("  ⚠ pose 값이 계단으로 바뀐다(service 0.1 s, #118) — 고른 lag 에 계단 지연이 섞인다")
    labels = classify(frames, stamps, poses)
    n_still = sum(lab == "still" for _, lab in labels)
    n_move = sum(lab == "moving" for _, lab in labels)
    print(f"정지 프레임 {n_still}, 이동 프레임 {n_move} (속도 < 2 mm/s 정지, ≥ 5 mm/s 이동)")
    if n_still < 10 or n_move < 10:
        sys.exit("정지·이동 프레임이 모자란다 — 이동 전후에 3 s 씩 세워 두고 다시 녹화")

    res = sweep(frames, stamps, poses, t_tcp_cam, k, d, plane_z, parse_lags(args.lags))
    print("\n lag(ms)  이동 RMS  이동 최대  정지 최대  남은 지연 추정(ms)")
    for r in res:
        print(f" {r.lag_ms:7.0f}  {r.moving_rms_mm:8.2f}  {r.moving_max_mm:8.2f}  "
              f"{r.still_max_mm:8.2f}  {r.residual_ms:+8.0f}")  # fmt: skip
    b = best(res)
    if b is None:
        sys.exit("이동 프레임 결과가 없다")
    ok = b.moving_max_mm <= MOVING_MAX_MM
    print(f"\n고른 lag {b.lag_ms:.0f} ms — 이동 RMS {b.moving_rms_mm:.2f}·최대 {b.moving_max_mm:.2f} mm, "
          f"정지 최대 {b.still_max_mm:.2f} mm, 기울기 확인 {b.lag_ms + b.residual_ms:.0f} ms, "
          f"기준점 ({b.ref_xy[0]:.1f}, {b.ref_xy[1]:.1f}) mm")  # fmt: skip
    print(f"판정: 이동 중 최대 {'≤' if ok else '>'} {MOVING_MAX_MM} mm → "
          f"{'통과 — box_tracker pose_lag_ms 후보' if ok else '미달 — 이 소스로 이동 중 좌표를 믿지 않는다'}")  # fmt: skip

    if args.csv:
        xy = positions(frames, stamps, poses, t_tcp_cam, k, d, plane_z, b.lag_ms / 1000.0)
        with args.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "u", "v", "label", "x_mm", "y_mm", "err_mm"])
            for fr, (_, lab), p in zip(frames, labels, xy, strict=True):
                err = float(np.hypot(p[0] - b.ref_xy[0], p[1] - b.ref_xy[1]))
                w.writerow([f"{fr.t:.4f}", f"{fr.u:.1f}", f"{fr.v:.1f}", lab, f"{p[0]:.2f}",
                            f"{p[1]:.2f}", f"{err:.2f}"])  # fmt: skip
        print(f"저장 {args.csv}")


if __name__ == "__main__":
    main()
