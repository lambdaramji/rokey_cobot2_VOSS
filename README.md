# rokey_cobot2_VOSS
[ROKEY BOOT CAMP 9기_C3] AI 기반 협동 로봇 작업 어시스턴트 구현 프로젝트

**VOSS** — 자연어 지시 기반 물류 분류 어시스턴트.
사용자가 "헬로, 로키" 호출 후 음성으로 지시하면, 두산 M0609가 컨베이어 위를 흐르는 미니 택배 박스를 추종·파지하고, 송장의 분류코드(`S07-02` 형식)와 동 이름을 OCR로 읽어 역삼동·대치동·청담동 구역에 적재한다.

| 항목 | 내용 |
|---|---|
| 기간 | 2026-10-05 ~ 10-16 (시연 10/15, 발표 10/16) |
| 팀 | C-3조: 남현지(@yujh5537, PL) · 정의석(@EuiseokJeongNZ) · 박병후(@ok778ts123) · 김학민(@rokeyhak) |
| 환경 | Ubuntu 24.04 · ROS 2 Jazzy · CycloneDDS · Python 3.12 · doosan-robot2 |
| 문서 | `docs/` (BRD·SRD 요약, 인터페이스 계약, 일정, 결정 기록) |

## 빠른 시작
```bash
# 개발 환경: docs/setup/dev-environment.md
cd ~/voss_ws && git clone https://github.com/yujh5537/rokey_cobot2_VOSS.git src/rokey_cobot2_VOSS
colcon build --symlink-install && source install/setup.bash
```

## 개발 규칙 (요약)
- `main` 직접 푸시 금지. 이슈 번호가 붙은 브랜치 → PR → CI + 리뷰 → squash merge.
- 노드 간 약속(토픽·서비스·메시지·YAML·JSON)은 코드보다 `docs/interfaces/`가 먼저다.
- Claude Code 사용 시 레포 루트의 `CLAUDE.md`가 자동으로 읽힌다. 자세한 규칙은 `docs/conventions.md`.
