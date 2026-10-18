# voss_1013_v4.bundle — 공용 PC 반영 안내 (10/13, 남현지)

> **v4 를 쓴다(BRD v1.5).** v1·v2(`voss_1012*.bundle`)는 팔레타이징이 v1.4(9칸 1단)다. v3 에 더해 v4 에는 pending #37 결정(1층 칸 박스가 FAILED 면 그 위 2층 박스를 빈 1층 칸에 당겨 놓기)과 검증 보고서(`verify/palletizing`)가 들어 있다.

GitHub 계정 정지로 push 가 안 돼서 브랜치를 git bundle 파일 하나로 묶었다. **아직 아무도 리뷰하지 않은 코드**다. 오늘(10/13) 게이트 실기를 위해 공용 PC 에서 같은 코드로 빌드하려는 것이고, 계정이 풀리면 브랜치별 PR 로 다시 리뷰한다.

- 파일: `voss_1013_v4.bundle` (5.5 MB, 전체 이력 — 공용 PC 에 무엇이 있든 그대로 받을 수 있다)
- sha256 앞 16자리: `6d195367d268e4e0`
- 로봇을 움직이는 명령(launch·서비스 호출·`voss_up.sh --real`)은 사람이 비상정지 옆에서 실행한다(CLAUDE.md 규칙 6).

## 들어 있는 브랜치
| 브랜치 | 끝 커밋 | 내용 |
|---|---|---|
| **`integ/1013-gate-v15`** | fef3153 | **아래 전부를 main(c90623f) 위에 합친 통합 브랜치 — 공용 PC 는 이것 하나만 빌드한다** (v2 의 `integ/1013-gate` 와 다른 이름) |
| feat/31-docker-vision | 1ba5ab4 | 비전 컨테이너 (#159) |
| feat/31-bringup-launch | 23c49c1 | voss_host·voss_vision·voss_dry_run launch (#161) |
| feat/31-voss-up-script | b233718 | `scripts/voss_up.sh`·`voss_down.sh` |
| docs/sprint2-v1.4 → docs/sprint2-v1.5 | 08b7675 → 559592d | BRD v1.4 → v1.5, 개발일정·plan·pending |
| feat/s2-t01 → t04 → t05 | c80ce3e → b6df6ed → 71fff8f | v1.4 팔레타이징 (기록용 — v15 가 대체) |
| **feat/s2-v15-palletizing** | 6c2881d | v1.5 인터페이스(94126e3)·pallet_plan(4118dde)·PALLETIZING(6c2881d) |
| feat/s2-t07-voss_hmi-pallet-log | 2c85b7f | sort_logger: `sort_log.slot`·`pallet_log`·ListPlacements, voss_hmi 시험 수집 고침 |
| feat/s2-t08-voss_hmi-pallet-bridge | b3cc33a | hmi_bridge: palletize 명령·`voss/pallet/state`·ACL 예시 |
| feat/s2-t06-voss_voice-palletize-intent | c25ae5c | 음성 palletize route, FastAPI 스키마 |
| docs/s2-t13-demo-script-gate | 4f420b5 | 시연 대본 v2(20개), 게이트 절차(D3 제안), ADR-0014, pending #36·#37 |
| feat/29-voss_manager-start-voice | 956a54f | start 때 "작업을 시작합니다." |
| feat/s2-t05-pull-down-layer2 | d8c1d78 | pending #37: FAILED 1층 칸 위 2층 박스를 빈 칸에 당겨 놓기 |
| verify/palletizing | c7b43d4 | 팔레타이징 검증 시험·보고서 `docs/verification/palletizing_report.md`(S1~S8·불변식 500회·실기 체크리스트) |

개인 PC 에서 `integ/1013-gate-v15` 를 따로 빌드해 8개 패키지 빌드·시험을 확인했다(bringup 27, hmi 64, manager 104, robot 100, servo 243, vision 114, voice 153 — 실패 0, ruff 통과). 공용 PC 실기는 아직이다.

## 받기 (공용 PC, 레포 `~/voss_ws/src/rokey_cobot2_VOSS`)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS
git status                                    # 바뀐 파일이 있으면 먼저 commit 또는 stash (지우지 않는다)
sha256sum ~/Downloads/voss_1013_v4.bundle     # 6d195367d268e4e0… 로 시작하는지
git bundle verify ~/Downloads/voss_1013_v4.bundle
git fetch ~/Downloads/voss_1013_v4.bundle 'refs/heads/*:refs/remotes/bundle1013/*'
git switch -c integ/1013-gate-v15 bundle1013/integ/1013-gate-v15
```
학민 쪽에 아직 push 못 한 브랜치(S2-T02·T03·T21 등)가 있으면 그 위에서 `git merge <그 브랜치>` 로 합친다.

## 빌드·준비
```bash
cd ~/voss_ws && colcon build --symlink-install    # voss_msgs 가 바뀌어 호스트 패키지 전부 다시 (MoveToZone 해시는 main 과 같다)
source install/setup.bash
```
- 빌드 중 `voss_bringup` 이 "can't copy … launch/voss_*.launch.py" 로 실패하면 다른 브랜치 빌드가 남긴 깨진 링크다 — `find build/voss_bringup install/voss_bringup -xtype l -delete` 뒤 다시.
- **DB 마이그레이션**(sort_logger 를 끈 뒤 한 번, `docker/db/README.md` "마이그레이션" 절). v2 에서 이미 적용했다면 **v1.5 pallet_log 는 열이 다르다** — `pallet_log` 가 비어 있으면 `DROP TABLE pallet_log;` 뒤 마이그레이션을 다시(정의석과 확인). 적용 전 DB 면 sort_logger 가 slot 없이 쓰며 "마이그레이션 필요" 경고를 낸다.
- **Mosquitto ACL**: `config/mosquitto.acl.example` 처럼 bridge 에 `topic write voss/pallet/state`, web 에 `topic read voss/pallet/state` 를 더한다.
- **비전 컨테이너**: 비전 메시지 해시는 그대로지만 box_tracker 코드가 바뀌었으니 이미지를 다시 만든다(`docker/vision/README.md`).
- **AI 컨테이너**(정의석): FastAPI 스키마에 palletize·`route` — 이미지를 다시 만들고 `python3 src/voss_voice/test/eval_real_intent.py --cases palletize`(8/8, OpenAI 비용).
- **팔레타이징 실기 전제**: A·B·C 트레이 8·8·6칸(D1, S2-T21), `zones.pallet` 교시 4×2×2(S2-T02), gateway PICK(A·B·C)·DROP(2층 +27 mm)·PALLET slot 0~15(S2-T03). 교시 전에는 sort_manager 가 palletize 를 거부한다.

## 기동 확인 (계획만 — 아무것도 띄우지 않는다)
```bash
source ~/voss_g0_env.sh
scripts/voss_up.sh --real --print
```
실제 기동은 비상정지 담당이 자리에 있을 때 `scripts/voss_up.sh --real`(두산 브링업이 이미 떠 있으면 `--skip T1`). 필요한 환경 변수: `VOSS_ROBOT_HOST`(컨트롤러 IP — 레포·Slack 에 적지 않는다), `VOSS_DB_LOGGER_PASSWORD`. 끌 때 `scripts/voss_down.sh`.

## 되돌리기
`git switch main` 뒤 `colcon build --symlink-install`. DB 마이그레이션은 열·표를 더하기만 한다.
