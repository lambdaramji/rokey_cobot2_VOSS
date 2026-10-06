string box_id             # <session_id>-<3자리 순번>, DB 유일키
string code
string dong
float32 confidence
string decided_by         # OCR | RECHECK | OPERATOR | NONE
string zone               # A | B | C | RECHECK | HOLD | "" (PASSED·FAILED)
string outcome            # PLACED | HELD | FAILED | PASSED
builtin_interfaces/Time stamp   # 결과 확정 시각 (PLACED 는 MoveToZone.placed_stamp)
string session_id         # start 시각 YYYYMMDDTHHMMSS
int32 track_id            # 참고용 (DB 키 아님)
builtin_interfaces/Time started_at  # 이 box_id 를 만든 첫 BoxTrack 의 촬영 시각 (t_detect)
string raw_text           # OCR 원문
string dong_alt           # 2위 후보 동, 없으면 ""
string rule_version       # 적용한 ZoneMap.version
string reason             # "" | LOW_CONF | NO_ANSWER | NON_TARGET | STOPPED | DEVICE_ERROR | (TrackAndGrasp reason)
int32 attempts            # 파지 총 시도 수 (TrackAndGrasp 결과), PASSED 는 0
