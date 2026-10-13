# scripts/
- `voss_up.sh` / `voss_down.sh` (본체 `voss_up.py`) — 런북 T1~T8 + 음성 3노드 + hmi_bridge 를 순서대로 띄우고 단계마다 준비 로그를 기다린다, 종료는 역순(IDLE·PAUSED 에서만). `--print` 는 계획만, `--dry --playback <bag>` 은 로봇 없이(도메인 30 거부), `--real` 은 확인 질문 뒤. 로그·상태 `~/voss_data/run`. 사람이 비상정지 옆에서 실행 (남현지, T22 #31)
- `measure_1006/` — 10/06 실측 키트: 벨트 속도(`measure_belt_speed.py`), 버전·환경(`env_report.sh`), RG2(`rg2_check.py`), 좌표 교시(`record_pose.py`), 노출 스윕(`exposure_sweep.py`). 절차는 그 폴더 README (김학민, 10/06)
- `measure_1009/` — T32·T34 완료 기준 시험 (김학민, 10/09). 실로봇은 사람이 비상정지 옆에서.
  - `queue_soak.py` — MoveToZone 을 반복하며(기본 30분, 먼저 `--minutes 5`) gateway 큐·pose 끊김·RobotState 기록 (T32 #41 "move_line 큐 30분 무정지")
  - `grip_check.py` — RG2 만 닫기·열기 반복, 보고 폭·grip_detected·찌그러짐 입력 (T34 #43 "찌그러짐 없는 파지 10회", ADR-0009 15°·30°)
- `measure_1012/` — 3×2 트레이·재확인·팔레타이징(16칸) 시연: 칸 확인(`empty_test.sh`·`place_test.sh`·`pallet_test.sh`), 전체 실행 명령·결과는 그 폴더 README (로컬 브랜치 local/1012-recheck-flow, 10/12)
- `calib_check.py` — 핸드아이 검증점 오차 출력 (남현지, 10/06)
실로봇을 움직이는 스크립트는 상단 주석에 "사람이 비상정지 옆에서 실행" 을 적는다.
