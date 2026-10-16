# ROS 2 정적 등록 전체 목록

`src/voss_*`의 Python AST에서 `create_publisher`, `create_subscription`, `create_service`, `create_client`, `ActionServer`, `ActionClient` 호출을 추출했다. 이 표는 코드 등록 표현식이며 실제 런타임 graph가 아니다. 동적 토픽명, 조건부 생성, 외부 드라이버의 실제 서버는 미확인으로 남긴다. `진단/대체`는 기본 운전 경로로 가정하지 않는다.

| 파일:줄 | 범위 | 등록 | 이름/표현식 | 타입 표현식 | 해석 |
|---|---|---|---|---|---|
| `src/voss_hmi/voss_hmi/hmi_bridge.py:105` | 운전 코드 | Service client | `/voss/sort/command` | `Command` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:106` | 운전 코드 | Publisher | `/voss/voice/say` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:107` | 운전 코드 | Publisher | `/voss/voice/text` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:108` | 운전 코드 | Subscriber | `/voss/voice/text/reply` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:112` | 운전 코드 | Subscriber | `/voss/sort/state` | `SortState` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:118` | 운전 코드 | Subscriber | `/voss/sort/result` | `SortResult` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:124` | 운전 코드 | Subscriber | `/voss/sort/zone_map` | `ZoneMap` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:130` | 운전 코드 | Subscriber | `/voss/robot/state` | `RobotState` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:136` | 운전 코드 | Subscriber | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:141` | 운전 코드 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:142` | 운전 코드 | Subscriber | `/dsr01/joint_states` | `JointState` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:143` | 운전 코드 | Subscriber | `/voss/log/status` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:149` | 운전 코드 | Subscriber | `/voss/pallet/state` | `PalletState` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:156` | 운전 코드 | Subscriber | `/voss/voice/status` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:181` | 운전 코드 | Subscriber | `/voss/voice/status` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:138` | 조건부/부분 구현 | Subscriber | `/voss/hmi/box_motion` | `BoxMotion` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:174` | 운전 코드 | Publisher | `/voss/voice/text` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/hmi_bridge.py:177` | 운전 코드 | Subscriber | `/voss/voice/text/reply` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/sort_logger.py:137` | 운전 코드 | Publisher | `/voss/log/status` | `String` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/sort_logger.py:138` | 운전 코드 | Subscriber | `/voss/sort/result` | `SortResult` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/sort_logger.py:139` | 운전 코드 | Subscriber | `/voss/pallet/result` | `PalletResult` | 리터럴/상수 |
| `src/voss_hmi/voss_hmi/sort_logger.py:140` | 운전 코드 | Service server | `/voss/log/list_placements` | `ListPlacements` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:123` | 운전 코드 | Publisher | `/voss/sort/state` | `SortState` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:124` | 운전 코드 | Publisher | `/voss/sort/result` | `SortResult` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:125` | 운전 코드 | Publisher | `/voss/sort/zone_map` | `ZoneMap` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:128` | 운전 코드 | Publisher | `/voss/voice/say` | `String` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:129` | 운전 코드 | Publisher | `/voss/pallet/state` | `PalletState` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:132` | 운전 코드 | Publisher | `/voss/pallet/result` | `PalletResult` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:137` | 운전 코드 | Subscriber | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:140` | 운전 코드 | Subscriber | `/voss/vision/label` | `LabelRead` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:141` | 운전 코드 | Subscriber | `/voss/voice/intent` | `Intent` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:142` | 운전 코드 | Subscriber | `/voss/log/status` | `String` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:143` | 운전 코드 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:146` | 운전 코드 | Subscriber | `/voss/robot/state` | `RobotState` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:151` | 운전 코드 | Service server | `/voss/sort/command` | `Command` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:152` | 운전 코드 | Action client | `/voss/servo/track_and_grasp` | `TrackAndGrasp` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:153` | 운전 코드 | Service client | `/voss/robot/move_to_zone` | `MoveToZone` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:154` | 운전 코드 | Service client | `/voss/robot/stop` | `Trigger` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:155` | 운전 코드 | Service client | `/voss/vision/read_label` | `ReadLabel` | 리터럴/상수 |
| `src/voss_manager/voss_manager/sort_manager.py:156` | 운전 코드 | Service client | `/voss/log/list_placements` | `ListPlacements` | 리터럴/상수 |
| `src/voss_robot/voss_robot/doosan.py:250` | 운전 코드 | Service client | `prefix + 'aux_control/get_current_tool_flange_posx'` | `GetCurrentToolFlangePosx` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:264` | 운전 코드 | Publisher | `prefix + 'speedl_stream'` | `SpeedlStream` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:272` | 운전 코드 | Service client | `prefix + 'motion/move_stop'` | `MoveStop` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:282` | 운전 코드 | Service client | `prefix + 'system/get_robot_state'` | `GetRobotState` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:294` | 운전 코드 | Service client | `prefix + 'motion/ikin'` | `Ikin` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:295` | 운전 코드 | Service client | `prefix + 'motion/fkin'` | `Fkin` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:296` | 운전 코드 | Service client | `prefix + 'aux_control/get_current_posx'` | `GetCurrentPosx` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:300` | 운전 코드 | Service client | `prefix + 'motion/move_line'` | `MoveLine` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:304` | 운전 코드 | Service client | `prefix + 'motion/check_motion'` | `CheckMotion` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:308` | 운전 코드 | Service client | `prefix + 'motion/move_spline_task'` | `MoveSplineTask` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:311` | 운전 코드 | Subscriber | `ns + 'error'` | `RobotError` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:312` | 운전 코드 | Subscriber | `ns + 'robot_disconnection'` | `RobotDisconnection` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/doosan.py:322` | 운전 코드 | Subscriber | `ns + 'joint_states'` | `JointState` | 동적·확인 필요 |
| `src/voss_robot/voss_robot/robot_gateway.py:107` | 운전 코드 | Publisher | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_robot/voss_robot/robot_gateway.py:150` | 운전 코드 | Subscriber | `/voss/robot/servo_cmd` | `TwistStamped` | 리터럴/상수 |
| `src/voss_robot/voss_robot/robot_gateway.py:155` | 운전 코드 | Service server | `/voss/robot/stop` | `Trigger` | 리터럴/상수 |
| `src/voss_robot/voss_robot/robot_gateway.py:192` | 운전 코드 | Service server | `/voss/robot/gripper` | `Gripper` | 리터럴/상수 |
| `src/voss_robot/voss_robot/robot_gateway.py:278` | 운전 코드 | Service server | `/voss/robot/move_to_zone` | `MoveToZone` | 리터럴/상수 |
| `src/voss_robot/voss_robot/robot_gateway.py:292` | 운전 코드 | Publisher | `/voss/robot/state` | `RobotState` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:379` | 운전 코드 | Subscriber | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:380` | 운전 코드 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:381` | 운전 코드 | Publisher | `/voss/robot/servo_cmd` | `TwistStamped` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:382` | 운전 코드 | Service client | `/voss/robot/stop` | `Trigger` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:383` | 운전 코드 | Service client | `/voss/robot/gripper` | `Gripper` | 리터럴/상수 |
| `src/voss_servo/voss_servo/belt_servo.py:389` | 운전 코드 | Action server | `/voss/servo/track_and_grasp` | `TrackAndGrasp` | 리터럴/상수 |
| `src/voss_servo/voss_servo/emu_rot.py:184` | 진단/대체 | Publisher | `/voss/robot/servo_cmd` | `TwistStamped` | 리터럴/상수 |
| `src/voss_servo/voss_servo/emu_rot.py:185` | 진단/대체 | Service client | `/voss/robot/stop` | `Trigger` | 리터럴/상수 |
| `src/voss_servo/voss_servo/emu_rot.py:216` | 진단/대체 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_servo/voss_servo/fake_box.py:185` | 진단/대체 | Publisher | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_servo/voss_servo/fake_box.py:190` | 진단/대체 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_servo/voss_servo/fake_gripper.py:88` | 진단/대체 | Service server | `/voss/sim/gripper` | `Gripper` | 리터럴/상수 |
| `src/voss_servo/voss_servo/sim_check.py:879` | 진단/대체 | Subscriber | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_servo/voss_servo/sim_check.py:953` | 진단/대체 | Action client | `/voss/servo/track_and_grasp` | `TrackAndGrasp` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:180` | 운전 코드 | Publisher | `/voss/vision/box` | `BoxTrack` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:181` | 운전 코드 | Publisher | `/voss/vision/label_crop` | `LabelCrop` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:184` | 운전 코드 | Subscriber | `/voss/sort/state` | `SortState` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:196` | 운전 코드 | Subscriber | `/voss/robot/pose` | `PoseStamped` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:199` | 운전 코드 | Subscriber | `/camera/color/camera_info` | `CameraInfo` | 리터럴/상수 |
| `src/voss_vision/voss_vision/box_tracker.py:202` | 운전 코드 | Subscriber | `image_topic` | `Image` | 동적·확인 필요 |
| `src/voss_vision/voss_vision/camera_preview.py:38` | 진단/대체 | Subscriber | `image_topic` | `Image` | 동적·확인 필요 |
| `src/voss_vision/voss_vision/camera_preview.py:39` | 진단/대체 | Subscriber | `box_topic` | `BoxTrack` | 동적·확인 필요 |
| `src/voss_vision/voss_vision/label_reader.py:240` | 운전 코드 | Subscriber | `/voss/vision/label_crop` | `LabelCrop` | 리터럴/상수 |
| `src/voss_vision/voss_vision/label_reader.py:246` | 운전 코드 | Subscriber | `/voss/sort/zone_map` | `ZoneMap` | 리터럴/상수 |
| `src/voss_vision/voss_vision/label_reader.py:355` | 운전 코드 | Subscriber | `self.view_topic` | `Image` | 동적·확인 필요 |
| `src/voss_vision/voss_vision/label_reader.py:313` | 운전 코드 | Publisher | `/voss/vision/label` | `LabelRead` | 리터럴/상수 |
| `src/voss_vision/voss_vision/label_reader.py:318` | 운전 코드 | Service server | `/voss/vision/read_label` | `ReadLabel` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:60` | 운전 코드 | Publisher | `/voss/voice/intent` | `Intent` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:61` | 운전 코드 | Publisher | `/voss/voice/say` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:62` | 운전 코드 | Publisher | `/voss/voice/text/reply` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:78` | 운전 코드 | Subscriber | `/voss/sort/zone_map` | `ZoneMap` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:81` | 운전 코드 | Subscriber | `/voss/sort/state` | `SortState` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:84` | 운전 코드 | Subscriber | `/voss/voice/transcript` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/intent_parser.py:87` | 운전 코드 | Subscriber | `/voss/voice/text` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/speech_out.py:42` | 운전 코드 | Subscriber | `/voss/voice/say` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/voice_listener.py:66` | 운전 코드 | Subscriber | `/voss/sort/state` | `SortState` | 리터럴/상수 |
| `src/voss_voice/voss_voice/voice_listener.py:68` | 운전 코드 | Publisher | `/voss/voice/transcript` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/voice_listener.py:69` | 운전 코드 | Publisher | `/voss/voice/status` | `String` | 리터럴/상수 |
| `src/voss_voice/voss_voice/voice_listener.py:70` | 운전 코드 | Publisher | `/voss/voice/say` | `String` | 리터럴/상수 |

총 98개 등록 호출. 조건부 분기와 실행 인자의 실제 값은 이 표만으로 확정할 수 없다. 표준 드라이버 패키지의 내부 등록은 저장소에 없으므로 제외한다.
