# VOSS SRD v0.2 취합 회신서 — 정의석

**수신:** 정의석 · **취합:** 박병후  
**담당 범위:** 음성·HMI·MQTT·DB·이력 조회  
**대상 기능/노드 후보:** voice_listener, intent_parser, speech_out, hmi_bridge, sort_logger, 웹 HMI/DB  
**양식 버전:** v0.2 r1(독립 재검 반영) · **기준일:** 2026-10-06(한국 시간)

> 작성 원칙: 현재 첨부 문서에서 확인된 값만 `확정/실측`으로 표시하고, 팀 확인이 필요한 값은 `제안/미정`으로 표시한다. 이 회신은 SRD 초안 자체를 직접 수정하지 않고, 박병후 취합자가 TBD와 계약 카드에 반영할 수 있도록 제출하는 자료다.

## 0. 회신 정보·공통 기준

| 항목 | 답변 |
|---|---|
| 작성자·회신일·회신 버전 | 정의석 · 2026-10-06 · 회신 r1 |
| 확인한 코드/문서/장비 버전 | `01_VOSS_SRD_v0.2_초안(1).md`(v0.2 r1), `정의석_프롬프트_claude.ai용.md`, `정의석_CLAUDE.local.md`, `README_프롬프트_사용법.md`, `conveyor_runbook.md`. 프로젝트 문서에 기록된 공용 PC: MSI Katana 17 / i7-13620H / RAM 32 GB / RTX 4060 Laptop VRAM 8 GB / Ubuntu 24.04 / ROS 2 Jazzy / CycloneDDS / Python 3.12 / Docker 29.8 + nvidia-container-toolkit 1.20 / ROS_DOMAIN_ID=30. 실제 코드 커밋·실행 로그는 이번 회신 자료에 첨부되지 않아 미확인. |
| 구현됨/설계만/실측됨/미확인 범위 | **실측됨:** 공용 PC HW/OS/ROS/Docker/NIC 기본 사양(프로젝트 지침의 measurements #5 완료 기록). **설계/계약 후보:** 음성·Intent·MQTT·DB·HMI 경로. **구현·실측 미확인:** wake word, Whisper 20개 전사, intent 20문장, TTS 3초, MQTT 왕복, DB 1건→1행, HMI 1초, 전체 루프. **미정:** 호출어 엔진, Whisper 모델 크기, TTS 엔진, 웹 스택 상세/실행 위치/MQTT JSON 최종본, DB 종류/버전. |
| 함께 확인한 담당자·확인 일시 | 이번 회신은 첨부 문서 기준 단독 작성. 남현지·김학민·박병후의 직접 확인 일시는 아직 없음. 상대 확인 후 확정 필요. |
| 추가 검토가 필요한 상대 | **남현지:** manager/Intent/SortState/SortResult/ZoneMap/command·stats 계약, `box_id`/attempt 의미. **김학민:** 공용 PC 네트워크/CycloneDDS 인터페이스 및 장비 실행환경. **박병후:** SRD TBD 반영, 성능 검증 카드/측정 경계 및 전체 통합 일정. |

- **A: 최초 전체 흐름 필수.** 박스1개 인식→이동 중 픽업→기본 구역 적재→DB 기록·조회→복귀/다음 관측 준비. 필요한 설정·안전·식별·계약 포함.
- **B: 최종 시연 필수.** 음성·HMI·우선/전체·로그 기반 이력·판독 예외·재시도·성능·컨테이너 연결. A보다 늦게 붙여도 선택 기능은 아님.
- **C: 선택.** 자연어 매핑 변경·신규 구역 교시. 이번 회신에서는 **후속 검토**로 둔다.
- 수치 목표는 현재 SRD/개발일정의 목표값이며, 실제 시험 결과와 구분한다.

---

## 1. 담당 요구사항 검토

> 아래의 `수용`은 **요구사항 문장에 동의한다는 의미**이며, 구현/시험 완료를 뜻하지 않는다. 시험이 끝나지 않은 항목은 검증 카드에 `미수행·예정일`을 남겼다.

| 요구사항·단계 / 검증 ID | 검토 답변·검증 카드 연결 |
| --- | --- |
| SYS-FR-014 / A / VT-014 | **수용.** A 최소 흐름에서 `/voss/sort/result` 1건이 `sort_log` 1행으로 저장되고 다시 조회되어야 함. DB 종류·식별키는 TBD-012/TBD-007 확인 필요. → `VC-EUS-DB-01` |
| SYS-FR-015 / B / VT-015 | **수용.** 호출어 엔진은 pending #5로 미정. 공용 PC 내장 마이크 1 m 실측 필요. → `VC-EUS-VOICE-01` |
| SYS-FR-016 / B / VT-016 | **수용.** 로컬 Whisper 사용 방향은 문서화되어 있으나 모델 크기/백엔드는 pending #6 미정. 20개 전사 시험 예정. → `VC-EUS-VOICE-01` |
| SYS-FR-017 / B / VT-017 | **수용 + 계약 수정 제안.** LangChain/OpenAI structured intent + 코드 allow-list 검증. 현재 Intent 후보에 `query_history`가 없어 필수 이력 질의 계약 보완 필요. → `VC-EUS-INTENT-01`, `CHG-EUS-01` |
| SYS-FR-022 / B / VT-022 | **수용.** `/voss/voice/say` → `speech_out`; TTS 엔진은 pending #12 미정. → `VC-EUS-TTS-01` |
| SYS-FR-029 / B / VT-029 | **수용.** 집계 원천은 `sort_log` DB를 source of truth로 제안. 음성/HMI가 같은 기준의 집계를 읽도록 한다. 실제 stats 제공 노드는 남현지와 확인 필요. → `VC-EUS-HMI-01`, `IC-EUS-STATS-01` |
| SYS-FR-030 / B / VT-030 | **수용.** HMI fallback 버튼 명령은 MQTT `voss/command` → hmi_bridge → `/voss/sort/command`으로 제안. command schema/ack는 pending #13. → `VC-EUS-HMI-01`, `IC-EUS-MQTT-01` |
| SYS-FR-031 / B / VT-031 | **수용.** 상태·지시·OCR·로봇·구역별 집계·보류 목록 표시. 데이터 원천은 ROS→MQTT/DB. → `VC-EUS-HMI-01` |
| SYS-FR-032 / B / VT-032 | **수용.** 예정 수량 기본 목표 10, 변경은 HMI 입력. `remaining=max(planned-completed,0)` 제안. completed 정의는 E-05에서 남현지 확인 필요. → `VC-EUS-HMI-01` |
| SYS-IF-004 / A / VT-040 | **수용.** `SortResult`→`sort_log` 1:1 저장을 기본으로 하고, OCR 원문·판정동·confidence·decided_by·zone·result·식별자·시각을 저장. `attempt` 구분은 TBD-007 필요. → `IC-EUS-DB-01`, `VC-EUS-DB-01` |
| SYS-IF-005 / B / VT-041 | **수용 + 계약 수정 제안.** 운전/우선분류/이력질의/예외응답/무효 입력을 명시하고, HMI command와 voice Intent를 동일 canonical command로 매핑해야 함. → `IC-EUS-CMD-01`, `CHG-EUS-01` |
| SYS-IF-006 / B / VT-042 | **수용.** MQTT schema/QoS/retained/command ack를 pending #13에서 확정. 현재 제안은 state/result/command QoS1 non-retained, zone_map QoS1 retained. → `IC-EUS-MQTT-01`, `VC-EUS-HMI-01` |
| SYS-PF-003 / B / VT-047 | **수용(목표값).** 4유형×5문장=20개 중 19개 이상 정답을 목표로 시험. 아직 실측 아님. → `VC-EUS-INTENT-01` |
| SYS-PF-005 / B / VT-049 | **수용(목표값).** 발화 종료→TTS 시작 ≤3초. API 정상/실패를 분리해 기록. → `VC-EUS-TTS-01` |
| SYS-PF-008 / B / VT-052 | **수용(목표값).** manager 상태 이벤트 수신 시각→브라우저 DOM 반영 시각 ≤1초를 제안 측정 경계로 사용. → `VC-EUS-HMI-01` |
| SYS-DT-001 / A / VT-057 | **수용.** MQTT QoS1/ROS 재전달로 중복 가능하므로 idempotent insert가 필요. 최종 unique key는 TBD-007의 box/attempt 규약 후 확정. → `IC-EUS-DB-01`, `VC-EUS-DB-01` |
| SYS-DT-002 / B / VT-058 | **수용.** 저장 실패는 정상 처리와 분리해 오류로 노출하고 처리 수에 반영하지 않음. 재시도 횟수/다음 박스 허용 정책은 미정. → `VC-EUS-DB-01` |
| SYS-DT-003 / B / VT-059 | **수용.** DB container는 host volume으로 보존. 보존 기간·세션 초기화·백업 정책은 미정. → `VC-EUS-DB-01` |
| SYS-CT-006 / B / VT-065 | **수용.** `OPENAI_API_KEY` 및 DB credential은 `.env`/runtime env로만 주입, Git·공유문서 금지. 실제 repo secret scan은 미수행. → `VC-EUS-SEC-01` |

---

## 2. 질문별 회신 — 빈 항목을 채울 자료

### E-05 — 이력·HMI 조회와 남은 수 (B)

- 채울 빈 항목: **TBD-008**
- 함께 확인할 상대: 남현지

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 집계 원천 / B | **제안:** 단일 source of truth는 `sort_log` DB. `sort_logger`가 `/voss/sort/result`를 저장하고, 음성 질의는 `/voss/sort/stats` 경로를 통해 **DB 기반 집계 결과**를 받아야 함. Web HMI 역시 동일 DB를 조회하거나 동일 query service를 사용하여 manager 메모리 통계와 DB가 서로 다른 숫자를 만들지 않도록 함. `/voss/sort/stats` 실제 제공 노드(manager vs logger/query service)는 남현지와 확정 필요. `IC-EUS-STATS-01`, `IC-EUS-DB-01` 참조. |
| 집계 의미 / B | **제안:** `PLACED`=정상/작업자 판정 포함 최종 적재 완료, `HELD`=보류 구역으로 최종 처리, `FAILED`=최종 적재 미완료. `skip`가 별도 결과 enum인지 현재 자료로 확인되지 않아 **미정**. 처리 수는 DB의 **고유 처리 시도(final result)** 기준으로 계산하고 MQTT/ROS 중복 수신은 중복 집계하지 않음. 동일 물리 박스 재투입/attempt 구분은 TBD-007 확정 필요. |
| 남은 수 / B | 예정 수량 기본값 **10(목표/시연 기본)**. HMI에서 `planned_count`를 입력/변경. **제안 계산:** `completed = PLACED + HELD`의 고유 처리 시도 수, `remaining = max(planned_count - completed, 0)`. `FAILED`는 완료 수에서 제외하여 재시도/재투입 가능하게 하는 안을 제안하되 남현지 확인 필요. 중복 결과는 unique key/idempotency로 제외. |
| 조회·표시 / B | **제안 질의:** `query_history` → `query_kind=count_by_dong|held_count|remaining_count`, `dong` 선택. 음성: "역삼동은 지금까지 N개입니다"/"보류는 N개입니다"/"남은 수량은 N개입니다". HMI: REST/내부 query 또는 MQTT 연동 backend가 같은 DB 집계 응답을 표시. 예시 응답: `{"query_kind":"count_by_dong","dong":"역삼동","count":3,"as_of":"2026-10-06T15:00:00+09:00"}`. 이 JSON은 **제안 스키마**이며 `CHG-EUS-01` 팀 확인 필요. |
| 일치 검증 / B | 동일 `as_of` 또는 동일 DB commit 이후 음성 질의 결과와 HMI 수치를 비교. DB container 재기동 후에도 같은 `sort_log`를 읽어 동일 집계가 나오는지 확인. HMI/음성에서 자체 카운트하지 않고 DB 결과만 표시. `VC-EUS-HMI-01`, `VC-EUS-DB-01`. |

A 상태·남은 항목: **해당 없음 — 이력/HMI 집계는 B 범위. 단 A의 DB 1건 저장·조회는 E-04에서 처리.**  
B 상태·남은 항목: **미정 — 집계 원천/계산식 제안 완료, `/voss/sort/stats` 제공 주체·FAILED 포함 여부·box/attempt 규약은 남현지 확인 필요.**  
C 선택 상태: **해당 없음**  
근거/파일/실측: `정의석_프롬프트_claude.ai용.md`, `정의석_CLAUDE.local.md`, SRD TBD-008/IC-STATS-01/IC-DB-01. **실측 미수행.**  
미정 담당·결정 예정일: **정의석+남현지 / 2026-10-08까지 인터페이스 계약 확인 제안**

### E-01 — intent·명령·응답 스키마 (B)

- 채울 빈 항목: **TBD-009**
- 함께 확인할 상대: 남현지

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 필수 intent 유형 / B | **현재 문서 후보:** `start`, `stop`, `resume`, `priority`, `answer`, `update_zone_map(C)` + 필드 `dong`, `zone`, `count`, `raw_text`. **필수 보완 제안:** `query_history` 추가. `start`는 전체 분류/운전 시작, `priority(dong)`는 특정 동 우선, `answer`는 OCR 예외 후보/보류 응답, `query_history`는 동별/보류/남은 수 질의. `update_zone_map`은 C 선택으로 B 완료 선행조건 아님. `IC-EUS-CMD-01`, `CHG-EUS-01`. |
| 일관된 명령 / B | 음성은 `Intent`를 canonical command로 생성하고, HMI는 MQTT `voss/command` JSON을 hmi_bridge가 같은 canonical type/args로 `/voss/sort/command`에 변환. 즉 같은 동작은 source가 VOICE/HMI여도 manager가 받는 type/args 의미가 동일해야 함. |
| 인자·허용값 / B | **제안:** 해당 없는 string은 `""`, count 미사용은 `0`; `null`은 ROS fixed message에서 사용하지 않음. `dong` 허용값은 현재 zone_map에 등록된 동(기본 역삼동/대치동/청담동), `zone`은 현재 zone_map의 A/B/C와 예외 답변의 HOLD를 허용하도록 팀 확인 필요. `priority`는 dong 필수, `answer`는 후보 dong 또는 HOLD, `query_history`는 `query_kind`와 선택 dong 필요. 허용 외 값/파싱 실패는 실행하지 않고 `/voss/voice/say`로 되묻기. |
| 접수/완료/실패 / B | **제안:** HMI command JSON에 `command_id`(UUID 또는 단조 증가 ID)를 포함. hmi_bridge는 `/voss/sort/command` 서비스의 접수 결과를 command_id와 함께 HMI로 회신. QoS1 재전달 시 같은 command_id는 재실행하지 않음. 실제 작업 완료는 SortState/SortResult 또는 manager 완료 이벤트로 별도 표시. service 응답 목표 ≤200 ms는 manager 책임으로 문서에 기록되어 있음. timeout/취소/실패 원인 enum은 manager와 확정 필요. |
| JSON 예시 / B | 아래 예시는 **제안 스키마**. `query_history`/`query_kind`/`command_id`는 기존 후보에 없는 보완 항목이므로 `CHG-EUS-01` 승인 필요. |

제안 JSON 예시:

```json
{"command_id":"cmd-001","type":"start","args":{},"raw_text":"작업 시작"}
{"command_id":"cmd-002","type":"stop","args":{},"raw_text":"멈춰"}
{"command_id":"cmd-003","type":"resume","args":{},"raw_text":"계속해"}
{"command_id":"cmd-004","type":"priority","args":{"dong":"역삼동"},"raw_text":"역삼동부터 분류해"}
{"command_id":"cmd-005","type":"start","args":{"mode":"all"},"raw_text":"전체 분류 시작"}
{"command_id":"cmd-006","type":"query_history","args":{"query_kind":"count_by_dong","dong":"역삼동"},"raw_text":"역삼동 몇 개야"}
{"command_id":"cmd-007","type":"query_history","args":{"query_kind":"held_count"},"raw_text":"보류 몇 개야"}
{"command_id":"cmd-008","type":"query_history","args":{"query_kind":"remaining_count"},"raw_text":"몇 개 남았어"}
{"command_id":"cmd-009","type":"answer","args":{"dong":"대치동"},"raw_text":"대치동"}
{"command_id":"cmd-010","type":"answer","args":{"zone":"HOLD"},"raw_text":"보류"}
{"command_id":"cmd-011","type":"UNKNOWN","args":{},"raw_text":"아무거나 해"}
```

A 상태·남은 항목: **해당 없음 — 본 질문은 B 음성/HMI 명령 계약.**  
B 상태·남은 항목: **미정 — 현재 6종 후보는 문서화되어 있으나 필수 이력 질의가 빠져 있어 `query_history` 계약 수정 필요. command_id/ack/timeout enum도 남현지 확인 필요.**  
C 선택 상태: **후속 검토 — `update_zone_map`은 선택 C로 유지. 신규 구역 교시는 이번 B 계약에서 제외.**  
근거/파일/실측: `정의석_프롬프트_claude.ai용.md`, `정의석_CLAUDE.local.md`, SRD IC-CMD-01/IC-STATS-01. **실측 미수행.**  
미정 담당·결정 예정일: **정의석(제안 작성)+남현지(consumer 확인) / 2026-10-08까지**

### E-02 — 음성 엔진·응답·시험 (B)

- 채울 빈 항목: **TBD-010**
- 함께 확인할 상대: 남현지

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 엔진·실행 위치 / B | **확인된 방향:** `voice_listener`에서 호출어 검출 + **로컬 Whisper STT**, `intent_parser`에서 **LangChain + OpenAI**, `speech_out`에서 TTS. 개발은 개인 PC, 최종 마이크/VRAM 동거 확인은 공용 PC. **미정:** 호출어 엔진 pending #5(10/06), Whisper 모델 크기/구현 backend pending #6(10/06), OpenAI 구체 모델명, TTS 엔진 pending #12(10/08). 공용 PC VRAM 8 GB를 YOLO·PaddleOCR·Whisper가 공유하므로 최종 Whisper 크기는 비전 VRAM 실측 후 결정. |
| 입출력 / B | 호출어 감지→녹음 시작→발화 종료/최대 녹음시간 조건(값 미정)→STT 결과를 `/voss/voice/transcript`(String) 발행→intent_parser가 구조화 Intent 생성/allow-list 검증→`/voss/voice/intent` 발행. manager의 `/voss/voice/say`(String) → speech_out TTS. **폴백:** 터미널/HMI 텍스트 입력을 transcript와 동일 경로로 넣어 STT 없이 intent_parser를 시험. TTS 재생 중 동시 음성 입력 처리(half-duplex/echo cancel)는 자료에 없어 미정. |
| 지연·장애 / B | 목표: 발화 종료→TTS 시작 ≤3초. STT/OpenAI/TTS 각 구간 시간을 따로 기록. 네트워크/API 오류 또는 structured output 파싱 실패/허용 외 값이면 실행 금지 + 작업자에게 되묻기/HMI 폴백. OpenAI 인터넷은 Wi-Fi 사용, 공용 PC 유선 gateway 설정 때문에 인터넷 불안정 가능성이 문서화되어 있음. timeout 값/재시도 횟수는 미정. |
| 시험 자료 / B | T08: 녹음 20개, 전사 정확 ≥90% 완료 기준. T09/VT-047: 필수 지시 4유형×5문장=20개 중 ≥19개(95%). 호출어 포함/미포함 세트 및 1 m 내장 마이크 시험은 공용 PC에서 수행. T10/VT-049: 발화 종료 timestamp와 TTS 시작 timestamp를 기록. 현재 실측 결과는 첨부되지 않음. `VC-EUS-VOICE-01`, `VC-EUS-INTENT-01`, `VC-EUS-TTS-01`. |

A 상태·남은 항목: **해당 없음 — 음성 완성은 B. A는 모의 유효 시작 입력 허용.**  
B 상태·남은 항목: **미정 — 구성 방향/시험 기준은 있음, 엔진·모델 선택과 실측 미완료.**  
C 선택 상태: **해당 없음**  
근거/파일/실측: T08 #17, T09 #18, T10 #19 일정/완료 기준. 공용 PC 사양은 문서상 실측 완료; 음성 성능은 미수행.  
미정 담당·결정 예정일: **정의석 / 호출어·Whisper 2026-10-06, TTS 2026-10-08**

### E-03 — HMI·MQTT·명령 회신 (B)

- 채울 빈 항목: **TBD-011**
- 함께 확인할 상대: 남현지·김학민

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| HMI 기능·스택 / B | **기능은 수용:** 운전 start/stop/resume, 우선/전체 분류, 예정 수량 입력, 운전 상태, 현재 지시, OCR 결과, 로봇 상태, 구역별 집계, 보류 목록. **스택은 pending #13로 미정. 제안:** 전 프로젝트 재사용 범위를 활용해 **React + TypeScript frontend + Spring Boot backend + Mosquitto** 최소 구성. 브라우저가 ROS에 직접 연결하지 않고 backend가 MQTT/DB를 구독·조회. FastAPI 분리는 현재 VOSS 문서 계약에 없으므로 이번 SRD 회신에는 넣지 않음. 실행 위치는 개인 PC 개발 후 공용 PC/컨테이너 여부를 10/08 결정. |
| 항목별 원천 / B | `/voss/sort/state`(≥2 Hz)→운전 상태/현재 지시, `/voss/sort/result`(박스당 1건)→최근 결과/OCR/판정/구역, `/voss/sort/zone_map`(reliable+transient_local)→현재 규칙, DB `sort_log`→집계/보류/이력, 로봇 상태는 manager가 SortState에 포함할지 별도 원천인지 남현지 확인 필요. 값 미수신 시 `UNKNOWN/연결 대기` 표시를 제안하며 0/정상으로 위장하지 않음. |
| MQTT 계약 / B | ROS→MQTT: `voss/state`, `voss/result`, `voss/zone_map`; Web→ROS: `voss/command`. **제안 QoS:** state/result/command MQTT QoS1 non-retained, zone_map QoS1 retained(ROS transient_local 대응). Web backend는 재연결 시 retained zone_map과 최신 state를 복구. 집계는 DB 조회를 source of truth로 사용하고 MQTT에 별도 stats topic을 만들지는 팀 결정을 따름. command 결과는 `voss/command_result` 신설 또는 backend의 service response 응답으로 제공하는 두 안 중 pending #13에서 확정. `IC-EUS-MQTT-01`. |
| 명령 회신·중복 / B | MQTT QoS1의 중복 가능성을 고려해 모든 command에 `command_id`를 제안. hmi_bridge는 같은 command_id 재수신 시 `/voss/sort/command`를 재호출하지 않고 기존 결과를 반환. 접수(service response)와 실제 작업 완료(SortState/SortResult)는 구분 표시. broker/backend 연결 끊김 시 명령 버튼 비활성화 + `DISCONNECTED` 표시 제안; 재접속 후 retained zone_map/DB snapshot 재동기화. |
| 목표 수용 / B | **≤1초 목표 수용(현재는 목표, 실측 아님).** 측정 시작=`/voss/sort/state` 또는 result를 hmi_bridge가 수신한 monotonic timestamp, 종료=브라우저가 해당 값으로 DOM을 갱신한 timestamp. 20회 이상 이벤트에서 각 지연과 최대값/분포를 기록하도록 제안. `VC-EUS-HMI-01`. |

A 상태·남은 항목: **해당 없음 — HMI 전체 기능은 B.**  
B 상태·남은 항목: **미정 — 기능/ROS-MQTT 방향은 문서화됨; 웹 스택·실행 위치·MQTT JSON/QoS·command ack는 pending #13 확정 필요.**  
C 선택 상태: **후속 검토 — update_zone_map UI는 C 기능 채택 시만 활성화.**  
근거/파일/실측: T11 #20(10/08~10), T13 #22(10/10~13), `정의석_프롬프트_claude.ai용.md`/`CLAUDE.local.md`. 실측 미수행.  
미정 담당·결정 예정일: **정의석+남현지 / pending #13, 2026-10-08**; 네트워크 연결 조건은 김학민 확인 필요.

### E-04 — DB·로그·보존·저장 오류 (A)

- 채울 빈 항목: **TBD-012**
- 함께 확인할 상대: 남현지

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| DB 선택·스키마 / A/B | **DB 종류는 pending #14로 10/09 결정 예정. 제안:** 전 프로젝트 재사용 경험과 집계/이력 요구를 고려해 **PostgreSQL**. 버전은 현재 자료로 확정하지 않음. container + host volume 사용. `sort_log` 제안 필드: `box_id`, `track_id`, `started_at`, `finished_at`, `ocr_text`, `region`, `confidence`, `second_region`, `decided_by(AUTO/OPERATOR/TIMEOUT)`, `zone`, `result(PLACED/HELD/FAILED)`, `reason_code`, `rule_version`, `retries`. 물리 박스/attempt/재투입 구분에 필요한 `attempt_id`/`session_id`는 TBD-007과 함께 확인 후 추가 제안. index는 `finished_at`, `region`, `zone`, `result` 제안. |
| 기록 보장 / A/B | `/voss/sort/result` 1건을 sort_logger가 transaction으로 1행 저장하고 **commit 성공 시에만 저장 성공**으로 본다. ROS/MQTT 중복 결과는 idempotency key로 중복 insert 방지. 최종 key는 TBD-007 후 결정; 제안은 `attempt_id` 또는 “box_id를 처리 시도마다 유일하게 발급” 중 하나. 재투입은 새 attempt로 기록하되 동일 물리 박스 연결 방법은 남현지 확인 필요. 업무 결과(PLACED/HELD/FAILED)와 저장 상태(DB_OK/DB_ERROR)는 분리. |
| 조회 계약 / A/B | **제안:** DB read path는 sort_logger/query service와 Web backend가 read-only로 사용. 필터: session/time range/dong/zone/result. 집계 응답은 `count_by_dong`, `held_count`, `remaining_count` 최소 지원. 음성의 `/voss/sort/stats`와 HMI가 같은 SQL/기준을 사용. DB credential은 writer/read-only 계정 분리 권장(구현 방식은 pending #14). |
| 오류·복구 / B | **미정 + 제안:** 저장 실패 시 해당 결과를 처리 수에 포함하지 않고 ERROR를 terminal/HMI에 표시. 재시도 횟수/backoff와 “DB down인데 다음 박스를 계속 받을지”는 시스템 정책 영향이 커서 남현지/박병후 결정 필요. 제안 기본은 A 통합 단계에서는 DB commit/조회 실패를 **전체 흐름 미완료**로 처리. 임시 메모리 queue 사용 여부는 B에서 결정. |
| 보존 / B | container DB data를 host volume에 마운트해 container 재기동 후 보존. **보존 기간, 세션 구분/초기화, CSV export/backup 주기와 경로는 미정.** 시연 전 reset 절차와 시연 후 보존 여부를 팀이 확정해야 함. |
| 첫 흐름 최소 연결 / A | manager가 `/voss/sort/result` 1건 발행 → sort_logger 수신 → DB INSERT commit → 동일 `box_id/attempt` SELECT 조회 → 터미널 또는 최소 query 결과로 저장 행 확인. 이 4단계가 성공해야 A의 DB 부분 완료. T12 정식 구현 전에는 mock SortResult를 사용 가능하나 **메모리 출력만으로 완료 판정하지 않음.** `VC-EUS-DB-01`. |

제안 DB 행 예시(타입은 DB 선택 후 확정):

```json
{
  "box_id": "box-0001",
  "track_id": "track-17",
  "started_at": "2026-10-06T14:01:10+09:00",
  "finished_at": "2026-10-06T14:01:27+09:00",
  "ocr_text": "역삼동",
  "region": "역삼동",
  "confidence": 0.96,
  "second_region": "대치동",
  "decided_by": "AUTO",
  "zone": "A",
  "result": "PLACED",
  "reason_code": "",
  "rule_version": "v1",
  "retries": 0
}
```

A 상태·남은 항목: **미정 — 결과1건→DB1행→조회 최소 계약 제안 완료. DB 종류, unique key, box/attempt 정책, 실제 코드/DB 시험은 미완료.**  
B 상태·남은 항목: **미정 — 장애복구·보존기간·session/reset/export 정책 필요.**  
C 선택 상태: **해당 없음**  
근거/파일/실측: T12 #21(10/09~11, 결과1건→DB1행), SRD IC-RESULT-01/IC-DB-01. 현재 DB 실측 없음.  
미정 담당·결정 예정일: **정의석 / DB 종류 pending #14 2026-10-09; box/attempt는 남현지와 2026-10-08까지 확인 제안**

### E-06 — PC·GPU·소프트웨어 자원 (A)

- 채울 빈 항목: **TBD-026**
- 함께 확인할 상대: 김학민·남현지

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 실제 PC / A | **문서상 실측 완료:** 공용 PC MSI Katana 17, Intel i7-13620H, RAM 32 GB, RTX 4060 Laptop VRAM 8 GB, NVIDIA driver 595.91, CUDA runtime 표기 13.2(호스트 nvcc 없음), Ubuntu 24.04, ROS 2 Jazzy, CycloneDDS, Python 3.12, Docker 29.8 + nvidia-container-toolkit 1.20, ROS_DOMAIN_ID=30. NIC: 유선 192.168.1.10/24(로봇 192.168.1.100), 인터넷 Wi‑Fi. 현재 CycloneDDS가 lo만 사용해 개인 PC에서 공용 PC 토픽이 보이지 않는 이슈가 문서화됨(김학민이 wlo1 추가 예정). Voice는 공용 PC 내장 마이크/스피커 사용 예정. USB별 장치 inventory는 이번 자료에서 미확인. |
| 동시 부하 / B | **미정.** RTX 4060 Laptop VRAM 8 GB를 YOLO·PaddleOCR·Whisper가 공유. Whisper 최종 모델은 비전 담당의 VRAM 사용량과 동시 실행 실측 후 결정. DB/MQTT/Web은 CPU/RAM 중심으로 분리하고 GPU를 사용하지 않는 구성을 제안. 동시 부하 CPU/RAM/VRAM 수치는 아직 없음. |
| 자원·배포 / A/B | 현재 문서 후보: ROS host에 voice_listener/intent_parser/speech_out/hmi_bridge/sort_logger, Mosquitto host 1883, DB/Web은 container 후보. **제안:** Web=React+Spring Boot container, DB=PostgreSQL container, Mosquitto는 host 또는 container 중 pending #13에서 결정. ROS_DOMAIN_ID=30과 DDS 통신이 필요한 프로세스는 host/host-network 조건 확인. 비전 GPU와 Whisper GPU 동거를 제외하면 web/DB는 GPU 충돌 없음. |
| 외부 의존 / B | OpenAI API는 Wi‑Fi 인터넷 필요. `OPENAI_API_KEY`는 환경 변수/.env로만 주입하고 Git/공유문서 금지. DB password/MQTT credential도 같은 원칙을 적용. 유선 gateway 설정 때문에 인터넷 불안정 가능성이 있어 API timeout 시 HMI/텍스트 폴백 필요. |

A 상태·남은 항목: **미정 — 공용 PC 기본 사양은 실측 완료이나 USB inventory, CycloneDDS NIC 수정 완료 여부, 실제 배포 위치는 미확정.**  
B 상태·남은 항목: **미정 — 동시 부하/VRAM, Whisper 모델, Web/DB/MQTT 배치, 외부 API 장애 시험 필요.**  
C 선택 상태: **해당 없음**  
근거/파일/실측: `정의석_프롬프트_claude.ai용.md`, `정의석_CLAUDE.local.md`의 공용 PC measurements #5 완료 기록. 실측 원본 로그 경로는 이번 첨부에 없음.  
미정 담당·결정 예정일: **정의석(음성/Web/DB), 남현지(비전 VRAM), 김학민(DDS/NIC) / 2026-10-08~10**

---

## 3. 인터페이스 카드 — 실제 연결별 회신

### 3.1 IC 커버리지

| 관련 IC-ID / 연결 | 역할·공통 카드 주 작성자 | 카드 ID / 상태 |
| --- | --- | --- |
| IC-CMD-01 / 음성/HMI→manager | 주 작성 / 정의석 | `IC-EUS-CMD-01` / **제안, 남현지 확인 필요** |
| IC-VOICE-01 / manager→speech_out | 주 작성 / 정의석 | `IC-EUS-VOICE-01` / **제안, TTS 엔진 미정** |
| IC-STATE-01 / manager→HMI | 상대 확인 / 남현지 | `IC-NHJ-STATE-01` 공통 카드 대기 / 정의석 요구: ≥2 Hz, HMI≤1초 검증 |
| IC-RESULT-01 / manager→logger/HMI | 상대 확인 / 남현지 | `IC-NHJ-RESULT-01` 공통 카드 대기 / 정의석 요구: 박스당 final 1건, 식별키·timestamp 필요 |
| IC-CONFIG-01 / 설정→각 소비자 | 상대 확인 / 남현지 | `IC-NHJ-CONFIG-01` 공통 카드 대기 / 정의석 요구: zone_map reliable+transient_local, bridge는 retained publish |
| IC-STATS-01 / 조회 기능→음성/HMI | 주 작성 / 정의석 | `IC-EUS-STATS-01` / **제안, 제공 노드 확인 필요** |
| IC-MQTT-01 / bridge↔웹 | 주 작성 / 정의석 | `IC-EUS-MQTT-01` / **제안, pending #13** |
| IC-DB-01 / logger↔DB/조회 | 주 작성 / 정의석 | `IC-EUS-DB-01` / **제안, pending #14/TBD-007** |
| IC-OPTION-01 / 명령↔설정/로봇 | 상대 확인 / 남현지 | **C 선택 후속 검토. 현재 상세 카드 미작성** |

### 3.2 카드 `IC-EUS-CMD-01` — IC-CMD-01 / E-01 / TBD-009·011

| 항목 | 답변 |
|---|---|
| 계약 상태·버전 / 기존 유지·변경·신규 | **기존 후보 유지 + 필수 보완 제안.** `/voss/voice/intent`와 `/voss/sort/command` 경로 유지, `query_history`/command_id/ack 규약 추가 제안. |
| 생산자·제공자 → 소비자·호출자 / 담당자 | voice_listener/intent_parser(정의석) → sort_manager(남현지). Web HMI → MQTT `voss/command` → hmi_bridge(정의석) → `/voss/sort/command`(남현지). |
| ROS topic/service/action·MQTT·DB/API 이름 / 실제 타입 | `/voss/voice/transcript` `std_msgs/String`; `/voss/voice/intent` `voss_msgs/Intent`; `/voss/sort/command` service 타입은 첨부자료에서 미확인; MQTT `voss/command` JSON. |
| 입력·출력 필드 / 필수·선택 / enum·범위 / 기본값 | 현재 Intent 후보: `type,dong,zone,count,raw_text`; type=`start|stop|resume|priority|answer|update_zone_map`. **추가 제안:** `query_history`, `query_kind`; 예외 answer 시 HOLD 표현 규칙. 해당 없는 string=`""`, count=`0` 제안. |
| 식별자·시각·단위 | HMI command에 `command_id` + `sent_at` 제안. Voice Intent의 command_id/stamp 필드는 현재 자료에 없어 **추가 여부 미정**. 물리 단위 없음. |
| 발행/호출 조건·주기 / QoS | Voice Intent는 유효 발화 1건당 1회. 프로젝트 PR 체크 기준상 voice는 reliable depth 10. HMI MQTT command는 event 기반, QoS1/non-retained 제안. |
| 접수/완료/실패 의미 / timeout·retry·cancel | `/voss/sort/command` service response=접수/거부, 실제 작업 완료=SortState/SortResult. service 응답 목표 ≤200 ms는 manager 책임. invalid intent는 실행하지 않고 `/voss/voice/say`로 되묻기. timeout/cancel enum은 남현지 확인 필요. |
| 중복·순서역전·오래된 데이터·재접속 처리 | MQTT command는 `command_id` idempotency 제안. 오래된 sent_at 거부 window는 미정. reconnect 후 사용자가 재전송하거나 backend가 ack 상태 표시. |
| 설정·외부 의존 / 준비 조건 / 실행 위치 | OpenAI key/runtime env, zone_map allow-list. intent_parser는 개인 PC→공용 PC host. HMI bridge는 host 후보. |
| 송수신 데이터 예시 | E-01 JSON 예시 참조. |
| 상대에게 필요한 변경 / 상대 확인자·일시 / 미합의 내용 | 남현지: `query_history`, query_kind/HOLD 표현, command service arg/response, command_id 수용 여부 확인. 확인 일시 미정. |
| A/B/C 상태 | A 해당 없음 / B 제안 완료·상대확인 필요 / C update_zone_map 후속 검토. |
| 관련 저장소 문서·메시지·코드 / 변경 영향 | `docs/interfaces/intent_json.md`, `topics.md`, `voss_msgs.md`, `mqtt.md` 변경 가능. 승인 시 interface 라벨+남현지 리뷰 필요. |

### 3.3 카드 `IC-EUS-VOICE-01` — IC-VOICE-01 / E-02 / TBD-010

| 항목 | 답변 |
|---|---|
| 계약 상태 | 기존 후보 유지. TTS 엔진/동시 입력 정책 미정. |
| 생산자→소비자 | sort_manager(남현지) → `/voss/voice/say` → speech_out(정의석) → 작업자. |
| 이름 / 실제 타입 | `/voss/voice/say`; `std_msgs/String`(첨부 문서 명시). |
| 필드/enum | String text. 별도 message_id/severity는 현재 자료에 없음. |
| 식별자·시각·단위 | message_id/timestamp 없음. 지연 시험은 subscriber 수신 monotonic time과 TTS audio start time을 별도 측정 로그에 기록. |
| QoS/주기 | 이벤트 발생 시 1회, reliable depth 10 제안/프로젝트 체크 기준. |
| 성공/실패 | 성공=TTS 재생 시작/완료. 엔진 실패 시 HMI/terminal text 표시 유지. retry/timeout 값 미정. |
| 중복 처리 | 동일 문구 중복 발행 방지는 upstream manager 책임으로 제안. speech_out 자체 dedupe 여부 미정. |
| 외부 의존 | TTS 엔진 pending #12. 로컬 엔진이면 네트워크 없음; 외부 API면 Wi‑Fi 필요. |
| 데이터 예시 | `data: "역삼동 3개입니다."` |
| 상대 확인 | 남현지: say 발행 시점(접수/완료/예외질문), 중복 정책 확인 필요. |
| A/B/C | A 해당 없음 / B 미정(엔진·시험 필요) / C 해당 없음. |
| 관련 문서 영향 | `docs/interfaces/topics.md`, speech_out package docs, pending #12/ADR. |

### 3.4 카드 `IC-EUS-STATS-01` — IC-STATS-01 / E-05 / TBD-008

| 항목 | 답변 |
|---|---|
| 계약 상태 | **신규 상세 제안**, 기존 `/voss/sort/stats` 후보 유지. |
| 생산자→소비자 | DB-backed stats provider(제공 노드 미정) → sort_manager/voice + Web backend. |
| 이름 / 타입 | `/voss/sort/stats` service 후보. 정확한 custom srv 타입은 첨부자료에서 미확인. |
| 입력·출력 | request 제안: `query_kind=count_by_dong|held_count|remaining_count`, optional `dong`, optional `session_id`; response: `success,count,as_of,error_code`. |
| 식별자·시각 | `as_of`를 DB 조회 완료 시각으로 반환 제안. |
| 호출 조건 | 사용자 이력 질의/HMI snapshot 요청 시. 지속 polling 대신 HMI는 result event 후 refresh 또는 일정 간격 query. |
| 실패 의미 | DB unavailable/invalid query/unknown dong을 구분하여 success=false. timeout 값 미정. |
| 중복·순서 | read-only query라 중복 호출은 데이터 손상 없음. `as_of`로 최신성 표시. |
| 준비 조건 | DB가 source of truth이고 `sort_logger` commit 완료. |
| 예시 | `{"query_kind":"count_by_dong","dong":"역삼동"} -> {"success":true,"count":3,"as_of":"..."}` |
| 상대 확인 | 남현지: service 제공 노드, request/response custom srv, FAILED/HELD 집계 규칙. |
| 상태 | B 제안 / A 해당 없음 / C 해당 없음. |
| 관련 문서 | `docs/interfaces/topics.md` 또는 service 계약 문서, DB schema, TBD-008. |

### 3.5 카드 `IC-EUS-MQTT-01` — IC-MQTT-01 / E-03 / TBD-011

| 항목 | 답변 |
|---|---|
| 계약 상태 | 기존 topic 이름 유지, JSON/QoS/ack 상세는 **제안**. pending #13에서 확정. |
| 생산자→소비자 | hmi_bridge(ROS subscriber) ↔ Mosquitto ↔ Web backend/HMI. |
| 이름 | ROS→MQTT: `voss/state`, `voss/result`, `voss/zone_map`; Web→ROS: `voss/command`; **제안:** command ack는 `voss/command_result` 또는 backend HTTP response 중 택1. |
| 필드 | state/result/zone_map은 ROS message의 필요한 필드를 JSON key로 1:1 직렬화. command는 `command_id,type,args,sent_at`. 최종 schema는 mqtt.md에서 확정. |
| 식별자·시각 | result는 box/attempt 식별자 포함 필요. command는 command_id. 모든 timestamp는 ISO-8601(+09:00) 또는 epoch 중 한 규칙으로 통일 필요(팀 결정). |
| 주기/QoS/retained | `/voss/sort/state` ≥2 Hz 수신. MQTT **제안:** state QoS1 retain=false, result QoS1 retain=false, zone_map QoS1 retain=true, command QoS1 retain=false. |
| 성공/실패/timeout | command broker publish 성공 ≠ manager 접수. service response를 ack로 표시. 실제 완료는 state/result. broker disconnect/command timeout은 별도 UI 오류. 값 미정. |
| 중복/재접속 | command_id로 QoS1 duplicate dedupe. zone_map retained로 재접속 복구. 최신 state는 reconnect 후 bridge/backend snapshot 요청 또는 다음 2 Hz state에서 복구. |
| 실행 위치 | Mosquitto host:1883가 문서 후보. web/backend container 여부 pending #13. |
| 예시 | `{"command_id":"cmd-004","type":"priority","args":{"dong":"역삼동"},"sent_at":"2026-10-06T15:00:00+09:00"}` |
| 상대 확인 | 남현지: command service schema/SortState/SortResult/ZoneMap 필드. 김학민: PC network/port/broker 접근. |
| 상태 | B 제안/미정 / A 해당 없음 / C update_zone_map 후속. |
| 관련 문서 | `docs/interfaces/mqtt.md`, topics/voss_msgs, pending #13, ADR. |

### 3.6 카드 `IC-EUS-DB-01` — IC-DB-01 / E-04·E-05 / TBD-008·012

| 항목 | 답변 |
|---|---|
| 계약 상태 | DB 종류/버전은 미정; PostgreSQL 제안. schema는 기존 후보 기반 제안. |
| 생산자→소비자 | `/voss/sort/result` → sort_logger → DB `sort_log`; query service/Web backend → DB read. |
| 이름 / 타입 | DB `sort_log`. DB driver/ORM/API는 web stack 결정 후 확정. |
| 필드 | box_id, track_id, started_at, finished_at, ocr_text, region, confidence, second_region, decided_by, zone, result, reason_code, rule_version, retries. attempt/session 필드는 TBD-007 후 추가 제안. |
| 식별자·시각·단위 | 중복 방지 key는 box/attempt 규약 확정 후 결정. started_at/finished_at은 timezone-aware timestamp 권장. confidence 0~1, retries 정수. |
| 기록 조건 | final SortResult 1건당 transaction 1회. commit 성공 후 저장 성공. |
| 실패/timeout/retry | DB 실패 시 DB_ERROR로 표시하고 집계 제외. 재시도 횟수/버퍼/다음 박스 허용은 미정. |
| 중복/순서/재기동 | unique/idempotency key로 중복 차단. host volume로 재기동 후 보존. out-of-order final result 정책은 manager/box attempt 규약 확인 필요. |
| 실행 위치 | DB container + host volume 후보. sort_logger host. Web backend read-only account 제안. |
| 예시 | E-04 DB 행 예시 참조. |
| 상대 확인 | 남현지: SortResult 필드, box/attempt, final 이벤트 조건. 박병후: A 흐름에서 DB 실패시 완료 판정. |
| 상태 | A 최소 계약 제안/미구현, B 장애·보존 정책 미정, C 해당 없음. |
| 관련 문서 | DB schema/migration, `docs/interfaces`, pending #14, TBD-007/008/012. |

---

## 4. 요구사항·성능 검증 카드

> 아래 카드는 **시험 계획**이다. 현재 첨부자료에 결과/로그가 없으므로 완료로 쓰지 않는다.

### `VC-EUS-VOICE-01` — 호출어/STT

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-FR-015/VT-015, SYS-FR-016/VT-016, E-02/TBD-010 |
| 확인 동작·목표 | 호출어 검출 후 녹음 시작, 한국어 STT. T08 완료 기준: 녹음 20개 전사 ≥90%. |
| 방법 | 공용 PC 실제 내장 마이크 실기 + 개인 PC 녹음파일 반복 시험. |
| 조건/환경 | 개인 PC 및 공용 PC; 공용 PC 1 m 마이크 조건, 배경 소음 조건을 기록. Whisper 모델명/버전도 증거에 남김. |
| 측정점·단위 | STT accuracy = 정답 전사 일치 건수/20. 호출어는 포함/미포함 각각 성공/오탐 건수. |
| 횟수/분모 | STT 20개. 호출어 횟수는 pending #5 시험안에서 확정. |
| 합격 기준 | STT ≥90%; 호출어 합격 기준은 SRD/결정 항목 확인 후 기입. |
| 결과/판정 | **미수행.** T08 일정 10/06~07, 담당 정의석. |
| 증거 | 예정: 녹음 목록/정답표/실행 로그/측정표. 실제 경로는 시험 후 기입. |
| 미달 시 대안 | Whisper 모델 크기/threshold 조정, 텍스트 입력 폴백. 최종 모델은 공용 PC VRAM 8 GB 동거 조건 재검. |

### `VC-EUS-INTENT-01` — intent 정확도/허용 목록

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-FR-017/VT-017, SYS-PF-003/VT-047, SYS-IF-005/VT-041, E-01/TBD-009 |
| 목표 | 필수 4유형×5문장=20개 중 ≥19개 정확; schema/allow-list 위반은 실행 금지. |
| 방법 | mock transcript → intent_parser 자동 시험(pytest 권장). OpenAI 응답 JSON과 최종 Intent를 비교. |
| 조건 | 동일 prompt/model/version, temperature 등 설정 기록. 정답 세트는 팀 확인 후 고정. |
| 측정점 | input transcript → validated Intent JSON. 정확도=완전 일치 정답/20. |
| 횟수 | 20문장. API 실패는 정확도 분모와 별도로 failure count 보고. |
| 합격 | ≥19/20 + 허용 외 값/파싱 실패 100% 거부. |
| 결과 | **미수행.** T09 10/06~08, 담당 정의석. |
| 증거 | 예정: test fixture, pytest report, API failure log(키 제외). |
| 미달 시 | prompt/schema 개선, few-shot/structured output 조정. 모델 변경 시 동일 20개 재시험. |

### `VC-EUS-TTS-01` — 음성 응답 지연

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-FR-022/VT-022, SYS-PF-005/VT-049, E-02/TBD-010 |
| 목표 | 발화 종료→TTS 시작 ≤3초. |
| 방법 | 실제 음성/모의 transcript 각각 시험, STT→LLM→manager response→speech_out 전체 timestamp 기록. |
| 조건 | 공용 PC, 정상 Wi‑Fi/API. 네트워크 실패 시험은 별도. |
| 측정점 | 시작=발화 종료, 종료=스피커 출력 시작. 단위 ms. |
| 횟수 | 최소 10회 제안(정식 분모는 박병후 검증 기준 확인 필요). |
| 합격 | 각 회차/최대값 기준 여부를 SRD 취합에서 확정. 현재 목표는 ≤3초. |
| 결과 | **미수행.** T10 10/08, 담당 정의석. |
| 증거 | 예정: timestamp log/video. |
| 미달 시 | local TTS 우선, 모델/네트워크 구간별 병목 분석, HMI text fallback. |

### `VC-EUS-HMI-01` — HMI 기능/1초 반영/명령 폴백

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-FR-029/030/031/032, SYS-IF-006/VT-042, SYS-PF-008/VT-052, E-03/TBD-011 |
| 목표 | 요구 화면 항목 표시 + HMI fallback command + 상태 변경→화면 ≤1초. |
| 방법 | mock ROS publisher→hmi_bridge→MQTT→Web HMI end-to-end. command는 Web→MQTT→service mock 왕복. |
| 조건 | 공용/개인 PC LAN, Mosquitto, web stack version 기록. |
| 측정점 | ROS subscriber 수신 timestamp → browser DOM update timestamp. command는 button click→service response. |
| 횟수 | state/result 각각 20 이벤트 제안, command type별 최소 3회 제안. |
| 합격 | HMI target event ≤1초; command duplicate 미실행; disconnect 표시/재접속 복구. |
| 결과 | **미수행.** T11 10/08~10, T13 10/10~13. |
| 증거 | 예정: MQTT log, browser timestamp, screen recording, test report. |
| 미달 시 | bridge/backend bottleneck 분리 측정, state throttle/snapshot 재설계. |

### `VC-EUS-DB-01` — 저장/중복/오류/재기동

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-FR-014/VT-014, SYS-IF-004/VT-040, SYS-DT-001/VT-057, SYS-DT-002/VT-058, SYS-DT-003/VT-059, E-04/TBD-012 |
| 목표 | 결과 1건→DB 1행, duplicate 미증가, DB failure 노출, container restart 후 보존. |
| 방법 | mock SortResult publish + DB query; 동일 ID 2회 publish; DB stop/credential error; container restart. |
| 조건 | DB 종류/버전 확정 후 기록, host volume 사용. |
| 측정점 | result 수신→commit timestamp; row count before/after. |
| 횟수 | 정상 10건 제안 + duplicate 5회 + failure/restart 각 3회 제안. 정식 분모는 SRD 취합에서 확정. |
| 합격 | 정상 1:1, duplicate row count 불증가, 오류 표시, restart 후 row 유지. |
| 결과 | **미수행.** T12 10/09~11. |
| 증거 | 예정: SQL query output, container logs, restart screenshot. |
| 미달 시 | unique key/migration 수정, write queue/재시도 정책 검토. |

### `VC-EUS-SEC-01` — Secret 검사

| 항목 | 답변 |
|---|---|
| 관련 SYS/VT/TBD | SYS-CT-006/VT-065, E-06/TBD-026 |
| 목표 | API key/DB password가 코드·yaml·compose·문서·Git history에 평문으로 없음. runtime env로만 주입. |
| 방법 | repo grep/secret scan + compose/env inspection. |
| 조건 | 실제 repo 최신 branch. |
| 측정점 | 해당 없음. |
| 횟수 | release/PR마다 1회. |
| 합격 | secret 0건. `.env` gitignored, `.env.example`에는 값 없음. |
| 결과 | **이번 첨부만으로 repo 검사는 미수행.** T11~T13 PR에서 검사 예정. |
| 증거 | 예정: CI/grep 결과. |
| 미달 시 | key rotate + history 정리 + CI secret scan 추가. |

---

## 5. 미정·의존·범위 제안

### 5.1 필수 변경 제안 카드

#### `CHG-EUS-01` — IC-CMD-01 / Intent·이력 질의·HMI command 계약 보완

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 변경 유형 | `CHG-EUS-01` / 정의석 / **수정 + 필드/enum 추가 제안** |
| 대상 SYS/IC/VT·카드 ID | SYS-FR-017, SYS-FR-029, SYS-IF-005, IC-CMD-01, IC-STATS-01, VT-017/029/041/047 |
| 변경 전 / 변경 후 | **전:** Intent type 후보 `start|stop|resume|priority|answer|update_zone_map`, fields `dong,zone,count,raw_text`; 이력 질의 type/args와 HMI command ack가 없음. **후:** B 필수에 `query_history` + `query_kind(count_by_dong|held_count|remaining_count)` 추가, answer의 HOLD 표현 규칙 명시, HMI command에 `command_id`/ack 규칙 명시. C의 `update_zone_map`은 유지하되 B 선행조건에서 제외. |
| 꼭 필요한 이유 | SRD/BRD의 **로그 기반 이력 질의가 B 최종 필수**인데 현재 Intent 후보로 동별/보류/남은 수를 명확히 표현할 수 없음. MQTT QoS1 중복 명령을 안전하게 막으려면 command_id가 필요. |
| 영향받는 파트·계약·코드·시험 | 남현지 sort_manager, `voss_msgs/Intent`, `docs/interfaces/intent_json.md`, `mqtt.md`, hmi_bridge, intent_parser, stats service, VT-017/041/047. |
| 대안·이행 방법·일정 영향 | `query_history`를 별도 service/API로만 분리하는 대안도 가능하나 음성→manager 흐름과 이중 계약이 됨. 10/08 sort_manager 연동 전 확정 권장. |
| 담당자 의견·상태 | 정의석 제안. 남현지 확인/PL 승인 미완료. **확정으로 기록하지 말 것.** |

### 5.2 미정·의존 사항

| 관련 ID | 미정 내용·이유 | 결정 담당·예정일 | 다른 파트 영향·먼저 필요한 입력 | 제안 |
|---|---|---|---|---|
| TBD-009 / CHG-EUS-01 | query_history/query_kind/HOLD/command_id 최종 schema | 정의석+남현지 / 10/08 | sort_manager, voss_msgs, intent tests | 10/08 manager 연동 전 계약 PR 우선 |
| TBD-010 / pending #5 | 호출어 엔진 | 정의석 / 10/06 | T08, 마이크 시험 | STT 문자열 매칭 vs 경량 wakeword 모델 비교 후 결정 |
| TBD-010 / pending #6 | Whisper 모델 크기/backend | 정의석+남현지 / 10/06~07 | YOLO/PaddleOCR VRAM 공유 | 개인 PC 비교 후 공용 PC 8GB 동거 실측으로 결정 |
| TBD-010 / pending #12 | TTS 엔진 | 정의석 / 10/08 | VT-049 3초 목표 | local vs API 지연/한국어 품질 비교 |
| TBD-011 / pending #13 | Web stack·실행 위치·MQTT JSON/QoS/ack | 정의석+남현지 / 10/08 | T11/T13, command/status contract | React+Spring Boot+Mosquitto 재사용안 제안, JSON은 docs/interfaces 먼저 확정 |
| TBD-012 / pending #14 | DB 종류/버전/credential/schema migration | 정의석 / 10/09 | T12, HMI stats, 이력 질의 | PostgreSQL 제안, host volume + writer/read 권한 분리 |
| TBD-007 연동 | physical box vs attempt/reinsertion 및 DB unique key | 남현지+정의석 / 10/08 제안 | DT-001, stats 정확도, sort_log PK | attempt_id 또는 box_id-per-attempt 중 하나로 명시 |
| IC-STATS-01 | `/voss/sort/stats` 제공 노드와 custom srv 타입 | 남현지+정의석 / 10/08 | query_history/HMI 집계 | DB-backed 단일 집계 source 유지 |
| TBD-026 | CycloneDDS lo-only NIC 수정 완료 여부·USB inventory·동시 GPU 부하 | 김학민+남현지+정의석 / 10/08~10 | ROS 연동, Whisper 최종 선택 | wlo1/DDS 설정 확인 + nvidia-smi 동시부하 로그 남김 |
| VT-049/052 등 | 시험 횟수/최대값 vs 평균 판정 방식 | 박병후+각 담당 / 검증 계획 확정 시 | 수락 판정 | 목표와 실측을 분리하고 raw 측정값 전체 보존 |

---

## 6. 회신 전 확인

- [x] 내 담당 요구사항의 수용/수정/미정을 표시했습니다.
- [x] 내 질문 ID의 각 답변을 채웠거나 미정/해당 없음과 이유를 적었습니다.
- [x] 데이터 예시·식별·시간·실패 처리와 상대에게 필요한 정보를 **확정/제안/미정으로 구분**해 적었습니다.
- [x] IC 커버리지 목록과 담당 VT 행에 카드 참조 또는 미정/후속 이유를 연결했습니다.
- [x] 혼합 질문의 A 완료와 B 후속 미완료를 별도 표시했습니다.
- [x] 필수 계약 누락(`query_history` 등)은 `CHG-EUS-01` 변경 제안으로 남겼고 기존 ID는 삭제하지 않았습니다.
- [x] 시험 목표와 실측 결과를 구분했고, 미정 담당·기한을 적었습니다.
- [x] 선택 기능(`update_zone_map`/신규 구역)은 기본 전체 흐름의 선행조건으로 넣지 않았습니다.
- [x] 비밀번호·API 키 값·개인 연락처는 넣지 않았습니다.

## 제출 전 정의석 본인 확인 필요 항목

1. `CHG-EUS-01`의 `query_history/query_kind/command_id` 제안을 남현지에게 보낼지 확인.
2. Web stack 제안 `React + Spring Boot + Mosquitto`를 pending #13 결정 후보로 유지할지 확인.
3. DB 후보를 PostgreSQL로 제안할지 확인(버전은 아직 기입하지 않음).
4. HMI command MQTT QoS1/zone_map retained 제안을 팀 계약으로 올릴지 확인.
5. `remaining = planned - (PLACED + HELD)`에서 FAILED 제외가 팀 의도와 맞는지 확인.
6. box_id/attempt/reinsertion 규칙을 남현지와 확인해 DB unique key를 확정.
7. 현재 직접 확인하지 않은 테스트/사람 확인을 **완료로 바꾸지 말 것**.
