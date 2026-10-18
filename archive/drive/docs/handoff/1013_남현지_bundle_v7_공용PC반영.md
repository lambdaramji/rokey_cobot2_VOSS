# voss_1013_v7.bundle — 공용 PC 반영 안내 (10/13, 남현지)

> **v7 을 쓴다(BRD v1.5).** v6 에 **게이트 판정 B 대비**를 더했다 — sort_manager 파라미터 `pallet_layers`(기본 2 = 지금과 같음, 1 = 1층 8칸만)와 판정별(A~D) 대본·문서 수정안. v5 에 더해 게이트 준비(S2-T13): 기록표 행 도구 `voss_manager.pallet_gate`, v1.5 게이트 절차·ADR-0014 판정 문구, 검증 보고서 갱신. voss_msgs·gateway·웹은 v5 와 같다. sort_manager 는 기본값에서 동작이 같다.

GitHub 계정 정지로 push 가 안 돼서 브랜치를 git bundle 파일 하나로 묶었다. **아직 아무도 리뷰하지 않은 코드**다. 계정이 풀리면 브랜치별 PR 로 다시 리뷰한다.

- 파일: `voss_1013_v7.bundle` (5.5 MB, 전체 이력 — 공용 PC 에 무엇이 있든 그대로 받을 수 있다)
- sha256 앞 16자리: `e895b35da31c3ce2`
- 로봇을 움직이는 명령(launch·서비스 호출·`voss_up.sh --real`)은 사람이 비상정지 옆에서 실행한다(CLAUDE.md 규칙 6).

## v5 → v7 에서 바뀐 것
| 브랜치 | 끝 커밋 | 내용 |
|---|---|---|
| **`integ/1013-gate-v15`** | 78844e5 | v5(807d54b) + 아래 브랜치들. **공용 PC 는 이것 하나만 빌드한다** |
| feat/s2-t13-voss_manager-pallet-layers (v7 새) | ca2704f | sort_manager `pallet_layers: 1` = 1층 칸 1·2·5·6·9·10·13(+14) 만, 용량 8 — 게이트 판정 B(2층 놓기를 시연에서 뺄 때). 기본 2 는 지금과 같다 |
| feat/s2-t13-voss_manager-pallet-gate-summary (새) | b1d3901 | `python3 -m voss_manager.pallet_gate <녹화>` → sprint2-gate.md §5 기록표 12열 + 박스별 상세(계획 칸·놓은 칸·#37 당겨 놓음·시도·박스당 s) |
| docs/s2-t13-demo-script-gate | 6fa0502 | 게이트 전제 첫 줄 v1.5(`cols` 없음·PalletState), 웹 HMI 전제, 녹화에 `/voss/voice/say`·`intent`, 6번 기록표 도구, ADR-0014 근거 칸·판정 문구 A~D·판정 뒤 문서 수정안, 대본 §6 판정별 표(B = 역삼 1층 7개 문장·칸), pending #31(D3)·#33(D5), plan D3 문구 |
| verify/palletizing | 7aa5891 | 보고서: TR-PAL-01 웹 입력·10 ④ 3D 구현(공용 PC 확인 전), B5(웹 PALLETIZING) |
| feat/s2-t16-voss_vision-boxtrack-yaw | 017331a | **통합에 안 넣음.** yaw 에 더해 box_tracker 벨트 영역 hull(J6 로 카메라가 돌면 송장을 자르던 문제)·J6 측정 도구 `tools/calib/j6_yaw_eval.py` |

개인 PC 에서 `integ/1013-gate-v15`(78844e5)를 따로 빌드해 확인했다: bringup 27, hmi 66(7 건너뜀), manager 145, robot 100, servo 243, vision 114, voice 159, 웹 백엔드 58·프런트 12(v5 와 같은 코드) — 실패 0, ruff 통과. `pallet_gate` 는 합성 녹화(mcap)로 읽기까지 확인했다. 공용 PC 실기는 아직이다.

## 받기 (공용 PC, 레포 `~/voss_ws/src/rokey_cobot2_VOSS`)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS
git status                                    # 바뀐 파일이 있으면 먼저 commit 또는 stash (지우지 않는다)
sha256sum ~/Downloads/voss_1013_v7.bundle     # e895b35da31c3ce2… 로 시작하는지
git bundle verify ~/Downloads/voss_1013_v7.bundle
git fetch ~/Downloads/voss_1013_v7.bundle 'refs/heads/*:refs/remotes/bundle1013/*'
git switch integ/1013-gate-v15 2>/dev/null && git merge --ff-only bundle1013/integ/1013-gate-v15 \
  || git switch -c integ/1013-gate-v15 bundle1013/integ/1013-gate-v15
```
- v4~v6 으로 이미 `integ/1013-gate-v15` 를 만들었으면 첫 줄(fast-forward)로 올라간다.
- 학민 쪽에 아직 push 못 한 브랜치(S2-T02·T03·T21 등)가 있으면 그 위에서 `git merge <그 브랜치>`. 정의석 웹 #22 의 더 새 커밋도 같이(App.tsx·CommandController 겹칠 수 있음).

## 빌드·준비
```bash
cd ~/voss_ws && colcon build --symlink-install    # voss_msgs 는 v4·v5 와 같다
source install/setup.bash
```
- v4 안내의 DB 마이그레이션·Mosquitto ACL·비전 컨테이너·AI 컨테이너, v5 안내의 웹 이미지 재빌드는 그대로다(했으면 다시 안 해도 된다).

## 게이트(18:00) — `docs/sprint2-gate.md`
1. §2 전제 확인 — 첫 줄은 `ros2 interface show voss_msgs/msg/PalletState` 에 `slot_dong`, MoveToZone 에 `cols` **없음**.
2. §3 녹화(토픽에 `/voss/voice/say`·`/voss/voice/intent` 추가됨) → palletize(사람이 비상정지 옆에서).
3. §3 6번: `python3 -m voss_manager.pallet_gate ~/voss_data/1013/s2gate_pal --out ~/voss_data/1013/s2gate_rows.md` → 사람 칸(입력·실물·밀림·DB 행)을 채워 §5 에 붙인다. 판정 열은 "완주 후보"까지만 나온다.
4. 판정 뒤 ADR-0014 의 문구 A~D 중 하나를 남기고, "판정 뒤 문서 수정안" 표대로 plan·pending·대본 §6 을 고친다.
5. **판정 B 면** 리허설 전에 `src/voss_manager/config/sort_manager.yaml` 의 `pallet_layers: 1` → sort_manager 다시 기동(로그 "팔레트 1층 8칸만"), 단계 9 는 "역삼동 실어줘"(대본 §6 B).

## 기동 확인 (계획만 — 아무것도 띄우지 않는다)
```bash
source ~/voss_g0_env.sh
scripts/voss_up.sh --real --print
```
실제 기동은 비상정지 담당이 자리에 있을 때 `scripts/voss_up.sh --real`(두산 브링업이 이미 떠 있으면 `--skip T1`). 필요한 환경 변수: `VOSS_ROBOT_HOST`(컨트롤러 IP — 레포·Slack 에 적지 않는다), `VOSS_DB_LOGGER_PASSWORD`. 끌 때 `scripts/voss_down.sh`.

## 되돌리기
v6 으로: `git switch integ/1013-gate-v15 && git reset --keep 2ee1828`, v5 로: `… --keep 807d54b` 뒤 `colcon build --symlink-install`. main 으로: `git switch main`.
