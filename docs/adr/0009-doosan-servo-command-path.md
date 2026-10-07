# ADR-0009: robot_gateway 의 두산 서보 명령 경로

- 날짜: 2026-10-07
- 상태: 승인 제안 (2026-10-07, PL 승인 전). 경로는 결정(pending #8), 적용 조건 수치는 2부 실로봇 실측 후 "결과" 절에 채운다
- 결정자: 박병후(제안), 김학민(robot_gateway 구현 #41)
- 관련: SR-SW-04, SR-IF-09, pending-decisions #8, measurements-1006 #3, ADR-0002, `src/voss_servo/DESIGN.md` DEC-02 · DEC-16
- 번호: 0003·0007·0008 은 열린 PR(#48·#72·#75)이 쓰고 있어 0009 를 쓴다.

## 배경
belt_servo 는 30 Hz 로 `/voss/robot/servo_cmd`(geometry_msgs/TwistStamped, TCP 선속도 m/s, 각속도 0, frame base_link)를 낸다(topics.md belt_servo 행, MC-010). robot_gateway 는 이것을 두산 M0609 에 넘겨야 하고, 후보는 셋이다. 경로·타입은 실로봇에서 광고가 확인됐다(이슈 #55 김학민 10/07, PR #84 topics.md robot_gateway 행). 남은 질문은 "30 Hz 로 바뀌는 목표를 실제로 받아 움직이는가, 끊기면 멈추는가"다.

| | ① speedl_stream | ② servol_stream | ③ move_line ASYNC |
|---|---|---|---|
| 경로 | 토픽 `/dsr01/dsr_controller2/speedl_stream` | 토픽 `/dsr01/dsr_controller2/servol_stream` | 서비스 `/dsr01/dsr_controller2/motion/move_line` (`sync_type`=1) |
| 받는 것 | 속도 `vel[6]` + `acc[2]` + `time` | 목표 위치 `pos[6]` + 상한 `vel[2]`·`acc[2]` + `time` | 목표 위치 + 속도·가속 + 블렌딩 |
| DRFL | `Drfl->speedl` (`dsr_controller2.cpp:2315`) | `Drfl->servol` (`:2289`) | `Drfl->amovel` (`:464`) |

근거 전체(파일:줄, 에뮬레이터 표)는 measurements-1006 #3 에 있다.

## 결정
robot_gateway 는 **speedl_stream** 을 주 경로로 쓴다. servol_stream 은 대안, move_line ASYNC 는 쓰지 않는다. 적용 조건(reliable 퍼블리셔, 0.1 s 안 퍼블리시 보장, acc 값, watchdog 순서)은 2부 실측 후 '결과' 절에 수치로 채운다.

## 고려한 대안
- **① speedl_stream**
  - 장점: belt_servo 출력(속도)과 의미가 같아 gateway 변환이 단위(m/s → mm/s ×1000)뿐이다. 현재 위치를 몰라도 된다. 컨트롤러가 **0.1 s 동안 다음 명령이 없으면 스스로 멈춘다**(에뮬레이터 알람 1215) — 스트림이 끊길 때 가장 안전하다. 비 RT 판은 TCP 명령 채널(`CNDKHandler::SendMoveSpeedLCommand`)이라 RT 연결이 필요 없을 것으로 예측된다.
  - 단점: 같은 타임아웃 때문에 명령 간격이 0.1 s 를 넘으면 추종 중에도 멈춘다 → gateway 퍼블리시 주기가 흔들리거나 컨트롤러 구독 큐(depth 10)에 명령이 밀리면 정지 원인이 된다. `time` 은 목표 속도 도달 시간이고 가속 한계가 우선한다(알람 1216: acc 20 mm/s² → 0.25 s, 100 → 0.05 s). 추종 반응을 빠르게 하려면 `acc` 를 올려야 하고 값은 실측으로 정한다. 위치 오차는 적분으로 쌓이므로 belt_servo 폐루프가 보정해야 한다(A안 전제와 같다).
- **② servol_stream**
  - 장점: 마지막 목표점에서 멈추므로 끊겨도 목표 이상으로 가지 않는다(에뮬레이터: 끊긴 뒤 뒤처진 1.8 mm 만 따라잡고 정지). 에뮬레이터에서 지령 10 mm 를 10.0 mm 로 정확히 따라갔다.
  - 단점: `vel`·`acc` 는 목표가 아니라 **상한**이다(`DRFLEx.h:503` `fLimitVel`·`fLimitAcc`). gateway 가 "다음 위치 = 현재 + v·Δt" 를 만들어야 하고, 그 "현재"를 얻으려면 `get_current_posx` 를 스트림과 같은 콜백 그룹(직렬)에서 불러야 해 지연이 붙는다. 목표 자세(rx, ry, rz)를 함께 보내야 하는데 관측 자세(ry ≈ −179°)는 ZYZ 표현이 퇴화하는 근처다 — 에뮬레이터에서 이전 표현의 자세로 보낸 1회는 움직이지 않았다.
- **③ move_line ASYNC**
  - 장점: 가장 흔한 API 라 동작이 예측된다. 블렌딩(`blend_type`)을 고를 수 있다.
  - 단점: 매 틱이 서비스 호출이라 robot_gateway 단일 호출 큐(CLAUDE.md 규칙 3)를 30 Hz 로 점유한다. 앞 이동과 겹칠 때의 거동(블렌딩·대기)이 미정이고, 컨트롤러 콜백은 `radius` 를 `amovel` 에 넘기지 않는다(`:464`).

## 결과
어느 경로든 belt_servo 출력(TwistStamped)과 TrackAndGrasp 액션은 바뀌지 않는다(DESIGN.md DEC-02). 바뀌는 것은 robot_gateway 안이다. 1부에서 나온, 경로와 상관없이 gateway 가 지켜야 할 점:
- 두산 스트림 퍼블리셔는 **reliable** 로 만든다. 컨트롤러 구독이 reliable(depth 10/20) 이라 best_effort 퍼블리셔는 연결되지 않는다.
- 스트리밍 중에는 `get_current_posx` 를 부르지 않거나 주기를 낮춘다(스트림 콜백과 직렬). `/voss/robot/pose` 는 TF·joint_states 기반으로 낼 수 있는지 학민과 검토한다.
- speedl 을 쓰면 PR #84 의 `servo_cmd` 만료 watchdog(200 ms 제안)보다 컨트롤러 타임아웃(0.1 s)이 먼저 동작한다. watchdog 값과 "끊김 → 정지" 순서를 F-04 실측에서 함께 정한다.
- 남은 실측(2부, `scripts/measure_1006/servo_stream_check.md`): 실로봇에서 명령 수용, 반영률·지연, 끊김 뒤 정지 시간·거리, 알람 1215·1216 이 같은지, `acc` 에 따른 반응.
- 리스크: 2부에서 speedl 이 실로봇 펌웨어(`GF02120100`)에서 다르게 동작하면 10/08 개루프 베이스라인(T26 #35)·10/10 게이트(ADR-0002) 일정에 영향이 있다. ADR-0002 의 "실행 경로 문제와 폐루프 성능 판단은 구분해 기록한다"를 따른다.
