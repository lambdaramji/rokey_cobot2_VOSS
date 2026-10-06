# 노드·토픽·서비스·액션 (SRD 9장 제안 — 10/05 팀 확정)

규칙: 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 커스텀 타입은 `voss_msgs`.

| 노드 | 패키지 / 담당 | 발행 / 제공 | 구독 / 호출 |
|---|---|---|---|
| voice_listener | voss_voice / 정의석 | `/voss/voice/transcript` (std_msgs/String) | 내장 마이크 |
| intent_parser | voss_voice / 정의석 | `/voss/voice/intent` (voss_msgs/Intent) | `/voss/voice/transcript`, `/voss/sort/zone_map` (동·구역·별칭 허용 목록. YAML 직접 읽기 금지) |
| speech_out | voss_voice / 정의석 | 내장 스피커 | `/voss/voice/say` (std_msgs/String) |
| sort_manager | voss_manager / 남현지 | `/voss/sort/state` (voss_msgs/SortState), `/voss/sort/result` (voss_msgs/SortResult), `/voss/sort/zone_map` (voss_msgs/ZoneMap, transient_local), `/voss/voice/say`. 서비스: `/voss/sort/command` (srv/Command), `/voss/sort/update_zone_map` (srv/UpdateZoneMap), `/voss/sort/stats` (srv/Stats) | `/voss/voice/intent`, `/voss/vision/box`, `/voss/vision/label`. 액션 호출 `/voss/servo/track_and_grasp`. 서비스 호출 `/voss/robot/move_to_zone`, `/voss/robot/gripper`, `/voss/vision/read_label` (RECHECK 상태에서) |
| hmi_bridge | voss_hmi / 정의석 | MQTT `voss/state`, `voss/result`, `voss/zone_map` (JSON) | MQTT `voss/command` → `/voss/sort/command` 호출. `/voss/sort/state`, `/voss/sort/result`, `/voss/sort/zone_map` 구독 |
| sort_logger | voss_hmi / 정의석 | DB 테이블 `sort_log` | `/voss/sort/result` |
| realsense2_camera | (외부, voss_bringup 이 `camera_namespace:=''` 로 기동) | `/camera/color/image_raw` (sensor_msgs/Image), `/camera/color/camera_info` | — |
| box_tracker | voss_vision / 남현지 | `/voss/vision/box` (voss_msgs/BoxTrack) 30 Hz, `/voss/vision/label_crop` (voss_msgs/LabelCrop, 선명 프레임만) | `/camera/color/image_raw`, `/voss/sort/state` (크롭의 stage 를 정하는 데만 씀) |
| label_reader | voss_vision / 남현지 | `/voss/vision/label` (voss_msgs/LabelRead). 서비스: `/voss/vision/read_label` (srv/ReadLabel, 3단계 재판독. 결과는 응답으로 주고 `/voss/vision/label` 에도 stage 3 으로 발행) | `/voss/vision/label_crop`, `/voss/sort/zone_map` (분류코드·동·별칭 = 퍼지 매칭 후보) |
| belt_servo | voss_servo / 박병후 | `/voss/robot/servo_cmd` (geometry_msgs/TwistStamped). 액션 제공 `/voss/servo/track_and_grasp` (voss_msgs/action/TrackAndGrasp) | `/voss/vision/box`, `/voss/robot/pose` |
| robot_gateway | voss_robot / 김학민 | `/voss/robot/pose` (geometry_msgs/PoseStamped, ~50 Hz). 서비스: `/voss/robot/move_to_zone` (srv/MoveToZone), `/voss/robot/gripper` (srv/Gripper), `/voss/robot/teach_zone` (srv/TeachZone) | `/voss/robot/servo_cmd`. 두산: `/dsr01/dsr_controller2/motion/move_line` (ASYNC), `/dsr01/servol_stream` (10/06 확인), `aux_control/get_current_posx`. RG2: Modbus TCP 또는 onrobot 드라이버 (미정) |

## QoS 제안
| 토픽 | reliability | durability | depth |
|---|---|---|---|
| /voss/vision/box, /voss/robot/pose, /voss/robot/servo_cmd | best_effort | volatile | 1 |
| /voss/sort/state, /voss/sort/result, /voss/vision/label, /voss/voice/* | reliable | volatile | 10 |
| /voss/vision/label_crop | reliable | volatile | 5 |
| /voss/sort/zone_map | reliable | transient_local | 1 |

## 변경 이력
- 2026-10-05: SRD 9장 제안을 그대로 옮김. 확정 전.
- 2026-10-06: pending #1 승인 PR (#10). `label_crop` 타입을 voss_msgs/LabelCrop 로 변경(track_id·stage 전달), `/voss/vision/read_label` 서비스 추가(3단계 재판독), box_tracker 가 `/voss/sort/state` 구독, intent_parser 가 `/voss/sort/zone_map` 구독(별칭), label_crop QoS 추가(박스당 크롭 몇 장뿐이라 유실 없게 reliable).
- 2026-10-06: realsense2_camera 는 `camera_namespace:=''` 로 띄워 `/camera/color/*` 를 유지 (기본값 `/camera/camera/*` 아님). voss_bringup 이 강제 (#10 리뷰 ②).
- 2026-10-06: `/voss/sort/state` 는 reliable·volatile·≥2 Hz 주기 발행 유지 (SRD 상호확인 #52 MC-026). 늦게 뜬 box_tracker 는 상태 수신 전까지 stage 1 로 둔다.
