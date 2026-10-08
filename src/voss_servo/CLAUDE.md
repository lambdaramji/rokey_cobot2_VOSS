# voss_servo — 박병후 (@ok778ts123)
노드: belt_servo. /voss/vision/box + /voss/robot/pose → /voss/robot/servo_cmd (TwistStamped) 30 Hz. 액션 /voss/servo/track_and_grasp 제공.
- A안 폐루프: 베이스 좌표 오차(BoxTrack.position_base − TCP) → 속도 명령 + 벨트 속도 피드포워드(FF+P) (voss_config belt.speed_cmps). B안 개루프 동기 추종은 같은 액션 인터페이스로 구현해 sort_manager 가 모르게 전환.
- 하강·파지 타이밍: 사전 개방 90 mm, 31 mm 폭 파지(46 mm 변 = 벨트 방향, ADR-0009). latency_offset_ms 로 튜닝.
- 안전: 속도 한계·작업 영역은 robot_gateway 가 강제하지만 여기서도 clamp.
- 실로봇 실행은 사람이. Claude 는 코드와 실행 명령만.
- 게이트 10/10: 20회 중 14회. 시도별 로그(성공/실패/원인) 는 `data/` 에, 집계만 ADR-0002 에.
- 두산 경로 speedl_stream(ADR-0010), 실측 measurements-1006 #3.
- 설계 노트: 결정 카드는 DESIGN.md, 단위별 설계(HLD · DD · pseudo)는 design/U1-{hld,dd,pseudo}.md.
