# Sprint 2 게이트 — 10/13(화) 18:00, 공용 PC

> **기준 (BRD v1.5 10.2·결정 D3 — 전원 결정 전 제안):** 팔레타이징은 **결정 D3 기준으로 실기 1회 완주**, 음성 시스템 기동은 **실기 1회 성공**. D3 이 정해지기 전에는 아래 "D3 제안"으로 판정한다(16칸 2층 완주는 일이 많고 최대 약 8분이라 10/14 리허설에서 확인). 못 미친 기능은 시연에서 빼고(팔레타이징은 1개 동 경로로 줄일 수 있다), 남은 시간은 1~9장 리허설에 쓴다. 판정은 PL, 기록은 ADR-0014.
>
> **로봇·벨트·그리퍼를 움직이는 명령은 모두 사람이 비상정지 옆에서 실행한다**(CLAUDE.md 규칙 6). 역할·비상정지·벨트 정지 담당과 기동 순서는 `docs/g0-runbook.md` 그대로다. 로봇 시간이 겹치면 1~9장 원래 기능(리허설·재확인 흐름)이 먼저다(BRD 10.2 우선순위).

## 1. 판정 정의 (측정 중 바꾸지 않는다)
| 항목 | 정의 |
|---|---|
| 팔레타이징 회차 | 분류 세션으로 박스를 A·B·C 에 놓은 뒤 보낸 `palletize` 1회. **D3 제안**: 경로 1개 동(역삼), 대상 8개 → 칸 0~7 = 1열·2열의 1층 4칸 + **2층 4칸**(구현 순서: 열마다 1층 2칸 → 2층 2칸). BRD 의 예시 "1층 8칸 + 2층 1칸"은 구현된 채우기 순서와 달라 같은 의도(2층 포함, 16칸보다 짧게)로 바꿨다. 16칸·3개 동(시연 단계 9, 시나리오 S8)은 10/14 리허설 |
| 팔레타이징 완주 | 계획된 박스 **전부** PalletResult `DONE`(PICK 재시도 포함) **그리고** 실물이 계획 칸에 놓임(1열 = 왼쪽 트럭 머리, 2층은 1층 위에 안정) **그리고** 옆 박스 밀림 0 **그리고** `pallet_log` 행 수 = 박스 수(초과·경로 제외가 있으면 그 행 포함) **그리고** 관측 자세 복귀·"팔레트 적재를 마쳤습니다" |
| 팔레타이징 미완주 | `FAILED` 가 하나라도 있음, 사람이 박스를 손으로 고침, 비상정지, 칸이 계획과 다름, 2층 박스가 기울거나 떨어짐. 원인은 표에 남긴다. 게이트 시각 전까지 다시 해도 되고 모든 회차를 남긴다. 1층 박스가 FAILED 면 그 위 2층 박스는 빈 1층 칸에 놓인다(pending #37 결정) — FAILED 가 있으니 미완주이고, 당겨 놓은 박스가 실물로 그 칸에 놓였는지 함께 적는다 |
| 입력 경로 | 음성(S2-T06)·HMI(S2-T08)·`ros2 service call` 모두 인정하고 표에 적는다 — 게이트는 팔레타이징 동작을 판정한다 |
| 음성 기동 성공 | ROS 스택이 꺼진 상태에서 "헬로, 로키. 시스템 켜줘" → 확인 "응" → 기동 순서 0~6(BRD 10.6) → "준비를 마쳤습니다" **그리고** `SortState.ready=true` **그리고** 그동안 로봇이 움직이지 않음 **그리고** 사람이 터미널을 만지지 않음 |
| 음성 기동 시간 | 명령 → "준비를 마쳤습니다" 를 잰다(NFR-16 3분은 실측 후 조정 — 게이트 판정에는 쓰지 않는다) |

## 2. 전제 — 게이트 전에 돼 있어야 하는 것
GitHub 계정 정지(10/12)로 머지가 막히면 공용 PC 는 같은 브랜치(또는 git bundle)로 빌드하고, 쓴 커밋 해시를 기록표에 적는다.

| 항목 | 담당 | 확인 |
|---|---|---|
| Sprint 2 인터페이스(S2-T01, v1.5) — voss_msgs 재빌드: 호스트 voss_voice·manager·hmi·robot 함께(비전 컨테이너는 해시 그대로라 재빌드 불필요). v1.5 에서 MoveToZone `cols` 는 뺐다(해시 main 과 같다) | 남현지 | `ros2 interface show voss_msgs/msg/PalletState` 에 `slot_dong`, `ros2 interface show voss_msgs/srv/MoveToZone` 에 `cols` **없음** |
| DB 마이그레이션 `docker/db/migrations/20261012_sprint2_pallet.sql` | 정의석 | `\d pallet_log`, `sort_log.slot` |
| sort_logger: `slot` 기록·`pallet_log`·`/voss/log/list_placements`(S2-T07) | 정의석 | `ros2 service list \| grep list_placements` |
| 팔레트 교시 `zones.pallet.pose`·16칸 2층 ikin·베이스 재측정(S2-T02), X·Y 피치·개방 폭(pending #23), **A·B·C 트레이 8·8·6칸(D1, S2-T21)** | 김학민 + 남현지 | voss_config 값, measurements |
| gateway PICK(A·B·C 칸)·`PALLET` slot 0~15 + `DROP`(2층 +27 mm)·관절 경유점(S2-T03, D2 — `cols` 없음) | 김학민 | 게이트 8칸(1·2열, 2층 4칸) DROP 각 1회, 밀림 0 |
| sort_manager PALLETIZING(S2-T05) | 남현지 | 로그 "팔레트 교시 됨", 단독 시험 통과 |
| voss_launcher·기동 프로필(S2-T09·T10) | 정의석 + 김학민 | 수동 기동과 같은 launch·환경 파일 |
| 웹 HMI(S2-T08 웹 쪽) — 웹 이미지 재빌드, Mosquitto ACL `voss/pallet/state`(bridge write·web read), `.env` `VOSS_MQTT_ENABLED=true` | 정의석 + 남현지 | HMI 04 패널에 3D 팔레트·집계가 뜬다(재생 확인은 `scripts/integration/README.md` S2-T08, sort_manager 끈 상태) |
| 시연 박스 구성(pending #19) | 전원 | 대본 §2 |

## 3. 순서 — 팔레타이징
1. g0-runbook 2절 순서로 기동(또는 음성 기동 회차 뒤 그대로). sort_manager 로그에 **"팔레트 교시 됨"**이 있어야 한다(없으면 palletize 를 받지 않는다).
2. 녹화 시작.
```bash
mkdir -p ~/voss_data/1013
ros2 bag record -s mcap -o ~/voss_data/1013/s2gate_pal --include-hidden-topics \
  /voss/sort/state /voss/sort/result /voss/pallet/state /voss/pallet/result \
  /voss/robot/pose /voss/robot/state /voss/log/status /voss/voice/say /voss/voice/intent /rosout
```
3. 트레이·팔레트가 비었는지 눈으로 확인 → `start` → 역삼 송장 박스 8개를 차례로 투입해 A 에 8칸 PLACED(**트레이 8칸 = 결정 D1 반영 뒤** — 3칸이면 4번째에서 "구역 가득" PAUSED). 3개 동 16칸 리허설은 대본 §2 의 20개.
4. 벨트 위 박스가 없고 SortState 가 RUNNING·`box_id=""` 일 때(비상정지 담당 준비 확인 뒤):
```bash
ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: palletize, arg: '역삼동'}"
```
5. 끝나면 확인:
```bash
ros2 topic echo /voss/pallet/state --once        # state DONE, done 8, slot_state 앞 8칸 DONE, overflow_warning false
docker compose -f ~/voss_ws/src/rokey_cobot2_VOSS/docker/db/compose.yml exec db psql -U voss_admin -d voss -c \
  "SELECT box_id, dong, route_index, zone, slot, pallet_slot, pallet_col, pallet_layer, pallet_lane, result, reason, attempts, finished_at FROM pallet_log ORDER BY finished_at;"
```
6. 기록표 행 만들기(녹화를 멈춘 뒤, 로봇과 무관 — 여러 회차를 한 번에):
```bash
python3 -m voss_manager.pallet_gate ~/voss_data/1013/s2gate_pal --out ~/voss_data/1013/s2gate_rows.md
```
   시각·경로·박스 수·DONE·FAILED(원인)·명령 칸 = 계획 칸(2층 수·당겨 놓음)·기대 pallet_log 행·박스당 최대 s 가 채워지고, 판정 열은 "완주 후보"까지만 나온다. **입력 경로, 실물 칸·2층 안정, 밀림, DB pallet_log 행(5번 SQL)은 사람이 채운다.** HMI 04 패널의 칸·집계가 pallet_log 와 같은지도 함께 본다(S2-T08 확인 — 판정에는 쓰지 않는다).
7. 다시 하려면 사람이 팔레트를 비우고 `stop` → `reset_zone PALLET` → (박스를 트레이로 되돌렸으면 새 `start` 부터).

## 4. 순서 — 음성 시스템 기동
정의석 S2-T09·T10 의 절차를 따른다. ROS 스택을 모두 끈 상태(DB·AI 컨테이너만)에서 시작하고, 비상정지 담당이 자리에 있을 때 "응"이라고 답한다. 실패하면 launcher 가 말한 단계 이름·원인을 적고 수동 기동으로 돌아간다(TR-VOICE-16).

## 5. 기록표
**팔레타이징** — 커밋 해시 ______ , voss_config sha256 ______

| 회차 | 시각 | 입력 | 경로 | 박스 수 | DONE | FAILED(원인) | 계획 칸대로(2층 포함) | 밀림 | pallet_log 행 | 박스당 최대 s (NFR-15 ≤ 30) | 판정 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | 역삼 (D3 제안) | | | | | | | | |
| 2 | | | | | | | | | | | |

**음성 시스템 기동**

| 회차 | 시각 | 명령 → 준비 완료 s | 실패 단계·원인 | 로봇 움직임 없음 | 터미널 손댐 없음 | 판정 |
|---|---|---|---|---|---|---|
| 1 | | | | | | |

## 6. 18:00 판정·회의
| 팔레타이징 | 음성 기동 | 시연 단계 |
|---|---|---|
| 완주 1회 이상 | 성공 1회 이상 | 0~9 전부 |
| D3 기준 완주 없음, 1층만 완주(2층 실패) 기록 있음 | — | 9 를 1층만 쓰는 1개 동 경로로 줄임 — 2층 놓기는 시연에서 뺀다 |
| 완주 없음, 1개 동도 없음 | — | 9 제외 |
| — | 성공 없음 | 0 제외(수동 기동) |

- 미달이어도 게이트를 미루지 않는다 — 10/14 는 전체 리허설(단계 0~9) 3회다(BRD 10.2 일정).
- 회의 뒤 PL 이 ADR-0014 "판정"·`docs/plan.md` 10/13 줄·시연 대본 §6·pending #19 를 갱신하고 Slack 에 올린다.

## 변경 이력
- 2026-10-12: 초안 (S2-T13). BRD v1.4 10.2·10.8 기준, 판정 정의·전제·순서·기록표·판정 표.
- 2026-10-13: **BRD v1.5** — 팔레타이징 기준을 결정 D3 제안(1개 동 8칸, 2층 4칸 포함 — 구현 채우기 순서에 맞춤)으로, 완주 정의에 2층 안정·초과/경로 제외 행 포함, pallet_log 조회 열(slot·열·층·줄), 트레이 8칸(D1) 전제.
- 2026-10-13 오후: 전제 첫 줄을 v1.5 로(`cols` 없음·PalletState 확인), 웹 HMI 전제, 녹화에 `/voss/voice/say`·`intent`, 기록표 행 도구 `voss_manager.pallet_gate`(6번), #37 당겨 놓기 기록.
