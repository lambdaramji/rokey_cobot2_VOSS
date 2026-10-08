# robot_gateway → /voss/robot/state (reliable·transient_local·depth 1, 상태가 바뀔 때 + 2 Hz)
std_msgs/Header header
bool connected           # 두산 컨트롤러·RG2 Modbus 모두 연결
string state             # READY | BUSY | STOPPED | ERROR
string action            # 실행 중 동작 예 MOVE_TO_ZONE:B | SERVO | GRIPPER, 없으면 ""
float32 gripper_width_mm # RG2 보고 폭 (실측 안쪽 간격: 보고 90 → 80, 빈손 39 → 28 mm. 차이 10~11 mm, 보정식 아님)
string error_code        # 예 ESTOP | SAFETY_STOP | GRIPPER_ERROR | TIMEOUT, 없으면 "". 비상정지 = state ERROR + ESTOP
string detail            # 사람이 읽는 설명
