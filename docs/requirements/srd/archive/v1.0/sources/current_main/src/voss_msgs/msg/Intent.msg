# intent_parser -> sort_manager. 허용 값은 docs/interfaces/intent_json.md
string type        # start | stop | resume | priority | answer | update_zone_map
string dong        # zone_map 의 정식 동 이름 (별칭 아님) | ""
string zone        # A | B | C | HOLD(answer 전용) | ""
int32 count        # 현재 미사용 (타입 해시 유지를 위해 남김)
string raw_text
string box_id      # answer 일 때만: 질문 중(ASKING)인 SortState.box_id. 그 밖은 ""
