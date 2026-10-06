int32 track_id
float32 u                # 픽셀 x
float32 v                # 픽셀 y
int32[4] bbox            # x, y, w, h (픽셀)
builtin_interfaces/Time stamp
geometry_msgs/Point position_base   # 박스 윗면 중앙 = TCP(핑거 끝)가 갈 점. 단위 m, 두산 베이스 축(base_link)
bool position_valid       # false 면 position_base 를 쓰지 않는다 (캘리브레이션·pose 정합 불가 등)
uint8 position_source     # 0 NONE | 1 OBSERVE_HOMOGRAPHY (관측 자세 정지) | 2 HAND_EYE (이동 중, 촬영 시각 pose)
string calib_version      # 사용한 캘리브레이션 파일 version·created
