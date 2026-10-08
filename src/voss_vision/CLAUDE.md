# voss_vision — 남현지 (@yujh5537, 비전 컨테이너에서 실행)
노드: box_tracker (/camera/color/image_raw → /voss/vision/box 30 Hz + /voss/vision/label_crop 선명 프레임), label_reader (크롭 → PaddleOCR → 퍼지 매칭 → /voss/vision/label, stage 1·2·3).
- 깊이 사용 금지. RGB + 핸드아이 + 박스 높이 27 mm.
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
- 아직 없음: stage 2(추종 중, 선명도 가중) — T19 2차, stage 3·`/voss/vision/read_label` — T23.
