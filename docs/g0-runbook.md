# G0 실행 절차서 (10/10 오전, 공용 PC)

G0 = 실물 박스 **1개**를 인식 → 이동 중 픽업 → 기본 구역 적재 → DB commit·같은 box_id 조회 → OBSERVE 복귀까지 한 번에 보내는 첫 연결(SRD v1.0 8.2, `docs/plan.md` "G0 준비"). 시작 입력만 모의 허용 — 음성·HMI 없이 `/voss/sort/command` 를 사람이 부른다. 음성·HMI·다단 OCR·재확인·질문·보류는 G0 에 없다.

> **로봇·벨트·그리퍼를 움직이는 명령(launch, 서비스 호출)은 모두 사람이 비상정지 옆에서 실행한다**(CLAUDE.md 규칙 6). `stop` 명령은 소프트웨어 정지일 뿐 안전 등급이 아니다(SR-NF-09) — 위험하면 비상정지 버튼.

## 역할
| 역할 | 사람 | 하는 일 |
|---|---|---|
| 판정·진행 | 남현지 (PL) | 순서 진행, 명령 입력, 증거 확인, 판정 기록 |
| 로봇·비상정지 | 김학민 | 브링업·게이트웨이, **비상정지 버튼 앞 대기(명령 입력과 겸하지 않는다)**, 속도·작업 영역 제한 확인 |
| 추종·파지 · **벨트 정지** | 박병후 | belt_servo 기동·로그, 파지 실패 원인 판정, **벨트 12 V 전원 스위치 앞 대기** |
| 기록·촬영 | 정의석 | DB 컨테이너·sort_logger, commit 로그·SELECT, **휴대폰으로 로봇·트레이 연속 촬영**(실물 영상 증거) |

> **로봇 비상정지는 벨트를 멈추지 않는다**(아두이노 12 V 별도). 박스가 끼거나 떨어지면 벨트 담당이 12 V 를 끈다. 아두이노 시리얼 포트를 열거나 RESET 하면 보드가 재시작해 **벨트가 바로 돈다**(`tools/README.md`) — 회차 중 포트를 건드리지 않는다.

