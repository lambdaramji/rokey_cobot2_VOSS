# ADR-0001: 인터페이스 명명 규칙과 voss_msgs 단일 패키지

- 날짜: 2026-10-05
- 상태: 승인됨 (2026-10-06, Slack 투표 👍 4/4 완료. 승인 PR에서 LabelCrop·ReadLabel·ZoneMapEntry 확장 반영 → docs/interfaces 변경 이력)
- 결정자: 전원
- 관련: SR-IF-01~12, pending-decisions #1

## 배경
4개 파트가 10/13에 통합되려면 노드 간 이름이 처음부터 고정되어야 한다. 전 프로젝트(rokey_cobot1) 이름과 섞이면 혼란.

## 결정
- 토픽 `/voss/<영역>/<이름>`, 서비스·액션 `/voss/<영역>/<동사>`. 영역: voice, vision, sort, robot, servo, log (log 는 2026-10-06 추가 — sort_logger 상태·기록, SRD 상호확인 #52 MC-019).
- 커스텀 타입은 `voss_msgs` 하나. 필드는 docs/interfaces/voss_msgs.md 와 1:1.
- 두산 네이티브 토픽·서비스(`/dsr01/...`)는 robot_gateway 만 접근.

## 고려한 대안
- 패키지별 msg 패키지: 의존성이 거미줄이 됨.
- 네임스페이스로 노드 분리: 시연 환경이 1대라 불필요.

## 결과
docs/interfaces/topics.md 가 유일한 이름표. 변경은 `interface` 라벨 PR.
