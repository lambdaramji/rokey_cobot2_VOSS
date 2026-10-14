# measure_1012 — 3×2 트레이·재확인·팔레타이징 시연 (10/12~13, 로컬 브랜치 `local/1012-recheck-flow`)

실로봇을 움직이는 것은 모두 사람이 비상정지 옆에서 실행한다.

## 시나리오
1. 벨트 20개: A·B·C 6개씩(칸 순서 2→5→1→4→0→3) + 흐린 송장 2개.
2. 재확인은 v1.5 즉시 흐름이다(`sort_manager.yaml` `defer_recheck: false`, 10/13 PL Q20): 흐린 송장 박스를 재확인 칸에 놓고 바로 다시 읽고, 못 읽으면 바로 묻는다(1·2위 + 보류, 후보 없으면 전체). 30초 답이 없으면 HOLD.
   첫 박스: 작업자가 동을 답함 → 그 구역 칸 6(칸 0 위 2층). 두 번째: `송장 확인 불가` → HOLD.
   - 폴백: 10/14 리허설 1회차에서 즉시 흐름이 실패하면 `defer_recheck: true` 로 되돌린다 — 10/12·10/13 게이트 방식(재확인 칸 0·1 에 보관하고 분류 계속, 작업자가 `재확인 시작`이라고 하면 칸 순서대로 다시 읽고 묻기).
3. 벨트를 끄고 `대치, 역삼, 청담 순서로 실어줘` → 팔레타이징(BRD v1.5 10.4, `pallet_fsm`). **말한 순서 = 배송 순서**(첫 배송지부터, 10/13 PL — `docs/interfaces/voss_msgs.md`). 첫 배송지(대치)가 문 쪽 4열, 마지막 배송지(청담)가 트럭 머리 1열.
   - 16칸을 넘으면 물량 많은 동부터 싣는다(같으면 먼저 배송하는 동이 후순위). 예: 역삼 7·대치 6·청담 6 → 청담 6(1~6), 역삼 7(7~13), 대치 3(14~16), **대치 3개 초과**(10/13 게이트 실기와 같음).
   - 구역 안은 2층 박스부터(10/13 cc1d0fe), 같은 층은 칸 번호 순. HOLD·재확인 칸 박스는 싣지 않는다.
   - (10/12 로컬 브랜치의 "말한 순서 = 싣는 순서(트럭 안쪽부터)" 해석은 쓰지 않는다.)

칸 번호
- A·B·C: 위 줄(+Y) 0·1·2, 아래 줄 3·4·5. 2층 6 = 칸 0 위.
- 팔레트: 칸 = 층×8 + 줄×4 + 열(열 0 = −X = 트럭 머리, 줄 0 = +Y). 적재 순서 0·4 → 8·12 → 1·5·9·13 → 2·6·10·14 → 3·7·11·15.

## 시험 스크립트 (T2 브링업 + T3 robot_gateway 만 띄우고, sort_manager·belt_servo 는 끈 상태)
- `empty_test.sh ZONE 칸...` — 빈손으로 칸마다 MoveToZone PLACE (예: `PALLET 0 4 8 12 3 7 11 15`)
- `place_test.sh [구역...|fill <2층 구역>|PALLET]` — 사람이 그리퍼에 박스를 넣고 칸에 놓기. `fill A` = 시연 상태 19개, `PALLET` = 적재 순서대로 16칸
- 팔레타이징은 시험 스크립트 없이 sort_manager `palletize` 로만 한다(경로 뜻이 반대이던 `pallet_test.sh` 는 10/13 Q19 로 삭제).

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
| 9 | `ros2 launch voss_manager sort_manager.launch.py` (시작 줄: `defer_recheck False`(폴백 때 True), `팔레트 16칸`) |
| 10 | `ros2 run voss_voice intent_parser` |
| 11 | `ros2 run voss_voice voice_listener --ros-args -p mode:=text` (OpenAI 키 장애로 텍스트 입력) |
| 13 | `ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: start}"` |

- T2 전에 펜던트 툴·TCP = **GripperDA_v1** 인지 확인한다(docs/g0-runbook.md). T3 시작 줄이 `컨트롤러 TCP 등록 voss_config 와 같음 (차 0.0 mm)` 이어야 한다.
  `TCP 등록 없음 → 플랜지 좌표로 명령` 이면 움직이긴 하지만 펜던트 공간 제한이 핑거 끝을 막지 못한다(10/12 실기가 이 상태였다).
- T3 시작 줄에서 PALLET 구역, vel [450.0, 45.0], acc [900.0, 90.0], blend 30.0 mm 를 확인한다.
- 팔레타이징은 T11 텍스트 대신 `"{command: palletize, arg: '대치동,역삼동,청담동'}"` 로도 된다. 멈춤 `stop`, 이어서 `resume`.
- 다시 하려면 팔레트를 비우고 `stop` → `reset_zone PALLET` → `resume`.

## 공용 PC 실값 (레포 밖 `~/voss_ws/config/`)
- `voss_config.yaml` = 이 폴더의 `voss_config.demo.yaml` (10/13 sha256 앞 12자리 c829cb0f3e21 — 10/12 의 39bf41a1bbe9 에서 `truck` → `pallet`, 적재 순서 order 추가).
  복원: `cp scripts/measure_1012/voss_config.demo.yaml ~/voss_ws/config/voss_config.yaml`.
  레포 `config/voss_config.yaml` 은 3×1 그대로 둔다(테스트가 그 값을 기준으로 함).
- `belt_servo_real.yaml` 은 커밋 금지 파일이라 값만 적는다.
  - 10/12 시연값: `z.lift_done_below_mm: 30.0`(LIFT 를 목표 30 mm 아래에서 끝냄, P 꼬리 2.7 s → 0.9 s), `zero_hold_s: 0.2`(0.5 → 0.2). 백업 `belt_servo_real.before_1012_u9.yaml`.
  - 10/12 저녁 U9 시험(박병후님) 뒤 공용 PC 파일은 U9 값이다. 시연값으로 돌릴지는 박병후님과 정한다. 그리퍼 50 mm 개방 튜닝도 박병후님이 진행 중(10/13).

## 10/12 저녁 결과 (bag `~/voss_data/1012/scenario_02`, 이전 이름 TRUCK·STAY·load_truck, 층 단위 적재 순서)
- 벨트 20개 모두 시도 1 파지. 18개 A·B·C 6개씩, 흐린 2개 재확인 칸 0·1.
- 재확인: 역삼동 답 → A 칸 6, 송장 확인 불가 → HOLD 칸 0.
- 트럭: 역삼동·대치동·청담동 → A 7(6,3,0,4,1,5,2) · B 6(3,0,4,1,5,2) · C 3(3,0,4) = 16/16, 남은 C 3개, OBSERVE 복귀.
- 파지 뒤 LIFT→VERIFY 0.97 s, VERIFY→구역 출발 0.2 s (전에는 약 3 s 멈춤). 트럭 1개당 약 9.6 s (16개 153 s).
- 알람 해결: 원호(move_spline_task) 앞뒤 블렌딩 금지 + check_motion IDLE 대기 (1203·1903).
- 16칸 모두 트레이 안 경로 없이 칸 바로 위에서 수직으로 내려가 놓았다(gateway 로그). 그래서 10/13 의 열 단위 적재 순서에서도 경로는 같다. 옆 열에 2층이 먼저 쌓인 상태로 놓는 것은 새 상황이라 1회 실기 확인이 필요하다.
