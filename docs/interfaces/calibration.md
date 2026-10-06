# 카메라 캘리브레이션 결과 파일 (ADR-0003)

`config/belt_homography.yaml` — 관측 자세에서 **픽셀 → 로봇 베이스 (x, y) mm** 변환. `tools/calib/fit_belt_homography.py` 가 만든다(사람이 실행, 노드는 쓰지 않음). 비전 컨테이너에는 `config/` 와 함께 읽기 전용 마운트.

| 키 | 형식 | 뜻 |
|---|---|---|
| version | int | 1 |
| method | str | `belt_plane_homography` (정식 핸드아이로 바뀌면 `hand_eye`) |
| created | str | 계산 시각 |
| image_size | [w, h] | 1920, 1080. 카메라 해상도가 다르면 무효 |
| observe_pose | [x, y, z, rx, ry, rz] | 사진을 찍은 관측 자세 posx. **이 자세에서만 유효** — voss_config `observe_pose` 와 같아야 한다 |
| plane_z_mm | float | 박스 윗면(벨트 + 27 mm) 높이, 터치 z 평균 |
| undistort | {k[9], d[]} 또는 null | 왜곡 보정 파라미터. 픽셀을 먼저 이걸로 보정한 뒤 H 적용 |
| H_px_to_base_xy | 3×3 | 동차좌표 [u, v, 1] → [x, y, w], (x/w, y/w) mm |
| tcp_pixel_at_observe | [u, v] | 관측 자세에서 TCP 바로 아래에 해당하는 픽셀 (서보 목표점 참고값) |
| errors_mm | {calib_rms, val_max, val{}} | 계산점 잔차, 검증점 오차 (SR-FN-02, ≤ 5 mm 제안값) |

## 쓰는 곳
- box_tracker: BoxTrack 는 픽셀 그대로 발행(변경 없음). 변환은 소비자가 한다.
- belt_servo(박병후): B안 개루프·A안 첫 접근 때 박스 중심 픽셀 → (x, y). 계산은 `voss_vision.belt_plane.apply_homography` 와 같은 식을 쓴다.
- 관측 자세가 바뀌면 다시 찍어야 한다. 추종 중(카메라가 움직일 때) 좌표가 필요해지면 정식 핸드아이(10/07)로 대체.

## 변경 이력
- 2026-10-06: 신설 (#25).
