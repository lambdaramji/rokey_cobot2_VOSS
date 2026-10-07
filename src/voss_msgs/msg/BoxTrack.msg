uint8 SOURCE_NONE=0
uint8 SOURCE_OBSERVE_HOMOGRAPHY=1   # 관측 자세 정지
uint8 SOURCE_HAND_EYE=2             # 이동 중, 촬영 시각 pose

int32 track_id           # 새 박스마다 +1, 재사용 안 함. 15프레임 미검출 시 폐기, PICKING 중인 트랙은 보류 (voss_msgs.md BoxTrack 규칙)
float32 u                # 픽셀 x
float32 v                # 픽셀 y
int32[4] bbox            # x, y, w, h (픽셀)
builtin_interfaces/Time stamp
geometry_msgs/Point position_base   # 촬영 시각(stamp)에 관측한 박스 윗면 중심. 단위 m, 두산 베이스 축(base_link). TCP 목표가 아니다 (belt_servo 가 계산)
bool position_valid       # false 면 position_base 를 쓰지 않는다 (캘리브레이션·pose 정합 불가 등)
uint8 position_source     # SOURCE_* 상수 중 하나
string calib_version      # 사용한 캘리브레이션 파일 version·created
