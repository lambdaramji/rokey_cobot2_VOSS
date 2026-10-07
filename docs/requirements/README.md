# 요구사항 문서

BRD·SRD 원본은 Claude Docs(공유 편집). 버전이 바뀔 때 Markdown 으로 내보내 여기에 사본을 둔다. 이 폴더의 사본은 직접 고치지 않는다. 원본을 고친 뒤 다시 내보내 교체한다.

| 파일 | 내용 | 담당 | 판 | 올린 날 |
|---|---|---|---|---|
| `VOSS_BRD.md` | 비즈니스 요구사항 (v1.1 사본. v1.2 로 교체 예정) | 남현지 | 2026-10-03 (Claude Docs 내보내기) | 2026-10-05 |
| `VOSS_BRD_v1.2.docx` | 비즈니스 요구사항 **v1.2 (기준판, #51 MC-034 PL 결정)**. 원본 Word 그대로. Markdown 사본(`VOSS_BRD.md`)은 아직 v1.1 이라 원본 담당이 다시 내보내 교체한다 | 남현지 | v1.2 (2026-10-06) | 2026-10-06 (김학민) |
| `VOSS_개발일정.xlsx` | 일정(간트) · 마일스톤 · 10/06 실측 체크리스트 · 미결정 항목 4개 시트 | 남현지 | 2026-10-05 | 2026-10-05 |
| `VOSS_SRD.md` | 시스템 요구사항 | 박병후 | — | 미반영 (#6) |
| `architecture/` | 시스템 아키텍처 그림: VOSS_logic.svg, VOSS_deploy.svg | 박병후 | — | 미반영 (#6) |

- BRD 사본의 `[embedded content: …]` 자리는 내보내기에서 빠진 그림이다(논리 구성도, 배포 구성도, 개발 일정). 그림은 `architecture/`에 올린다.
- docx 도 Claude Code 가 바로 읽지 못한다. 기준판이 바뀌면 Markdown 사본을 같은 PR 이나 바로 다음 PR 에서 맞춘다.
- xlsx 는 Claude Code 가 바로 읽지 못한다. 일정의 텍스트판은 `docs/plan.md`, 실측 항목은 `docs/measurements-1006.md`, 미결정 항목은 `docs/pending-decisions.md` 이고, xlsx 가 바뀌면 이 세 파일도 같은 PR 에서 맞춘다.

개발 중 참조하는 요약은 docs/architecture.md, docs/interfaces/ 이고, 수치의 근거가 필요할 때 여기를 본다.
