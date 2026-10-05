# 파트 간 인터페이스 계약

병렬 개발이 10/13에 한 번에 붙으려면 여기가 맞아야 한다. **코드보다 이 문서가 먼저다.**

| 파일 | 내용 | 상태 |
|---|---|---|
| topics.md | 노드별 발행·구독·서비스·액션 전체 표 | SRD 9장 제안 → **10/05 확정 필요** |
| voss_msgs.md | 커스텀 메시지 필드 정의 (src/voss_msgs 와 1:1) | 제안 |
| intent_json.md | intent_parser 가 만드는 JSON 과 허용 목록 | 제안 |
| mqtt.md | hmi_bridge ↔ 웹 HMI MQTT 토픽·JSON | 미정 (정의석, 10/08) |
| voss_config.md | voss_config.yaml 스키마 (zone_map, 구역 좌표, 벨트 속도 등) | 제안 |

## 변경 절차
1. 이 폴더의 문서를 고치는 PR을 먼저 올린다 (`interface` 라벨). 영향받는 파트 담당자를 리뷰어로.
2. 승인 후 `src/voss_msgs` 와 노드 코드를 고친다 (같은 PR 또는 바로 다음 PR).
3. 변경 이력을 해당 문서 끝에 한 줄 남긴다.
