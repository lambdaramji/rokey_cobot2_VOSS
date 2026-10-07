# VOSS 추종·파지 설계 노트 (박병후)

- 문서 ID: VOSS-BH-DECISION-001 · 버전 r5 · 2026-10-07 (KST) · 결정자: 박병후
- 기준 커밋: main `e8dd5e5` (#63 · #65 · #57 · #70 반영본). r4 는 `668703e` 기준이라 낡았다. r5.1: 그 뒤 머지된 #64(`6302204`, belt.direction_base·값 규칙)·#79(`671c67f`, BRD v1.3)만 반영(김학민 리뷰).
- 성격: 박병후 개인 설계 노트. **팀 계약은 docs/interfaces 가 우선**이고, 이 문서는 "왜 이렇게 골랐나 · 무엇을 유보했나"를 남긴다. 팀 결정이 필요한 항목은 pending-decisions / ADR 로 올리고 여기서는 가리키기만 한다.
- 읽는 법 (초급 개발자 기준): §2 대조표에서 r4 와 레포의 차이를 먼저 보고, §5 카드에서 이유를 읽는다. 처음 나오는 용어는 그 자리에서 한 줄로 풀었다. 수치는 모두 레포 문서에서 가져왔고, 레포에서 못 찾은 것은 "확인 필요"로 적었다.
- 출처 약어: topics.md = docs/interfaces/topics.md, voss_msgs.md = docs/interfaces/voss_msgs.md, measurements #n = docs/measurements-1006.md 의 n 번 항목, pending #n = docs/pending-decisions.md 의 n 번, MC-nnn = SRD 상호확인 합의 번호(#50 · #51 · #52 · #53), PR #n = GitHub PR.

## 2. 레포 대조표 (r4 → main e8dd5e5)

r4 에서 "미확인 · 후보"였다가 레포에서 확정된 것, r4 와 반대인 것, 여전히 미정인 것을 한 표로 모았다.

| 카드 | r4 | 레포 현재 (출처) | 상태 |
|---|---|---|---|
| DEC-01 좌표 | 베이스 좌표 채택. 기준점 · frame · offset 은 계약 후보 | `BoxTrack.position_base` = stamp 시각에 관측한 **박스 윗면 중심**, m, base_link. `position_valid` · `position_source`(SOURCE_*) · `calib_version` 추가. TCP 목표는 belt_servo 계산. 벨트 위 파지 높이 TCP z = `position_base.z − 19 mm` 를 belt_servo 파라미터 YAML 에 (topics.md belt_servo 행, voss_msgs.md BoxTrack, MC-001 · 009) | 확정. 19 mm 는 31 mm 면 기준으로 pending #16 결정(10/07)과 함께 확정 |
| DEC-02 속도 목표 | 속도 목표 + speedl 계열 우선, 장비 지원 확인 전 | `servo_cmd` = TwistStamped, TCP 기준 선속도 m/s · 각속도 rad/s, frame_id base_link, G0 각속도 0 (topics.md, MC-010). gateway 두산 경로는 `/dsr01/servol_stream`(10/06 확인 표기) 또는 move_line ASYNC. measurements #3 ☐, pending #8 미정 | 출력 확정 / 두산 경로 **미정** |
| DEC-03 시각 · 예측 | 촬영 시각 + 일정 속도 예측. 시계 매핑 · pose 이력 미정 | `/voss/robot/pose` = TCP, ~50 Hz, stamp = `get_current_posx` 응답 수신 시각, RTT/2 사용 금지 (MC-004). 촬영 시각 pose 보간은 box_tracker 책임 (MC-001 · 002). 벨트 4.8 cm/s (measurements #1). stamp 나이만으로 폐기 금지 (MC-031) | 확정 |
| DEC-04 FF+P | FF 는 실측 벨트 속도, 수치는 실기에서 | `belt.speed_cmps 4.8`, `belt.direction_base [0.99992, −0.01292, 0.0]`(베이스 기준 진행 단위벡터, +x 에서 −0.74°, measurements #6. #64 머지 `6302204`) — 소비 노드는 기동 때 ‖v‖ = 1 ± 0.01 검사 (voss_config.md 값 규칙) | 확정 |
| DEC-05 FSM | prepare→…→verify, 높이 · 전환 대기 | feedback.phase = PREPARE/TRACK/DESCEND/GRASP/LIFT/VERIFY 대문자 6종. `grasped` = LIFT · VERIFY 완료 (TrackAndGrasp.action, voss_msgs.md) | 확정 |
| DEC-06 파지 판정 | 유보. 직접 확보 피드백 실험 우선 | Gripper.srv 응답은 `ok` · `width_actual` 뿐. GRASP→LIFT 조건 = 닫힘 완료 응답 + `grip_detected` + 검증된 보고폭 범위 (voss_msgs.md). `grip_detected` 는 srv 에 **아직 없음**. measurements #8: 14 N, 31 mm 면, 쥔 폭 40.1~40.3 · 빈손 38.7. 늦은 응답 폐기 (MC-012 · 013) | 조건 확정 / srv 필드 미정 |
| DEC-07 action · 정지 | 정지 확인 불가 = `STOP_UNCONFIRMED` 오류 표시 | `STOP_UNCONFIRMED` **삭제** (#53 박병후 최소안). 정지 요청 실패 = ABORTED + `DEVICE_ERROR` + 로그, sort_manager PAUSED, 수동 재개 (voss_msgs.md) | **r4 와 반대 → 정정** |
| DEC-08 재시도 · 게이트 | 재시도 채택, 자동 개루프 전환 없음 | `attempts` ≤ 3 servo 단독 카운터, goal 1개당 result 1건, 바쁘면 reject. 게이트 14/20 미달이어도 자동 전환 없음, ①B안 ②범위 축소 ③A안 10/12 연장 (ADR-0002, plan.md, pending #3) | 확정 |
| DEC-09 2차 OCR | servo 수렴 신호를 비차단 전달하는 후보 | 2단계 프레임은 **영상 품질로만** 고르고 phase 에 의존하지 않음 (MC-007). `LabelCrop.stage` 는 box_tracker 가 `SortState.track_id` 로 정함 (voss_msgs.md) | 수정 (수렴 신호 불필요) |
| DEC-10 설정 | 시작 전 설정 스냅샷, 공급 경로 미정 | CLAUDE.md 규칙 5: voss_config.yaml 을 읽는 노드는 sort_manager 뿐. #64 값 규칙(머지 `6302204`): 정적 값은 bringup launch 가 파라미터로 넘김(null 키는 넘기지 않음 → 그 값을 쓰는 노드는 READY 거부), 각 노드가 `config_version`·`config_sha256` 로그 | 규칙 확정 / belt_servo 파라미터 구현 대기 |
| DEC-11 증거 | G0 정의, 로그 항목 | 로그 = 시도 번호 · 벨트 속도 · 결과 · 실패 원인 (ADR-0002). 시도별 로그 `data/`, 집계만 ADR (src/voss_servo/CLAUDE.md) | 확정 (형식) |
| DEC-12 칼만 | 초기 미도입 | 레포에 추정기 관련 계약 없음. 변화 없음 | 유보 |
| DEC-13 스택 | rclpy · NumPy · 명시적 FSM | voss_servo 는 rclpy 골격(belt_servo.py)만 있고 package.xml 의존은 rclpy · voss_msgs 뿐. NumPy 의존 미선언 | 확정 (골격) / NumPy 확인 필요 |
| DEC-14 비동기 · 장비 | 실행 구조 미정 | goal 실행 중 gripper 는 belt_servo 만 호출, 비동기, 응답 = RG2 동작 완료 또는 timeout (topics.md). 두산 서비스는 gateway 단일 큐만 (CLAUDE.md 규칙 3) | 확정 (원칙) |
| DEC-15 QoS | best_effort · depth 1 은 후보 | box · pose · servo_cmd = best_effort · volatile · depth 1 (topics.md QoS 표, pending #1 수용) | 확정 |
| DEC-16 watchdog | 수치 · 정지 수단 미정 | topics.md 에 watchdog · cmd 유효기간 · stop 수단 명세 없음. voss_msgs.md 는 "servo_cmd 만료 워치독(값은 실측 후)"만 언급. RobotState 는 김학민 10/07 정의 예정 | 미정 |
| DEC-17 파지 면 · 자세 | 고정 자세, 27 mm 높이 가정 | pending #16 **결정(10/07)**: 31 mm 면 파지(46 mm 변 = 벨트 방향, 닫힘축이 벨트를 가로지름), 목표 폭 39 mm(보고값) · 14 N, 파지 높이 TCP z = position_base.z − 19 mm. 고정 자세 · 각속도 0 (MC-010). 박스 27 mm. 남은 일: ADR(김학민). BRD TR-PICK-06 은 v1.3 으로 정정됨(#79) | 확정 |
| DEC-18 배포 | host 실행 | architecture.md 호스트 배포 유지. 공용 PC 사양 measurements #5 (CycloneDDS lo 전용 → 개인 PC 에서 토픽 안 보임) | 확정 (방향) |

## 3. 공부 · 논의 순서 (r4 §2 요약)

1. 역할 분리: 남현지 = 관측 · 비전 · sort_manager, 박병후 = 관측과 로봇 피드백 사이의 추종 · 파지 판단, 김학민 = 장비 실행(gateway), 정의석 = 음성 · HMI · DB.
2. 좌표 · 시간 · 추종 원리: 픽셀과 실제 거리의 차이, 손목 카메라 변환, 촬영 시각, 벨트 속도 피드포워드, 폐루프 보정과 개루프 추종 비교.
3. 로봇 출력 경로: 위치 목표와 속도 목표를 비교하고 topic / service / action 의 역할과 두산 API 명령 의미를 구분.
4. 픽업 구조: manager 전체 상태와 servo 내부 단계, 그리퍼 비동기 요청, 접수 · 완료 · 확보, 취소와 물리적 정지 확인을 구분.
5. 팀 문서와 비교: 큰 구조와 FF+P 는 일치. 픽셀 중심 설명을 베이스 좌표 오차로 구체화.
6. 최소 연결 기준선(G0): 단일 박스 인식 → 픽업 → 적재 → DB 저장 · 조회 → 복귀를 먼저 만든다.
7. 1차 방향 선택: ①~⑤ · ⑦ · ⑩ · ⑪ 채택, ⑥ 유보, ⑧ 조건부, ⑨ 일부 채택.
8. 좌표 결정: 베이스 오차 계산 + 남현지 비전 노드가 변환 결과 제공 (→ #50 에서 BoxTrack.position_base 로 계약됨).
9. 추정기: 초기 칼만 필터 미도입, 실측 벨트 속도로 일정 속도 예측.
10. 공통 기록 기준: 칼만 · PID · speedl 등 모든 선택을 같은 8칸 카드로 기록 (r4).
11. 레포 대조(r5): #50 · #53 · #57 · #63 · #65 · PR #64 와 대조해 확정 · 정정 · 미정을 나눔. 실험 · 회의 · 합의는 레포에 있는 것만 적는다.

## 4. 우선순위와 기준선

| 구분 | 범위 | 현재 처리 |
|---|---|---|
| A: 첫 전체 흐름 필수 (G0) | 기본 인식 / OCR · 구역 판단 · 단일 픽업 · 적재 · DB 저장 · 복귀, ID · 시각 · 좌표 · 설정 · 안전 중단 | 계약을 먼저 맞추고 구현. 성공 판단 경로와 안전값은 첫 실기 전에 확인 |
| B: 후속 필수 | 재시도, 음성 / HMI / 판독 예외, 성공률 · 주기 · 지연 · 사이클 검증 | 기본 흐름 이후 보완. 선택 기능으로 바꾸지 않음 |
| B 중 별도 판단 | 추종 중 2단계 OCR | 구조상 가능 여부를 B 단계에서 남현지와 판단 (DEC-09) |
| C: 선택 | 자연어 규칙 변경 · 신규 구역 교시 | 기본 흐름 이후. 선행조건으로 넣지 않음 |
| 내부 고도화 후보 | 칼만 필터 · 온라인 속도 추정 · 전체 PID · MPC | 필요와 실측 근거가 생기면 검토. G0 착수 조건에서 제외 |

초기 기술 기반: **Python 3.12, ROS 2 Jazzy / rclpy, NumPy, 명시적 Python 상태기계**. servo / gateway 는 호스트 실행(architecture.md). 실제 PC · 드라이버 버전, executor 구조와 부하 성능은 아직 검증하지 않았다. voss_servo 는 현재 rclpy 골격뿐이다(belt_servo.py).

## 5. 결정 카드

각 카드는 8칸 고정: 상태 / 문제 / 선택과 이유 / 대안과 미채택 이유 / 한계 · 성립 조건 / 레포 확정 사항 / 남은 결정 · 실측 / 연결. 상태 값은 채택 · 레포 확정 · 조건부 · 유보 · 미정이며 "r4 상태 → 레포 반영 후 상태"로 적는다. r4 의 IC- / VT- / TBD- / NEW-B 번호는 괄호로만 병기한다.

### BH-DEC-01 — 오차 좌표계와 변환 담당
- **상태:** 채택 → 레포 확정. 파지 높이 19 mm 도 pending #16 결정(10/07)으로 확정.
- **문제:** 실제 TCP(= 툴 중심점, 여기서는 핑거 끝)와 박스 파지 목표의 차이를 재고, 벨트 속도 보정 · 하강 · 파지를 같은 공간에서 이어야 한다. 손목 카메라는 로봇과 함께 움직인다.
- **선택과 이유:** 베이스 좌표(base_link = 로봇 밑판 기준 고정 좌표계)에서 오차를 m 단위로 계산한다. 픽셀 → 베이스 변환은 비전(남현지) 단일 책임으로 두어 캘리브레이션 관리와 역할이 맞고, 나는 TCP 목표 계산에 집중한다.
- **대안과 미채택 이유:** 픽셀 오차 제어(IBVS)는 하강 중 거리 변화 보정과 FF 와의 기하 관계가 추가로 필요해 이번 주 제어 방식에서 미채택(영구 배제 아님). 별도 변환 노드 · servo 내부 변환은 초기 미도입. voss_msgs.md 가 "servo 는 비전 변환 함수를 가져다 쓰거나 따로 구현하지 않는다"로 못 박았다.
- **한계 · 성립 조건:** 변환의 체계적 오류가 그대로 목표 오류가 된다. RGB + 알려진 박스 높이 27 mm + 핸드아이 캘리브레이션(카메라가 로봇 손목 어디에 붙어 있는지 재는 작업) + 촬영 시각 pose 가 맞아야 한다. 캘리브레이션 검증점 오차(measurements #7)는 아직 ☐.
- **레포 확정 사항:** `position_base` = stamp 시각 관측 박스 윗면 중심, m, base_link, TCP 목표 아님(voss_msgs.md, MC-001). `position_valid` false 면 쓰지 않음, `position_source` 는 SOURCE_NONE / SOURCE_OBSERVE_HOMOGRAPHY / SOURCE_HAND_EYE 상수로 비교, `calib_version` 기록(BoxTrack.msg). 벨트 위 파지 높이 TCP z = `position_base.z − 19 mm`(박스 27 − 핑거 끝 박스 밑면 +8, measurements #6)를 belt_servo 파라미터 YAML 에 둔다(MC-009). servo 는 TCP 로 명령하므로 TCP 오프셋을 직접 쓰지 않는다(topics.md).
- **남은 결정 · 실측:** topics.md 의 "31 mm 면 기준 후보" 문구를 확정으로 고치는 docs/interfaces 갱신(담당자 확인). 이동 중 SOURCE_HAND_EYE 값의 일관성(정지 박스를 카메라가 움직이며 봐도 같은 위치가 나오는지), 오차 · 나이 · 갱신율 실측. measurements #7 결과 수신.
- **연결:** DEC-03 · 15 · 17. 남현지 box_tracker(#25~#33 중 해당 이슈), 김학민 TCP 등록(#57). 내 이슈 T27 #36. (IC-VISION-02 / ROBOT-02, TBD-002 / 003 / 020, NEW-B-01, VT-BH-01 / 02)

### BH-DEC-02 — 속도 목표·speedl과 위치 목표·servol/amovel
- **상태:** 채택 → 출력 형식은 레포 확정, 두산 실행 경로는 **미정**(pending #8). T25 #34 가 가장 급한 미결.
- **문제:** 제어기가 30 Hz 로 계속 바꾸는 XY / Z 속도 목표를 장비가 어떤 의미로 받는지 맞춰야 한다. 공개 메시지 타입이 있다는 것과 설치된 장비에서 실제로 동작한다는 것은 다르다.
- **선택과 이유:** belt_servo 는 **속도 목표**(TwistStamped = 선속도 · 각속도에 시각 · frame 을 붙인 표준 메시지)만 낸다. FF+P 의 출력이 속도라 계산 의미와 바로 이어지고, 두산 API 호출 · 단위 변환 · 한계는 김학민 gateway 에 모은다. belt_servo 구현은 gateway 가 servol_stream 을 쓰든 move_line ASYNC 를 쓰든 **독립**이다.
- **대안과 미채택 이유:** servol(위치 스트리밍) · 짧은 상대 move_line ASYNC(짧은 직선 이동을 기다리지 않고 큐에 넣는 방식)는 속도에서 다음 위치 · 시간 · 제한을 만드는 변환이 gateway 쪽에 필요하다. 초기 주 경로로는 미채택이지만 속도 스트리밍이 안 되면 바로 검토한다(영구 배제 아님). 속도 값을 servol 의 위치 필드에 그대로 넣을 수는 없다.
- **한계 · 성립 조건:** 어떤 경로든 30 Hz 갱신 · 최신값 처리 · 실제 정지를 자동으로 보장하지 않는다. r4 는 "speedl 우선"이라 썼지만 topics.md 는 `/dsr01/servol_stream` 과 move_line ASYNC 만 적고 있어 **용어가 다르다**. 어느 쪽이 설치된 drcf(`GF02120100`, measurements #2)에서 되는지는 실측 전이다.
- **레포 확정 사항:** `servo_cmd` = geometry_msgs/TwistStamped, TCP 기준점 선속도 m/s · 각속도 rad/s, frame_id base_link, G0 추종은 고정 자세 · 각속도 0(topics.md, MC-010). gateway 두산 경로 표기: `/dsr01/dsr_controller2/motion/move_line`(ASYNC), `/dsr01/servol_stream`(10/06 확인)(topics.md robot_gateway 행). 그러나 measurements #3(servol_stream 유무 · 주기)은 ☐, pending #8 미정 → "10/06 확인"의 근거는 **확인 필요**.
- **남은 결정 · 실측:** measurements #3 기록(토픽 존재 · 주기 · 단위 · 낮은 속도 명령 대비 실제 움직임 · 최신값 처리 · publisher 소실 시 동작) → pending #8 결정 → ADR. 공용 PC 에서만 가능.
- **연결:** DEC-04 · 07 · 15 · 16. 김학민 robot_gateway(#41). 내 이슈 T25 #34. (IC-ROBOT-01 / DEVICE-01, TBD-014 / 017 / 020, NEW-B-02, VT-BH-02 / 04)

### BH-DEC-03 — 관측 시각·일정 속도 예측·ID
- **상태:** 채택 → 레포 확정.
- **문제:** 촬영과 제어 사이에 박스가 움직인다. 손목 카메라 자체의 움직임이 영상에 섞이고, 다른 박스나 다른 시점의 값을 쓰면 잘못된 목표가 된다.
- **선택과 이유:** 예측 위치 = 촬영 시각의 관측 위치 + 벨트 속도 × (제어 시각 − 촬영 시각). 벨트 속도가 일정하다는 프로젝트 조건에서 모델이 단순하고 물리 의미가 분명하다. 새 유효 관측이 올 때마다 그 관측 기준으로 다시 예측한다.
- **대안과 미채택 이유:** 시각 없는 최신 픽셀을 현재 위치로 쓰는 방식은 미채택. 온라인 속도 추정 · 긴 누락 중 무제한 예측은 초기 미도입(DEC-12).
- **한계 · 성립 조건:** 예측은 잡음을 줄여 주지 않는다. 틀린 변환 · ID · 역전된 시각을 속도 예측으로 고칠 수 없다. pose 의 stamp 는 측정 시각이 아니라 응답 수신 시각이므로 시점 오차를 보장값으로 쓰지 않는다.
- **레포 확정 사항:** `/voss/robot/pose` = TCP pose, ~50 Hz, stamp = `get_current_posx` 응답 수신 시각(호스트 시계), RTT/2 를 측정 시각으로 쓰지 않음(topics.md, MC-004); 촬영 시각 pose 보간(두 pose 사이 값을 시간 비례로 추정)은 box_tracker 책임(MC-001 · 002). 벨트 h250 = 4.8 cm/s(measurements #1, 5분 후 4.79). stamp 나이 100 ms 초과만으로 정지 · 폐기하지 않음(MC-031). `track_id` 는 1부터 증가 · 재사용 없음 · 15프레임 미검출 시 폐기, PICKING 중 현재 트랙은 보류(voss_msgs.md).
- **남은 결정 · 실측:** 실측 벨트 속도와 실제 박스 속도 차이, 관측 나이 분포 · 누락 길이. STALE_INPUT 판정 기준(position_valid=false 또는 pose 미수신 지속 시간)은 belt_servo 파라미터로 정한다(voss_msgs.md) — 값은 실측 후.
- **연결:** DEC-01 · 11 · 12 · 15. 남현지(보간), 김학민(pose stamp, #41). (IC-VISION-02 / ROBOT-02 / CONFIG, TBD-003 / 020 / 022, VT-BH-01 / 02 / 04)

### BH-DEC-04 — 피드포워드+P와 전체 PID 제어
- **상태:** 채택 → 레포 확정(입력 값). 방향 표현도 #64 머지(`6302204`)로 확정.
- **문제:** 일정하게 움직이는 박스를 따라가며 시작 오차 · 외란 · 관측 오차를 줄여야 한다. 벨트 운동까지 오차 보정에 맡기면 늘 뒤처진다.
- **선택과 이유:** 속도 명령 = 피드포워드(FF = "벨트가 이만큼 움직일 걸 아니까 미리 그만큼 따라가는 몫") + P(= "남은 오차에 비례해 더 밀어 주는 몫", v = v_belt + Kp × e). 두 항의 역할이 분명하고 초기 튜닝 요소가 Kp 와 한계값뿐이다.
- **대안과 미채택 이유:** I 항(오차 누적 보정)은 포화 · 시야 상실 · 단계 전환에서 누적 초기화와 anti-windup 이 필요하고, D 항(오차 변화율 보정)은 영상 잡음과 불규칙한 dt 를 증폭한다. 필요하다는 실측 근거가 없어 전체 PID 는 초기 미도입(영구 배제 아님). FF 만 쓰면 관측 오차가 안 줄고, P 만 쓰면 주 이동도 오차에 의존한다.
- **한계 · 성립 조건:** FF 속도 불일치 · 지연 · 포화로 잔여 오차나 진동이 남을 수 있다. 캘리브레이션 · 오프셋 오류는 I 로 덮지 말고 먼저 고친다. Kp 가 크면 지연 · 잡음에 민감하고 작으면 느리다.
- **레포 확정 사항:** FF 입력 = voss_config `belt.speed_cmps 4.8` + 방향. 방향 = `belt.direction_base: [0.99992, −0.01292, 0.0]`(베이스 기준 진행 단위벡터, +x 에서 −0.74°, z = 0 수평 성분만, measurements #6). #64(작성 남현지, 리뷰 김학민·박병후) 머지 `6302204`. 소비 노드는 기동 때 크기 1 ± 0.01 검사. 아직 이 키를 쓰는 코드는 없다.
- **남은 결정 · 실측:** Kp · 속도 한계 · `timing.latency_offset_ms`(현재 0) 는 실기 튜닝. 추종 오차 · 목표/실제 속도 · 포화 · dt 를 기록해 조정한다.
- **연결:** DEC-02 · 03 · 10 · 12 · 16 · 17. 남현지·김학민(#64, #40). 내 이슈 T27 #36. (SYS-FR-008, IC-CONFIG / ROBOT-01, TBD-019 / 020 / 021, VT-BH-01 / 02 / 04)

### BH-DEC-05 — 국소 FSM·단계 전환·인계
- **상태:** 채택 → 레포 확정(phase 이름 · 인계 의미). 전환 조건 값은 미정.
- **문제:** 영상에서 가까워졌다는 것만으로 하강 · 파지를 시작할 수 없다. 닫힘 시간 · 시야 가림 · 남은 접근 거리 · 보유 상태가 단계마다 다르다.
- **선택과 이유:** sort_manager 의 전체 상태기계와 별도로 belt_servo 안에 픽업 전용 상태기계(FSM = 상태와 전이 조건을 명시한 작은 기계)를 둔다. servo 가 빠른 관측 · 목표 · 전환을 가까이서 판단하고 manager 는 분류 · 적재 · 기록 순서만 관리한다.
- **대안과 미채택 이유:** 시간만의 시퀀스(딜레이로 단계 진행)는 미채택. 모든 로직을 manager 에 두는 안, FSM 라이브러리 · Behavior Tree 도입은 초기 미도입.
- **한계 · 성립 조건:** 상대 속도 · 오차 잡음 · 가림 중 예측 한계가 있다. 전환 값과 각 단계의 중단 · 재개가 미정이므로 완주를 이미 입증했다고 하지 않는다.
- **레포 확정 사항:** feedback `phase` = PREPARE | TRACK | DESCEND | GRASP | LIFT | VERIFY, `err_u` · `err_v` 는 px(제어용 m 오차와 섞지 않음)(TrackAndGrasp.action). `grasped` = 물체 확보 후 안전 높이까지 LIFT · VERIFY 완료, 닫힘만으로는 false(MC-005). PREPARE 사전 개방 · GRASP 닫기 · VERIFY 확인은 belt_servo 가 gripper 를 부른다(topics.md).
- **남은 결정 · 실측:** TRACK→DESCEND 조건(오차 · 유지 시간), DESCEND 속도 · 높이, LIFT 안전 높이(measurements #6 의 홈 복귀 TCP z 200 은 복귀용이라 LIFT 값으로 쓸지 확인 필요), 단계별 timeout.
- **연결:** DEC-06 · 07 · 17. 남현지 sort_manager(#29). 내 이슈 T26 #35 · T27 #36. (IC-PICK-01 / ROBOT-03, TBD-015 / 017 / 019, VT-BH-01 / 02 / 03)

### BH-DEC-06 — 실제 파지 성공 피드백과 폭 기반 대안
- **상태:** 유보 → 조건부(판정 규칙은 레포 확정, srv 필드는 미정).
- **문제:** 접수 성공 · 명령 실행 · 닫힘 완료 · 물체 확보 · 적재 완료는 다르다. Gripper.srv 의 `ok` 와 `width_actual` 만으로는 확보 여부를 알 수 없다.
- **선택과 이유:** RG2 의 직접 확보 신호(grip_detected)를 주 판정, 보고 폭 범위를 보조 판정으로 쓴다(measurements #8 판정 문구와 일치). `ok` 를 `grasped` 로 복사하지 않는다.
- **대안과 미채택 이유:** 폭만으로 판정하는 안은 빈손 38.7 mm 와 쥔 폭 40.1~40.3 mm 차이가 약 1.4 mm(40.1 − 38.7)뿐이라 단독으로는 위험. 힘 · 시간 기반 판정은 미측정.
- **한계 · 성립 조건:** grip_detected 도 물체 없는 닫힘 · 지연 · 오류를 구분해야 한다. 폭만으로 미끄러짐(slip)을 완전히 검출할 수 없다. 응답을 기다리느라 추종 타이머나 정지 경로가 막히면 안 된다.
- **레포 확정 사항:** Gripper.srv 응답 = `bool ok`, `float32 width_actual` 뿐(src/voss_msgs/srv/Gripper.srv); GRASP→LIFT 전환 = 유효 통신의 닫힘 완료 응답 + `grip_detected` + 검증된 보고폭 범위, 값은 T34 후 확정(voss_msgs.md) — `grip_detected` 는 srv 에 **아직 없음**. measurements #8: 14 N, 31 mm 면, 쥔 폭 40.1~40.3 mm, 빈손 38.7 mm(RG2 보고값, 실제 ≈ 보고 − 10 mm); voss_config gripper: pre_open_mm 90, grasp_width_mm 39, force_n 14.0. 이전 attempt 의 늦은 응답은 goal/attempt 별 future(비동기 결과 자리)로 버린다(MC-012 · 013). `grasped=false` 는 빈손이 아니므로 자동 개방 금지.
- **남은 결정 · 실측:** `grip_detected` 를 Gripper.srv 응답에 넣을지 김학민 확인 → docs/interfaces PR(interface 라벨). 폭 범위(measurements #8 제안 39.5~41.5)는 T34 낙하 시험 후. 파지 면은 31 mm 로 결정됐으므로(pending #16, 10/07) 재측정 불필요.
- **연결:** DEC-05 · 07 · 14 · 17. 김학민 RG2(T34, ADR-0005). 내 이슈 T27 #36. (SYS-FR-010, IC-ROBOT-03 / DEVICE-01 / PICK-01, TBD-015 / 019, NEW-B-03, VT-BH-02)

### BH-DEC-07 — action·전체 상태와 실제 취소/중단
- **상태:** 채택 → 레포 확정. **r4 정정**: r4 의 `STOP_UNCONFIRMED` 는 #53 최소안(박병후)으로 삭제됐다.
- **문제:** 픽업은 오래 걸리므로 대상 · 진행 · 결과 · 취소가 필요하다. action 취소 접수와 실제 장비 정지는 다르고, 박스 보유 중 복구도 관리해야 한다.
- **선택과 이유:** action(= 오래 걸리는 작업을 시작 · 진행 · 결과 · 취소까지 주고받는 통신)으로 픽업 수명을 관리한다. sort_manager 가 client, belt_servo 가 server, gateway 가 실행 · 정지. 정지 요청이 실패하면 별도 상태를 만들지 않고 **DEVICE_ERROR 로 끝내고 사람이 확인**한다 — 상태 수가 적어 G0 에서 구현 · 시험이 쉽다.
- **대안과 미채택 이유:** r4 의 `STOP_UNCONFIRMED` 오류 표시 + 새 goal 금지(자동 정지 판별)는 #53 에서 **미채택**. topic 만의 start/stop 표시나 service 응답으로 픽업 전체를 대체하는 안도 미채택.
- **한계 · 성립 조건:** action 종료 상태와 장비 안전 상태는 다르다. DEVICE_ERROR 후 로봇이 실제로 멈췄는지는 사람이 본다. 파지 후 자동 개방 · 자동 재개는 금지.
- **레포 확정 사항:** reason ↔ status: `OK`(SUCCEEDED, grasped=true) · `GRASP_FAILED`(ABORTED, 3회 모두 실패) · `LOST`(ABORTED) · `OUT_OF_REACH`(ABORTED, 748 mm 끝, measurements #6) · `STALE_INPUT`(ABORTED) · `DEVICE_ERROR`(ABORTED, gripper · gateway 서비스 실패, **정지 요청 응답 없음/오류 포함**) · `CANCELED`(CANCELED, 정지 정상 완료)(voss_msgs.md). 정지 요청 실패 = ABORTED + DEVICE_ERROR + 로그 "정지 요청 응답 없음/오류", sort_manager 는 PAUSED, 사람이 확인 후 수동 재개(MC-006 · 014); 자동 정지 판별 없음. sort_manager 는 status 가 아니라 **reason 으로 분기**. 바쁘거나 READY 아니면 goal reject(result 없음).
- **남은 결정 · 실측:** gateway 의 정지 수단(어떤 서비스로 멈추는지)과 응답 시간(DEC-16). 단계별 cancel 시험(TRACK · DESCEND · GRASP 중 각각).
- **연결:** DEC-05 · 08 · 14 · 15 · 16. 남현지 sort_manager(#29), 김학민 gateway(#41). #53. (IC-PICK-01 / ROBOT-01 / 03, TBD-005 / 017 / 019 / 020, NEW-B-04, VT-BH-01 / 02)

### BH-DEC-08 — 재시도·폐루프 유지와 개루프 검토 조건
- **상태:** 조건부 → 레포 확정(재시도 규칙 · 게이트 처리).
- **문제:** G0 정상 1회 픽업을 먼저 잇고 B 에서 놓침을 처리한다. 실패 후 같은 박스를 다시 집을 시간 · 영역이 남는지 보고, 기술 방향 포기는 팀이 함께 정한다.
- **선택과 이유:** 한 goal 안에서 최초 + 재시도 최대 3회, 카운터는 belt_servo 단독 소유. 유효 관측 · 남은 영역 · 안전이 정상일 때만 재시도한다. 주 방향은 폐루프(A안)이고 개루프(B안)는 같은 액션 인터페이스로 바꿔 끼울 수 있게 둔다(ADR-0002).
- **대안과 미채택 이유:** 70% 미달 · 10/10 도래 · 관측 상실만으로 자동 개루프 전환하는 규칙은 미채택. manager 가 재시도 횟수를 세는 안도 미채택(servo 단독).
- **한계 · 성립 조건:** 개루프도 pose · 작업 영역 · 정지가 필요하고 실제 벨트 · 박스 속도 차이를 보정하지 못한다. 재시도가 사이클 시간과 성공률 분모에 미치는 영향은 공통 집계 규약이 필요하다.
- **레포 확정 사항:** result `attempts` = goal 안 총 시도, 최대 3, servo 단독 카운터(TrackAndGrasp.action). goal 1개당 result 1건. 게이트 10/10: 20회 중 14회 점검 유지, 미달이어도 자동 전환 없음 — 게이트 회의에서 ① B안 ② 범위 축소(벨트 감속 · 여유 확대) ③ A안 10/12 연장 중 결정, 결정자 전원, 기록 PL(ADR-0002, plan.md, pending #3). 1차 측정은 10/08 저녁(plan.md 병목 주의).
- **남은 결정 · 실측:** 재시도 가능 조건(남은 구간 · 시간)의 수치. 게이트 로그 형식(DEC-11). "폐루프 성능이 상당히 부족하다"의 근거 · 시점 · 개선 시도 기록.
- **연결:** DEC-07 · 11 · 16. 남현지 PL, 전원(#13 게이트). 내 이슈 T27 #36 · T28 #37. (SYS-FR-011 / PF-001, TBD-019 / 021 / 022, NEW-B-05, VT-BH-04)

### BH-DEC-09 — OCR 독립 실행·2차 OCR 가능성
- **상태:** 일부 채택 → 레포 확정(연동 방식 수정). 구조상 가능 여부 B 단계 판단은 유지.
- **문제:** OCR 은 추종보다 오래 걸릴 수 있고 손목 카메라의 거리 · 가림 · 초점이 변한다. 추종 수렴 상태만으로 선명한 프레임이 보장되지 않는다.
- **선택과 이유:** OCR 과 servo 를 독립 실행한다. 2단계(추종 중) 프레임 선택은 비전이 영상 품질로만 하므로 **belt_servo 가 수렴 신호를 보낼 필요가 없다**. 추종 타이머가 OCR 을 기다리지 않는다.
- **대안과 미채택 이유:** r4 의 "servo 수렴 신호를 ID · stage · 촬영 시각과 함께 비차단 전달" 후보는 MC-007 로 **불필요해짐**. 정적 재판독은 3단계(`/voss/vision/read_label`, RECHECK)로 이미 별도 계약이 있다.
- **한계 · 성립 조건:** 추종 중 OCR 이 구조상 가능한지(시야 · 거리 · 가림 · 선명도 · 동시 부하)는 B 단계에서 남현지와 판단한다. 불가하면 요구사항 변경을 공동 조정한다.
- **레포 확정 사항:** 2단계 프레임은 PICKING 동안 액션 result 가 올 때까지 영상 품질(선명도 · 가림 · 송장 크기)로만 고르고 phase 문자열에 의존하지 않음(MC-007). `LabelCrop.stage` 는 box_tracker 가 `SortState.track_id` 와 같은 트랙만 PICKING→2 · RECHECK→3 으로 정함(voss_msgs.md). `LabelRead.stamp ≥ 단계 시작` 인 결과만 sort_manager 가 채택.
- **남은 결정 · 실측:** 추종 · 하강 중 송장이 읽히는 프레임이 실제로 나오는지(10/08~ box_tracker 연동 후). T28 #37 의 "2단계 OCR 연동"은 수렴 신호가 아니라 **servo 가 OCR 을 방해하지 않는지 확인**으로 범위를 다시 적는다.
- **연결:** DEC-05 · 11. 남현지 label_reader · box_tracker. 내 이슈 T28 #37. (SYS-FR-023 / VT-023, IC-VISION-03 / 04, TBD-003 / 004 / 019, NEW-B-06)

### BH-DEC-10 — 설정·버전·기동 준비
- **상태:** 채택 → 규칙 확정(#64 머지 `6302204`) / belt_servo 파라미터 구현 대기.
- **문제:** 노드마다 다른 속도 · frame · 오프셋 · 한계를 쓰거나 placeholder(자리만 채운 값)를 실제 값으로 쓰면 잘못된 움직임이 난다.
- **선택과 이유:** 시작 전 단일 버전 설정을 읽고 준비 검사를 통과해야 goal 을 받는다. 미측정 값이면 시작 금지, 운전 중 자동 설정 변경 없음.
- **대안과 미채택 이유:** belt_servo 가 voss_config.yaml 을 직접 읽는 안은 CLAUDE.md 규칙 5 로 **배제**. runtime 설정 토픽은 초기 미도입.
- **한계 · 성립 조건:** 설정이 있어도 정확성 · 안전을 보장하지 않는다. 늦게 뜨거나 재시작한 노드도 같은 version 을 써야 한다. 내부 Kp 같은 튜닝값은 설정 계약과 구분한다.
- **레포 확정 사항:** voss_config.yaml 을 읽는 노드는 sort_manager 뿐(CLAUDE.md 규칙 5, voss_config.md). belt_servo 가 belt · gripper · timing 값을 받는 경로는 #64 값 규칙으로 정해졌다(머지 `6302204`): 정적 값은 voss_bringup launch 가 파라미터로 넘기고(구현 김학민), null(미측정) 키는 넘기지 않으며 노드는 값이 안 온 파라미터를 미측정으로 보고 READY 를 거부한다. 각 노드는 `config_version`·`config_sha256` 를 로그에 남긴다. 키에 단위 접미사. sort_manager 의 SERVO 준비 판단은 `SortState.ready / not_ready`(voss_msgs.md).
- **남은 결정 · 실측:** belt_servo 가 launch 파라미터로 받을 키 목록(belt.*, gripper.*, timing.*, 파지 높이 19 mm)과 READY 조건을 src/voss_servo/launch · config 에 반영. SERVO not_ready 를 어떻게 알릴지(RobotState 처럼 상태 토픽이 필요한지) 남현지와 확인 필요.
- **연결:** DEC-04 · 06 · 16 · 17. 김학민(#64 bringup 구현), 남현지(sort_manager 준비 판단). (IC-CONFIG-01, TBD-006 / 018 / 019 / 020, VT-BH-01 / 02)

### BH-DEC-11 — 기본 전체 흐름·모의/실기·측정과 증거
- **상태:** 채택 → 레포 확정(로그 형식 · 보관 위치).
- **문제:** 기능 연결과 성능 수락을 구분하고 실패 원인을 재현해야 한다. 완료 · 분모가 다르면 성과를 잘못 집계한다.
- **선택과 이유:** 단계별 논리 시험(개인 PC: 순수 함수 pytest, fake_box · fake_pose) → 실기(공용 PC) → G0 → B 순서. 원본 로그 · ID · 설정 version 으로 계약 · 제어 · 장비 문제를 분리한다.
- **대안과 미채택 이유:** mock 통과로 G0 완료 처리, publish 타이머를 실제 30 Hz 로 간주하는 방식은 미채택. 목표 수치를 실측처럼 기록하지 않는다.
- **한계 · 성립 조건:** 70%(14/20) · 30 Hz · 100 ms 관측 나이 · 30초 사이클은 목표이며 pending #4 승인 전 "제안값"이다. 개인 PC 는 로봇 · 카메라가 없고 공용 PC DDS 가 lo 전용이라 토픽이 안 보인다(measurements #5).
- **레포 확정 사항:** 게이트 로그 = 시도 번호 · 벨트 속도 · 결과 · 실패 원인(ADR-0002). 시도별 로그는 `data/`, 집계만 ADR-0002(src/voss_servo/CLAUDE.md). 실측값은 measurements-1006.md 에만 적고 voss_config 는 그것을 참조(measurements 머리말). 실로봇 명령은 사람이 비상정지 옆에서 실행(CLAUDE.md 규칙 6).
- **남은 결정 · 실측:** §7 최소 로그 항목을 belt_servo 로그 포맷으로 확정. `data/` 의 .gitignore 처리와 파일 이름 규칙 확인 필요.
- **연결:** DEC-08 · 12 · 13 · 18. 전원(#13 게이트), 남현지 PL. 내 이슈 T27 #36 · T29 #38. (B-04 / 05, TBD-022 / 025, VT-BH-01~04)

### BH-DEC-12 — 일정 속도 예측과 칼만 필터
- **상태:** 유보(초기 미도입) → 유보. 레포 변화 없음.
- **문제:** 관측 잡음 · 속도 변동 · 누락의 영향이 아직 실측으로 분리되지 않았다. 기본 1박스 연결이 우선이다.
- **선택과 이유:** 실측 벨트 속도의 일정 속도 예측(DEC-03)만 쓴다. 추가 추정 상태와 튜닝 요소를 넣기 전에 잡음 · 속도 오차 증거를 확보한다.
- **대안과 미채택 이유:** 칼만 필터(= 모델 예측과 관측을 각각의 불확실성 크기에 따라 섞어 주는 추정기)는 Q(모델 변동) · R(관측 잡음) · 초기 공분산 · 초기화 규칙이 필요한데 근거 실측이 없어 초기 미도입(영구 배제 아님). 단순 평활 · 온라인 속도 추정도 아직 채택 없음.
- **한계 · 성립 조건:** 현재 예측은 잡음을 줄이지 못하고 벨트 · 박스 속도 차이만큼 오차가 난다. 칼만도 틀린 캘리브레이션 · ID · stamp 를 고치지 못하고 과하게 평활하면 반응이 느려진다.
- **레포 확정 사항:** 추정기 관련 계약 · 수치는 레포에 없다(변화 없음). 입력 쪽 규칙은 DEC-03 의 MC-004 · 031 그대로.
- **남은 결정 · 실측:** 정지 · 이동 중 관측 흔들림, 실제 속도 차이, 목표 속도 요동 · 누락이 문제가 되면 좌표 · 시각부터 확인한 뒤 칼만 후보를 같은 기록으로 비교.
- **연결:** DEC-03 · 04 · 11 · 15. 병후 · 남현지 · 김학민. 추정기 변경과 제어기 변경은 별개. (IC-VISION-02 / ROBOT-02 / CONFIG, TBD-020 / 022, VT-BH-01 / 02 / 04)

### BH-DEC-13 — Python·ROS 2 Jazzy·rclpy·NumPy·명시적 FSM
- **상태:** 채택 → 레포 확정(골격). NumPy 의존은 확인 필요.
- **문제:** 팀의 ROS 2 Jazzy · 두산 드라이버와 기존 ament_python 골격 위에서 제어 수식 · 입력 · 단계를 짧은 기간에 개발 · 시험해야 한다.
- **선택과 이유:** rclpy(ROS 2 파이썬 API) + NumPy(벡터 · 행렬 계산) + 명시적 Python 상태기계. 팀 환경과 맞고 수식 · 단계 변경을 검증하기 쉽다. 코드는 작은 함수 + 줄마다 한국어 주석(초급 개발자 기준).
- **대안과 미채택 이유:** C++ · 실시간 실행, FSM 라이브러리 · Behavior Tree · MoveIt Servo · MPC 는 성능 · 기능 증거가 없어 초기 미도입. 모든 스칼라 계산에 NumPy 가 필수라는 뜻은 아니다.
- **한계 · 성립 조건:** Python · 호스트 실행만으로 30 Hz 나 실시간을 보장하지 않는다. 콜백 대기 · GC · 계산 시간은 측정 대상이다.
- **레포 확정 사항:** src/voss_servo 는 ament_python, belt_servo.py 는 노드 골격만(로그 "skeleton"), test/test_smoke.py 존재. package.xml 의존 = rclpy · voss_msgs(+ pytest). **NumPy 는 package.xml 에 미선언** → 쓰려면 `python3-numpy` 추가 필요(확인 필요).
- **남은 결정 · 실측:** NumPy 의존 추가 여부(순수 함수는 math 로 충분할 수 있음). 30 Hz 타이머의 실제 주기 · 지터 측정(공용 PC).
- **연결:** DEC-05 · 14 · 18. 병후. (voss_servo/package.xml, belt_servo.py, SYS-PF-006 / 007, VT-BH-01 / 04)

### BH-DEC-14 — topic·service·action과 비동기·장비 접근 집중
- **상태:** 채택 → 레포 확정(원칙). executor · callback group 은 미정.
- **문제:** 빠른 추종 계산과 그리퍼 · OCR · 전체 업무의 다른 시간 규모를 함께 처리하고, 여러 노드의 동시 두산 호출을 막아야 한다.
- **선택과 이유:** topic = 연속 관측 · 목표, service = 단발 요청 · 응답, action = 작업 goal · 진행 · 결과 · 취소. 구독으로 최신값 보관 → 타이머에서 계산 · 전이 → 비동기 요청 → 나중에 완료 처리. 모든 두산 호출 · 제한 · 정지는 gateway 에 모은다.
- **대안과 미채택 이유:** 타이머 안에서 서비스 · OCR 완료를 동기로 기다리는 구조, 각 노드가 직접 장비를 부르는 구성은 미채택. MultiThreadedExecutor 가 필수라는 선택도 아직 없다.
- **한계 · 성립 조건:** 비동기 API 만으로 정지 우선 처리나 큐 점유가 저절로 풀리지 않는다. 실제 pose 조회 · 스트리밍 · RG2 병행 시 지연을 확인해야 한다.
- **레포 확정 사항:** goal 실행 중 `/voss/robot/gripper` 는 belt_servo 만 호출(PREPARE 사전 개방 · GRASP 닫기 · VERIFY 확인), 놓을 때 개방은 MoveToZone(PLACE). 응답 시점 = RG2 동작 완료 또는 timeout, 비동기 호출이라 닫히는 동안 추종 계속(topics.md); RG2 개폐 약 1.2 s(measurements #4). 두산 서비스는 robot_gateway 단일 호출 큐만(CLAUDE.md 규칙 3). RG2 는 gateway 안에서 Modbus TCP 직접(ADR-0005).
- **남은 결정 · 실측:** callback group · executor 선택, gripper 대기 중 cmd 갱신 · 정지 처리 지연 측정. 가림 1.2 s 동안 추종 입력 처리(DEC-03 의 PICKING 중 트랙 보류와 맞물림).
- **연결:** DEC-06 · 07 · 13 · 15 · 16. 김학민 gateway(#41). (IC-PICK / ROBOT / DEVICE, TBD-014 / 015 / 017 / 019 / 020, VT-BH-01 / 02 / 04)

### BH-DEC-15 — 최신 유효값·QoS·timestamp·ID 계약
- **상태:** 채택(후보) → 레포 확정.
- **문제:** 빠른 제어에 과거 관측 · 목표가 밀려 처리되면 지금 오차와 다른 명령을 실행한다. 다른 박스 · 단위 · frame · 시각을 잘못 결합해도 오류가 난다.
- **선택과 이유:** 고속 토픽은 QoS best_effort · depth 1(= "늦은 값은 버리고 최신 하나만"). 추종은 현재 상태만 반영하고 과거 속도 목표를 순서대로 재실행하지 않는다. 유실은 나이 · 연속성으로 감시한다.
- **대안과 미채택 이유:** best_effort 를 모든 토픽 · action · 정지에 일괄 적용하는 안, 기록성 이벤트를 최신 하나로 덮는 안은 미채택. 느린 이벤트(state · result · label)는 reliable · depth 10.
- **한계 · 성립 조건:** depth 1 만으로 stale · frame · 시계 오류가 해결되지 않고, 최신이라도 invalid 면 거부한다. QoS 가 양쪽에서 다르면 연결이 안 된다.
- **레포 확정 사항:** `/voss/vision/box`, `/voss/robot/pose`, `/voss/robot/servo_cmd` = best_effort · volatile · depth 1(topics.md QoS 표, pending #1 수용). label_crop 은 reliable · depth 5, zone_map 은 transient_local(늦게 뜬 구독자도 마지막 값을 받음). 미검출 프레임에는 BoxTrack 을 발행하지 않음, `position_valid=false` 는 검출됐지만 좌표를 못 믿을 때만(voss_msgs.md).
- **남은 결정 · 실측:** 실제 drop · 순서 역전 · 재접속 시험(공용 PC). STALE_INPUT 기준 시간(DEC-03).
- **연결:** DEC-01 · 03 · 07 · 11 · 14. 전원. (SYS-IF-008, IC-VISION / ROBOT / PICK, TBD-003 / 014 / 019 / 020, VT-BH-01 / 04)

### BH-DEC-16 — 속도·가속·영역 제한과 독립 watchdog
- **상태:** 채택(원칙) → 미정(수치 · 정지 수단). 김학민에게 이슈로 요청할 항목.
- **문제:** 오류 · 지연 · 소실로 계산값이 급변하거나 마지막 속도 명령이 남을 수 있다. servo 프로세스가 죽어도 장비 쪽에서 멈춰야 한다.
- **선택과 이유:** 두 층 — belt_servo 의 입력 검사 · 목표 clamp(한계값으로 자르기)와 gateway 의 최종 한계 · watchdog(= 일정 시간 새 명령이 없으면 스스로 멈추는 감시 타이머). 속도 0 을 한 번 발행하는 것과 실제 정지 확인은 다르다.
- **대안과 미채택 이유:** 소실 시 마지막 명령 무기한 유지, 무제한 예측, 재접속 자동 재개는 미채택. 자동 개루프 전환도 미채택(DEC-08).
- **한계 · 성립 조건:** watchdog 이 있어도 실제 정지 · 보유 박스 안전을 보장하지 않는다. 비상정지(하드웨어)와 소프트웨어 정지("멈춰", SR-NF-09)는 역할이 다르다.
- **레포 확정 사항:** 속도 한계 · 작업 영역은 robot_gateway 가 강제하지만 belt_servo 도 clamp(src/voss_servo/CLAUDE.md). 추종 가능 구간 748 mm(TCP x −107 → 638, measurements #6) → OUT_OF_REACH 근거. topics.md 에는 watchdog · cmd 유효기간 · stop 수단 **명세 없음**; voss_msgs.md 가 "robot_gateway 의 servo_cmd 만료 워치독(값은 실측 후)"만 언급. `/voss/robot/state`(RobotState)는 김학민 10/07 정의 예정.
- **남은 결정 · 실측:** 김학민에게 이슈로 요청: ① servo_cmd 만료 시간 ② gateway 정지 수단과 응답 ③ RobotState 필드. 나는 clamp 값(속도 · 가속 · XY 영역 · Z 하한)을 파라미터로 두고 실측 후 채운다.
- **연결:** DEC-02 · 04 · 06 · 07 · 10. 김학민 gateway(#41, RobotState). (SYS-SF-001 / 002, IC-ROBOT / DEVICE / CONFIG, TBD-017 / 020, VT-BH-02 / 04)

### BH-DEC-17 — XY 추종·Z 단계 계획·고정 자세·RGB 높이 가정
- **상태:** 채택 → 레포 확정(파지 면 pending #16 결정 10/07, 고정 자세 MC-010).
- **문제:** 첫 단일 박스 픽업에서 회전 · 높이 · 복잡한 경로를 동시에 풀 필요가 있는지 분리한다. 카메라 검출 기준점과 TCP · 파지점은 다르다.
- **선택과 이유:** XY 는 FF+P 추종, Z 는 단계별 높이 · 속도 제한, 자세는 고정(각속도 0). 박스 윗면 중심(관측) → TCP 목표 = 관측 + 파지 높이 오프셋. 실측 관측 평면과 일정한 박스 조건을 활용해 기본 추종 · 타이밍을 먼저 검증한다.
- **대안과 미채택 이유:** 깊이 영상(CLAUDE.md 규칙 4 로 배제), 완전 6D 자세 추정, 새 경로 프레임워크는 초기 미도입. 박스 회전 추종은 G0 에서 제외.
- **한계 · 성립 조건:** 벨트면 · 박스 높이 · 카메라 장착 · TCP 설정이 틀리면 가정이 무너진다. 하강은 픽셀 스케일과 가림을 바꾸고, LIFT 중 벨트 분리 시점도 확인해야 한다. 벨트 윗면은 745 mm 동안 2.4 mm 기울기(measurements #6).
- **레포 확정 사항:** 박스 46 × 31 × 27 mm(BRD); BRD **v1.3**(#79 머지 `671c67f`) TR-PICK-06 = 박스의 31 mm 폭을 잡는다(핑거가 46 × 27 mm 긴 옆면, 닫힘축 벨트 가로), 사전 개방 90 mm. v1.2 의 "46 mm 면" 은 정정됐다. 10/06 실측은 **31 mm 면**(46 mm 변 = 벨트 방향, measurements #8). pending #16 **결정(10/07, #70)**: 31 mm 면 파지. 사전 개방 여유(실제 약 ±24.5 mm)는 벨트 가로 방향이라 벨트 방향 타이밍 여유는 추종(피드포워드 · 서보)이 맡는다. 값: 목표 폭 39 mm(보고값) · 14 N, 파지 높이 TCP z = position_base.z − 19 mm. 남은 일: ADR(김학민). G0 는 고정 파지 자세 · 각속도 0(MC-010); 구역 놓기는 그리퍼 방향 −90°(measurements #6 트레이).
- **남은 결정 · 실측:** 벨트 방향 여유가 없으므로(닫힘축이 벨트를 가로지름) 추종 오차 허용치가 그대로 파지 성공률을 정한다 — 실측으로 허용 오차를 잡는다. 핑거 끝이 박스 밑면 +8 mm 인 상태에서 벨트 기울기 2.4 mm 가 문제인지 실측.
- **연결:** DEC-01 · 04 · 05 · 06. 김학민 · 박병후 · PL(pending #16). (SYS-FR-007~010, IC-VISION / ROBOT / CONFIG, TBD-002 / 015 / 019, VT-BH-02 / 03)

### BH-DEC-18 — host 실행·실행 구조·자원 분리
- **상태:** 채택 → 레포 확정(방향). 부하 성능은 미확인.
- **문제:** 비전 · OCR · 음성 · DB 와 servo 가 공용 PC 자원을 공유하므로 지연 · 주기가 영향받는다. 배포 선택과 실시간 동작은 구분해야 한다.
- **선택과 이유:** belt_servo · robot_gateway 는 호스트, 비전은 GPU 컨테이너(`--network host`, 같은 ROS_DOMAIN_ID). 서보 루프 지연을 컨테이너와 분리한다는 팀 배포안을 그대로 따른다.
- **대안과 미채택 이유:** 전체 배포 재설계, C++ 전환, 멀티스레드 · RT 경로는 실측 근거 없이 채택하지 않는다. 컨테이너 유무만으로 지연 우열을 단정하지 않는다.
- **한계 · 성립 조건:** 호스트 · Python 이라도 30 Hz 보장이 없다. 공용 PC 의 CycloneDDS 가 lo 전용이라 개인 PC 에서 토픽이 안 보인다(김학민 wlo1 추가 전까지).
- **레포 확정 사항:** 배포 구성 표(architecture.md): 호스트 = 두산 브링업 · robot_gateway · belt_servo(30 Hz) · sort_manager · 음성 3노드 · hmi_bridge · sort_logger · Mosquitto, 비전 컨테이너 = box_tracker · label_reader. 공용 PC = i7-13620H · 32 GB · RTX 4060 8 GB · ROS_DOMAIN_ID 30 · DDS lo 전용(measurements #5). 개인 PC 도메인 34.
- **남은 결정 · 실측:** 단독 · 동시 부하에서 타이머 주기 · 콜백 대기 · CPU 사용 계측(공용 PC). DDS 인터페이스 변경은 김학민 결정.
- **연결:** DEC-10 · 11 · 13 · 14. 전원, 김학민(환경). (TBD-018 / 020 / 026, IC-CONFIG / DEVICE, VT-BH-04)

## 6. 결정 간 관계

```text
남현지 BoxTrack.position_base · stamp · position_valid (DEC-01·15)
  → 시각·ID 검사, 일정 속도 예측 (DEC-03·12) → TCP 목표·오차 (DEC-01·17)
  → FF+P 속도 명령 + 픽업 단계 FSM (DEC-04·05) → clamp (DEC-16)
  → servo_cmd TwistStamped → 김학민 gateway → 두산 (DEC-02) / RG2 (DEC-06·14)
  ← /voss/robot/pose · Gripper 응답 · RobotState(예정) · 정지 결과 (DEC-03·06·16)
sort_manager ↔ belt_servo action: goal(track_id) · feedback(phase) · result(grasped·reason·attempts) (DEC-07·08)
OCR 은 독립 (DEC-09) · 설정은 launch 파라미터 예정 (DEC-10) · 증거는 data/ + ADR (DEC-11)
```

- 칼만은 **추정기** 변경, PI / PD / PID 는 **제어 계산** 변경, servol / move_line 은 **장비 명령 경로** 변경이다. 하나를 바꿔도 다른 것이 자동으로 채택 · 폐기되지 않는다.
- 좌표 변환 · 기준점 · 시각 · 단위 오류를 먼저 고치고, 추정기 · 제어기 고도화로 체계적 오류를 숨기지 않는다.
- 필드 · 타입 · QoS · 단위 · 의미가 바뀌면 docs/interfaces 를 코드보다 먼저 고치고 `interface` 라벨 PR (CLAUDE.md 규칙 2).
- 내부 gain · 클래스 · 필터 수식(이 문서)과 외부 계약(docs/interfaces)을 구분한다.

## 7. 실측 · 고도화 순서

| 단계 | 목적 · 할 일 | 결과로 남길 것 | 환경 |
|---|---|---|---|
| 계약 · 기초 확인 | servol_stream 유무 · 주기(measurements #3) → pending #8, grip_detected 유무 | measurements · pending · ADR 갱신 | 공용 PC (T25 #34) |
| 논리 시험 | 오차 → 속도 · clamp · 상태 전이 순수 함수 + pytest, fake_box · fake_pose 로 액션 서버 | 테스트 통과, 로그 포맷 | 개인 PC |
| 고정 자세 · 높이 추종 | 벨트 축부터 FF+P, 횡 오차 보정, Kp · 한계 · 나이 계측 | 관측 / 목표 / 실제 · 오차 · 주기 · 지연 | 공용 PC + 로봇 (T26 #35) |
| 단일 픽업 | 하강 · 닫힘 · LIFT, 가림 · timeout · 확보, 단계별 중단 | 전환 · 높이 · 시간 · 폭 · 힘 원본 | 현장 (T26 · T27) |
| 게이트 측정 | 20회 시도, 1차 10/08 저녁, 본 측정 10/10 | `data/` 시도 로그, ADR-0002 집계 | 현장 (T27 #36, #13) |
| B 후속 | 재시도 · 실패 감지 · OCR 비간섭 확인 · 성능 집계 | 사례 · 분모 · 성공률 · 지터 | 현장 (T28 #37) |
| 문제별 고도화 | 위치 · 속도 잡음 → 추정기, 지속 · 과도 오차 → 제어기, 명령 병목 → 경로 · 실행 구조 | 같은 조건 비교 · 채택 근거 | 필요 시 |
| 튜닝 · 리허설 | latency_offset_ms · 타이밍 | 리허설 통과 | 현장 (T29 #38) |

최소 로그 항목: box_id / track_id / goal / attempt · 촬영 stamp / pose stamp / 계산 시각 / cmd 발행 시각 · position_base(관측) / 예측 / TCP 목표 / 오차 · 벨트 속도 / 목표 속도 / 실제 속도 · position_valid · clamp 작동 · phase · reason · Gripper 응답(ok · width_actual) · 설정 version · sha256. 예측이나 필터를 도입해도 관측 나이를 줄여 보고하지 않는다.

## 8. 일정 · 상태

- **T25 #34(servol_stream 확인 · 제어 방식 결정, 10/06 오후 예정)는 10/06 에 끝나지 않았다.** measurements #3 ☐, pending #8 미정. 10/07 중간 점검 발표가 있어 로봇 점유는 스탠드업에서 다시 잡는다.
- pending #16(파지 면)은 **10/07 결정(#70)**: 31 mm 면, 폭 39 mm · 14 N, 높이 19 mm. DEC-01 · 06 · 17 에 반영했다. 남은 일은 ADR(김학민). BRD 는 v1.3 으로 정정됨(#79).
- #64(belt.direction_base · 값 규칙)는 머지됨(`6302204`) → DEC-04 확정, DEC-10 규칙 확정(r5.1).
- 게이트 1차 측정 10/08 저녁, 본 게이트 10/10 (plan.md).

| 버전 | 변경 |
|---|---|
| r1 | 최소 권장안 · 본인 선택 전 초안 |
| r2 | 사용자 ①~⑪ 채택 / 유보 / 조건 반영 |
| r3 / 10/07 | 후속 변환 담당 · 추정기 / 스택 / ROS 근거와 고도화 계획 보완 |
| r4 / 10/07 | 칼만을 예시로 한 공통 기록 요구 반영. PID · speedl 등 18개 항목을 같은 8항목 결정 카드로 재정리 |
| r5 / 10/07 | 레포 main e8dd5e5(#63 · #65 · #57 · #70) 대조 반영, DEC-07 정정, pending #16 결정(31 mm 면) 반영, 가독성 재구성, 레포 번호 병기, src/voss_servo/DESIGN.md 로 이동 |
| r5.1 / 10/07 | #64(`6302204`)·#79(`671c67f`) 머지 반영: DEC-04 방향 단위벡터 확정, DEC-10 값 규칙 확정, DEC-17 BRD v1.3. #64 작성자 표기 정정(남현지). 결정 내용은 그대로 (김학민 리뷰) |

## 9. 미확정 경계

| 범주 | 포함한 항목 | 결정 ID | 현재 상태 |
|---|---|---|---|
| 관측 / 좌표 · 기하 | 픽셀 / 베이스, 변환 노드, TCP · 파지 높이, RGB 높이 · 자세 가정 | 01 / 17 | 계약 확정, 파지 면 31 mm · 19 mm 확정(pending #16) |
| 추정 | 시각 · ID · 일정 속도 예측, 칼만 · 온라인 속도 · 필터 | 03 / 12 | 입력 규칙 확정, 추정기 유보 |
| 제어 | FF / P / PI / PD / PID, 이득 · 포화 · 잡음 · 지연 | 04 / 16 | 구조 확정, Kp · 한계 · watchdog 미정 |
| 장비 목표 · 경로 | servol_stream / move_line ASYNC, 단위 · 시간 · 갱신 · 정지 | 02 | 출력 확정, 경로 pending #8 미정 |
| 픽업 작업 | 단계 전환 · 인계, 파지 피드백 · 폭 대안, 재시도 | 05 / 06 / 08 | phase · reason · attempts 확정, grip_detected 필드 · 전환 값 미정 |
| ROS · 실행 | topic / service / action, QoS, 비동기 · 큐, watchdog | 07 / 14 / 15 / 16 | 계약 확정, executor · watchdog 값 미정 |
| 개발 · 배포 | Python / rclpy / NumPy / FSM, host / container | 13 / 18 | 방향 확정, NumPy 의존 · 부하 성능 미확인 |
| 통합 · 설정 · 증거 | OCR 독립, 설정 공급 경로 · READY, 전체 흐름 · 로그 | 09 / 10 / 11 | OCR 연동 방식 확정, 설정 규칙 확정(#64), belt_servo 파라미터 구현 대기 |

**미확정 사항(레포에서 확인 안 됨):** servol_stream 의 실제 지원 · 주기(measurements #3), gateway 정지 수단 · cmd 유효기간 · RobotState 필드, `grip_detected` 의 srv 반영, 구체 Kp · 안전 한계 · 단계 전환 값 · timeout, NumPy 의존, 수치 목표 승인(pending #4). 이들은 확인 정보를 받아야 채울 수 있으며 문서 완성도를 위해 임의로 확정하지 않는다.

향후 수정은 문제 · 실측 근거 → 관련 결정 ID → 대안 비교 → 새 결과 · 미선택 이유 → docs/interfaces · measurements · pending · ADR 영향 → 회귀 검증 순서로 같은 양식에 남긴다.
