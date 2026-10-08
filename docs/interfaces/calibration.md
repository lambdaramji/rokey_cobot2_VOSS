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
- **이 파일의 범위:** 관측 자세에서 정지해 있을 때의 좌표. `hand_eye.yaml` 이 `moving_verified=true` 면 **기본 출처는 핸드아이**이고 이 파일은 같은 픽셀의 비교값(로그, 3 mm 경고)으로만 쓴다 — 한 트랙 안에서 출처가 바뀌어 좌표가 2~4 mm 튀지 않게, 그리고 이 파일의 유효 영역(x −100 ~ +3 mm, 박스당 약 2.1 s) 밖에서도 좌표가 이어지게(10/08 박병후 #90·#95 리뷰). 핸드아이가 없거나 미검증이면, 또는 box_tracker `observe_source: homography`(되돌림용, 게이트 측정 중 바꾸지 않음)면 `position_source=OBSERVE_HOMOGRAPHY` 로 쓴다. 이때 현재 pose(`/voss/robot/pose`, TCP)가 `flange_to_tcp(observe_pose)` 와 1 mm / 0.5°(**자세 전체 각** — 공구축 둘레 회전 포함: 카메라가 TCP 에서 떨어져 있어 rz 만 달라도 화면이 돈다) 넘게 다르거나, 픽셀이 `calib_hull_px` 밖이거나, `image_size` 가 카메라와 다르면 `position_valid=false`.
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
| solver | str | 채택한 `cv2.calibrateHandEye` 방법(`PARK` 등). 터치로 위치를 고쳤으면 `PARK + touch_translation`. 다른 방법 결과와의 차이는 errors 에 |
| board | {inner_corners: [c, r], square_mm} | 체커보드. 10/08 = 강의 배포 보드 11×8 칸 → 내부 코너 [10, 7], 25.0 mm |
| image_size | [w, h] | 1920, 1080. 카메라 해상도가 다르면 무효 |
| camera | {k[9], d[], source} | **좌표 계산에 쓰는** 내부 파라미터. `source: camera_info`(공장값) 또는 `board_reestimate …`(보드 사진으로 재추정 — 10/08 채택: 공장 camera_info 는 d = 0 이라 보드 재투영 1 px 를 못 맞췄다). box_tracker 는 픽셀 왜곡 보정·광선에 이 k·d 를 쓴다 |
| camera_factory | {k[9], d[]} | 촬영 때 camera_info(공장값). **운용 중 camera_info 의 k 를 이것과 비교**해 다르면(1 px 초과) 무효 — 카메라·해상도가 바뀐 것. 없으면 camera.k 와 비교 |
| pose_frame | str | `tcp` — 입력 자세는 `/voss/robot/pose`(TCP, `base_link`) |
| tcp_offset_mm | [x, y, z] | 촬영 때 voss_config `robot.tcp_offset_mm`. 이 값이 바뀌면 TCP 정의가 바뀐 것이라 다시 계산한다 |
| T_tcp_camera | 4×4 | 카메라 광학 좌표계(x 오른쪽, y 아래, z 앞)의 점을 TCP 좌표로: `p_tcp = T · p_cam`. 평행이동 mm. 위치 보정을 했으면 보정 뒤 값 |
| touch_correction | {offset_camera_mm[3], solver_translation_mm[3], n_t16, n_touch, source} 또는 null | 보드 풀이 뒤 **T16 대응점 + 터치 점(위치를 아는 박스 윗면 점)에 맞게 카메라 위치만 고친 양**(카메라 좌표, 회전 그대로). 보정 전 위치를 같이 남긴다 |
| moving_verified | bool | 이동 중 검증(멈춘 박스를 로봇 이동 중 관측) 통과 여부 — `moving_spread_mm`·`moving_spread_lag_mm` 가 모두 5 mm 이하. **false 면 이동 중 `position_valid=false`** |
| errors | dict | `n_used`·`n_rejected`, `reproj_px_max`, `board_spread_mm`·`board_spread_deg`(사진마다 계산한 베이스→보드의 흩어짐), `method_spread_mm`·`method_spread_deg`, `t16_val_max_mm`·`t16_val`(T16 검증점을 이 변환으로 다시 계산한 오차), `moving_spread_mm`(이동 중 검증) · 위치 보정 때 `board_spread_corrected_mm`(보정 뒤 보드 흩어짐 = 보드와 터치 데이터의 어긋남)·`touch_val`·`touch_val_max_mm` · 이동 중 검증 `moving_spread_mm`(영상-pose 지연 0)·`moving_spread_lag_mm`(`pose_lag_ms_measured` 적용)·`moving_note`(bag·속도·프레임 수) |

**합격 기준(제안값, SR-FN-02 의 5 mm 와 같은 축):** board_spread ≤ 2 mm·0.5°(보드 풀이 그대로의 값), method_spread ≤ 2 mm, t16_val_max ≤ 5 mm, touch_val_max ≤ 5 mm(터치를 쓴 경우), moving_spread·moving_spread_lag ≤ 5 mm. board_spread 는 보드 사진끼리 일관된지만 본다 — 그리퍼가 가는 TCP 좌표와 맞는지는 T16·터치·이동 중 검증이 본다. 10/08: board_spread 0.85 mm 였지만 T16·터치는 광축 방향으로 약 9 mm 어긋나 (보드 사진이 모두 ≤ 25° 기울기) 위치를 고쳤고, 고친 뒤 board_spread 는 4.1 mm(`board_spread_corrected_mm`)가 된다. 공구가 수직이면 "카메라 거리" 오차와 "평면(터치 z·TCP z) 높이" 오차는 효과가 같아 이 데이터로 가를 수 없다 — 보정은 TCP 좌표에 맞췄으므로 **수직 공구(G0 고정 파지 자세)에서 유효**하고, 공구를 기울여 쓰기 전에는 기울기 30° 이상 자세로 다시 찍어 가린다. T16 점만으로는 카메라 자세가 정해지지 않으므로(10/07: PnP 와 호모그래피 분해가 37 mm·7° 차이) 회전은 보드 풀이 그대로 두고 위치만 고친다.

## 쓰는 곳 (box_tracker, `voss_vision.hand_eye`)
- 촬영 시각 `stamp` **+ `pose_lag_ms`** 의 TCP pose 를 `/voss/robot/pose` 이력에서 구한다(위치 선형, 자세 slerp). pose stamp 는 응답 수신 시각(MC-004, gateway `pose_source: service` — 기본)이라 실제 로봇 상태보다 늦다(`joint_states` 소스는 관절 읽은 시각이라 이 지연이 대부분 없어진다 — 그 소스로 바꿀 때 `pose_lag_ms` 를 다시 잰다, topics.md·#118): 10/08 이동 중 검증에서 영상 시각보다 약 60 ms 뒤 stamp 의 pose 를 쓸 때 흔들림이 가장 작았다(2.55 → 1.13 mm). `pose_lag_ms`(기본 60)는 box_tracker 파라미터다. 그 시각이 이력 안이면 보간하되 가장 가까운 pose 가 40 ms(2 주기, 제안값) 넘게 떨어져 있거나 **보간하는 앞뒤 pose 사이가 80 ms(2 × 40)를 넘으면** 무효(게이트웨이 호출 큐가 막혀 pose 가 끊긴 구간을 선형으로 메우지 않는다), **마지막 pose 보다 뒤면 최근 pose 5개의 속도로 `pose_max_extrap_ms`(80 ms, 제안값)까지만 앞으로 외삽**한다(그 pose 가 올 때까지 기다리면 BoxTrack 이 약 40 ms 늦어진다. 등속 추종에서는 외삽 오차가 1 mm 미만). 이력이 끊겼거나(간격 > 40 ms) 80 ms 를 넘으면 무효. 첫 pose 보다 앞은 외삽하지 않는다.
- `T_base_camera(t) = T_base_tcp(t) · T_tcp_camera`, 왜곡 보정한 박스 윗면 중심 픽셀의 광선이 **박스 윗면 평면 z = `belt_homography.yaml` 의 `plane_z_mm`** 과 만나는 점이 `position_base`(m) — 평면 높이는 그 파일 하나에서만 읽는다. `position_source = SOURCE_HAND_EYE`.
- 출처: **`moving_verified=true` 면 관측 자세에서도 `HAND_EYE`**(위 "이 파일의 범위"). 관측 자세에 정지해 있고 픽셀이 호모그래피 유효 영역 안이면 같은 픽셀의 호모그래피 값과의 차이를 로그로 남긴다(3 mm 넘으면 경고 — 10/08 A_MIX 재생 최대 2.2 mm). `observe_source: homography` 면 관측 자세 = `OBSERVE_HOMOGRAPHY`, 벗어나면 `HAND_EYE` 이고 출처가 바뀌는 순간 좌표가 튈 수 있다(belt_servo 는 `position_source` 가 바뀌면 예측·필터를 리셋).
- `calib_version` = `<method> v<version> <created> sha256:<파일 sha256 앞 8자리>` (예 `hand_eye v1 2026-10-08T11:21:40 sha256:1a2b3c4d`) — 시도마다 어떤 캘리브레이션 파일이었는지 특정한다(belt_servo 틱 로그).
- `position_valid=false`: 파일 없음·camera_info 로 해상도·k 를 확인하기 전(실시간)·`moving_verified=false`(이동 중일 때)·image_size 나 k(camera_factory) 불일치·pose 를 촬영 시각 + pose_lag 에서 보간·외삽할 수 없음·광선이 평면과 거의 평행(광선과 평면 법선 사이 75° 초과, 제안값).
- 카메라를 다시 달거나 툴(TCP) 정의가 바뀌면 다시 찍는다. 그리퍼 공구 자세를 수직이 아니게 쓰려면 먼저 큰 기울기 자세로 다시 찍는다(위 합격 기준).

## 변경 이력
- 2026-10-06: 신설 (#25).
- 2026-10-06: 운용 해상도 1280×720 확정(SRD 상호확인 MC-032) — image_size 를 사진에서 읽도록 변경.
- 2026-10-06 저녁: 운용 해상도를 **1920×1080 으로 최종 결정**(10/06 측정 데이터 재사용, SRD 상호확인 #51 MC-032). `pose_frame`·`tcp_offset_mm` 추가, 기준점 규칙 명시(MC-010, #48 리뷰 ①⑥).
- 2026-10-06 밤: #48 리뷰(박병후) 반영 — 좌표 계약을 BoxTrack 과 일치(비전이 변환, 관측 박스 윗면 중심, TCP 목표는 서보, 이 파일은 초기 획득 전용). `pose_frame` → `input_pose_frame`, observe_pose 는 플랜지·H 는 접촉점으로 정규화, `tcp_offset_mm` 항상 기록, `calib_hull_px` 추가, errors_mm 에 z_range·tilt_max_deg 추가.
- 2026-10-07: #48 리뷰(김학민) 반영 — `/voss/robot/pose` 는 TCP 기준(#53 MC-010)이므로 "observe_pose 와 같은 기준" 서술을 고치고, 관측 자세 비교는 `flange_to_tcp(observe_pose)` 로 한다고 명시. 터치 툴축 경고 기준 0.5° → 2°(10/06 관측 자세가 수직에서 0.93° 기울어 정상 터치도 전부 경고되던 오경보, 접촉점 정규화로 기울기 영향은 오프셋 오차 × 각도뿐).
- 2026-10-07: `config/hand_eye.yaml`(정식 핸드아이, 이동 중 좌표) 절 신설 — T_tcp_camera, 합격 기준, box_tracker 사용 규칙(pose 보간 40 ms, 평면 높이는 belt_homography 하나, `moving_verified`). 촬영은 `/voss/robot/pose` 구독(김학민 T32 ①, 두산 직접 호출 없음). 촬영 10/08 오전.

- 2026-10-08: 핸드아이 확정(#25, 김학민 촬영·터치·이동 중 검증, 남현지 결정). `camera` 는 보드 재추정 k·d(좌표 계산용), `camera_factory` 신설(운용 중 camera_info 비교용), `touch_correction`(T16 15점 + 터치 5관측으로 위치만 보정, 광축 +9.2 mm) 신설, errors 에 터치·이동 중 검증 키. 합격 기준에 터치·이동 중(지연 보정 포함) 추가, board_spread 의 한계와 수직 공구 조건 명시. 사용 규칙: pose 는 촬영 시각 + `pose_lag_ms`(60), 마지막 pose 뒤는 80 ms 까지 앞으로 외삽(이전: 외삽 안 함) — `interface` 변경.
- 2026-10-08 오후: #90·#95 박병후 리뷰 반영 — `moving_verified=true` 면 관측 자세에서도 `HAND_EYE`(트랙 안 출처 고정, 호모그래피는 비교 로그·`observe_source: homography` 되돌림), 관측 자세 판정은 자세 전체 각, 보간 앞뒤 pose 간격 ≤ 80 ms, camera_info 확인 전 무효, `calib_version` 형식 — `interface` 변경.