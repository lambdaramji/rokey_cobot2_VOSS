# voss_vision — 남현지 (@yujh5537, 비전 컨테이너에서 실행)
노드: box_tracker (/camera/color/image_raw → /voss/vision/box 30 Hz + /voss/vision/label_crop 선명 프레임), label_reader (크롭 → PaddleOCR → 퍼지 매칭 → /voss/vision/label, stage 1·2·3).
- 깊이 사용 금지. RGB + 박스 높이 27 mm. 픽셀 → 베이스는 `belt_plane.py` + `config/belt_homography.yaml` (ADR-0003, 관측 자세 전용). 정식 핸드아이는 10/07.
- 추론 지연 예산: 검출 ≤ 20 ms, 루프 ≤ 100 ms. 지연 측정 로그를 남긴다.
- OCR: 분류코드(5.5 mm, 약 30 px)·동 이름(4.5 mm) 만 읽는다. 받는 사람은 무시. 편집거리 퍼지 매칭은 순수 함수로 두고 pytest.
- 녹화 영상 재생 모드(`playback:=<file>`)를 둬서 로봇 없이 개발.
- 완료 기준: 검출률 ≥ 99%, 정지 송장 50장 ≥ 95%, 추종 중 50장 ≥ 90%.
- 모델 가중치는 커밋 금지. 경로·다운로드 방법만 README.
