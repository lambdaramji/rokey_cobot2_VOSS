# voss_vision — 남현지 (@lambdaramji, 비전 컨테이너에서 실행)
노드: box_tracker (/camera/color/image_raw → /voss/vision/box 30 Hz + /voss/vision/label_crop 선명 프레임), label_reader (크롭 → PaddleOCR → 퍼지 매칭 → /voss/vision/label, stage 1·2·3).
- 깊이 사용 금지. RGB + 박스 높이 27 mm. 픽셀 → 베이스 변환은 비전 단일 책임 → `BoxTrack.position_base`(관측 박스 윗면 중심, m. TCP 목표 아님 — 서보가 계산).
  - 관측 자세 정지: `belt_plane.pixel_to_base_xy` + `config/belt_homography.yaml` (ADR-0003, `calib_hull_px` 밖은 무효).
  - **이동 중: G0 필수.** 핸드아이(`config/hand_eye.yaml` 10/08 확정, `moving_verified: true`, 수직 공구에서만 유효) + **촬영 시각 + `pose_lag_ms`(60) 의 pose**(보간, 아직 없으면 80 ms 까지 앞으로 외삽) + 박스 윗면 평면 교점(`HAND_EYE`). calibration.md·ADR-0003 10/08.
  - **`pose_lag_ms` 다시 재기**: pose 소스(#118 `service`/`joint_states`)를 바꾸면 stamp 의미가 바뀌므로 `tools/calib/pose_lag_eval.py`(계산 `pose_lag.py`)로 다시 잰다. 합성 시험: 계단 pose(0.1 s)에 지연 60 ms 면 고른 lag ≈ 90 ms·이동 최대 1.7 mm, 부드러운 pose·지연 0 이면 0 ms·0.3 mm — 계단은 갱신 간격 절반쯤 지연을 더한다.
  - 카메라 USB 가 끊기면 box_tracker 는 살아 있어 sort_manager 가 모른다 → 5초 로그의 Hz 를 본다(25 Hz 밑이면 WARN).
- 추론 지연 예산: 검출 ≤ 20 ms, 루프 ≤ 100 ms. 지연 측정 로그를 남긴다.
- OCR: 분류코드(5.5 mm, 약 30 px)·동 이름(4.5 mm) 만 읽는다. 받는 사람은 무시. 편집거리 퍼지 매칭은 순수 함수로 두고 pytest.
- 녹화 영상 재생 모드(`playback:=<file>`)를 둬서 로봇 없이 개발.
- 완료 기준: 검출률 ≥ 99%, 정지 송장 50장 ≥ 95%, 추종 중 50장 ≥ 90%.
- 모델 가중치는 커밋 금지. 경로·다운로드 방법만 README.

## label_reader (T19 1차, #28 — G0 경로)
- stage 1(입구 관측)만 읽는다: LabelCrop → `find_label_in_crop`(크롭 중심 송장) → `crop_upright` → PaddleOCR(`ocr_engine.read_label`, 글자가 없으면 180° 돌려 한 번 더) → `match_label` → 트랙별 다수결(`label_vote`, NONE 은 분모 제외) → `/voss/vision/label`.
- 후보는 `/voss/sort/zone_map` 에서만. 발행자는 엔진 예열 + zone_map 수신 뒤에 만든다(sort_manager 의 OCR 준비 = 발행자 존재).
- OCR 은 작업 스레드 하나, 트랙마다 최신 크롭 1장만 대기, 같은 동 2장 + confidence_min 이상이면 그 트랙은 더 안 읽는다.
- 호스트 G0 는 PaddleOCR venv(`--system-site-packages`)로: `ros2 launch voss_vision label_reader.launch.py python:=<venv>/bin/python`. GPU·컨테이너는 T22.
- 아직 없음: stage 2(추종 중, 선명도 가중) — T19 2차.

## label_reader 재판독 (stage 3, T23 #32)
- `/voss/vision/read_label`: 요청 동안만 `/camera/color/image_raw` 구독 → max_frames 장(기본 5)을 timeout_s(기본 2 s) 안에 모음 → 해제. 재확인 트레이는 초록 벨트가 아니라 box_tracker 크롭이 없다 → `label_view.find_labels_in_view`(전체 화면 흰 송장, `view.roi` 중심에 가까운 순) → 선명도 순으로 최대 `view.max_ocr` 장 OCR, 같은 동 `view.min_agree` 장 + confidence_min 이면 조기 종료.
- 작업 스레드는 재판독을 크롭보다 먼저 처리. 서비스 콜백은 결과를 기다리므로 MultiThreadedExecutor(4) + 서비스·카메라 콜백 그룹 분리.
- 실패 사유: timeout(프레임 0장·OCR 대기 초과) / no_box / no_text. 낮은 신뢰도는 ok=true 로 돌려주고 질문 여부는 sort_manager 가 정한다.
- `view.area_*`·`aspect_tol`·`roi` 는 10/08 VIEW 자세(view_pose #116) 사진 11장으로 정한 값(송장 174~177 px, 칸 0 y ≈ 420·칸 1 ≈ 690). view_pose 를 바꾸면 다시 잰다. 사진 판독(프레임 1장씩, 개인 PC CPU): 칸 0·1 단독 6장·BOTH 칸별·R180·TILT 20° 모두 1.00, 흐린 송장은 코드만 0.63, EMPTY no_box. `debug_save_dir` 를 주면 요청마다 첫 프레임을 `view_s3_<stamp>.png` 로 남긴다(튜닝용, 커밋 금지).
- **칸 지정**(10/08 결정): `ReadLabel.slot`(기본 -1) — sort_manager 가 그 박스의 재확인 칸을 보내면 `view.slot_rois` 의 그 칸 영역만 본다(칸 0 = 화면 위, 1 = 아래). -1 은 `view.roi` 중심(박스 1개일 때만 안전 — BOTH 에서는 중심이 두 칸 가운데). 없는 칸 번호는 `bad_slot`.
