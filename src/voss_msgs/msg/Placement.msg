# Sprint 2 — ListPlacements 응답 항목. sort_logger 가 그 세션 sort_log 의 result PLACED · zone A/B/C 행만 준다 (docs/interfaces/voss_msgs.md)
string box_id
string dong
string zone                    # A | B | C
int32 slot -1                  # sort_log.slot (NULL 이면 -1, 기본값 -1)
builtin_interfaces/Time stamp  # sort_log.finished_at = 놓은 시각. 같은 칸이 다시 쓰였으면(reset_zone) 나중 기록만 트레이에 있다
bool palletized                # pallet_log 에 그 box_id 의 DONE 행이 있음
