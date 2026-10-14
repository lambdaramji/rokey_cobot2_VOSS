"""J6 회전 시 핸드아이 오차·박스 yaw 를 녹화로 잰다 (S2-T16, BRD v1.5 R-28·TR-SERVO-06). 사람이 실행, 로봇과 무관(오프라인).

녹화 조건(10/14, 김학민 티치펜던트 저속 · 비상정지 대기자 · 벨트 정지):
- 박스 1개를 관측 자세 화면 가운데 벨트 위에 둔다. 녹화 하나 = 박스 한 번 놓기. 박스 각을 바꿀 때(대략 0·15·30·45°)마다 새 녹화
- 관측 자세에서 시작해 **J6 만** 0 → +15 → +30 → +45°(되면 −15·−30·−45°도), 각마다 **약 3 s 정지**. 박스는 건드리지 않는다
- 토픽: `/camera/color/image_raw/compressed`(또는 `image_raw`), `/camera/color/camera_info`, `/voss/robot/pose`

계산은 box_tracker 와 같다(`voss_vision/j6_eval.py`, pytest): 분할 검출 → 트래커 → 촬영 시각 + lag 의 pose →
T_tcp_camera → 박스 윗면 평면, yaw 는 송장 긴 변 양 끝. 박스가 그대로라 J6 각마다 값이 같아야 하고, 관측 자세 구간
대비 차가 J6 회전 때의 핸드아이 오차다. 관측 자세 구간은 호모그래피 값과도 비교한다.

  source /opt/ros/jazzy/setup.bash
  python3 tools/calib/j6_yaw_eval.py ~/voss_data/1014/j6_box00 ~/voss_data/1014/j6_box30 \
      --hand-eye config/hand_eye.yaml --homography config/belt_homography.yaml [--lag-ms 60] [--csv j6.csv]

판정(제안값): J6 각마다 Δ위치 ≤ 5 mm(calibration.md 핸드아이 기준), |Δyaw| ≤ 2°(TR-SERVO-05 데드밴드).
결과는 measurements 와 TR-SERVO-06 실기 측정 2건 중 "J6 ±30·45° 핸드아이 오차" 에 쓴다.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from pose_lag_eval import read_bag  # noqa: E402
from voss_vision.belt_plane import flange_to_tcp, rot_zyz_deg  # noqa: E402
from voss_vision.box_detect import SegParams, detect_boxes  # noqa: E402
from voss_vision.box_track import Tracker  # noqa: E402
from voss_vision.hand_eye import interpolate_pose, make_t  # noqa: E402
from voss_vision.j6_eval import (  # noqa: E402
    POS_MAX_MM,
    YAW_MAX_DEG,
    YawFrame,
    find_holds,
    measure,
    measure_homography,
    median_xy_yaw,
    passed,
    summarize,
    yaw_diff_deg,
)
from voss_vision.tracker_logic import near_observe  # noqa: E402


def track_frames(images, seg: SegParams) -> tuple[list[YawFrame], int]:
    """box_tracker 와 같은 검출·트래커로 가장 오래 이어진 트랙 하나(검출된 프레임만, 송장 긴 변 포함)."""
    tracker = Tracker(max_missed=15, gate_px=120.0, min_hits=5)
    per_track: dict[int, list[YawFrame]] = {}
    for t, bgr in sorted(images, key=lambda x: x[0]):
        for tr in tracker.update(detect_boxes(bgr, seg)):
            if tr.missed == 0:
                per_track.setdefault(tr.id, []).append(
                    YawFrame(t, float(tr.u), float(tr.v), tr.half_axis)
                )
    if not per_track:
        return [], 0
    return max(per_track.values(), key=len), len(per_track)


def observe_t(homo: dict) -> np.ndarray:
    """belt_homography.yaml observe_pose(플랜지 posx) → TCP 4×4 — box_tracker 와 같다."""
    obs = np.asarray(homo["observe_pose"], float)
    return make_t(rot_zyz_deg(*obs[3:6]), flange_to_tcp(obs, np.asarray(homo["tcp_offset_mm"])))


def fmt(v: float, nd: int = 1) -> str:
    return "-" if not math.isfinite(v) else f"{v:.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bags", type=Path, nargs="+", help="녹화 하나 = 박스 한 번 놓기")
    ap.add_argument("--hand-eye", type=Path, default=Path("config/hand_eye.yaml"))
    ap.add_argument("--homography", type=Path, default=Path("config/belt_homography.yaml"))
    ap.add_argument("--lag-ms", type=float, default=60.0, help="box_tracker pose_lag_ms (기본 60)")
    ap.add_argument("--image-topic")
    ap.add_argument("--csv", type=Path, help="구간별 결과")
    args = ap.parse_args()

    he = yaml.safe_load(args.hand_eye.read_text())
    t_tcp_cam = np.asarray(he["T_tcp_camera"], float)
    k = np.asarray(he["camera"]["k"], float).reshape(3, 3)
    d = np.asarray(he["camera"].get("d") or [0.0] * 5, float)
    homo = yaml.safe_load(args.homography.read_text())
    plane_z, t_obs = float(homo["plane_z_mm"]), observe_t(homo)
    print(f"핸드아이 {he.get('version', '?')} moving_verified={he.get('moving_verified', False)} · "
          f"호모그래피 {homo.get('version', '?')} · 평면 z {plane_z} mm · lag {args.lag_ms:.0f} ms")  # fmt: skip

    rows, all_ok = [], True
    for bag in args.bags:
        print(f"\n== {bag}")
        images, stamps, poses = read_bag(bag, args.image_topic)
        frames, n_tracks = track_frames(images, SegParams())
        holds = find_holds(frames, stamps, poses)
        if not frames or not holds:
            print(
                f"  검출 프레임 {len(frames)}, 정지 구간 {len(holds)} — 각마다 3 s 정지했는지·박스가 화면에 있는지 확인"
            )
            all_ok = False
            continue
        vals = measure(frames, stamps, poses, t_tcp_cam, k, d, plane_z, args.lag_ms / 1000.0)
        # 관측 자세 구간 = 기준. 구간 가운데 프레임 시각의 pose 로 판정한다
        ref = None
        for i, h in enumerate(holds):
            mid = frames[h.idx[len(h.idx) // 2]].t
            p = interpolate_pose(mid, stamps, poses, max_gap_s=0.15, max_extrap_s=0.0)
            if p is not None and near_observe(p, t_obs):
                ref = i
                break
        res = summarize(holds, vals, ref)
        print(f"  트랙 {n_tracks}개 중 가장 긴 것 {len(frames)} 프레임, 정지 구간 {len(holds)}개, "
              f"기준 = {'관측 자세 구간' if ref is not None else '관측 자세 없음 → J6 가장 작은 구간'}")  # fmt: skip
        print("   J6(°)  프레임(유효)    x(mm)    y(mm)  yaw(°)  흔들림(mm/°)  Δ위치(mm)  Δyaw(°)")
        for r in res:
            print(f"  {r.j6_deg:6.1f}  {r.n:5d}({r.n_valid:4d})  {fmt(r.x):>7}  {fmt(r.y):>7}  "
                  f"{fmt(r.yaw_deg):>6}  {fmt(r.spread_mm)}/{fmt(r.spread_deg)}  "
                  f"{fmt(r.dpos_mm, 2):>9}  {fmt(r.dyaw_deg, 2):>7}")  # fmt: skip
            rows.append(
                [
                    bag.name,
                    *(round(v, 3) if isinstance(v, float) else v for v in r.__dict__.values()),
                ]
            )
        if ref is not None:
            sel = [frames[i] for i in holds[ref].idx]
            hx, hy, hyaw, *_, hn = median_xy_yaw(measure_homography(sel, homo))
            ex, ey, eyaw, *_ = median_xy_yaw(vals[list(holds[ref].idx)])
            if hn:
                print(f"  관측 자세: 핸드아이 − 호모그래피 = 위치 {math.hypot(ex - hx, ey - hy):.2f} mm, "
                      f"yaw {yaw_diff_deg(eyaw, hyaw):+.2f}° (호모그래피 유효 {hn} 프레임)")  # fmt: skip
        ok = passed(res)
        all_ok &= ok
        print(
            f"  판정 {'PASS' if ok else 'FAIL'} (Δ위치 ≤ {POS_MAX_MM} mm, |Δyaw| ≤ {YAW_MAX_DEG}° — 제안값)"
        )

    if args.csv and rows:
        with args.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["bag", "j6_deg", "n", "n_valid", "x_mm", "y_mm", "yaw_deg", "spread_mm",
                        "spread_deg", "dpos_mm", "dyaw_deg"])  # fmt: skip
            w.writerows(rows)
        print(f"\n저장 {args.csv}")
    print(f"\n전체 {'PASS' if all_ok else 'FAIL'} — measurements 에 표와 녹화 경로를 남긴다")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
