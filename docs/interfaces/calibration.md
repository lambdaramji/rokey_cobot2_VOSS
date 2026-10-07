# 카메라 캘리브레이션 결과 파일 (ADR-0003)

`config/belt_homography.yaml` — 관측 자세에서 **픽셀 → 로봇 베이스 (x, y) mm** 변환. `tools/calib/fit_belt_homography.py` 가 만든다(사람이 실행, 노드는 쓰지 않음). 비전 컨테이너에는 `config/` 와 함께 읽기 전용 마운트.

| 키 | 형식 | 뜻 |
|---|---|---|
| version | int | 1 |
| method | str | `belt_plane_homography` (정식 핸드아이로 바뀌면 `hand_eye`) |
| created | str | 계산 시각 |
| image_size | [w, h] | 사진에서 읽은 실제 크기. 운용 해상도 1920, 1080 (MC-032 최종). 카메라 해상도가 다르면 무효 |
| observe_pose | [x, y, z, rx, ry, rz] | 사진을 찍은 관측 자세 posx, **플랜지 기준**(voss_config `observe_pose` 와 같음). `/voss/robot/pose` 는 **TCP** 기준(#53 MC-010)이라, 비교할 때는 `belt_plane.flange_to_tcp(observe_pose, tcp_offset_mm)` 로 위치를 바꾼다(툴 오프셋은 평행이동뿐이라 자세는 같다). 입력이 TCP 면 도구가 플랜지로 바꿔 적는다. **이 자세에서만 유효** |
| input_pose_frame | str | points.csv 가 어느 기준이었는지 기록(`tcp`/`flange`). 10/06 측정은 `tcp`. 출력 값은 이것과 무관하게 아래 의미로 정규화돼 있다 |
| tcp_offset_mm | [x, y, z] | 플랜지 → 핑거 끝 오프셋(툴 좌표). 항상 기록. 10/06: (1.382, 2.684, 246.642) |
| plane_z_mm | float | 박스 윗면(벨트 + 27 mm) 높이 = 접촉점(핑거 끝) z 평균, 베이스 mm |
| undistort | {k[9], d[]} 또는 null | 왜곡 보정 파라미터. 픽셀을 먼저 이걸로 보정한 뒤 H 적용 |
| H_px_to_base_xy | 3×3 | 보정된 픽셀 [u, v, 1] → [x, y, w], (x/w, y/w) mm = **박스 윗면 위 접촉점** (x, y) |
| calib_hull_px | [[u, v], …] | 대응점 9개(계산 + 검증)의 볼록 껍질, 보정 후 픽셀. **밖은 외삽 → `position_valid=false`** |
| tcp_pixel_at_observe | [u, v] | 관측 자세에서 TCP 바로 아래 박스 윗면 점의 픽셀(툴이 수직일 때). 화면 확인용 참고값 |
| errors_mm | {calib_rms, val_max, val{}, z_range, tilt_max_deg} | 계산점 잔차, 검증점 오차 (SR-FN-02, ≤ 5 mm 제안값), 접촉점 z 범위(≤ 3 mm), 터치 자세 툴축과 관측 자세 툴축의 최대 각(참고값, 2° 넘으면 경고 — 접촉점은 TCP 로 정규화돼 기울기 자체는 오차가 아님) |

## 쓰는 곳 (좌표 계약 — voss_msgs.md BoxTrack 과 같은 정의, #50 MC-001·002)
- **변환은 비전 단일 책임.** box_tracker 가 `voss_vision.belt_plane.pixel_to_base_xy` (왜곡 보정 → H → 유효 영역 판정)로 박스 윗면 중심 픽셀을 바꿔 `BoxTrack.position_base` 에 싣는다. belt_servo 는 이 파일·변환 함수를 쓰지 않는다.
- **출력의 뜻:** `position_base` = 촬영 시각(`stamp`)에 관측한 **박스 윗면 중심**, m, 베이스 축. x, y 는 H, z 는 `plane_z_mm`. **TCP 목표가 아니다** — 지연·벨트 속도 예측, 파지 높이·오프셋을 반영한 핑거 끝/TCP 목표는 belt_servo 가 계산한다.
- **이 파일의 범위:** 관측 자세에서 정지해 있을 때의 **초기 위치 획득**(`position_source=OBSERVE_HOMOGRAPHY`)만. 현재 pose(`/voss/robot/pose`, TCP)가 `flange_to_tcp(observe_pose)` 와 1 mm / 0.5°(툴축 각) 넘게 다르거나, 픽셀이 `calib_hull_px` 밖이거나, `image_size` 가 카메라와 다르면 `position_valid=false`.
- **이동 중 좌표는 G0 필수이며 이 파일이 대신하지 않는다** → 아래 `config/hand_eye.yaml`.
- **기준점:** 이 파일의 observe_pose 는 플랜지, H·plane_z 는 접촉점(핑거 끝) 기준으로 이미 정규화돼 있다. 측정 입력이 플랜지였으면 도구가 터치 자세마다 `p_tcp = p_flange + R_zyz(rx, ry, rz)·tcp_offset` 으로 바꿔 계산한다. 툴이 수직이어도 오프셋 xy 가 약 3 mm 라 기준점을 섞으면 x, y 가 약 3 mm, z 가 약 247 mm 어긋난다.
- 관측 자세가 바뀌면 다시 찍어야 한다.

# 핸드아이 결과 파일 — 이동 중 좌표 (G0 필수)

`config/hand_eye.yaml` — **TCP → 카메라 광학 좌표계** 고정 변환(Eye-in-Hand). `tools/calib/fit_hand_eye.py` 가 만든다(사람이 실행). 촬영은 `tools/calib/handeye_capture.py` 가 `/voss/robot/pose`(TCP) 와 영상을 함께 저장한다 — 두산 서비스를 직접 부르지 않는다(규칙 3). 깊이는 쓰지 않는다(규칙 4).

| 키 | 형식 | 뜻 |
|---|---|---|
| version | int | 1 |
| method | str | `hand_eye` |
| created | str | 계산 시각 |
| solver | str | 채택한 `cv2.calibrateHandEye` 방법(`PARK` 등). 다른 방법 결과와의 차이는 errors 에 |
| board | {inner_corners: [c, r], square_mm} | 체커보드. 10/08 = 강의 배포 보드 11×8 칸 → 내부 코너 [10, 7], 25.0 mm |
| image_size | [w, h] | 1920, 1080. 카메라 해상도가 다르면 무효 |
| camera | {k[9], d[], source} | 풀이에 쓴 내부 파라미터. `source: camera_info`(공장값). 운용 중 camera_info 의 k 가 이것과 다르면 무효 |
| pose_frame | str | `tcp` — 입력 자세는 `/voss/robot/pose`(TCP, `base_link`) |
| tcp_offset_mm | [x, y, z] | 촬영 때 voss_config `robot.tcp_offset_mm`. 이 값이 바뀌면 TCP 정의가 바뀐 것이라 다시 계산한다 |
| T_tcp_camera | 4×4 | 카메라 광학 좌표계(x 오른쪽, y 아래, z 앞)의 점을 TCP 좌표로: `p_tcp = T · p_cam`. 평행이동 mm |
| moving_verified | bool | 이동 중 검증(멈춘 박스를 로봇 이동 중 관측) 통과 여부. **false 면 이동 중 `position_valid=false`** |
| errors | dict | `n_used`·`n_rejected`, `reproj_px_max`, `board_spread_mm`·`board_spread_deg`(사진마다 계산한 베이스→보드의 흩어짐), `method_spread_mm`·`method_spread_deg`, `t16_val_max_mm`·`t16_val`(T16 검증점을 이 변환으로 다시 계산한 오차), `moving_spread_mm`(이동 중 검증) |

**합격 기준(제안값, SR-FN-02 의 5 mm 와 같은 축):** board_spread ≤ 2 mm·0.5°, method_spread ≤ 2 mm, t16_val_max ≤ 5 mm, moving_spread ≤ 5 mm. 핵심은 board_spread — 여러 자세에서 같은 보드가 같은 곳에 나와야 움직이는 카메라에서도 맞는다. T16 점(한 평면·좁은 영역)만으로는 카메라 자세가 정해지지 않으므로(10/07: PnP 와 호모그래피 분해가 37 mm·7° 차이) 핸드아이를 대신할 수 없다.

## 쓰는 곳 (box_tracker, `voss_vision.hand_eye`)
- 촬영 시각 `stamp` 의 TCP pose 를 `/voss/robot/pose` 이력에서 **보간**한다(위치 선형, 자세 slerp). pose stamp 는 응답 수신 시각(MC-004)이라 측정 시각과 RTT 만큼 어긋날 수 있다 — 보장 오차로 쓰지 않는다. 앞뒤 pose 가 없거나 가장 가까운 pose 가 40 ms(2 주기, 제안값) 넘게 떨어져 있으면 외삽하지 않고 `position_valid=false`.
- `T_base_camera(t) = T_base_tcp(t) · T_tcp_camera`, 왜곡 보정한 박스 윗면 중심 픽셀의 광선이 **박스 윗면 평면 z = `belt_homography.yaml` 의 `plane_z_mm`** 과 만나는 점이 `position_base`(m) — 평면 높이는 그 파일 하나에서만 읽는다. `position_source = SOURCE_HAND_EYE`.
- 관측 자세에 정지해 있을 때는 지금처럼 `OBSERVE_HOMOGRAPHY` 를 쓰고, 그때 두 방식의 차이를 로그로 남긴다(3 mm 넘으면 경고). 관측 자세를 벗어나면 `HAND_EYE`.
- `position_valid=false`: 파일 없음·`moving_verified=false`(이동 중일 때)·image_size 나 k 불일치·pose 보간 불가·광선이 평면과 거의 평행(광선과 평면 법선 사이 75° 초과, 제안값).
- 카메라를 다시 달거나 툴(TCP) 정의가 바뀌면 다시 찍는다.

## 변경 이력
- 2026-10-06: 신설 (#25).
- 2026-10-06: 운용 해상도 1280×720 확정(SRD 상호확인 MC-032) — image_size 를 사진에서 읽도록 변경.
- 2026-10-06 저녁: 운용 해상도를 **1920×1080 으로 최종 결정**(10/06 측정 데이터 재사용, SRD 상호확인 #51 MC-032). `pose_frame`·`tcp_offset_mm` 추가, 기준점 규칙 명시(MC-010, #48 리뷰 ①⑥).
- 2026-10-06 밤: #48 리뷰(박병후) 반영 — 좌표 계약을 BoxTrack 과 일치(비전이 변환, 관측 박스 윗면 중심, TCP 목표는 서보, 이 파일은 초기 획득 전용). `pose_frame` → `input_pose_frame`, observe_pose 는 플랜지·H 는 접촉점으로 정규화, `tcp_offset_mm` 항상 기록, `calib_hull_px` 추가, errors_mm 에 z_range·tilt_max_deg 추가.
- 2026-10-07: #48 리뷰(김학민) 반영 — `/voss/robot/pose` 는 TCP 기준(#53 MC-010)이므로 "observe_pose 와 같은 기준" 서술을 고치고, 관측 자세 비교는 `flange_to_tcp(observe_pose)` 로 한다고 명시. 터치 툴축 경고 기준 0.5° → 2°(10/06 관측 자세가 수직에서 0.93° 기울어 정상 터치도 전부 경고되던 오경보, 접촉점 정규화로 기울기 영향은 오프셋 오차 × 각도뿐).
- 2026-10-07: `config/hand_eye.yaml`(정식 핸드아이, 이동 중 좌표) 절 신설 — T_tcp_camera, 합격 기준, box_tracker 사용 규칙(pose 보간 40 ms, 평면 높이는 belt_homography 하나, `moving_verified`). 촬영은 `/voss/robot/pose` 구독(김학민 T32 ①, 두산 직접 호출 없음). 촬영 10/08 오전.
