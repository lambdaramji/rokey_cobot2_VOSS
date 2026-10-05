스탠드업용 3줄 보고를 만들어라. 각 줄은 한 문장.

1. 어제(또는 마지막 세션) 한 것: `git log --since="1 day ago" --author="$(git config user.name)" --oneline` 기준.
2. 오늘 할 것: CLAUDE.local.md 의 이번 주 이슈와 docs/plan.md 의 오늘 날짜 작업 기준.
3. 막힌 것 / 다른 파트에 필요한 것: 인터페이스 미확정, 실측값 미기록, 리뷰 대기 PR 등.
