# VOSS 레포 스타터 키트 — 적용 순서

레포: https://github.com/yujh5537/rokey_cobot2_VOSS (현재 README 하나)

## 0. 이 키트가 무엇을 담고 있나
- `CLAUDE.md` — 팀 공유 지침. 모든 팀원의 Claude Code 가 자동으로 읽음 (절대 규칙 8개, 명령, 일정 핵심)
- `src/*/CLAUDE.md` — 패키지별 지침 (담당·노드·인터페이스·완료 기준). 그 폴더에서 작업할 때만 로드됨
- `CLAUDE.local.md.example` — 개인 역할 템플릿 (4명분)
- `.claude/commands/` — `/sync` `/pr` `/standup`
- `.claude/settings.json` — Claude 가 `ros2 launch/run`, `docker compose up`, `git push main` 을 못 하게 deny
- `docs/interfaces/` — **파트 간 계약** (SRD 9장 제안을 그대로 옮김). 10/05 확정 대상
- `src/voss_msgs/` — 계약과 1:1 인 msg/srv/action 파일 (실제 빌드 가능)
- `src/voss_*` — 7개 ament_python 패키지 골격 (노드 파일·entry point·smoke test)
- `docs/plan.md`, `pending-decisions.md`, `measurements-1006.md`, `adr/0001·0002` — 일정·결정·실측
- `.github/` — PR 템플릿, 이슈 템플릿 3종, CODEOWNERS, CI (ros:jazzy 컨테이너에서 ruff + colcon build/test + 인터페이스 문서 검사)

## 1. 레포에 넣기 — PL, 10/05 (30분)
1. 키트 내용을 레포 루트에 복사 (기존 README.md 는 키트 것으로 교체). 첫 커밋: `chore: project skeleton, interfaces, docs (#1)`
2. `.github/CODEOWNERS` 는 4명 GitHub 아이디로 채워져 있음 (yujh5537 / EuiseokJeongNZ / ok778ts123 / rokeyhak). 경로마다 2명 (작성자는 자기 PR을 승인할 수 없으므로, #2). 3명을 레포 Collaborator 로 초대
3. GitHub → Settings → Branches → `main` 보호 규칙 (CODEOWNERS 2인 구성이 main 에 들어간 뒤에 건다)
   - Require a pull request before merging (승인 1)
   - Require status checks: `build-test`
   - Require review from Code Owners
   - Do not allow bypassing (관리자 포함)
4. Labels 추가: `interface`, `task`, `decision`, `bug`, `hardware`
5. Claude Code GitHub Actions 설치 (PR 에서 `@claude` 리뷰, #8). 워크플로는 `.github/workflows/claude.yml`
   - Claude GitHub App 을 이 레포에만 설치: https://github.com/apps/claude
   - 인증은 PL 구독 OAuth 토큰: 로컬 터미널에서 `claude setup-token` → `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R yujh5537/rokey_cobot2_VOSS` 에 붙여넣기. 토큰은 채팅·파일에 남기지 않는다
   - 멘션할 때만 돈다(모든 PR 자동 리뷰 없음). 레포에 쓰기 권한이 있는 사람만 호출할 수 있다
6. BRD 를 Markdown 으로 내보내 `docs/requirements/` 에, `VOSS_개발일정.xlsx` 도 같은 폴더에 (완료 #4). SRD 와 시스템 아키텍처 SVG 는 박병후 담당 (#6)

## 2. 팀원 온보딩 — 각자, 10/05 (15분)
1. `git clone` → `cp CLAUDE.local.md.example CLAUDE.local.md` → 자기 블록만 남기고 이번 주 이슈 번호 기입
2. Claude Code: 레포 루트에서 실행 → `/sync` 동작 확인
3. claude.ai 채팅만 쓰는 사람: claude.ai 프로젝트에 `CLAUDE.md` + `docs/` 전체 + 자기 패키지 `CLAUDE.md` 를 프로젝트 지식으로 추가. docs 가 바뀌면 다시 올린다
4. 첫 PR 연습: 자기 패키지 README 한 줄 수정 → PR → CI → 리뷰 → squash merge. 10/05 안에 4명 전원

## 3. 10/05 저녁까지 결정할 것 (docs/pending-decisions.md #1)
- docs/interfaces/topics.md, voss_msgs.md 승인 (또는 수정 PR). 이게 안 되면 10/06 이후 병렬 개발이 흔들린다
- 배정(추종·파지=박병후, 로봇 제어·환경 설정=김학민)과 분류코드 매핑(01 역삼 / 02 대치 / 03 청담)은 확정 반영됨

## 4. 운영 루틴
- 매일: `/sync` → 이슈 작업 → `/pr` → 리뷰 → squash merge → `/standup`
- 실측·결정이 나올 때마다: measurements-1006.md / pending-decisions.md / adr 갱신 (PR 템플릿 체크박스)
- 10/08 저녁 게이트 1차 측정, 10/10 게이트 판정 → ADR-0002 갱신
