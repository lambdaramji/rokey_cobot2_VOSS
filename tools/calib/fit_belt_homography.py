"""개인 PC용: 현장 사진 + 터치 좌표 → config/belt_homography.yaml (ADR-0003, 스키마 docs/interfaces/calibration.md).

입력 폴더(--dir):
  C1.png … C6.png, V1.png … V3.png   관측 자세에서 찍은 사진
  points.csv   name,x,y,z,rx,ry,rz      터치한 posx (mm·deg). 관측 자세 행은 name=OBS
  camera_info.yaml (선택)              `ros2 topic echo --once /camera/color/camera_info` 결과
pixels.csv 가 없으면 사진을 하나씩 띄워 송장의 + 를 클릭하게 한다(Enter 확정, r 다시).

  python3 tools/calib/fit_belt_homography.py --dir ~/voss_calib --out config/belt_homography.yaml
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from voss_vision.belt_plane import apply_homography, fit_homography, point_errors_mm  # noqa: E402

SCALE = 1.0  # 1280×720 은 그대로 표시 (더 큰 해상도면 줄이고, 클릭 좌표는 원본으로 환산)


def click_pixels(folder: Path, names: list[str]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for name in names:
        img = cv2.imread(str(folder / f"{name}.png"))
        if img is None:
            raise SystemExit(f"{name}.png 가 없다")
        small = cv2.resize(img, None, fx=SCALE, fy=SCALE)
        pick: list[tuple[float, float]] = []

        def on_mouse(ev, x, y, *_, pick=pick):  # 루프마다 새 pick 을 묶는다
            if ev == cv2.EVENT_LBUTTONDOWN:
                pick[:] = [(x / SCALE, y / SCALE)]

        cv2.namedWindow(name)
        cv2.setMouseCallback(name, on_mouse)
        while True:
            view = small.copy()
            if pick:
                u, v = pick[0]
                cv2.drawMarker(
                    view, (int(u * SCALE), int(v * SCALE)), (0, 0, 255), cv2.MARKER_CROSS, 30, 2
                )
            cv2.imshow(name, view)
            key = cv2.waitKey(30) & 0xFF
            if key == 13 and pick:  # Enter
                out[name] = pick[0]
                break
            if key == ord("r"):
                pick.clear()
        cv2.destroyWindow(name)
    return out


def load_undistort(folder: Path) -> tuple[np.ndarray, np.ndarray] | None:
    path = folder / "camera_info.yaml"
    if not path.exists():
        print("! camera_info.yaml 없음 — 왜곡 보정 없이 계산")
        return None
    info = next(yaml.safe_load_all(path.read_text()))
    return np.array(info["k"], dtype=float).reshape(3, 3), np.array(info["d"], dtype=float)


def undistort(px: np.ndarray, cam: tuple[np.ndarray, np.ndarray] | None) -> np.ndarray:
    if cam is None or not np.any(cam[1]):
        return px
    k, d = cam
    return cv2.undistortPoints(px.reshape(-1, 1, 2).astype(np.float64), k, d, P=k).reshape(-1, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path.home() / "voss_calib")
    ap.add_argument("--out", type=Path, default=Path("config/belt_homography.yaml"))
    args = ap.parse_args()

    rows = {r["name"]: r for r in csv.DictReader((args.dir / "points.csv").open())}
    cal = sorted(n for n in rows if n.startswith("C"))
    val = sorted(n for n in rows if n.startswith("V"))

    pix_csv = args.dir / "pixels.csv"
    if pix_csv.exists():
        pix = {r["name"]: (float(r["u"]), float(r["v"])) for r in csv.DictReader(pix_csv.open())}
    else:
        pix = click_pixels(args.dir, cal + val)
        with pix_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "u", "v"])
            w.writerows([n, f"{u:.1f}", f"{v:.1f}"] for n, (u, v) in pix.items())

    first = cv2.imread(str(args.dir / f"{cal[0]}.png"))
    image_size = [int(first.shape[1]), int(first.shape[0])] if first is not None else None
    cam = load_undistort(args.dir)
    px = {n: undistort(np.array([pix[n]]), cam)[0] for n in cal + val}
    xy = {n: np.array([float(rows[n]["x"]), float(rows[n]["y"])]) for n in cal + val}

    h = fit_homography(np.array([px[n] for n in cal]), np.array([xy[n] for n in cal]))
    e_cal = point_errors_mm(h, np.array([px[n] for n in cal]), np.array([xy[n] for n in cal]))
    e_val = point_errors_mm(h, np.array([px[n] for n in val]), np.array([xy[n] for n in val]))
    z = np.array([float(rows[n]["z"]) for n in cal + val])

    print(f"계산점 {len(cal)}개 잔차 RMS {np.sqrt((e_cal**2).mean()):.2f} mm")
    for n, e in zip(val, e_val, strict=True):
        print(f"  검증 {n}: {e:.2f} mm {'OK' if e <= 5.0 else '초과'}")
    print(f"검증점 최대 {e_val.max():.2f} mm (기준 ≤ 5 mm, 제안값)")
    print(f"터치 z 평균 {z.mean():.1f} mm, 범위 {np.ptp(z):.1f} mm (3 mm 넘으면 평면·터치 재확인)")

    obs = rows.get("OBS")
    result = {
        "version": 1,
        "method": "belt_plane_homography",
        "created": datetime.now().isoformat(timespec="minutes"),
        "image_size": image_size,
        "observe_pose": [float(obs[k]) for k in ("x", "y", "z", "rx", "ry", "rz")] if obs else None,
        "plane_z_mm": round(float(z.mean()), 1),
        "undistort": {"k": cam[0].ravel().tolist(), "d": cam[1].tolist()} if cam else None,
        "H_px_to_base_xy": np.round(h, 9).tolist(),
        "tcp_pixel_at_observe": (
            np.round(
                apply_homography(np.linalg.inv(h), [[float(obs["x"]), float(obs["y"])]])[0], 1
            ).tolist()
            if obs
            else None
        ),
        "errors_mm": {
            "calib_rms": round(float(np.sqrt((e_cal**2).mean())), 2),
            "val_max": round(float(e_val.max()), 2),
            "val": {n: round(float(e), 2) for n, e in zip(val, e_val, strict=True)},
        },
    }
    args.out.write_text(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    print(f"저장 {args.out}")


if __name__ == "__main__":
    main()
