# intent JSON (intent_parser 출력)

LLM(FastAPI `/intent`, OpenAI structured output — ADR-0006)의 출력은 반드시 아래 JSON 하나다. intent_parser 는 이 JSON 을 **다시 검증**하고, 허용 목록 밖 값이나 파싱 실패는 실행하지 않고 `/voss/voice/say` 로 되묻는다.

```json
{
  "type": "start | stop | resume | priority | answer | query_history | update_zone_map",
  "dong": "<zone_map 의 정식 동 이름> | null",
  "zone": "A | B | C | HOLD | null",
  "count": 0,
  "query_kind": "count_by_dong | held_count | remaining_count | null",
  "raw_text": "사용자 발화 원문"
}
```

## 값 규칙
- **`type` 은 소문자**, 값 enum(`zone`, `query_kind`)은 대문자·소문자를 위 표기 그대로 쓴다(SRD 상호확인 #52 MC-023).
- LLM JSON 의 `null` 은 ROS `voss_msgs/Intent` 로 옮길 때 `""`(문자열) / `0`(count) 으로 바꾼다.
- **허용 동·구역·별칭은 `/voss/sort/zone_map`(transient_local) 에서 받는다.** YAML 을 직접 읽지 않는다.
  - 발화의 별칭("역삼")은 intent_parser 가 정식 이름(`ZoneMapEntry.dong`, "역삼동")으로 바꿔 `dong` 에 넣는다. **별칭은 출력에 나가지 않는다.**
  - `dong`(정식 이름)은 `aliases` 가 비어 있어도 항상 허용한다.
  - zone_map 을 아직 받지 못했으면 intent 를 발행하지 않고 "준비 중입니다" 라고 답한다.
- "보류" 는 `zone = "HOLD"` 로 바꾼다(answer 에서만 허용).

## type 별 처리
| type | 필수 | 보내는 곳 | 비고 |
|---|---|---|---|
| start | — | `/voss/voice/intent` | `dong` 비움 = 전체 분류 (Command `start` arg `""`/`ALL` 과 같은 뜻) |
| stop / resume | — | `/voss/voice/intent` | resume 은 PAUSED 에서만 유효(manager 판단) |
| priority | `dong` | `/voss/voice/intent` | dong 없으면 되묻기 |
| answer | `dong` 또는 `zone=HOLD`, `box_id` | `/voss/voice/intent` | `box_id` = 발화 시작 시점의 최신 `/voss/sort/state` 가 ASKING 일 때의 `box_id`. ASKING 이 아니면 발행하지 않고 "지금은 답할 질문이 없습니다". 다른 type 은 `box_id = ""` |
| query_history | `query_kind` (+ `dong` 은 count_by_dong 에서 필수) | **REST `GET /api/stats`** (Spring Boot, `web_api.md`) | **sort_manager 로 보내지 않는다.** 결과를 intent_parser 가 `/voss/voice/say` 로 읽는다. DB 장애면 "기록을 조회할 수 없습니다" |
| update_zone_map | `dong`, `zone`(A/B/C) | `/voss/voice/intent` | **C 선택 범위** — G0 이후 채택 여부 결정(MC-033). 채택 전에는 "지금은 지원하지 않습니다" |

## 발화 예
| 발화 예 | type | dong | zone | query_kind | box_id |
|---|---|---|---|---|---|
| "전부 분류해" | start | null | null | null | "" |
| "역삼부터 분류해" | priority | 역삼동 | null | null | "" |
| "멈춰" / "다시 시작" | stop / resume | null | null | null | "" |
| (질문 중) "청담동이야" | answer | 청담동 | null | null | SortState.box_id |
| (질문 중) "보류해" | answer | null | HOLD | null | SortState.box_id |
| "역삼동 지금까지 몇 개야" | query_history | 역삼동 | null | count_by_dong | — (REST) |
| "보류 몇 개야" | query_history | null | null | held_count | — (REST) |
| "몇 개 남았어" | query_history | null | null | remaining_count | — (REST) |
| "대치동을 C 구역으로 바꿔" | update_zone_map | 대치동 | C | null | "" (C 범위) |
| "아무거나 해" | (거부) | | | | 되묻기 |

## 발화·중복
- intent_parser 가 `/voss/voice/say` 로 내는 문장(되묻기·준비 중·이력 응답)의 중복 억제는 intent_parser 가 맡는다(MC-025). manager 가 내는 문장은 manager 가 맡는다.
- 질문 회차(`<box_id>#<n>`) 를 쓰기로 하면 `box_id` 에 그대로 싣는다(#54, 남현지 결정 대기). 음성 쪽은 둘 다 처리한다.

## 시험 (VC-EUS-INTENT-01, #54 MC-031)
- 정답 세트 20문장(필수 지시 4유형 × 5)은 시험 전에 `src/voss_voice/test/fixtures/` 에 커밋한다.
- 판정: **전체 20건 중 정답 ≥ 19**. API 오류·timeout 도 분모에 넣고 따로 보고하며, API 성공 건만의 조건부 정확도는 참고로 적는다. 허용 외 입력은 100% 거부.

## 변경 이력
- 2026-10-05: 초안.
- 2026-10-06: SRD 상호확인 합의 반영 (#18, #52 MC-022·023·024·025, #47 별칭).
  - `type` 에 `query_history` 추가, `query_kind` 필드 추가. 이력 질의는 manager 로 보내지 않고 REST `GET /api/stats` 로 조회.
  - `zone` 에 `HOLD` 추가(answer 전용), 값 enum 대문자 규칙.
  - answer 의 `box_id`(Intent 끝에 추가, voss_msgs.md) — 늦은 답이 다음 질문에 적용되지 않게.
  - 별칭 → 정식 동 이름 변환, 허용 목록은 zone_map 토픽, zone_map 미수신 시 발행 안 함.
  - `update_zone_map` 은 C 선택 범위로 표시.
