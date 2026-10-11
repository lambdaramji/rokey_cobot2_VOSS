"""하강 중 송장이 화면 아래 끝에 걸려 box_tracker 가 버리기 시작하는 TCP 높이 — belt_servo `vision_cutoff_above_top_mm` 근거.

카메라가 공구축에서 약 8 cm 옆이라 TCP 가 박스 위로 내려가면 송장이 화면 아래로 빠진다. box_tracker 는 가장자리에
걸린 송장을 내지 않으므로(box_detect `border_px`, 중심이 치우침) 그 높이부터 BoxTrack 이 끊긴다. belt_servo 는
`vision_cutoff_above_top_mm` 아래만 비전 사각으로 보므로, 끊긴 높이가 그보다 위면 그 사이를 하강하는 동안
`lost_timeout_s` 가 돌아 LOST 가 난다(10/10 G1 기울어진 박스 하강 LOST, #30).

계산(핸드아이 모델, 로봇과 무관): TCP 를 박스 윗면 중심 위(정렬 허용 오차만큼 벗어남 포함)에 관측 자세 방향으로 두고
송장(40 × 25 mm, 긴 변 = 벨트 방향, 박스 회전각만큼 돌림)의 네 꼭짓점을 `T_tcp_camera`·K·왜곡으로 투영한다.
핸드아이 오차(≤ 5 mm 제안값)는 이 거리에서 수십 px 이라 여유가 몇 px 인 결과는 녹화(tools/vision/box_overlay.py)로 확인한다.

  python3 tools/calib/descend_visibility.py [--approach 40 --cutoff 10 --descend-mps 0.05 --lost-s 0.5]
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "voss_vision"))
from voss_vision.hand_eye import posx_to_t  # noqa: E402

LABEL_MM = (40.0, 25.0)  # 송장 (긴 변 = 박스 46 mm 변 = 벨트 방향, ADR-0009)


def label_px(h_mm, yaw_deg, d_along, d_cross, *, t_tcp_cam, k, d, top_z, rot_zyz, belt):
    """TCP 가 박스 윗면 + h_mm, 박스 중심에서 (벨트 방향 d_along, 가로 d_cross) mm 벗어났을 때 송장 꼭짓점 픽셀."""
    cross = np.array([-belt[1], belt[0]])
    box = np.zeros(2)
    tcp_xy = box + d_along * belt + d_cross * cross
    t_cam = posx_to_t([tcp_xy[0], tcp_xy[1], top_z + h_mm, *rot_zyz]) @ t_tcp_cam
    a = np.radians(yaw_deg)
    r = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    lx, ly = LABEL_MM[0] / 2, LABEL_MM[1] / 2
    local = np.array([[lx, ly], [lx, -ly], [-lx, -ly], [-lx, ly]]) @ r.T
    world = np.array([[*(box + p[0] * belt + p[1] * cross), top_z] for p in local])
    inv = np.linalg.inv(t_cam)
    pc = (inv[:3, :3] @ world.T).T + inv[:3, 3]
    if (pc[:, 2] <= 0).any():
        return None
    uv, _ = cv2.projectPoints(pc, np.zeros(3), np.zeros(3), k, d)
    return uv.reshape(-1, 2)


def cut_height(geo, yaw, da, dc, size, border, h_from, h_to, step=0.1):
    """h_from 에서 내려가며 송장이 가장자리 판정에 처음 걸리는 높이. 끝까지 안 걸리면 None."""
    w, h = size
    for hh in np.arange(h_from, h_to - step / 2, -step):
        uv = label_px(hh, yaw, da, dc, **geo)
        if uv is None:
            return float(hh)
        x0, y0 = uv.min(0)
        x1, y1 = uv.max(0)
        if x0 <= border or y0 <= border or x1 >= w - border or y1 >= h - border:
            return float(hh)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hand-eye", type=Path, default=REPO / "config/hand_eye.yaml")
    ap.add_argument("--homography", type=Path, default=REPO / "config/belt_homography.yaml",
                    help="plane_z_mm = 박스 윗면 z")  # fmt: skip
    ap.add_argument("--voss-config", type=Path, default=REPO / "config/voss_config.yaml",
                    help="observe_pose 방향(하강 중 그대로)·belt.direction_base")  # fmt: skip
    ap.add_argument(
        "--approach",
        type=float,
        default=40.0,
        help="하강 시작 높이(윗면 기준 mm) approach_above_top_mm",
    )
    ap.add_argument(
        "--cutoff", type=float, default=10.0, help="지금 사각 높이 vision_cutoff_above_top_mm"
    )
    ap.add_argument("--descend-mps", type=float, default=0.05, help="하강 속도 descend_speed_mps")
    ap.add_argument("--lost-s", type=float, default=0.5, help="lost_timeout_s")
    ap.add_argument(
        "--tol-along", type=float, default=3.0, help="정렬 허용 벨트 방향 mm align_tol_along_mm"
    )
    ap.add_argument(
        "--tol-cross", type=float, default=5.0, help="정렬 허용 가로 mm align_tol_cross_mm"
    )
    ap.add_argument("--border", type=int, default=4, help="box_detect border_px")
    ap.add_argument("--yaws", default="0,10,15,20,30,45", help="박스 회전각(°), 쉼표")
    args = ap.parse_args()

    he = yaml.safe_load(args.hand_eye.read_text())
    vc = yaml.safe_load(args.voss_config.read_text())
    geo = {
        "t_tcp_cam": np.asarray(he["T_tcp_camera"], float),
        "k": np.asarray(he["camera"]["k"], float).reshape(3, 3),
        "d": np.asarray(he["camera"].get("d") or [0.0] * 5, float),
        "top_z": float(yaml.safe_load(args.homography.read_text())["plane_z_mm"]),
        "rot_zyz": [float(x) for x in vc["observe_pose"][3:6]],
        "belt": np.asarray(vc["belt"]["direction_base"][:2], float),
    }
    size = tuple(int(x) for x in he.get("image_size", [1920, 1080]))
    yaws = [float(y) for y in args.yaws.split(",")]
    lim = size[1] - args.border
    offsets = [(0.0, 0.0)] + [
        (sa * args.tol_along, sc * args.tol_cross) for sa in (1, -1) for sc in (1, -1)
    ]

    heights = [
        args.approach + 10,
        args.approach,
        args.approach - 5,
        args.approach - 10,
        20,
        args.cutoff,
        0,
    ]
    print(f"송장 아래 끝 v (TCP 가 박스 중심 바로 위, 화면 {size[1]}, 버림 ≥ {lim})")
    print("회전 \\ 윗면+mm " + "".join(f"{h:>7.0f}" for h in heights))
    for yaw in yaws:
        row = []
        for hh in heights:
            uv = label_px(hh, yaw, 0.0, 0.0, **geo)
            row.append("      -" if uv is None else f"{uv[:, 1].max():7.0f}")
        print(f"{yaw:5.0f}°        " + "".join(row))

    print(f"\n하강 {args.approach:g} → 사각 {args.cutoff:g} mm, {args.descend_mps * 1000:g} mm/s, LOST {args.lost_s:g} s "
          f"(정렬 오차 벨트 ±{args.tol_along:g}·가로 ±{args.tol_cross:g} mm 네 귀퉁이 + 중심)")  # fmt: skip
    print(" 회전  버리기 시작 높이(최고~최저)  안 보이는 하강 최대  시간 최대  판정")
    worst = None
    for yaw in yaws:
        cuts = [
            cut_height(geo, yaw, da, dc, size, args.border, args.approach, args.cutoff)
            for da, dc in offsets
        ]
        hs = [c for c in cuts if c is not None]  # None = 사각 높이까지 안 걸림
        if not hs:
            print(f"{yaw:5.0f}°  사각 높이까지 안 걸림  0 mm  0.00 s  -")
            continue
        top = max(hs)
        span = max(0.0, min(top, args.approach) - args.cutoff)
        t = span / (args.descend_mps * 1000)
        worst = top if worst is None else max(worst, top)
        print(f"{yaw:5.0f}°  {top:+.1f} ~ {min(hs):+.1f} mm  {span:5.1f} mm  {t:5.2f} s  "
              f"{'LOST' if t > args.lost_s else '-'}")  # fmt: skip
    if worst is not None:
        need = float(np.ceil(worst))
        print(f"\n사각 높이를 하강 중 가장 먼저 끊기는 높이({worst:+.1f} mm) 이상으로 두면 그 사이 LOST 가 나지 않는다 → "
              f"후보 {need:g} mm (교차 검사: approach {args.approach:g} > cutoff + 5 이면 cutoff ≤ {args.approach - 5:g})")  # fmt: skip
        if need > args.approach - 5:
            print(f"  ⚠ {need:g} 은 approach − 5 를 넘는다 → cutoff {args.approach - 5:g} 로 두면 남는 "
                  f"{need - (args.approach - 5):g} mm 는 {(need - (args.approach - 5)) / (args.descend_mps * 1000):.2f} s "
                  f"(LOST {args.lost_s:g} s 미만이면 괜찮다), 아니면 approach 를 올린다")  # fmt: skip
    print(
        "\n※ 핸드아이 모델 값. 여유가 몇 px 이면 핸드아이 오차 안이다 — G1 녹화를 box_overlay.py 로 재생해 실제 끊긴 높이를 본다."
    )


if __name__ == "__main__":
    main()
