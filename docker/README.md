# 컨테이너

| 폴더 | 내용 | 담당 |
|---|---|---|
| vision/ | ros:jazzy + PaddleOCR(CPU/GPU — `compose.gpu.yml`). box_tracker(OpenCV 분할, ADR-0011 — YOLO 안 씀)·label_reader 를 서비스 하나씩. 실행·시험은 `vision/README.md` | 남현지 |
| db/ | PostgreSQL 16 + 호스트 볼륨 (`sort_log`, `session_plan`). 실행·G0 조회·시험은 `db/README.md` | 정의석 |
| web/ | Spring Boot(Java 21) + React·Vite 빌드 + Nginx | 정의석 |
| ai/ | FastAPI + Whisper + OpenAI API (GPU). 음성 ROS 노드가 `127.0.0.1:8000` 으로 호출. 실행·시험은 `ai/README.md` | 정의석 |

웹·AI·DB 스택 근거: docs/adr/0006-web-ai-db-stack.md. 비밀값은 `.env`(gitignore) 로만.

공통: `--network host`, `ROS_DOMAIN_ID` 와 `RMW_IMPLEMENTATION` 을 호스트와 동일하게, `config/` 는 `:ro` 마운트.
`docker compose up` 은 사람이 실행한다 (Claude settings 에서 deny).
