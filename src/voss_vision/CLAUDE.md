# voss_vision — 남현지 (@lambdaramji, 비전 컨테이너에서 실행)
노드: box_tracker (/camera/color/image_raw → /voss/vision/box 30 Hz + /voss/vision/label_crop 선명 프레임), label_reader (크롭 → PaddleOCR → 퍼지 매칭 → /voss/vision/label, stage 1·2·3).
- 깊이 사용 금지. RGB + 박스 높이 27 mm. 픽셀 → 베이스 변환은 비전 단일 책임 → `BoxTrack.position_base`(관측 박스 윗면 중심, m. TCP 목표 아님 — 서보가 계산).
- **yaw (S2-T16, TR-SERVO-04 — 제안)**: `BoxTrack.yaw_base`·`yaw_valid` = 박스 긴 변(46 mm)의 베이스 XY 각, rad, (−π/2, π/2]. seg 가 송장 minAreaRect 긴 변(`Detection.half_axis`)을 주고, box_tracker 가 중심 ± 그 벡터 두 점을 position 과 **같은 출처·같은 변환**으로 옮겨 `tracker_logic.choose_yaw`. J6 회전은 pose 에 들어 있다(시험: test_box_tracker_yaw·test_hand_eye). 실기 J6 0·15·30·45° 오차는 미측정 — 그 전에는 관측 기록용(측정 도구 `tools/calib/j6_yaw_eval.py`). BoxTrack 해시가 바뀌어 호스트·비전 컨테이너를 함께 다시 빌드한다.
- **벨트 영역 `seg.belt_roi` (S2-T16)**: 이전 열 방식(`columns`)은 벨트가 화면 세로라고 보고 초록 열 범위로 자른다. 카메라가 J6 로 돌면 벨트가 기울어 그 경계가 송장을 잘라 **놓치거나 틀린 중심·각을 냈다**(10/13 원근 합성: J6 30~75° 놓침, 박스 30°·J6 45° 에서 중심 50 px ≈ 12 mm). 기본 `hull` = 열 범위 ∪ 벨트 볼록 껍질 + 여유 — 이전 영역을 넓히기만 해서 10/06 실제 프레임 1593장에서 검출이 이전과 똑같다(1256개, 중심 차 0 px). 두 방식 모두 **영역 경계에 걸린 송장은 내지 않는다**(`border`). 되돌림: `seg.belt_roi: columns`.
  - 관측 자세 정지: `belt_plane.pixel_to_base_xy` + `config/belt_homography.yaml` (ADR-0003, `calib_hull_px` 밖은 무효).
  - **이동 중: G0 필수.** 핸드아이(`config/hand_eye.yaml` 10/08 확정, `moving_verified: true`, 수직 공구에서만 유효) + **촬영 시각 + `pose_lag_ms`(15, gateway `pose_source:=joint_states` 기준 #140 — `service` 면 60) 의 pose**(보간, 아직 없으면 80 ms 까지 앞으로 외삽) + 박스 윗면 평면 교점(`HAND_EYE`). calibration.md·ADR-0003 10/08.
  - **`pose_lag_ms` 다시 재기**: pose 소스(#118 `service`/`joint_states`)를 바꾸면 stamp 의미가 바뀌므로 `tools/calib/pose_lag_eval.py`(계산 `pose_lag.py`)로 다시 잰다. 합성 시험: 계단 pose(0.1 s)에 지연 60 ms 면 고른 lag ≈ 90 ms·이동 최대 1.7 mm, 부드러운 pose·지연 0 이면 0 ms·0.3 mm — 계단은 갱신 간격 절반쯤 지연을 더한다.
  - 카메라 USB 가 끊기면 box_tracker 는 살아 있어 sort_manager 가 모른다 → 5초 로그의 Hz 를 본다(25 Hz 밑이면 WARN).
- **하강 중 끊김**: 카메라가 공구축에서 약 8 cm 옆이라 TCP 가 박스 위로 내려가면 송장이 화면 아래 끝으로 빠지고, 가장자리에 걸린 송장은 내지 않으므로(`border_px`) 그 높이부터 BoxTrack 이 끊긴다. 10/10 g1_s1 녹화 재생(`tools/vision/box_overlay.py`, 10/11 김학민): 실제 마지막 BoxTrack 은 OK·LOST 모두 DESCEND 뒤 0.26~0.47 s, **윗면 +31~37 mm** — 핸드아이 모델(`tools/calib/descend_visibility.py`, TCP 가 박스 중심 위) 0° +37.4 와 맞는다. belt_servo 사각은 윗면 + 10 부터라 그 사이를 `lost_timeout_s` 0.5 s 안에 지나야 하는데, OK 20회의 사각 진입 때 관측 나이는 0.40~0.48 s(여유 0.02~0.10 s), 기울인 박스 3회는 0.56~0.59 s 로 LOST(measurements-1010 의도 시험). 틱의 `visible` 은 마지막 메시지를 lost_timeout 까지 유지하므로 실제 관측 시각으로 쓰지 않는다. 대응(사각 높이·lost 판정)은 servo(박병후) 판단.
- 추론 지연 예산: 검출 ≤ 20 ms, 루프 ≤ 100 ms. 지연 측정 로그를 남긴다.
- OCR: 분류코드(5.5 mm, 약 30 px)·동 이름(4.5 mm) 만 읽는다. 받는 사람은 무시. 편집거리 퍼지 매칭은 순수 함수로 두고 pytest.
- 녹화 영상 재생 모드(`playback:=<file>`)를 둬서 로봇 없이 개발. 기본은 녹화 시각을 그대로 낸다(분석용). 재생으로 sort_manager·belt_servo 를 돌릴 때는 `playback_restamp:=true`(첫 메시지를 지금에 맞추고 영상·pose 를 같이 옮김, `tracker_logic.PlaybackClock`) — 녹화 시각이면 sort_manager 가 "관측 시작 전 촬영"으로 버린다(10/11 voss_dry_run).
- 완료 기준: 검출률 ≥ 99%, 정지 송장 50장 ≥ 95%, 추종 중 50장 ≥ 90%.
- 모델 가중치는 커밋 금지. 경로·다운로드 방법만 README.

## label_reader (T19 #28 — 1차 G0 경로 stage 1, 2차 stage 2)
- stage 1(입구 관측): LabelCrop → `find_label_in_crop`(크롭 중심 송장) → `crop_upright` → PaddleOCR(`ocr_engine.read_label`, 글자가 없으면 180° 돌려 한 번 더) → `match_label` → 트랙별 다수결(`label_vote`, NONE 은 분모 제외) → `/voss/vision/label`.
- 후보는 `/voss/sort/zone_map` 에서만. 발행자는 엔진 예열 + zone_map 수신 뒤에 만든다(sort_manager 의 OCR 준비 = 발행자 존재).
- OCR 은 작업 스레드 하나, 트랙마다 최신 크롭 1장만 대기, 같은 동 2장 + confidence_min 이상이면 그 트랙은 더 안 읽는다.
- 호스트 G0 는 PaddleOCR venv(`--system-site-packages`)로: `ros2 launch voss_vision label_reader.launch.py python:=<venv>/bin/python`. 컨테이너(T22 #31)는 `docker/vision/` — 같은 venv 방식(`/opt/voss_ocr`, `VOSS_OCR_PYTHON`), config 는 `VOSS_CONFIG_DIR=/opt/voss/config` 읽기 전용, GPU 는 `compose.gpu.yml`(`ocr_device:=gpu:0`).
- **stage 2(추종 중, T19 2차 #28, BRD TR-OCR-02) — `stage2.enable`(기본 off, launch `stage2:=true`).** box_tracker 가 PICKING 동안 보내는 sort_manager 트랙의 크롭(5 Hz) 중, 작업 스레드가 비면 그사이 온 **가장 선명한 한 장**을 읽는다(`label_stage2.Stage2Picker`). 트랙당 `stage2.max_ocr`(3) 장, 같은 동 `stage2.min_agree`(2) 장 + confidence_min 이면 그만 — **2단계 발행도 그때만**(`label_stage2.publishable`, #171 리뷰: sort_manager 는 확실한 2단계 한 번에 구역을 바꾸므로 1장 오판이 틀린 구역이 되지 않게. 모이기 전에 goal 이 끝나면 재확인으로, sort_manager 로그 "추종 중 판독 늦게 도착"). 다수결은 선명도 가중(`label_vote.vote(weighted=True)`, MC-007). 순서: 재판독 → 2단계 → 1단계.
  - sort_manager 는 2단계를 **재확인 구역으로 가려던 박스**에만 쓴다(`sort_fsm._on_label_tracking` — 확실해지면 목적 구역으로 바꿈) → `stage2.skip_confident_stage1`(기본 true): 1단계 발행이 **모두** 확실했던 트랙은 읽지 않는다. 대부분 박스는 추종 중 OCR 부하가 0 이다.
  - 실기 확인 전(켜기 전에): belt_servo 틱 주기(33.3 ms, 최대 ≤ 40)가 2단계 OCR 중에도 유지되는지, 2단계 결과가 goal 결과보다 먼저 오는지(sort_manager 로그 "추종 중 판독 확정"), 추종 중 판독률(완료 기준 "추종 중 50장 ≥ 90%").

## label_reader 재판독 (stage 3, T23 #32)
- `/voss/vision/read_label`: 요청 동안만 `/camera/color/image_raw` 구독 → max_frames 장(기본 5)을 timeout_s(기본 2 s) 안에 모음 → 해제. 재확인 트레이는 초록 벨트가 아니라 box_tracker 크롭이 없다 → `label_view.find_labels_in_view`(전체 화면 흰 송장, `view.roi` 중심에 가까운 순) → 선명도 순으로 최대 `view.max_ocr` 장 OCR, 같은 동 `view.min_agree` 장 + confidence_min 이면 조기 종료.
- 작업 스레드는 재판독을 크롭보다 먼저 처리. 서비스 콜백은 결과를 기다리므로 MultiThreadedExecutor(4) + 서비스·카메라 콜백 그룹 분리.
- 실패 사유: timeout(프레임 0장·OCR 대기 초과) / no_box / no_text. 낮은 신뢰도는 ok=true 로 돌려주고 질문 여부는 sort_manager 가 정한다.
- `view.area_*`·`aspect_tol`·`roi` 는 10/08 VIEW 자세(view_pose #116) 사진 11장으로 정한 값(송장 174~177 px, 칸 0 y ≈ 420·칸 1 ≈ 690). view_pose 를 바꾸면 다시 잰다. 사진 판독(프레임 1장씩, 개인 PC CPU): 칸 0·1 단독 6장·BOTH 칸별·R180·TILT 20° 모두 1.00, 흐린 송장은 코드만 0.63, EMPTY no_box. `debug_save_dir` 를 주면 요청마다 첫 프레임을 `view_s3_<stamp>.png` 로 남긴다(튜닝용, 커밋 금지).
- **칸 지정**(10/08 결정): `ReadLabel.slot`(기본 -1) — sort_manager 가 그 박스의 재확인 칸을 보내면 `view.slot_rois` 의 그 칸 영역만 본다(칸 0 = 화면 위, 1 = 아래). -1 은 `view.roi` 중심(박스 1개일 때만 안전 — BOTH 에서는 중심이 두 칸 가운데). 없는 칸 번호는 `bad_slot`.
