# voss_robot — 김학민 (@rokeyhak)
노드: robot_gateway. 두산 서비스 단일 호출 큐, /voss/robot/pose ~50 Hz 발행, /voss/robot/servo_cmd 구독 → speedl_stream (ADR-0010, PR #87. 발행 QoS reliable, 끊기면 gateway 가 정지 책임), 서비스 move_to_zone / gripper / teach_zone.
- 두산 `/dsr01/...` 을 부르는 코드는 이 패키지에만. 호출은 직렬 큐 하나.
- 타임아웃 난 요청은 cancel 하지 않고 늦은 응답을 기다린 뒤 다음을 보낸다(`doosan.GuardedCaller`, 컨트롤러 쪽 요청 겹침 방지). 응답 없음 3회 연속(`max_call_misses`)이면 FAULT — 두산 호출을 멈추고 gateway 재시작으로 푼다. move_stop 은 큐 밖 별도 경로.
- 작업 영역 리밋·속도 상한을 여기서 강제 (다른 노드 명령을 믿지 않는다).
- `dry_run:=true` 모드: 두산 없이 로그만. 개인 PC 개발용.
- RG2: Modbus TCP 직접 vs onrobot 드라이버 → pending-decisions #9. 파지력은 measurements #8.
- 구역 좌표는 voss_config.yaml zones. 격자 오프셋(slot) 계산은 순수 함수 + pytest.
- 실로봇 실행은 사람이 비상정지 옆에서.
