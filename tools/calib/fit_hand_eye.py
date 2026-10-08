"""핸드아이 풀이·검증 → config/hand_eye.yaml (docs/interfaces/calibration.md). 사람이 실행, 로봇과 무관.

  python3 tools/calib/fit_hand_eye.py --data ~/voss_data/1008/handeye --intrinsics board \
      --homography config/belt_homography.yaml --t16 ~/voss_data/1007/t16 \
      --touch ~/voss_data/1008/touch/touch.csv \
      --moving-spread-mm 4.08 --moving-spread-lag-mm 2.73 --pose-lag-ms 60 \
      --moving-note "he_moving_01 ..." --out config/hand_eye.yaml

검증(제안값): ① 사진마다 계산한 베이스→보드 흩어짐 ≤ 2 mm·0.5°  ② PARK·HORAUD·ANDREFF 차이 ≤ 2 mm
③ T16 대응점(터치 좌표)을 관측 자세 사진 픽셀에서 다시 계산 ≤ 5 mm  ④ 터치 관측 ≤ 5 mm  ⑤ 이동 중 ≤ 5 mm.
① 은 보드 사진끼리의 일관성일 뿐 그리퍼가 실제로 가는 TCP 좌표와의 일치는 보지 않는다. 10/08: ① 0.85 mm 인데
T16·터치는 광축 방향으로 약 9 mm 어긋났다(보드 사진이 모두 ≤ 25° 기울기). `--touch` 를 주면 T16 + 터치 점에
맞게 카메라 위치만(회전 그대로) 고친다 — 고친 뒤 ① 이 커지는 만큼(10/08: 4.1 mm)이 보드와 터치 데이터의 어긋남이다.
공구가 수직이면 "카메라 거리" 오차와 "평면(터치 z·TCP z) 높이" 오차는 효과가 같아 이 데이터로 가를 수 없다.
보정은 TCP 좌표(터치)에 맞추므로 수직 공구(G0)에서는 맞고, 공구를 기울여 쓰기 전에는 큰 기울기로 다시 찍어 가린다.
① 판정은 보정 전 값, 보정 후 값은 board_spread_corrected_mm 로 남긴다.
T16 점만으로는 카메라 자세가 정해지지 않는다(한 평면·좁은 영역이라 기울기와 이동이 섞인다) — 위치만 고친다.

--intrinsics board: 보드 사진으로 K·왜곡을 다시 추정해 PnP·필터·③④ 에 쓴다(10/08 채택, 공장 camera_info 는
d = 0 이라 1 px 필터에 27장 모두 걸렸다). 공장 K 는 camera_factory 로 남겨 실행 중 camera_info 확인에 쓴다.
--touch CSV 열: name,u,v,x,y,z,tcp_x,tcp_y,tcp_z,tcp_rx,tcp_ry,tcp_rz — 사진 픽셀, 핑거 끝 터치 좌표(mm, 평면 z),
사진 찍을 때 TCP posx(mm·deg ZYZ).
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
    correct_translation,
    make_t,
    mean_pose,
    plane_errors,
    posx_to_t,
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
OPTIONAL_LIMITS = {"touch_val_max_mm": 5.0, "moving_spread_mm": 5.0, "moving_spread_lag_mm": 5.0}
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
    ap.add_argument("--reproj-max-px", type=float, default=REPROJ_MAX_PX,
                    help="코너 재투영이 이보다 큰 사진은 뺀다")  # fmt: skip
    ap.add_argument("--intrinsics", choices=["camera_info", "board"], default="camera_info",
                    help="K·왜곡: 공장 camera_info 또는 보드 사진 재추정")  # fmt: skip
    ap.add_argument("--touch", type=Path, help="터치 관측 CSV — T16 과 함께 카메라 위치 보정·④")
    ap.add_argument(
        "--moving-spread-mm", type=float, help="이동 중 검증 최대 오차(영상-pose 지연 0)"
    )
    ap.add_argument("--moving-spread-lag-mm", type=float, help="같은 검증, --pose-lag-ms 보정 적용")
    ap.add_argument(
        "--pose-lag-ms", type=float, help="이동 중 검증에서 흔들림이 가장 작았던 pose 지연"
    )
    ap.add_argument("--moving-note", default="", help="이동 중 검증 조건(bag·속도·프레임 수)")
    ap.add_argument(
        "--out", type=Path, help="config/hand_eye.yaml (검증 통과 때만 쓴다, --force 로 강제)"
    )
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    info = load_info(args.data / "camera_info.yaml")
    k_factory = np.array(info["k"], dtype=float).reshape(3, 3)
    d_factory = np.array(info.get("d") or [0.0] * 5, dtype=float)
    board = tuple(args.board)
    rows = [
        r for r in csv.DictReader((args.data / "poses.csv").open()) if r["name"] not in args.drop
    ]

    found, size = [], None
    for r in rows:
        img = cv2.imread(str(args.data / f"{r['name']}.png"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            sys.exit(f"{r['name']}.png 없음")
        size = img.shape[::-1]
        ok, corners = cv2.findChessboardCornersSB(img, board)
        if not ok:
            print(f"  {r['name']}: 코너 못 찾음 → 제외")
            continue
        found.append((r, corners))

    # 내부 파라미터: 보드 사진 재추정(rms) — board 면 이것으로 풀고, 아니면 참고로만 출력
    obj = [board_object_points(board, args.square_mm)] * len(found)
    rms, k_board, d_board, _, _ = cv2.calibrateCamera(obj, [c for _, c in found], size, None, None)
    print(f"내부 파라미터 공장 fx {k_factory[0, 0]:.1f} fy {k_factory[1, 1]:.1f} cx {k_factory[0, 2]:.1f} cy {k_factory[1, 2]:.1f} d=0 | "
          f"보드 재추정 fx {k_board[0, 0]:.1f} fy {k_board[1, 1]:.1f} cx {k_board[0, 2]:.1f} cy {k_board[1, 2]:.1f} "
          f"d {np.round(d_board.ravel(), 4).tolist()} (rms {rms:.3f} px, {len(found)}장)")  # fmt: skip
    if args.intrinsics == "board":
        k, d = k_board, d_board.ravel()
        k_source = f"board_reestimate (cv2.calibrateCamera, {len(found)}장, rms {rms:.3f} px)"
    else:
        k, d, k_source = k_factory, d_factory, "camera_info"

    names, t_tcp, t_cb, reproj = [], [], [], []
    for r, corners in found:
        t, err = board_pose(corners, board, args.square_mm, k, d)
        if err > args.reproj_max_px:
            print(f"  {r['name']}: 재투영 {err:.2f} px > {args.reproj_max_px} → 제외")
            continue
        q = [float(r[c]) for c in ("qx", "qy", "qz", "qw")]
        pos = [float(r[c]) for c in ("x_mm", "y_mm", "z_mm")]
        names.append(r["name"])
        t_tcp.append(make_t(quat_to_rot(*q), pos))
        t_cb.append(t)
        reproj.append(err)
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
    final, correction = best, None
    t16_obs, touch_obs, t16_names, touch_names = [], [], [], []
    if args.homography:
        cal = yaml.safe_load(args.homography.open())
        obs = np.array(cal["observe_pose"], dtype=float)
        tcp_offset = tcp_offset or cal["tcp_offset_mm"]
        t_obs = make_t(rot_zyz_deg(*obs[3:6]), flange_to_tcp(obs, np.array(cal["tcp_offset_mm"])))
        if args.t16:
            pts = {r["name"]: r for r in csv.DictReader((args.t16 / "points.csv").open())}
            for p in csv.DictReader((args.t16 / "pixels.csv").open()):
                if p["name"] in pts:
                    q = pts[p["name"]]
                    z = float(q["z"]) if q.get("z") else float(cal["plane_z_mm"])  # 점마다 터치 z
                    t16_obs.append(
                        (t_obs, (float(p["u"]), float(p["v"])), (float(q["x"]), float(q["y"])), z)
                    )
                    t16_names.append(p["name"])
    if args.touch:
        for r in csv.DictReader(args.touch.open()):
            tcp = [float(r[c]) for c in ("tcp_x", "tcp_y", "tcp_z", "tcp_rx", "tcp_ry", "tcp_rz")]
            touch_obs.append(
                (
                    posx_to_t(tcp),
                    (float(r["u"]), float(r["v"])),
                    (float(r["x"]), float(r["y"])),
                    float(r["z"]),
                )
            )
            touch_names.append(r["name"])

    def report(label: str, t: np.ndarray) -> None:
        for nm, ob, names_ in (("T16", t16_obs, t16_names), ("터치", touch_obs, touch_names)):
            if ob:
                e = plane_errors(t, k, d, ob)
                print(f"  {label} {nm} 최대 {e.max():.2f} 평균 {e.mean():.2f} mm: "
                      + "  ".join(f"{n} {v:.1f}" for n, v in zip(names_, e, strict=True)))  # fmt: skip

    if touch_obs:
        print(f"카메라 위치 보정 (T16 {len(t16_obs)} + 터치 {len(touch_obs)}, 회전 그대로):")
        report("보정 전", best)
        off = correct_translation(best, k, d, t16_obs + touch_obs)
        final = best @ make_t(np.eye(3), off)
        report("보정 후", final)
        fb_mm, _ = spread(board_in_base(t_tcp, final, t_cb))
        print(f"  보정량(카메라 좌표 mm, z = 광축) {np.round(off, 2).tolist()}, 보정 후 보드 흩어짐 {fb_mm:.2f} mm "
              f"(= 보드와 터치 데이터의 어긋남, ① 판정은 보정 전 값)")  # fmt: skip
        correction = {
            "offset_camera_mm": [round(float(v), 2) for v in off],
            "solver_translation_mm": [round(float(v), 2) for v in best[:3, 3]],
            "n_t16": len(t16_obs),
            "n_touch": len(touch_obs),
            "source": f"{args.touch.name} + T16 {args.t16.name if args.t16 else '-'}",
        }
        errors["board_spread_corrected_mm"] = round(float(fb_mm), 2)
    elif t16_obs:
        report("T16", best)

    if t16_obs:
        e = plane_errors(final, k, d, t16_obs)
        errors["t16_val"] = {n: round(float(v), 2) for n, v in zip(t16_names, e, strict=True)}
        errors["t16_val_max_mm"] = round(float(e.max()), 2)
    if touch_obs:
        e = plane_errors(final, k, d, touch_obs)
        errors["touch_val"] = {n: round(float(v), 2) for n, v in zip(touch_names, e, strict=True)}
        errors["touch_val_max_mm"] = round(float(e.max()), 2)
    if args.moving_spread_mm is not None:
        errors["moving_spread_mm"] = args.moving_spread_mm
    if args.moving_spread_lag_mm is not None:
        errors["moving_spread_lag_mm"] = args.moving_spread_lag_mm
    if args.pose_lag_ms is not None:
        errors["pose_lag_ms_measured"] = args.pose_lag_ms
    if args.moving_note:
        errors["moving_note"] = args.moving_note

    print(f"T_tcp_camera ({args.method}{' + 위치 보정' if correction else ''}) 위치 mm {np.round(final[:3, 3], 2).tolist()}, "
          f"광축과 공구 z 사이 {np.degrees(np.arccos(np.clip(final[2, 2], -1, 1))):.1f}°")  # fmt: skip
    limits = {**LIMITS, **{k_: v for k_, v in OPTIONAL_LIMITS.items() if k_ in errors}}
    verdict = {
        key: errors.get(key) is not None and errors[key] <= lim for key, lim in limits.items()
    }
    for key, lim in limits.items():
        print(f"  {'통과' if verdict[key] else '미달'} {key} = {errors.get(key)} (기준 ≤ {lim})")
    moving = [errors[key] for key in ("moving_spread_mm", "moving_spread_lag_mm") if key in errors]
    moving_verified = bool(moving) and all(v <= OPTIONAL_LIMITS["moving_spread_mm"] for v in moving)

    if args.out and (all(verdict.values()) or args.force):
        out = {
            "version": 1,
            "method": "hand_eye",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "solver": args.method + (" + touch_translation" if correction else ""),
            "board": {"inner_corners": list(board), "square_mm": args.square_mm},
            "image_size": list(size),
            "camera": {
                "k": np.round(k.reshape(-1), 4).tolist(),
                "d": np.round(d, 6).tolist(),
                "source": k_source,
            },
            "camera_factory": {"k": k_factory.reshape(-1).tolist(), "d": d_factory.tolist()},
            "pose_frame": "tcp",
            "tcp_offset_mm": [float(v) for v in tcp_offset] if tcp_offset else None,
            "T_tcp_camera": np.round(final, 6).tolist(),
            "touch_correction": correction,
            "moving_verified": moving_verified,
            "errors": errors,
        }
        args.out.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
        print(f"저장 {args.out} (moving_verified={moving_verified})")
    elif args.out:
        print(
            "미달 항목이 있어 저장하지 않았다 (--drop 으로 이상한 사진을 빼거나 다시 찍기, 강제는 --force)"
        )


if __name__ == "__main__":
    main()
