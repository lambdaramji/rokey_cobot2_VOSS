"""fit_hand_eye.py 와 같은 계산으로, 재투영 필터 없이 (a) 공장 K (b) 보드로 재추정한 K·왜곡 을 비교."""
import sys, csv, itertools, numpy as np, cv2, yaml
from pathlib import Path
sys.path.insert(0, str(Path.home()/'voss_he/src/voss_vision'))
from voss_vision.belt_plane import flange_to_tcp, rot_zyz_deg
from voss_vision.hand_eye import (COMPARE, board_in_base, board_object_points, board_pose, make_t, mean_pose,
                                  pixel_to_plane, quat_to_rot, rot_angle_deg, solve, spread)
D = Path.home()/'voss_data/1008/handeye'; BOARD=(10,7); SQ=float(sys.argv[1]) if len(sys.argv)>1 else 25.0
drop = sys.argv[2:] 
info = yaml.safe_load(open(D/'camera_info.yaml')); K0=np.array(info['k']).reshape(3,3); D0=np.array(info['d'])
rows=[r for r in csv.DictReader(open(D/'poses.csv')) if r['name'] not in drop]
names, T, C = [], [], []
for r in rows:
    g=cv2.imread(str(D/f"{r['name']}.png"),0); ok,c=cv2.findChessboardCornersSB(g,BOARD)
    if not ok: print('no corners',r['name']); continue
    names.append(r['name']); C.append(c)
    T.append(make_t(quat_to_rot(*[float(r[x]) for x in ('qx','qy','qz','qw')]),[float(r[x]) for x in ('x_mm','y_mm','z_mm')]))
size=g.shape[::-1]
obj=[board_object_points(BOARD,SQ)]*len(C)
rms,K1,D1,_,_=cv2.calibrateCamera(obj,C,size,None,None)
print(f"photos {len(names)}; re-estimated K fx {K1[0,0]:.1f} fy {K1[1,1]:.1f} cx {K1[0,2]:.1f} cy {K1[1,2]:.1f} d {np.round(D1.ravel(),4).tolist()} rms {rms:.3f}px")
print(f"factory   K fx {K0[0,0]:.1f} fy {K0[1,1]:.1f} cx {K0[0,2]:.1f} cy {K0[1,2]:.1f}")
# 자세 다양성
angs=[rot_angle_deg(a[:3,:3],b[:3,:3]) for a,b in itertools.combinations(T,2)]
print(f"pairwise TCP rotation: median {np.median(angs):.1f} deg, max {max(angs):.1f} deg")
cal=yaml.safe_load(open(Path.home()/'voss_he/config/belt_homography.yaml'))
obs=np.array(cal['observe_pose']); t_obs=make_t(rot_zyz_deg(*obs[3:6]), flange_to_tcp(obs,np.array(cal['tcp_offset_mm']))); zp=float(cal['plane_z_mm'])
pts={r['name']:r for r in csv.DictReader(open(Path.home()/'voss_data/1007/t16/points.csv'))}
pix={r['name']:r for r in csv.DictReader(open(Path.home()/'voss_data/1007/t16/pixels.csv'))}
for label,K,Dd in (("(a) factory K, d=0",K0,D0),("(b) re-estimated K,d",K1,D1.ravel())):
    B=[]; errs=[]
    for c in C:
        t,e=board_pose(c,BOARD,SQ,K,Dd); B.append(t); errs.append(e)
    sols={m:solve(T,B,m) for m in COMPARE}; X=sols['PARK']
    mm=max(np.linalg.norm(a[:3,3]-b[:3,3]) for a in sols.values() for b in sols.values())
    boards=board_in_base(T,X,B); bmm,bdeg=spread(boards); mb=mean_pose(boards)
    per=[np.linalg.norm(b[:3,3]-mb[:3,3]) for b in boards]
    tb=t_obs@X; val=[]
    for n,p in pix.items():
        if n in pts:
            xyz,ok=pixel_to_plane(tb,K,Dd,[[float(p['u']),float(p['v'])]],zp)
            if ok[0]: val.append(np.hypot(xyz[0,0]-float(pts[n]['x']),xyz[0,1]-float(pts[n]['y'])))
    print(f"\n{label}: reproj max per photo {min(errs):.2f}~{max(errs):.2f} px")
    print(f"  T_tcp_camera PARK {np.round(X[:3,3],2).tolist()} mm, optical vs tool {np.degrees(np.arccos(np.clip(X[2,2],-1,1))):.2f} deg")
    print(f"  ① board_spread {bmm:.2f} mm / {bdeg:.3f} deg (≤2 / 0.5)   ② method_spread {mm:.2f} mm (≤2)   ③ t16 max {max(val):.2f} mm, mean {np.mean(val):.2f} (≤5)")
    print("  per-photo board diff mm: "+" ".join(f"{n[3:]}:{d:.1f}" for n,d in zip(names,per)))
