# 웹·AI HTTP API (Spring Boot `/api`, FastAPI `/ai`)

2026-10-14 확장(T13 #37, PL 리뷰): SSE `box_track`·`robot_pose`·`robot_joints`·`voice_status` **승인**(실시간 전용 — 저장·접속 스냅샷·재전송 없음), `box_motion` 은 **제안**(BoxMotion IDL 전, [box_carry_proposal.md](box_carry_proposal.md)). `robot_pose.orientation`은 TCP 기준 박스 오프셋 회전용이다. Truck 수량은 계속 `/api/sessions/current.by_zone`의 DB 집계만 사용한다.

ADR-0006 기준. 브라우저는 Nginx(80) 하나로 들어오고 `/` → React, `/api` → Spring Boot(127.0.0.1:8080) 로 넘어간다. **Nginx 는 `/ai` 를 넘기지 않는다** — FastAPI 는 음성 ROS 노드만 `http://127.0.0.1:8000` 으로 부른다(Wi-Fi 에서 OpenAI 사용량이 나가지 않게). 브라우저·Spring Boot 는 ROS 에 직접 붙지 않는다(ROS ↔ 웹은 MQTT, `mqtt.md`).

## 공통
- JSON, UTF-8. 시각은 ISO-8601 `+09:00` 문자열(공용 PC 시스템 시계).
- 실패 응답: HTTP 4xx/5xx + `{"ok": false, "message": "<대문자 코드>", "detail": "<사람이 읽을 문구>"}`.
  - 코드: `DB_ERROR`(DB 연결·조회 실패) · `INVALID_QUERY`(허용 외 파라미터) · `UNKNOWN_DONG`(zone_map 에 없는 동) · `NO_SESSION`(세션 없음) · `MQTT_DOWN`(브로커 끊김) · `FORBIDDEN_REMOTE`(원격에서 움직이는 명령)
- **열 포트 (ufw 기준, #55 MC-026·029 · #68 김학민 리뷰):**

  | 포트 | 바인드 | `wlo1` 개방 |
  |---|---|---|
  | 80 Nginx | 0.0.0.0 | ✅ |
  | 1883 Mosquitto | 0.0.0.0 (아래 ACL 적용) | 개발 중 디버그 필요 시에만 임시 개방, **시연 때 ❌** (#20) |
  | 8080 Spring Boot (`server.address=127.0.0.1`) · 8000 FastAPI · 5432 PostgreSQL (`listen_addresses=localhost`) | 127.0.0.1 | ❌ |

  로봇망 `enp4s0` 에는 어떤 웹·MQTT 포트도 열지 않는다.
- **로봇을 움직이는 명령의 접근 제한 (안전, #68 남현지 🔴):** `POST /api/commands` 의 `start`·`resume`·`priority`·`answer`·`recheck`·`reset_zone`·`palletize`(Sprint 2) 는 **공용 PC 로컬 접속(공용 PC 화면의 HMI)** 에서만 받는다. 그 밖은 `403 {"ok": false, "message": "FORBIDDEN_REMOTE"}`. **`stop` 은 어디서든 받는다**(멈추는 쪽은 막지 않는다). 조회(`GET`)·SSE 는 `wlo1` 허용.
  - 원격 판정은 Nginx 가 넣는 `X-Real-IP $remote_addr` 로만 한다. 클라이언트가 보낸 `X-Forwarded-For` 는 믿지 않는다(Nginx 뒤에서는 모든 요청이 127.0.0.1 로 보이므로).
  - 판정은 Spring Boot 한 곳에서만 한다. hmi_bridge(ROS) 는 원격 여부를 다시 판단하지 않는다.
- **Mosquitto ACL:** `voss/command` 쓰기는 Spring Boot 계정(`web`)만. 개인 PC 디버그 계정(`debug`)은 `voss/#` 읽기만. hmi_bridge 계정(`bridge`)은 `voss/command` 읽기와 bridge 출력 토픽만 쓰기(`voss/command` write 금지). 비밀번호는 Git에 넣지 않는다. 브로커는 공용 PC 호스트 1883이며 시연 때 `wlo1`의 1883은 닫는다. 상세는 #20 `mqtt.md`.
- 그 밖의 인증은 없다(교육장 LAN, 시연 2주). 원격 HMI 시작이 필요해지면 `.env` 공유 토큰 헤더로 바꾼다.
- **집계의 유일한 원천은 PostgreSQL `sort_log`**(#52 MC-022). Spring Boot 는 읽기 전용 계정으로만 조회한다. 쓰기는 sort_logger(ROS) 하나.
- 현재 세션 = **`SortState.session_id`**(#78). sort_manager 가 `start` 때 만들고 다음 `start` 까지 유지한다(IDLE·PAUSED 에서도 유지). Spring Boot 는 hmi_bridge 가 MQTT 로 넘기는 SortState 에서 이 값을 받는다(#20 mqtt.md).
  - **`session_id == ""`(첫 `start` 전) 이면 현재 세션이 없는 것**으로 본다. `session_id` 를 생략한 조회(`/api/stats`·`/api/results`·`/api/export.csv`)는 `404 NO_SESSION` 을 돌려주고(음성은 "기록을 조회할 수 없습니다"), HMI 는 빈 문자열로 조회하지 않는다. `/api/sessions/current` 만 예외로 `200` + `session_id: ""`·`planned`(다음 세션 예정 수량)·나머지 0 을 돌려준다(시작 전 HMI 가 투입 수량을 보여 주도록). `session_id=all` 과 명시한 session_id 조회는 그대로 된다.
  - `sort_log` 의 최근 행으로 현재 세션을 추정하지 않는다(PAUSED 중이거나 첫 결과 전인 세션을 놓친다).

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
- Spring Boot 자체 테이블 `session_plan(session_id varchar(24) PK, planned int NOT NULL, updated_at timestamptz)` 에 저장. 세션이 아직 없으면(`SortState.session_id == ""`) `next` 로 저장했다가, 새 `SortState.session_id` 를 처음 받을 때(`start` 시점) 그 session_id 에 붙인다.

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
- 요청 `{"type": "start|stop|resume|priority|answer|recheck|reset_zone|palletize", "args": {...}, "raw_text": "HMI 버튼"}` (type·args 는 `Command` canonical 표, voss_msgs.md). `recheck`의 `args`는 `{}`.
- Spring Boot 가 `command_id`(UUID)·`sent_at` 을 붙여 MQTT 로 발행하고 **즉시** `202 {"ok": true, "command_id": "…"}` 를 준다. 이것은 "브로커 전달" 이지 manager 접수가 아니다.
- manager 접수 결과는 SSE `command_ack` 이벤트로 온다(hmi_bridge 가 `/voss/sort/command` 응답을 `voss/command/ack` 로 회신). 완료는 `state`·`result` 이벤트로 본다.
- 브로커 끊김: `503 {"ok": false, "message": "MQTT_DOWN"}`, HMI 버튼 비활성화.
- 원격에서 움직이는 명령: `403 FORBIDDEN_REMOTE`(위 공통 절). `stop` 은 원격·로컬 모두 받는다.
- **Sprint 2 인자 검사 (S2-T08, 발행 전에 Spring Boot 가 본다):**
  - `palletize` — `args` 는 `{"route": [...]}` 키 하나. `route` = 문자열 배열 1~3개·중복 없음·빈 문자열 없음(배송 순서, 첫 배송지부터). 형식이 틀리면 `400 INVALID_QUERY`, zone_map 정식 동 이름이 아니면(별칭 포함) `400 UNKNOWN_DONG`. MQTT `voss/command` 에는 `args` 를 그대로 싣는다(쉼표 문자열로 바꾸는 것은 hmi_bridge, mqtt.md). 시작 조건(처리 중 박스 없음·팔레트 칸 0·교시)은 manager 가 보고 `command_ack` 로 거부한다.
  - `reset_zone` — `zone` 에 `PALLET` 추가(A/B/C/RECHECK/HOLD/PALLET). manager 는 PALLET 비움 확인을 IDLE·PAUSED 에서만 받고, RUNNING 은 거부한다(PR #176 PL 안전 결정). 웹 화면은 먼저 정지 → 실물 비움 확인 → 비움 명령 → 재개 순서를 안내한다. 소프트웨어 stop 은 물리 안전정지를 대신하지 않는다.

### `POST /api/voice/announce` — 로컬 HMI 버튼 음성 안내

`{"action":"start|stop|resume|priority|answer|reset_zone|palletize|plan"}` 하나만 받는다. 로컬 Nginx의 `X-Real-IP`가 `127.0.0.1` 또는 `::1`일 때만 `202`와 `request_id`를 반환하고, 고정 문구 코드만 MQTT `voss/voice/request`로 보낸다. 브리지가 `/voss/voice/say`로 전달하고 Nodes PC의 `speech_out`이 재생한다. 응답은 MQTT 전송 접수이며 실제 스피커 출력이나 로봇 동작 완료를 보장하지 않는다.

### `POST /api/voice/text` — 로컬 관제 화면 자연어 명령
요청은 `{"request_id":"<UUID>","text":"역삼, 대치 순서로 팔레타이징 실행해"}`다. 텍스트는 1~240자이며 Web PC 로컬 `X-Real-IP`만 허용한다. `202`는 MQTT 전달 접수일 뿐이다. 텍스트는 `voss/voice/text` → Web PC 브리지 → 로컬 ROS `intent_parser`로 가서 음성과 같은 동·구역 검증을 받는다. Web PC의 intent_parser는 `GET /api/stream`의 `zone_map`·`state`로도 허용 동과 현재 질문을 갱신한다(PC 간 ROS 데이터 지연 대비). 해석 결과 문구는 MQTT `voss/voice/text/reply` → SSE `text_reply`로 반환한다. 실행 명령은 Web PC의 intent_parser가 로컬 `POST /api/commands`로 보내며, 거부·접속 오류 시 성공 안내를 하지 않는다. `"팔레타이징 실행해"`처럼 배송 순서가 없으면 실행하지 않고 순서를 묻는다. 실제 명령 접수·완료 여부는 별도 `command_ack`·로봇 상태로 확인한다.

### `GET /api/stream` — SSE (React 실시간 갱신)
| event | data | 원천 |
|---|---|---|
| `state` | `voss/state` JSON 그대로 | SortState (≥2 Hz) |
| `result` | `voss/result` JSON 그대로 | SortResult (박스당 1건) |
| `zone_map` | `voss/zone_map` JSON | retained |
| `robot` | `voss/robot` JSON | RobotState |
| `box_track` | `voss/box_track` JSON 그대로 | BoxTrack 유효 좌표·트랙 ID, 최대 10 Hz/트랙. 재전송 없음 |
| `robot_pose` | `voss/robot_pose` JSON 그대로 | TCP base_link 좌표, 최대 20 Hz. 재전송 없음 |
| `robot_joints` | `voss/robot_joints` JSON 그대로 | 기존 6축 JointState, rad, 최대 20 Hz. 저장·재전송 없음. [상세](robot_joints_fk_proposal.md) |
| `voice_status` | `{"phase","event_id","utterance_id"}` | 음성 표시등. retained 거부·snapshot 없음. [상세](voice_status.md) |
| `text_reply` | `{"request_id","message"}` | 텍스트 명령 해석 결과 안내. retained 거부·snapshot 없음 |
| `box_motion` (제안) | `voss/box_motion` JSON 그대로 | BoxMotion GRASPED/RELEASED. 저장·재전송 없음. [제안](box_carry_proposal.md) |
| `command_ack` | `voss/command/ack` JSON | Command 응답 |
| `log_status` | `{"status": "OK|DB_ERROR|SPOOL_FULL|STARTING", "stamp": "…"}` | `/voss/log/status` (hmi_bridge 전달) |
| `link` | `{"mqtt": "UP|DOWN"}` | Spring Boot 브로커 연결 |
| `pallet_state` | `voss/pallet/state` JSON 그대로 | PalletState (Sprint 2 S2-T08 — 바뀔 때, retained. 계획 직후·첫 PICK 전 한 번 + 박스마다) |
- 접속 직후 Spring Boot 가 마지막 `state`·`zone_map`·`robot`·`log_status`·`pallet_state` 를 한 번씩 보낸다(늦게 연 브라우저도 바로 표시).
- 3초 이상 `state` 가 없으면 HMI 는 `UNKNOWN` 으로 표시한다(값을 0·정상으로 위장하지 않음).
- `state` 의 값은 voss_msgs.md SortState 그대로 받는다 — Sprint 2 `PALLETIZING` 포함. 목록에 없는 값은 버린다(그러면 3초 뒤 UNKNOWN).
- `pallet_state` 는 바뀔 때만 와서 나이로 장애를 가르지 않는다. 마지막 배치도를 계속 보이되 `link` 가 DOWN 이거나 SSE 가 끊기면 "갱신 안 됨"으로 표시한다. `run_id == ""` 이면 실행 없음(빈 팔레트). 칸 배열 인덱스 = slot 0~15(voss_msgs.md PalletState).
- `GET /api/pallet/placements/latest`는 `pallet_log`의 가장 최근 회차에서 `run_id`, `box_id`, `dong`, `route_index`, `pallet_slot`, `result`만 읽는다. `pallet_state`가 도착하지 않는 Web PC에서는 이 공식 기록으로 적재된 칸을 채우고 새 `DONE` 행마다 애니메이션을 보여준다. 화면에는 최근 DB 회차임을 표시하며, DB만으로 실물 비움 여부나 회차 종료를 단정하지 않는다.
- HMI 반영 ≤ 1초 측정: manager 상태 변경 로그 → DOM(전체), hmi_bridge 수신 → DOM(부분) 둘 다 기록(#54 MC-031).

### 음성 상태 SSE (`voice_status`, 10/14 승인)

기존 `GET /api/stream`에 `voice_status` 이벤트를 더했다. `/api/events`는 실제 계약에 없으므로 사용하지 않는다.
데이터는 `phase`, `event_id`, `utterance_id`이며 [voice_status.md](voice_status.md)의 검증·중복·연결 처리 규칙을 따른다.
이 이벤트는 접속 직후 snapshot/재연결 replay 대상이 아니다. 다른 SSE 이벤트·DB·명령 API는 그대로다.

## FastAPI `/ai` (음성 ROS 노드 전용, ADR-0006)
브라우저는 쓰지 않는다(Nginx 미노출). voice_listener·intent_parser 가 `http://127.0.0.1:8000` 으로 직접 호출한다. stop 키워드는 FastAPI 를 거치지 않는다(intent_json.md). `OPENAI_API_KEY` 는 이 컨테이너 환경 변수에만 둔다.

### `POST /ai/stt` — Whisper 전사
- 요청: `multipart/form-data` `audio`(WAV 16 kHz mono) + `language=ko`
- 응답: `{"ok": true, "text": "역삼동부터 분류해", "duration_ms": 1830, "stt_ms": 420, "model": "whisper-<크기>"}` — 모델 크기는 pending #6(10/08 동시 부하 시험 후)
- 실패: `{"ok": false, "message": "STT_ERROR|AUDIO_INVALID"}` → voice_listener 는 "다시 말씀해 주세요"

### `POST /ai/intent` — 자연어 → intent JSON
- 요청: `{"text": "역삼부터 해", "allowed": {"dongs": ["역삼동","대치동","청담동"], "aliases": {"역삼동": ["역삼"]}, "zones": ["A","B","C"]}}` — `allowed` 는 intent_parser 가 `/voss/sort/zone_map` 에서 만든다(FastAPI 는 YAML·ROS 를 모른다).
- 응답: `{"ok": true, "intent": <intent_json.md 의 JSON>, "llm_ms": 640, "model": "<OpenAI 모델명>"}`
- 지원하지 않는 요청은 `intent.type="unknown"` 으로 반환한다. `intent_parser` 는 이를 실행하지 않고 미지원 안내만 한다.
- 실패: `{"ok": false, "message": "LLM_TIMEOUT|LLM_ERROR|PARSE_ERROR"}`, timeout 기본 3초.
- **intent_parser 가 응답을 다시 검증**한다(허용 목록·필수 필드). FastAPI 응답을 그대로 믿지 않는다.

### `POST /ai/tts` — GPT-4o mini TTS 음성 합성 (T10 #19)
- 호출자: ROS `speech_out` 전용. FastAPI는 127.0.0.1:8000에서만 수신하고 Nginx로 노출하지 않는다.
- 요청: `{"text": "분류를 시작합니다."}` (공백 제외 불가, 1~500자)
- 모델: `gpt-4o-mini-tts`, 초기 음성 `coral` (`docker/ai/.env` 설정)
- 성공: HTTP 200, `Content-Type: application/octet-stream`
- 음성 형식: `X-Audio-Format: S16LE;rate=24000;channels=1`
- 본문: 헤더 없는 24 kHz, 16-bit little-endian, mono PCM 스트림
- 실패: 공통 오류 JSON 형식
  - 400 `TTS_INVALID`: 잘못된 입력
  - 503 `TTS_UNAVAILABLE`: TTS 설정 누락
  - 504 `TTS_TIMEOUT`: 첫 음성 생성 전 시간 초과
  - 502 `TTS_ERROR`: 첫 음성 생성 전 API 실패
- 스트리밍 시작 후 실패는 HTTP 상태를 변경할 수 없으므로 연결 종료와 오류 로그로 처리한다.
- 자동 재시도 없음. API 키는 FastAPI 컨테이너에만 보관한다.
- 검증: SYS-FR-022 / VT-022, SYS-PF-005 / VT-049

## 변경 이력
- 2026-10-13: **Sprint 2 S2-T08 웹 쪽**(BRD v1.5 TR-PAL-10 — 제안, 정의석 확인 필요). SSE `pallet_state`(접속 직후 스냅샷 포함, 나이 판정 없음), `palletize`·`reset_zone PALLET` 인자 검사, SortState `PALLETIZING` 수용 명시, `pallet_log` 웹 조회는 두지 않음.
- 2026-10-12: **Sprint 2**(S2-T01 — 제안). `POST /api/commands` 에 `palletize`(로봇을 움직이므로 공용 PC 로컬만). 팔레트 배치도 SSE·이력 조회(`pallet_log`)는 S2-T08 에서 정한다.
- 2026-10-08: #20 MQTT 계약 확정에 맞춰 1883/wlo1은 개발 디버그 때만 임시 개방하고 시연 때 차단하도록 정합.
- 2026-10-07: `SortState.session_id`(#78) 머지에 맞춰 "현재 세션" 확정 — 임시 규칙(최근 `sort_log` 행) 삭제, `session_id == ""` 이면 `NO_SESSION`(#78 김학민 🟢, `/api/sessions/current` 는 예정 수량만), `next` 예정 수량은 첫 결과가 아니라 `start` 때 붙임. "의존" 절 삭제.
- 2026-10-07: 리뷰 반영(#68 남현지·김학민) — 움직이는 명령은 공용 PC 로컬만·`stop` 은 어디서든, 원격 판정은 Nginx `X-Real-IP`, 포트 바인드 표, Mosquitto ACL, Nginx `/ai` 제거, SortState.session_id 수용.
- 2026-10-06: 초안 (#22, ADR-0006, SRD 상호확인 #52 MC-020·021·022·026·027, #54 MC-030·031). 제안 상태 — mqtt.md(10/08, #20) 확정 때 SSE `data` 형식을 함께 맞춘다.
- 2026-10-13: (T13 #37) SSE `box_track`·`robot_pose` 추가. 제안: `robot_joints`·`box_motion`·`voice_status`(snapshot·replay 없음).
- 2026-10-14: #37 PL 리뷰 — `robot_joints`·`voice_status` 승인, `box_motion` 제안 유지, SSE 표에 행 추가.

- 2026-10-15: PR #176 PL 결정 — PALLET 비움의 manager 상태 제한(`IDLE`·`PAUSED`) 및 HMI의 정지→실물 비움→재개 안내 명시. REST 필드·오류 코드 추가 없음.
