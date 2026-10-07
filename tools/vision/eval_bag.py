"""T17 오프라인 평가: 녹화 bag → 분할 검출(seg) + 트래커 → 요약·확인 시트·(선택) YOLO 자동 라벨.

정답 라벨이 없으므로 대리 지표를 낸다(정답셋 200장 평가는 10/08, ADR-0004 #69):
- 오검출: 박스가 없는 bag(B_EMPTY)에서 검출된 프레임 수 (손 포함)
- 트랙: 박스마다 트랙 하나인지, 트랙 첫~끝 프레임 사이 빠진 프레임(구간 검출률)
- 지연: 프레임당 검출+추적 시간 (개인 PC CPU 는 참고값, 완료 수치는 공용 PC)

  source /opt/ros/jazzy/setup.bash
  python3 tools/vision/eval_bag.py <bag_dir> [--sheet out.jpg] [--export-yolo DIR --stride 3]
"""

import argparse
import csv
import random
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import CompressedImage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from voss_vision.box_detect import detect_boxes  # noqa: E402
from voss_vision.box_track import Tracker  # noqa: E402


def frames(bag_dir: Path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag_dir)), rosbag2_py.ConverterOptions("", ""))
    topic = next(
        t.name for t in reader.get_all_topics_and_types() if t.name.endswith("image_raw/compressed")
    )
    reader.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    i = 0
    while reader.has_next():
        _, data, _ = reader.read_next()
        msg = deserialize_message(data, CompressedImage)
        yield i, cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        i += 1


def overlay(img, dets, tracks, label: str):
    v = img.copy()
    for d in dets:
        x, y, w, h = d.bbox
        cv2.rectangle(v, (x, y), (x + w, y + h), (0, 0, 255), 3)
        cv2.drawMarker(v, (int(d.u), int(d.v)), (255, 0, 255), cv2.MARKER_CROSS, 40, 3)
    for t in tracks:
        cv2.putText(v, f"id{t.id}", (int(t.u) + 30, int(t.v)), 0, 1.2, (0, 255, 255), 3)
    v = cv2.resize(v[:, 760:1500], (370, 540))
    cv2.putText(v, label, (5, 25), 0, 0.7, (0, 0, 255), 2)
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bag", type=Path)
    ap.add_argument("--sheet", type=Path, help="검출 프레임·트랙 공백 프레임 확인 시트(jpg)")
    ap.add_argument("--export-yolo", type=Path, help="YOLO 자동 라벨 폴더 (images/, labels/)")
    ap.add_argument("--stride", type=int, default=3, help="YOLO 내보내기 간격")
    ap.add_argument("--neg-stride", type=int, default=30, help="박스 없는 프레임 내보내기 간격")
    ap.add_argument("--min-hits", type=int, default=5, help="이만큼 검출된 트랙만 확정(발행)")
    ap.add_argument(
        "--frames", default=":", help="내보내기·시트 프레임 범위 a:b (추적은 처음부터 돈다)"
    )
    ap.add_argument(
        "--frames-csv",
        type=Path,
        help="프레임마다 확정 트랙 id·bbox 를 CSV 로 (정답 확인 시트 고르기용, make_check_sheets.py)",
    )
    args = ap.parse_args()
    lo, hi = (int(x) if x else None for x in args.frames.split(":"))

    tr = Tracker(min_hits=args.min_hits)
    per_frame, raw_dets, lat, keep, track_rows = [], [], [], {}, []
    rng = random.Random(0)
    for i, img in frames(args.bag):
        t0 = time.perf_counter()
        dets = detect_boxes(img)
        tracks = tr.update(dets)
        lat.append(time.perf_counter() - t0)
        per_frame.append([t.id for t in tracks])
        raw_dets.append(dets)
        track_rows.extend((i, t.id, *t.bbox) for t in tracks)
        if (lo is not None and i < lo) or (hi is not None and i >= hi):
            continue
        if args.sheet and (dets and rng.random() < 0.01 or i in keep):
            keep[i] = overlay(img, dets, tracks, f"{args.bag.name}[{i}]")

    if args.frames_csv:
        with args.frames_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "track_id", "x", "y", "w", "h"])
            w.writerows(track_rows)

    if args.export_yolo:
        # 2차 순회: 양성 = 확정 트랙이 있는 프레임, 음성 = 앞뒤 60 프레임(2 s) 안에 검출이 전혀 없는
        # 프레임. 손에 가리거나 화면 끝에 걸려 거른 박스가 '배경'으로 학습되지 않게 한다.
        any_det = np.array([bool(d) for d in raw_dets])
        near = np.convolve(any_det.astype(int), np.ones(121, int), mode="same") > 0
        img_dir, lab_dir = args.export_yolo / "images", args.export_yolo / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lab_dir.mkdir(parents=True, exist_ok=True)
        n_pos = n_neg = 0
        for i, img in frames(args.bag):
            if (lo is not None and i < lo) or (hi is not None and i >= hi):
                continue
            pos = bool(per_frame[i]) and i % args.stride == 0
            neg = not near[i] and i % args.neg_stride == 0
            if not (pos or neg):
                continue
            stem = f"{args.bag.name}_{i:05d}"
            cv2.imwrite(str(img_dir / f"{stem}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            H, W = img.shape[:2]
            with (lab_dir / f"{stem}.txt").open("w") as f:
                for d in raw_dets[i] if pos else []:
                    x, y, w, h = d.bbox
                    f.write(
                        f"0 {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}\n"
                    )
            n_pos, n_neg = n_pos + pos, n_neg + (not pos)
        print(f"  YOLO 내보내기 {args.export_yolo}: 양성 {n_pos}, 음성 {n_neg}")

    n = len(per_frame)
    det_frames = sum(1 for ids in per_frame if ids)
    spans: dict[int, list[int]] = {}
    for i, ids in enumerate(per_frame):
        for tid in ids:
            spans.setdefault(tid, []).append(i)
    print(f"{args.bag.name}: {n} 프레임, 검출 있는 프레임 {det_frames}")
    long_tracks = {k: v for k, v in spans.items() if len(v) >= 15}
    short = {k: len(v) for k, v in spans.items() if len(v) < 15}
    tot_span = tot_hit = 0
    for tid, fr in long_tracks.items():
        span = fr[-1] - fr[0] + 1
        tot_span, tot_hit = tot_span + span, tot_hit + len(fr)
        gaps = span - len(fr)
        print(
            f"  트랙 {tid:3d}: 프레임 {fr[0]:5d}~{fr[-1]:5d} ({span / 30:4.1f} s) 검출 {len(fr)}/{span}, 빠짐 {gaps}"
        )
    print(
        f"  트랙(≥15 프레임) {len(long_tracks)}개, 짧은 트랙 {len(short)}개 {short if short else ''}"
    )
    if tot_span:
        print(f"  트랙 구간 검출률 {tot_hit}/{tot_span} = {100 * tot_hit / tot_span:.2f}%")
    print(
        f"  지연(CPU, 참고) 중앙 {statistics.median(lat) * 1000:.1f} ms, p95 {np.percentile(lat, 95) * 1000:.1f} ms"
    )
    if args.sheet and keep:
        tiles = list(keep.values())[:40]
        while len(tiles) % 8:
            tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(
            str(args.sheet),
            np.vstack([np.hstack(tiles[k : k + 8]) for k in range(0, len(tiles), 8)]),
        )
        print(f"  확인 시트 {args.sheet} ({len(keep)}장 중 {min(len(keep), 40)})")


if __name__ == "__main__":
    main()
