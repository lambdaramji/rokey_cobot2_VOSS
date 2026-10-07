# scripts/
- `bringup_host.sh` — 두산 브링업 → robot_gateway → belt_servo → sort_manager → 음성 → hmi_bridge → sort_logger 순 기동 (김학민·남현지, 10/11~13)
- `measure_1006/` — 10/06 실측 키트: 벨트 속도(`measure_belt_speed.py`), 버전·환경(`env_report.sh`), RG2(`rg2_check.py`), 좌표 교시(`record_pose.py`), 노출 스윕(`exposure_sweep.py`). 절차는 그 폴더 README (김학민, 10/06)
- `calib_check.py` — 핸드아이 검증점 오차 출력 (남현지, 10/06)
실로봇을 움직이는 스크립트는 상단 주석에 "사람이 비상정지 옆에서 실행" 을 적는다.
