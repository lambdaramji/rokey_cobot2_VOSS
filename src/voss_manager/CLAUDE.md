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

## G0 임시 규칙 (T23·SRD F-04/06/07 확정 전까지)
- **분류 결정:** RUNNING 에서 OBSERVE 도착 뒤 촬영된 stage 1 판독 중 처음으로 확실한 것(분류코드 우선, 동 이름과 다르면 불확실, `confidence ≥ ocr.confidence_min`)으로 바로 집는다. 한 번에 한 박스.
- **불확실(LOW_CONF·UNKNOWN·불일치)은 집지 않고 다음 판독을 기다린다.** box_id·SortResult 없음. 재확인 구역 → 질문 → 보류는 T23.
- **start·resume 은 먼저 `MoveToZone(OBSERVE)`**(`home_first`), 도착 시각부터의 판독만 쓴다. PLACE 응답 뒤에도 그 시각부터 다시 관측.
- **파지 실패(GRASP_FAILED·LOST·OUT_OF_REACH·STALE_INPUT·DEVICE_ERROR)·goal 거부·적재 실패 → FAILED + PAUSED.** 자동 복귀·자동 개방 없음, 사람이 확인하고 resume(OBSERVE 로 이동). goal 거부는 reason DEVICE_ERROR·attempts 0.
- **적재:** `placed_stamp ≠ 0` 이면 PLACED + 칸 증가(ok=false 면 reason DEVICE_ERROR, 우리가 stop 했거나 응답 코드가 `STOPPED` 면 STOPPED — #100. RETURN_FAILED 의 outcome 은 F-06 제안). `placed_stamp = 0` 이면 FAILED, 같은 칸 재사용.
- **stop:** `/voss/robot/stop` 먼저 → goal 취소 → PAUSED. 취소된 박스는 FAILED·STOPPED. stop 이 false·시간 초과면 not_ready 에 ROBOT, **stop 을 다시 보내 성공해야 resume**. **IDLE 에서 stop 은 IDLE 유지**(세션이 없어 resume 할 곳이 없음 — SRD 표 "모든 상태 → PAUSED" 와 다름, F-04 에 제안).
- **구역 가득:** 다음 박스 구역의 칸 = grid 칸 수면 PAUSED(그 박스는 box_id 없이 통과), `reset_zone` 전 resume 거부. ZONE_FULL 결과 기록은 F-07 제안 상태라 아직 안 한다.
- **priority:** 비대상은 PASSED·NON_TARGET·attempts 0. IDLE 에서 저장한 우선은 start 뒤에도 유지, 운전 중 start(ALL) 는 전체로 전환. PAUSED 에서는 거부.
- **준비 판단 한계:** VISION·OCR 은 발행자 존재만 본다(BoxTrack·LabelRead 는 박스가 있을 때만 나와서 나이로 장애를 못 가른다). SERVO 는 액션 서버 존재. 상태 신호(heartbeat)는 인터페이스 변경이라 G0 뒤 논의.
- 아직 없음: RECHECK·ASKING 진입, answer, UpdateZoneMap(C 범위), voss_config 쓰기, 2단계 판독 반영.
