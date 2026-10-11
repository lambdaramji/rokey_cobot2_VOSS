# tools/
- `make_labels.py` — 40×25 mm 송장 PDF 생성. 분류코드 5.5 mm 굵은 고정폭, 동 이름 4.5 mm, 받는 사람 2.8 mm, 여백 3 mm. 흐린 송장 1장 옵션 (김학민, 10/11~13)
- `arduino/conveyor_test/conveyor_test.ino` — 벨트 컨베이어 아두이노 스케치. 개발 설정 4.89 cm/s, 시리얼 9600 `s`/`r`. Arduino IDE 2 에서 보드 `Arduino UNO`, 포트 `/dev/ttyACM0` 로 업로드 (`dialout` 그룹 필요). 업로드 전에 12 V 모터 전원을 끄고 벨트 위를 비운다 (김학민)
  - ⚠ 시리얼 포트를 열거나 RESET 하면 보드가 재시작해 **벨트가 바로 돈다** (`isRunning = true` 로 시작). PC 에서 포트를 여는 스크립트·노드를 쓰기 전에 벨트 위를 비운다.
- `ocr/eval_static.py` — T18 정지 송장 OCR 평가(ADR-0008). 파일명이 정답(`S0701_03.png`, `BLUR_S0701_02.png`). 라벨 크롭 → PaddleOCR → `voss_vision.label_match` → 정확도·저신뢰 목록·CSV. PaddleOCR 는 워크스페이스 밖 venv 에 둔다(colcon 이 venv 를 패키지로 잡지 않게):
  ```bash
  python3 -m venv --system-site-packages ~/.venvs/voss_ocr
  ~/.venvs/voss_ocr/bin/pip install paddlepaddle paddleocr      # CPU. 공용 PC 는 비전 컨테이너(GPU)
  ~/.venvs/voss_ocr/bin/python tools/ocr/eval_static.py --dir <ocr_static> --out <결과.csv> [--save-crops <폴더>]
  ```
  paddle 3.3 CPU 는 oneDNN 오류가 있어 도구가 `enable_mkldnn=False` 로 띄운다 (남현지)
- `vision/eval_bag.py` — T17 녹화 bag 평가(ADR-0004): 분할 검출(`voss_vision.box_detect`) + 트래커 → 오검출·트랙·구간 검출률·지연(CPU 참고), 확인 시트, YOLO 자동 라벨 내보내기(`--export-yolo`, 음성은 앞뒤 2 s 안에 검출이 없는 프레임만). ROS Jazzy 환경에서 실행 (남현지)
- `vision/box_overlay.py` — box_tracker 시각화(T21 #30, 하강 LOST 원인 찾기). 카메라 화면에 송장 후보·**버린 이유**(면적·가장자리·비율·채움, `box_detect.detect_candidates` = box_tracker 와 같은 판정)·발행된 BoxTrack·OCR 결과·단계·TCP 높이(윗면 기준)를 덧그린다. 구독·읽기만 한다(장비 무관):
  ```bash
  source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash   # voss_msgs 필요
  python3 tools/vision/box_overlay.py <G1 bag> [--start 12 --end 30] [--out a.mp4] [--csv a.csv] [--show]   # 끝에 "발행 끊김" 목록
  python3 tools/vision/box_overlay.py --live [--candidates] [--hz 10] [--out live.mp4] [--no-window]          # 공용 PC, 게이트 측정 중에는 띄우지 않는다
  ```
  녹화는 g0-runbook 3절 토픽(`image_raw/compressed`·`/voss/vision/box`·`/voss/robot/pose`·액션 feedback)을 쓴다. 한글은 Nanum 폰트가 있으면 PIL 로, 없으면 영문 (남현지)
- `calib/descend_visibility.py` — 하강 중 송장이 화면 아래 끝에 걸려 BoxTrack 이 끊기기 시작하는 TCP 높이(박스 회전각·정렬 오차·TCP 가 박스보다 하류로 앞선 거리 `--tcp-ahead` 별)와 그 사이 LOST 여부 → belt_servo `vision_cutoff_above_top_mm` 근거. 핸드아이 모델 값이고 `--tcp-ahead` 에 민감하다(10/10 g1_s1 재생의 실제 끊김 윗면 +31~37 mm 는 0 과 맞음) — 새 조건은 `box_overlay.py` 로 녹화를 확인한다 (남현지)
- `calib/pose_lag_eval.py` — 영상-pose 지연(box_tracker `pose_lag_ms`)과 이동 중 좌표 오차를 녹화 하나로 잰다(T21 #30, calibration.md 이동 중 검증). 박스를 세워 두고 로봇만 움직인 녹화(이동 전후 3 s 정지, +x 한 방향·두 속도면 충분)에서 box_tracker 와 같은 계산으로 lag 를 훑어 이동 프레임 RMS 가 가장 작은 값을 고르고, 진행 방향 오차의 기울기로 한 번 더 확인한다. pose 값 갱신 간격(service 0.1 s 계단, #118)도 알려 준다. 계산은 `voss_vision/pose_lag.py`(pytest). `python3 tools/calib/pose_lag_eval.py <bag> --hand-eye config/hand_eye.yaml --homography config/belt_homography.yaml [--lags=-20:150:5] [--csv out.csv]` (남현지)
- `colab/t17_yolo_train.ipynb` — 자동 라벨로 YOLO nano 학습·이어 학습·holdout 평가·ONNX 내보내기. 입력·체크포인트·출력 경로는 팀 Drive 구조(`docs/setup/drive.md`)를 따른다 (남현지)
- `mock/g0_mock.py` — G0 모의 상대: belt_servo 액션(`--servo`)·robot_gateway MoveToZone·stop·pose(`--robot`)·sort_logger 상태(`--log`)·박스 1개 BoxTrack·LabelRead(`--vision`). 진짜 서버·발행자가 이미 있으면 그 부분은 띄우지 않는다. 장비를 움직이지 않는다 — sort_manager 를 로봇 없이 끝까지 돌려 보는 용도 (남현지)
