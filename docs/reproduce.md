# 처음부터 다시 구현하기 — 재현 안내

프로젝트를 끝내며(2026-10-16) "이 레포만 보고 10/15 시연 시스템을 다시 세울 수 있게" 흩어진 정보를 한곳에 모은 문서다. 새 절차를 만들지 않고 **이미 있는 런북·설정을 어떤 순서로 보면 되는지**와 **레포 밖에 있어서 따로 준비해야 하는 것**을 적는다. 작성: 김학민(PC 초기화 전 정리).

## 1. 결과물

| 무엇 | 위치 |
|---|---|
| 최종 발표 PPT·전체 시연 영상·보고서 그림 | `docs/presentations/` (목록: `docs/presentations/README.md`) |
| 10/15 시연 결과 (값의 기준) | `docs/measurements-1015.md` |
| 시연 대본·판정 기록표 | `docs/demo-script.md` |

## 2. 코드 기준점

| 기준점 | 커밋 | 쓰는 곳 |
|---|---|---|
| 시연 빌드 (노드 PC) | 태그 `demo-20261015` = `25a726e` (브랜치 `15thOct11-10-nodespc-freezing`) | 10/15 시연과 **똑같이** 돌릴 때. 상세는 `docs/measurements-1015.md` 0절 |
| 시연 스냅샷 (웹 PC) | 브랜치 `15thOct11-10-webpc-freezing` (`a9debbb`) | 웹 PC. 시연 시점 커밋이 정확히 어느 것인지는 미확인(`measurements-1015.md` 5절) |
| 제출용 웹 PC 스냅샷 | 브랜치 `webpc-freezing-16thOct` (제출 zip = `43de1bd`, 브랜치 끝은 10/16 13:38 `b9e0abb`) | main 에 아직 없는 웹·AI·음성 변경 19커밋 |
| 최신 | `main` | 시연 뒤 바뀐 점: 2단계 판독 기본 켬(#181), J6 회전 파지(#167·#179, 노드 기본 off·실기 예시 on), servo 각속도 전달(#164, 기본 off), 시연 웹·음성 통합(#176) |

## 3. 외부 의존성 (버전)

| 항목 | 버전 | 받는 곳 |
|---|---|---|
| OS · ROS | Ubuntu 24.04, ROS 2 Jazzy, `rmw_cyclonedds_cpp`, Python 3.12 | `docs/setup/dev-environment.md` |
| 두산 드라이버 | `doosan-robot2_jazzy` **31750d6** | https://github.com/ROKEY-SPARK/doosan-robot2_jazzy (`docs/measurements-1006.md` #2) |
| 브링업 패키지 `m0609_rg2_bringup` | `m0609_rg2_integration` **e80512d** 의 `src/m0609_rg2_bringup` | https://github.com/ROKEY-SPARK/m0609_rg2_integration — `~/cobot2_ws/src/` 에 심볼릭 링크로 넣었다 |
| RG2 | `onrobot-ros2` **c6e3903** (VOSS 는 드라이버 대신 Modbus 직접 사용, ADR-0005) | https://github.com/ABC-iRobotics/onrobot-ros2 |
| RealSense | `ros-jazzy-librealsense2` 2.58.4, `ros-jazzy-realsense2-camera` 4.58.4 | apt (`docs/measurements-1006.md`) |
| 컨베이어 펌웨어 | `tools/arduino/conveyor_test` (`HALF_PERIOD_US = 250`, 4.77 cm/s) | 레포 |
| 모델 | 받을 가중치 없음 — 박스 검출은 OpenCV 분할(ADR-0011), Whisper·PaddleOCR 은 첫 실행 때 내려받음(인터넷 필요) | |

두산 오버레이는 `~/cobot2_ws` 에 위 세 개를 넣고 빌드한 뒤, VOSS 보다 먼저 source 한다(`docs/g0-runbook.md` 1-5 의 `~/voss_g0_env.sh`).

## 4. 레포 밖에서 준비할 파일

레포에는 템플릿만 있고 실제 값은 공용 PC·웹 PC에 있었다. **비밀값은 커밋하지 않는다.**

| 파일 | 템플릿 | 값의 근거 |
|---|---|---|
| `~/voss_ws/config/voss_config.yaml` | `config/voss_config.yaml` (그대로 복사) | 시연 사본 sha 앞 12자리 `844f45cfc0a2`. 레포 사본은 쓰지 않는 `pallet grid.order` 만 다르다(#52 `4ef1a1a`) |
| `~/voss_ws/config/hand_eye.yaml`, `belt_homography.yaml` | `config/` (그대로 복사) | 10/10~13 로그 sha 와 같다. 다시 구하려면 `docs/interfaces/calibration.md` |
| `~/voss_ws/config/belt_servo_real.yaml` | `src/voss_servo/config/belt_servo_real.yaml.example` | null 이 남아 있으면 belt_servo 가 READY 를 거부한다. 값: `docs/measurements-1012.md`·`1013.md`, `src/voss_servo/design/` 현장 분석 문서 |
| `~/voss_g0_env.sh` | — | `docs/g0-runbook.md` 1-5 에 전체 내용 |
| `docker/{ai,db,web,vision}/.env`, `deploy/node/.env` | 각 폴더 `.env.example` | OpenAI API 키·DB 비밀번호 등. 각 `docker/*/README.md` |
| Mosquitto 계정·ACL | `config/mosquitto.{conf,acl}.example`, `docker/mqtt/` | `docker/mqtt/README.md`, `docs/interfaces/mqtt.md` |
| CycloneDDS 설정 | — | 공용 PC `~/.config/cyclonedds/cyclonedds.xml`(인터페이스 lo·무선). 웹 PC 쪽은 `scripts/web_pc_voice.sh` 가 만든다 |
| 망 주소 | — | 로봇 컨트롤러 192.168.1.100:12345 (`scripts/measure_1012/README.md`). 나머지 주소는 현장 `.env` 와 비공개 런북에만 있다 |

## 5. 세우는 순서

1. **환경** — 3절 의존성 설치, `~/cobot2_ws` 빌드, 이 레포를 `~/voss_ws/src/` 에 clone 후 `colcon build --symlink-install`.
2. **실측·캘리브레이션** (작업대를 새로 꾸몄다면) — `docs/measurements-1006.md`(벨트·구역 좌표), `docs/interfaces/calibration.md`(관측 자세·카메라·핸드아이). 결과를 `config/` 와 `voss_config.yaml` 에 반영.
3. **노드 PC 단독 기동** — `docs/g0-runbook.md` (T1~T8 순서, PaddleOCR venv, DB, 시작 전 확인표) 또는 `scripts/voss_up.sh --real --print` 로 계획을 먼저 본다. 실기 기동은 사람이 비상정지 옆에서(CLAUDE.md 규칙 6).
4. **웹 PC** — `docker/db`·`docker/mqtt`·`docker/ai`·`docker/web` README 순서로 컨테이너를 올리고, 노드 PC 에서 SSH 포워드(8000·8080·1883·5432 …, `docs/interfaces/deployment_two_pc_trial.md`)를 연 뒤 `scripts/web_pc_voice.sh`.
5. **시연** — `docs/demo-script.md` 3절(시작 전) → 4절(단계별 대본) → 5절(기록표).

## 6. 알려진 공백 (2026-10-16 기준)

- 10/15 의 **두 PC 배치**(노드 PC + 웹 PC)를 처음부터 끝까지 적은 런북이 없다. `deployment_two_pc_trial.md` 는 아직 "제안" 상태이고, `g0-runbook.md` 는 공용 PC 한 대 기준이다. 4절의 조각을 이어 붙여야 한다.
- `docs/setup/dev-environment.md` 에 설치 명령이 비어 있다(두산·RealSense·Docker·NVIDIA).
- 웹 PC 로컬에만 있던 파일 4개(`voice_logo_local.py`, `test_voice_web_e2e.py`, 결과 txt 2개)는 레포에 없다(`docs/testing/voice_web_link.md`).
- 웹 PC 의 최종 상태(`webpc-freezing-16thOct`)는 main 에 머지되지 않았다. 웹 음성 경로의 stop 이중 경로는 ADR-0016 제안 단계.
- 멈춤·재개를 시연 속도(300 mm/s)에서 확인한 기록이 없다(`measurements-1015.md` 5절).
