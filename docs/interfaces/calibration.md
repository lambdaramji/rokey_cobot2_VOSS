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
- **이동 중 좌표는 G0 필수이며 아직 없다.** 정식 핸드아이(10/07) + 촬영 시각 pose 보간 + 박스 윗면 평면(`plane_z_mm`) 교점으로 계산하고(`HAND_EYE`), 10/08 검증 전까지 이동 중에는 `position_valid=false` 로 낸다. 이 파일이 그 요구를 대신하지 않는다.
- **기준점:** 이 파일의 observe_pose 는 플랜지, H·plane_z 는 접촉점(핑거 끝) 기준으로 이미 정규화돼 있다. 측정 입력이 플랜지였으면 도구가 터치 자세마다 `p_tcp = p_flange + R_zyz(rx, ry, rz)·tcp_offset` 으로 바꿔 계산한다. 툴이 수직이어도 오프셋 xy 가 약 3 mm 라 기준점을 섞으면 x, y 가 약 3 mm, z 가 약 247 mm 어긋난다.
- 관측 자세가 바뀌면 다시 찍어야 한다.

## 변경 이력
- 2026-10-06: 신설 (#25).
- 2026-10-06: 운용 해상도 1280×720 확정(SRD 상호확인 MC-032) — image_size 를 사진에서 읽도록 변경.
- 2026-10-06 저녁: 운용 해상도를 **1920×1080 으로 최종 결정**(10/06 측정 데이터 재사용, SRD 상호확인 #51 MC-032). `pose_frame`·`tcp_offset_mm` 추가, 기준점 규칙 명시(MC-010, #48 리뷰 ①⑥).
- 2026-10-06 밤: #48 리뷰(박병후) 반영 — 좌표 계약을 BoxTrack 과 일치(비전이 변환, 관측 박스 윗면 중심, TCP 목표는 서보, 이 파일은 초기 획득 전용). `pose_frame` → `input_pose_frame`, observe_pose 는 플랜지·H 는 접촉점으로 정규화, `tcp_offset_mm` 항상 기록, `calib_hull_px` 추가, errors_mm 에 z_range·tilt_max_deg 추가.
- 2026-10-07: #48 리뷰(김학민) 반영 — `/voss/robot/pose` 는 TCP 기준(#53 MC-010)이므로 "observe_pose 와 같은 기준" 서술을 고치고, 관측 자세 비교는 `flange_to_tcp(observe_pose)` 로 한다고 명시. 터치 툴축 경고 기준 0.5° → 2°(10/06 관측 자세가 수직에서 0.93° 기울어 정상 터치도 전부 경고되던 오경보, 접촉점 정규화로 기울기 영향은 오프셋 오차 × 각도뿐).
