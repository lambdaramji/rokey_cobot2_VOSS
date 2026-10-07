"""T17 정답셋 사람 확인 시트 (ADR-0004 결정 2: 박스 통과 10회 이상, 통과당 최대 20장, 경계 포함).

eval_bag.py --frames-csv 로 만든 프레임별 트랙 기록에서 고른다.
- 박스 통과(트랙)마다 20장: 화면 안쪽 18장(트랙 구간에 고르게) + 화면 경계 2장(트랙 시작 직전·끝 직후,
  박스가 화면 끝에 걸려 일부러 내지 않는 프레임 — "검출 없음"이 맞는지 사람이 본다)
- 음성 프레임(--neg-bag 범위): 손·빈 벨트 25장 — 오검출 확인
결과: images/·labels/(자동 라벨), sheet_<n>.jpg(25장씩, 번호), check.csv(사람이 ok 칸에 y/n)

  python3 tools/vision/make_check_sheets.py --bag <C_MIX_01> --frames-csv C.csv \
      --neg-bag <B_EMPTY_01> --neg-frames 900: --out <holdout_check>
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_bag import frames  # noqa: E402

INSIDE, EDGE_GAP = 18, 6  # 통과당 안쪽 장수, 경계 프레임 = 트랙 시작 6 프레임 전·끝 6 프레임 후


def pick(track_frames: dict[int, list[int]], min_len: int = 15) -> list[tuple[int, int, str]]:
    out = []
    for tid, fr in sorted(track_frames.items()):
        if len(fr) < min_len:
            continue
        idx = np.linspace(0, len(fr) - 1, INSIDE).round().astype(int)
        out += [(fr[k], tid, "inside") for k in sorted(set(idx))]
        out += [(fr[0] - EDGE_GAP, tid, "edge"), (fr[-1] + EDGE_GAP, tid, "edge")]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bag", type=Path, required=True)
    ap.add_argument("--frames-csv", type=Path, required=True)
    ap.add_argument("--neg-bag", type=Path)
    ap.add_argument("--neg-frames", default=":", help="음성 프레임 범위 a:b")
    ap.add_argument("--neg-count", type=int, default=25)
    ap.add_argument("--min-passes", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    boxes: dict[int, list[tuple[int, int, int, int]]] = {}
    tracks: dict[int, list[int]] = {}
    for r in csv.DictReader(args.frames_csv.open()):
        f, tid = int(r["frame"]), int(r["track_id"])
        boxes.setdefault(f, []).append(tuple(int(r[k]) for k in ("x", "y", "w", "h")))
        tracks.setdefault(tid, []).append(f)
    picks = pick(tracks)
    n_pass = len({tid for _, tid, _ in picks})
    if n_pass < args.min_passes:
        sys.exit(f"박스 통과 {n_pass}회 < {args.min_passes} — ADR-0004 정답셋 규칙 미달")

    jobs = [(args.bag, picks)]
    if args.neg_bag:
        lo, hi = (int(x) if x else None for x in args.neg_frames.split(":"))
        n = sum(1 for _ in frames(args.neg_bag))
        lo, hi = lo or 0, hi or n
        neg = np.linspace(lo, hi - 1, args.neg_count).round().astype(int)
        jobs.append((args.neg_bag, [(int(f), -1, "negative") for f in neg]))

    (args.out / "images").mkdir(parents=True, exist_ok=True)
    (args.out / "labels").mkdir(parents=True, exist_ok=True)
    rows, tiles = [], []
    for bag, plist in jobs:
        want = {f: (tid, kind) for f, tid, kind in plist}
        for i, img in frames(bag):
            if i not in want:
                continue
            tid, kind = want[i]
            H, W = img.shape[:2]
            auto = boxes.get(i, []) if bag == args.bag else []
            stem = f"{bag.name}_{i:05d}"
            cv2.imwrite(
                str(args.out / "images" / f"{stem}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90]
            )
            with (args.out / "labels" / f"{stem}.txt").open("w") as f:
                for x, y, w, h in auto:
                    f.write(
                        f"0 {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}\n"
                    )
            no = len(rows)
            rows.append([no, bag.name, i, tid, kind, len(auto), "", ""])
            v = img.copy()
            for x, y, w, h in auto:
                cv2.rectangle(v, (x - 6, y - 6), (x + w + 6, y + h + 6), (0, 0, 255), 8)
            t = cv2.resize(v[:, 860:1400], (270, 540))
            cv2.putText(t, f"#{no} {kind[0]}", (5, 30), 0, 1, (0, 255, 255), 2)
            tiles.append(t)
    with (args.out / "check.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["no", "bag", "frame", "track_id", "kind", "boxes_auto", "ok(y/n)", "note"])
        w.writerows(rows)
    for s in range(0, len(tiles), 25):
        t = tiles[s : s + 25]
        while len(t) % 5:
            t.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(t[k : k + 5]) for k in range(0, len(t), 5)])
        cv2.imwrite(
            str(args.out / f"sheet_{s // 25 + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
    kinds = {k: sum(1 for r in rows if r[4] == k) for k in ("inside", "edge", "negative")}
    print(
        f"박스 통과 {n_pass}회, {len(rows)}장 {kinds} → {args.out} (시트 {(len(tiles) + 24) // 25}장)"
    )


if __name__ == "__main__":
    main()
