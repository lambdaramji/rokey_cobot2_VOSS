# tools/
- `make_labels.py` — 40×25 mm 송장 PDF 생성. 분류코드 5.5 mm 굵은 고정폭, 동 이름 4.5 mm, 받는 사람 2.8 mm, 여백 3 mm. 흐린 송장 1장 옵션 (김학민, 10/11~13)
- `arduino/conveyor_test/conveyor_test.ino` — 벨트 컨베이어 아두이노 스케치. 개발 설정 4.89 cm/s, 시리얼 9600 `s`/`r`. Arduino IDE 2 에서 보드 `Arduino UNO`, 포트 `/dev/ttyACM0` 로 업로드 (`dialout` 그룹 필요). 업로드 전에 12 V 모터 전원을 끄고 벨트 위를 비운다 (김학민)
  - ⚠ 시리얼 포트를 열거나 RESET 하면 보드가 재시작해 **벨트가 바로 돈다** (`isRunning = true` 로 시작). PC 에서 포트를 여는 스크립트·노드를 쓰기 전에 벨트 위를 비운다.
- `vision/eval_bag.py` — T17 녹화 bag 평가(ADR-0004): 분할 검출(`voss_vision.box_detect`) + 트래커 → 오검출·트랙·구간 검출률·지연(CPU 참고), 확인 시트, YOLO 자동 라벨 내보내기(`--export-yolo`, 음성은 앞뒤 2 s 안에 검출이 없는 프레임만). ROS Jazzy 환경에서 실행 (남현지)
- `colab/t17_yolo_train.ipynb` — 자동 라벨로 YOLO nano 학습·이어 학습·holdout 평가·ONNX 내보내기. 입력·체크포인트·출력 경로는 팀 Drive 구조(`docs/setup/drive.md`)를 따른다 (남현지)
