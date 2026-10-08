# docs/ 안내

| 파일/폴더 | 용도 | 누가 고치나 |
|---|---|---|
| architecture.md | 노드 구성, 배포 구성, 상태기계 | PL. 변경은 ADR 동반 |
| conventions.md | 브랜치·커밋·PR·ROS·Python 규칙 | 팀 합의 후 PL |
| interfaces/ | **파트 간 계약**: 토픽·서비스·메시지, intent JSON, MQTT JSON, voss_config.yaml | 해당 노드 담당자가 제안, PL 승인 |
| plan.md | 마일스톤, 파트별 작업, 게이트 기준 | PL (엑셀 일정표와 동기) |
| pending-decisions.md | 팀이 정해야 할 항목 (SRD 16장) | 담당자가 결정 후 갱신 |
| measurements-1006.md | 10/06 실측 체크리스트와 결과 | 측정한 사람 |
| g0-runbook.md | 10/10 G0 실행 절차(전제·공용 PC 준비·기동 순서·확인·증거·문제 대응) | PL |
| adr/ | 설계 결정 기록 | 결정한 사람 |
| setup/ | 개발 환경 구성. `drive.md` = 팀 Google Drive 구조·규칙(원본·데이터셋·모델·결과 위치) | 김학민·남현지 / drive.md: PL |
| requirements/ | BRD·SRD (Claude Docs에서 Markdown으로 내보낸 사본), 개발일정 xlsx, 시스템 아키텍처 그림 | BRD·개발일정: PL / SRD·`architecture/` 그림: 박병후 |

규칙 두 가지.
1. 코드와 문서가 다르면 **문서가 틀린 것**으로 보고 같은 PR에서 고친다.
2. 인터페이스는 **문서 → 코드** 순서. docs/interfaces/ 를 먼저 고치고 그다음 voss_msgs와 노드를 바꾼다.
