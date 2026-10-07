# tools/
- `make_labels.py` — 40×25 mm 송장 PDF 생성. 분류코드 5.5 mm 굵은 고정폭, 동 이름 4.5 mm, 받는 사람 2.8 mm, 여백 3 mm. 흐린 송장 1장 옵션 (김학민, 10/11~13)
- `arduino/conveyor_test/conveyor_test.ino` — 벨트 컨베이어 아두이노 스케치. 개발 설정 4.89 cm/s, 시리얼 9600 `s`/`r`. Arduino IDE 2 에서 보드 `Arduino UNO`, 포트 `/dev/ttyACM0` 로 업로드 (`dialout` 그룹 필요). 업로드 전에 12 V 모터 전원을 끄고 벨트 위를 비운다 (김학민)
  - ⚠ 시리얼 포트를 열거나 RESET 하면 보드가 재시작해 **벨트가 바로 돈다** (`isRunning = true` 로 시작). PC 에서 포트를 여는 스크립트·노드를 쓰기 전에 벨트 위를 비운다.
- `ocr/eval_static.py` — T18 정지 송장 OCR 평가(ADR-0007). 파일명이 정답(`S0701_03.png`, `BLUR_S0701_02.png`). 라벨 크롭 → PaddleOCR → `voss_vision.label_match` → 정확도·저신뢰 목록·CSV. PaddleOCR 는 워크스페이스 밖 venv 에 둔다(colcon 이 venv 를 패키지로 잡지 않게):
  ```bash
  python3 -m venv --system-site-packages ~/.venvs/voss_ocr
  ~/.venvs/voss_ocr/bin/pip install paddlepaddle paddleocr      # CPU. 공용 PC 는 비전 컨테이너(GPU)
  ~/.venvs/voss_ocr/bin/python tools/ocr/eval_static.py --dir <ocr_static> --out <결과.csv> [--save-crops <폴더>]
  ```
  paddle 3.3 CPU 는 oneDNN 오류가 있어 도구가 `enable_mkldnn=False` 로 띄운다 (남현지)
