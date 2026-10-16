# box_tracker → label_reader. 송장 영역 크롭 1장 (선명 프레임만 보낸다)
std_msgs/Header header       # stamp = 원본 카메라 프레임 시각(보존), frame_id = 카메라 광학 프레임
int32 track_id               # BoxTrack.track_id 와 같은 값
uint8 stage                  # 1 입구 관측 | 2 추종 중 | 3 재확인 구역 (/voss/sort/state 로 결정)
float32 sharpness            # 선명도 점수, 클수록 선명 (프레임 선택·다수결 가중)
sensor_msgs/Image image      # 송장 영역 크롭, 전처리 전 원본 색
