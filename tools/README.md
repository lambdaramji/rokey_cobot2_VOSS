# tools/
- `make_labels.py` — 40×25 mm 송장 PDF 생성. 분류코드 5.5 mm 굵은 고정폭, 동 이름 4.5 mm, 받는 사람 2.8 mm, 여백 3 mm. 흐린 송장 1장 옵션 (김학민, 10/11~13)
- `arduino/conveyor_test/conveyor_test.ino` — 벨트 컨베이어 아두이노 스케치. 개발 설정 4.89 cm/s, 시리얼 9600 `s`/`r`. Arduino IDE 2 에서 보드 `Arduino UNO`, 포트 `/dev/ttyACM0` 로 업로드 (`dialout` 그룹 필요). 업로드 전에 12 V 모터 전원을 끄고 벨트 위를 비운다 (김학민)
