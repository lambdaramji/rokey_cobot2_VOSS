# ADR-0005: RG2 는 robot_gateway 안에서 Modbus TCP 로 직접 제어한다

- 날짜: 2026-10-06
- 상태: 제안됨
- 결정자: 김학민
- 관련: SR-HW-02, SR-SW-05, pending-decisions #9, measurements-1006 #4 #8

## 배경
RG2 그리퍼를 제어할 수 있는 경로가 세 가지다. 10/06 실기에서 셋 다 동작을 확인했다(measurements #4).

## 결정
- robot_gateway 가 Compute Box(192.168.1.1:502, unit 65)에 Modbus TCP 로 직접 명령한다. 레지스터 0 힘(0.1 N), 1 폭(0.1 mm), 2 제어(16), 상태 268 bit1 `grip_detected`, 폭 267/275.
- 브링업의 onrobot ROS 2 드라이버는 그대로 두되 명령은 보내지 않는다. 함께 떠 있어도 읽기·쓰기가 정상임을 확인했다.
- Compute Box 의 WebLogic 프로그램 "C2 - voss"(디지털 I/O 로 파지·개방)는 펜던트로 손 시험할 때만 쓰는 예비다. 시스템 운전 중에는 STOP 해서 두 경로가 그리퍼를 동시에 제어하지 않게 한다.
- 파지 성공 판정은 `grip_detected` 를 주로, 폭(보고값 39.5~41.5 mm)을 보조로 쓴다.

## 고려한 대안
- onrobot ROS 2 드라이버(`/onrobot/sendCommand`): 힘을 바로 지정하지 못하고(기본 40 N, 2.5 N 단계), 응답이 이동 완료를 기다리지 않으며, 파지 감지가 없다. joint_states 의 `header.stamp` 가 0 이다.
- WebLogic + 디지털 I/O: 펜던트·DRL 만으로 쓸 수 있고 전원을 다시 켜도 유지된다. 그러나 폭·힘이 웹 화면의 고정값이고, 결과가 신호 두 개(파지 성공·열림)뿐이며, 명령이 두산 컨트롤러를 거쳐 단일 호출 큐의 부담이 늘어난다.

## 결과
- robot_gateway 가 로봇과 그리퍼를 모두 소유한다(절대 규칙 3과 같은 결).
- `voss_config.yaml` 의 gripper 값(pre_open 90, grasp_width 39, force 14 N)을 그대로 Modbus 명령에 쓴다. 폭은 RG2 보고값이다.
- 리스크: WebLogic 을 STOP 하지 않고 시스템을 돌리면 DIO 입력에 따라 그리퍼가 덮어써질 수 있다. 브링업 체크리스트에 "WebLogic STOP"을 넣는다(T32).
