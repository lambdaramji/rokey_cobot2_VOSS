# measure_1012 — 3×2 트레이·재확인·트럭 적재 시연 (10/12, 로컬 브랜치 `local/1012-recheck-flow`)

실로봇을 움직이는 것은 모두 사람이 비상정지 옆에서 실행한다.

## 시나리오
1. 벨트 20개: A·B·C 6개씩(칸 순서 2→5→1→4→0→3) + 흐린 송장 2개는 재확인 칸 0·1 에 보관.
2. `재확인 시작` → 첫 박스: 작업자가 동을 답함 → 그 구역 칸 6(칸 0 위 2층). 두 번째: `송장 확인 불가` → HOLD.
3. 벨트 끄고 `역삼동, 대치동, 청담동 순으로 트럭에 실어` → 말한 동 순서로 구역 칸에서 집어 트럭(4×2×2층 = 16)에.
   구역 안은 놓은 순서의 역순, 16개면 끝(남은 3개는 다음 트럭), HOLD 는 싣지 않음.

칸 번호: 위 줄(+Y) 0·1·2, 아래 줄 3·4·5. 2층 6 = 칸 0 위. 트럭은 0~7 이 1층, 8~15 가 같은 자리 2층.

## 시험 스크립트 (T2 브링업 + T3 robot_gateway 만 띄우고, sort_manager·belt_servo 는 끈 상태)
- `empty_test.sh ZONE 칸...` — 빈손으로 칸마다 MoveToZone PLACE (예: `TRUCK 0 7 3 4`)
- `place_test.sh [구역...|fill <2층 구역>|TRUCK]` — 사람이 그리퍼에 박스를 넣고 칸에 놓기. `fill A` = 시연 상태 19개
- `pallet_test.sh <2층 구역> 동1 동2 동3` — 구역 칸 PICK → 트럭 STAY. `AUTO=1` 이면 Enter 없이

## 전체 실행 (터미널마다 `source ~/voss_g0_env.sh` 먼저)
| T | 명령 |
|---|---|
| 1 | `cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/db && docker compose up -d` |
| 2 | `ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100 port:=12345 model:=m0609` |
| 3 | `ros2 launch voss_robot robot_gateway.launch.py dry_run:=false pose_source:=joint_states zone_vel_mm_s:=450 zone_acc_mm_s2:=900 zone_blend_mm:=30` |
| 4 | `ros2 run realsense2_camera realsense2_camera_node --ros-args -r __ns:=/ -r __node:=camera -p enable_color:=true -p enable_depth:=false -p enable_infra1:=false -p enable_infra2:=false -p enable_accel:=false -p enable_gyro:=false -p rgb_camera.color_profile:=1920x1080x30 -p rgb_camera.enable_auto_exposure:=false -p rgb_camera.exposure:=60 -p rgb_camera.enable_auto_white_balance:=false -p rgb_camera.white_balance:=4600.0 -p initial_reset:=true` |
| 5 | `export $(grep '^VOSS_DB_LOGGER_PASSWORD=' docker/db/.env)` 후 `ros2 run voss_hmi sort_logger` |
| 6 | `ros2 launch voss_vision box_tracker.launch.py` |
| 7 | `ros2 launch voss_vision label_reader.launch.py python:=$HOME/.venvs/voss_ocr/bin/python` |
| 8 | `ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml log_dir:=$HOME/voss_ws/src/rokey_cobot2_VOSS/data/servo` |
| 9 | `ros2 launch voss_manager sort_manager.launch.py` (시작 줄: `defer_recheck True`, `트럭 16칸`) |
| 10 | `ros2 run voss_voice intent_parser` |
| 11 | `ros2 run voss_voice voice_listener --ros-args -p mode:=text` (OpenAI 키 장애로 텍스트 입력) |
| 13 | `ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: start}"` |

T3 시작 줄에서 TRUCK 구역, vel [450.0, 45.0], acc [900.0, 90.0], blend 30.0 mm 를 확인한다.
트럭 적재는 T11 텍스트 대신 `"{command: load_truck, arg: '역삼동,대치동,청담동'}"` 로도 된다. 멈춤 `stop`, 이어서 `resume`.

## 공용 PC 실값 (레포 밖 `~/voss_ws/config/`)
- `voss_config.yaml` = 이 폴더의 `voss_config.demo_1012.yaml` (sha256 앞 12자리 39bf41a1bbe9). 복원: `cp scripts/measure_1012/voss_config.demo_1012.yaml ~/voss_ws/config/voss_config.yaml`.
  레포 `config/voss_config.yaml` 은 3×1 그대로 둔다(테스트가 그 값을 기준으로 함).
- `belt_servo_real.yaml` 은 커밋 금지 파일이라 바꾼 값만 적는다 (백업 `belt_servo_real.before_1012_lift.yaml`):
  - `z.lift_done_below_mm: 30.0` — LIFT 를 목표 30 mm 아래에서 끝냄 (P 꼬리 2.7 s → 0.9 s)
  - `zero_hold_s: 0.2` (0.5 → 0.2)

## 10/12 저녁 결과 (bag `~/voss_data/1012/scenario_02`)
- 벨트 20개 모두 시도 1 파지. 18개 A·B·C 6개씩, 흐린 2개 재확인 칸 0·1.
- 재확인: 역삼동 답 → A 칸 6, 송장 확인 불가 → HOLD 칸 0.
- 트럭: 역삼동·대치동·청담동 → A 7(6,3,0,4,1,5,2) · B 6(3,0,4,1,5,2) · C 3(3,0,4) = 16/16, 남은 C 3개, OBSERVE 복귀.
- 파지 뒤 LIFT→VERIFY 0.97 s, VERIFY→구역 출발 0.2 s (전에는 약 3 s 멈춤). 트럭 1개당 약 9.6 s (16개 153 s).
- 알람 해결: 원호(move_spline_task) 앞뒤 블렌딩 금지 + check_motion IDLE 대기 (1203·1903).
