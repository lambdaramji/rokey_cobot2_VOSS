# 개발 규칙

## 브랜치·커밋·PR
- `main`: 항상 빌드 통과. 직접 푸시 금지 (브랜치 보호).
- 브랜치: `<type>/<이슈번호>-<패키지>-<설명>` 예) `feat/12-servo-feedforward`, `fix/31-ocr-fuzzy`
- type: feat, fix, docs, refactor, test, chore
- 커밋: `<type>(<패키지>): <요약> (#이슈)` 예) `feat(voss_servo): add belt speed feedforward (#12)`
- PR 하나 = 이슈 하나. 300줄 이내 권장. 브랜치 수명 2일 이내 (일정이 2주라 더 짧게).
- 머지: squash merge. 조건: CI(`build-test`) 통과 + CODEOWNERS 승인 1. `main` 보호 규칙은 관리자(PL)에게도 적용된다.
- 리뷰 순서: ① Claude 자동 리뷰(PR에 `@claude` 멘션) → ② 동료 1명 → ③ 인터페이스·voss_msgs·ADR 변경 시 PL.
- `@claude` 는 PL 의 Claude 구독으로 돈다. 네 명의 호출이 같은 사용 한도를 쓰므로 PR 하나에 몰아서 요청한다. 설정: `.github/workflows/claude.yml` (#8)
- CODEOWNERS는 경로마다 2명이다(작성자는 자기 PR을 승인할 수 없다). 두 번째 오너는 인터페이스가 맞물리는 사람이다. 표는 `.github/CODEOWNERS`.
- docs/interfaces·voss_msgs·config·docs/adr 는 PL과 김학민이 오너지만, 작성자가 PL이 아니면 PL이 승인한다. PL이 작성한 PR만 김학민이 승인한다. (CODEOWNERS로는 강제되지 않는 약속)
- 매일 작업 끝에 자기 브랜치를 PR로 올린다. 미완성이면 Draft PR. "나중에 한 번에"는 없다.

## ROS 2
- 패키지는 `voss_<영역>`, 노드 이름은 docs/interfaces/topics.md 의 이름 그대로.
- 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 네임스페이스 없이 절대 경로.
- 커스텀 msg/srv/action은 `voss_msgs` 에만. 표준 메시지로 되면 표준을 쓴다.
- QoS: 센서·서보 스트림은 best_effort depth 1~5, 상태·zone_map은 reliable + transient_local.
- 파라미터는 launch 파일에서 넘긴다. 하드코딩된 좌표·속도 금지 → `config/voss_config.yaml` (sort_manager) 또는 패키지 파라미터 YAML.
- 두산 서비스는 robot_gateway 단일 큐로만. 두산 서비스 호출과 voss_config 의 pose 는 두산 posx (mm, deg), ROS 표준 메시지(geometry_msgs)는 SI (m, rad, m/s). 변환은 robot_gateway 가 한다. 표는 docs/interfaces/voss_config.md 값 규칙.

## Python
- Python 3.12, `ruff` (설정은 루트 `pyproject.toml`). 타입 힌트 권장.
- 노드 하나 = 파일 하나. 로직은 노드와 분리해 순수 함수로 두고 pytest 로 시험한다 (퍼지 매칭, 타이밍 계산, 상태 전이 등).
- 외부 API 키는 환경 변수 (`OPENAI_API_KEY`). 코드·YAML에 넣지 않는다.

## 실기 안전
- CI는 실기를 돌리지 않는다. 실로봇·벨트·그리퍼 시험은 사람이 비상정지 옆에서.
- 로봇 동작 코드 PR은 "실기 확인" 칸에 확인자·일시·결과를 적어야 머지.
- 작업 영역 리밋·속도 제한은 robot_gateway 에서 강제하고, 다른 노드는 믿지 않는다.

## 문서
- 인터페이스: 문서 먼저, 코드 나중. PR에 `interface` 라벨.
- 결정: docs/adr/ 한 파일. 미결정 목록(docs/pending-decisions.md)에서 지운다.
- 실측값: docs/measurements-1006.md 에만. 다른 문서는 이 파일을 참조.

## 일일 루틴
1. `/sync` → 2. 담당 이슈 작업 → 3. `/pr` → 4. 리뷰 요청 → 5. `/standup` 으로 3줄 보고
스탠드업 10분: 오늘 건드릴 이슈, 인터페이스 변경 예정, 막힌 것만.
