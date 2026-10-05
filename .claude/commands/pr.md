현재 브랜치를 PR로 올릴 준비를 해라. 커밋·푸시·PR 생성은 내가 확인한 뒤에만 한다.

1. `colcon build --symlink-install --packages-select <내 패키지>` 와 `colcon test`, `ruff check`, `ruff format --check` 를 실행하고 실패를 고친다.
2. `git diff origin/main --stat` 과 내용을 보고 다음을 판정한다.
   - src/voss_msgs, config/voss_config.yaml, intent JSON, MQTT JSON 중 하나라도 바뀌었나? → 바뀌었으면 docs/interfaces/ 의 해당 문서가 같이 바뀌었는지 확인하고, 안 바뀌었으면 갱신한다. PR 본문 "인터페이스 변경"에 적고 `interface` 라벨을 붙이라고 알려 준다.
   - 설계 결정(제어 방식, 모델 선택, DB 종류 등)이 있었나? → docs/adr/ 에 ADR 초안을 추가한다. docs/pending-decisions.md 에 같은 항목이 있으면 "결정"으로 바꾼다.
   - 실측값이 바뀌었나? → docs/measurements-1006.md 갱신.
3. 실로봇으로 확인한 내용이 있으면 PR 본문 "실기 확인"에 누가·언제·결과를 적도록 빈칸을 남긴다 (Claude가 채우지 않는다).
4. .github/PULL_REQUEST_TEMPLATE.md 형식으로 PR 본문 초안을 보여 준다. 제목은 `type(pkg): 요약 (#이슈)`.
