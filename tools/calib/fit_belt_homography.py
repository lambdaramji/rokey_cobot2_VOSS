"""개인 PC용: 현장 사진 + 터치 좌표 → config/belt_homography.yaml (ADR-0003, 스키마 docs/interfaces/calibration.md).

입력 폴더(--dir):
  C1.png … C6.png, V1.png … V3.png   관측 자세에서 찍은 사진
  points.csv   name,x,y,z,rx,ry,rz      터치한 posx (mm·deg). 관측 자세 행은 name=OBS
  camera_info.yaml                     grab_frames.py 가 자동 저장 (없으면 왜곡 보정 없이 계산)
pixels.csv 가 없으면 사진을 하나씩 띄워 송장의 + 를 클릭하게 한다(Enter 확정, r 다시).

points.csv 의 기준점은 --pose-frame 으로 알려 준다(10/06 측정은 tcp). flange 면 각 터치 자세와
--tcp-offset-mm 로 접촉점(핑거 끝)으로 바꾼 뒤 계산한다. 출력은 항상 같은 의미로 정규화된다:
  H·plane_z = 접촉점(박스 윗면) 기준, observe_pose = 플랜지 기준(voss_config observe_pose 와 같음).

  python3 tools/calib/fit_belt_homography.py --dir ~/voss_calib --pose-frame tcp \
      --out config/belt_homography.yaml
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
from voss_vision.belt_plane import (  # noqa: E402
    apply_homography,
    convex_hull,
    fit_homography,
    flange_to_tcp,
    point_errors_mm,
    rot_zyz_deg,
    tool_axis_angle_deg,
    undistort_pixels,
)

SCALE = 0.5  # 1920×1080 을 화면에 맞게 줄여 보여 준다 (클릭 좌표는 원본으로 환산)
# 터치 자세가 관측 자세와 이만큼 넘게 다르면 경고. 접촉점은 터치 자세마다 TCP 로 정규화하므로
# 기울기 자체는 오차가 아니고, 남는 영향은 TCP 오프셋 오차 × 각도(1 mm·1° ≈ 0.02 mm)뿐이다.
# 10/06 관측 자세(=홈)는 수직에서 0.93° 기울어 있어 수직 터치도 0.93° 가 나온다 → 0.5° 는 오경보.
TILT_WARN_DEG = 2.0
Z_RANGE_WARN_MM = 3.0  # 접촉점 z 범위가 넘으면 평면·터치 재확인
POSE_MATCH_MM, POSE_MATCH_DEG = 1.0, 0.5  # voss_config observe_pose 와 비교 허용치


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


def load_camera_info(folder: Path) -> tuple[np.ndarray, np.ndarray] | None:
    path = folder / "camera_info.yaml"
    if not path.exists():
        print(
            "! camera_info.yaml 없음 — 왜곡 보정 없이 계산 (grab_frames.py 로 다시 받으면 생긴다)"
        )
        return None
    info = next(yaml.safe_load_all(path.read_text()))
    return np.array(info["k"], dtype=float).reshape(3, 3), np.array(info["d"], dtype=float)


def posx(row: dict) -> np.ndarray:
    return np.array([float(row[k]) for k in ("x", "y", "z", "rx", "ry", "rz")])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path.home() / "voss_calib")
    ap.add_argument("--out", type=Path, default=Path("config/belt_homography.yaml"))
    ap.add_argument(
        "--pose-frame",
        choices=["tcp", "flange"],
        required=True,
        help="points.csv posx 의 기준점. 10/06 측정은 tcp (김학민). 모르면 펜던트 TCP 설정부터 확인",
    )
    ap.add_argument(
        "--tcp-offset-mm",
        type=float,
        nargs=3,
        default=[1.382, 2.684, 246.642],
        help="플랜지 → 핑거 끝 오프셋(툴 좌표, mm). 10/06 실측값",
    )
    ap.add_argument(
        "--config", type=Path, default=Path("config/voss_config.yaml"), help="observe_pose 비교용"
    )
    args = ap.parse_args()
    t_tcp = np.array(args.tcp_offset_mm, dtype=float)

    rows = {r["name"]: r for r in csv.DictReader((args.dir / "points.csv").open())}
    cal = sorted(n for n in rows if n.startswith("C"))
    val = sorted(n for n in rows if n.startswith("V"))
    if len(cal) < 4:
        raise SystemExit(f"계산점이 {len(cal)}개 — 4개 이상 필요")

    # 1) 터치 posx → 접촉점(핑거 끝, 베이스 mm). 기준점을 하나로 맞춘 뒤에만 계산한다 (#48 리뷰 P1)
    pose = {n: posx(r) for n, r in rows.items()}
    if args.pose_frame == "tcp":
        contact = {n: pose[n][:3] for n in cal + val}
    else:
        contact = {n: flange_to_tcp(pose[n], t_tcp) for n in cal + val}

    # 2) 관측 자세는 플랜지 기준으로 정규화 (voss_config observe_pose 와 같은 기준)
    obs = pose.get("OBS")
    obs_flange = None
    if obs is None:
        print("! OBS 행 없음 — 관측 자세·기울기 확인을 못 한다. 결과를 쓰지 말고 OBS 를 기록할 것")
    else:
        obs_flange = obs.copy()
        if args.pose_frame == "tcp":
            obs_flange[:3] = obs[:3] - rot_zyz_deg(*obs[3:]) @ t_tcp

    # 3) 기울기: ZYZ 각을 빼지 않고 툴 z축 사이 각으로 본다 (ry≈±180 에서 각 차가 360 가까이 튐)
    tilts = {n: tool_axis_angle_deg(pose[n], obs) for n in cal + val} if obs is not None else {}
    if tilts:
        worst = max(tilts, key=tilts.get)
        print(f"터치 툴축 − 관측 툴축 최대 {tilts[worst]:.2f}° ({worst}) — 접촉점은 TCP 로 정규화")
    for n, a in tilts.items():
        if a > TILT_WARN_DEG:
            print(
                f"  ! {n} 툴축이 {a:.2f}° 다름 — TCP 오프셋 오차가 섞일 수 있다. 자세·오프셋 확인"
            )

    # 4) 픽셀: 클릭 원본 → 왜곡 보정 (box_tracker 와 같은 함수)
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
    if first is None:
        print(f"! {cal[0]}.png 를 못 읽어 image_size 를 비운다 — 소비 노드가 해상도 확인을 못 한다")
    image_size = [int(first.shape[1]), int(first.shape[0])] if first is not None else None
    cam = load_camera_info(args.dir)
    k, d = cam if cam else (None, None)
    und = undistort_pixels(np.array([pix[n] for n in cal + val]), k, d)
    px = dict(zip(cal + val, und, strict=True))

    # 5) 호모그래피와 오차
    p_cal = np.array([px[n] for n in cal])
    xy_cal = np.array([contact[n][:2] for n in cal])
    h = fit_homography(p_cal, xy_cal)
    e_cal = point_errors_mm(h, p_cal, xy_cal)
    e_val = (
        point_errors_mm(h, np.array([px[n] for n in val]), np.array([contact[n][:2] for n in val]))
        if val
        else np.zeros(0)
    )
    z = np.array([contact[n][2] for n in cal + val])
    hull = convex_hull(und)

    print(f"계산점 {len(cal)}개 잔차 RMS {np.sqrt((e_cal**2).mean()):.2f} mm")
    for n, e in zip(val, e_val, strict=True):
        print(f"  검증 {n}: {e:.2f} mm {'OK' if e <= 5.0 else '초과'}")
    if val:
        print(f"검증점 최대 {e_val.max():.2f} mm (기준 ≤ 5 mm, 제안값)")
    else:
        print("! 검증점(V*) 없음 — 정확도 판정 불가")
    print(f"접촉점 z 평균 {z.mean():.1f} mm, 범위 {np.ptp(z):.1f} mm (기준 ≤ {Z_RANGE_WARN_MM} mm)")
    # 기준점을 잘못 주면 x, y 는 약 3 mm 만 틀려 검증을 통과할 수 있다 — z 가 약 247 mm 틀리는 걸로 잡는다
    print(
        "  → 이 z 가 핑거 끝을 박스 윗면에 댔을 때 펜던트 TCP z 와 같은지 확인"
        f" (--pose-frame 이 틀리면 약 {t_tcp[2]:.0f} mm 차이)"
    )
    print(f"유효 영역 calib_hull_px 꼭짓점 {len(hull)}개 — 밖은 외삽이라 position_valid=false")

    # 6) voss_config observe_pose 와 비교 (자리표시 0 이면 건너뜀)
    if obs_flange is not None and args.config.exists():
        cfg_obs = np.array(yaml.safe_load(args.config.read_text()).get("observe_pose") or [0] * 6)
        if np.any(cfg_obs):
            dp = float(np.linalg.norm(cfg_obs[:3] - obs_flange[:3]))
            da = tool_axis_angle_deg(cfg_obs, obs_flange)
            ok = dp <= POSE_MATCH_MM and da <= POSE_MATCH_DEG
            print(
                f"voss_config observe_pose 와 차이 {dp:.2f} mm / {da:.2f}° {'OK' if ok else '! 불일치'}"
            )

    tcp_px = None
    if obs is not None:
        obs_tcp_xy = obs[:2] if args.pose_frame == "tcp" else flange_to_tcp(obs, t_tcp)[:2]
        tcp_px = np.round(apply_homography(np.linalg.inv(h), [obs_tcp_xy])[0], 1).tolist()

    result = {
        "version": 1,
        "method": "belt_plane_homography",
        "created": datetime.now().isoformat(timespec="minutes"),
        "image_size": image_size,
        "observe_pose": np.round(obs_flange, 3).tolist() if obs_flange is not None else None,
        "input_pose_frame": args.pose_frame,
        "tcp_offset_mm": [float(v) for v in t_tcp],
        "plane_z_mm": round(float(z.mean()), 1),
        "undistort": {"k": k.ravel().tolist(), "d": d.tolist()} if cam else None,
        "H_px_to_base_xy": np.round(h, 9).tolist(),
        "calib_hull_px": np.round(hull, 1).tolist(),
        "tcp_pixel_at_observe": tcp_px,
        "errors_mm": {
            "calib_rms": round(float(np.sqrt((e_cal**2).mean())), 2),
            "val_max": round(float(e_val.max()), 2) if val else None,
            "val": {n: round(float(e), 2) for n, e in zip(val, e_val, strict=True)},
            "z_range": round(float(np.ptp(z)), 1),
            "tilt_max_deg": round(max(tilts.values()), 2) if tilts else None,
        },
    }
    args.out.write_text(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    print(f"저장 {args.out}")


if __name__ == "__main__":
    main()
