# voss_servo — 박병후 (@ok778ts123)
노드: belt_servo. /voss/vision/box + /voss/robot/pose → /voss/robot/servo_cmd (TwistStamped) 30 Hz. 액션 /voss/servo/track_and_grasp 제공.
- A안 폐루프: 픽셀 오차 → 속도 명령 + 벨트 속도 피드포워드 (voss_config belt.speed_cmps). B안 개루프 동기 추종은 같은 액션 인터페이스로 구현해 sort_manager 가 모르게 전환.
- 하강·파지 타이밍: 사전 개방 90 mm, 46 mm 면을 벨트 방향으로. latency_offset_ms 로 튜닝.
- 안전: 속도 한계·작업 영역은 robot_gateway 가 강제하지만 여기서도 clamp.
- 실로봇 실행은 사람이. Claude 는 코드와 실행 명령만.
- 게이트 10/10: 20회 중 14회. 시도별 로그(성공/실패/원인) 는 `data/` 에, 집계만 ADR-0002 에.
- 10/06: servol_stream 유무 → docs/measurements-1006.md #3, 제어 경로 → pending-decisions #8
