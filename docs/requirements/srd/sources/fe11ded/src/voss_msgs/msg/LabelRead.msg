int32 track_id
string code
string dong
float32 confidence
uint8 stage              # 1 입구 관측 | 2 추종 중 | 3 재확인 구역
builtin_interfaces/Time stamp   # 판정에 쓴 원본 프레임 중 가장 최근 촬영 시각 (오래된 결과 거르기)
string raw_text           # OCR 원문 (여러 줄이면 줄바꿈 문자 포함), HMI·로그용
string dong_alt           # 2위 후보 동, 없으면 ""
float32 confidence_alt    # 2위 후보 신뢰도, 없으면 0
