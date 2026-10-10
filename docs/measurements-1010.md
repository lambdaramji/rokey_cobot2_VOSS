# 10/10 실측·확인 (셋업 · ①② · G0 · G1 · VIEW·15칸 · #41)

값은 **여기에만** 적는다. 측정은 공용 PC(ms-03, ROS_DOMAIN_ID 30), 비상정지 김학민. 기록은 Claude(공용 PC 세션)가 로그·출력·파일에서 옮겨 적었다.
이 문서는 관측값과 근거만 적고, 추측은 *(추측)* 으로 따로 표시한다. **voss_servo(belt_servo 추종·파지) 관련 항목**(#4·#5·#6·#10, belt_servo 로그·파라미터)의 판정·해석은 박병후 님이 한다. 그 밖의 항목(공간 제한·pose 지연·특이점·로봇 관절·파지 힘·카메라 등)은 박병후 님 판단으로 넘기지 않는다.
원본(bag·CSV·로그·사진)은 Drive `raw/1010/` (레포에 넣지 않는다). 아래 경로는 공용 PC 기준.
시각은 KST. epoch 는 ROS 로그 값.

## 요약표 (체크리스트 C 번호)

| # | 항목 | 시각 | 결과 (값·단위) | 근거 |
|---|---|---|---|---|
| 0 | 셋업·버전 | 10:5x~11:06 | main `280f786` 빌드(8 패키지), voss_config sha256 앞 12 `db97243ec6ef`, 펜던트 TCP `GripperDA_v1`, gateway real·100 mm/s·z ≥ 78·x −107~638·TCP 차 0.0 mm | 아래 "0. 셋업" |
| 1 | 벨트 면 z · 벨트 y · 프레임 | 11:4x~12:0x | **닫힘(보고 37~38) 접촉 TCP z: x −107 → 73.53, x 300 → 74.0, x 620 → 76.0.** 열림(보고 90.4) 접촉: 56 / 59 / 측면 프레임 53.0. 벨트 가장자리(프레임 포함, x 300) y −243.21 / −315.0 | 아래 "1." |
| 2 | 펜던트 공간 제한 | 12:0x~12:23 | 직육면체 베이스 P1 (−150, −350, −50) · P2 (700, −208, 77), **유효 공간 외부**, 검사 TCP, 마진 0. 조그 하강 **77.45 에서 정지**. A1·C2·HOLD1 PLACE 통과 | 아래 "2." · 펜던트 사진 3장 |
| 3 | pose 지연 (gateway `pose_source:=joint_states`) | 12:32~12:36 | pose 값 갱신 간격 중앙값 **20 ms**, 고른 lag **15 ms**(기울기 확인 15), 이동 중 RMS 0.11·**최대 0.31 mm**, 정지 최대 0.23 mm (lag 60 이면 이동 최대 2.18 mm) | `pose_lag_js_01/`, `pose_lag_js_01_eval.txt`, `.csv` |
| 4 | VERIFY 재닫기 (39 mm·14 N) | 13:07~13:12 | 파지 1677 ms·폭 41.1·grip True → LIFT 뒤 재닫기 5회: **167·168·167·173·171 ms, 모두 폭 41.1·grip True**. 처짐 보고 없음 | gateway 로그, `goto/*.csv` |
| G1 | G1 s1 (sort_manager) | 16:44~17:15 | **20사례 중 20 OK, 모두 시도 1**(gate_summary). 무효 6(의도 시험: 기울임·뒤집기) | 아래 "G1 시리즈 s1"·"의도 시험" |
| 5 | ① 추종·cancel (Kp 0) | 14:18~14:56 | goal 6회: LOST 2 · OUT_OF_REACH 2 · **CANCELED 2 (STOP_OK, TRACK 1.5 s·4.5 s 뒤 취소)**. Kp 0 전 구간 2회: z 140.8 유지, 벨트 방향 간격 −75~−93 mm, 가로 ≤ 3.8 mm. 취소 때 gateway move_stop 2회 ok | 아래 "5." |
| G0 | G0 1회차 (런북 4장) | 16:08~16:13 | **box `…-001` 대치동 → B 칸 0 PLACED, TrackAndGrasp OK 시도 1, DB 1행** | 아래 "G0 1회차" |
| 6 | ② TrackAndGrasp 1회 (Kp 1.0) | 15:26 | **`grasped: true`, `reason: OK`, attempts 1**, 11.4 s. 정렬 TCP x **90.7**(문턱 382.5), DESCEND 2.60 s → z 83.8, GRASP 1.70 s(닫기 1685 ms·폭 41.4·grip True), LIFT 2.70 s → z 148.8, VERIFY 167 ms·폭 41.4. 뒤이어 HOLD 0 PLACE ok 51.4 s | 아래 "6." |
| 7 | VIEW 자세 pose | 17:28 | `MoveToZone RECHECK 0 VIEW` **OK 8.0 s**, OBSERVE 복귀 OK 8.0 s (100 mm/s — gateway 재시작 금지로 안내의 30 mm/s 아님). **pose (517.94, −39.32, 120.51) mm** = 기대 (517.9, −39.3, 120.5) 와 차 ≤ 0.04 mm (stamp 17:28:12.766) | 아래 "7·8." · gateway 로그 |
| 8 | 박스 적재 15칸 (#44) | 17:31~17:40 | **15/15 OK** (A0·1·2, B0·1·2, C0·1·2, 재확인 0·1·0, 보류 0·1·0), 100 mm/s. 시간 17.4~32.3 s. 파지 15회 모두 grip True·폭 40.1~41.4 | 아래 "7·8." · gateway 로그 |
| 9 | G1 gateway 로그 (#41) | 16:41:52~17:46:22 | **연속 64.5 분(판정 확인 17:42:27 시점 60.6 분)·재시작 없음, FAULT 0, 두산 응답 없음 0, pose 조회 실패 1(기동 직후). pose 5초 창 727개 중 45 Hz 미만 13개, 최소 30.2 Hz → "pose ≥ 45 Hz" 미달.** 45 미만 13개 모두 C2·HOLD1 PLACE "트레이 안 이동" 구간 | 아래 "#41 판정용 확인" · `~/.ros/log/python3_69693_1791618112606.log` |
| 10 | belt_servo 파라미터 변경 | 12:5x~14:12 | `input.pose_lag_ms` 60 → 15 → **0** (PL 결정·DESIGN r7 DEC-03). 나머지 값은 받은 그대로 | 아래 "10." |
| 11 | 벨트 속도 | 14:20 | **4.76 cm/s**, 방향 −0.69° (h250 스케치, 업로드 안 함) | `belt_speed.py --bag track_rehearsal_02` |
| 12 | watchdog 정지 (f04 부산물) | 12:33 | 20 mm/s: 0.24 s·4.98 mm. 48 mm/s: 끊긴 뒤 약 0.25 s 에 정지, 10.3 mm (스크립트 출력 0.756 s·12.12 mm) | `f04/cut_123311·123335*` |
| 14 | 특이점 영역 안내(두산 3205/3206) | 14:36~15:27 | x ≈ 600 근처 추종 중·x 620 에서 OBSERVE 복귀 중·HOLD 왕복 중 "Change singularity region status" 8회. 실행자 보고: "x +580 까지 이동 후 홈 복귀 때 로봇팔 관절이 걸리는 현상" | 아래 "14." |
| 13 | x ≥ 600 z 처짐 | 14:37·14:40 | TRACK z 목표 140.8 에서 x 600 → 139.5, x 618 → **136.5** (z 명령 +2 → +6.5 mm/s), 2/2 재현 | 틱 로그 |

사건: **14:25 카메라 USB 재연결(프레임 끊김)** · **12:0x 공간 제한 '유효 공간 내부'로 적용 → 보호정지** — 아래 "사건".

---

## 0. 셋업

- 레포: 처음 체크아웃은 `fix/41-gateway-tcp-guard`(머지·삭제된 브랜치), 로컬 main 은 origin 보다 74 커밋 뒤 → `git switch main && git pull --ff-only` → **`280f786`**(#121·#122·#123·#125·#130~#133 포함). `colcon build --symlink-install` 8 패키지 통과(이전 install 에는 voss_servo 없었음).
- config: `~/voss_ws/config/` 가 없어서 새로 만들고 레포 3개 복사(레포와 바이트 동일). 10/08~09 gateway 는 `config:=<레포>/config/voss_config.yaml` 로 띄웠었다(bash 기록).
  - sha256: voss_config `db97243ec6ef…`, belt_homography `95d28cdf…`, hand_eye `0d73dffd…`, belt_servo_kp0 `f1d7c0ab…`, belt_servo_real 은 #10 참고.
- `~/voss_g0_env.sh` 없음 → 런북 1-5 내용으로 생성(DOMAIN 30, VOSS_CONFIG_DIR). `~/voss_g0_test.sh` 는 도메인 77·LOCALHOST 시뮬용(실기 터미널에서 쓰지 않음).
- 브링업: `dsr_controller2`·`joint_state_broadcaster` active. `get_current_tcp` → `info='GripperDA_v1'`.
- gateway 기동 기록:

| 기동 | 시각 | pose_source | 로그 |
|---|---|---|---|
| 1 | 11:06:22 | service | sha `db97243ec6ef`, real, TCP 차 0.0 mm, pose 49.6~50.0 Hz |
| 2 | 12:20:05 | service | 12:19:57 **브링업 재시작** 직후(보호정지 복구 중). TCP 차 0.0 mm (등록 유지) |
| 3 | **12:29:36** | **joint_states** | `pose_source joint_states 확인: 서비스 플랜지와 0.00 mm → 사용 (guard pose 지연 20 ms)`. 기동 직후 `pose 조회 실패: joint_states 없음` WARN 1회(첫 5초 fail 1) |

- OBSERVE: MoveToZone ok, pose (−14.5, −276.9, 203.9) mm (기준 203.6).
- 레포 변화(오늘): **#140** 머지 `fed7264`(13:29:59, box_tracker `pose_lag_ms` 60→15, 승인 박병후). **#138** 머지 `9cba6d0`(13:59, docs/interfaces/topics.md 2줄 — 학민 님 다른 세션). **#141**(런북 T2·32행·T5) 열림 — 남현지 변경 요청(belt_servo 0 문구) → `1065821` 반영, 재리뷰 대기. 공용 PC 체크아웃은 `fed7264`. 이후 **#126** 머지 `1d74b76`(마이크 1 m 기록 문서) — **#142** 머지 `1f8f5f4`(15:28, voss_voice TTS — src/voss_voice·docker/ai·docs). **#141** 머지 **`c66eeff`**(15:38:48, 런북 T2·32행·T5, 승인 남현지). 공용 PC `git pull` → `c66eeff`, voss_voice 빌드(15:4x). `fed7264` 이후 바뀐 파일은 docs·docker/ai·src/voss_voice 뿐 — voss_robot·voss_servo·voss_vision·voss_msgs·config 변경 없음(실행 중 gateway·belt_servo·box_tracker 재기동 안 함). 이어서 **#135** 머지 **`9aa1162`**(15:55:38, 런북 T7 칸·`.gitignore` belt_servo 실값 파일, 승인 박병후·남현지 — 학민 15:53 안내 "#135 를 G0 해시에"). 공용 PC pull → `9aa1162`. 안내 1절 확인: `git diff --stat c66eeff 9aa1162 -- src/voss_robot src/voss_servo src/voss_vision src/voss_manager src/voss_msgs config` 비어 있음, `fed7264` 기준도 비어 있음 → 실행 중 노드 재시작 안 함. 작업 트리 미추적 `data/`(belt_servo 로그)만. **G0 해시 = `9aa1162`** (실행 중 빌드 체크아웃: gateway 12:29 `fed7264`, box_tracker 13:39 `fed7264`, belt_servo 14:58 `fed7264` — 핵심 패키지 동일).

## 1. 벨트 면 z · 벨트 y · 프레임 (펜던트, 핑거 끝 TCP = GripperDA_v1)

조건: 벨트 12 V 끔, 박스 없음, 펜던트 Base 좌표. "닿기 직전" = 0.1 mm 조그, 종이 걸림.

| 측정 | 그리퍼 | x | y | TCP z | 메모 |
|---|---|---|---|---|---|
| 1-1 | 열림(90.4) | −107 | 중앙 근처 | 56 | 카메라 기준 오른쪽 핑거 먼저 |
| 1-2 | 열림 | 580 | 중앙 근처 | 59 | 오른쪽 핑거 먼저 |
| 1-3 로봇 쪽 가장자리 | 열림 | 300 | **−243.210** | 56.26 | 두 핑거 가운데를 가장자리 위에. a 5.69, b −180, c −85.55 |
| 1-3 반대쪽 가장자리 | 열림 | 300 | **−315** | 56 | a 133.78, b 180, c 43 |
| 1-4 측면 프레임 | 열림 | 621.620 | −200.420 | 52.990 | 로봇 쪽 측면 프레임, 왼쪽 핑거 아래쪽 접촉. a 176.89, b 180, c 85.25 |
| 1-C-1 | **닫힘** | −107 | −274 (목표) | **73.530** | |
| 1-C-2 | **닫힘** | 620 | −283 (목표) | **76.0** | |
| ③-1 첫 시도 | 닫힘 | 300 | −279 | 74 | 공간 제한 설정 전 하강(접촉 높이로 기록) |

- 측면 프레임 높이: 벨트와 거의 같음(눈 확인). x 620 너머 구조물 없음(눈 확인).
- 열림 값이 닫힘보다 15~18 mm 낮다. 같은 시각 근거: 열린 핑거 안쪽 간격 ≈ 80 mm(보고 90 → 실측 80, voss_config 주석) > 벨트 폭(프레임 포함) 71.8 mm. *(추측: 열린 핑거가 벨트 바깥으로 걸쳐 내려갔고, RG2 는 열수록 핑거 끝이 올라간다)*
- 기울기: 닫힘 x −107 → 620 (727 mm) 에 +2.47 mm (measurements-1006 "745 mm 에 2.4 mm" 와 같은 방향·크기). 하류가 높다.
- box_tracker 평면 z 는 100.8 하나(belt_homography `plane_z_mm`) — 위 실측 벨트 + 27 은 100.5(x −107) ~ 103.0(x 620).
- 닫힘 빈손 때 RobotState `gripper_width_mm` 37.0 (10/08 빈손 닫기 보고 38.0~38.7 과 다름 — 기록만).

## 2. 펜던트 공간 제한

- 위치: Workcell Manager → 로봇 → Space Limit. 형상 직육면체, 기준좌표계 베이스.
- 값: 포인트 1 (−150, −350, −50), 포인트 2 (700, −208, 77). 속성: 검사 **공구중심점(TCP)** (선택지 로봇/TCP), **유효 공간 외부** (선택지 내부/외부), 구역 마진 0.000 mm.
- 설정 근거(계산): L 77 = 높은 벨트 면 76.0 < L < gateway 78. y 범위 = 벨트 가장자리(기울기 −0.74° 로 x 끝까지 옮김: x −107 에서 −237.9/−309.7, x 638 에서 −247.6/−319.4) ± 30 mm. 재확인·보류 트레이 벽 y −142 와 66 mm.
- 확인:
  - 조그 하강(x 300, y −279, 닫힘): **77.45 에서 정지**, 알람 없이 경계 앞에서 섬. ROS pose (300.0, −279.0, 77.5).
  - 제어권 반환 뒤 PLACE(빈손): A1 ok(placed 12:21:00), C2 ok(12:22:06), HOLD1 ok(12:23:24). 보호정지 없음. gateway 로그 "트레이 안 이동: 칸 0 위 거쳐 TCP 60/70 높이로 옆으로".
- 실제 속도에서 정지 거리: **미측정**(조그 저속만). gateway 가 죽은 상태의 speedl 하강 정지는 재지 않음.
- 하류 끝(x 620)에서 L 77 과 닫힘 벨트 면 76.0 의 차 1.0 mm (계산값).

## 3. pose 지연 재측정 (pose_lag_js_01)

- 조건: gateway 3번 기동(joint_states), 카메라 `realsense2_camera_node` 1920×1080×30·노출 60·자동 꺼짐·WB 4600 자동 꺼짐(파라미터 읽어 확인), 박스 P4 정지(벨트 정지), 그리퍼 열림.
- 이동: `servo_f04.py cut --fast --speed 20 --secs 2` → OBSERVE → `cut --fast --speed 48 --secs 0.8` → OBSERVE, 사이 3 s 정지.
- 녹화: `~/voss_data/1010/pose_lag_js_01/` (70.9 s, 1.0 GB) — compressed 2126(30 Hz), camera_info 2126, pose 3543(49.9 Hz), state 151.
- 분석: PR #128 `tools/calib/pose_lag_eval.py`(worktree `~/voss_pl`, `827d97f`), `--hand-eye`·`--homography` = `~/voss_ws/config/`. 출력 `pose_lag_js_01_eval.txt`, 프레임 CSV `pose_lag_js_01.csv`.
  - 트랙 1개 2122장, 정지 1918·이동 190 프레임(정지 < 2 mm/s, 이동 ≥ 5 mm/s).
  - lag 표(이동 최대 mm): 0 → 0.85, 10 → 0.37, **15 → 0.31**, 20 → 0.46, 60 → 2.18, 100 → 4.09, 150 → 6.50.
  - 기준점 (−94.9, −276.1) mm (10/08 P4 터치 (−98.29, −274.03)).
- 10/08(service, he_moving_01): lag 60 ms, 이동 최대 2.73 mm, 갱신 간격 100 ms.
- 쓰는 곳: box_tracker `pose_lag_ms` 15 (#140). belt_servo 는 #10 참고(같은 값을 쓰지 않음 — DEC-03).

## 4. VERIFY 재닫기 (실제 RG2, 박스 쥔 채)

- 방식(체크리스트의 "손으로 건넴" 대신): 벨트 위 P4 박스(중심 (−94.8, −276.0), 카메라 검출 15프레임 ±0.03 mm)를 `servo_goto.py`(servo_cmd 경유, 아래 "현장 도구")로 내려가 파지.
- 높이(belt_servo 파라미터와 같은 계산): 접근 140.8, 파지 **81.8**(도착 81.91), LIFT **150.8**(도착 150.69), 내려놓기 82.3(도착 82.39). 각 이동 도착 오차 0.12~0.16 mm.

| 회 | 위치 | 응답 시간 | grip_detected | width_actual |
|---|---|---|---|---|
| 파지 | z 81.9 | 1677 ms | True | 41.1 |
| 재닫기 1 | z 150.7 | 167 ms | True | 41.1 |
| 재닫기 2 | 〃 | 168 ms | True | 41.1 |
| 재닫기 3 | 〃 | 167 ms | True | 41.1 |
| 재닫기 4 | 〃 | 173 ms | True | 41.1 |
| 재닫기 5 | 〃 | 171 ms | True | 41.1 |
| 열기 90 | z 82.4 | 1436 ms | False | 90.4 |

- 박스 처짐·미끄러짐: 실행자 보고 없음(메모 없음).
- 이동 중 gateway: 거부 0, 자름 0, 매 이동 끝 watchdog → move_stop ok.
- **벨트 위 실제 VERIFY 재닫기 (belt_servo 로그 `gripper 응답 VERIFY`, 39 mm·14 N): 오늘 24회 모두 OK·grip True, 폭 40.6~41.5 mm, DROPPED 0.** ② 15:26:13 41.4(`python3_40732_*`) · G0 16:12:17 40.7 · 중단된 G1 첫 박스 16:34:18 41.2(`python3_55200_*`) · G1 s1 20사례 + 의도 시험 OK 1(17:09:42) = 21회 40.6~41.5(`python3_69826_*`). 요청→응답 간격(로그 시각 차) 166~200 ms.
- 슬로모션 미촬영 → #123 "접촉 ↔ 응답 간격" 직접 측정 없음. 쥔 상태 재닫기 응답 167~173 ms 가 같은 질문의 간접 자료.

## 5. ① 추종·cancel (Kp 0, belt_servo T7 overrides kp0)

- belt_servo 기동 14:16:02: `config_sha256=db97243ec6ef params_sha256=708358ba6bf9ae78d8b9764634da5d5511caa4b913e157078cea7056602fd7c2`, READY, `pose_lag_ms=0.0`(뒤 "service 기준" 문장은 고정 문구), "x 여유: 하강 예상 2.64 s + 닫힘 2.10 s → 정렬 때 x_max 까지 237 mm 이상 남아야 DESCEND".
- 로그: `data/servo/ticks/servo_ticks_20261010_141602.jsonl`, `data/servo/attempts/servo_attempts_20261010_141602.jsonl`. 녹화 `track_rehearsal_02`(14:18~14:24, 3 GB+), `_03`(14:29 짧게 끝남, 0.4 MB), `_04`(14:4x~14:58, **18.3 GB**).
- box_tracker(13:39:49 기동): `pose_lag=15 ms`, `moving_verified=True`, homography `95d28cdf`, hand_eye `0d73dffd`, 29.8~30.0 Hz, 카메라→발행 p95 55~57 ms, 호모그래피↔핸드아이 최대 0.7 mm. P4 정지 박스 BoxTrack (−94.8, −275.6, 100.8), valid, source hand_eye.

| # | 시각 | goal | track | 결과 (reason / cause) | 길이 | TCP x 시작→끝 | z 최저 | 벨트 방향 간격(시작→끝) | 가로 최대 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 14:18:57 | `66c1ff77` | 1 | LOST / BOX_MISSING | 2.53 s | −14.5 → 89.9 | 143.3 | −77 → −157 | 0.4 |
| 2 | 14:36:45 | `f33b4154` | 3 | OUT_OF_REACH / REACH_X_MAX | 13.87 s | −14.5 → 620.6 | 135.8 | −91 → −76 (중간 −75~−88) | 3.3 |
| 3 | 14:40:22 | `75e3e892` | 4 | OUT_OF_REACH / REACH_X_MAX | 13.87 s | −14.5 → 620.7 | 135.9 | −93 → −78 | 3.8 |
| 4 | 14:43:13 | `1bc04059` | 5 | LOST / BOX_MISSING | 1.33 s(틱) | −14.5 → 32.4 | 158.8 | −156 → −170 | 0.3 |
| 5 | 14:46:34 | `4221dd6e` | 7 | **CANCELED / STOP_OK** | 3.03 s | −14.5 → 112.5 | 142.2 | −70 → −55 | 3.5 |
| 6 | 14:56:08 | `eab77bdd` | 8 | **CANCELED / STOP_OK** | 6.07 s | −14.5 → 258.2 | 140.8 | −69.5 → −58.0 | 2.1 |

회차별 관측:
- **1:** goal 대기 명령이 직전까지 정지해 있던 P4 박스 트랙(1)을 잡음 → 박스를 들어 올린 뒤 트랙 끊김 → LOST. PREPARE 개방 응답 175 ms. 끝에 watchdog → move_stop 1 ok.
- **2·3:** Ctrl+C 가 belt_servo 에 닿지 않음(`stopping` 기록 없음, 출력에 `^C` 없음). FF 48 mm/s 로 x 620 까지 가서 자동 종료. 접근 높이 140.8 도달까지 약 4~5 s. 벨트 방향 간격이 줄지 않음(Kp 0). y 는 −276.5 → −283.8 (벨트 방향 −0.74° 와 같은 기울기). 끝에 watchdog → move_stop 1 ok, 거부 0, 자름 0. 이동 내내 box_tracker 30 Hz·WARN 0.
- **4:** 박스가 화면에 처음 잡힌 직후 goal → 시작 간격 −156 mm. 로봇이 내려가는 중(z 203 → 163) 0.83 s 에 마지막 박스 수신, 0.5 s 뒤 LOST. 같은 시각 box_tracker 30 Hz(카메라 정상). *(추측: 화면 위 가장자리 박스가 시야가 좁아지며 빠짐)*
- **5:** `wait_track.py --x-min -120` + `timeout -s INT 3`. 3.00 s 에 취소 수신(`stopping`), 그 틱부터 명령 0. gateway 순서: 14:46:37.234 `RobotState STOPPED` → `servo_cmd 거부: stop` 1 → `/voss/robot/stop → OK`(.254) → 14:46:37.266 `BUSY SERVO`(0 명령 수신) → 14:46:38.004 watchdog → 0 속도 + move_stop. 5초 통계: `거부 {'stop': 1}, watchdog 1, stop 1, move_stop 2 ok / 0 fail`. 취소 때 TCP x 112.4, z 142.2. 정지까지 거리(녹화 `_04` /voss/robot/pose, `stopdist.py`): 취소 때 48.1 mm/s → **0.099 s 뒤 정지, 0.97 mm** (3 s 뒤 총 0.86 mm).
  - CLI 출력 `Canceling goal...` 뒤 `Executor is already spinning`(ros2 action send_goal 쪽 메시지) — 결과 줄은 출력되지 않음. belt_servo 로그 `goal 종료 reason=CANCELED cause=STOP_OK`.
  - track 6 은 goal 에 쓰이지 않음(번호만 건너뜀, 원인 미확인).
- **6:** `wait_track.py --min 7 --x-min -120` + `timeout -s INT 6`. 6.03 s(14:56:14.230)에 취소 수신, TCP (258.0, z 140.8), 접근 높이 도달 뒤 정속 추종 구간에서 취소. gateway 순서: 14:56:14.232 `STOPPED` → .235 `/voss/robot/stop → OK` → .267 `BUSY SERVO`(0 명령) → 14:56:14.986 watchdog → 0 속도 + move_stop. 5초 통계 `거부 0, watchdog 1, stop 1, move_stop 2 ok / 0 fail`. PREPARE 개방 응답 175 ms. CLI 출력은 5회와 같음(`Canceling goal...` → `Executor is already spinning`). 정지까지 거리(같은 방법): 48.0 mm/s → **0.083 s 뒤 정지, 0.74 mm** (3 s 뒤 총 0.55 mm). 이동 중 box_tracker WARN 0. 벨트 방향 간격이 시작 0.24 s 동안 +11.5 mm 변한 뒤 일정 *(추측: 로봇 가속(0.1 m/s²) 동안 박스가 따라붙음 — 2회의 −91 → −75 와 같은 모양)*.
- 모든 goal: 틱마다 `clamped` 20 틱(가속·속도 제한), z 는 140 아래로 내려가지 않음(최저 135.8 은 #13).

## 6. ② TrackAndGrasp 1회 (Kp 1.0)

- belt_servo 14:58:54 재기동(overrides 없음) `params_sha256=01a6fc1f866c…`. 녹화 `track_grasp_05`. goal 대기 `wait_track.py --min 8 --x-min -120`.
- goal `ce3b3e80`, track 9, 시작 15:26:02.9 (epoch 1791613562.9). 로그 `servo_ticks_20261010_145854.jsonl`·`servo_attempts_20261010_145854.jsonl`.

| 단계 | 시작(goal 기준) | 길이 | TCP (x, y, z) 시작 | 메모 |
|---|---|---|---|---|
| PREPARE | 0.00 s | 0.17 s | (−14.5, −276.5, 203.6) | 개방 90 응답 176 ms, 벨트 방향 간격 −70.1 mm |
| TRACK | 0.17 s | 3.50 s | (−14.5, −276.7, 202.5) | 접근 높이로 내려가며 정렬 |
| DESCEND | 3.67 s | 2.60 s | **(90.7, −278.8, 141.3)** | 정렬 순간 간격 −2.9 mm·가로 0.0 mm (허용 3·5). x 90.7 ≤ 382.5 |
| GRASP | 6.27 s | 1.70 s | (213.5, −280.0, **83.8**) | 파지 높이 목표 81.8 + height_tol 2.0 = 83.8 에서 전환. gateway 닫기 39 mm·14 N → **1685 ms, 폭 41.4, grip True**. 이 단계 시야 없음(vision cutoff) |
| LIFT | 7.97 s | 2.70 s | (295.0, −281.1, 83.7) | 수직 들기 |
| VERIFY | 10.67 s | ~0.7 s | (317.4, −281.5, **148.8**) | 목표 150.8 − tol 2.0 에서 전환. 재닫기 **167 ms, 폭 41.4, grip True** (belt_servo 기록 지연 0.200 s, verdict HELD) |
| 끝 | 11.4 s | | x 최대 317.5, z 최저 83.7 | `GOAL_END OK`, grasped true, attempts 1 |

- 끝난 뒤 gateway: watchdog → 0 속도 + move_stop 1 ok, 거부 0, 자름 0.
- 이어서 `MoveToZone HOLD 0`(PLACE): ok, **51.4 s**, placed 15:27:23. gateway: "수평 이동 높이 플랜지 z 426.6 (TCP 180)", 특이점 안내 6회(#14), 큐 대기 최대 97~105 ms·pose 48.2~48.4 Hz(이동 중 5초 창).
- 간섭(카메라 손목·트레이) 눈 확인: 실행자 보고 없음.
- 그리퍼 힘: 실행자(김학민)가 **박스가 조금 찌그러져서** 14 N → 12 N 을 검토(15:3x) → 변경 절차(voss_config PR·docs/interfaces·PL 승인·gateway/belt_servo 재기동)가 길어 **14 N 유지로 결정**(15:4x). 참고 근거(ADR-0009): 10/06 시험 3·8·10·12·14 N 중 12 N 부터 미끄러짐 없음(12 N 3회, 14 N 2회), 14 N = "최저 합격 12 N + 여유". 값 위치는 `config/voss_config.yaml` `gripper.force_n`(gateway·belt_servo 둘 다 읽음). 찌그러짐 정도(사진·치수)는 기록 없음.

## 14. 특이점 영역 안내 (두산 3205/3206, gateway 로그)

| 시각 | 상황 | 안내 |
|---|---|---|
| 14:36:57 | ① 2회 추종 중, x ≈ 600 근처 (#13 z 처짐 시작 14:36:58 과 같은 때) | Outside → Inside |
| 14:37:39 · 14:37:41 | x 620 에서 OBSERVE 복귀(22.7 s) | Outside → Inside, Inside → Outside |
| 14:40:34 | ① 3회 추종 중, x ≈ 600 근처 | Outside → Inside |
| 14:40:51 · 14:40:53 | OBSERVE 복귀(22.7 s) | Outside → Inside, Inside → Outside |
| 15:27:14 · 15:27:16 · 15:27:18 | HOLD 0 PLACE 가는 길 | Outside → Inside ×2, Inside → Outside |
| 15:27:26 · 15:27:29 · 15:27:31 | HOLD 에서 OBSERVE 복귀 | Outside → Inside ×2, Inside → Outside |

- 전체 문구: `1/2/3205 Change singularity region status(Outside -> Inside), Singularity handling mode(1)` / `3206 … (Inside -> Outside)`.
- 실행자 보고 "x +580 까지 이동 후 홈 위치 복귀할 때 로봇팔 관절이 걸리는 현상" 과 시각이 겹치는 안내는 위 복귀 행들. *(추측: 특이점 처리 모드 진입 때 관절 속도가 제한되어 걸리는 것처럼 보임)*
- 10/09 기록: C2 32.6 s · HOLD1 30.2 s (100 mm/s). 오늘 HOLD0 51.4 s 는 30 mm/s(`zone_vel_mm_s:=30`).

## 10. belt_servo 파라미터

- 받은 파일: 박병후 Slack 첨부 `belt_servo_real.yaml`·`belt_servo_kp0.yaml` → `~/voss_ws/config/`. `hold_width_max_mm` 43.5 → **44.0**(15:5x, 박병후 결정 — 김학민 15:53 안내로 전달, GitHub 문서 근거는 찾지 못함). 44.0 적용 오프라인 READY: kp0 `0010a217011a`, Kp1 **`215e6274f074`**, 파일 sha256 `87fb481552bb…`. 적용은 belt_servo 재기동 뒤(14:58 기동 노드는 43.5).
- `input.pose_lag_ms` 변경:

| 시각 | 값 | 이유 | READY (오프라인 build_params·check_params) | params_sha256 (kp0 / Kp1, 앞 12) |
|---|---|---|---|---|
| 받음 | 60.0 | service 기준 | READY / READY | e825c1c984ab / f0a0a416511d |
| 12:5x | 15.0 | 체크리스트 2번 "belt_servo 도 같은 값" | READY / READY | 28c77d752901 / 74831c7d4846 |
| 14:12 | **0.0** | PL(남현지) #135 승인·#141 리뷰: joint_states 면 0(시험값, DESIGN r7 DEC-03 — belt_servo lag 는 pose stamp 의 물리→stamp 지연. 15 ms 는 영상 대비 상대 지연이라 box_tracker 전용) | READY / READY | **708358ba6bf9 / 01a6fc1f866c** |

- 파일 sha256(0.0): `6b4e36899c7639038b31b8cd2ab3629f2950e10f25e0918de5cc7cc9bae58f61`. 노드 기동 로그 params_sha256 = `708358ba6bf9…`(kp0, 계산값과 같음).

## 11. 벨트 속도

- `belt_speed.py --bag ~/voss_data/1010/track_rehearsal_02`: 트랙 2, 95점 3.1 s, x −47 → 102 mm, **4.76 cm/s**, 방향 −0.69°, 직선 잔차 최대 0.3 mm. (트랙 1 = 정지 P4 박스, 이동 0.3 mm)
- 기록값: h250 10/08 4.77 cm/s, voss_config `belt.speed_cmps` 4.8, 방향 −0.74°. 아두이노 업로드 안 함(스케치는 읽어낼 수 없음).

## 12. watchdog 정지 (f04, joint_states pose)

- `f04/cut_123311.csv`(20 mm/s 2 s): 스크립트 `stop_s` 0.242 s, `overshoot_mm` 4.98.
- `f04/cut_123335.csv`(48 mm/s 0.8 s): 스크립트 0.756 s · 12.12 mm. CSV 속도 단면: 끊긴 뒤 0.197 s 까지 43~52 mm/s, 0.255 s 에 2.9 mm/s, 0.315 s 에 0.1 mm/s, 끊긴 뒤 최대 이동 10.29 mm, 이후 −0.2~−0.5 mm/s 로 약 0.15 mm 되돌아옴. *(추측: 스크립트의 멈춤 판정(0.3 mm/s, 0.2 s 창)이 되돌아오는 움직임을 잡아 0.756 s 로 나옴)*
- 10/08 F-04 기록: 48 mm/s 약 0.3 s · 10~11 mm. 10/08 같은 시나리오 `cut_164053`(service): stop_s −0.02, 4.82 mm.

## 13. x ≥ 600 z 처짐 (① 2·3회 틱 로그)

| x (mm) | 2회 z | 3회 z | belt_servo z 명령 |
|---|---|---|---|
| ~600 | 139.4 | 139.5 | +2.0~2.1 mm/s |
| ~607 | 138.7 | 138.8 | +3.0~3.1 |
| ~613 | 137.5 | 137.9 | +4.3~4.9 |
| ~618 | 136.5 | 136.6 | +6.3~6.5 |

- `tcp_pose_m`(측정 pose)도 같은 값(외삽 아님). 이 위치의 베이스 거리 ≈ √(618² + 284²) ≈ 680 mm, 10/06 기록 "최대 리치 697 mm". *(추측: 팔이 펴지는 구간에서 speedl z 추종 한계)*

## 사건

### 공간 제한 '유효 공간 내부' 적용 → 보호정지 (12:0x~12:1x)
- 1차 "확인" 때 속성이 **유효 공간 내부**(TCP 가 상자 안에 있어야 정상)였다. 적용 시 TCP (300.0, −279.2, 76.5) — 펜던트 "안전제한치 위반, 암호장치, 또는 자기진단 오류검출로 인한 보호정지", RobotState `ERROR`/`SAFETY_STOP`/`SAFE_OFF2`.
- 복구 모드는 관절 이동만 가능 → 관절로 (180.3, −416.7, 372.6) 까지 옮겼으나 계속 보호정지(자세 크게 기울어짐).
- 속성을 **외부**로 바꾸고 적용 → 해제. 관측 자세 관절값 (−93.89, −13.54, 97.73, −0.01, 94.88, −185.08)(measurements-1006 #6)로 복귀.
- 그 사이 12:19:57 브링업 재시작, 12:20:05 gateway 재시작(TCP 차 0.0 mm).
- 펜던트 화면 사진: 형상(12:02:28·12:02:31), 속성 내부(12:13:54 서보 오프).

### 카메라 USB 재연결 (14:25)
- box_tracker: 14:24:59 18.8 Hz WARN → **14:25:04 부터 `영상 0 프레임`** (14:34 까지).
- 카메라 노드: `Frames didn't arrived within 5 seconds` 5 s 마다. lsusb D435i 장치 번호 002 → 003 (재연결).
- 직전 14:18:57~14:19:00 ① 1회 로봇 이동(x −14.5 → 89.9). *(추측: 손목 케이블 당김 — 10/08 10:52 USB 끊김과 같은 증상)*
- 복구: T3 카메라 노드 재기동 14:34:28(`initial_reset`, 장치 004), 파라미터 노출 60·WB 4600·자동 꺼짐 확인, box_tracker 재기동 없이 29.6~30 Hz 회복. 이후 ① 2~5회 이동 중 WARN 0.

### 카메라 프레임 저하·끊김 2차 (16:11~16:22)
- box_tracker 5초 창 영상 주기: 16:11:48 까지 30.0 Hz → 16:11:53 27.8 → **16:11:58 20.0** → G0 추종 구간 16:12:03~16:12:13 **26.6·25.6·25.0 Hz**(box 3·128·32, 무효 1) → 16:12:18~16:13:53 15.2~28.0 Hz → 16:13:58~16:14:23 29~30 Hz → 이후 **영상 0 프레임**.
- 카메라 노드: `Incomplete video frame detected! … Frame Corrupted`(프레임 크기 3~54 %) **13회, 16:11:57~16:13:50** → 16:14:28 부터 `Frames didn't arrived within 5 seconds` 5 초마다 → 16:22:20 Ctrl+C 로 노드 종료.
- lsusb D435i 장치 번호 005(16:04 기동 때) → **006** (재연결).
- 그 시각 로봇: 16:08:35~16:12:07 OBSERVE 정지(관측), 16:12:07~16:13:10 G0 추종·파지·B 칸 0 PLACE 왕복, 16:13:21 이후 정지(PAUSED). 프레임 저하 시작(16:11:53)은 로봇 정지 중. *(추측: 케이블·커넥터 접촉 또는 USB 전원·노이즈 — 1차(14:25)는 로봇 이동 직후, 2차는 정지 중 시작이라 이동만으로는 설명이 안 됨. ① 2~6회(14:36~14:56, 벨트·로봇 동작) 동안은 WARN 0)*
- G0 증거 영향: G0 판독·추종(16:12:06~16:12:14)은 25.0~26.6 Hz 구간에서 이루어짐(box_tracker `hz_warn` 25 근처). G0 결과(OK·PLACED·DB)는 위 표대로.
- 같은 때 sort_manager: 16:20:59 `명령 거부: PAUSED 에서는 resume` (G1 용 start 를 PAUSED 상태에서 보냄 — start 는 IDLE 에서만). 녹화 `g1_s1` 16:20 시작(카메라 끊긴 상태, G1 회차 없음) → 종료 후 `g1_s1_aborted_camera` 로 이름 변경(보관).
- 복구(16:3x): USB 커넥터·케이블 점검(김학민), T3 카메라 재기동, T8 sort_manager 재기동(IDLE). 확인: D435i Bus 002 Dev 007 **5000M**, `/camera/color/image_raw` 29.1 Hz, 노출 60·자동 꺼짐·WB 4600, box_tracker 29.6~29.8 Hz, `/voss/sort/state` IDLE·ready·not_ready [], 노드 7개(gateway·camera·box_tracker·label_reader·belt_servo·sort_logger·sort_manager). gateway 16:04:00 그대로.
- 벨트만 켠 확인(박스 없음, 벨트 켬 약 16:30:5x, 16:30:30~16:32:28 5초 창 24개): box_tracker **29.4~30.0 Hz**, 카메라 경고(Incomplete·Frames Timeout) **0**, USB 장치 007 그대로.

### 카메라 노드 수동 재기동 (17:13, G1 20회차 전)

- 직전 카메라 노드(pid 64321, 16:28:12 기동) 경고: 17:01:42 `Incomplete video frame detected! 3785480 / 4147455 bytes (91%)` **1회**. 그 밖의 경고 없음.
- 17:13:38 SIGINT(사람이 Ctrl+C) → 17:13:42 재기동(pid 79776, `initial_reset:=true`, 장치 리셋 6 s) → 17:13:49 `RealSense Node Is Up!`, USB 3.2·포트 2-2 그대로.
- box_tracker: 17:13:43·17:13:48 창 `영상 0.0 Hz < 25` 경고 2회(재기동 공백) → 17:13:53 25.4 Hz → 이후 29.6~30.0 Hz. 근거 `~/.ros/log/realsense2_camera_node_64321_*.log`·`_79776_*.log`, `python3_54511_*.log` 934~948행.
- 재기동 사유는 기록 없음 *(추측: 20회차 전 정리)*. 20회차(17:15) 는 재기동 뒤 카메라로 실행.

## G0 준비 상태 (15:45 확인, 읽기 전용)

| 항목 | 상태 | 근거 |
|---|---|---|
| main 해시 | **`9aa1162`**(#135, 15:55) ← `c66eeff`(공용 PC pull·voss_voice 빌드 완료). 15:5x `git fetch` 재확인: origin/main 그대로 `c66eeff`. #143(#142 되돌리기) 은 머지 없이 닫힘(15:50). 열린 PR #127·#128·#134~#137·#139 는 G1 뒤 | `git log -1`, `gh pr list` |
| T1 브링업 · T2 gateway(joint_states, 12:29:36~) · T3 카메라(14:34~) · T5 box_tracker(13:39~) · T7 belt_servo Kp 1.0(14:58~) | 실행 중 | `ros2 node list` |
| DB (런북 1-4) | 15:45 미설치 → **15:42~15:44 설치**(김학민): `/var/lib/voss/pgdata·spool` 생성, `.env` 3개 비밀번호 채움(값은 기록하지 않음, gitignore 확인), `docker compose up -d` → `db-db-1` postgres:16 **healthy**, 127.0.0.1:5432. 테이블 `session_plan`·`sort_log`, 계정 `voss_admin`·`voss_logger`·`voss_web`, `sort_log` 0행 | `docker compose ps/logs`, `psql \dt` |
| sort_logger 의존성 | `python3-psycopg2` 없음 → apt 설치 2.9.9 | `python3 -c "import psycopg2"` |
| T4 sort_logger · T6 label_reader · T8 sort_manager | 미기동 | `ros2 node list` |
| PaddleOCR venv | 있음 — `~/.venvs/voss_ocr` paddleocr 3.7.0, 모델 `korean_PP-OCRv5_mobile_rec`·`PP-OCRv5_server_det` | |
| 트레이 | 보류 칸 0 에 ② 박스 있음(15:27 PLACE) | #6 |
| 벨트 | h250 4.76 cm/s (#11). 런북 3장 "1회차는 h500(2.38 cm/s), 성공하면 h250" 항목 ↔ voss_config `belt.speed_cmps` 4.8 (belt_servo FF 입력). **결정(김학민 15:4x): G0 는 h250** — ②가 h250 에서 성공, 벨트 속도 조절은 다음에 | 런북·config |

## G0-2 노드 기동 확인 (15:58~16:01, 모두 확인 뒤 Ctrl+C 로 내림)

| 노드 | 시각 | 기동 로그 |
|---|---|---|
| T7 belt_servo (hold_width 44.0) | 15:58:57 | `params_sha256=215e6274f074e54fde6321f1cc991718b422ddfbce6a577d2f05bbf917a64896`(오프라인 계산과 같음), READY, pose_lag 0.0, 로그 `servo_*_20261010_155857.jsonl` |
| T4 sort_logger | 15:59:15 | `spool=/var/lib/voss/spool/sort_log.jsonl`, **DB 연결 성공**, `/voss/log/status: - → OK`. Ctrl+C 때 `RCLError: rcl_shutdown already called`(종료 처리 예외, 기록만) |
| T6 label_reader | 15:59:47 | voss_config sha `db97243ec6ef`, confidence_min 0.6, OCR cpu, stage1_enough 2, **OCR 엔진 준비 cpu 3.1 s**, 16:00:09 zone_map v1 후보 S07-01 역삼동·S07-02 대치동·S07-03 청담동 → **판독 준비 완료** |
| T8 sort_manager | 16:00:09 | voss_config sha `db97243ec6ef`, 구역 칸 A3·B3·C3·RECHECK2·HOLD2, confidence_min 0.6, home_first True |

- 16:0x `ros2 node list`: belt_servo·sort_logger·label_reader·sort_manager 없음(위 4개 Ctrl+C). gateway(12:29~)·box_tracker·camera 는 계속 실행.

## 전체 재기동 → G0 시작 전 확인 (16:04~16:07, 런북 3장)

- 16:0x 모든 터미널 종료 후 재기동(김학민). 새 gateway 기동 **16:04:00** (#41 연속 시간 시작점, 이전 gateway 12:29:37~16:0x).

| 노드 | 기동 | 로그 |
|---|---|---|
| T2 gateway | 16:04:00 | sha `db97243ec6ef`, real·max 100 mm/s·z ≥ 78·x −107~638, TCP 차 0.0 mm, `pose_source joint_states 확인: 서비스 플랜지와 0.00 mm → 사용` |
| T4 sort_logger | 16:04:41 | DB 연결 성공 |
| T5 box_tracker | 16:04:48 | homography `95d28cdf`, hand_eye `0d73dffd`, (pose_lag 15) |
| T6 label_reader | 16:04:56 | sha `db97243ec6ef`, 16:05:13 판독 준비 완료 |
| T7 belt_servo | 16:05:04 | `params_sha256=215e6274f074…`, READY |
| T8 sort_manager | 16:05:13 | sha `db97243ec6ef`, 칸 A3·B3·C3·RECHECK2·HOLD2 |

| 확인 (16:07) | 결과 |
|---|---|
| `/voss/sort/state` | IDLE, **ready: true, not_ready: []** |
| `/voss/log/status` | OK |
| `/voss/robot/state` | connected, READY, controller STANDBY, gripper 90.4 |
| pose | (−14.5, −276.5) OBSERVE, `topic hz` 50.0 Hz |
| 카메라 | `/camera/color/image_raw` 30.1 Hz, D435i Bus 002 **5000M** |
| voss_config sha256 (T2·T6·T8) | 모두 `db97243ec6ef` |
| 코드 | `9aa1162` |

## G0 1회차 (16:08~16:13, 런북 4장) — main `9aa1162`

| 항목 | 값 | 근거 |
|---|---|---|
| 세션 | `20261010T160835-e8c7` start 16:08:35, OBSERVE 도착 16:08:35.6 | sort_manager 로그 |
| box_id · track | **`20261010T160835-e8c7-001`**, track 1 | sort_manager 로그 |
| OCR | `S07-02 대치동 1.00 AGREE → 투표 대치동 1.00 (2/2)`, OCR 3064·2995 ms (16:12:06.958·16:12:09.965) | label_reader 로그 |
| 분류 | 대치동 → **B 칸 0** | sort_manager 로그 |
| TrackAndGrasp | goal `a494dab6`, **OK · grasped true · 시도 1**, 10.8 s | attempts `servo_attempts_20261010_160504.jsonl` |
| 단계 (goal 기준) | PREPARE 0.00 → TRACK 0.17 → DESCEND 2.70 (TCP x 89.7, z 142.7, 간격 −1.6·가로 0.6 mm) → GRASP 5.33 (z 83.7) → LIFT 7.33 → VERIFY 10.07 (z 148.8) | ticks `servo_ticks_20261010_160504.jsonl` |
| 좌표 출처 | 추종 중 `position_source=2`(HAND_EYE), visible (DESCEND 까지), GRASP 이후 시야 없음 | ticks |
| 그리퍼 | 개방 173 ms · 닫기 39 mm·14 N **1998 ms, 폭 40.7, grip True** · VERIFY **182 ms, 폭 40.7, grip True** | gateway 로그 |
| 적재 | MoveToZone B 칸 0 PLACE → OK **52.9 s**(OBSERVE 복귀 포함), SortResult `PLACED B reason=- attempts=1` 16:13:10.124 | gateway·sort_manager 로그 |
| DB | `db_committed box_id=…-001 result=PLACED zone=B … at=16:13:10.129`. SELECT 1행: result PLACED, zone B, attempts 1, **finished_at 16:12:43.412898**, inserted_at 16:13:10.124374. sort_log 전체 1행 | sort_logger 로그, psql |
| stop | 16:13:21.6 `RUNNING → PAUSED`, gateway `/voss/robot/stop → OK` | sort_manager·gateway 로그 |
| 녹화 | `~/voss_data/1010/g0_01/` (16:07~, 16:14 기준 5.1 GB) | |
| 육안 | 실행자 보고 "정상 작동한 것 같다" | |

- gateway 이 구간: 거부 0, 자름 0, goal 끝 watchdog → move_stop 1 ok.
- 녹화 `g0_01` 종료(16:16, 5.06 GB). bag 확인(`g0_bag_check.py`):
  - `/voss/log/status`: OK 521개, **DB_ERROR 0**
  - `/voss/sort/state`: 16:07:54.9 IDLE → 16:08:35.1 RUNNING → 16:12:06.957 PICKING(`…-001`, track 1) → **16:13:10.124 RUNNING** → 16:13:21.6 PAUSED
  - `/voss/vision/box` track 1: valid·source 2(HAND_EYE) 162개, invalid·source 0 1개
  - `/voss/sort/result` 16:13:10.123: `…-001`, code S07-02, dong 대치동, zone B, PLACED, track 1, attempts 1
  - `/voss/vision/label` 2개(16:12:06.956·16:12:09.964), track 1 대치동 1.0
- 휴대폰 영상: 촬영·육안 확인 완료(김학민 보고). 개방 순간 ↔ finished_at 16:12:43.4 대조는 영상 원본으로(Drive `raw/1010/g0_01/`).
- 끝난 뒤 B 칸 0 박스 꺼냄, 작업 공간 비움(16:1x).

## G1 시리즈 s1 (준비 16:2x)

고정 조건(시작 전 기록):
| 항목 | 값 |
|---|---|
| main | `9aa1162` |
| belt_servo | `~/voss_ws/config/belt_servo_real.yaml` sha256 `87fb481552bb…`, 노드 params_sha256 `215e6274f074e54f…`(Kp 1.0, hold 39.5~44.0, pose_lag 0) |
| voss_config | `db97243ec6ef` (gripper 39 mm·14 N, belt.speed_cmps 4.8) |
| 벨트 | h250, 실측 4.76 cm/s (#11) |
| 카메라 | 1920×1080×30, 노출 60(6 ms), WB 4600 고정 |
| box_tracker | detector seg, observe_source hand_eye, **pose_lag_ms 15** (#140 — `docs/g1-gate.md` 고정 조건의 "60" 은 #140 전 문구), hand_eye `0d73dffd`, homography `95d28cdf` |
| gateway | ~~16:04:00 기동, `zone_vel_mm_s:=30`~~ → **16:41:52 기동**, `pose_source:=joint_states`, `zone_vel` 인자 없음(구역 100 mm/s), 재시작 금지(#41) |
| goal 경로 | sort_manager (start → 판독 → goal → PLACE) |
| 집계 도구 | #137 gate_summary — `~/voss_gs`(origin/feat/13-voss_servo-gate-summary `5f9b62c`, 로컬 worktree) |

회차 기록: (진행하면서 채움)

**G1 첫 박스 — 적재 시간 초과 (16:33~16:35, "본 측정 시작" 선언 전)**
- 세션 `20261010T163322-4e00` start 16:33:22.8, OBSERVE 도착 16:33:23.0. 녹화 `g1_s1`.
- box `…-4e00-001`, track 4, 청담동 → C 칸 0. TrackAndGrasp goal `625df3f1` **OK·grasped true·시도 1** (PREPARE 16:34:07.77 → TRACK .96 → DESCEND 16:34:11.15 → GRASP 13.76 → LIFT 15.46 → VERIFY 18.19). 그리퍼: 개방 170 ms, 닫기 **1671 ms·폭 41.2·grip True**, VERIFY 170 ms·폭 41.2·grip True.
- MoveToZone C 칸 0 PLACE: sort_manager 호출 16:34:18.39 → **`move_timeout_s` 60.0 초과(16:35:18.39)** → SortResult **FAILED reason=DEVICE_ERROR attempts=1** → PAUSED. gateway 는 **16:35:18.687 `PLACE → OK, 60.3 s`**(placed_stamp 16:34:46.84) — sort_manager 로그 "시간 초과 뒤 늦은 MoveToZone(C) 응답: ok=True … 칸 수를 사람이 확인".
- PLACE 중 특이점 안내 6회(16:34:37~40 가는 길, 16:34:52~54 복귀).
- DB: `20261010T163322-4e00-001 | FAILED | (zone 없음) | 1 | finished_at 16:35:18.39`.
- 참고 PLACE 시간(gateway `zone_vel_mm_s:=30`): B0 52.9 s(G0), HOLD0 51.4 s, **C0 60.3 s**. 10/09(100 mm/s): A 18.6 · B 21.9 · C 32.8 s. sort_manager `move_timeout_s` 60.0 (`src/voss_manager/config/sort_manager.yaml`, launch 인자 없음). gateway 기본(인자 없음) 구역 속도 100 mm/s(13:01 dry_run 기동 로그 `vel [100.0, 45.0]`).
- 조치(김학민 결정, 16:4x): 박스 C 칸 0 에서 꺼냄, 녹화 `g1_s1` → `g1_s1_aborted_timeout`(보관). T8·T7·T2 종료 → **T2 런북 명령 그대로(`zone_vel_mm_s` 없음) 재기동 16:41:52**: sha `db97243ec6ef`, **`vel [100.0, 45.0]`**, real·max 100 mm/s·z ≥ 78, TCP 차 0.0 mm, joint_states 사용. **#41 연속 시간 새 시작점 16:41:52.** T7 belt_servo 16:42:10 `params_sha256=215e6274f074…` READY. T8 sort_manager 재기동(IDLE). 확인: sort state IDLE·ready, log OK, robot READY·gripper 90.4, pose 50.0 Hz, 노드 7개.
- G1 고정 조건 표의 gateway 행: 16:41:52 기동, `zone_vel` 인자 없음(100 mm/s) 으로 바뀜.

**본 측정 s1** — "본 측정 시작" 16:44 (김학민), 세션 `20261010T164407-77da`(start 16:44:07), 녹화 `g1_s1`, attempts `servo_attempts_20261010_164210.jsonl`.

| # | GOAL_END | box_id | track | 송장(OCR 투표) | reason | attempts | grasped | 적재 | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:44:30 | …-77da-001 | 7 | 청담동 | OK | 1 | true | C0 PLACED | |
| 2 | 16:45:07 | …-002 | 8 | 청담동 | OK | 1 | true | C1 PLACED | |
| 3 | 16:45:45 | …-003 | 9 | 대치동 | OK | 1 | true | B0 PLACED | |
| 4 | 16:46:20 | …-004 | 10 | 역삼동 | OK | 1 | true | A0 PLACED | |
| 5 | 16:46:54 | …-005 | 11 | 역삼동 | OK | 1 | true | A1 PLACED | |
| 6 | 16:47:28 | …-006 | 12 | 대치동 | OK | 1 | true | B1 PLACED | |
| 7 | 16:48:03 | …-007 | 13 | 역삼동 | OK | 1 | true | A2 PLACED | |
| 8 | 16:48:39 | …-008 | 14 | 대치동 | OK | 1 | true | B2 PLACED | |
| 9 | 16:49:15 | …-009 | 15 | 청담동 | OK | 1 | true | C2 PLACED | |
| 10 | 16:50:02 | …-010 | 16 | 역삼동 0.60→0.65 (CODE_ONLY, LOW_CONF) | OK | 1 | true | RECHECK0 → HELD(DEVICE_ERROR) | 아래 |

- 10회 모두 TrackAndGrasp OK·grasped true·시도 1 (영상 확인 전). 10회 동안 box_tracker `Hz < 25` 0회, 최저 26.6 Hz.
- 10회차 흐름(sort_manager): LOW_CONF → RECHECK 칸 0 PLACE(16:50:02~16:50:19) → VIEW → 다시 읽기 요청 16:50:27 → 질문 16:50:33 "LOW_CONF conf=0.60: 후보 역삼동" → 30 s 무응답(`ask_timeout_s` 30) 16:51:03 NONE 판정 → HOLD 칸 0 으로 옮기려 MoveToZone RECHECK 칸 0 **PICK** → gateway `NOT_CONFIGURED: PICK 은 아직 구현 전 (10/13 재확인 흐름)` → SortResult **HELD RECHECK reason=DEVICE_ERROR attempts=1** → **PAUSED**. 박스는 재확인 칸 0 에 남음.
- label_reader track 16: `S07-01 역삼동 0.60 CODE_ONLY`(OCR 1948 ms), `0.69 CODE_ONLY → 투표 0.65`(2155 ms). confidence_min 0.6.
- DB(세션 77da): 001~009 PLACED(A3·B3·C3), 010 HELD RECHECK, 모두 attempts 1.
- 이 시점 A·B·C 각 3칸 사용 = 세 구역 모두 가득.

**s1 11~20회** — 10회차 PAUSED 뒤 트레이 비움·T8 재기동, 세션 `20261010T165518-45d2`(start 16:55:18), 같은 녹화 `g1_s1`·같은 attempts 파일. gateway 16:41:52 그대로.

| # | GOAL_END | box_id | track | 송장(OCR 투표) | reason | attempts | grasped | 적재 | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| 11 | 16:55:45 | …-45d2-001 | 17 | 청담동 | OK | 1 | true | C0 PLACED | |
| 12 | 16:56:22 | …-002 | 18 | 역삼동 | OK | 1 | true | A0 PLACED | |
| 13 | 16:56:55 | …-003 | 19 | 역삼동 | OK | 1 | true | A1 PLACED | |
| 14 | 16:57:28 | …-004 | 20 | 청담동 | OK | 1 | true | C1 PLACED | |
| 15 | 16:58:05 | …-005 | 21 | 청담동 | OK | 1 | true | C2 PLACED | |
| 16 | 16:58:54 | …-006 | 22 | 대치동 | OK | 1 | true | B0 PLACED | |
| 17 | 16:59:29 | …-007 | 23 | 대치동 | OK | 1 | true | B1 PLACED | |
| 18 | 17:00:04 | …-008 | 24 | 역삼동 | OK | 1 | true | A2 PLACED | |
| 19 | 17:00:40 | …-009 | 25 | 대치동 | OK | 1 | true | B2 PLACED | |
| 무효 | 17:01:21 | …-45d2-010 | 26 | S07-01 역삼동 0.50→0.56 (CODE_ONLY, LOW_CONF) | LOST / BOX_MISSING | 0 | false | — (FAILED reason=LOST → PAUSED) | **의도 시험(박스를 벨트와 비스듬히 투입)** → 무효 ①, 아래 "의도 시험" |
| 20 | 17:15:00 | `20261010T171422-3407-001` | 34 | S07-02 대치동 1.00 AGREE | OK | 1 | true | B0 PLACED(17:15:20) | 세션 `20261010T171422-3407`(start 17:14:22, T8 재기동 뒤). 단계: PREPARE 0 → TRACK 0.20 → DESCEND 3.20(x 85, 간격 −3.0·가로 0.1) → GRASP 5.80(z 84) → LIFT 7.93 → VERIFY 10.63, 11.37 s |

- 20회차 틱(goal `4b20ee34`): PREPARE 0.00 → TRACK 0.17 → **DESCEND 3.43 s**(TCP x 78.0, z 141.5, 벨트 방향 간격 −3.0 mm = 허용 3 의 경계, 가로 0.4) → 4.33 s 이후 박스 관측 없음(틱 visible 비어 있음) → **4.80 s LOST(BOX_MISSING)**, 시도 0(GRASP 전). box_tracker 같은 때: 17:01:18 창 box 118(hand_eye), 17:01:23 창 box 42, 17:01:28 창 box 0 — 영상 27.8~30 Hz, `Hz < 25` 0. label_reader track 26: 0.50·0.54·0.66 CODE_ONLY → 투표 0.56.
- g1-gate 1절 정의: 무효 ① "박스를 정한 위치·방향과 다르게 놓음". 실행자(김학민): 17:01 회차(track 26)와 17:06~17:10 goal 5개는 **일부러 기울이거나 뒤집어 본 시험** → 무효로 빼고 17:15 회차를 20회차로 기록.
- 11~20 동안 box_tracker `Hz < 25` 0회.

**의도 시험 — 박스를 기울이거나 뒤집어 투입 (17:01~17:10, G1 분모 밖, 김학민)**

박스 자세는 실행자가 일부러 바꿨다(회차별 정확한 각도·자세는 기록 없음). OCR 의 "180° 뒤집힘" 은 label_reader 판정 그대로.

| GOAL_END | goal | track | 세션 / box_id | OCR | reason | 시도 | 끝난 phase | 틱 요약 |
|---|---|---|---|---|---|---|---|---|
| 17:01:21 | `4b20ee34` | 26 | 45d2-010 | S07-01 역삼동 0.50~0.66 CODE_ONLY(투표 0.56) | LOST / BOX_MISSING | 0 | DESCEND | DESCEND 3.43 s(x 78, 간격 −3.0), DESCEND+0.87 s(z 111.0) 마지막 관측, 4.80 s LOST. 실행자: 벨트와 비스듬히 |
| 17:06:58 | `636e5fc2` | 28 | `20261010T170639-e4bd-001` | S07-01 역삼동 1.00 AGREE **(180° 뒤집힘)** | LOST / BOX_MISSING | 0 | TRACK | 시작 간격 **+31.9 mm**(박스가 TCP 하류), 가로 1.6. 0.50 s 마지막 관측, 1.00 s LOST |
| (goal 없음) | — | 29 | — | S07-01 역삼동 1.00 AGREE (180° 뒤집힘) | — | — | — | label_reader 판독만 기록 |
| 17:07:32 | `37b0182c` | 30 | `20261010T170721-696d-001` | S07-01 역삼동 1.00 AGREE (180° 뒤집힘) | LOST / BOX_MISSING | 0 | TRACK | 시작 간격 **+34.0**, 가로 **8.4**. 0.50 s 마지막 관측, 1.00 s LOST |
| 17:08:17 | `e4ba943c` | 31 | `20261010T170805-e86f-001` | S07-01 역삼동 1.00 AGREE | LOST / BOX_MISSING | 0 | DESCEND | DESCEND 3.17 s(x 84, 간격 −2.9·가로 0.2), DESCEND+0.83 s(z 112.4) 마지막 관측, 4.53 s LOST |
| 17:09:42 | `babd92db` | 32 | `20261010T170916-eb6e-001` | S07-01 역삼동 1.00 AGREE | **OK** | 1 | VERIFY | DESCEND 3.37(x 86), GRASP 5.97(z 84), VERIFY 10.90 → A0 PLACED |
| 17:10:10 | `ad7f6404` | 33 | `20261010T170916-eb6e-002` | S07-02 대치동 1.00 AGREE | LOST / BOX_MISSING | 0 | DESCEND | DESCEND 3.10 s(x 81, 간격 −3.0·가로 0.0), DESCEND+0.83 s(z 112.4) 마지막 관측, 4.43 s LOST |

- 비교(같은 틱 로그): 성공 회차(본 측정 19 `72422cfa`, 시험 32, 20회차 34)도 마지막 박스 관측은 DESCEND+0.83~0.87 s, z 110.9~112.3 으로 같다. 차이: 성공 회차는 그 뒤에도 하강이 이어져 z 83.8~83.9 에 도달, LOST 회차는 마지막 관측 뒤 틱에 TCP 기록이 없고 0.5 s(`lost_timeout_s`) 뒤 LOST. *(판정은 박병후 — voss_servo)*
- 이 시험들 동안 box_tracker `Hz < 25` 0.
- 시험 뒤 sort_manager 는 LOST 마다 PAUSED → T8 재기동 반복(세션 e4bd·696d·e86f·eb6e). 17:10:39 `명령 거부: PAUSED 에서는 resume`.

**gate_summary 최종 집계**(`--exclude 4b20ee34 636e5fc2 37b0182c e4ba943c babd92db ad7f6404`, 나머지 인자 같음) → `~/voss_data/1010/g1_s1_gate_summary_final.md`: **20사례 중 20 성공(100 %), 최초 시도 성공 20, 무효 6**, reason OK 20, 분모 밖 선언 전 9건. 사람이 센 본 측정 20회 = 표 20회.

(이전 집계, 무효 지정 없음 → `~/voss_data/1010/g1_s1_gate_summary.md`, 17:04):
- 20사례 중 **19 성공**, 최초 시도 성공 19, 무효 0(지정 안 함), reason OK 19·LOST 1, 자동 힌트 L 1. 분모 밖: 선언 전 9건.
- 사람이 센 회차 수(20)와 표의 회차 수(20) 같음.
- 도구 표기: 벨트 "h250(4.80 cm/s)" 는 voss_config 값(실측 4.76, #11). "하강 최대 오차 mm" 열이 20건 모두 59.5~59.9 — 접근 높이 140.8 과 파지 높이 81.8 의 차(59.0)와 비슷한 값(기록만, 도구 정의는 #137).
- 녹화 `g1_s1`: 17:04 기준 14.6 GB, 녹화 중.

## 7·8. VIEW 자세 · 박스 적재 15칸 (17:27~17:41, 학민 안내 7절, gateway pid 69693 그대로)

- 준비(17:2x): sort_manager `stop` → 벨트 12 V 끔 → T8·T7·T6·T5·T4·T3 Ctrl+C, gateway(T2)·브링업(T1)만 남김. 트레이 모두 비움.
- 17:27:24.881 gateway `RobotState BUSY action=SERVO` → 17:27:25.099 `servo_cmd 끊김(watchdog) → 0 속도 + move_stop`, 통계 `servo rx 0.2 Hz, speedl 1, 거부 0, 자름 0, watchdog 1, move_stop 1 ok`. 보낸 쪽은 로그에 없음 *(추측: T7 belt_servo 종료 때 0 명령)*. 로봇 움직임 보고 없음.
- **#7 VIEW:** 17:28:03 `move_to_zone RECHECK 칸 0 VIEW 시작` → 17:28:11.578 **OK 8.0 s**. 17:28:13 OBSERVE → **OK 8.0 s**. 속도 100 mm/s (안내는 30 mm/s; #41 때문에 gateway 재시작 안 함). `topic echo --once /voss/robot/pose`(stamp 1791620892.766 = 17:28:12.766, VIEW OK 1.2 s 뒤, frame base_link): **x 0.5179351, y −0.0393174, z 0.1205066 m**, 자세 쿼터니언 (−0.70747, 0.70674, −1.6e−5, 1.6e−5). 기대 (0.5179, −0.0393, 0.1205) ±3 mm 대비 **+0.04 · −0.02 · +0.01 mm** → measurements-1008 #13·#44 에 옮길 값.
- 손 건네기 연습(17:28~17:30, OBSERVE): 17:28:36 닫기 → **폭 38.0·grip False**(박스 안 잡힘) → 개방 90.4 → 닫기 40.6 True → 개방·닫기 3회(40.3·40.1·40.7, 모두 True).
- **#8 15칸 (모두 `{width: 39, force: 14}` 로 닫은 뒤 PLACE, 사람이 OBSERVE 에서 손으로 건넴):**

| 순서 | 칸 | 닫기 폭·grip·시간 | PLACE | gateway 안내 |
|---|---|---|---|---|
| 1 | A0 | 40.7·True·1678 ms (17:30:28) | **OK 17.4 s** (placed 17:31:25) | 특이점 3205/3206 ×2쌍 |
| 2 | A1 | 40.3·True·1891 ms | **OK 17.9 s** | 특이점 ×2쌍 |
| 3 | A2 | 40.6·True·1643 ms | **OK 18.5 s** | 특이점 ×2쌍 |
| 4 | B0 | 40.4·True·1995 ms | **OK 19.8 s** | — |
| 5 | B1 | 40.9·True·1650 ms | **OK 20.6 s** | — |
| 6 | B2 | 40.1·True·1878 ms | **OK 21.5 s** | — |
| 7 | C0 | 40.7·True·1678 ms | **OK 22.9 s** | 특이점 ×2쌍 |
| 8 | C1 | 41.4·True·1625 ms | **OK 23.6 s** | 수평 이동 높이 TCP 150 ×2, 특이점 |
| 9 | C2 | 40.6·True·1794 ms | **OK 32.3 s** | 트레이 안 이동 TCP 60 ×2, 특이점 |
| 10 | 재확인 0 | 40.4·True·1861 ms | **OK 17.4 s** | — |
| 11 | 재확인 1 | 40.7·True·**2128 ms** | **OK 18.5 s** | — |
| 12 | 재확인 0 (1 에 박스 둔 채) | 40.4·True·1678 ms | **OK 17.4 s** | — |
| 13 | 보류 0 | 40.3·True·1866 ms | **OK 21.6 s** | 수평 이동 높이 TCP 180 ×2, 특이점 |
| 14 | 보류 1 | 41.1·True·1686 ms | **OK 29.9 s** | 트레이 안 이동 TCP 70 ×2, 특이점 |
| 15 | 보류 0 (1 에 박스 둔 채) | 40.4·True·1685 ms | **OK 21.6 s** (placed 17:40:4x, 응답 17:40:54) | 수평 이동 높이 TCP 180 ×2, 특이점 |

- 참고값과 비교(안내 7절, 10/09 빈손 100 mm/s): A 17.5~18.8 → 17.4~18.5 · B 19.9~21.9 → 19.8~21.5 · C2 32.5 → 32.3 · HOLD1 30.2 → 29.9. 오류·BUSY·LIMIT 없음.
- 닫기 폭 40.1~41.4: 안내 7절 기대 40.7~43.0 보다 낮은 것 9/15 (40.1~40.6), belt_servo 파지 판정 범위 39.5~44.0 안. 닫기 시간 1625~2128 ms (2.1 s 초과 1회 — belt_servo `close_time_max_s` 2.1 은 이 수동 시험에 적용 안 됨).
- C 칸 이웃 박스 틈(≈2.4 mm): 실행자 눈 확인 "이상 없음"(틈 수치 측정은 안 함). 박스 찌그러짐: 15칸 동안 이상 없음(김학민 보고, 14 N).
- 끝난 뒤 로봇 OBSERVE, 그리퍼 열림, 트레이에 박스 13개(재확인 0·보류 0 은 2번째 박스 꺼냄).

## #41 판정용 확인 (17:42:37, gateway pid 69693 로그, 읽기 전용)

- 범위: `robot_gateway started: real …` **16:41:52** ~ 마지막 줄 **17:42:27** = **60.6 분, 재시작 없음**. 이 구간에 G1 s1 20사례·의도 시험 6개·VIEW·15칸 포함.
- `두산 호출 중단|FAULT`: **0**. `응답 없음|TIMEOUT|miss`: **0** (FAULT 는 응답 없음 3회 연속, doosan.py `max_misses=3`).
- `pose 조회 실패`: **1** — 16:41:52 `joint_states 없음·0.1 s 넘게 오래됨` (기동 직후, 첫 세션과 같은 양상). pose fail 합 1.
- **pose 5초 창 727개: 중앙 50.0, 최대 50.0, 최소 30.2 Hz(17:36:37). 45 미만 13개, 49 미만 25개.** skip 합 1214, queue wait 최대 106.4 ms.
- 45 미만 13개 시각·연관 이동 (모두 "트레이 안 이동: 칸 0 위 거쳐 TCP 60/70" 직후 5 s 창):

| 창 끝 | Hz | skip | 그때 이동 |
|---|---|---|---|
| 16:49:17·22·32·37 | 38.4·41.4·44.4·35.0 | 58·43·28·75 | G1 9회차 C2 PLACE (트레이 안 이동 16:49:18·34) |
| 16:58:07·12·27 | 40.2·39.6·33.2 | 49·52·84 | G1 15회차 C2 PLACE (16:58:09·24) |
| 17:36:17·37 | 34.2·**30.2** | 79·99 | 15칸 C2 (17:36:18·35) |
| 17:39:52·57, 17:40:07·12 | 38.6·42.0·44.4·35.8 | 57·40·28·71 | 15칸 보류 1 (17:39:53·17:40:09) |

- 45~49 Hz 창 12개: 46.0~46.4(C1 PLACE·C2 PLACE 중 "수평 이동 높이 TCP 150" 구간) · 48.2~48.4(보류 0 PLACE "수평 이동 높이 TCP 180" 구간). 나머지 창은 49 이상.
- G1 구간만(16:41:52~17:15:20) 봐도 45 미만 7개(최소 33.2) — 15칸 시험이 없었어도 미달.
- 앞 gateway(pid 17659, 12:29:36~16:0x) 최소 43.2 Hz 는 x 620 OBSERVE 복귀(특이점) 때. 그 세션 로그에 "트레이 안 이동"(C2·HOLD1 PLACE) 없음 — 12:21~12:23 빈손 C2·HOLD1 은 그 전 gateway 세션.
- **안내 8절 조건 대비: 60 분 ✅ · FAULT 0 ✅ · max_call_misses 0 ✅ · pose ≥ 45 Hz ❌ (최소 30.2).** 안내: 미달이면 #41 열어 두고 10/11 `scripts/measure_1009/queue_soak.py --minutes 5 → 30`. *(추측: 트레이 안 이동 경로 계산의 ikin 호출들이 같은 큐를 써서 pose 읽기가 skip 됨 — `_travel_z` 주석 "ikin 은 한 번씩 큐로 보낸다")*

## #41 로그 확인 명령 시험 (학민 15:53 안내 5절, 15:5x)

- 안내 명령은 `launch.log` 에서 `robot_gateway started: real` 을 찾는데, **launch.log 에는 노드 출력이 없어 대상이 비어 나온다**(output=screen). 노드 로그는 `~/.ros/log/python3_17659_1791602976846.log`(rcl 로그 파일).
- 같은 패턴을 노드 로그에 돌린 결과(12:29:37 ~ 16:0x):
  - `robot_gateway started: real …` 12:29:37 (1791602977)
  - `두산 호출 중단|FAULT`: **0**
  - `pose 조회 실패`: **1** — 12:29:37 `joint_states 없음·0.1 s 넘게 오래됨`(기동 직후 첫 메시지 전, #0 셋업 표)
  - `pose N Hz` 최솟값: **43.2** (5초 창 2482개 중 45 미만 2개, 중앙 50.0) — **14:37:42, 14:40:52** = x 620 에서 OBSERVE 복귀 중(#14 특이점 안내와 같은 때), 큐 대기 최대 101~102 ms, skip 34
  - pose fail 합: **1**

## 종료 (17:4x, 학민 안내 9절·런북 7장)

- 순서: (17:2x) sort_manager `stop` → 벨트 12 V 끔 → T8·T7·T6·T5·T4·T3 → (#7·#8 시험) → **T2 gateway 17:46:22.256 Ctrl+C** → 17:46:23.011 `process has finished cleanly` → **T1 브링업 17:46:23.15 SIGINT**(gateway 종료 뒤) → ros2_control·OnRobot 정상 종료, `gripper_joint_state_publisher` exit 1·rviz2 exit −6(10/08 21:53·10/10 16:03 브링업 종료 때와 같은 양상). 근거 `~/.ros/log/2026-10-10-16-41-52-*-69690/launch.log`, `…-16-03-40-*-53560/launch.log` 5499~5534행.
- gateway 마지막 줄 17:46:22.756 `pose 조회 실패: TIMEOUT 0.50s: …/motion/fkin` — Ctrl+C 0.50 s 뒤, 종료 처리 중(브링업은 그 뒤에 내려감). **gateway pid 69693 전체 구간 16:41:52~17:46:22 = 64.5 분, FAULT 0, 응답 없음 0, pose 조회 실패 2(기동 직후 1·종료 중 1).** 17:40:54 마지막 이동 뒤 pose 50.0 Hz·fail 0.
- 17:49 확인: ROS 노드 프로세스 없음. DB 컨테이너 `db-db-1` 은 켜 둠.
- belt_servo_real.yaml: 오늘 바뀐 값(`pose_lag_ms` 0.0, `hold_width_max_mm` 44.0) 반영돼 있음(레포 밖, 커밋 안 함).

## Drive `raw/1010/` 업로드 목록 (공용 PC `~/voss_data/1010/`)

| 경로 | 크기 | 내용 |
|---|---|---|
| `g1_s1/` | 18 G | G1 s1 bag (16:4x~17:15, 의도 시험 포함) |
| `g0_01/` | 4.8 G | G0 1회차 bag |
| `g1_s1_aborted_camera/` · `g1_s1_aborted_timeout/` | 4.1 G · 2.6 G | 중단된 G1 시도 2개 (카메라 끊김 · PLACE 60 s 시간 초과) |
| `track_grasp_05/` | 6.7 G | ② TrackAndGrasp |
| `track_rehearsal_02/` · `_03/` · `_04/` | 4.7 G · 448 K · 18 G | ① 추종·cancel |
| `pose_lag_js_01/` + `.csv` + `_eval.txt` | 962 M | #3 pose 지연 |
| `f04/` · `goto/` | 32 K · 68 K | #12 watchdog · #4 VERIFY 벤치 CSV |
| `logs/ros_log/` | 6.5 M | 오늘 `~/.ros/log` 노드·launch 로그 288개 사본 (gateway `python3_17659_*`·`python3_69693_*`, belt_servo, box_tracker, 카메라 등) |
| `logs/servo/` | 20 M | belt_servo attempts·ticks jsonl 4세트 (레포 `data/servo/`, 미추적) 사본 |
| `*.py`, `g1_s1_gate_summary*.md`, `measurements-1010.md` | — | 현장 도구·집계·이 기록 |
| (실행자 보관) | — | 펜던트 공간 제한 사진 3장, G0 휴대폰 영상 |

bag 합계 약 60 GB.

## 현장 도구 (레포 밖 `~/voss_data/1010/`, 커밋 안 함)

| 파일 | 하는 일 | 시험 |
|---|---|---|
| `servo_goto.py` | TCP 를 목표점까지 servo_cmd 로 이동(자세 고정). 거부: 목표 z < 80, 한 번 150 mm 초과, z < 140 에서 수평 3 mm 초과. 중단(+stop): 경로 이탈 5 mm, pose 0.3 s 끊김, 1.5 s 무이동, 시간 초과, Ctrl-C. 도착 0.2 mm | 도메인 77 dry_run gateway 에서 전체 순서 시험 후 실기 사용(#4) |
| `belt_speed.py` | /voss/vision/box 트랙별 직선 맞춤 → cm/s (실시간·bag, 읽기 전용) | #11 |
| `stopdist.py` | bag 의 /voss/robot/pose 로 취소 뒤 정지 시간·거리 계산(읽기 전용) | #5 |
| `wait_track.py` | track_id > N(·x ≥ X) 첫 유효 트랙 번호 출력(읽기 전용). `ros2 topic echo | awk` 가 파이프 버퍼로 출력이 늦어 대체 | ① 2~5회 |

## 미결·후속 (기록만)

- **#41:** 이슈 완료 기준(재시작 없이 60분↑·FAULT 0) 충족, 10/10 안내 8절의 pose ≥ 45 Hz 는 미달(최소 30.2, C2·HOLD1 트레이 안 이동 때) → #41 열어 두고 PL 판단(안내대로면 10/11 `queue_soak`). #41 댓글에 벤치·로그 결과 올림(10/10).
- **#44:** 15칸 OK → 이 PR 로 닫음. C2 32.3 s(> 30 s)·PICK 미구현은 안내 7절대로 #45·#32 로.
- **voss_servo (박병후 판단):** G1 의도 시험 LOST 4건과 OK 회차의 마지막 박스 관측 시점 비교("의도 시험" 절) · x ≥ 600 TRACK z 처짐(#13 행) · `hold_width_max_mm` 레포 기본 43.5 → 44.0 (G1 뒤 병후 PR) · belt_servo READY 로그 고정 문구("service 기준").
- 그리퍼 힘: 14 N 유지(10/10 결정). 박스 찌그러짐 관찰 1건(② 15:26 무렵 실행자 보고, 정도 미기록), 15칸 시험 중에는 이상 없음.
- box_tracker 주석 "게이트웨이 수신 시각"(joint_states 면 관절을 읽은 시각), hand_eye.yaml `pose_lag_ms_measured: 60.0`·`moving_spread_lag_mm: 2.73`, 런북 T5 — G1 뒤 후속(#140 리뷰, 김학민).
- 안내 5절 #41 확인 명령은 `launch.log` 대신 노드 로그(`~/.ros/log/python3_<pid>_*.log`)를 봐야 함("#41 로그 확인 명령 시험" 절).
