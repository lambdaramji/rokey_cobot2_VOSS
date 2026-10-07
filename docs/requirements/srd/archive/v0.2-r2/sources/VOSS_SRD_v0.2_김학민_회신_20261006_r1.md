# VOSS SRD v0.2 취합 회신서 — 김학민

**수신:** 김학민 · **취합:** 박병후  
**담당 범위:** 로봇 게이트웨이·그리퍼·적재·실측·실행 환경  
**대상 기능/노드 후보:** robot_gateway, 두산 브링업 및 장비 연결  
**양식 버전:** v0.2 r1(독립 재검 반영) · **기준일:** 2026-10-06(한국 시간)

> 표기: `⏳#n` = 10/06 실측 `docs/measurements-1006.md #n` 결과로 채울 칸(마감 전 반영 목표, 못 채우면 미정으로 제출). `(제안)` = 상대 확인 전 값·계약. 실측 안 된 좌표·속도·힘은 0으로 쓰지 않았습니다.

## 0. 회신 정보·공통 기준

| 항목 | 답변 |
|---|---|
| 작성자·회신일·회신 버전 | 김학민 · 2026-10-06 · r1 (실측 진행 중 초안, ⏳칸은 측정 후 갱신) |
| 확인한 코드/문서/장비 버전 | 레포 `rokey_cobot2_VOSS` main `668703e` + 브랜치 `chore/measure-1006-kit` `bc14d20`. 문서: `docs/interfaces/topics.md`·`voss_msgs.md`·`voss_config.md`(2026-10-05판, 제안 상태), `architecture.md`, `pending-decisions.md`, `measurements-1006.md`, `adr/0002`, `scripts/measure_1006/README.md`, **BRD v1.2(2026-10-06, 남현지)**. doosan-robot2: 학민 노트북 `31750d6`(ROKEY-SPARK/doosan-robot2_jazzy), onrobot-ros2: `c6e3903`(ABC-iRobotics/onrobot-ros2) — 둘 다 ~/cobot2_ws. dsr_msgs2 서비스·스트리밍 정의는 이 커밋 소스로 대조. 컨트롤러 DRCF/DRFL 버전 ⏳#2 |
| 구현됨/설계만/실측됨/미확인 범위 | **구현됨:** 10/06 실측 도구(조회 전용 pose 기록, RG2 Modbus 확인·파지력 기록, 벨트 속도 계산, 노출 스윕, 환경 보고). **설계만:** robot_gateway(패키지 골격만, 노드 코드 없음 — T32 #41, 10/06~08), srv 정의(MoveToZone·Gripper·TeachZone). **실측 중:** #1·#2·#4·#6·#8·#9. **미확인:** servol_stream 가용(박병후 #3), 정지 지연, pose 실제 주기 |
| 함께 확인한 담당자·확인 일시 | [기입] |
| 추가 검토가 필요한 상대 | 박병후(R-02 servo_cmd·pose 규약, R-03 그리퍼 호출·판정 책임), 남현지(R-04 zones·observe_pose·slot, IC-ROBOT-03 호출, config 기준점, FR-001 준비 판단), 정의석(R-06 DB·웹 실행 위치, CT-005, NEW-R-06 HMI 로봇 상태 원천) |

## 1. 담당 요구사항 검토

| 요구사항·단계 / 검증 ID | SRD 초안 문장 | 검토 답변·검증 카드 연결 |
| --- | --- | --- |
| SYS-FR-001 / A / VT-001 | 시스템은 카메라·로봇·그리퍼·설정·로그 저장 경로의 준비 여부를 확인한 뒤 기본 분류 작업의 실행 가능 여부를 표시해야 한다. | **수정제안**(CHG 카드 NEW-R-01). 카메라·설정·로그 준비까지 통합 판단하는 주체는 sort_manager. robot_gateway는 로봇·그리퍼 준비 상태만 제공. 주담당을 남현지로, 김학민은 로봇·그리퍼 준비 신호 제공으로 분리 제안 / VC-R-02(로봇·그리퍼 준비 부분), 통합 판단은 남현지 카드 |
| SYS-FR-012 / A / VT-012 | 시스템은 파지한 박스를 결정된 구역의 유효 적재 위치에 놓아야 한다. | **수용.** 유효 적재 위치 = zones 구역 기준 자세 + slot 격자 오프셋(R-04). 구역이 가득 찼을 때 처리는 미정(TBD-016·005) / VC-R-03, 미수행·10/08~10 예정(T35) |
| SYS-FR-013 / A / VT-013 | 시스템은 적재 완료 후 다음 박스를 관측할 수 있는 대기 자세로 복귀해야 한다. | **수용.** 대기 자세 = `observe_pose`(BRD TR-PICK-01: 벨트 상류 끝 위 약 15 cm에서 상류 구간 약 20 cm 촬영. 정확한 자세는 10/06 R3 캘리브레이션 때 남현지·박병후와 결정). move_to_zone 응답 = 복귀 도달 후(제안, R-04) / VC-R-03, 미수행·10/08~10 예정 |
| SYS-OP-002 / C / VT-036 | 선택 기능 채택 시 시스템은 대기 상태의 직접교시 좌표를 확인받아 새 구역으로 등록해야 한다. | **선택 — 후속 검토.** T36(10/11~13, Should). 기본 흐름(G0) 승인 후 판단 / 미수행 |
| SYS-IF-003 / A / VT-039 | 시스템의 로봇 인터페이스는 좌표·속도·그리퍼의 단위, 좌표계, 응답 의미와 오류 규약을 명시해야 한다. | **수용.** IC-R-01(pose)·IC-R-02(move_to_zone·gripper)·IC-R-03(장비) 카드로 제안. 현재 srv 응답에 오류 코드·파지 감지가 없어 보완 제안(NEW-R-02) / VC-R-02 |
| SYS-SF-001 / A / VT-053 | 시스템은 정지 명령 또는 유효 제어 입력 상실 시 승인된 안전 중단 동작을 수행해야 한다. | **수용.** gateway에서 servo_cmd 입력 감시(일정 시간 미수신 시 정지) + 정지 요청 최우선 처리(R-05). **현재 gateway에 정지 요청을 받는 인터페이스가 없음** → NEW-R-04(`/voss/robot/stop`) 제안. 감시 시간·최대 정지 지연은 미측정 / VC-R-04, 미수행·10/08 예정 |
| SYS-SF-002 / A / VT-054 | 시스템은 로봇 동작 명령에 작업 영역과 속도 제한을 적용해야 한다. | **수용.** robot_gateway에서 강제(다른 노드의 제한을 믿지 않음). BRD NFR-09의 협동로봇 속도 제한(펜던트 설정)과 이중으로 적용. 작업 영역은 #6 실측 후, 속도 상한은 T32 실기 후 확정 / VC-R-02 |
| SYS-SF-003 / A / VT-055 | 물리 비상정지는 음성·클라우드·웹 HMI의 정상 동작과 독립적으로 접근 가능해야 한다. | **수용.** 티치펜던트 비상정지가 최종 수단. 음성 "멈춰"·HMI 정지는 소프트웨어 정지이며 안전 등급이 아님. 실기 시 비상정지 앞 1인 상주(2인 1조) / VC-R-01 |
| SYS-CT-001 / A / VT-060 | 시스템은 지정된 M0609·RG2·D435i·컨베이어 장비와 ROS 2 Jazzy 환경에서 동작해야 한다. | **수용.** 버전 ⏳#2, PC 사양 #5(정의석) / VC-R-01 |
| SYS-CT-003 / A / VT-062 | 시스템의 두산 서비스 조회·명령은 robot_gateway의 단일 직렬 호출 경로를 통해 실행되어야 한다. | **수용 + 운영 조건 보완.** 실측·캘리브레이션 도구(record_pose, 남현지 캘리브레이션, servol 확인)는 robot_gateway가 꺼진 상태에서 한 번에 하나만 실행. 동시 호출 시 dsr_controller2가 응답을 멈추고 브링업 재시작으로만 복구됨(전 프로젝트 실측) / VC-R-02 |
| SYS-CT-004 / A / VT-063 | 시스템은 한 번에 박스 1개를 운영하고 분류 동작 중 컨베이어 속도·운전을 자동 제어하지 않아야 한다. | **수용.** 벨트 속도는 사람이 아두이노에서 설정. VOSS 노드와 아두이노 사이 연결 없음 / VC-R-01 |
| SYS-CT-005 / B / VT-064 | 시스템은 비전 추론과 DB를 컨테이너로 실행하고 호스트 기능과 통신할 수 있어야 한다. | **수정제안(담당)**(NEW-R-03). 비전 컨테이너=남현지(docker/vision), DB 컨테이너=정의석(docker/db)이 주담당. 김학민은 호스트 쪽 브링업·네트워크(DDS·도메인) 확인으로 공동 / 미수행·10/13 통합 시 |
| SYS-EN-002 / A / VT-069 | 작업자의 박스 투입 위치는 로봇의 관측·대기 위치와 겹치지 않아야 한다. | **수용 + 배치 주의.** BRD는 관측 자세를 "벨트 상류 끝 위"(TR-PICK-01)로, 투입 위치도 "벨트 상류 끝"(NFR-10)으로 적어 그대로 두면 겹칠 수 있음 → 투입 지점은 벨트 맨 상류 끝, 관측 자세는 그보다 하류 쪽(카메라가 상류 구간을 비스듬히 보도록)으로 분리해 #6에서 확인. #1 측정 때 투입 쪽·진행 방향을 벨트에 표시, #6-a 배치 스케치·사진으로 확인 / VC-R-01 |
| SYS-EN-003 / A / VT-070 | 장비 배치와 케이블은 승인된 로봇·그리퍼·벨트 동작 범위에서 간섭이나 케이블 당김을 발생시키지 않아야 한다. | **수용.** #6-b 좌표 교시 때 각 구역·관측·safe 자세에서 케이블 여유 확인, T35에서 재확인. BRD 6.3: 파지 시 핑거 끝이 벨트 면 약 10 mm까지 내려감 → 가이드를 쓰면 높이 15 mm 이하, 벨트 프레임과 핑거 간섭 확인 / VC-R-01(배치), VC-R-03(동작 범위) |

## 2. 질문별 회신 — 빈 항목을 채울 자료

### R-01 — 장비·버전·벨트·환경 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 실제 장비·버전 / A | M0609 컨트롤러/DRCF·doosan-robot2·RG2·D435i·벨트·아두이노·툴/TCP 버전/이름 | M0609(리치 900 mm, 가반 6 kg) + OnRobot RG2(스트로크 0~110 mm) + 손목 D435i(Eye-in-Hand, BRD 목표 RGB 1920×1080 30 fps, 깊이 미사용). DRCF/DRFL ⏳#2(전 프로젝트 값 GF02120100/GL013303과 같은지 표시 예정). doosan-robot2: 학민 노트북 `31750d6`, 브링업 PC 커밋 ⏳#2(4명 PC 일치 확인). onrobot-ros2 드라이버: 학민 노트북 `c6e3903`. 브링업 패키지 `m0609_rg2_bringup`(~/cobot2_ws). 벨트: **싸이피아 A3 탁상용 미니 컨베이어**(BRD 6.1: 외형 1090×125×85 mm, 벨트 폭 70 mm, 상부 벨트 1,040 mm, 스텝모터 + 3:1 풀리 감속, 드라이버·컨트롤러 포함, 아두이노 제어). 아두이노 보드 모델·스케치 버전: 미확인(10/06 #1 측정 때 확인). 툴/TCP: T32 등록 스크립트에서 정함(미정). **브링업을 다시 켜면 툴·TCP 등록이 풀림** → 기동 절차에 재등록 포함(R-06) |
| 연결 환경 / A | 장비 주소·포트·NIC·USB/시리얼·ROS_DOMAIN_ID·DDS | 공용 PC 유선 192.168.1.10/24 ↔ 로봇 컨트롤러 192.168.1.100:12345(로봇 전용 서브넷, BRD 6.1), RG2 Modbus TCP 192.168.1.1:502(응답 ⏳#4). 인터넷 Wi-Fi(wlo1). D435i USB 3.0. 아두이노 `/dev/ttyACM0`(dialout 필요). ROS_DOMAIN_ID 공용 30 / 개인 개발 31~34(통합·시연 때 개인 PC를 붙이면 30, BRD 6.1). RMW CycloneDDS. MQTT Mosquitto 1883(공용 PC 호스트). **조치 예정:** CycloneDDS가 lo만 써서 다른 PC에서 토픽이 안 보임 → wlo1 추가, 유선 게이트웨이(192.168.1.1) 제거. 변경은 `docs/setup/`에 기록 |
| 벨트 실측 / A | 설정값별 속도(cm/s)·3회 결과/평균·방향·≤10cm/s 가능 여부·변동 | ⏳#1(설정값별 3회 평균, 편차 ±5% 이내 판정, 5분 운전 후 드리프트). 개발 기준 속도 제안 약 5 cm/s(사전 개방 90 mm 여유 ±22 mm → 5 cm/s에서 ±0.4 s). 최종 속도는 박병후와 10/10 게이트 때 결정. BRD 6.2 가정: 리치 안 추종 구간 약 50~60 cm → 10 cm/s에서 5초 이상 추종 가능(#6-b로 실제 구간 확인) |
| 물리 배치 / A | 작업대/베이스/벨트·투입 위치·5구역·케이블 여유·가이드·조명/노출 | 배치: 로봇 왼쪽, 위 줄 역삼(A)·대치(B)·청담(C), 가운데 줄 재확인·보류, 아래 벨트. 치수·베이스 위치 ⏳#6-a. 구역 1개는 2×2 격자(pitch 60 mm) 기준 130×120 mm 이상 권장, 베이스에서 반경 약 850 mm 이내(리치 900 mm), 추종 가능 구간 ≥500 mm 확인 예정. 재확인 구역은 벨트에 가장 가깝게(BRD 2.4). 벨트 하류 끝에 **비대상 박스 회수함**(TR-PICK-09). 작업대에 신규 구역 교시용 여유 자리 표시(BRD 6.3, C 선택). 가이드는 필요할 때만, 높이 15 mm 이하(BRD 6.3). 조명·가이드 레일은 문제가 생기면 구매(BRD 6.3). 조도·노출 ⏳#9(목표 수동 노출 5~8 ms, 고정 WB — NFR-13) |
| 운영 가정 / A | 1개 투입·벨트 수동 운전·박스/송장 크기와 실제 차이 | 1개씩 투입, 벨트 수동 운전(CT-004). 박스 46×31×27 mm 종이, 핑거가 46 mm 면을 잡음(닫힘축 = 벨트 진행 방향, 송장 위). 송장 40×25 mm(박스 가장자리 사방 3 mm 여백, 글자 방향은 46 mm 변 = 벨트 진행 방향과 나란, 300 dpi 이상 무광 라벨지). 시연 박스 10개 = 역삼·대치·청담 각 3 + 흐린 송장 1(BRD 2.4). 실제 박스 치수 차이 [기입: 캘리퍼스 측정값] |

A 상태·남은 항목: `미정 — 10/06 실측 중, 16:00 전 ⏳칸 반영 목표` · B 상태·남은 항목: `해당 없음` · C 선택 상태: `해당 없음`  
근거/파일/실측: `docs/measurements-1006.md #1·#2·#6·#9`, `scripts/measure_1006/` · 미정 담당·결정 예정일: `김학민 / 10/06`

### R-02 — 로봇 인터페이스·큐·단위 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 실제 API / A | 두산 서비스/스트리밍 토픽 이름·실제 타입·가용 여부·드라이버 버전·확인 증거 | **소스 확인(doosan-robot2 `31750d6`, dsr_controller2.cpp), 실기 미확인.** 서비스: `/dsr01/dsr_controller2/motion/move_line`(dsr_msgs2/srv/MoveLine, sync_type ASYNC=1), `/dsr01/dsr_controller2/aux_control/get_current_posx`(GetCurrentPosx), `/dsr01/dsr_controller2/motion/move_stop`(MoveStop). 스트리밍 토픽(구독, 응답 없음): `/dsr01/dsr_controller2/servol_stream`(ServolStream), `/dsr01/dsr_controller2/speedl_stream`(SpeedlStream) 등. ⚠ topics.md의 `/dsr01/servol_stream`은 소스 기준 경로와 다름 → 수정 필요. 실기 가용·주기는 박병후 #3·pending #8 |
| pose/servo / A/B | pose 제공 주기·시각·frame_id, servo_cmd의 속도/좌표/단위·유효 시간·권장 주기 | IC-R-01 참조. pose: PoseStamped ~50 Hz(제안), best_effort depth 1, 단위 m·quaternion, frame_id `base_link`(제안). **50 Hz 근거는 전 프로젝트 값뿐**(BRD 6.1: 조회와 모션 명령을 한 줄로 이었을 때 약 43~50 Hz, 하루 안정). 이번 장비·스트리밍 조합에서는 미확인 — pose 조회도 같은 단일 큐를 지나 이동 명령과 경쟁함(T32에서 측정). servo_cmd(박병후 제공): TwistStamped 30 Hz, m/s·rad/s, frame `base_link` 기대. 유효 시간(감시 시간)은 R-05 |
| 단위 변환 / A | ROS Pose/Twist와 두산 posx의 m/mm·rad/deg·orientation 변환 담당 및 예시 | **robot_gateway가 전담**(제안). ROS 쪽 SI(m, rad, quaternion) ↔ 두산 posx(mm, deg, ZYZ 오일러). 예: `position.x = 0.4123 m` ↔ `posx x = 412.3 mm`. 다른 노드는 두산 단위를 보지 않음. voss_config.yaml zones는 사람이 펜던트 값과 대조하기 쉽게 posx(mm/deg) 유지 |
| 큐·동시성 / A/B | 위치 조회/이동/그리퍼/스트리밍의 큐 범위·우선순위·정지·실제 응답 시간 | 두산 서비스 호출은 큐 하나로 직렬화(제안). 우선순위: 정지 > 이동/스트리밍 > pose 조회. RG2(Modbus)는 두산 서비스가 아니므로 별도 연결이지만 소유는 gateway. 참고(전 프로젝트, BRD 6.1): `move_line` ASYNC 응답 16~94 ms(이동 완료를 기다리지 않음), `move_stop` 응답 115~124 ms. 이번 장비 실제 응답 시간 미측정 — T32 완료 기준 "move_line 큐 1시간 무정지" 시험에서 함께 측정(10/08) |
| 서비스 응답 / A | 접수와 실제 완료 구분·timeout·실패 사유·이미 이동 중 명령 처리 | IC-R-02 참조. move_to_zone·gripper 응답 = **실제 완료 후** 반환(제안, 접수 응답 없음). 실패는 `ok=false` + `message`에 사유 코드(제안: `busy`, `invalid_zone`, `pose_not_set`, `timeout`, `stopped`, `gripper_error`). 이동 중 들어온 동작 명령은 거부(`busy`). 작업 시작 시 관측 자세로 가는 명령(BRD 8.1 1단계)은 현재 srv에 없음 → NEW-R-05(`zone="observe"`). timeout 값 미정(T35 실측 사이클 시간 기준) |

A 상태·남은 항목: `미정 — 설계 제안 완료, 실제 타입·주기·응답 시간은 T32 실기(10/06~08) 후 확정` · B 상태·남은 항목: `미정 — 30 Hz 스트리밍 중 큐 지연(pending #8 결과 의존)` · C 선택 상태: `해당 없음`  
근거/파일/실측: `docs/interfaces/topics.md`, `src/voss_robot/CLAUDE.md` · 미정 담당·결정 예정일: `김학민·박병후 / 10/08`

### R-03 — 그리퍼 경로·값·피드백 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 제어 경로 / A | Modbus/드라이버/두산 경유의 선택·주소/타입·호출 주체·실측 여부 | **제안: Modbus TCP 직접(robot_gateway 안)**, 192.168.1.1:502. 이유: 힘 0.1 N 단위 지정 가능, 파지 감지 비트·busy 비트 읽기 가능, gateway가 로봇·그리퍼를 모두 소유. onrobot 드라이버는 응답이 이동 완료를 안 기다리고 항상 success, `'c'` 명령 기본 힘 40 N(최대)이라 종이 박스에 부적합. BRD 6.1 후보 드라이버는 `onrobot_driver`(ahnisinc/cobot_rg2)인데 현재 설치·검토한 것은 ABC-iRobotics/onrobot-ros2 `c6e3903` → 드라이버를 쓰게 되면 어느 쪽인지 확인 필요. 조건: 브링업의 onrobot 드라이버와 공존 시험 통과(⏳#4), 실패 시 드라이버를 빼는 launch 인자. pending #9 오늘 결정 → ADR-0003 |
| 힘·폭·시간 / A | 사전 개방90mm 후보, 실제 파지 폭/힘/허용값·단위·명령 시간·무손상 시험 | 사전 개방 90 mm(BRD TR-PICK-06·2.4: 닫힘축을 벨트 방향으로, 타이밍 오차 양쪽 22 mm씩 흡수), 파지 목표 폭 40 mm(박스 46 mm보다 작게 해 힘에 닿아 멈추게). 힘 ⏳#8(3→5→8→10→15 N, 힘마다 2회, 찌그러짐 없고 안 미끄러지는 최저 힘 + 한 단계 여유). 명령 시간 미측정. 무손상 파지 10회는 T34(10/07~08) 완료 기준 |
| 피드백 / A | width_actual·힘·상태의 가용 여부/주기/단위, 빈 파지/성공/센서 오류 판정 | BRD TR-PICK-07은 "그리퍼 폭 피드백으로 파지 실패 감지". Modbus 상태 레지스터: 실제 폭(0.1 mm), grip_detected 비트, busy 비트. 주기 = 명령 시 gateway가 폴링(상시 발행 없음, 제안). 판정 제안: 성공 = grip_detected AND 폭 46±3 mm(⏳#8 실측 폭으로 확정), 빈 파지 = 목표 폭 근처까지 닫힘, 센서 오류 = Modbus 연결 실패·timeout → `ok=false, gripper_error`. 현재 Gripper.srv에는 grip_detected 필드가 없음 → NEW-R-02 |
| 책임 경계 / A | servo와 gateway 중 개방/닫힘/성공 판정을 누가 호출·결정하며 timeout은 어디서 처리하는지 | **미합의.** 현 topics.md는 gripper 호출 주체를 sort_manager로 적었고, SRD IC-ROBOT-03은 "manager/servo"로 열어 둠. 제안: gateway = 개폐 실행 + 측정값(width_actual, grip_detected) 반환, Modbus timeout은 gateway에서 처리. **파지 중 닫힘 호출과 성공 판정은 추종 타이밍을 아는 belt_servo**(FR-009·010 박병후). 적재 위치에서의 개방은 move_to_zone 안에서 gateway가 처리(R-04). 박병후 B-01 회신과 맞춰 확정 |

A 상태·남은 항목: `미정 — 경로 #9·힘 #8 오늘 결정/실측, 호출 주체는 박병후·남현지 합의 필요` · B 상태·남은 항목: `미정 — 재시도(FR-011) 시 재개방·재파지 규약은 박병후 B-01` · C 선택 상태: `해당 없음`  
근거/파일/실측: `scripts/measure_1006/README.md #4·#8`, `rg2_check.py` · 미정 담당·결정 예정일: `김학민(경로·값) 10/06, 호출 주체 박병후·남현지·김학민 10/07`

### R-04 — 구역·관측 자세·격자·적재 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 좌표 표 / A | A/B/C/recheck/hold·관측 자세 posx, 단위·frame·도구 기준·실측 일시/담당 | ⏳#6-b. 형식: 두산 posx `[x, y, z, rx, ry, rz]` mm/deg, 로봇 베이스 기준, **플랜지 기준(TCP 미적용)**, 구역 중심에서 박스 밑면이 막 닿는 높이 + 5 mm, 수직 아래 자세. 구역 번호는 BRD 2.4 매핑 표 기준(01 역삼 A · 02 대치 B · 03 청담 C · 90 재확인 · 99 보류), config 키는 A/B/C/recheck/hold. 담당 김학민, 일시 [기입]. 관측 자세는 BRD TR-PICK-01(상류 끝 위 약 15 cm) 기준으로 R3에서 남현지·박병후와 결정. 미실측 0값 pose는 gateway가 `pose_not_set`으로 거부(제안). `voss_config.md`에 기준점(TCP/플랜지)·슬롯 원점이 없어 문서 보완 요청 예정 |
| 적재 슬롯 / A/B | cols/rows/pitch·slot→위치·구역 용량·가득 찼을 때 처리·카운터 주체 | A/B/C: 2×2, pitch 60 mm(config 초안) → 구역당 4칸. slot→위치는 구역 중심 기준 오프셋, slot 0~3 행 우선(제안, 순수 함수 + pytest). **카운터 주체 = sort_manager**(BRD TR-PICK-08 "구역별 적재 카운터로 격자 오프셋" — MoveToZone 요청에 slot을 담아 보냄). 가득 참: gateway는 범위 밖 slot을 `invalid_zone`으로 거부, 이후 처리는 manager(TBD-005). recheck는 1칸(정지 재판독 위치). **hold는 config에 격자가 없음** → 보류가 여러 개면 위치 충돌 → 격자 추가 필요(B, 남현지와 결정) |
| 적재·복귀 / A | move_to_zone 요청/접수/실제 완료/오류, 복귀 조건·다음 관측 준비 | 시퀀스 제안: safe 높이 → 구역 slot 상공 → 하강 → 그리퍼 개방 → 상승 → observe_pose 복귀 → 응답 `ok=true`. 응답 시점 = 복귀 도달 후이므로 응답 수신 = 다음 관측 준비 완료. 단계 실패 시 `ok=false` + 사유. 결과 기록(logger)과의 선후는 manager가 결정(TBD-007). 작업 시작 때 관측 자세로만 이동하는 경우(BRD 8.1 1단계)는 NEW-R-05 |
| 검증 / A/B | 5구역 각 시험 횟수·위치 충돌/박스 손상·실측 증거 | VC-R-03: T35 완료 기준 "5구역 적재 각 3회 성공"(정지 Pick&Place, 10/08 마일스톤, 10/08~10). 위치 충돌·박스 손상·케이블 확인, 영상·poses.csv 증거 |

A 상태·남은 항목: `미정 — 좌표 ⏳#6, 관측 자세 R3 결정, 시퀀스는 제안` · B 상태·남은 항목: `미정 — hold 격자, 구역 가득 찼을 때 처리` · C 선택 상태: `해당 없음`  
근거/파일/실측: `docs/interfaces/voss_config.md`, `record_pose.py` · 미정 담당·결정 예정일: `김학민(좌표 10/06), 남현지(관측 자세 10/06, hold 격자 10/08)`

### R-05 — 제한·안전 중단·복구 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 제한값 / A | 작업 영역·속도·가속·그리퍼 제한의 값/단위·근거·강제 위치 | **강제 위치 = robot_gateway**(모든 servo_cmd·move 명령을 clamp/거부). 근거 BRD NFR-09(협동로봇 속도 제한, 작업 영역 소프트웨어 리밋). 작업 영역: #6 실측 기반 직육면체(작업대 면 위 여유, 리치 850 mm 이내) — 값 미정. 속도·가속 상한: 미정(T32 실기 저속부터, 벨트 추종을 위해 벨트 속도보다는 커야 함). 그리퍼 힘 상한: #8 선택값 + 여유, 40 N 사용 금지. 실측 단계는 펜던트 협동 속도 제한 상태에서 진행 |
| 정지·취소 / A/B | 각 동작 단계의 stop/action cancel/비상정지 경로·최대 중단 지연·정지 확인 방법 | 경로(제안): ① 작업 정지("멈춰"·HMI 정지, BRD TR-VOICE-05·NFR-09): sort_manager stop → track_and_grasp 취소(박병후) → gateway 정지 요청(`/voss/robot/stop` 신설 제안 NEW-R-04, 두산 move_stop) ② move_to_zone 중 정지: gateway가 move_stop 후 `ok=false, stopped` ③ 비상정지: 티치펜던트(최종 수단). move_stop 모드 제안: 소프트웨어 정지 = `DR_QSTOP(1)`(Stop Category 2), 일시 정지 후 재개 가능성이 필요하면 `DR_HOLD(3)` 검토 — 실기에서 정지 거리 비교 후 확정. 정지 확인 = 정지 후 pose 변화 없음. **취소 접수 ≠ 실제 정지**로 구분. 참고: 전 프로젝트 move_stop **응답** 115~124 ms(BRD 6.1, 정지 완료 시간 아님). 최대 중단 지연 미측정(VC-R-04) |
| 입력 상실 / A | servo/pose/box 입력 오래됨·통신 상실·프로세스 종료에서 안전 상태 | servo_cmd: 마지막 수신 후 감시 시간 초과 시 gateway가 속도 0/정지(감시 시간 값 미정, 30 Hz 기준 몇 주기 — 박병후 B-02와 결정). pose·box 오래됨은 servo 쪽 판단(B-02). **gateway 프로세스가 죽었을 때:** ASYNC move_line은 컨트롤러에서 계속 진행될 수 있음 → 스트리밍 명령은 짧은 상대 이동 단위로 제한해 남는 이동량을 작게(제안). 확인 필요 |
| 복구 / A/B | 정지/노드 재기동 후 상태·보유 박스·작업 재개 조건·사람 확인 | 정지 후 보유 중인 박스는 사람이 확인·제거. dsr_controller2 무응답 시 복구는 브링업 재시작뿐(전 프로젝트 실측) → 재시작 후 툴/TCP 재등록 필수. gateway 재기동 시 이동 명령 없이 pose 발행부터 재개, 첫 동작 전 사람 확인. 작업 재개 조건·상태 전이는 sort_manager(TBD-005) |
| 물리 접근 / A | 비상정지·투입 위치·케이블/그리퍼/벨트 간섭에 대한 실제 확인 | 실기 시 비상정지 앞 1인 상주. 투입 위치 표시(#1), 케이블·간섭은 #6-b 교시 때 확인, 사진 ⏳#6 |

A 상태·남은 항목: `미정 — 구조 제안 완료, 제한값·정지 지연·감시 시간은 T32 실기(10/08) 후` · B 상태·남은 항목: `미정 — 재개 조건(남현지 TBD-005)` · C 선택 상태: `해당 없음`  
근거/파일/실측: `src/voss_robot/CLAUDE.md`, `scripts/measure_1006/README.md §0` · 미정 담당·결정 예정일: `김학민·박병후 / 10/08`

### R-06 — 배포·준비·기동·복구 (A)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 배포 목록 / A/B | 기능별 호스트/비전 컨테이너/DB/웹 실행 위치·외부 장비 연결·책임자 | (architecture.md 기준) **호스트(공용 MSI):** 두산 브링업, robot_gateway(김학민), belt_servo(박병후), sort_manager(남현지), voice 3노드·hmi_bridge·sort_logger(정의석), Mosquitto 1883. **비전 컨테이너(GPU):** box_tracker·label_reader(남현지). **DB 컨테이너:** 정의석(종류 pending #14). **웹:** 미정(pending #13, 정의석). 장비: 로봇·RG2 유선, D435i USB 3.0, 아두이노 시리얼(VOSS 노드와 연결 없음) |
| 준비·기동 / A | 각 노드/장비 준비 신호, 초기 툴/TCP·설정 적용, 실행 순서·한 번의 기동 가능 범위 | 순서 제안: ① 두산 브링업 `mode:=real host:=192.168.1.100` → "Configured and activated dsr_controller2" 확인 ② 툴/TCP 등록 스크립트(T32) ③ robot_gateway → pose·로봇 상태 발행 확인(=로봇 준비, NEW-R-06) ④ 카메라·비전 컨테이너 ⑤ belt_servo·sort_manager·음성·HMI. ①~③은 voss_bringup launch 하나로 묶는 것이 목표(남현지 공동), ①은 사람이 비상정지 옆에서 실행. 운전 시작("작업 시작") 때 관측 자세로 이동(BRD 8.1 1단계, NEW-R-05). 로봇 준비 신호 형식은 NEW-R-01·06 |
| 통신·저장 / A/B | DDS/MQTT·host network/domain·마운트/볼륨·시각 동기·DB 접속 | CycloneDDS, ROS_DOMAIN_ID 30, 컨테이너 `--network host` + 같은 도메인, 설정 파일은 호스트 `~/voss_ws/config/voss_config.yaml`, 비전 컨테이너에는 읽기 전용 마운트, 쓰는 노드는 sort_manager 하나(BRD TR-SYS-06). 공용 PC 유선(로봇 서브넷)·Wi-Fi(인터넷, OpenAI API) NIC 분리(BRD 6.1). 노드 대부분이 한 PC라 같은 시계. 개인 PC를 붙이면 시각 동기 필요(미정). DB 접속·볼륨은 정의석 |
| 재기동·실패 / A/B | 기동 누락·장비 미연결·노드 종료·컨테이너 재기동의 확인·복구 | 로봇 미연결: 브링업이 activated 로그를 안 냄 → gateway 기동 안 함. 브링업 재시작 시 TCP 풀림 → 재등록. dsr_controller2 무응답 → 브링업 재시작. RG2 무응답 → gateway가 gripper `ok=false`. 컨테이너 재기동은 해당 담당 |
| 그림 자료 / A/B | 논리·배포 구성도에 넣을 장비/연결/위치 목록·초안 그림 경로 | 논리: `docs/architecture.md` mermaid. 배포: 같은 파일 배포 표 + 위 장비 연결. 물리 배치: `작업 환경 구성도.png`(팀 스케치), #6-a 실측 스케치 사진 ⏳ |

A 상태·남은 항목: `미정 — 순서는 제안, 툴/TCP 스크립트·launch는 T32(10/08)` · B 상태·남은 항목: `미정 — 웹·DB 위치(정의석), 컨테이너 연결 시험 10/13` · C 선택 상태: `해당 없음`  
근거/파일/실측: `docs/architecture.md`, `docs/setup/dev-environment.md` · 미정 담당·결정 예정일: `김학민(호스트·로봇 쪽) 10/08, 정의석(DB·웹) 10/08~09`

### R-07 — 선택 신규 구역 교시 (C)

| 답변 항목·단계 | 작성할 내용 | 답변·카드 참조 |
| --- | --- | --- |
| 채택 상태 / C | [미채택/후속 검토/채택 제안] | **후속 검토.** T36(10/11~13)에서 G0 승인·기본 흐름 안정 후 판단. 일정이 밀리면 먼저 제외(BRD 8장). 단 BRD R-14 완화책대로 **직접교시 좌표 읽기만은 초기에 단독 확인** — 10/06 #6-b `record_pose.py`(현재 posx 조회)로 확인 예정 |
| 채택 시 계약 / C | 대기/직접교시 조건·TCP 조회·영역 검증·확인·등록/취소·좌표/설정 전달 | 현재 정의: `/voss/robot/teach_zone`(TeachZone: `zone` → `ok`, `message`). 채택 시 IDLE 상태에서만 허용(BRD TR-VOICE-10 "대기 상태의 직접교시 모드"), 현재 posx 조회 → 작업 영역 검증 → 확인. **충돌:** voss_config.md는 "설정을 쓰는 노드는 sort_manager뿐" → gateway는 좌표를 반환만 하고 저장은 manager가 하도록 응답에 pose 필드 추가 필요(채택 시 변경 제안, BRD TR-SYS-06과도 일치). BRD는 "현재 **TCP** 좌표"로 적었는데 zones는 플랜지 기준으로 기록 중 → 기준점 통일 필요(TBD-016) |
| 영향 / C | manager·설정·intent·HMI에 주는 영향과 작업량 | manager(설정 쓰기·zone_map 갱신), intent(teach 유형 추가 — 현재 Intent type에 없음), HMI(확인 표시). 작업량 1~2일 추정 |

A 상태·남은 항목: `해당 없음` · B 상태·남은 항목: `해당 없음` · C 선택 상태: `후속 검토`  
근거/파일/실측: `docs/interfaces/voss_msgs.md`, `voss_config.md` · 미정 담당·결정 예정일: `김학민·남현지 / G0 승인 후`

## 3. 인터페이스 카드

| 관련 IC-ID / 연결 | 역할·공통 카드 주 작성자 | 카드 ID / 미정 / 해당 없음·이유 |
| --- | --- | --- |
| IC-ROBOT-01 / servo→gateway | 상대 확인 / 박병후 | 박병후 카드 대기. gateway가 기대하는 것: TwistStamped, `frame_id=base_link`, linear m/s·angular rad/s, 30 Hz, best_effort depth 1. gateway가 속도·영역 clamp와 감시 시간 정지를 적용함. 확인 일시: 미확인 — 회신 제출 후 박병후에게 확인 요청 |
| IC-ROBOT-02 / gateway→servo | 주 작성 / 김학민 | **IC-R-01** (아래) |
| IC-ROBOT-03 / manager/servo↔gateway | 주 작성 / 김학민 | **IC-R-02** (아래). 그리퍼 호출 주체 미합의. 신설 제안 연결: `/voss/robot/stop`(NEW-R-04), `zone="observe"`(NEW-R-05), `/voss/robot/state`(NEW-R-06) |
| IC-CONFIG-01 / 설정→각 소비자 | 상대 확인 / 남현지 | 남현지 카드 대기. 요청 차이: ① zones·observe_pose의 기준점(플랜지/TCP)과 slot 원점(중심) 명시 ② 벨트 방향을 `direction_axis: "x"` 대신 단위 벡터로(베이스 축과 틀어진 경우, 박병후 피드포워드 영향) ③ hold 격자 추가 ④ gateway도 zones·limits를 읽어야 함(소비자 목록 추가) |
| IC-DEVICE-01 / gateway↔장비 | 주 작성 / 김학민 | **IC-R-03** (아래) |
| IC-OPTION-01 / 명령↔설정/로봇 | 상대 확인 / 남현지 | 선택 미채택(후속 검토). R-07의 teach_zone 응답 필드 충돌만 기록 |

#### IC-R-01 — robot pose

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC-ID / 연결 질문 ID·TBD-ID | IC-R-01 / IC-ROBOT-02 / R-02 · TBD-014, TBD-020 |
| 계약 상태·버전 / 기존 유지·변경·신규 | 제안 / 기존 이름 유지(topics.md 2026-10-05), frame·단위·기준점 추가 |
| 생산자·제공자 → 소비자·호출자 / 담당자 | robot_gateway(김학민) → belt_servo(박병후), (선택) sort_manager·HMI |
| ROS topic/service/action·MQTT·DB/API 이름 / 실제 타입 | `/voss/robot/pose` / geometry_msgs/PoseStamped |
| 입력·출력 필드 / 필수·선택 / enum·범위 / 기본값 | header.stamp, header.frame_id, pose.position(m), pose.orientation(quaternion). 모두 필수 |
| 식별자·촬영/처리 시각·시계 / 단위·frame_id·orientation | stamp = 두산 위치 조회 응답을 받은 시각(제안, 호스트 시계). frame_id `base_link`(제안). 위치 기준점 **플랜지 or TCP 미정** — 캘리브레이션(남현지) 기준과 맞춰 결정 |
| 발행/호출 조건·주기 / 신뢰성·durability·depth / MQTT QoS·retained | ~50 Hz(제안, 미확인), best_effort / volatile / depth 1. 로봇 준비 후 상시 발행 |
| 접수/완료/실패 의미 / 오류 코드 / timeout·retry·cancel | 조회 실패 시 해당 주기 발행 생략(오래된 값 재발행 안 함, 제안) → 소비자는 stamp 나이로 stale 판단 |
| 중복·순서역전·오래된 데이터·재접속 처리 | depth 1 최신값만. stale 기준은 박병후 B-02 |
| 설정·외부 의존 / 준비 조건 / 실행 위치 | 두산 `get_current_posx`, 단일 큐 / 브링업 activated / 호스트 |
| 송수신 데이터 예시 / 단위 변환 예시 | 아래 |
| 상대에게 필요한 변경 / 상대 확인자·일시 / 미합의 내용 | 박병후: stale 기준·필요 주기 회신 / 미확인 — 회신 제출 후 박병후 확인 요청 / 기준점(플랜지·TCP), 실제 주기 |
| A 최소 계약 상태·남음 / B 후속 상태·남음 / C 채택 상태 | A: 제안, 주기 실측 남음 / B: 30 Hz 서보 부하에서 주기 유지 확인 / C: 해당 없음 |
| 관련 저장소 문서·메시지·코드 / 변경 영향 | topics.md / frame·기준점 명시는 topics.md 보완 |

```text
두산 posx (mm, deg, ZYZ): [412.3, -35.0, 210.5, 0.0, 180.0, 0.0]
→ PoseStamped: header.frame_id="base_link", position=(0.4123, -0.0350, 0.2105),
  orientation = ZYZ(0°,180°,0°)를 쿼터니언으로 변환한 값  (예시값, 실측 아님)
```

#### IC-R-02 — move_to_zone / gripper

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC-ID / 연결 질문 ID·TBD-ID | IC-R-02 / IC-ROBOT-03 / R-02·R-03·R-04 · TBD-015, TBD-016, TBD-019 |
| 계약 상태·버전 / 기존 유지·변경·신규 | 제안 / 이름·요청 필드 유지, 응답 보완 제안(NEW-R-02) |
| 생산자·제공자 → 소비자·호출자 / 담당자 | robot_gateway(김학민) ← move_to_zone: sort_manager(남현지) / gripper: **미합의**(sort_manager 또는 belt_servo, R-03) |
| ROS topic/service/action·MQTT·DB/API 이름 / 실제 타입 | `/voss/robot/move_to_zone` voss_msgs/srv/MoveToZone, `/voss/robot/gripper` voss_msgs/srv/Gripper |
| 입력·출력 필드 / 필수·선택 / enum·범위 / 기본값 | MoveToZone: `zone` ∈ {A,B,C,recheck,hold} (+ 제안 `observe`, NEW-R-05), `slot` 0~3(A/B/C), recheck·hold는 0 → `ok`, `message`. Gripper: `width` mm(0~110), `force` N(0~상한) → `ok`, `width_actual` mm (+ 제안 `grip_detected`, `message`) |
| 식별자·촬영/처리 시각·시계 / 단위·frame_id·orientation | 박스 식별자 없음(manager가 box_id와 연결). mm·N |
| 발행/호출 조건·주기 / 신뢰성·durability·depth / MQTT QoS·retained | 이벤트 호출. 동시에 한 동작만 |
| 접수/완료/실패 의미 / 오류 코드 / timeout·retry·cancel | 응답 = 실제 완료(move_to_zone은 놓기+observe_pose 복귀 후). 실패 `ok=false`, message 사유 코드 `busy`/`invalid_zone`/`pose_not_set`/`timeout`/`stopped`/`gripper_error`(제안). 재시도는 호출자 판단. 취소는 서비스라 불가 → 정지 요청으로 중단(R-05) |
| 중복·순서역전·오래된 데이터·재접속 처리 | 동작 중 두 번째 호출은 `busy` 거부 |
| 설정·외부 의존 / 준비 조건 / 실행 위치 | voss_config.yaml zones·observe_pose·gripper / 로봇 준비 + zones 실측값 / 호스트 |
| 송수신 데이터 예시 / 단위 변환 예시 | 아래 |
| 상대에게 필요한 변경 / 상대 확인자·일시 / 미합의 내용 | 남현지: slot 카운터 manager 소유 확인, 사유 코드 수용, stop·observe·state 신설 검토 / 박병후: gripper 호출 주체 / 미확인 — 회신 제출 후 남현지·박병후 확인 요청 / gripper 호출 주체, hold 격자 |
| A 최소 계약 상태·남음 / B 후속 상태·남음 / C 채택 상태 | A: 제안 / B: 구역 가득 찼을 때, 재시도 시 그리퍼 규약 / C: teach_zone 후속 검토 |
| 관련 저장소 문서·메시지·코드 / 변경 영향 | voss_msgs.md, src/voss_msgs/srv / Gripper.srv 변경 시 voss_msgs·docs 동시 수정 + interface 라벨 + 남현지 승인 |

```text
MoveToZone 요청: {zone: "A", slot: 2}  →  응답: {ok: true, message: "placed A/2, at observe_pose"}
MoveToZone 실패: {zone: "hold", slot: 0} → {ok: false, message: "pose_not_set: hold"}
Gripper 요청: {width: 40.0, force: <#8 값>} → 응답: {ok: true, width_actual: 45.8, grip_detected: true(제안)}
```

#### IC-R-03 — gateway ↔ 장비

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC-ID / 연결 질문 ID·TBD-ID | IC-R-03 / IC-DEVICE-01 / R-01·R-02·R-03 · TBD-013, TBD-014, TBD-015 |
| 계약 상태·버전 / 기존 유지·변경·신규 | 제안 / RG2 경로 오늘 결정(pending #9) |
| 생산자·제공자 → 소비자·호출자 / 담당자 | robot_gateway(김학민) → 두산 dsr_controller2, RG2 |
| ROS topic/service/action·MQTT·DB/API 이름 / 실제 타입 | 두산(소스 확인, 접두 `/dsr01/dsr_controller2/`): `motion/move_line` — MoveLine 요청 `pos[6]`(mm/deg), `vel[2]`(mm/s, deg/s), `acc[2]`, `time`(s), `radius`(mm), `ref`(BASE 0/TOOL 1/WORLD 2), `mode`(ABS 0/REL 1), `blend_type`, `sync_type`(SYNC 0/ASYNC 1) → `success`. `aux_control/get_current_posx` — GetCurrentPosx 요청 `ref` → `task_pos_info[]`(posx + solution space), `success`. `motion/move_stop` — MoveStop 요청 `stop_mode`(QSTOP_STO 0 / QSTOP 1 / SSTO 2 / HOLD 3) → `success`. 스트리밍: `servol_stream` — ServolStream `pos[6]`, `vel[2]`, `acc[2]`, `time`. `speedl_stream` — SpeedlStream `vel[6]`(작업공간 속도), `acc[2]`, `time`, `ref`(**M2.40 이상만**, DRCF 버전 ⏳#2로 확인). Twist(속도 명령)와 형태가 맞는 것은 speedl_stream → 박병후 #8 비교 후보로 전달. RG2: Modbus TCP 192.168.1.1:502 (unit 65, 제어 레지스터 0~2·상태 레지스터 258·267·268·275, 수업 코드 onrobot.py와 같은 레지스터) |
| 입력·출력 필드 / 필수·선택 / enum·범위 / 기본값 | 두산 posx mm/deg. RG2 힘 0.1 N, 폭 0.1 mm |
| 식별자·촬영/처리 시각·시계 / 단위·frame_id·orientation | 로봇 베이스 좌표, ZYZ |
| 발행/호출 조건·주기 / 신뢰성·durability·depth / MQTT QoS·retained | 두산 서비스는 단일 큐 직렬. **gateway 외 프로그램 동시 호출 금지**. 소스상 move_stop만 별도 callback group으로 등록돼 있어 다른 서비스 처리 중에도 정지 요청이 들어갈 수 있음 → gateway도 정지를 큐 밖 경로로 보냄(제안). 스트리밍 토픽 depth: servol 20, speedl 10(소스) |
| 접수/완료/실패 의미 / 오류 코드 / timeout·retry·cancel | ASYNC move_line은 접수 후 바로 반환 → 완료는 위치/상태 조회로 확인. RG2 완료는 busy 비트 해제 |
| 중복·순서역전·오래된 데이터·재접속 처리 | dsr_controller2 무응답 시 브링업 재시작. Modbus 끊김 시 재연결 시도 후 실패 보고 |
| 설정·외부 의존 / 준비 조건 / 실행 위치 | doosan-robot2(~/cobot2_ws), 유선 서브넷 / 브링업 activated, TCP 등록 / 호스트 |
| 송수신 데이터 예시 / 단위 변환 예시 | IC-R-01 예시 참조 |
| 상대에게 필요한 변경 / 상대 확인자·일시 / 미합의 내용 | 박병후: servol_stream 확인 결과(#3) / 미확인 — 박병후 #3 결과 수신 후 / 스트리밍 방식 |
| A 최소 계약 상태·남음 / B 후속 상태·남음 / C 채택 상태 | A: 미정(#4·#3 오늘) / B: 30 Hz 스트리밍 큐 영향 / C: 해당 없음 |
| 관련 저장소 문서·메시지·코드 / 변경 영향 | topics.md robot_gateway 행, pending #8·#9, ADR-0003(예정) / 두산·RG2 의존은 voss_robot 패키지에만 |

## 4. 요구사항·성능 검증 카드

#### VC-R-01 — 장비·환경·배치 검사

| 항목 | 답변 |
|---|---|
| 관련 SYS-ID / VT-ID / 연결 질문·TBD-ID | SYS-CT-001/VT-060, SYS-CT-004/VT-063, SYS-SF-003/VT-055, SYS-EN-002/VT-069, SYS-EN-003/VT-070 / R-01·R-05 · TBD-013, TBD-017 |
| 확인할 동작·목표 / 목표의 근거 | 장비·버전 일치, 벨트 자동 제어 경로 없음, 비상정지 접근, 투입 위치와 관측 자세 비중첩, 케이블 무간섭, (가이드 사용 시) 높이 15 mm 이하, 회수함 위치 / BRD 2.2·6.1·6.3, NFR-09·10 |
| 방법: 검사/분석/시연/시험 / 모의·실기 구분 | 검사(I) / 실기 |
| 입력·정답 세트·조건·환경·장비/코드 버전 | 실제 작업대·장비, env_report.sh, 배치 스케치 |
| 시작/종료 측정점·시각 필드·단위 | 해당 없음(검사) |
| 시험 횟수·분모 / retry·실패·skip·held·재투입의 포함 여부 | 항목별 1회 확인, T37(10/14~15) 재점검 |
| 합격 기준·계산식 / 평균·상한·분포의 보고 방식 | 5개 하위 조건 모두 확인 시 통과 |
| 하위 조건·SYS/VT별 결과 / 전체 판정 / 미수행이면 예정일·담당 | CT-001: ⏳#2 / CT-004: 검사 예정 10/06 / SF-003: 10/06 / EN-002: ⏳#1·#6 / EN-003: ⏳#6, 동작 범위는 VC-R-03 / 전체: 미수행 / 김학민 |
| 증거 파일·로그·스크린샷/영상·확인자·일시 | env_report 출력, 배치 사진, measurements #1·#2·#6 / 확인자 김학민, 일시는 실측 완료 시 기록(10/06) |
| 목표 달성 불가/자료 부족 시 대안·영향 | 투입 위치 겹침 시 관측 자세·투입 표시 재배치 |

#### VC-R-02 — robot_gateway 단일 큐·제한·인터페이스

| 항목 | 답변 |
|---|---|
| 관련 SYS-ID / VT-ID / 연결 질문·TBD-ID | SYS-CT-003/VT-062, SYS-SF-002/VT-054, SYS-IF-003/VT-039, SYS-FR-001/VT-001(로봇·그리퍼 준비 부분) / R-02 · TBD-014, TBD-017 |
| 확인할 동작·목표 / 목표의 근거 | 두산 호출 직렬화, 영역·속도 clamp, 단위 변환, 응답 규약 / T32 완료 기준 "move_line 큐 1시간 무정지" |
| 방법: 검사/분석/시연/시험 / 모의·실기 구분 | 시험(T) / ① dry_run·pytest(모의) ② 실기 1시간 큐 |
| 입력·정답 세트·조건·환경·장비/코드 버전 | 가짜 servo_cmd(`ros2 topic pub`), 경계 밖 좌표·속도 초과 입력, robot_gateway 커밋(미구현 — 시험 시 기록) |
| 시작/종료 측정점·시각 필드·단위 | 호출 요청~응답 시각, pose stamp 간격(Hz) |
| 시험 횟수·분모 / retry·실패·skip·held·재투입의 포함 여부 | 1시간 연속, 경계 입력 케이스별 1회 이상 |
| 합격 기준·계산식 / 평균·상한·분포의 보고 방식 | 1시간 무정지, 경계 밖 입력 100% 거부/clamp, 동시 호출 0건. pose 주기는 평균·최소 보고 |
| 하위 조건·SYS/VT별 결과 / 전체 판정 / 미수행이면 예정일·담당 | 미수행 / 10/08 / 김학민 |
| 증거 파일·로그·스크린샷/영상·확인자·일시 | gateway 로그, pytest 결과, PR 실기 확인 칸 |
| 목표 달성 불가/자료 부족 시 대안·영향 | 50 Hz pose 불가 시 주기 하향 → 박병후 B-02와 재협의 |

#### VC-R-03 — 정지 Pick&Place 5구역

| 항목 | 답변 |
|---|---|
| 관련 SYS-ID / VT-ID / 연결 질문·TBD-ID | SYS-FR-012/VT-012, SYS-FR-013/VT-013, SYS-EN-003/VT-070(동작 범위) / R-04 · TBD-016 |
| 확인할 동작·목표 / 목표의 근거 | 5구역 slot 적재 + observe_pose 복귀 / T35 완료 기준 "5구역 적재 각 3회 성공" |
| 방법: 검사/분석/시연/시험 / 모의·실기 구분 | 시험(T) / 실기(저속 시작, 비상정지 앞 1인) |
| 입력·정답 세트·조건·환경·장비/코드 버전 | 정지 상태 박스, zones ⏳#6, 그리퍼 힘 ⏳#8 |
| 시작/종료 측정점·시각 필드·단위 | move_to_zone 요청~응답(s) |
| 시험 횟수·분모 / retry·실패·skip·held·재투입의 포함 여부 | 5구역 × 3회 = 15회, 재시도 없이 집계 |
| 합격 기준·계산식 / 평균·상한·분포의 보고 방식 | 15/15, 박스 손상·위치 충돌·케이블 간섭 0. 소요 시간 평균·최대 보고 |
| 하위 조건·SYS/VT별 결과 / 전체 판정 / 미수행이면 예정일·담당 | 미수행 / 10/08~10 / 김학민 |
| 증거 파일·로그·스크린샷/영상·확인자·일시 | 영상, gateway 로그 / 미수행 — 10/08~10 시험 시 확인자·일시 기록 |
| 목표 달성 불가/자료 부족 시 대안·영향 | 좌표 재교시, 속도 하향. 10/08 마일스톤 지연 시 G0 영향 |

#### VC-R-04 — 정지·입력 상실

| 항목 | 답변 |
|---|---|
| 관련 SYS-ID / VT-ID / 연결 질문·TBD-ID | SYS-SF-001/VT-053 / R-05 · TBD-017, TBD-020 |
| 확인할 동작·목표 / 목표의 근거 | 정지 요청·servo_cmd 끊김 시 정지 / NFR-09 |
| 방법: 검사/분석/시연/시험 / 모의·실기 구분 | 시험(T) / dry_run 로직 확인 후 실기(저속) |
| 입력·정답 세트·조건·환경·장비/코드 버전 | 단계별(이동 중·스트리밍 중·move_to_zone 중) 정지 요청, servo_cmd 발행 중단, gateway 종료 |
| 시작/종료 측정점·시각 필드·단위 | 정지 요청 시각 ~ pose 변화 없음 확인 시각(ms) |
| 시험 횟수·분모 / retry·실패·skip·held·재투입의 포함 여부 | 단계별 3회(제안) |
| 합격 기준·계산식 / 평균·상한·분포의 보고 방식 | 모든 경우 정지. 최대 지연 값은 측정 후 승인 |
| 하위 조건·SYS/VT별 결과 / 전체 판정 / 미수행이면 예정일·담당 | 미수행 / 10/08 / 김학민·박병후 |
| 증거 파일·로그·스크린샷/영상·확인자·일시 | gateway 로그(시각), 영상 / 미수행 — 10/08 시험 시 확인자·일시 기록 |
| 목표 달성 불가/자료 부족 시 대안·영향 | 스트리밍 단위 이동량 축소, 속도 상한 하향 |

## 5. 미정·의존·범위 제안

### 5.1 필수 변경 제안 카드

#### NEW-R-01 — SYS-FR-001 담당·문장 분리

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-01 · 김학민 / 수정(담당·문장) |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | SYS-FR-001 / VT-001, ID 유지 |
| 변경 전 내용 / 변경 후 내용 | 전: "시스템은 카메라·로봇·그리퍼·설정·로그 저장 경로의 준비 여부를 확인한 뒤…" (김학민). 후: 문장 유지, **주담당 남현지(sort_manager 통합 판단·표시)**. 각 파트는 자기 준비 상태 제공(로봇·그리퍼 = robot_gateway 김학민). 준비 상태 전달 형식은 TBD-018에서 결정 |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | 카메라·설정·로그 준비는 robot_gateway가 알 수 없어 김학민 담당으로는 검증 불가. 통합 판단 위치가 정해지지 않으면 VT-001 수행 주체가 없음 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | sort_manager, robot_gateway, TBD-018, VT-001 |
| 대안·이행 방법·기존 기능/일정 영향 | 대안: 공동 담당(남현지 주, 김학민 부). 일정 영향 없음 |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 남현지 의견 미수신 / 제안 |

#### NEW-R-02 — Gripper.srv 응답에 파지 감지·사유 추가

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-02 · 김학민 / 계약 수정(IC-ROBOT-03) |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | IC-ROBOT-03, IC-R-02 / SYS-FR-010·SYS-IF-003 관련 |
| 변경 전 내용 / 변경 후 내용 | 전: Gripper 응답 `bool ok, float32 width_actual`. 후: `bool ok, float32 width_actual, bool grip_detected, string message` |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | FR-010(파지 성공 판정)은 그리퍼 피드백이 필요한데 현재 응답에는 폭만 있음. 폭만으로는 빈 파지·센서 오류 구분이 약하고 실패 사유를 전달할 필드가 없음 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | voss_msgs(srv), docs/interfaces/voss_msgs.md, 호출자(sort_manager 또는 belt_servo), TBD-015·019 |
| 대안·이행 방법·기존 기능/일정 영향 | 필드 추가라 기존 필드 호환. docs/interfaces 먼저 수정 → interface 라벨 → 남현지 승인 → Slack 공지. 10/07 전 반영 목표 |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 박병후·남현지 의견 미수신 / 제안 |

#### NEW-R-03 — SYS-CT-005 담당 분리

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-03 · 김학민 / 수정(담당) |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | SYS-CT-005 / VT-064, ID 유지 |
| 변경 전 내용 / 변경 후 내용 | 전: 김학민 단독. 후: 비전 컨테이너 남현지, DB 컨테이너 정의석이 주담당, 김학민은 호스트 쪽 네트워크(DDS·도메인·host network)·기동 순서 확인 |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | docker/vision·docker/db 소유자가 다름(architecture.md·dev-environment.md). 단독 담당이면 이미지·의존성·볼륨 검증 책임이 비어 있음 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | TBD-018·026, VT-064 |
| 대안·이행 방법·기존 기능/일정 영향 | 일정 영향 없음 |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 남현지·정의석 의견 미수신 / 제안 |

#### NEW-R-04 — 로봇 정지 서비스 신설

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-04 · 김학민 / 계약 추가(IC-ROBOT-03 연결) |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | IC-ROBOT-03, IC-R-02 / SYS-SF-001·SYS-FR-019 관련, VT-053 |
| 변경 전 내용 / 변경 후 내용 | 전: gateway 서비스는 move_to_zone·gripper·teach_zone뿐, 정지 경로 없음. 후: `/voss/robot/stop` (std_srvs/srv/Trigger) — 요청 즉시 진행 중 이동·스트리밍 중단(두산 move_stop), 응답 `success`·`message`(정지 완료 확인 후). 호출자: sort_manager("멈춰"·HMI 정지), 필요 시 belt_servo(취소 처리) |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | BRD TR-VOICE-05 "멈춰는 진행 중 동작을 안전하게 중단", 8.1 7단계 "멈춰 → 로봇 정지". track_and_grasp 취소는 추종 중에만 통하고, move_to_zone(적재·복귀) 중에는 로봇을 멈출 경로가 없음 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | topics.md(robot_gateway 행), sort_manager, belt_servo, TBD-017, VT-053 |
| 대안·이행 방법·기존 기능/일정 영향 | 표준 타입이라 voss_msgs 변경 없음. topics.md 먼저 수정 → interface 라벨 → 남현지 승인. 대안: move_to_zone을 action으로 바꿔 cancel 사용(변경 범위 더 큼) |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 남현지·박병후 의견 미수신 / 제안 |

#### NEW-R-05 — 관측 자세 이동 경로(`zone="observe"`)

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-05 · 김학민 / 계약 수정(허용값 추가) |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | IC-ROBOT-03, IC-R-02 / SYS-FR-013·SYS-FR-018 관련 |
| 변경 전 내용 / 변경 후 내용 | 전: MoveToZone `zone` ∈ {A,B,C,recheck,hold}, 항상 놓기 동작 포함. 후: `zone="observe"`(slot 0)를 추가 — 그리퍼를 움직이지 않고 observe_pose로만 이동 |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | BRD 8.1 1단계 "작업 시작 → 관측 자세로 이동", 재개·파지 실패 후 복귀에도 필요. 지금 계약으로는 sort_manager가 로봇을 관측 자세로만 보낼 방법이 없음 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | voss_msgs.md(MoveToZone 설명), sort_manager, TBD-016·018 |
| 대안·이행 방법·기존 기능/일정 영향 | 필드 변경 없이 허용값만 추가. 대안: `/voss/robot/go_observe`(Trigger) 별도 서비스 |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 남현지 의견 미수신 / 제안 |

#### NEW-R-06 — 로봇 상태 토픽(`/voss/robot/state`)

| 항목 | 변경 제안 |
|---|---|
| 제안 ID·담당 / 수정·추가·삭제·ID 변경 | NEW-R-06 · 김학민 / 계약 추가 |
| 대상 SYS/IC/VT·카드 ID / 이전→새 ID 대응 | 신규(IC-ROBOT-02 옆) / SYS-FR-001·SYS-FR-031(4) 로봇 상태·SYS-FR-034 관련 |
| 변경 전 내용 / 변경 후 내용 | 전: 로봇 상태를 알리는 토픽 없음. 후: `/voss/robot/state` — 상태 `READY / MOVING / STREAMING / STOPPED / ERROR / DISCONNECTED` + 사유 문자열, 변경 시 + 1 Hz 발행, reliable·transient_local depth 1(제안). 타입은 std_msgs/String(JSON) 또는 voss_msgs 신규 — 남현지와 결정 |
| 꼭 필요한 이유·해결할 문제·변경하지 않을 때 영향 | BRD TR-SYS-03 HMI에 "로봇 상태" 표시가 있는데 원천이 없음. FR-001 준비 판단(NEW-R-01)에도 로봇·그리퍼 준비 신호가 필요 |
| 영향받는 파트·계약·코드·시험·TBD·문서 | topics.md, sort_manager, hmi_bridge(정의석), TBD-011·018 |
| 대안·이행 방법·기존 기능/일정 영향 | 대안: sort_manager가 SortState에 로봇 상태를 합쳐 HMI로 전달. B 기능이라 A 연결에는 READY만 먼저 |
| 관련 담당자 의견·미합의 / 검토·확정 상태 | 남현지·정의석 의견 미수신 / 제안 |

### 5.2 미정·의존 사항

| 관련 ID | 미정 내용·이유 | 결정 담당·예정일 | 다른 파트 영향·먼저 필요한 입력 | 제안 |
|---|---|---|---|---|
| TBD-015 / pending #9 | RG2 제어 경로 | 김학민 / 10/06 | #4 공존 시험 결과 | Modbus TCP 직접, ADR-0003 |
| TBD-014 / pending #8 | servol_stream vs move_line ASYNC | 박병후 / 10/06 | #3 결과 → gateway 스트리밍 구현 방식 | 결과 받는 대로 IC-R-03 갱신 |
| TBD-014 (문서 수정) | topics.md의 두산 스트리밍 경로 `/dsr01/servol_stream`이 소스 기준 `/dsr01/dsr_controller2/servol_stream`과 다름. speedl_stream(속도 명령)도 후보에 없음 | 김학민·박병후 / 10/06 | 박병후 #3 실기 확인(`ros2 topic list`로 실제 경로 확인) | 실기 확인 후 topics.md 경로 수정 PR(interface 라벨) |
| TBD-015·019 | 그리퍼 호출 주체·성공 판정 위치 | 박병후·남현지·김학민 / 10/07 | belt_servo·sort_manager 구현 | 닫힘·판정 = belt_servo, 놓기 = move_to_zone 안 |
| TBD-016 | zones·observe_pose 기준점(플랜지/TCP), slot 원점, hold 격자 | 김학민·남현지 / 10/06~08 | 캘리브레이션 기준, voss_config.md | 플랜지·구역 중심 기준, hold에 격자 추가 |
| TBD-001 (참고, 남현지) | 카메라 해상도: BRD 6.1은 RGB 1920×1080 30 fps인데 현 브링업·`realsense` 별칭은 1280×720 → 관측 20 cm에서 분류코드 약 20 px(1080p면 약 30 px) | 남현지 / 10/06 | #9 노출 스윕, OCR | 1080p 또는 관측 높이 15 cm |
| TBD-013 | 벨트 방향이 베이스 축과 틀어진 경우 표현 | 김학민·박병후 / 10/06 | #6-b 결과, 피드포워드 | direction_axis 대신 단위 벡터 |
| TBD-017·020 | servo_cmd 감시 시간, 속도·영역 상한, 최대 정지 지연 | 김학민·박병후 / 10/08 | T32 실기 | 실측 후 값 확정 |
| pending #10·#11 | 흐린 송장 방식·장수, 받는 사람 이름 | 김학민 / 10/07 | 남현지 OCR 시험 | BRD 2.4·8.1은 흐린 송장 **1장**(시연 5단계 박스 9, 역삼/청담 후보). 인쇄 초안은 번짐 처리 2장(S07-01) → 시연은 1장, 1장은 예비로 제안. 이름은 팀원 4명 |
| TBD-013·017 (배치) | 관측 자세(TR-PICK-01 상류 끝 위)와 작업자 투입 위치(NFR-10 상류 끝)가 겹칠 가능성 | 김학민·남현지 / 10/06 | #6 배치, 캘리브레이션 관측 자세 | 투입은 벨트 맨 상류 끝, 관측 자세는 하류 쪽으로 띄워 상류를 비스듬히 봄 |
| TBD-015 (드라이버) | BRD 6.1 RG2 드라이버 후보(ahnisinc/cobot_rg2)와 설치본(ABC-iRobotics/onrobot-ros2) 불일치 | 김학민 / 10/06 | #4 | Modbus 직접으로 가면 영향 없음, 드라이버로 가면 저장소 확정 |

## 6. 회신 전 확인

- [x] 내 담당 요구사항의 수용/수정/미정을 표시했습니다.
- [ ] 내 질문 ID의 각 답변을 채웠거나 미정/해당 없음과 이유를 적었습니다. (⏳ 실측 칸 남음)
- [x] 실제 데이터 예시·단위·식별·시간·실패 처리와 상대에게 필요한 정보를 적었습니다.
- [x] IC 커버리지 목록과 담당 VT 행에 카드 참조 또는 미정/미채택·이유를 연결했습니다.
- [x] 혼합 질문의 A 완료와 B 후속 미완료를 별도 표시했습니다.
- [x] 수정·추가·삭제가 꼭 필요한 경우 변경 카드와 해당 양식의 대체 내용을 작성하고 기존 ID·이력을 남겼습니다.
- [x] 시험 목표와 실측 결과를 구분했고, 미정 담당·기한을 적었습니다.
- [x] 선택 기능을 기본 전체 흐름의 선행조건으로 넣지 않았습니다.
- [x] 비밀번호·API 키 값·개인 연락처 등은 넣지 않았습니다.
