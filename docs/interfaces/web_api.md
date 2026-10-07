# 웹·AI HTTP API (Spring Boot `/api`, FastAPI `/ai`)

ADR-0006 기준. 브라우저는 Nginx(80) 하나로 들어오고 `/` → React, `/api` → Spring Boot(127.0.0.1:8080) 로 넘어간다. **Nginx 는 `/ai` 를 넘기지 않는다** — FastAPI 는 음성 ROS 노드만 `http://127.0.0.1:8000` 으로 부른다(Wi-Fi 에서 OpenAI 사용량이 나가지 않게). 브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다(ROS ↔ 웹은 MQTT, `mqtt.md`).

## 공통
- JSON, UTF-8. 시각은 ISO-8601 `+09:00` 문자열(공용 PC 시스템 시계).
- 실패 응답: HTTP 4xx/5xx + `{"ok": false, "message": "<대문자 코드>", "detail": "<사람이 읽을 문구>"}`.
  - 코드: `DB_ERROR`(DB 연결·조회 실패) · `INVALID_QUERY`(허용 외 파라미터) · `UNKNOWN_DONG`(zone_map 에 없는 동) · `NO_SESSION`(세션 없음) · `MQTT_DOWN`(브로커 끊김) · `FORBIDDEN_REMOTE`(원격에서 움직이는 명령)
- **열 포트 (ufw 기준, #55 MC-026·029 · #68 김학민 리뷰):**

  | 포트 | 바인드 | `wlo1` 개방 |
  |---|---|---|
  | 80 Nginx | 0.0.0.0 | ✅ |
  | 1883 Mosquitto | 0.0.0.0 (아래 ACL 적용) | ✅ 디버그 읽기용. 시연 때 닫을지는 #20 에서 결정 |
  | 8080 Spring Boot (`server.address=127.0.0.1`) · 8000 FastAPI · 5432 PostgreSQL (`listen_addresses=localhost`) | 127.0.0.1 | ❌ |

  로봇망 `enp4s0` 에는 어떤 웹·MQTT 포트도 열지 않는다.
- **로봇을 움직이는 명령의 접근 제한 (안전, #68 남현지 🔴):** `POST /api/commands` 의 `start`·`resume`·`priority`·`answer`·`reset_zone` 은 **공용 PC 로컬 접속(공용 PC 화면의 HMI)** 에서만 받는다. 그 밖은 `403 {"ok": false, "message": "FORBIDDEN_REMOTE"}`. **`stop` 은 어디서든 받는다**(멈추는 쪽은 막지 않는다). 조회(`GET`)·SSE 는 `wlo1` 허용.
  - 원격 판정은 Nginx 가 넣는 `X-Real-IP $remote_addr` 로만 한다. 클라이언트가 보낸 `X-Forwarded-For` 는 믿지 않는다(Nginx 뒤에서는 모든 요청이 127.0.0.1 로 보이므로).
  - 판정은 Spring Boot 한 곳에서만 한다. hmi_bridge(ROS) 는 원격 여부를 다시 판단하지 않는다.
- **Mosquitto ACL:** `voss/command` 쓰기는 Spring Boot 계정(`web`)만. 개인 PC 디버그 계정(`debug`)은 `voss/#` 읽기만. hmi_bridge 계정(`bridge`)은 `voss/command` 읽기, 나머지 `voss/#` 쓰기. 비밀번호는 `.env`(gitignore). 상세 설정은 #20 mqtt.md.
- 그 밖의 인증은 없다(교육장 LAN, 시연 2주). 원격 HMI 시작이 필요해지면 `.env` 공유 토큰 헤더로 바꾼다.
- **집계의 유일한 원천은 PostgreSQL `sort_log`**(#52 MC-022). Spring Boot 는 읽기 전용 계정으로만 조회한다. 쓰기는 sort_logger(ROS) 하나.
- 현재 세션 = **`SortState.session_id`**(남현지 수용, 추가 예정). 그 필드가 main 에 들어오기 전까지는 `sort_log` 에서 가장 최근 `finished_at` 의 `session_id`.

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
- 원격에서 움직이는 명령: `403 FORBIDDEN_REMOTE`(위 공통 절). `stop` 은 원격·로컬 모두 받는다.

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
브라우저는 쓰지 않는다(Nginx 미노출). voice_listener·intent_parser 가 `http://127.0.0.1:8000` 으로 직접 호출한다. stop 키워드는 FastAPI 를 거치지 않는다(intent_json.md). `OPENAI_API_KEY` 는 이 컨테이너 환경 변수에만 둔다.

### `POST /ai/stt` — Whisper 전사
- 요청: `multipart/form-data` `audio`(WAV 16 kHz mono) + `language=ko`
- 응답: `{"ok": true, "text": "역삼동부터 분류해", "duration_ms": 1830, "stt_ms": 420, "model": "whisper-<크기>"}` — 모델 크기는 pending #6(10/08 동시 부하 시험 후)
- 실패: `{"ok": false, "message": "STT_ERROR|AUDIO_INVALID"}` → voice_listener 는 "다시 말씀해 주세요"

### `POST /ai/intent` — 자연어 → intent JSON
- 요청: `{"text": "역삼부터 해", "allowed": {"dongs": ["역삼동","대치동","청담동"], "aliases": {"역삼동": ["역삼"]}, "zones": ["A","B","C"]}}` — `allowed` 는 intent_parser 가 `/voss/sort/zone_map` 에서 만든다(FastAPI 는 YAML·ROS 를 모른다).
- 응답: `{"ok": true, "intent": <intent_json.md 의 JSON>, "llm_ms": 640, "model": "<OpenAI 모델명>"}`
- 실패: `{"ok": false, "message": "LLM_TIMEOUT|LLM_ERROR|PARSE_ERROR"}`, timeout 기본 3초.
- **intent_parser 가 응답을 다시 검증**한다(허용 목록·필수 필드). FastAPI 응답을 그대로 믿지 않는다.

## 의존
- **SortState 끝에 `string session_id`** — 남현지 수용(#68 리뷰), 남현지 인터페이스 PR 에서 추가. 들어오면 "현재 세션" 은 이 값을 쓴다.

## 변경 이력
- 2026-10-07: 리뷰 반영(#68 남현지·김학민) — 움직이는 명령은 공용 PC 로컬만·`stop` 은 어디서든, 원격 판정은 Nginx `X-Real-IP`, 포트 바인드 표, Mosquitto ACL, Nginx `/ai` 제거, SortState.session_id 수용.
- 2026-10-06: 초안 (#22, ADR-0006, SRD 상호확인 #52 MC-020·021·022·026·027, #54 MC-030·031). 제안 상태 — mqtt.md(10/08, #20) 확정 때 SSE `data` 형식을 함께 맞춘다.
