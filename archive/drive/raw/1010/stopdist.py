import sys, math, rosbag2_py
from rclpy.serialization import deserialize_message
from geometry_msgs.msg import PoseStamped
bag = sys.argv[1]
for tc in map(float, sys.argv[2:]):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=bag), rosbag2_py.ConverterOptions("", ""))
    r.set_filter(rosbag2_py.StorageFilter(topics=["/voss/robot/pose"]))
    r.seek(int((tc - 1.0) * 1e9))
    pts = []
    while r.has_next():
        _, d, t = r.read_next()
        if t > (tc + 3.0) * 1e9: break
        m = deserialize_message(d, PoseStamped)
        s = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        p = m.pose.position
        pts.append((s, p.x * 1e3, p.y * 1e3, p.z * 1e3))
    pts.sort()
    at = min(pts, key=lambda q: abs(q[0] - tc))
    # 멈춤: 0.2 s 창 속도 < 0.5 mm/s 가 처음 되는 시각
    stop = None
    for i, q in enumerate(pts):
        if q[0] < tc: continue
        w = [z for z in pts[i:] if z[0] - q[0] <= 0.2]
        if len(w) > 3 and math.dist(w[-1][1:], w[0][1:]) / (w[-1][0] - w[0][0]) < 0.5:
            stop = q; break
    fin = pts[-1]
    v_before = [q for q in pts if tc - 0.2 <= q[0] <= tc]
    vb = math.dist(v_before[-1][1:], v_before[0][1:]) / (v_before[-1][0] - v_before[0][0]) if len(v_before) > 2 else float('nan')
    print(f"cancel {tc:.3f}: 그때 TCP ({at[1]:.1f},{at[2]:.1f},{at[3]:.1f}) 속도≈{vb:.1f} mm/s | 멈춤 {stop[0]-tc:.3f} s 뒤 ({stop[1]:.1f},{stop[2]:.1f},{stop[3]:.1f}) 이동 {math.dist(stop[1:],at[1:]):.2f} mm | 3 s 뒤 총 {math.dist(fin[1:],at[1:]):.2f} mm")
