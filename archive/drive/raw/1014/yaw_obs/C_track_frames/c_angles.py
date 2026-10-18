#!/usr/bin/env python3
"""파트 C 녹화에서 트랙마다 박스 외곽 각도를 비전과 독립적으로 잰다 (읽기 전용).

1) /voss/vision/box 로 트랙별 프레임(stamp)·비전 yaw 를 모은다. 기준 프레임 = 박스 x 가 −93 mm(화면 가운데)에 가장 가까운 것.
2) 그 stamp 의 압축 영상을 풀어, 벨트 열(u 995~1265) 안에서 초록 벨트가 아닌 영역(골판지+송장) → 가장 큰 윤곽 → minAreaRect.
3) 꼭짓점을 belt_homography H_px_to_base_xy 로 벨트 평면에 옮겨 벨트 방향과의 각(벨트 0°, 위에서 반시계 +, (−90, 90]).
비전 yaw(송장 긴 축)와 다른 입력(박스 외곽)이라 '놓은 각' 추정으로 쓸 수 있다. 정확도는 대략 ±1~2° *(추정)*.
"""
import csv
import math
import os
import sys
import time

import cv2
import numpy as np
import rosbag2_py
import yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import CompressedImage
from voss_msgs.msg import BoxTrack

BAG = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
H = np.asarray(yaml.safe_load(open(os.path.expanduser("~/voss_ws/config/belt_homography.yaml")))["H_px_to_base_xy"], float)
BELT = np.array([0.99992, -0.01292])
BELT_DEG = math.degrees(math.atan2(BELT[1], BELT[0]))
U0, U1 = 995, 1265


def wrap(d):
    d = (d + 90) % 180 - 90
    return 90.0 if d == -90.0 else d


def to_base(px):
    p = np.c_[px, np.ones(len(px))] @ H.T
    return p[:, :2] / p[:, 2:3]


def reader(topic):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=BAG, storage_id="mcap"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    r.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    return r


tracks: dict[int, list] = {}
r = reader("/voss/vision/box")
while r.has_next():
    _, data, _ = r.read_next()
    m = deserialize_message(data, BoxTrack)
    tracks.setdefault(m.track_id, []).append(m)

want = {}
for tid, ms in tracks.items():
    ref = min(ms, key=lambda m: abs(m.position_base.x + 0.093))
    k = ref.stamp.sec * 10**9 + ref.stamp.nanosec
    want[k] = (tid, ref)

imgs = {}
r = reader("/camera/color/image_raw/compressed")
while r.has_next() and len(imgs) < len(want):
    _, data, _ = r.read_next()
    m = deserialize_message(data, CompressedImage)
    k = m.header.stamp.sec * 10**9 + m.header.stamp.nanosec
    if k in want:
        imgs[k] = cv2.imdecode(np.frombuffer(m.data, np.uint8), cv2.IMREAD_COLOR)

rows = []
for k, (tid, ref) in sorted(want.items()):
    ms = tracks[tid]
    ys = [wrap(math.degrees(m.yaw_base) - BELT_DEG) for m in ms if m.yaw_valid]
    c = sum(math.cos(math.radians(2 * y)) for y in ys) / max(len(ys), 1)
    s = sum(math.sin(math.radians(2 * y)) for y in ys) / max(len(ys), 1)
    vis = math.degrees(math.atan2(s, c)) / 2 if ys else float("nan")
    vis_ref = wrap(math.degrees(ref.yaw_base) - BELT_DEG) if ref.yaw_valid else float("nan")
    img = imgs.get(k)
    box_ang, e1, e2, note = float("nan"), float("nan"), float("nan"), ""
    if img is None:
        note = "프레임 없음"
    else:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 60, 20), (95, 255, 200))
        m = cv2.bitwise_not(green)
        col = np.zeros_like(m)
        col[:, U0:U1] = 255
        m &= col
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cs = [c_ for c_ in cs if cv2.pointPolygonTest(c_, (float(ref.u), float(ref.v)), False) >= 0] or cs
        if cs:
            cnt = max(cs, key=cv2.contourArea)
            px = cv2.boxPoints(cv2.minAreaRect(cnt))
            b = to_base(px)
            ed = [b[1] - b[0], b[2] - b[1]]
            e1, e2 = np.linalg.norm(ed[0]), np.linalg.norm(ed[1])
            long_e = ed[0] if e1 >= e2 else ed[1]
            box_ang = wrap(math.degrees(math.atan2(long_e[1], long_e[0])) - BELT_DEG)
            if not (38 <= min(e1, e2) <= 52 and 40 <= max(e1, e2) <= 60):
                note = "외곽 크기 이상"
            vis_img = img.copy()
            cv2.polylines(vis_img, [px.astype(np.int32)], True, (0, 0, 255), 3)
            cv2.circle(vis_img, (int(ref.u), int(ref.v)), 6, (0, 255, 255), -1)
            cv2.putText(vis_img, f"track {tid} box {box_ang:+.1f} vis {vis_ref:+.1f}", (U0 - 300, 60), 0, 1.2, (0, 0, 255), 3)
            cv2.imwrite(f"{OUT}/track{tid}.jpg", cv2.resize(vis_img[:, U0 - 320:U1 + 320], None, fx=0.5, fy=0.5),
                        [cv2.IMWRITE_JPEG_QUALITY, 80])
        else:
            note = "외곽 못 찾음"
    t0 = ms[0].stamp.sec + ms[0].stamp.nanosec * 1e-9
    rows.append(dict(track=tid, first=time.strftime("%H:%M:%S", time.localtime(t0)), frames=len(ms), yaw_valid=len(ys),
                     x_start=round(ms[0].position_base.x * 1000), x_end=round(ms[-1].position_base.x * 1000),
                     vision_yaw=round(vis, 2), vision_yaw_ref=round(vis_ref, 2), box_angle=round(box_ang, 1),
                     box_edges=f"{e1:.1f}x{e2:.1f}", diff=round(wrap(vis_ref - box_ang), 1) if not math.isnan(box_ang) else "",
                     note=note))

rows.sort(key=lambda d: d["track"])
with open(f"{OUT}/c_tracks.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
for d in rows:
    print(" | ".join(str(d[k]) for k in d))
