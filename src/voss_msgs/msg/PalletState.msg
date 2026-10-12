# Sprint 2 — sort_manager → /voss/pallet/state (reliable·transient_local·1, 바뀔 때). HMI 배치도·진행률 (TR-PAL-10)
string run_id                  # palletize 실행 ID (YYYYMMDDTHHMMSS-xxxx, 실행마다 새로). 실행 전 ""
string state                   # RUNNING | PAUSED | DONE | "" (실행 없음)
string[] route                 # 첫 배송지부터. 열 수 = len(route), 열 0 = 가장 왼쪽(−X), 첫 배송지 = 가장 오른쪽 열
int32 total                    # 계획 박스 수
int32 done
int32 failed
string box_id                  # 지금 옮기는 박스, 없으면 ""
string[] slot_state            # 길이 = 열 수 × 3, 인덱스 = 팔레트 칸(열 × 3 + 칸): EMPTY | PLANNED | MOVING | DONE | FAILED
string[] slot_box_id           # 같은 인덱스, 그 칸에 계획된 box_id (없으면 "")
