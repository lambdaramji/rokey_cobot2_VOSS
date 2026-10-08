# voss_vision — 남현지 (@yujh5537, 비전 컨테이너에서 실행)
노드: box_tracker (/camera/color/image_raw → /voss/vision/box 30 Hz + /voss/vision/label_crop 선명 프레임), label_reader (크롭 → PaddleOCR → 퍼지 매칭 → /voss/vision/label, stage 1·2·3).
- 깊이 사용 금지. RGB + 박스 높이 27 mm. 픽셀 → 베이스 변환은 비전 단일 책임 → `BoxTrack.position_base`(관측 박스 윗면 중심, m. TCP 목표 아님 — 서보가 계산).
  - 관측 자세 정지: `belt_plane.pixel_to_base_xy` + `config/belt_homography.yaml` (ADR-0003, `calib_hull_px` 밖은 무효).
  - **이동 중: G0 필수.** 핸드아이(`config/hand_eye.yaml` 10/08 확정, `moving_verified: true`, 수직 공구에서만 유효) + **촬영 시각 + `pose_lag_ms`(60) 의 pose**(보간, 아직 없으면 80 ms 까지 앞으로 외삽) + 박스 윗면 평면 교점(`HAND_EYE`). calibration.md·ADR-0003 10/08.
  - 카메라 USB 가 끊기면 box_tracker 는 살아 있어 sort_manager 가 모른다 → 5초 로그의 Hz 를 본다(25 Hz 밑이면 WARN).
- 추론 지연 예산: 검출 ≤ 20 ms, 루프 ≤ 100 ms. 지연 측정 로그를 남긴다.
- OCR: 분류코드(5.5 mm, 약 30 px)·동 이름(4.5 mm) 만 읽는다. 받는 사람은 무시. 편집거리 퍼지 매칭은 순수 함수로 두고 pytest.
- 녹화 영상 재생 모드(`playback:=<file>`)를 둬서 로봇 없이 개발.
- 완료 기준: 검출률 ≥ 99%, 정지 송장 50장 ≥ 95%, 추종 중 50장 ≥ 90%.
- 모델 가중치는 커밋 금지. 경로·다운로드 방법만 README.
