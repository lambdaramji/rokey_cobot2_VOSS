"""핸드아이 풀이·검증 → config/hand_eye.yaml (docs/interfaces/calibration.md). 사람이 실행, 로봇과 무관.

  python3 tools/calib/fit_hand_eye.py --data ~/voss_data/1008/handeye \
      --homography config/belt_homography.yaml --t16 ~/voss_data/1007/t16 --out config/hand_eye.yaml

검증(제안값): ① 사진마다 계산한 베이스→보드 흩어짐 ≤ 2 mm·0.5°  ② PARK·HORAUD·ANDREFF 차이 ≤ 2 mm
③ T16 대응점(터치 좌표)을 관측 자세 사진 픽셀에서 다시 계산 ≤ 5 mm(공장 내부 파라미터 강체 모델의 최선 ≈ 3 mm).
핵심은 ① — 여러 자세에서 같은 보드가 같은 곳에 나와야 움직이는 카메라에서도 맞는다. T16 점만으로는
카메라 자세가 정해지지 않는다(한 평면·좁은 영역이라 기울기와 이동이 섞인다: 10/07 PnP 와 호모그래피 분해가 37 mm·7° 차이).
"""

import argparse
import csv
import datetime
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from voss_vision.belt_plane import flange_to_tcp, rot_zyz_deg  # noqa: E402
from voss_vision.hand_eye import (  # noqa: E402
    COMPARE,
    board_in_base,
    board_object_points,
    board_pose,
    make_t,
    mean_pose,
    pixel_to_plane,
    quat_to_rot,
    rot_angle_deg,
    solve,
    spread,
)

LIMITS = {
    "board_spread_mm": 2.0,
    "board_spread_deg": 0.5,
    "method_spread_mm": 2.0,
    "t16_val_max_mm": 5.0,
}
REPROJ_MAX_PX = 1.0  # 이보다 큰 사진은 코너 검출이 의심스러워 뺀다


