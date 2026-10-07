#!/usr/bin/env python3
"""10/06 실측 #9 — D435i 컬러 수동 노출 스윕. 로봇을 움직이지 않는다 (카메라 파라미터만 바꾼다).

카메라 노드가 떠 있어야 한다 (bringup camera:=true 또는 realsense 별칭). 송장 붙은 박스를
관측 높이(15~20 cm)에서 보게 둔 상태에서 실행한다.

    python3 exposure_sweep.py                       # 기본 50 60 70 80 (단위는 아래 참고)
    python3 exposure_sweep.py --values 40 50 60 80 100 --wb 4600 --tag lux320

- 실행하면 rgb_camera.exposure 의 허용 범위를 먼저 출력한다. 범위가 1~10000 이면 단위는 0.1 ms
  (50~80 = 5~8 ms). 다르면 --values 를 맞춰 다시 돌린다.
- 프레임마다 저장(PNG)하고 밝기 평균, 포화(≥250)·암부(≤5) 비율, 중앙 영역 선명도(라플라시안 분산)를 표로 낸다.
- 끝나면 자동 노출로 되돌리지 않는다(--restore-auto 로 되돌림). 고정값은 bringup 파라미터로 옮긴다.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))


def metrics(bgr, roi: float = 0.5) -> dict:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    y0, x0 = int(h * (1 - roi) / 2), int(w * (1 - roi) / 2)
    c = gray[y0 : h - y0, x0 : w - x0]
    return {
        "mean": float(gray.mean()),
        "sat_pct": float((gray >= 250).mean() * 100),
        "dark_pct": float((gray <= 5).mean() * 100),
        "sharp": float(cv2.Laplacian(c, cv2.CV_64F).var()),
        "roi_mean": float(np.mean(c)),
    }


class Cam:
    def __init__(self, node_name: str, topic: str):
        import rclpy
        from cv_bridge import CvBridge
        from rcl_interfaces.srv import DescribeParameters, SetParameters
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image

        self.rclpy = rclpy
        rclpy.init()
        self.node = rclpy.create_node("voss_exposure_sweep")
        self.bridge = CvBridge()
        self.frame, self.stamp_count = None, 0
        self.node.create_subscription(Image, topic, self._cb, qos_profile_sensor_data)
        self.set_cli = self.node.create_client(SetParameters, f"{node_name}/set_parameters")
        self.desc_cli = self.node.create_client(
            DescribeParameters, f"{node_name}/describe_parameters"
        )
        self.SetParameters, self.DescribeParameters = SetParameters, DescribeParameters
        for c in (self.set_cli, self.desc_cli):
            if not c.wait_for_service(timeout_sec=5.0):
                raise SystemExit(f"{c.srv_name} 없음. 카메라 노드 이름 확인: ros2 node list")

    def _cb(self, msg):
        self.frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        self.stamp_count += 1

    def _call(self, cli, req):
        fut = cli.call_async(req)
        self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=3.0)
        if not fut.done():
            raise RuntimeError(f"{cli.srv_name} 시간초과")
        return fut.result()

    def describe(self, names):
        r = self._call(self.desc_cli, self.DescribeParameters.Request(names=names))
        return r.descriptors

    def set(self, name: str, value) -> bool:
        from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue

        if isinstance(value, bool):
            pv = ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=value)
        else:
            pv = ParameterValue(type=ParameterType.PARAMETER_INTEGER, integer_value=int(value))
        r = self._call(
            self.set_cli, self.SetParameters.Request(parameters=[Parameter(name=name, value=pv)])
        )
        res = r.results[0]
        if not res.successful:
            print(f"  ⚠ {name}={value} 실패: {res.reason}")
        return res.successful

    def grab(self, settle_frames: int = 8, timeout: float = 5.0):
        start = self.stamp_count
        t0 = time.monotonic()
        while self.stamp_count - start < settle_frames:
            self.rclpy.spin_once(self.node, timeout_sec=0.1)
            if time.monotonic() - t0 > timeout:
                raise RuntimeError(
                    "이미지가 안 들어온다. 토픽 이름 확인: ros2 topic list | grep color"
                )
        return self.frame.copy()

    def close(self):
        self.node.destroy_node()
        self.rclpy.shutdown()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--node", default="/camera")
    ap.add_argument("--topic", default="/camera/color/image_raw")
    ap.add_argument("--values", type=int, nargs="+", default=[50, 60, 70, 80])
    ap.add_argument(
        "--wb", type=int, default=None, help="고정 화이트밸런스(K). 없으면 자동 WB 유지"
    )
    ap.add_argument("--gain", type=int, default=None)
    ap.add_argument("--tag", default="", help="조도 등 메모 (파일 이름에 붙는다)")
    ap.add_argument("--restore-auto", action="store_true")
    a = ap.parse_args(argv)

    import cv2

    out = DATA_DIR / f"exposure_{datetime.datetime.now():%H%M%S}{'_' + a.tag if a.tag else ''}"
    out.mkdir(parents=True, exist_ok=True)
    cam = Cam(a.node, a.topic)
    try:
        for d in cam.describe(
            ["rgb_camera.exposure", "rgb_camera.gain", "rgb_camera.white_balance"]
        ):
            rng = d.integer_range[0] if d.integer_range else None
            print(
                f"{d.name}: "
                + (
                    f"{rng.from_value}~{rng.to_value} step {rng.step}"
                    if rng
                    else "(범위 정보 없음)"
                )
            )
        rows = []
        auto = cam.grab()
        cv2.imwrite(str(out / "auto.png"), auto)
        rows.append(("auto", metrics(auto)))
        print(f"해상도 {auto.shape[1]}x{auto.shape[0]}")
        cam.set("rgb_camera.enable_auto_exposure", False)
        if a.wb is not None:
            cam.set("rgb_camera.enable_auto_white_balance", False)
            cam.set("rgb_camera.white_balance", a.wb)
        if a.gain is not None:
            cam.set("rgb_camera.gain", a.gain)
        for v in a.values:
            if not cam.set("rgb_camera.exposure", v):
                continue
            img = cam.grab()
            cv2.imwrite(str(out / f"exp_{v}.png"), img)
            rows.append((str(v), metrics(img)))
        lines = [
            "| 노출 | 밝기 평균 | 중앙 밝기 | 포화 % | 암부 % | 선명도 |",
            "|---|---|---|---|---|---|",
        ]
        for name, m in rows:
            lines.append(
                f"| {name} | {m['mean']:.0f} | {m['roi_mean']:.0f} | {m['sat_pct']:.2f} | "
                f"{m['dark_pct']:.2f} | {m['sharp']:.0f} |"
            )
        text = "\n".join(lines)
        print(text)
        (out / "result.md").write_text(text + f"\n\n태그: {a.tag}\n")
        print(f"\n저장: {out}  (PNG 는 남현지 OCR 확인용으로 공유. 레포에 커밋하지 않는다)")
        if a.restore_auto:
            cam.set("rgb_camera.enable_auto_exposure", True)
        return 0
    finally:
        cam.close()


if __name__ == "__main__":
    sys.exit(main())