## 0. 전제 — G0 전에 돼 있어야 하는 것
| 항목 | 담당 | 10/08 현재 | 확인 방법 |
|---|---|---|---|
| main 머지: #75 ✅ → #97 (label_reader) | 남현지 · 리뷰 병후·학민 | #75 머지, #97 승인·CI 중 | `git log main` |
| main 머지: #90 → #95 (핸드아이·box_tracker) | 남현지 · 리뷰 학민·병후 | #90 승인·CI 중, #95 병후 재리뷰 대기 | 〃 |
| main 머지: #96 (sort_manager) ✅, #99 (ADR-0011·measurements-1008) ✅, #103 (TrackAndGrasp feedback = phase 만) ✅ | — | 머지됨 | 〃 |
| main 머지: #94 (sort_logger·DB) ✅ | 정의석 | 머지됨 | 〃 |
| main 머지: #100 (MoveToZone STOPPED·OBSERVE 이동만) ✅ | 김학민 | 머지됨 | 〃 |
| robot_gateway `servo_cmd` → speedl_stream(**퍼블리셔 reliable**) + 만료 watchdog 200 ms·**TCP z 하한 clamp**·추종 구간 x·`stop`(F-04) | 김학민 | #104 (F-04 5 mm/s 실측, 리뷰 중) | ADR-0010·measurements 의 F-04 수치 |
| robot_gateway `move_to_zone`(PLACE·OBSERVE, STOPPED 코드)·`gripper`·`/voss/robot/state` | 김학민 (T32 ⑤) | PR 전 | `ros2 service list`, `ros2 topic echo --once /voss/robot/state` |
| belt_servo `/voss/servo/track_and_grasp` 액션 | 박병후 (#36) | U1 액션 골격 PR 10/08 15:30 · U2 FF+P 추종 18:00 · **U5 파지 시퀀스 22:00 이후** | `ros2 action list`, **TrackAndGrasp 1회 인계는 U5 뒤 — 10/10 오전 G0 직전** |
| 카메라 USB 케이블 손목에 여유 고리로 고정, `lsusb -t` 에서 RealSense 5000M | 김학민 | ✅ 10/08 (Bus 002 5000M, 팔에 고정) | G0 직전 `lsusb -t` 한 번 더 |
| 아두이노가 레포 `conveyor_test`(h250) 스케치인지 | 김학민 | ✅ 10/08 다시 올림(전에는 h500 옛 스케치) | 벨트 4.8 cm/s 근처 |
| 공용 PC PaddleOCR venv | 남현지 (아래 1-3) | 없음 | `label_reader` 가 "판독 준비 완료" |

**머지 순서**(충돌 최소): **#98(아이디 변경)을 먼저** — CODEOWNERS 가 옛 아이디라 지금은 리뷰어가 자동으로 붙지 않는다 → #99 → #90 → #95(main 을 받아 맞춘 뒤) → #75 → #97(base 를 main 으로 바꾼 뒤) → #100 → #96 → #94 → 학민·병후 PR. 각 PR 은 CODEOWNERS 승인 뒤 squash. **G0 는 main 한 커밋에서 돌리고 그 해시를 기록한다.**

**10/08 저녁 리허설(로봇 시간 우선순위):** ① gateway watchdog·종료 시험(학민, 추종 속도 48 mm/s 에서 watchdog 초과 거리 포함) → ② **goal 수락 → TRACK 추종 → cancel 때 0 속도 정지**까지(병후 U2, 파지 없음) → ③ 아래 2~4 를 박스 없이 start → OBSERVE → stop 까지. **파지 1회 인계는 10/10 오전 G0 직전**(병후 U5).

## 1. 공용 PC 준비 (10/10 08:30 전, 1회)
### 1-1 코드·빌드 — 학민님이 게이트웨이 작업을 push 한 뒤
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS && git status            # 바뀐 파일이 없어야 한다
git switch main && git pull
git worktree remove ~/voss_bt; git worktree remove ~/voss_sm  # 10/08 측정용 작업 폴더 정리
cd ~/voss_ws && colcon build --symlink-install                # voss_msgs 가 바뀌어 전체 다시 빌드
git -C ~/voss_ws/src/rokey_cobot2_VOSS log --oneline -1       # ← 이 해시를 기록
```
- 10/08 확인용 오버레이 `~/voss_sm_ws` 는 **source 하지 않는다**(지워도 된다).

### 1-2 설정 파일 — 모든 노드가 같은 파일을 읽게
```bash
mkdir -p ~/voss_ws/config
diff ~/voss_ws/config/voss_config.yaml ~/voss_ws/src/rokey_cobot2_VOSS/config/voss_config.yaml   # 다르면 멈추고 학민님과 맞춘다(레포가 원본)
cp ~/voss_ws/src/rokey_cobot2_VOSS/config/{voss_config.yaml,belt_homography.yaml,hand_eye.yaml} ~/voss_ws/config/
sha256sum ~/voss_ws/config/*.yaml
```
- 게이트웨이는 `~/voss_ws/config/voss_config.yaml`, 비전·sort_manager 는 `VOSS_CONFIG_DIR` 를 읽는다 → 아래 환경 파일로 같은 폴더를 가리킨다.

### 1-3 PaddleOCR venv (label_reader, 처음 한 번)
```bash
python3 -m venv --system-site-packages ~/.venvs/voss_ocr     # rclpy 를 같이 쓰려고 system-site-packages
~/.venvs/voss_ocr/bin/pip install paddlepaddle==3.3.1 paddleocr==3.7.0
```
- 첫 실행 때 모델(약 100 MB)을 내려받는다(인터넷 필요). 시연장 네트워크가 불안하면 개인 PC `~/.paddlex/official_models` 를 Drive 로 옮겨 같은 경로에 둔다.

### 1-4 DB (정의석, `docker/db/README.md`)
```bash
sudo mkdir -p /var/lib/voss/pgdata /var/lib/voss/spool && sudo chown $USER /var/lib/voss/spool
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/db && docker compose up -d && docker compose ps   # healthy
```

### 1-5 터미널 공통 환경 파일 (한 번 만들고 모든 터미널에서 `source ~/voss_g0_env.sh`)
```bash
cat > ~/voss_g0_env.sh <<'EOF'
source /opt/ros/jazzy/setup.bash
source ~/cobot2_ws/install/setup.bash
source ~/voss_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export VOSS_CONFIG_DIR=$HOME/voss_ws/config
EOF
```

## 2. 기동 순서 (터미널마다 `source ~/voss_g0_env.sh` 먼저)
| T | 무엇 | 명령 | 누가 | 정상 표시 |
|---|---|---|---|---|
| 1 | 두산 브링업 | `ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=<로봇 컨트롤러 IP> port:=12345 model:=m0609` (IP 는 `scripts/measure_1006/servo_stream_check.md`·현장 메모 — 공개 레포라 여기 적지 않는다) | 학민 · **비상정지** | `dsr_controller2` active, 펜던트 AUTONOMOUS·STANDBY |
| 2 | robot_gateway | `ros2 launch voss_robot robot_gateway.launch.py dry_run:=false` (config 기본 `~/voss_ws/config/voss_config.yaml`). **`dry_run` 기본이 true** — 빼먹으면 로봇이 안 움직이고 가짜 pose 가 나온다 | 학민 · **비상정지** | `voss_config version=1 sha256=<12자리>`, `robot_gateway started: real …`(**real 확인**), 5초마다 `pose 50.0 Hz, rtt …` · FAULT 없음 |
| 3 | 카메라 (노드 하나만) | `ros2 launch realsense2_camera rs_launch.py camera_namespace:=/ camera_name:=camera enable_depth:=false rgb_camera.color_profile:=1920,1080,30 rgb_camera.enable_auto_exposure:=false` 뒤 `ros2 param set /camera rgb_camera.exposure 60`, `… enable_auto_white_balance false`, `… white_balance 4600.0` | 남현지 | 30 fps |
| 4 | sort_logger (**sort_manager 보다 먼저**) | `export VOSS_DB_LOGGER_PASSWORD=<.env 값>` → `ros2 run voss_hmi sort_logger` | 정의석 | `/voss/log/status` STARTING → OK |
| 5 | box_tracker | `ros2 launch voss_vision box_tracker.launch.py` | 남현지 | 시작 줄 `hand_eye=2026-10-08T11:21:40 moving_verified=True pose_lag=60 ms`, 5초 로그 ≈ 30 Hz·WARN 없음 |
| 6 | label_reader | `ros2 launch voss_vision label_reader.launch.py python:=$HOME/.venvs/voss_ocr/bin/python` | 남현지 | "OCR 엔진 준비" (판독 준비 완료는 T8 뒤 zone_map 을 받으면) |
| 7 | belt_servo | `ros2 launch voss_servo belt_servo.launch.py <파라미터 파일>` — 정확한 인자는 박병후 U1 PR 본문(머지 뒤 이 칸 확정) | 박병후 · **비상정지** | `READY` 로그 + 파라미터 sha256 한 줄 |
| 8 | sort_manager | `ros2 launch voss_manager sort_manager.launch.py` | 남현지 | voss_config sha256 로그(T2·T6 과 같은 값) |
| 9 | 명령·관측 | 아래 3·4 | 남현지 | |

## 3. 시작 전 확인 (모두 ✅ 여야 start)
```bash
ros2 daemon stop                                   # 오래된 그래프 정보 지우기 (10/08: 토픽이 안 보였던 원인)
ros2 topic echo --once /voss/sort/state            # ready: true, not_ready: []
ros2 topic hz /voss/robot/pose                     # ≈ 50 Hz
ros2 topic echo --once /voss/log/status            # OK
```
- [ ] T6 label_reader 에 "판독 준비 완료 — /voss/vision/label 발행 시작"
- [ ] voss_config sha256 이 T2·T6·T8 로그에서 같다(셋 다 앞 12자리로 비교)
- [ ] 트레이 A·B·C 비어 있음 (새 세션 start 때 칸 카운터가 0 이 된다)
- [ ] 벨트 h250(10/08 실측 4.77 cm/s, measurements-1008 #10), 벨트 위 비어 있음, 송장 박스 1개 준비(명확한 송장, 예 S07-02 대치동 → B)
- [ ] 비상정지 대기자(학민)·벨트 12 V 담당(병후) 위치

**박스 회차 Go/No-Go — 하나라도 ☐ 이면 박스 회차를 하지 않고 박스 없는 start → OBSERVE → stop 까지만 한다**(ADR-0010: gateway 가 죽으면 speedl 이 계속 간다):
- [ ] F-04 기록 있음(학민): servo_cmd 만료 watchdog 값, 움직이는 speedl 에 move_stop 이 걸림, gateway 강제 종료 때 로봇 거동 — measurements 에 수치
- [ ] gateway 기동 로그에 속도 상한·TCP z 하한(ADR-0010 조건 7) 값이 찍힘
- [ ] 펜던트 안전 설정 공간 제한(벨트 위 TCP z 하한·추종 구간 x)이 켜져 있음 — ROS 와 무관하게 동작하는 마지막 방어선(ADR-0010 리스크)
- [ ] TrackAndGrasp 1회 인계 성공 기록(10/10 오전 G0 직전, 박병후 U5 뒤 — 10/08 저녁에는 추종·cancel 까지만)
- [ ] 1회차는 벨트 h500(2.38 cm/s, measurements-1008 #10)로, 성공하면 h250

- [ ] 증거 녹화 시작(아래), 휴대폰 촬영 시작
```bash
mkdir -p ~/voss_data/1010
ros2 bag record -s mcap -o ~/voss_data/1010/g0_01 --include-hidden-topics \
  /voss/sort/state /voss/sort/result /voss/vision/box /voss/vision/label \
  /voss/robot/pose /voss/robot/state /voss/robot/servo_cmd /voss/log/status /rosout \
  /voss/servo/track_and_grasp/_action/feedback /voss/servo/track_and_grasp/_action/status \
  /camera/color/image_raw/compressed /camera/color/camera_info
```
(`/rosout` 에 노드 로그 — `db_committed`·파지·적재 로그가 시각과 함께 남는다. 1080p 압축 영상이라 3분에 약 2~3 GB.)

## 4. 실행 (사람이 비상정지 옆에서)
1. **start** — 로봇이 OBSERVE 로 먼저 간다(sort_manager `home_first`).
   ```bash
   ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: start}"
   ```
   → `ok: True`, `/voss/sort/state` RUNNING, session_id 기록.
2. **박스 1개**를 벨트 상류에 올린다(송장 위로). 손은 화면 밖으로 빨리 뺀다.
3. 로그 순서 확인:
   - T6 `track N s1: S07-02 대치동 … → 투표 대치동 …`
   - T8 `…-001 track N 대치동→B 칸 0 파지 시작` → servo phase 로그 → `파지 완료(시도 k) → B 칸 0 적재` → `적재 완료` → `SortResult …-001 PLACED B`
   - T4 `db_committed box_id=…-001 at=…`
   - 로봇이 OBSERVE 로 돌아오고 state 가 RUNNING
4. **stop** — `ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: stop}"` → PAUSED, "로봇 정지 요청 성공". stop 뒤 **그리퍼에 박스가 있는지** 본다 — 있으면 아래 6절 비상정지 복구 ⑤ 로 연 뒤 resume(그대로 resume 하면 다음 PREPARE 사전 개방에서 벨트로 떨어진다).
5. **같은 box_id 조회**(정의석):
   ```bash
   cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/db && docker compose exec db psql -U voss_admin -d voss -c \
     "SELECT box_id, session_id, result, zone, attempts, finished_at, inserted_at FROM sort_log WHERE box_id = '<ID>';"
   ```
6. 녹화(Ctrl-C)·촬영을 멈춘다.

## 5. 판정 — G0 증거 (SRD 8.2)
| 증거 | 어디서 | 통과 |
|---|---|---|
| 실물 영상: 벨트 위 박스 → 이동 중 파지 → B 트레이 칸 0 → OBSERVE 복귀 | 휴대폰 영상 | ☐ |
| box_id·track_id·goal·attempts 가 한 박스로 이어짐 | SortResult, T8 로그 | ☐ |
| OCR(code·dong·신뢰도)과 좌표(BoxTrack `position_base`, 추종 중 `source=2 HAND_EYE`, `valid=true`) | bag `/voss/vision/label`·`/voss/vision/box` | ☐ |
| 파지 인계: TrackAndGrasp `OK`·`grasped=true`(LIFT·VERIFY 완료) | bag action status·feedback, T7 로그 | ☐ |
| 적재: `placed_stamp`(SortResult.stamp)와 영상의 개방 순간 대조 | SortResult + 영상 | ☐ |
| OBSERVE 복귀·다음 관측 준비(state RUNNING) | `/voss/robot/pose`, `/voss/sort/state` | ☐ |
| DB commit 로그 뒤 같은 box_id SELECT 1행 | T4 로그, 4-5 출력 | ☐ |
| 회차 동안 `/voss/log/status` 가 한 번도 `DB_ERROR` 아님 (DB_ERROR 회차는 G0 증거로 쓰지 않고 기록만 남긴다) | bag `/voss/log/status` | ☐ |

**회차 기록**(measurements-1010 에 옮긴다): 회차 · 시각 · main 해시 · box_id · 결과(outcome·reason·attempts) · 원인 · 증거 경로(Drive `raw/1010/g0_NN/`). 실패 회차도 지우지 않는다.

## 6. 문제가 생기면
| 증상 | 원인 후보 | 조치 |
|---|---|---|
| start 거부 `준비 안 됨: LOG` | DB·비밀번호·스풀 폴더, sort_logger 미기동 | T4 로그, `docker compose ps` |
| `준비 안 됨: OCR` | label_reader 엔진 로딩 중·실패, zone_map 미수신 | T6 로그. sort_manager 가 떠야 zone_map 이 온다 |
| `준비 안 됨: ROBOT` | pose 끊김, move_to_zone 없음, RobotState 가 READY/STOPPED 아님, 직전 stop 응답 실패 | 학민 확인. stop 실패였으면 stop 을 다시 보내 성공을 받은 뒤 resume |
| `준비 안 됨: SERVO` / `VISION` | belt_servo / box_tracker 미기동 | T7 / T5 |
| box_tracker `영상 … Hz < 25` WARN | 카메라 USB 끊김 | 비상정지 판단 → 케이블 확인 → **카메라 노드(T3)만** 다시 띄운다(box_tracker 는 그대로) |
| 판독이 계속 `대기 LOW_CONF`·`UNKNOWN` | 흐림·반사·송장 가림 | G0 는 명확한 송장만. 박스를 바꾼다(불확실한 박스는 집지 않는다) |
| 파지 실패(`GRASP_FAILED`·`LOST`·`OUT_OF_REACH`·`STALE_INPUT`) | 추종·좌표·지연 | FAILED + PAUSED, **자동 개방·복귀 없음** → 그리퍼·박스를 사람이 확인·치움 → `resume`(OBSERVE 로 이동) |
| 적재 실패(`GRIP_FAIL`·`TIMEOUT`·`RETURN_FAILED`) | 게이트웨이·RG2 | PAUSED. RETURN_FAILED 면 박스는 칸에 있고 로봇이 OBSERVE 아님 → 학민 확인 뒤 resume |
| `구역 가득` PAUSED | 칸 3개 다 참 | 트레이 비우고 `{command: reset_zone, arg: B}` → resume |
| 비상정지를 눌렀다 · stop 때 박스를 쥔 채 멈췄다 | — | **복구(학민):** ① 원인 제거·주변 확인 → ② 비상정지 해제, 펜던트 알람 리셋·서보 온 → ③ T2 로그에 FAULT(두산 응답 없음 3회)가 있으면 gateway(T2)만 다시 띄운다(T8 sort_manager 는 그대로) → ④ RobotState connected·state STOPPED, pose 50 Hz 확인 → ⑤ 그리퍼에 박스가 있으면 한 사람이 박스를 받치고 학민이 연다: `ros2 service call /voss/robot/gripper voss_msgs/srv/Gripper "{width: 90.0, force: 14.0}"` → ⑥ `stop` 성공 확인 → ⑦ `resume`. **T32 ⑤ PR(RobotState·gripper) 전 리허설:** ④ 는 pose 50 Hz 만, ⑤ 는 펜던트에서 RG2 를 연다 |
| `ros2` 명령에 토픽·서비스가 안 보임 | CLI 데몬의 오래된 정보 | `ros2 daemon stop` |

## 7. 끝나면
- 끄는 순서: ① `stop` → PAUSED·로봇 OBSERVE 정지 확인 → ② 벨트 12 V 끄기 → ③ T8 sort_manager → T7 belt_servo → T6 → T5 → T4 → T3 → T2·T1(학민). belt_servo 를 gateway 보다 먼저 끈다(끊기면 watchdog 이 정지).
- 증거를 Drive `raw/1010/g0_NN/` 에: bag 폴더, 휴대폰 영상, T2·T4·T5·T6·T7·T8 로그(복사), SELECT 출력, main 해시. **레포에는 넣지 않는다**(규칙 8).
- `docs/measurements-1010.md` 회차 표, `docs/plan.md` G0 결과 줄을 PL 이 갱신한다. 정상 G0 와 DB 장애·스풀 복구 시험은 따로 한다(SRD 8.2).
