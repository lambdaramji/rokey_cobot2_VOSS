# Sprint 2 (BRD v1.5) — sort_manager → /voss/pallet/result, 박스마다 1건 (TR-PAL-09). sort_logger → DB pallet_log (유일키 run_id + box_id)
# 싣지 않는 박스도 계획 직후 한 건씩: 초과 OVERFLOW, 경로 밖 동 EXCLUDED (S1 = 16 + 3 = 19건)
string run_id
string session_id
string box_id
string dong
int32 route_index              # 경로 순번, 0 = 첫 배송지. EXCLUDED 는 -1
string zone                    # 원래 구역 A | B | C (싣지 않은 박스는 거기 그대로, TR-PAL-11)
int32 slot                     # 원래 칸
int32 pallet_slot              # 0~15 = (열−1)×4 + (층−1)×2 + (줄−1). OVERFLOW·EXCLUDED 는 -1 (FAILED 는 계획했던 칸)
int32 pallet_col               # 1~4 (1 = 트럭 머리 −X, 4 = 문 +X), 싣지 않으면 0
int32 pallet_lane              # 1~2, 싣지 않으면 0
int32 pallet_layer             # 1~2 (2 = +27 mm), 싣지 않으면 0
string outcome                 # DONE | FAILED | OVERFLOW | EXCLUDED
string reason                  # "" | GRIP_FAIL | DROPPED | BLOCKED | STOPPED | DEVICE_ERROR
int32 attempts                 # PICK 시도 수 (처음 + 재시도 최대 2), 싣지 않으면 0
builtin_interfaces/Time stamp  # DONE = DROP 개방 완료(placed_stamp), FAILED = 확정, OVERFLOW·EXCLUDED = 계획 시각
