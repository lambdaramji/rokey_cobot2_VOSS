# 파트 간 인터페이스 계약

병렬 개발이 10/13에 한 번에 붙으려면 여기가 맞아야 한다. **코드보다 이 문서가 먼저다.**

| 파일 | 내용 | 상태 |
|---|---|---|
| topics.md | 노드별 발행·구독·서비스·액션 전체 표 | 10/05 확정 + 상호확인(#50~#55) 반영, SRD v1.0 정합 |
| voss_msgs.md | 커스텀 메시지 필드 정의 (src/voss_msgs 와 1:1) | 상호확인 반영 |
| intent_json.md | intent_parser 가 만드는 JSON 과 허용 목록 | 제안 |
| mqtt.md | hmi_bridge ↔ Spring Boot MQTT 토픽·QoS·JSON | MC-026 합의 반영, 최종 확정 정의석 #20 (10/08) |
| voss_config.md | voss_config.yaml 스키마 (zone_map, 구역 좌표, 벨트 속도 등) | 제안 |
| calibration.md | config/belt_homography.yaml 스키마 (픽셀 → 베이스 xy) | 제안 (ADR-0003, 10/06) |
| web_api.md | 웹·AI HTTP API (Spring Boot `/api` 이력·집계·명령·SSE, FastAPI `/ai` STT·intent) — ADR-0006 | 제안 (정의석, 10/06) |

## 변경 절차
1. 이 폴더의 문서를 고치는 PR을 먼저 올린다 (`interface` 라벨). 영향받는 파트 담당자를 리뷰어로.
2. 승인 후 `src/voss_msgs` 와 노드 코드를 고친다 (같은 PR 또는 바로 다음 PR).
3. 변경 이력을 해당 문서 끝에 한 줄 남긴다.

## SRD 와의 대응
SRD v1.0(PR #77 머지 후 `docs/requirements/srd/`) 5장의 IC-ID 가 이 폴더의 계약을 가리킨다. SRD 는 무엇을 보장해야 하는지, 이 폴더는 이름·타입·필드·QoS 를 정한다. 둘이 다르면 이 폴더를 고치는 PR 에서 SRD 부록 C 도 함께 확인한다.

열린 interface PR 과의 관계(10/07 기준): #48 `calibration.md`(belt_homography.yaml, 관측 자세 초기 위치) · #76 BoxTrack 확정 발행(`min_hits`, ID 건너뜀) · (#81 은 main 에 머지됨 — web_api 현재 세션 = `SortState.session_id`·`""` 이면 NO_SESSION, intent_json.md 늦은 답 문장 철회). 이 폴더의 다른 문서는 이 PR 들의 내용과 맞춰 두었고, 해당 PR 이 머지되면 그 문서가 기준이 된다.
