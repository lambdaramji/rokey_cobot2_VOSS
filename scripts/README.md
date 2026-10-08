# scripts/
- `bringup_host.sh` — 두산 브링업 → robot_gateway → belt_servo → sort_manager → 음성 → hmi_bridge → sort_logger 순 기동 (김학민·남현지, 10/11~13)
- `measure_1006/` — 10/06 실측 키트: 벨트 속도(`measure_belt_speed.py`), 버전·환경(`env_report.sh`), RG2(`rg2_check.py`), 좌표 교시(`record_pose.py`), 노출 스윕(`exposure_sweep.py`). 절차는 그 폴더 README (김학민, 10/06)
- `measure_1009/` — T32·T34 완료 기준 시험 (김학민, 10/09). 실로봇은 사람이 비상정지 옆에서.
  - `queue_soak.py` — MoveToZone 을 1시간 반복하며 gateway 큐·pose 끊김·RobotState 기록 (T32 #41 "move_line 큐 1시간 무정지")
  - `grip_check.py` — RG2 만 닫기·열기 반복, 보고 폭·grip_detected·찌그러짐 입력 (T34 #43 "찌그러짐 없는 파지 10회", ADR-0009 15°·30°)
- `calib_check.py` — 핸드아이 검증점 오차 출력 (남현지, 10/06)
실로봇을 움직이는 스크립트는 상단 주석에 "사람이 비상정지 옆에서 실행" 을 적는다.
