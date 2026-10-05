# 노드·토픽·서비스·액션 (SRD 9장 제안 — 10/05 팀 확정)

규칙: 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 커스텀 타입은 `voss_msgs`.

| 노드 | 패키지 / 담당 | 발행 / 제공 | 구독 / 호출 |
|---|---|---|---|
| voice_listener | voss_voice / 정의석 | `/voss/voice/transcript` (std_msgs/String) | 내장 마이크 |
| intent_parser | voss_voice / 정의석 | `/voss/voice/intent` (voss_msgs/Intent) | `/voss/voice/transcript` |
| speech_out | voss_voice / 정의석 | 내장 스피커 | `/voss/voice/say` (std_msgs/String) |
| sort_manager | voss_manager / 남현지 | `/voss/sort/state` (voss_msgs/SortState), `/voss/sort/result` (voss_msgs/SortResult), `/voss/sort/zone_map` (voss_msgs/ZoneMap, transient_local), `/voss/voice/say`. 서비스: `/voss/sort/command` (srv/Command), `/voss/sort/update_zone_map` (srv/UpdateZoneMap), `/voss/sort/stats` (srv/Stats) | `/voss/voice/intent`, `/voss/vision/box`, `/voss/vision/label`. 액션 호출 `/voss/servo/track_and_grasp`. 서비스 호출 `/voss/robot/move_to_zone`, `/voss/robot/gripper` |
| hmi_bridge | voss_hmi / 정의석 | MQTT `voss/state`, `voss/result`, `voss/zone_map` (JSON) | MQTT `voss/command` → `/voss/sort/command` 호출. `/voss/sort/state`, `/voss/sort/result`, `/voss/sort/zone_map` 구독 |
| sort_logger | voss_hmi / 정의석 | DB 테이블 `sort_log` | `/voss/sort/result` |
| realsense2_camera | (외부) | `/camera/color/image_raw` (sensor_msgs/Image), `/camera/color/camera_info` | — |
| box_tracker | voss_vision / 남현지 | `/voss/vision/box` (voss_msgs/BoxTrack) 30 Hz, `/voss/vision/label_crop` (sensor_msgs/Image, 선명 프레임만) | `/camera/color/image_raw` |
| label_reader | voss_vision / 남현지 | `/voss/vision/label` (voss_msgs/LabelRead) | `/voss/vision/label_crop`, `/voss/sort/zone_map` |
| belt_servo | voss_servo / 박병후 | `/voss/robot/servo_cmd` (geometry_msgs/TwistStamped). 액션 제공 `/voss/servo/track_and_grasp` (voss_msgs/action/TrackAndGrasp) | `/voss/vision/box`, `/voss/robot/pose` |
| robot_gateway | voss_robot / 김학민 | `/voss/robot/pose` (geometry_msgs/PoseStamped, ~50 Hz). 서비스: `/voss/robot/move_to_zone` (srv/MoveToZone), `/voss/robot/gripper` (srv/Gripper), `/voss/robot/teach_zone` (srv/TeachZone) | `/voss/robot/servo_cmd`. 두산: `/dsr01/dsr_controller2/motion/move_line` (ASYNC), `/dsr01/servol_stream` (10/06 확인), `aux_control/get_current_posx`. RG2: Modbus TCP 또는 onrobot 드라이버 (미정) |

## QoS 제안
| 토픽 | reliability | durability | depth |
|---|---|---|---|
| /voss/vision/box, /voss/robot/pose, /voss/robot/servo_cmd | best_effort | volatile | 1 |
| /voss/sort/state, /voss/sort/result, /voss/vision/label, /voss/voice/* | reliable | volatile | 10 |
| /voss/sort/zone_map | reliable | transient_local | 1 |

## 변경 이력
- 2026-10-05: SRD 9장 제안을 그대로 옮김. 확정 전.
