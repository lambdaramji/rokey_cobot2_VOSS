# intent JSON (intent_parser 출력, LangChain + OpenAI)

LLM 출력은 반드시 아래 JSON 하나. 허용 목록 밖 값은 intent_parser 가 거부하고 `/voss/voice/say` 로 되묻는다.

```json
{
  "type": "start | stop | resume | priority | answer | update_zone_map",
  "dong": "역삼동 | 대치동 | 청담동 | null",
  "zone": "A | B | C | null",
  "count": 0,
  "raw_text": "사용자 발화 원문"
}
```

| 발화 예 | type | dong | zone | count |
|---|---|---|---|---|
| "전부 분류해" | start | null | null | 0 |
| "역삼동부터 분류해" | priority | 역삼동 | null | 0 |
| "멈춰" / "다시 시작" | stop / resume | | | |
| (질문에) "청담동이야" | answer | 청담동 | | |
| "대치동을 C 구역으로 바꿔" | update_zone_map | 대치동 | C | |

- 허용 동 3개, 구역 3개는 `/voss/sort/zone_map` 과 같아야 한다.
- 지시 해석 정확도 목표 ≥ 95% (20개 중 19개).

## 변경 이력
- 2026-10-05: 초안.
