작업 시작 전 동기화. 순서대로 수행하고 마지막에 한 문단으로 요약해라.

1. `git fetch origin` 후 현재 브랜치에 `origin/main`을 리베이스한다. 충돌이 나면 멈추고 어떤 파일인지 보고한다.
2. `git log --since="3 days ago" --name-only --oneline -- docs/ src/voss_msgs/ config/` 로 최근 바뀐 문서·인터페이스·설정을 찾고, 바뀐 파일을 읽어 **내 담당 패키지에 영향 있는 변경**만 요약한다.
3. docs/interfaces/ 가 바뀌었다면 내 패키지 코드가 그 변경과 일치하는지 점검하고 불일치를 나열한다.
4. CLAUDE.local.md 의 "이번 주 이슈"를 `gh issue view <번호>` 로 확인해 상태를 요약한다 (gh 가 없으면 건너뛴다).
