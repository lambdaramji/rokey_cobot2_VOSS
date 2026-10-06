# ADR-0005: 웹·AI·DB 스택 — React + Spring Boot + FastAPI + PostgreSQL

- 날짜: 2026-10-06
- 상태: 제안됨 (정의석 제안. PL·관련 담당 승인 전. 승인 후 "승인됨"으로 바꾸고 pending #13·#14 갱신)
- 결정자: 정의석 (음성·웹·HMI), 승인 남현지 (PL)
- 관련: pending-decisions #13 (웹 스택·실행 위치) · #14 (DB 종류), SRD v0.2 TBD-011·012·026, 상호확인 MC-022·026·028·029 (#52·#55), 이슈 #20·#21·#22

## 배경
SRD v0.2 회신과 상호확인(#52·#55)에서 웹 스택·DB·Mosquitto 위치가 "제안, 미확정"으로 남아 MC-022(Stats 제공자)·MC-026(MQTT)·MC-029(배포)의 답을 정할 수 없다.
정의석 파트(음성·웹·HMI)의 구현 기준은 `정의석_기술스택_및_아키텍처.md`(이하 "스택 문서", `docs/requirements/정의석_기술스택_및_아키텍처.md`)이며, 이 ADR은 그 기준을 VOSS 계약(docs/interfaces, 절대 규칙)과 충돌 없이 옮긴 것이다.

## 결정
| 영역 | 기술 | 역할 |
|---|---|---|
| Frontend | React + TypeScript + Vite | Web HMI: 운전 버튼·투입 수량·상태·OCR 결과·구역 집계·보류 목록·이력 |
| Backend | Java 21 + Spring Boot | 메인 웹 백엔드. REST API, 비즈니스 로직, 이력·통계 조회, SSE 로 React 실시간 갱신, MQTT 구독·발행 |
| AI / Voice | Python 3.12 + FastAPI + Whisper + OpenAI API | STT·LLM intent 추출 전용 서비스. 일반 CRUD·업무 로직은 하지 않는다 |
| Database | PostgreSQL | `sort_log` (결과 1건 = 1행), 이력·집계 |
| Messaging | Mosquitto (호스트 1883) | ROS ↔ 웹의 유일한 경계 |
| Infra | Docker Compose + Nginx + GitHub Actions | 컨테이너 실행, `/` React, `/api` → Spring Boot, `/ai` → FastAPI(필요 시) |

### 경계 (VOSS 계약과 맞춘 부분)
1. **브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다.** ROS ↔ 웹은 `hmi_bridge` ↔ Mosquitto ↔ Spring Boot 만. MQTT JSON 은 `docs/interfaces/mqtt.md` (10/08 확정, #20).
2. **음성 ROS 노드 계약은 그대로 둔다.** `voice_listener`·`intent_parser`·`speech_out` 과 `/voss/voice/*` 토픽은 바뀌지 않는다.
   - `voice_listener`(호스트, 마이크) → 녹음 WAV 를 FastAPI `/stt` 로 보내 Whisper 전사 → `/voss/voice/transcript`
   - `intent_parser` → FastAPI `/intent` 로 transcript 전달 → OpenAI structured output → 허용 목록 검증 → `/voss/voice/intent`
   - 허용 목록 검증은 intent_parser 에서 최종 수행한다 (FastAPI 응답도 신뢰하지 않음, `intent_json.md`).
   - FastAPI HTTP 스펙(`/stt`, `/intent`)은 #17·#18 PR 에서 `docs/interfaces/` 에 추가한다.
3. **분류 결과 DB 쓰기는 `sort_logger`(rclpy)가 한다.** `/voss/sort/result` → `sort_log` INSERT (writer 계정). Spring Boot 는 `sort_log` 를 읽기 전용 계정으로 조회·집계하고, 웹 전용 업무 데이터(투입 예정 수량 등)는 자기 테이블에 쓴다. G0 의 "DB commit·조회"는 sort_logger + PostgreSQL 만으로 판정할 수 있어 웹 스택 기동 여부와 분리된다.
4. **집계의 기준(source of truth)은 PostgreSQL 하나.** 음성 이력 질의("역삼동 몇 개?")와 HMI 숫자는 같은 Spring Boot 조회 API 결과를 쓴다. 음성 경로(intent_parser → Spring Boot REST → 응답 발화)와 `/voss/sort/stats` 정리는 MC-022·023 합의 후 `intent_json.md`·`topics.md` 변경 PR 로 한다 (이 ADR 에서 토픽 계약을 바꾸지 않음).
5. **LLM 은 해석만 한다.** DB 처리·로봇 명령 실행은 Spring Boot·sort_manager 가 한다.

### 배포 (제안 — MC-029 에서 김학민·남현지 확인)
| 구성요소 | 위치 | 포트(제안) | 비고 |
|---|---|---|---|
| Mosquitto | 호스트 | 1883 | 현재 문서 유지 |
| voice_listener / intent_parser / speech_out / hmi_bridge / sort_logger | 호스트 (ROS) | — | 변경 없음 |
| FastAPI (Whisper) | `docker/ai/` 컨테이너, GPU | 8000 | VRAM 을 비전과 공유 → Whisper 크기는 동시 부하 실측 후 (pending #6, MC-028) |
| Spring Boot | `docker/web/` 컨테이너 | 8080 | `--network host` 로 Mosquitto·PostgreSQL 접근 |
| React (빌드 산출물) + Nginx | `docker/web/` 컨테이너 | 80 | 단일 진입점 |
| PostgreSQL | `docker/db/` 컨테이너 + 호스트 볼륨 | 5432 | 버전은 #21 에서 기록 |

비밀값(`OPENAI_API_KEY`, DB 비밀번호)은 `.env`(gitignore) 로만 주입한다. `OPENAI_API_KEY` 는 FastAPI 컨테이너에만 둔다.

## 고려한 대안
- **웹을 Python(FastAPI 하나)으로 통일**: 언어는 하나지만 스택 문서 기준(업무 로직은 Spring Boot)과 다르고 AI 의존성과 웹이 한 프로세스에 묶임.
- **Spring Boot 가 DB 유일 writer (MQTT `voss/result` 구독 후 INSERT)**: 스택 문서 원칙에 더 가깝지만 `sort_logger` 를 없애야 해서 topics.md 가 바뀌고, G0 DB 판정이 Mosquitto·Spring Boot 기동에 의존. B 단계에서 다시 검토 가능.
- **Whisper·OpenAI 를 ROS 노드 안에서 직접 호출**: 구성은 단순하지만 Spring Boot 의 텍스트 명령·이력 질의와 AI 로직이 중복됨.
- **DB SQLite**: 설치는 쉽지만 Spring Boot 동시 조회·컨테이너 분리·집계 SQL 에 불리.

## 결과
- pending #13 의 "웹 스택·실행 위치"와 #14 "DB 종류"를 이 ADR 로 제안. 승인 시 두 행을 "결정"으로. #13 의 MQTT JSON 은 10/08 `mqtt.md` 에서 별도 확정.
- 새 디렉터리 `docker/ai/` (CODEOWNERS 추가: 정의석 + 남현지).
- 상호확인 회신에서 이 ADR 을 근거로 답한다: MC-022(조회 = Spring Boot + PostgreSQL), MC-026(Spring Boot 가 MQTT 클라이언트), MC-028(FastAPI GPU 동거), MC-029(배포 표).
- 리스크: 컨테이너 3개 추가로 공용 PC 자원 사용 증가(MC-028 실측 필요), Java 빌드 시간. A 단계(G0)는 sort_logger + PostgreSQL 만 필요하므로 웹·AI 컨테이너가 G0 를 막지 않는다.
