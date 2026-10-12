# Sprint 2 — sort_manager → /voss/pallet/result, 박스마다 1건 (TR-PAL-09). sort_logger → DB pallet_log (유일키 run_id + box_id)
string run_id
string session_id
string box_id
string dong
int32 route_index              # 경로 순번, 0 = 첫 배송지
string zone                    # 집은 곳: 원래 구역 A | B | C
int32 slot                     # 집은 곳: 원래 칸
int32 pallet_col               # 놓은 곳: 팔레트 열 (0 = 가장 왼쪽 −X)
int32 pallet_row               # 놓은 곳: 열 안 칸. MoveToZone PALLET slot = pallet_col × 3 + pallet_row
string outcome                 # DONE | FAILED
string reason                  # "" | GRIP_FAIL | DROPPED | STOPPED | DEVICE_ERROR
int32 attempts                 # PICK 시도 수 (처음 + 재시도 최대 2)
builtin_interfaces/Time stamp  # DONE = DROP 개방 완료 시각(placed_stamp), FAILED = 확정 시각
