# 개발 환경 (Ubuntu 24.04 + ROS 2 Jazzy)

개인 PC 4대와 공용 PC 모두 같은 구성. 세부 설치 명령은 환경 확인 후 김학민·남현지가 채운다.

## 공통
- Ubuntu 24.04 LTS, ROS 2 Jazzy (desktop), `rmw_cyclonedds_cpp`
- Python 3.12, `ruff`, `pytest`
- 워크스페이스: `~/voss_ws/src/rokey_cobot2_VOSS`
- `~/.bashrc` 예시
  ```bash
  source /opt/ros/jazzy/setup.bash
  source ~/voss_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export ROS_DOMAIN_ID=<팀 번호>   # 공용 PC와 같게. 개인 PC는 서로 다르게 (충돌 방지)
  ```

## 로봇 (공용 PC·브링업 담당)
- `doosan-robot2` (dsr_controller2), 컨트롤러 버전은 docs/measurements-1006.md #2
- 로봇 서브넷 유선 전용. RG2 Modbus TCP 192.168.1.1:502 (확인 필요)

## 비전 컨테이너
- 베이스 `ros:jazzy` 계열 + CUDA, YOLO, PaddleOCR(한국어). `docker/vision/`
- `--network host`, `config/` 읽기 전용 마운트, 같은 ROS_DOMAIN_ID

## 음성
- Whisper 로컬 (모델 크기 미정), LangChain + OpenAI (`OPENAI_API_KEY` 환경 변수), TTS 미정

## 개인 PC에서 로봇 없이 개발하기
- robot_gateway 는 `--ros-args -p dry_run:=true` 로 두산 서비스 대신 로그만 찍는 모드를 둔다 (김학민).
- box_tracker 는 녹화 영상 재생 모드를 둔다 (남현지). 녹화 파일은 레포 밖 `data/`.
- 이렇게 해야 4명이 로봇 한 대를 기다리지 않는다.
