# voss_1013_v5.bundle — 공용 PC 반영 안내 (10/13, 남현지)

> **v5 를 쓴다(BRD v1.5).** v4 에 더해 v5 의 `integ/1013-gate-v15` 에는 **웹 HMI 3D 팔레트(S2-T08 웹 쪽)** 와 검증 보고서(`verify/palletizing`)가 합쳐져 있다. 웹은 **정의석 `feat/22-web-hmi-initial`(#22, 머지 전) 위에** 올렸으므로 그 웹 코드도 함께 들어 있다. S2-T16 BoxTrack yaw 는 **브랜치로만** 넣었다(통합 X — 아래 "yaw").

GitHub 계정 정지로 push 가 안 돼서 브랜치를 git bundle 파일 하나로 묶었다. **아직 아무도 리뷰하지 않은 코드**다. 계정이 풀리면 브랜치별 PR 로 다시 리뷰한다.

- 파일: `voss_1013_v5.bundle` (5.5 MB, 전체 이력 — 공용 PC 에 무엇이 있든 그대로 받을 수 있다)
- sha256 앞 16자리: `c618fd012217e2f1`
- 로봇을 움직이는 명령(launch·서비스 호출·`voss_up.sh --real`)은 사람이 비상정지 옆에서 실행한다(CLAUDE.md 규칙 6).

## v4 → v5 에서 바뀐 것
| 브랜치 | 끝 커밋 | 내용 |
|---|---|---|
| **`integ/1013-gate-v15`** | 807d54b | v4(fef3153) + `verify/palletizing` + 아래 웹 두 브랜치. **공용 PC 는 이것 하나만 빌드한다** |
| docs/s2-t08-web-pallet-api | dad0b94 | `web_api.md`: SSE `pallet_state`, `palletize` route 검사, `reset_zone PALLET`, SortState `PALLETIZING` 수용 (문서 먼저) |
| feat/s2-t08-web-pallet-3d | 089f5c2 | 정의석 #22 웹(8c009dd) 위: Spring Boot `voss/pallet/state` 구독·SSE·명령 검사·**PALLETIZING 수용**(없으면 팔레타이징 중 3초 뒤 UNKNOWN), React 팔레트 패널(경로 입력·3D 4×2×2·위에서 본 칸 표·실을 수/초과/경로 제외·경고·진행률), 재생기·DOM 관측 |
| feat/s2-t16-voss_vision-boxtrack-yaw | 413cc70 | **통합에 안 넣음.** BoxTrack `yaw_base`·`yaw_valid`(TR-SERVO-04). 타입 해시가 바뀐다 |

나머지 브랜치(feat/31-*, docs/sprint2-*, feat/s2-t01~t08, feat/s2-v15-palletizing, feat/s2-t05-pull-down-layer2, docs/s2-t13, feat/29, verify/palletizing)는 v4 와 같다.

개인 PC 에서 `integ/1013-gate-v15`(807d54b)를 따로 빌드해 확인했다: bringup 27, hmi 66(7 건너뜀), manager 133, robot 100, servo 243, vision 114, voice 159, **웹 백엔드 58, 웹 프런트 12** — 실패 0, ruff 통과, 프런트 빌드 통과. 공용 PC 실기·웹 컨테이너 기동은 아직이다.

## 받기 (공용 PC, 레포 `~/voss_ws/src/rokey_cobot2_VOSS`)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS
git status                                    # 바뀐 파일이 있으면 먼저 commit 또는 stash (지우지 않는다)
sha256sum ~/Downloads/voss_1013_v5.bundle     # c618fd012217e2f1… 로 시작하는지
git bundle verify ~/Downloads/voss_1013_v5.bundle
git fetch ~/Downloads/voss_1013_v5.bundle 'refs/heads/*:refs/remotes/bundle1013/*'
git switch integ/1013-gate-v15 2>/dev/null && git merge --ff-only bundle1013/integ/1013-gate-v15 \
  || git switch -c integ/1013-gate-v15 bundle1013/integ/1013-gate-v15
```
- v4 로 이미 `integ/1013-gate-v15` 를 만들었으면 위 첫 줄(fast-forward)로 올라간다.
- 학민 쪽에 아직 push 못 한 브랜치(S2-T02·T03·T21 등)가 있으면 그 위에서 `git merge <그 브랜치>`.
- **정의석 웹:** 공용 PC 에 #22 웹 브랜치의 더 새 커밋이 있으면 그 브랜치를 `integ/1013-gate-v15` 에 merge 한다(App.tsx·CommandController 에서 겹칠 수 있다 — 정의석과 같이).

## 빌드·준비
```bash
cd ~/voss_ws && colcon build --symlink-install    # v4 와 같다 (voss_msgs 변경 없음)
source install/setup.bash
```
- v4 안내의 DB 마이그레이션·Mosquitto ACL(`voss/pallet/state`)·비전 컨테이너·AI 컨테이너 항목은 그대로다(v4 에서 했으면 다시 안 해도 된다).
- **웹 컨테이너(정의석 또는 담당자가 실행)**: Spring Boot·React 가 바뀌었으니 이미지를 다시 만든다 — `docker/web/README.md` "공용 PC 배포"(`.env` 의 `VOSS_MQTT_ENABLED=true`). 확인용 시험: `cd docker/web/backend && ./gradlew test`, `cd docker/web/frontend && npm ci && npm test && npm run build`.
- **3D 화면 재생 확인·반영 ≤ 1초(S2-T08 완료 기준)**: `scripts/integration/README.md` "S2-T08" — `sort_manager` 를 끈 상태에서 `python3 scripts/integration/s2_pallet_replay.py` + 브라우저 콘솔 `s2_pallet_dom_observer.js`. 화면용 `/voss/pallet/state` 만 발행하고 로봇 명령은 없다.

## yaw (S2-T16) — 오늘 게이트 뒤에
`feat/s2-t16-voss_vision-boxtrack-yaw` 는 BoxTrack 끝에 필드를 더해 **타입 해시가 바뀐다**. 호스트와 비전 컨테이너 중 한쪽만 바꾸면 `/voss/vision/box` 가 연결되지 않으므로 팔레타이징 게이트 뒤, 박병후·김학민 확인 후에 `integ` 에 merge → 호스트 `colcon build` + 비전 이미지 재빌드를 **같이** 한다. belt_servo 는 아직 yaw 를 읽지 않는다(관측 기록용). J6 0·15·30·45° 오차 실측은 남현지(10/14).

## 기동 확인 (계획만 — 아무것도 띄우지 않는다)
```bash
source ~/voss_g0_env.sh
scripts/voss_up.sh --real --print
```
실제 기동은 비상정지 담당이 자리에 있을 때 `scripts/voss_up.sh --real`(두산 브링업이 이미 떠 있으면 `--skip T1`). 필요한 환경 변수: `VOSS_ROBOT_HOST`(컨트롤러 IP — 레포·Slack 에 적지 않는다), `VOSS_DB_LOGGER_PASSWORD`. 끌 때 `scripts/voss_down.sh`.

## 되돌리기
v4 로: `git switch integ/1013-gate-v15 && git reset --keep fef3153` 뒤 `colcon build --symlink-install`(웹 이미지는 이전 것으로). main 으로: `git switch main`.
