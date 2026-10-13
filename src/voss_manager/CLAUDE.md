# voss_manager — 남현지 (@lambdaramji)
노드: sort_manager. 상태 IDLE → RUNNING → PICKING → RECHECK → ASKING → PAUSED (docs/architecture.md).
- voss_config.yaml 을 읽고 쓰는 **유일한** 노드. 바뀌면 /voss/sort/zone_map 재발행 (transient_local).
- 상태 전이는 순수 함수 (상태, 이벤트) → (다음 상태, 액션) 로 두고 pytest 로 6상태 전이를 시험한다.
- 로봇은 /voss/servo/track_and_grasp 액션과 /voss/robot/* 서비스로만. 두산 직접 호출 금지.
- OCR 신뢰도 < confidence_min → 재확인 구역 → 재판독 → 미확정이면 ASKING(음성 질문) → 응답 없으면 보류.
- 완료 기준: 6상태 단독 시험 통과, 흐린 송장 박스 완주 3회, 사이클 ≤ 30초.

## 구조 (T20 1차, #29)
- `sort_fsm.py` 순수 전이 `step(ctx, event) → Out(ctx, actions, reply)`. `readiness.py` 준비 판단. `sort_manager.py` 는 입출력·장비 호출 시간 초과만(단일 스레드 executor, 잠금 없음).
- 파라미터 `config/sort_manager.yaml`, voss_config 는 `config_path`(launch `config_dir`, 기본 `VOSS_CONFIG_DIR` → 레포 `config/`). 어긋난 설정은 기동 거부.
- 로봇 없이 시험: `tools/mock/g0_mock.py` (belt_servo·gateway·logger·비전 대역, 아무것도 움직이지 않음).
- `pallet_plan.py` 팔레타이징 배치 계획(S2-T04, **BRD v1.5** 10.4): 팔레트 4열 × 2줄 × 2층 = 16칸 고정, slot = (열−1)×4 + (층−1)×2 + (줄−1)(결정 D2). 대상 16개 이하면 전부, 넘으면 물량 많은 순(동률이면 먼저 방문하는 동이 후순위)으로 `allocate()` — 못 실은 박스는 OVERFLOW, 경로 밖 동은 EXCLUDED(`Plan.unloaded`, 원래 칸에 그대로). 위치는 수량과 따로 마지막 방문 동부터 slot 0 → 15(열 단위, 열 안 1층 2칸 → 2층 2칸, 같은 층 1줄 → 2줄 — D6 제안). 한 동의 일부만 실을 때는 (구역, 칸) 앞의 박스부터(명세 미정). **2층 트레이(voss_config grid `layers` ≥ 2 → `Config.layer_cells`)는 구역 안에서 위층 박스부터 집는다**(`tray_layer_cells`, 10/13 게이트 — 칸 6 이 칸 0 위). 일부만 실으면 아래층이 남는다. 1층 트레이는 칸 순서 그대로. 같은 구역·칸에 PLACED 가 둘이면(세션 중 reset_zone) 나중 것만. 재개는 다시 계획하지 않고 `remaining()`. 시험 = 정답 생성기·S1~S8·불변식 500회(`test/test_pallet_plan.py`).

## 운용 규칙 (T20, SRD F-04/06/07·T23 확정 전 값은 제안)
- **분류 결정:** RUNNING 에서 OBSERVE 도착 뒤 촬영된 stage 1 판독으로 정한다. 확실(분류코드 우선, 동 이름과 같고 `confidence ≥ ocr.confidence_min`)하면 목적 구역으로 바로 집는다. 한 번에 한 박스.
- **불확실:** 후보가 하나도 없거나(UNKNOWN, 글자를 못 읽음) LOW_CONF·코드와 동 이름 불일치면 **집어서 재확인 구역**(빈 칸, 최대 2)으로. UNKNOWN 도 첫 판독에서 바로 집는다 — OCR 한 번 ≈ 2 s 라 다음 판독을 기다리면 박스가 지나간다(10/12 실기, 로컬 시험 브랜치 변경 — 담당 확인 전). 재확인에서도 모르면 전체 동을 후보로 묻는다. 추종 중 stage 2 판독이 확실하면 재확인 대신 목적 구역으로 바꾼다.
- **재확인(RECHECK):** 재확인 칸에 놓기 → `MoveToZone(RECHECK, VIEW)` → `/voss/vision/read_label`(stage 3) → 확실하면 `decided_by=RECHECK` → `MoveToZone(RECHECK, 칸, PICK)` → 목적 구역 PLACE. VIEW·ReadLabel 실패(서비스 없음·시간 초과 포함)나 불확실하면 질문.
- **질문(ASKING):** 후보 최대 2동(+ 보류), 문장은 `SortState.pending_question` 과 `/voss/voice/say`. 답은 `answer <box_id>|<동 또는 HOLD>` — 다른 box_id 는 거부, 후보가 아닌 답은 1회만 재안내(타이머 유지). 답 = `OPERATOR`, HOLD 답 = HELD·OPERATOR. **30 s 무응답 = HOLD·HELD·`NONE`·`NO_ANSWER`**(`ask_timeout_s`). 질문 중 stop → 타이머 멈춤, resume → 다시 묻고 30 s 새로.
- **재확인 실패:** PICK 실패 = 박스는 재확인 칸에 둔 채 HELD(zone RECHECK, reason DEVICE_ERROR·STOPPED) + PAUSED — 칸은 `reset_zone RECHECK` 로 비운다(처리 중 박스가 칸에 있으면 거부). 목적 구역이 가득이면 박스를 재확인 칸에 둔 채 PAUSED → reset_zone → resume 하면 PICK 부터.
- **재확인 흐름 중 stop:** 응답을 PAUSED 에서 받고, resume 하면 멈춘 단계부터 — VIEW·판독 중이었으면 VIEW 다시, PICK 뒤였으면 목적 구역 PLACE.
- **start 를 접수하면 "작업을 시작합니다."**(`/voss/voice/say`, BRD 8.1 1단계 — 거부·운전 중 전체 전환은 말하지 않는다). **start·resume 은 먼저 `MoveToZone(OBSERVE)`**(`home_first`), 도착 시각부터의 판독만 쓴다. PLACE 응답 뒤에도 그 시각부터 다시 관측.
- **파지 실패(GRASP_FAILED·LOST·OUT_OF_REACH·STALE_INPUT·DEVICE_ERROR)·goal 거부·적재 실패 → FAILED + PAUSED.** 자동 복귀·자동 개방 없음, 사람이 확인하고 resume(OBSERVE 로 이동). goal 거부는 reason DEVICE_ERROR·attempts 0.
- **적재:** `placed_stamp ≠ 0` 이면 PLACED(HOLD 구역이면 HELD) + 칸 증가(ok=false 면 reason DEVICE_ERROR, 우리가 stop 했거나 응답 코드가 `STOPPED` 면 STOPPED — #100. RETURN_FAILED 의 outcome 은 F-06 제안). `placed_stamp = 0` 이면 FAILED, 같은 칸 재사용.
- **stop:** `/voss/robot/stop` 먼저 → goal 취소 → PAUSED. 취소된 박스는 FAILED·STOPPED. stop 이 false·시간 초과면 not_ready 에 ROBOT, **stop 을 다시 보내 성공해야 resume**. **IDLE 에서 stop 은 IDLE 유지**(세션이 없어 resume 할 곳이 없음 — SRD 표 "모든 상태 → PAUSED" 와 다름, F-04 에 제안).
- **구역 가득:** 다음 박스 구역의 칸 = grid 칸 수면 PAUSED(그 박스는 box_id 없이 통과), `reset_zone` 전 resume 거부. ZONE_FULL 결과 기록은 F-07 제안 상태라 아직 안 한다.
- **priority:** 비대상은 PASSED·NON_TARGET·attempts 0. IDLE 에서 저장한 우선은 start 뒤에도 유지, 운전 중 start(ALL) 는 전체로 전환. PAUSED 에서는 거부. 불확실한 박스는 동을 몰라 재확인으로 보낸다(판정 뒤 그 구역에 놓는다).
- **ROBOT 준비:** RobotState READY·STOPPED + connected + 오류 없음. BUSY 는 우리 goal·MoveToZone 중이거나 끝난 뒤 `robot_busy_grace_s`(1.5 s) 안일 때만 준비(운전 중 `SortState.ready` 유지). 남이 움직이는 BUSY 는 미준비.
- **준비 판단 한계:** VISION·OCR 은 발행자 존재만 본다(BoxTrack·LabelRead 는 박스가 있을 때만 나와서 나이로 장애를 못 가른다). SERVO 는 액션 서버 존재. 상태 신호(heartbeat)는 인터페이스 변경이라 G0 뒤 논의.
- **팔레타이징(PALLETIZING, S2-T05 — `pallet_fsm.py`, 노드는 `pallet_fsm.step`):** `palletize <동,동,…>` 는 처리 중 박스가 없는 RUNNING·PAUSED 또는 세션이 있는 IDLE 에서, ROBOT·LOG 준비·`zones.pallet.pose` 교시·팔레트 칸 0 일 때만 받는다(응답 = 접수). ListPlacements → `pallet_plan` → **계획 직후(첫 PICK 전)** 시작 안내·싣지 않는 박스의 PalletResult(OVERFLOW·EXCLUDED)·PalletState(집계·경고·16칸 배정) → 박스마다 `MoveToZone(구역, 칸, PICK)` → `MoveToZone(PALLET, 격자 칸, DROP)`(적재 순서 slot 0~15(D2) 를 `pallet_plan.grid_cell` 로 gateway 격자 번호 (층−1)×8+(줄−1)×4+(열−1) 로 바꿔 부른다 — 10/12 김학민 실기 칸 자세·`zones.pallet.grid.order` 와 같은 대응, PalletState·PalletResult·HMI·DB 는 D2 그대로) → PalletResult(DONE·FAILED). 대상 조회 실패·계획 거부는 음성으로 알리고 시작 전 상태로. GRIP_FAIL 은 최대 3회 뒤 FAILED·GRIP_FAIL·다음 박스. **1층 칸 박스가 FAILED 면 그 바로 위 2층 칸 박스를 빈 1층 칸에 당겨 놓는다**(pending #37 결정, `placed_slot`·`Run.moved` — DROP 때 정해 재개해도 같은 칸). 그 밖의 실패·stop → PAUSED, resume 은 남은 박스부터 — 박스를 든 채(또는 집다가) 멈췄으면 RobotState 보고 폭(`pallet_hold_width_mm`)으로 확인해 쥐고 있으면 놓고, 집은 박스를 놓쳤으면 FAILED·DROPPED + 안내, 집다가 멈췄는데 빈손이면 다시 집는다. 폭을 모르면 resume 거부. 놓은 뒤 끊긴 DROP 은 DONE(+STOPPED·DEVICE_ERROR). 끝나면 OBSERVE → 트레이가 다 빈 구역 칸 0(`emptied_zones` — 초과·경로 제외가 남은 구역은 그대로) → 구역별 실은 수·초과·경로 제외·실패 안내(`finish_sentence`) → 시작 전 상태(RUNNING 이면 도착 시각부터 판독). 팔레타이징 중 start·priority·answer·reset_zone 거부, 멈춘 실행이 있으면 reset_zone(모든 구역)·palletize 거부. `reset_zone PALLET` 은 IDLE·PAUSED 에서만(사람이 손을 넣기 전에 멈춘다). 멈춘 실행을 버리는 명령은 아직 없다(노드 재시작). **1층만(`pallet_layers: 1`, ADR-0014 B)**: 게이트에서 2층 놓기를 뺐을 때 sort_manager 파라미터로 1층 칸(0·1·4·5·8·9·12·13, 용량 8)만 쓴다 — 칸 번호 규칙·메시지·PalletState 16칸은 그대로, 2층 칸은 EMPTY.
- **SortResult.slot (S2-T07 sort_manager 몫):** PLACED·HELD 는 놓은 칸, 재확인 칸 PICK 실패 HELD 는 재확인 칸, 그 밖은 -1.
- **아직 없음:** label_reader 의 `/voss/vision/read_label`(3단계, T23 비전) — 없으면 바로 질문으로 간다. `zones.recheck.view_pose` 교시(김학민 T35) 전에는 VIEW 가 거부돼 질문으로 간다. UpdateZoneMap(C 범위), voss_config 쓰기.
