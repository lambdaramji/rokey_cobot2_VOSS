# Sprint 2 (BRD v1.5) — sort_manager → /voss/pallet/state (reliable·transient_local·1, 바뀔 때, 계획 직후·첫 PICK 전에 한 번). HMI 3D 팔레트 (TR-PAL-10)
string run_id                  # palletize 실행 ID (YYYYMMDDTHHMMSS-xxxx, 실행마다 새로). 실행 전 ""
string state                   # RUNNING | PAUSED | DONE | "" (실행 없음)
string[] route                 # 첫 배송지부터
string[] dongs                 # 집계 동: 경로 동(방문 순서) 다음에 경로 밖 동(A·B·C 에 PLACED 박스가 있으면)
int32[] load                   # dongs 와 같은 순서: 팔레트에 실을 수
int32[] overflow               # 초과로 못 싣는 수 (경로 동만)
int32[] excluded               # 경로 제외 수 (경로 밖 동만)
bool overflow_warning          # 초과가 있으면 true → HMI "배송 물량 남음"
int32 total                    # 실을 박스 수 (= load 합, ≤ 16)
int32 done
int32 failed
string box_id                  # 지금 옮기는 박스, 없으면 ""
string[] slot_state            # 길이 16, 인덱스 = slot 0~15 = (열−1)×4 + (층−1)×2 + (줄−1): EMPTY | PLANNED | MOVING | DONE | FAILED
string[] slot_box_id           # 길이 16, 그 칸에 계획된 box_id (없으면 "")
string[] slot_dong             # 길이 16, 그 칸에 계획된 동 (없으면 "", 3D 색)
