# VOSS 프로젝트 지침 (팀 공유 — 모든 팀원의 Claude가 읽는다)

짧게 유지한다. 상세는 docs/ 를 가리킨다. 네 역할과 담당 이슈는 CLAUDE.local.md 에 있다.

## 프로젝트 한 줄
두산 M0609 + RG2 + 손목 D435i로 컨베이어 위 46×31×27 mm 박스를 추종·파지하고, 40×25 mm 송장의 분류코드/동 이름을 OCR로 읽어 5구역(역삼 A·대치 B·청담 C·재확인·보류)에 적재한다. 지시는 음성("헬로, 로키" → Whisper → OpenAI intent).

## 환경
- Ubuntu 24.04, ROS 2 Jazzy, CycloneDDS, Python 3.12. 워크스페이스 `~/voss_ws`, 이 레포는 `~/voss_ws/src/rokey_cobot2_VOSS`.
- 호스트: 두산 브링업, robot_gateway, belt_servo(30 Hz), sort_manager, 음성 3노드, hmi_bridge, sort_logger, Mosquitto.
- 컨테이너(GPU): box_tracker, label_reader. DB도 컨테이너. `--network host`, 같은 ROS_DOMAIN_ID.
- 구조·상태기계: @docs/architecture.md

## 절대 규칙
1. 커스텀 메시지는 `src/voss_msgs` 한 곳에만. 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 이름 목록: docs/interfaces/topics.md
2. 인터페이스(토픽·서비스·메시지 필드·voss_config.yaml·intent JSON·MQTT JSON)를 바꾸려면 **코드보다 먼저 docs/interfaces/ 를 고치고** PR에 `interface` 라벨을 붙인다. 다른 파트의 코드가 깨지는 변경이다.
3. 두산 로봇 서비스는 robot_gateway의 단일 호출 큐를 통해서만 부른다. 다른 노드가 `/dsr01/...`을 직접 호출하지 않는다.
4. D435i 깊이(depth)는 쓰지 않는다. RGB + 핸드아이 캘리브레이션 + 알려진 박스 높이(27 mm)로 위치를 구한다.
5. `voss_config.yaml`을 쓰는 노드는 sort_manager 뿐. 다른 노드는 `/voss/sort/zone_map` 토픽(transient_local)을 구독한다.
6. **실로봇·벨트·그리퍼를 움직이는 명령(launch, 서비스 호출, 스크립트)은 Claude가 실행하지 않는다.** 코드를 만들고 실행 명령을 보여주기만 한다. 실행은 사람이 비상정지 옆에서 한다.
7. 자기 담당 패키지 밖을 고쳐야 하면 먼저 사용자에게 알리고, 해당 담당자에게 이슈로 요청하는 쪽을 우선 제안한다.
8. 모델 가중치(.pt, .onnx), 녹음, 촬영 데이터는 커밋하지 않는다 (.gitignore 참고). 경로와 다운로드 방법만 README에 적는다.

## 자주 쓰는 명령
```bash
cd ~/voss_ws && colcon build --symlink-install --packages-select <pkg>   # 빌드
source install/setup.bash
colcon test --packages-select <pkg> && colcon test-result --verbose     # 테스트
ruff check src/rokey_cobot2_VOSS && ruff format --check src/rokey_cobot2_VOSS  # 린트
ros2 topic list | grep voss                                             # 인터페이스 확인
```

## 작업 시작 전
1. `/sync` (main 리베이스 + 최근 바뀐 docs 확인)
2. CLAUDE.local.md 의 담당 이슈와 docs/plan.md 의 이번 주 표를 본다.
3. 담당 패키지 디렉터리의 CLAUDE.md 를 읽는다 (패키지별 노드·인터페이스·완료 기준).

## PR 전 (`/pr` 커맨드가 수행)
빌드·테스트·린트 통과 → 인터페이스 변경 시 docs/interfaces 갱신 확인 → 설계 결정은 docs/adr → PR 템플릿대로 본문 작성.

## 일정의 핵심
10/06 실측 · 10/07 중간 점검 발표 · **10/10 게이트(추종 파지 성공률 70% 점검. 미달이어도 자동 전환 없이 게이트 회의에서 B안·범위 축소·A안 연장 중 결정, ADR-0002)** · 10/13 전체 루프 통합 · 10/15 시연 · 10/16 발표. 상세: docs/plan.md
