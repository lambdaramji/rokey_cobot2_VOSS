# intent JSON (intent_parser 출력)

LLM(FastAPI `/intent`, OpenAI structured output — ADR-0006)의 출력은 반드시 아래 JSON 하나다. intent_parser 는 이 JSON 을 **다시 검증**하고, 허용 목록 밖 값이나 파싱 실패는 실행하지 않고 `/voss/voice/say` 로 되묻는다.

```json
{
  "type": "start | stop | resume | priority | answer | recheck | palletize | query_history | update_zone_map",
  "dong": "<zone_map 의 정식 동 이름> | null",
  "zone": "A | B | C | HOLD | null",
  "count": 0,
  "query_kind": "count_by_dong | held_count | remaining_count | null",
  "route": ["<정식 동 이름>", "..."] | null,
  "raw_text": "사용자 발화 원문"
}
```

## 값 규칙
- **stop 예외 (안전, #67 김학민 리뷰):** "멈춰 / 정지 / 스톱 / 그만" 같은 정지 키워드는 **LLM 호출 전에 로컬 매칭**으로 판정해 `type=stop` 을 바로 발행한다. zone_map 수신 여부·FastAPI·OpenAI 상태와 무관하며 되묻지 않는다. 오인식으로 멈추는 쪽은 허용한다(resume 으로 복구). 키워드 목록과 지연(발화 끝 → Intent 발행)은 #18 구현 PR 에서 측정해 정지 경로 전체 지연(#53 `/voss/robot/stop`)과 함께 보고한다.
- **`type` 은 소문자**, 값 enum(`zone`, `query_kind`)은 대문자·소문자를 위 표기 그대로 쓴다(SRD 상호확인 #52 MC-023).
- LLM JSON 의 `null` 은 ROS `voss_msgs/Intent` 로 옮길 때 `""`(문자열) / `0`(count) / `[]`(route) 으로 바꾼다.
- **`route`(palletize, Sprint 2 TR-PAL-01):** 말한 배송 순서 그대로(첫 배송지부터) 정식 동 이름 배열. 별칭은 정식 이름으로 바꾼다(`dong` 과 같은 규칙). **1~3개, 중복·미등록이 하나라도 있으면 발행하지 않고 되묻는다**(예 "배송 순서를 다시 말씀해 주세요"). palletize 가 아니면 `null`. 시작 조건(분류 중 박스 없음, 팔레트 비어 있음)은 sort_manager 가 보고 거부 이유를 말한다(TR-PAL-02).
- **허용 동·구역·별칭은 `/voss/sort/zone_map`(transient_local) 에서 받는다.** YAML 을 직접 읽지 않는다.
  - A/B/C 및 "에이/비/씨 구역"은 현재 구역표에서 동 하나에만 대응하면 그 동의 별칭으로 처리한다. 여러 동이 같은 구역을 공유하면 구역명만으로 동을 정하지 않는다. 팔레타이징 경로에서도 같은 변환을 쓴다.
  - "A구역부터 분류해", "비 구역 우선 선별해"는 LLM 없이 `priority`로 처리한다. 출력 `dong`은 현재 구역표의 정식 동 이름이다. "보류해"·부정·복합 목적지는 이 규칙으로 실행하지 않는다.
  - 발화의 별칭("역삼")은 intent_parser 가 정식 이름(`ZoneMapEntry.dong`, "역삼동")으로 바꿔 `dong` 에 넣는다. **별칭은 출력에 나가지 않는다.**
  - `dong`(정식 이름)은 `aliases` 가 비어 있어도 항상 허용한다.
  - zone_map 을 아직 받지 못했으면 intent 를 발행하지 않고 "준비 중입니다" 라고 답한다. **단 stop 은 예외**(위).
- "보류" 는 `zone = "HOLD"` 로 바꾼다(answer 에서만 허용). 질문 중(ASKING)에는 "고류"·"고려우"·"보루"처럼 보류로 들리는 STT 오인식도 intent_parser 가 보류 답으로 받는다(두 음절 자모 거리 ≤ 1 또는 "ㅗ + ㄹ류/려/루" 꼴, 10/15).
- **로컬 질문 답변(#124):** 등록된 동 이름 단독(`"대치동."`) 및 등록 동을 목적지로 한 `"~로 보내"`(`"역삼으로, 보내요"`)는 문장부호·공백을 정규화해 LLM 전에 처리한다. `ASKING`이고 현재 `box_id`가 있을 때만 `answer`를 발행한다. 그렇지 않으면 발행하지 않고 "지금은 답할 질문이 없습니다"라고 안내한다. 부정·복합·미등록 동 발화는 로컬 판정 대상이 아니며 기존 LLM·허용 목록 검증을 따른다. `raw_text`는 원문을 보존한다.

## type 별 처리
| type | 필수 | 보내는 곳 | 비고 |
|---|---|---|---|
| start | — | `/voss/voice/intent` | `dong` 비움 = 전체 분류 (Command `start` arg `""`/`ALL` 과 같은 뜻) |
| stop | — | `/voss/voice/intent` | **로컬 키워드 매칭으로 즉시 발행. LLM·zone_map 대기 없음, 되묻지 않음** |
| resume | — | `/voss/voice/intent` | PAUSED 에서만 유효(manager 판단) |
| priority | `dong` | `/voss/voice/intent` | dong 없으면 되묻기 |
| answer | `dong` 또는 `zone=HOLD`, `box_id` | `/voss/voice/intent` | `box_id` = 발화 시작 시점의 최신 `/voss/sort/state` 가 ASKING 일 때의 `box_id`. ASKING 이 아니면 발행하지 않고 "지금은 답할 질문이 없습니다". 다른 type 은 `box_id = ""` |
| recheck | — | `/voss/voice/intent` | 보관 중인 재확인 칸 박스 처리 시작(Command `recheck`). "재확인 시작/진행/해 줘" 는 LLM 전에 로컬 매칭(10/12 로컬 시험 브랜치). 보관 박스가 없거나 RUNNING 이 아니면 manager 가 거부 |
| query_history | `query_kind` (+ `dong` 은 count_by_dong 에서 필수) | **REST `GET /api/stats`** (Spring Boot, `web_api.md`) | **sort_manager 로 보내지 않는다.** 결과를 intent_parser 가 `/voss/voice/say` 로 읽는다. DB 장애면 "기록을 조회할 수 없습니다" |
| update_zone_map | `dong`, `zone`(A/B/C) | `/voss/voice/intent` | **C 선택 범위** — G0 이후 채택 여부 결정(MC-033). 채택 전에는 "지금은 지원하지 않습니다" |
| palletize | `route`(1~3개) | `/voss/voice/intent` | **Sprint 2**. `dong`·`zone` 비움. sort_manager 가 순서를 되읽는다("역삼동, 대치동, 청담동 순서로 싣겠습니다. 첫 배송지 역삼동은 오른쪽 열입니다") "대치, 역삼, 청담 순서로 실어줘" 같은 문형은 LLM 전에 로컬 매칭(10/12 김학민) — 말한 순서 = 배송 순서(첫 배송지부터, 10/13 PL). |

## 발화 예
| 발화 예 | type | dong | zone | query_kind | box_id |
|---|---|---|---|---|---|
| "전부 분류해" | start | null | null | null | "" |
| "역삼부터 분류해" | priority | 역삼동 | null | null | "" |
| "멈춰" / "다시 시작" | stop / resume | null | null | null | "" |
| (질문 중) "청담동이야" | answer | 청담동 | null | null | SortState.box_id |
| (질문 중) "대치동." | answer (로컬) | 대치동 | null | null | SortState.box_id |
| (질문 중) "역삼으로, 보내요" | answer (로컬) | 역삼동 | null | null | SortState.box_id |
| (질문 중) "보류해" | answer | null | HOLD | null | SortState.box_id |
| "역삼동 지금까지 몇 개야" | query_history | 역삼동 | null | count_by_dong | — (REST) |
| "보류 몇 개야" | query_history | null | null | held_count | — (REST) |
| "몇 개 남았어" | query_history | null | null | remaining_count | — (REST) |
| "대치동을 C 구역으로 바꿔" | update_zone_map | 대치동 | C | null | "" (C 범위) |
| "역삼, 대치, 청담 순서로 실어줘" | palletize (route `[역삼동, 대치동, 청담동]`) | null | null | null | "" |
| "청담 먼저, 그다음 역삼으로 실어" | palletize (route `[청담동, 역삼동]`) | null | null | null | "" |
| "역삼, 역삼 순서로 실어줘" | (거부 — 중복) | | | | 되묻기 |
| "아무거나 해" | (거부) | | | | 되묻기 |

## 발화·중복
- intent_parser 가 `/voss/voice/say` 로 내는 문장(되묻기·준비 중·이력 응답)의 중복 억제는 intent_parser 가 맡는다(MC-025). manager 가 내는 문장은 manager 가 맡는다. voice_listener 의 TIMED_OUT 안내(#40)는 발화당 한 번만 낸다.
- `box_id` 에는 원래 투입 box_id 만 싣는다(회차 없음, PL 결정 #67·#54). 다른 박스에 대한 늦은 답은 box_id 가 달라 manager 가 거른다. **같은 박스를 pause/resume 뒤 다시 물을 때는 앞 질문의 늦은 답이 섞일 수 있다**(#54 최종 정정, SRD v0.4 F-09). 질문 회차·답 수락 창·타이머 재시작은 B 상세로 sort_manager 가 정하고, 회차를 box_id 에 섞지 않는다. intent_parser 는 발화 시점의 SortState(`state`, `box_id`)로 answer 를 만든다.

## 음성 stop 최종 안내 — 인터페이스 변경 제안 (승인 전, `interface` PR)

**PR #176 선택 계약:** `intent_parser` 는 정지 키워드를 LLM·zone_map·다른 발화 대기보다 먼저 판정한다. 기본 `ros` 모드는 `/voss/voice/intent`의 `stop`을 발행한다. Web PC `web_api` 모드의 stop은 ROS `/voss/voice/intent` 발행을 먼저 시도하고 REST `POST /api/commands`도 시도한다. REST 거부·timeout이어도 ROS 시도를 생략하지 않으며, 다른 명령은 기존 단일 경로를 유지한다. 같은 시점에 도착한 stop 서비스 호출은 manager의 진행 중 작업에 합치되, 실패·timeout 뒤 새 stop은 재시도한다. 두 경로가 시간차로 도착하면 gateway의 멱등 stop이 다시 호출될 수 있다. Web PC DDS가 Nodes PC에 연결되지 않으면 ROS 발행만으로 전달을 보장할 수 없다. 현재 `/voss/voice/say`의 "요청을 처리하겠습니다."는 전달 시도에 대한 안내이며 정지 완료 확인이 아니다. sort_manager는 stop 결과를 아직 음성으로 안내하지 않는다(로그만).
**제안:** 접수 시점 안내("정지 요청을 전달했습니다.")는 계속 내지 않고, 최종 안내의 유일한 발행자는
`sort_manager`이며 기존 `/voss/voice/say`와 `speech_out`을 사용한다. Web PC에서 `speech_out`을 실행할 때에는 기존 웹 SSE `state.pending_question`을 받아 ASKING 진입당 한 번 같은 문장을 로컬 `/voss/voice/say`로 전달한다. PC 간 ROS 음성 토픽이 도착하지 않아도 질문을 읽기 위한 경로이며, 로봇 명령이나 새 MQTT 토픽은 만들지 않는다.
새 토픽·메시지 필드는 제안하지 않는다. manager의 stop 작업 토큰으로 음성 요청과
`/voss/robot/stop` 응답을 연결하고, 요청 이후 새 RobotState를 추가 확인한다.
`SortState=PAUSED`와 Command 접수 응답만으로 완료를 판정하지 않는다.

| 확인 조건 | 한 번만 발행할 문장 |
|---|---|
| 해당 stop 작업의 로봇 서비스 성공 **및** 요청 이후 새로 수신한 `RobotState`가 `connected=true`, `state=STOPPED`, `error_code=""` | 정지되었습니다. |
| manager가 stop 명령을 명시적으로 거부하고 로봇 stop 호출이 시작되지 않음 (현재 FSM 에는 없는 경로 — 방어용) | 정지하지 못했습니다. 명령이 거부되었습니다. |
| 해당 작업의 로봇 서비스 부재(manager 내부 `NO_SERVICE`) 또는 명시적 통신 오류(gateway `Trigger.message=DEVICE_ERROR`) | 정지 상태를 확인하지 못했습니다. 로봇 통신 오류입니다. |
| `stop_timeout_s`(3.0 s, sort_manager.yaml) 안에 — gateway `message=TIMEOUT` 포함 — 서비스 응답과 신선한 `STOPPED` 상태를 모두 확인하지 못함, 또는 원인 미분류 실패 | 정지 상태를 확인하지 못했습니다. 로봇 상태를 확인해 주세요. |

manager는 작업별 최종 안내를 최대 한 번만 발행하고 늦은 응답·상태를 버린다.
중복 stop 발화가 진행 중 작업에 겹치면 한 작업으로 묶어 최종 안내를 중복하지
않는 방안은 manager 담당자가 검토한다. `Trigger.success=true`는 move_stop 정상
응답이지 물리적 안전 등급 비상정지의 증거가 아니다. 새 `STOPPED` 상태의 의미와
서비스 응답의 순서는 로봇 담당자가 확인해야 하며, 그 전에는 성공 문장을 내지 않는다.
담당 승인: sort_manager 남현지, RobotState·stop 응답 김학민, 음성 안내 정의석.

## 시험 (VC-EUS-INTENT-01, #54 MC-031)
- 정답 세트 20문장(필수 지시 4유형 × 5)은 시험 전에 `src/voss_voice/test/fixtures/` 에 커밋한다.
- 판정: **전체 20건 중 정답 ≥ 19**. API 오류·timeout 도 분모에 넣고 따로 보고하며, API 성공 건만의 조건부 정확도는 참고로 적는다. 허용 외 입력은 100% 거부.
- **palletize(Sprint 2, S2-T06)** 는 이 20건에 넣지 않고 `src/voss_voice/test/fixtures/palletize_cases.json` 에 따로 둔다(받기 5 + 거부 3 — 중복·미등록·4개). 판정: 8건 전부(받기 5/5, 거부 100%). NFR-03 판정 세트를 바꾸지 않기 위해서다.

## 변경 이력
- 2026-10-08: #124 로컬 단독 동·목적지 답변의 문장부호·띄어쓰기·`보내요` 처리와 ASKING 외 발행 차단을 명시. 토픽·Intent JSON 필드·메시지 스키마 변경 없음.
- 2026-10-05: 초안.
- 2026-10-06: SRD 상호확인 합의 반영 (#18, #52 MC-022·023·024·025, #47 별칭).
  - `type` 에 `query_history` 추가, `query_kind` 필드 추가. 이력 질의는 manager 로 보내지 않고 REST `GET /api/stats` 로 조회.
  - `zone` 에 `HOLD` 추가(answer 전용), 값 enum 대문자 규칙.
  - answer 의 `box_id`(Intent 끝에 추가, voss_msgs.md) — 늦은 답이 다음 질문에 적용되지 않게.
  - 별칭 → 정식 동 이름 변환, 허용 목록은 zone_map 토픽, zone_map 미수신 시 발행 안 함.
  - `update_zone_map` 은 C 선택 범위로 표시.
  - 리뷰 반영(#67): stop 은 로컬 키워드로 즉시 발행(LLM·zone_map 대기 없음), box_id 회차 없음(PL 결정), `count` 현재 미사용.
- 2026-10-07: "같은 박스의 늦은 답은 해가 없다" 문장 철회 — #54 최종 정정대로 pause/resume 뒤 같은 박스 재질문에는 섞일 수 있음, 회차·수락 창은 sort_manager B 상세(SRD v0.4 F-09·TBD-009).
- 2026-10-12: **Sprint 2**(BRD v1.4 10.7·TR-PAL-01, S2-T01 — 제안). `type` 에 `palletize`, `route` 필드(정식 동 이름 배열, 1~3개·중복·미등록 거부, null → `[]`), 발화 예 3개. FastAPI 프롬프트·structured output 스키마는 S2-T06.
- 2026-10-13: (T13 #37) 음성 stop 최종 안내 제안(sort_manager 단일 발행, 새 토픽 없음) — 제안.
- 2026-10-14: #37 리뷰 — 현재 동작과 제안을 구분, 실패 코드 매핑(`NO_SERVICE`·`TIMEOUT`·`DEVICE_ERROR`)·`stop_timeout_s` 명시. voice_listener TIMED_OUT 안내 줄 추가.