def load_info(path: Path) -> dict:
    return next(yaml.safe_load_all(path.open()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True, help="handeye_capture.py 출력 폴더")
    ap.add_argument("--board", type=int, nargs=2, default=[10, 7])
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--method", default="PARK", choices=COMPARE)
    ap.add_argument(
        "--homography", type=Path, help="config/belt_homography.yaml — ③ 의 관측 자세·plane_z"
    )
    ap.add_argument("--t16", type=Path, help="T16 points.csv·pixels.csv 폴더 — ③")
    ap.add_argument(
        "--tcp-offset", type=float, nargs=3, help="촬영 때 voss_config robot.tcp_offset_mm"
    )
    ap.add_argument("--drop", nargs="*", default=[], help="뺄 사진 이름 (예: HE_07)")
    ap.add_argument(
        "--out", type=Path, help="config/hand_eye.yaml (검증 통과 때만 쓴다, --force 로 강제)"
    )
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    info = load_info(args.data / "camera_info.yaml")
    k = np.array(info["k"], dtype=float).reshape(3, 3)
    d = np.array(info.get("d") or [0.0] * 5, dtype=float)
    board = tuple(args.board)
    rows = [
        r for r in csv.DictReader((args.data / "poses.csv").open()) if r["name"] not in args.drop
    ]

    names, t_tcp, t_cb, reproj, size, corners_all = [], [], [], [], None, []
    for r in rows:
        img = cv2.imread(str(args.data / f"{r['name']}.png"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            sys.exit(f"{r['name']}.png 없음")
        size = img.shape[::-1]
        ok, corners = cv2.findChessboardCornersSB(img, board)
        if not ok:
            print(f"  {r['name']}: 코너 못 찾음 → 제외")
            continue
        t, err = board_pose(corners, board, args.square_mm, k, d)
        if err > REPROJ_MAX_PX:
            print(f"  {r['name']}: 재투영 {err:.2f} px > {REPROJ_MAX_PX} → 제외")
            continue
        q = [float(r[c]) for c in ("qx", "qy", "qz", "qw")]
        pos = [float(r[c]) for c in ("x_mm", "y_mm", "z_mm")]
        names.append(r["name"])
        t_tcp.append(make_t(quat_to_rot(*q), pos))
        t_cb.append(t)
        reproj.append(err)
        corners_all.append(corners)
    n_rejected = len(rows) - len(names)
    if len(names) < 10:
        sys.exit(f"쓸 수 있는 사진 {len(names)}장 < 10 — 더 찍어야 한다")

    sols = {m: solve(t_tcp, t_cb, m) for m in COMPARE}
    best = sols[args.method]
    method_mm = max(
        np.linalg.norm(a[:3, 3] - b[:3, 3]) for a in sols.values() for b in sols.values()
    )
    method_deg = max(
        rot_angle_deg(a[:3, :3], b[:3, :3]) for a in sols.values() for b in sols.values()
    )
    boards = board_in_base(t_tcp, best, t_cb)
    b_mm, b_deg = spread(boards)
    mb = mean_pose(boards)
    print(f"사진 {len(names)}장 사용, {n_rejected}장 제외, 코너 재투영 최대 {max(reproj):.2f} px")
    print("사진별 베이스→보드 위치 차이(mm, 평균 기준):")
    print(
        "  "
        + "  ".join(
            f"{n} {np.linalg.norm(b[:3, 3] - mb[:3, 3]):.1f}"
            for n, b in zip(names, boards, strict=True)
        )
    )

    # 내부 파라미터 참고: 보드 사진으로 다시 추정한 값과 camera_info(공장값) 비교
    obj = [board_object_points(board, args.square_mm)] * len(corners_all)
    rms, k2, _, _, _ = cv2.calibrateCamera(obj, corners_all, size, None, None)
    print(f"내부 파라미터(참고) 공장 fx {k[0, 0]:.1f} fy {k[1, 1]:.1f} cx {k[0, 2]:.1f} cy {k[1, 2]:.1f} | "
          f"보드 재추정 fx {k2[0, 0]:.1f} fy {k2[1, 1]:.1f} cx {k2[0, 2]:.1f} cy {k2[1, 2]:.1f} (rms {rms:.2f} px)")  # fmt: skip

    errors = {
        "n_used": len(names),
        "n_rejected": n_rejected,
        "reproj_px_max": round(max(reproj), 3),
        "board_spread_mm": round(b_mm, 2),
        "board_spread_deg": round(b_deg, 3),
        "method_spread_mm": round(float(method_mm), 2),
        "method_spread_deg": round(float(method_deg), 3),
    }
    tcp_offset = args.tcp_offset
    if args.homography:
        cal = yaml.safe_load(args.homography.open())
        obs = np.array(cal["observe_pose"], dtype=float)
        tcp_offset = tcp_offset or cal["tcp_offset_mm"]
        t_obs = make_t(rot_zyz_deg(*obs[3:6]), flange_to_tcp(obs, np.array(cal["tcp_offset_mm"])))
        t_base_cam = t_obs @ best
        zp = float(cal["plane_z_mm"])
        if args.t16:
            pts = {r["name"]: r for r in csv.DictReader((args.t16 / "points.csv").open())}
            pix = {r["name"]: r for r in csv.DictReader((args.t16 / "pixels.csv").open())}
            val = {}
            for n, p in pix.items():
                if n not in pts:
                    continue
                xyz, ok = pixel_to_plane(t_base_cam, k, d, [[float(p["u"]), float(p["v"])]], zp)
                if ok[0]:
                    val[n] = round(
                        float(
                            np.hypot(xyz[0, 0] - float(pts[n]["x"]), xyz[0, 1] - float(pts[n]["y"]))
                        ),
                        2,
                    )
            errors["t16_val"] = val
            errors["t16_val_max_mm"] = max(val.values()) if val else None
            print("T16 대응점 오차(mm): " + "  ".join(f"{n} {e}" for n, e in val.items()))

    print(f"T_tcp_camera ({args.method}) 위치 mm {np.round(best[:3, 3], 2).tolist()}, "
          f"광축과 공구 z 사이 {np.degrees(np.arccos(np.clip(best[2, 2], -1, 1))):.1f}°")  # fmt: skip
    verdict = {
        key: errors.get(key) is not None and errors[key] <= lim for key, lim in LIMITS.items()
    }
    for key, lim in LIMITS.items():
        print(f"  {'통과' if verdict[key] else '미달'} {key} = {errors.get(key)} (기준 ≤ {lim})")

    if args.out and (all(verdict.values()) or args.force):
        out = {
            "version": 1,
            "method": "hand_eye",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "solver": args.method,
            "board": {"inner_corners": list(board), "square_mm": args.square_mm},
            "image_size": list(size),
            "camera": {"k": k.reshape(-1).tolist(), "d": d.tolist(), "source": "camera_info"},
            "pose_frame": "tcp",
            "tcp_offset_mm": [float(v) for v in tcp_offset] if tcp_offset else None,
            "T_tcp_camera": np.round(best, 6).tolist(),
            "moving_verified": False,
            "errors": errors,
        }
        args.out.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
        print(f"저장 {args.out} (moving_verified=false — 이동 중 검증 뒤 true)")
    elif args.out:
        print(
            "미달 항목이 있어 저장하지 않았다 (--drop 으로 이상한 사진을 빼거나 다시 찍기, 강제는 --force)"
        )


if __name__ == "__main__":
    main()
