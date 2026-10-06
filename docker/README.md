# 컨테이너

| 폴더 | 내용 | 담당 |
|---|---|---|
| vision/ | ros:jazzy + CUDA + YOLO + PaddleOCR. box_tracker, label_reader 실행 | 남현지 |
| db/ | PostgreSQL + 호스트 볼륨 (`sort_log`) | 정의석 |
| web/ | Spring Boot(Java 21) + React·Vite 빌드 + Nginx | 정의석 |
| ai/ | FastAPI + Whisper + OpenAI API (GPU). 음성 ROS 노드가 HTTP 로 호출 | 정의석 |

웹·AI·DB 스택 근거: docs/adr/0005-web-ai-db-stack.md. 비밀값은 `.env`(gitignore) 로만.

공통: `--network host`, `ROS_DOMAIN_ID` 와 `RMW_IMPLEMENTATION` 을 호스트와 동일하게, `config/` 는 `:ro` 마운트.
`docker compose up` 은 사람이 실행한다 (Claude settings 에서 deny).
