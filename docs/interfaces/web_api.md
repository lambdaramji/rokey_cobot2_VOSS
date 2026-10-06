# 웹·AI HTTP API (Spring Boot `/api`, FastAPI `/ai`)

ADR-0006 기준. 브라우저는 Nginx(80) 하나로 들어오고 `/api` → Spring Boot(8080), `/ai` → FastAPI(8000) 로 넘어간다. 브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다(ROS ↔ 웹은 MQTT, `mqtt.md`).

## 공통
- JSON, UTF-8. 시각은 ISO-8601 `+09:00` 문자열(공용 PC 시스템 시계).
- 실패 응답: HTTP 4xx/5xx + `{"ok": false, "message": "<대문자 코드>", "detail": "<사람이 읽을 문구>"}`.
  - 코드: `DB_ERROR`(DB 연결·조회 실패) · `INVALID_QUERY`(허용 외 파라미터) · `UNKNOWN_DONG`(zone_map 에 없는 동) · `NO_SESSION`(세션 없음) · `MQTT_DOWN`(브로커 끊김)
- 인증 없음. 공용 PC `wlo1` 에서만 열고 로봇망 `enp4s0` 에는 열지 않는다(#55 MC-026, ufw 는 김학민 10/07).
- **집계의 유일한 원천은 PostgreSQL `sort_log`**(#52 MC-022). Spring Boot 는 읽기 전용 계정으로만 조회한다. 쓰기는 sort_logger(ROS) 하나.
- 현재 세션 = `sort_log` 에서 가장 최근 `finished_at` 의 `session_id`. SortState 에 `session_id` 가 생기면 그것을 쓴다(아래 "확인 요청").

## Spring Boot `/api`

### `GET /api/stats` — 이력 질의 (음성·HMI 공용, #52 MC-021·022)
| 파라미터 | 필수 | 값 |
|---|---|---|
| `query_kind` | ✓ | `count_by_dong` · `held_count` · `remaining_count` |
| `dong` | count_by_dong 일 때 ✓ | zone_map 의 정식 동 이름 |
| `session_id` | | 생략 = 현재 세션 |

| query_kind | 계산 (같은 session_id 안) |
|---|---|
| `count_by_dong` | `COUNT(*) WHERE result = 'PLACED' AND dong = :dong` (그 동으로 분류 적재한 수) |
| `held_count` | `COUNT(*) WHERE result = 'HELD'` |
| `remaining_count` | `GREATEST(planned − COUNT(*) FILTER (WHERE result IN ('PLACED','HELD','FAILED')), 0)` — PASSED 제외 (MC-021) |

응답 예:
```json
{"ok": true, "query_kind": "count_by_dong", "dong": "역삼동", "session_id": "20261010T143012-a3f9", "count": 3, "as_of": "2026-10-10T14:31:02+09:00"}
```
- `as_of` = 조회 완료 시각. 음성("역삼동은 지금까지 3개입니다")과 HMI 숫자는 같은 이 API 결과를 쓴다.
- DB 장애: `503 {"ok": false, "message": "DB_ERROR"}` → 음성은 "기록을 조회할 수 없습니다".

### `GET /api/sessions/current` — HMI 요약 카드
```json
{"ok": true, "session_id": "20261010T143012-a3f9", "planned": 10,
 "placed": 3, "held": 1, "failed": 1, "passed": 2, "remaining": 5,
 "by_zone": {"A": 1, "B": 1, "C": 1, "RECHECK": 0, "HOLD": 1},
 "as_of": "2026-10-10T14:35:40+09:00"}
```

### `PUT /api/sessions/current/plan` — 투입 예정 수량 (SYS-FR-032)
- 요청 `{"planned": 10}` (1 ~ 100 정수, 기본 10). 응답은 위 `/api/sessions/current` 와 같은 형식.
- Spring Boot 자체 테이블 `session_plan(session_id varchar(24) PK, planned int NOT NULL, updated_at timestamptz)` 에 저장. 세션이 아직 없으면 `next` 로 저장했다가 첫 결과의 session_id 에 붙인다.

### `GET /api/results` — 이력·보류 목록
| 파라미터 | 값 |
|---|---|
| `session_id` | 생략 = 현재 세션, `all` = 전체 |
| `result` | `PLACED` · `HELD` · `FAILED` · `PASSED` (여러 개는 쉼표) |
| `limit` | 기본 50, 최대 500 (최근 `finished_at` 순) |

응답: `{"ok": true, "items": [ <sort_log 행 JSON> ... ], "as_of": "…"}`. 행 필드 이름은 `sort_log` 컬럼 그대로(#52 MC-020). 보류 목록 = `result=HELD`.

### `GET /api/export.csv` — 시험 증거 내보내기 (#54 MC-030·031)
- 파라미터 `session_id`(생략 = 현재, `all` = 전체). `sort_log` 전 컬럼 + `cycle_s = finished_at − started_at`(started_at 없으면 빈칸).
- 행을 사후에 고르지 않는다. 필터는 받는 쪽에서 SQL·스프레드시트로 한다.

### `POST /api/commands` — HMI 버튼 → MQTT `voss/command`
- 요청 `{"type": "start|stop|resume|priority|answer|reset_zone", "args": {...}, "raw_text": "HMI 버튼"}` (type·args 는 `Command` canonical 표, voss_msgs.md)
- Spring Boot 가 `command_id`(UUID)·`sent_at` 을 붙여 MQTT 로 발행하고 **즉시** `202 {"ok": true, "command_id": "…"}` 를 준다. 이것은 "브로커 전달" 이지 manager 접수가 아니다.
- manager 접수 결과는 SSE `command_ack` 이벤트로 온다(hmi_bridge 가 `/voss/sort/command` 응답을 `voss/command/ack` 로 회신). 완료는 `state`·`result` 이벤트로 본다.
- 브로커 끊김: `503 {"ok": false, "message": "MQTT_DOWN"}`, HMI 버튼 비활성화.

### `GET /api/stream` — SSE (React 실시간 갱신)
| event | data | 원천 |
|---|---|---|
| `state` | `voss/state` JSON 그대로 | SortState (≥2 Hz) |
| `result` | `voss/result` JSON 그대로 | SortResult (박스당 1건) |
| `zone_map` | `voss/zone_map` JSON | retained |
| `robot` | `voss/robot` JSON | RobotState |
| `command_ack` | `voss/command/ack` JSON | Command 응답 |
| `log_status` | `{"status": "OK|DB_ERROR|SPOOL_FULL|STARTING", "stamp": "…"}` | `/voss/log/status` (hmi_bridge 전달) |
| `link` | `{"mqtt": "UP|DOWN"}` | Spring Boot 브로커 연결 |
- 접속 직후 Spring Boot 가 마지막 `state`·`zone_map`·`robot`·`log_status` 를 한 번씩 보낸다(늦게 연 브라우저도 바로 표시).
- 3초 이상 `state` 가 없으면 HMI 는 `UNKNOWN` 으로 표시한다(값을 0·정상으로 위장하지 않음).
- HMI 반영 ≤ 1초 측정: manager 상태 변경 로그 → DOM(전체), hmi_bridge 수신 → DOM(부분) 둘 다 기록(#54 MC-031).

## FastAPI `/ai` (음성 ROS 노드 전용, ADR-0006)
브라우저는 쓰지 않는다. voice_listener·intent_parser 가 `http://localhost:8000` 으로 직접 호출한다. `OPENAI_API_KEY` 는 이 컨테이너 환경 변수에만 둔다.

### `POST /ai/stt` — Whisper 전사
- 요청: `multipart/form-data` `audio`(WAV 16 kHz mono) + `language=ko`
- 응답: `{"ok": true, "text": "역삼동부터 분류해", "duration_ms": 1830, "stt_ms": 420, "model": "whisper-<크기>"}` — 모델 크기는 pending #6(10/08 동시 부하 시험 후)
- 실패: `{"ok": false, "message": "STT_ERROR|AUDIO_INVALID"}` → voice_listener 는 "다시 말씀해 주세요"

### `POST /ai/intent` — 자연어 → intent JSON
- 요청: `{"text": "역삼부터 해", "allowed": {"dongs": ["역삼동","대치동","청담동"], "aliases": {"역삼동": ["역삼"]}, "zones": ["A","B","C"]}}` — `allowed` 는 intent_parser 가 `/voss/sort/zone_map` 에서 만든다(FastAPI 는 YAML·ROS 를 모른다).
- 응답: `{"ok": true, "intent": <intent_json.md 의 JSON>, "llm_ms": 640, "model": "<OpenAI 모델명>"}`
- 실패: `{"ok": false, "message": "LLM_TIMEOUT|LLM_ERROR|PARSE_ERROR"}`, timeout 기본 3초.
- **intent_parser 가 응답을 다시 검증**한다(허용 목록·필수 필드). FastAPI 응답을 그대로 믿지 않는다.

## 확인 요청
- **SortState 에 `string session_id` 추가 (남현지):** 첫 결과가 나오기 전에도 HMI·투입 수량이 현재 세션을 알 수 있게, SortState 끝에 `session_id` 를 붙이는 것을 제안한다. 받기 전까지는 위 "현재 세션" 규칙(최근 sort_log 행)으로 동작한다.

## 변경 이력
- 2026-10-06: 초안 (#22, ADR-0006, SRD 상호확인 #52 MC-020·021·022·026·027, #54 MC-030·031). 제안 상태 — mqtt.md(10/08, #20) 확정 때 SSE `data` 형식을 함께 맞춘다.
