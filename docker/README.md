# 컨테이너

| 폴더 | 내용 | 담당 |
|---|---|---|
| vision/ | ros:jazzy + CUDA + YOLO + PaddleOCR. box_tracker, label_reader 실행 | 남현지 |
| db/ | 작업 로그 DB (종류 미정) | 정의석 |
| web/ | 웹 HMI (스택 미정, 호스트 실행이면 삭제) | 정의석 |

공통: `--network host`, `ROS_DOMAIN_ID` 와 `RMW_IMPLEMENTATION` 을 호스트와 동일하게, `config/` 는 `:ro` 마운트.
`docker compose up` 은 사람이 실행한다 (Claude settings 에서 deny).
