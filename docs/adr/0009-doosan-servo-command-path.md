# ADR-0009: robot_gateway 의 두산 서보 명령 경로

- 날짜: 2026-10-07
- 상태: 승인 제안 (2026-10-07, PL 승인 전). 경로는 결정(pending #8). 2부 실로봇 실측(10/07) 반영
- 결정자: 박병후(제안), 김학민(robot_gateway 구현 #41)
- 관련: SR-SW-04, SR-IF-09, pending-decisions #8, measurements-1006 #3, ADR-0002, `src/voss_servo/DESIGN.md` DEC-02 · DEC-16
- 번호: 0003·0007·0008 은 열린 PR(#48·#72·#75)이 쓰고 있어 0009 를 쓴다.

## 배경
belt_servo 는 30 Hz 로 `/voss/robot/servo_cmd`(geometry_msgs/TwistStamped, TCP 선속도 m/s, 각속도 0, frame base_link)를 낸다(topics.md belt_servo 행, MC-010). robot_gateway 는 이것을 두산 M0609 에 넘겨야 하고, 후보는 셋이다. 경로·타입은 실로봇에서 광고가 확인됐다(이슈 #55 김학민 10/07, PR #84 topics.md robot_gateway 행). 남은 질문은 "30 Hz 로 바뀌는 목표를 실제로 받아 움직이는가, 끊기면 멈추는가"였고, 10/07 실로봇 시험(measurements #3 2부)으로 답했다.

| | ① speedl_stream | ② servol_stream | ③ move_line ASYNC |
|---|---|---|---|
| 경로 | 토픽 `/dsr01/dsr_controller2/speedl_stream` | 토픽 `/dsr01/dsr_controller2/servol_stream` | 서비스 `/dsr01/dsr_controller2/motion/move_line` (`sync_type`=1) |
| 받는 것 | 속도 `vel[6]` + `acc[2]` + `time` | 목표 위치 `pos[6]` + 상한 `vel[2]`·`acc[2]` + `time` | 목표 위치 + 속도·가속 + 블렌딩 |
| DRFL | `Drfl->speedl` (`dsr_controller2.cpp:2315`) | `Drfl->servol` (`:2289`) | `Drfl->amovel` (`:464`) |

근거 전체(파일:줄, 에뮬레이터 표)는 measurements-1006 #3 에 있다.

## 결정
robot_gateway 는 **speedl_stream** 을 주 경로로 쓴다. servol_stream 은 대안, move_line ASYNC 는 쓰지 않는다. 적용 조건(reliable 퍼블리셔, 끊김 시 gateway 가 0 속도·정지를 보냄, acc 값, watchdog 순서)은 아래 '결과' 절에 실측 수치로 둔다.

## 고려한 대안
- **① speedl_stream**
  - 장점: belt_servo 출력(속도)과 의미가 같아 gateway 변환이 단위(m/s → mm/s ×1000)뿐이다. 현재 위치를 몰라도 된다. 실로봇에서 RT 연결 없이 30 Hz 명령을 받아 지령 이동량을 100 % 따라갔고(10 mm → 10.01~10.02), 시작 지연이 가장 짧다(acc 100 에서 62 ms).
  - 단점: **실로봇은 스트림이 끊겨도 마지막 속도로 계속 간다**(1.0 s 동안 +5 mm, 알람 1215 없음 — 에뮬레이터의 0.1 s 타임아웃은 실로봇에 없다). 정지 책임이 전부 robot_gateway 에 있다. `time` 은 목표 속도 도달 시간이고 가속 한계가 우선한다(알람 1216, 실로봇·에뮬레이터 같음: acc 20 → 0.25 s, 100 → 0.05 s) → 반응 속도는 `acc` 로 정한다. 위치 오차는 적분으로 쌓이므로 belt_servo 폐루프가 보정해야 한다(A안 전제와 같다).
- **② servol_stream**
  - 장점: 마지막 목표점에서 멈추므로 끊겨도 목표 이상으로 가지 않는다(실로봇: 뒤처진 1.25 mm 만 따라잡고 0.33 s 에 정지). 실로봇 10 mm → 10.02 mm. 관측 자세(ry ≈ −179°)에서도 실로봇 첫 시도에 동작했다.
  - 단점: `vel`·`acc` 는 목표가 아니라 **상한**이다(`DRFLEx.h:503` `fLimitVel`·`fLimitAcc`). gateway 가 "다음 위치 = 현재 + v·Δt" 를 만들어야 하고, 그 "현재"를 얻으려면 `get_current_posx` 를 스트림과 같은 콜백 그룹(직렬)에서 불러야 해 지연이 붙는다. 목표 자세(rx, ry, rz)를 함께 보내야 하는데 관측 자세(ry ≈ −179°)는 ZYZ 표현이 퇴화하는 근처다(에뮬레이터 ry = 0 에서 1회 불동작). 실로봇 시작 지연 205 ms 로 speedl 의 2~3 배이고, 알람 "[ServoL] Can't keep target time" 이 나왔다.
- **③ move_line ASYNC**
  - 장점: 가장 흔한 API 라 동작이 예측된다. 블렌딩(`blend_type`)을 고를 수 있다.
  - 단점: 매 틱이 서비스 호출이라 robot_gateway 단일 호출 큐(CLAUDE.md 규칙 3)를 30 Hz 로 점유한다. 앞 이동과 겹칠 때의 거동(블렌딩·대기)이 미정이고, 컨트롤러 콜백은 `radius` 를 `amovel` 에 넘기지 않는다(`:464`).

## 결과
belt_servo 출력(TwistStamped)과 TrackAndGrasp 액션은 바뀌지 않는다(DESIGN.md DEC-02). 바뀌는 것은 robot_gateway 안이다.

실로봇 2부 실측(10/07, DRCF `GF02120100`, measurements #3, 5 mm/s · ±10 mm):
| | speedl acc 20 | speedl acc 100 | servol (대안) |
|---|---|---|---|
| 30 Hz 수용 · 지령 이동 | 예 · 100 % | 예 · 100 % | 예 · 100 % |
| 명령 → 움직임 시작 | 113.5 ms | 61.8 ms | 205.4 ms |
| 퍼블리시가 끊기면 | **계속 감** (1.0 s 에 +5 mm) | **계속 감** | 목표점(+1.25 mm)에서 0.33 s 에 정지 |
| 속도 0 재전송 → 정지 | ≈ 0.41 s | ≈ 0.15 s | — |

robot_gateway 적용 조건 (speedl):
1. 두산 스트림 퍼블리셔는 **reliable** 로 만든다. 컨트롤러 구독이 reliable(speedl depth 10) 이라 best_effort 퍼블리셔는 연결되지 않는다.
2. **정지 책임은 gateway 에 있다.** 컨트롤러는 끊김을 감지하지 않는다. `servo_cmd` 만료 watchdog 이 끊김을 감지하면 즉시 속도 0 speedl 을 보내고, 정지가 확인되지 않으면 `motion/move_stop`(별도 콜백 그룹)을 부른다. belt_servo 가 의도적으로 멈출 때도 마지막 명령은 속도 0 이어야 한다.
3. watchdog 값(PR #84: 200 ms 제안)은 F-04 에서 정한다. 근거: 48 mm/s 추종 중 200 ms 이면 감지까지 약 9.6 mm, acc 100 감속(v²/2a ≈ 11.5 mm)까지 합쳐 20 mm 넘게 더 갈 수 있다.
4. `acc` 는 `time` 보다 우선한다(`time` 은 0 으로 둔다). 5 mm/s 에서 acc 100 mm/s² 가 시작 지연을 114 → 62 ms 로 줄였다. 추종 속도(48 mm/s)에서의 acc 값은 T26 #35 · T27 #36 실기에서 정한다(제안값, pending #4 전).
5. 스트리밍 중에는 `get_current_posx` 를 부르지 않거나 주기를 낮춘다(스트림 콜백과 직렬). `/voss/robot/pose` 는 TF·joint_states(100 Hz) 기반으로 낼 수 있는지 학민과 검토한다.
6. 에뮬레이터(`GF03020000`)는 끊김 처리가 실로봇과 달랐다(0.1 s 타임아웃 1215). 정지·안전 동작은 에뮬레이터 결과를 근거로 쓰지 않는다.

리스크: 2·3 이 구현되기 전에는 belt_servo 가 죽거나 DDS 가 끊기면 로봇이 마지막 속도로 계속 간다. 10/08 개루프 베이스라인(T26 #35) 실기는 gateway watchdog(0 속도 전송)이 들어간 뒤에 한다. ADR-0002 의 "실행 경로 문제와 폐루프 성능 판단은 구분해 기록한다"를 따른다.
