# voss_bringup — 김학민 (@rokeyhak) + 남현지 (@lambdaramji)
launch 파일과 파라미터. 호스트 전체 기동 `voss_host.launch.py`, 비전 컨테이너용 `voss_vision.launch.py`, 개발용 `voss_dry_run.launch.py`.
- 기동 순서: 두산 브링업 → robot_gateway → belt_servo → sort_manager → 음성 3노드 → hmi_bridge → sort_logger.
- 툴/TCP 등록 스크립트, 카메라 노출·화이트밸런스 고정 파라미터도 여기.
- ros2 launch 는 Claude 가 실행하지 않는다.
