string state             # IDLE | RUNNING | PICKING | RECHECK | ASKING | PAUSED
string box_id
string pending_question
int32 track_id           # 현재 처리 중인 박스의 BoxTrack.track_id, 없으면 -1
