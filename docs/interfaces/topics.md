# 노드·토픽·서비스·액션 (SRD 9장 제안 — 10/05 팀 확정)

규칙: 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 커스텀 타입은 `voss_msgs`.

| 노드 | 패키지 / 담당 | 발행 / 제공 | 구독 / 호출 |
|---|---|---|---|
| voice_listener | voss_voice / 정의석 | `/voss/voice/transcript` (std_msgs/String) | 내장 마이크 |
| intent_parser | voss_voice / 정의석 | `/voss/voice/intent` (voss_msgs/Intent), `/voss/voice/say` (되묻기·이력 조회 응답, 중복 억제는 intent_parser) | `/voss/voice/transcript`, `/voss/sort/zone_map` (동·구역·별칭 허용 목록. YAML 직접 읽기 금지), `/voss/sort/state` (answer 의 box_id). 이력 질의는 REST `GET /api/stats` |
| speech_out | voss_voice / 정의석 | 내장 스피커 | `/voss/voice/say` (std_msgs/String) |
| sort_manager | voss_manager / 남현지 | `/voss/sort/state` (voss_msgs/SortState), `/voss/sort/result` (voss_msgs/SortResult), `/voss/sort/zone_map` (voss_msgs/ZoneMap, transient_local), `/voss/voice/say`. 서비스: `/voss/sort/command` (srv/Command), `/voss/sort/update_zone_map` (srv/UpdateZoneMap). `/voss/voice/say` 는 같은 box_id 의 같은 이벤트를 한 번만 발행 | `/voss/voice/intent`, `/voss/vision/box`, `/voss/vision/label`, `/voss/robot/state`·`/voss/log/status` (준비 판단). 액션 호출 `/voss/servo/track_and_grasp`. 서비스 호출 `/voss/robot/move_to_zone`, `/voss/robot/gripper`, `/voss/vision/read_label` (RECHECK 상태에서) |
| hmi_bridge | voss_hmi / 정의석 | MQTT `voss/state`, `voss/result`, `voss/zone_map`, `voss/robot`, `voss/command/ack` (JSON) | MQTT `voss/command` → `/voss/sort/command` 호출. `/voss/sort/state`, `/voss/sort/result`, `/voss/sort/zone_map`, `/voss/robot/state` 구독 |
| sort_logger | voss_hmi / 정의석 | DB 테이블 `sort_log`(유일키 box_id), `/voss/log/status` (std_msgs/String `STARTING`/`OK`/`DB_ERROR`/`SPOOL_FULL`, 1 Hz) | `/voss/sort/result` |
| realsense2_camera | (외부, voss_bringup 이 `camera_namespace:=''` 로 기동) | `/camera/color/image_raw` (sensor_msgs/Image), `/camera/color/camera_info` | — |
| box_tracker | voss_vision / 남현지 | `/voss/vision/box` (voss_msgs/BoxTrack, 픽셀 + 베이스 좌표 m) 30 Hz, `/voss/vision/label_crop` (voss_msgs/LabelCrop, 선명 프레임만) | `/camera/color/image_raw`, `/voss/sort/state` (크롭의 stage 를 정하는 데만 씀), `/voss/robot/pose` (TCP. 이동 중 좌표: 촬영 시각 pose 보간. 핸드아이 촬영 자세도 같은 TCP pose 로 기록 → `T_tcp→camera`) |
| label_reader | voss_vision / 남현지 | `/voss/vision/label` (voss_msgs/LabelRead). 서비스: `/voss/vision/read_label` (srv/ReadLabel, 3단계 재판독. 결과는 응답으로 주고 `/voss/vision/label` 에도 stage 3 으로 발행) | `/voss/vision/label_crop`, `/voss/sort/zone_map` (분류코드·동·별칭 = 퍼지 매칭 후보) |
| belt_servo | voss_servo / 박병후 | `/voss/robot/servo_cmd` (geometry_msgs/TwistStamped: **TCP 기준점**의 선속도 m/s·각속도 rad/s, frame_id `base_link`. G0 추종은 고정 파지 자세·각속도 0 — #53 MC-010). 액션 제공 `/voss/servo/track_and_grasp` (voss_msgs/action/TrackAndGrasp) | `/voss/vision/box` (`position_base` 관측값 → TCP 목표는 belt_servo 가 계산. 벨트 위 파지 높이 = TCP z `position_base.z − 19 mm`(박스 27 mm − 핑거 끝 박스 밑면 +8 mm, measurements #6)로 belt_servo 파라미터 YAML 에 둔다(MC-009). servo 는 TCP 로 명령하므로 TCP 오프셋을 쓰지 않는다), `/voss/robot/pose` (TCP). 서비스 호출 `/voss/robot/gripper`: goal 실행 중 gripper 는 **belt_servo 만** 부른다(PREPARE 사전 개방·GRASP 닫기·VERIFY 확인). 놓을 때 개방은 MoveToZone(PLACE). 응답 시점 = RG2 동작 완료 또는 timeout(비동기 호출, 닫히는 동안 추종 계속). 폭·힘은 voss_config `gripper.*` |
| robot_gateway | voss_robot / 김학민 | `/voss/robot/pose` (geometry_msgs/PoseStamped, ~50 Hz: **TCP(핑거 끝)** pose, frame_id `base_link`, 위치 m·자세 쿼터니언(두산 posx ZYZ 에서 변환). TCP = voss_config `robot.tcp_offset_mm`(플랜지 → 핑거 끝, #57), robot_gateway 가 브링업마다 등록하고 변환한다 — zones·observe_pose 는 플랜지 그대로(#53 MC-010). stamp = `get_current_posx` 요청 송신·응답 수신 시각의 중간값. RTT 를 함께 로그로 남기며 오차 보장값으로 쓰지 않는다 — MC-004), `/voss/robot/state` (voss_msgs/RobotState, 정의 예정 — 김학민 10/07). 서비스: `/voss/robot/move_to_zone` (srv/MoveToZone), `/voss/robot/gripper` (srv/Gripper), `/voss/robot/teach_zone` (srv/TeachZone) | `/voss/robot/servo_cmd`. 두산: `/dsr01/dsr_controller2/motion/move_line` (ASYNC), `/dsr01/servol_stream` (10/06 확인), `aux_control/get_current_posx`. RG2: Modbus TCP 또는 onrobot 드라이버 (미정) |

## QoS 제안
| 토픽 | reliability | durability | depth |
|---|---|---|---|
| /voss/vision/box, /voss/robot/pose, /voss/robot/servo_cmd | best_effort | volatile | 1 |
| /voss/sort/state, /voss/sort/result, /voss/vision/label, /voss/voice/* | reliable | volatile | 10 |
| /voss/log/status | reliable | volatile | 1 |
| /voss/vision/label_crop | reliable | volatile | 5 |
| /voss/sort/zone_map | reliable | transient_local | 1 |

## 변경 이력
- 2026-10-05: SRD 9장 제안을 그대로 옮김. 확정 전.
- 2026-10-06: pending #1 승인 PR (#10). `label_crop` 타입을 voss_msgs/LabelCrop 로 변경(track_id·stage 전달), `/voss/vision/read_label` 서비스 추가(3단계 재판독), box_tracker 가 `/voss/sort/state` 구독, intent_parser 가 `/voss/sort/zone_map` 구독(별칭), label_crop QoS 추가(박스당 크롭 몇 장뿐이라 유실 없게 reliable).
- 2026-10-06: realsense2_camera 는 `camera_namespace:=''` 로 띄워 `/camera/color/*` 를 유지 (기본값 `/camera/camera/*` 아님). voss_bringup 이 강제 (#10 리뷰 ②).
- 2026-10-06: `/voss/sort/state` 는 reliable·volatile·≥2 Hz 주기 발행 유지 (SRD 상호확인 #52 MC-026). 늦게 뜬 box_tracker 는 상태 수신 전까지 stage 1 로 둔다.
- 2026-10-06: SRD 상호확인 합의 (#51·#52). `/voss/sort/stats` 삭제(집계는 REST `GET /api/stats`, 정의석), sort_logger `/voss/log/status` 신설(영역 `log`, ADR-0001), intent_parser 의 say 발행·`/voss/sort/state` 구독 추가, hmi_bridge `/voss/robot/state` 구독. `/voss/robot/state`(RobotState) 정의는 김학민이 추가.
- 2026-10-06: #63 리뷰 반영. robot_gateway 가 `/voss/robot/state` 발행(타입은 김학민 PR), `/voss/log/status` 에 `SPOOL_FULL` 추가(#54 합의).
- 2026-10-06: box_tracker 가 `/voss/robot/pose` 구독(이동 중 베이스 좌표, #50 MC-001·002).
- 2026-10-06: #65 리뷰 반영. `/voss/robot/pose` stamp 정의(김학민), belt_servo 는 `position_base` 를 관측값으로 받아 TCP 목표를 계산(#50 MC-001), belt_servo 의 `/voss/robot/gripper` 호출 추가. (이때 pose 를 플랜지로 적었으나 10/07 TCP 로 정정 — 아래)
- 2026-10-07: #65 리뷰(김학민 10/07 01:23, 박병후) 반영. `/voss/robot/pose` = **TCP** pose, `servo_cmd` = TCP 기준점 속도·`base_link`·G0 각속도 0 (#53 MC-010). TCP 변환은 gateway 만(`robot.tcp_offset_mm`, #57). 벨트 위 파지 높이 = TCP z `position_base.z − 19 mm` 를 belt_servo 파라미터로(MC-009). belt_servo 의 gripper 직접 호출 확정(조건 4개, 박병후 확인).
