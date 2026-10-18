string state             # IDLE | RUNNING | PICKING | RECHECK | ASKING | PAUSED
string box_id
string pending_question
int32 track_id           # 현재 처리 중인 박스의 BoxTrack.track_id, 없으면 -1
bool ready               # 준비 판단 (SYS-FR-001): 모두 READY 일 때만 start 를 받는다
string[] not_ready       # 준비 안 된 항목 (ROBOT / SERVO / VISION / OCR / LOG)
string session_id        # 현재 세션 (start 때 생성, SortResult.session_id 와 같은 값, 다음 start 까지 유지). 첫 start 전 ""
