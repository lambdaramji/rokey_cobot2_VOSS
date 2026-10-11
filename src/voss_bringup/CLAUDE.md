# voss_bringup — 김학민 (@rokeyhak) + 남현지 (@lambdaramji)
launch 파일과 파라미터 (T22 #31). 실행은 사람이 한다 — ros2 launch 는 Claude 가 실행하지 않는다.
- `voss_host.launch.py`: 호스트 전체(런북 T2~T8 + 음성 3노드 + hmi_bridge). **기본 dry_run:=true**(가짜 로봇·RG2). `dry_run:=false` 는 실기 — T1 두산 브링업(외부 패키지·컨트롤러 IP, 공개 레포에 안 적음)을 먼저, 비상정지 옆에서. camera·logger·voice·hmi 는 `auto` = 실기일 때만. 비전은 기본 컨테이너(`docker/vision`), 호스트로는 `with_vision:=true`.
- `voss_vision.launch.py`: box_tracker + label_reader 묶음(컨테이너를 못 쓸 때 호스트 대체, voss_host·voss_dry_run 이 부름).
- `voss_dry_run.launch.py`: 로봇 없이 소프트웨어 전체 루프 — 녹화 재생(`playback_restamp`) → OCR → sort_manager → TrackAndGrasp → gateway dry_run(가짜 PLACE). g0_mock `--log` 로 LOG 준비. TrackAndGrasp 는 기본 `servo:=mock`(g0_mock `--servo`) — 고정 카메라 녹화로는 진짜 belt_servo 가 박스를 화면에 붙잡지 못해 LOST(10/11), `servo:=sim` 은 진짜 belt_servo(sim 파라미터)로 PREPARE·TRACK 확인. **도메인 30 이면 기동 거부.**
- 기동 순서(런북 g0-runbook 2절): 두산 브링업(T1) → robot_gateway(T2, `pose_source:=joint_states`) → 카메라(T3) → sort_logger(T4, sort_manager 보다 먼저) → 비전(T5·T6) → belt_servo(T7) → sort_manager(T8) → 음성 3노드 → hmi_bridge. 운전 시작은 sort_manager 준비 판단(ROBOT·SERVO·VISION·OCR·LOG)이 막는다.
- 끄는 순서: belt_servo 를 gateway 보다 먼저(끊기면 watchdog 이 정지) — 런북 7장.
- 카메라 노출·화이트밸런스 고정값은 `voss_host.launch.py` `CAMERA_PARAMS`(런북 T3 10/08 확인 명령). 툴/TCP 등록 스크립트도 여기(학민).
- 순수 함수(`host_plan`·`dry_run_host_args`·`refuse_operating_domain`)와 "넘기는 인자가 대상 launch 에 선언돼 있는지"는 `test/test_launch.py`.
