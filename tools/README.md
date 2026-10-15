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
- `vision/box_overlay.py` — box_tracker 시각화(T21 #30, 하강 LOST 원인 찾기). 카메라 화면에 송장 후보·**버린 이유**(면적·가장자리·비율·채움, `box_detect.detect_candidates` = box_tracker 와 같은 판정)·발행된 BoxTrack·OCR 결과·단계·TCP 높이(윗면 기준)를 덧그린다. 발행된 bbox 는 초록, 위 가운데에 `BOX<번호> <채움 %>` — 번호는 sort_manager box_id 끝 순번(`/voss/sort/state`·`/voss/sort/result` 로 track_id 와 짝지음, 발급 전에는 번호 없이 `BOX`, 세션이 바뀌거나 트랙이 새로 나타나면 — box_tracker 재시작으로 track_id 가 다시 쓰여도 — 앞 번호를 버림. 시험 `python3 -m pytest tools/vision`), 채움 % 는 짝지은 송장 후보의 윤곽 면적 / 회전 사각형(fill_min 80 % 이상만 통과 — 학습 신뢰도 아님), 각도는 노랑 `yaw +45°`(yaw 필드가 있는 v15 빌드면 숫자, 송장 긴 축 선은 항상). 짝지은 후보가 없으면 `-%`. 실시간에서 % 가 필요 없으면 `--no-score`(% 를 아예 안 씀). 구독·읽기만 한다(장비 무관):
  ```bash
  source /opt/ros/jazzy/setup.bash && source ~/voss_ws/install/setup.bash   # voss_msgs 필요
  python3 tools/vision/box_overlay.py <G1 bag> [--start 12 --end 30] [--out a.mp4] [--csv a.csv] [--show]   # 끝에 "발행 끊김" 목록
  python3 tools/vision/box_overlay.py --live [--candidates] [--hz 10] [--out live.mp4] [--no-window]          # 공용 PC, 게이트 측정 중에는 띄우지 않는다
  ```
  녹화는 g0-runbook 3절 토픽(`image_raw/compressed`·`/voss/vision/box`·`/voss/robot/pose`·액션 feedback)을 쓴다. 한글은 Nanum 폰트가 있으면 PIL 로, 없으면 영문 (남현지)
- `calib/descend_visibility.py` — 하강 중 송장이 화면 아래 끝에 걸려 BoxTrack 이 끊기기 시작하는 TCP 높이(박스 회전각·정렬 오차·TCP 가 박스보다 하류로 앞선 거리 `--tcp-ahead` 별)와 그 사이 LOST 여부 → belt_servo `vision_cutoff_above_top_mm` 근거. 핸드아이 모델 값이고 `--tcp-ahead` 에 민감하다(10/10 g1_s1 재생의 실제 끊김 윗면 +31~37 mm 는 0 과 맞음) — 새 조건은 `box_overlay.py` 로 녹화를 확인한다 (남현지)
- `calib/pose_lag_eval.py` — 영상-pose 지연(box_tracker `pose_lag_ms`)과 이동 중 좌표 오차를 녹화 하나로 잰다(T21 #30, calibration.md 이동 중 검증). 박스를 세워 두고 로봇만 움직인 녹화(이동 전후 3 s 정지, +x 한 방향·두 속도면 충분)에서 box_tracker 와 같은 계산으로 lag 를 훑어 이동 프레임 RMS 가 가장 작은 값을 고르고, 진행 방향 오차의 기울기로 한 번 더 확인한다. pose 값 갱신 간격(service 0.1 s 계단, #118)도 알려 준다. 계산은 `voss_vision/pose_lag.py`(pytest). `python3 tools/calib/pose_lag_eval.py <bag> --hand-eye config/hand_eye.yaml --homography config/belt_homography.yaml [--lags=-20:150:5] [--csv out.csv]` (남현지)
- `calib/j6_yaw_eval.py` — **J6 회전 시 핸드아이 오차·박스 yaw**(S2-T16, R-28·TR-SERVO-06 실기 측정). 박스를 세워 두고(벨트 정지) 관측 자세에서 J6 만 0 → 15 → 30 → 45°(되면 −쪽도) 돌리며 각마다 약 3 s 멈춘 녹화 — 박스가 그대로라 J6 각마다 좌표·yaw 가 같아야 하고, 관측 자세 구간 대비 차가 J6 회전 때 오차다(관측 자세 구간은 호모그래피와도 비교). 정지는 병진·회전 둘 다 본다(J6 만 돌리면 TCP 점은 그대로). 계산은 `voss_vision/j6_eval.py`(pytest, box_tracker 와 같은 검출·변환). 판정(제안값) Δ위치 ≤ 5 mm, |Δyaw| ≤ 2°. 녹화 하나 = 박스 한 번 놓기(대략 0·15·30·45°마다 새 녹화)
  - **박스는 TCP 바로 아래(공구축이 벨트 평면과 만나는 점)에 둔다** — 공구축 위 점은 J6 를 돌려도 화면 같은 자리에 있어 0~90° 내내 보인다. 화면 가운데에 두면 J6 를 돌릴 때 시야 밖으로 나간다(10/13 합성 녹화).
  - 로봇 자세 이동은 김학민이 티치펜던트·저속, 비상정지 대기자 옆. 토픽: `/camera/color/image_raw/compressed`·`/camera/color/camera_info`·`/voss/robot/pose`
  ```bash
  python3 tools/calib/j6_yaw_eval.py <녹화> [<녹화> …] --hand-eye config/hand_eye.yaml --homography config/belt_homography.yaml [--lag-ms 60] [--csv j6.csv]
  ```
  핸드아이가 맞는 합성 녹화(10/13)에서 J6 0~90° 남는 값 ≤ 1.2 mm·1.3°(원근으로 사다리꼴인 송장에 회전 사각형을 맞추는 검출 바닥값) — yaw 기준 2° 와 여유가 크지 않다 (남현지)
- `colab/t17_yolo_train.ipynb` — 자동 라벨로 YOLO nano 학습·이어 학습·holdout 평가·ONNX 내보내기. 입력·체크포인트·출력 경로는 팀 Drive 구조(`docs/setup/drive.md`)를 따른다 (남현지)
- `mock/g0_mock.py` — G0 모의 상대: belt_servo 액션(`--servo`)·robot_gateway MoveToZone·stop·pose(`--robot`)·sort_logger 상태(`--log`)·박스 1개 BoxTrack·LabelRead(`--vision`). 진짜 서버·발행자가 이미 있으면 그 부분은 띄우지 않는다. 장비를 움직이지 않는다 — sort_manager 를 로봇 없이 끝까지 돌려 보는 용도 (남현지)
