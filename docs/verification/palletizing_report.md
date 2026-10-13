# 팔레타이징 검증 보고서 — BRD v1.5 (2026-10-13)

- **검증 대상:** 로컬 통합 브랜치 `integ/1013-gate-v15`(fef3153, **리뷰 전**) 위의 `verify/palletizing`. GitHub 계정 정지로 팔레타이징 코드는 main 에 없고 로컬 브랜치에만 있다 — S2-T01(94126e3)·T04(4118dde)·T05(6c2881d)·T06(c25ae5c)·T07(2c85b7f)·T08 브리지(b3cc33a)·T13 문서(360fac0). 웹 HMI 는 원격 브랜치 `origin/feat/22-web-hmi-initial`(8c009dd)에만 있다.
- **기준:** BRD v1.5 10장(TR-PAL-01~12, 10.10 결정 D1~D7)과 검증 프롬프트 v2(정답 생성기 2.3·시나리오 S1~S8·불변식 2.5). 명세가 정답이고, 명세가 정하지 않은 것은 "명세 미정"으로 둔다.
- **방법:** 코드 읽기와 로봇·LLM 없는 시험. 로봇·컨베이어·그리퍼 명령, LLM 호출, `.env` 열람은 하지 않았다.
- **이전 판(10/12, v1.4 구현 기준)** 은 git 기록에 없다(커밋 전) — 그때 결과: S1~S8 전부 시작 거부, 무작위 500회 중 468 불일치, 버그 B1~B4. 이번 판은 v1.5 구현 뒤의 결과다.
- **추가한 시험** (xfail 없음 — 모두 통과해야 한다):
  - `src/voss_manager/test/test_verify_palletizing.py` — 정답 생성기(원본), S1~S8 ↔ 명세 표, 불변식 500회, v1.4 잔재 없음, 대상 선정, 입력 검증, 결정성, 시작·안내·기록·재개 (29 통과)
  - `src/voss_voice/test/test_verify_palletize_intent.py` — 음성 경로 검증(LLM 없이) (6 통과)
  - `src/voss_hmi/test/test_verify_hmi_palletize.py` — HMI 명령·배치도 전달 (2 통과)
  - 통합 트리 전체: bringup 27, hmi 64(실제 DB 7 건너뜀), manager 101, robot 100, servo 243, vision 114, voice 153 — 실패 0, ruff 통과

## 1. 선행 조건 (0단계)
| 항목 | 결과 | 근거 |
|---|---|---|
| A·B·C 트레이가 동별 7개를 받나 (D1) | ❌ 미충족 | `config/voss_config.yaml` A·B·C grid 3칸. D1 제안 A·B 8칸·C 6칸(김학민 S2-T21, pending #29). sort_manager 는 grid 에서 칸 수를 계산하므로 설정만 바뀌면 된다 |
| `zones.pallet` 교시 좌표 | ❌ 미충족 | 설정에 키 없음 → sort_manager 가 palletize 거부("팔레트 구역 좌표가 교시되지 않음"). S2-T02 |
| `zones.pallet` 격자 4×2×2·피치·층 27 mm·여유 폭 | ⚠️ 문서만 | `docs/interfaces/voss_config.md` 에 `cols 4 · lanes 2 · layers 2 · pitch_x_mm · pitch_y_mm · layer_mm 27 · drop_margin_mm` 스키마. 피치·여유 폭 값은 pending #23 |
| MoveToZone PICK(A·B·C)·DROP·PALLET | ❌ 미구현 | gateway `robot_gateway.py`: PICK 은 RECHECK 만, DROP 없음, ZONES 에 PALLET 없음(S2-T03). 인터페이스는 slot 0~15·`cols` 없음(D2, 94126e3) — MoveToZone 타입 해시는 main 과 같다 |
| 인터페이스 문서와 코드 | ✅ 일치 | voss_msgs.md ↔ `.msg`·`.srv`, mqtt.md ↔ hmi_bridge(palletize·`voss/pallet/state`·`slot`), topics.md ↔ sort_logger(`/voss/log/list_placements`), intent_json.md ↔ voss_voice |
| 투입 예정 수량 기본값 20 | ❌ 10 | 웹 `PlanRepository.java:15`·`App.tsx:43`(웹 브랜치). S2-T22 정의석 |
| DB 마이그레이션 | ⬜ 공용 PC | `docker/db/migrations/20261012_sprint2_pallet.sql`(v1.5 pallet_log). 적용 전이면 sort_logger 가 slot 없이 쓰며 경고하고, ListPlacements 는 `DB_ERROR` |

## 2. 요약
| 판정 | 개수 | 항목 |
|---|---|---|
| 통과 | 6 | TR-PAL-02·03·04·08·09·11 (03·09 는 실제 DB, 08 은 실기 확인 필요) |
| 미구현 | 6 | TR-PAL-01(웹 경로 입력 화면), 05·06·07(gateway), 10 ④(3D 웹), 12(남은 수) |
| v1.5 미반영 | 0 | — |
| 실패 | 0 | — |
| 명세 미정 | 5 | §7 (#37 은 10/13 결정) |

**가장 심각한 문제 3개**
1. **[상] 로봇 쪽과 트레이가 없어 실기를 할 수 없다.** A·B·C 칸 PICK·DROP(2층)·PALLET(S2-T03), 트레이 8·8·6칸(S2-T21, D1), 팔레트 교시(S2-T02). 관리자 FSM 이 PICK 을 보내면 gateway 가 `INVALID` 로 답해 첫 박스에서 PAUSED.
2. **[중] (고침) 1층 칸 박스가 FAILED 면 그 위 2층에 박스가 놓일 수 있었다** — pending #37 결정(10/13 PL)대로 위층 박스를 빈 1층 칸에 당겨 놓도록 고쳤다(d8c1d78, `test_layer2_box_pulled_down_onto_failed_slot`).
3. **[중] 웹 HMI 의 경로 입력·3D 팔레트·남은 수가 없다**(S2-T08 웹 쪽 D5 미정, S2-T22). ROS·MQTT 쪽(`voss/pallet/state` 에 집계·경고·16칸)은 준비됐다.

## 3. 요구사항별 결과
| ID | 결과 | 근거 | 비고 |
|---|---|---|---|
| TR-PAL-01 | **미구현(웹 화면)** · 음성·브리지 통과 | 음성 `intent_logic.py` `check_route`·palletize 분기, `test_verify_palletize_intent.py` 6건, `palletize_cases.json` 8건. 브리지 `mqtt_logic.py:150` `_route_arg`(1~3·중복 없음 → "a,b,c"), `test_verify_hmi_palletize.py` | 실제 LLM 정확도 미측정(`eval_real_intent.py --cases palletize`, 비용 — 실행 전 확인). 웹 경로 입력 화면은 D5 |
| TR-PAL-02 | **통과** | `pallet_fsm.py:222` `_on_palletize`, `:28` `BUSY_MSG` 문장 일치, 칸 카운터 ≠ 0 거부·reset_zone PALLET 요청, PALLETIZING; `test_start_conditions` | "세션이 있는 IDLE"은 지금 FSM 에서 생기지 않는다(관찰) |
| TR-PAL-03 | **통과** (실제 DB 확인 필요) | PLACED·A/B/C·경로·미이동, 보류 제외·작업자 판정 흐린 박스 포함, 동별 상한 없음(`test_no_v14_residue`), 경로 제외 수 `Plan.counts()`(`pallet_plan.py:96`). DB 실패·스풀 남음 → 시작 안 함(`sort_logger.py:155`, `db_writer.py:147`) | 실DB 시험 `test_slot_and_pallet_log_and_list_placements`(공용 PC) |
| TR-PAL-04 | **통과** | `pallet_plan.py:142` `allocate`(16 이하 전부, 넘으면 물량 많은 순·동률은 먼저 방문 동이 후순위), `:155` 위치는 수량과 따로. S1~S8 명세 표 일치, 불변식 500회 실패 0, 결정적 | 계획 하나를 FSM·PalletState·TTS·PalletResult 가 공유(`pallet_fsm.py` `run.plan`) |
| TR-PAL-05 | **미구현(gateway)** · 관리자 통과 | `pallet_fsm.py:26` `MAX_PICK = 3`, GRIP_FAIL 재시도 → FAILED → 다음 박스 | gateway A·B·C PICK 없음(S2-T03) |
| TR-PAL-06 | **미구현(gateway)** · 관리자 통과 | 관리자: `CallMove("PALLET", slot 0~15, "DROP")`, 박스마다 관측 복귀 없음, 마지막 뒤 OBSERVE. gateway DROP·최소 개방·2층 +27 mm 없음 | |
| TR-PAL-07 | **미구현** | 관절 경유점·16칸 2층 ikin — S2-T02·T03 | |
| TR-PAL-08 | **통과** (실기 확인 필요) | `pallet_fsm.py:468` `_on_resume`: 든 채 멈춤 → 보고 폭 확인 → 같은 칸에 놓기, 놓쳤으면 FAILED·DROPPED + 안내, 다음 칸부터(`test_resume_continues_at_next_slot`) | 보고 폭 범위 39.5~44.0 실기 확인 |
| TR-PAL-09 | **통과** (실제 DB 확인 필요) | PalletResult 에 slot·열·줄·층(`_finish_box` `pallet_fsm.py:356`), 싣지 않은 박스 OVERFLOW·EXCLUDED 를 계획 직후 발행(S1 = 19건, `test_s1_records_and_finish_sentence`). sort_logger `_on_pallet`(`sort_logger.py:151`) → pallet_log, 다 옮긴 트레이만 칸 0(`emptied_zones`) | 미적재 박스 칸 비움은 하지 않는다(그대로 있으니) |
| TR-PAL-10 | **미구현(④ 3D 웹)** · ①②③ 통과 | ① 계획 직후 첫 PICK 전 `PublishPalletState`(`pallet_fsm.py:304`, `sort_manager.py:307`) — 동별 실을 수·초과·경로 제외·`overflow_warning`·16칸, MQTT 전달 `hmi_bridge.py:212`. ② "…첫 배송지 대치동은 오른쪽입니다. 팔레트가 16칸이라 3개는…"(`pallet_fsm.py:154`). ③ "… 역삼동 7개, 대치동 3개, 청담동 6개를 실었습니다. 초과로 못 실은 박스는 대치동 3개입니다."(`:168`) | ④ 웹 3D 는 D5. 경고는 초과일 때만(`test_s3_excluded_has_no_overflow_warning`) |
| TR-PAL-11 | **통과** | 초과·경로 제외 박스는 PICK 하지 않고 원래 구역·칸을 기록(`Plan.unloaded`), 칸 카운터도 그대로 | |
| TR-PAL-12 | **미구현** | 남은 수 = 예정 − 처리(PLACED·HELD·FAILED) — 팔레타이징 결과 미반영(`SessionController.java:53`, web_api.md) | S2-T22 정의석 |

## 4. 시나리오 결과 (S1~S8)
정답 생성기(원본)는 명세 2.4 표 8개를 그대로 재현하고, 구현은 8개 모두 정답과 같다 — 동별 실은 수·초과·경로 제외·칸 배치·적재 순서. 줄 순서도 명세 표와 같다(1줄 → 2줄, 줄 대칭 없이 일치 — `test_lane_order_is_lane1_first`).

| 시나리오 | 실음 / 초과 / 경로 제외 | 결과 |
|---|---|---|
| S1 역→대→청, 7·6·6 | 역 7·청 6·대 3 / 대 3 / — | 일치 |
| S2 청→역→대, 7·6·6 | 역 7·대 6·청 3 / 청 3 / — | 일치 |
| S3 역→청, 7·6·6 | 역 7·청 6 / 0 / 대 6 | 일치 (초과 경고 없음) |
| S4 역→대→청, 6·5·5 | 16 / 0 / — | 일치 (경계 `> 16`) |
| S5 역→대→청, 8·6·5 | 역 8·대 6·청 2 / 청 3 / — | 일치 |
| S6 역→대→청, 6·6·6 | 청 6·대 6·역 4 / 역 2 / — | 일치 |
| S7 대→역→청, 4·3·5 | 12 / 0 / — | 일치 (4열 빈 칸) |
| S8 대→역→청, 7·6·6 | 청 6·역 7·대 3 / 대 3 / — | 일치 (첫 배송지 대치 = 4열) |

## 5. 불변식 시험 (무작위 500회, seed 20261013)
| 분류 | 횟수 |
|---|---|
| 불변식 1~6 + 정답 일치 | 489 |
| 실패 | **0** |
| 대상 0개(명세 미정, 판정 제외) | 11 — 구현은 시작 거부("옮길 박스가 없음"), 정답 생성기는 빈 계획 |

## 6. 발견한 버그·문제와 처리
| # | 심각도 | 내용 | 처리 |
|---|---|---|---|
| B1 | 하 | PalletState 가 첫 PICK 요청 뒤에 발행 | **고침**(6c2881d) — `PublishPalletState` 액션을 첫 CallMove 앞에 |
| B2 | 중 | psycopg2 없는 PC 에서 `colcon test` 가 voss_hmi 시험을 하나도 안 돌림 | **고침**(2c85b7f) — 모듈 수준 importorskip 대신 ImportError 를 잡음, 이제 64개 실행 |
| B3 | 중 | hmi_bridge 가 palletize·`voss/pallet/state` 를 모름 | **고침**(b3cc33a) — ACL 예시 포함 |
| B4 | 중 | 대본·게이트 문서가 v1.4 전제 | **고침**(360fac0) — 20개·16칸·D3 제안 |
| N1 | 중 | 1층 FAILED 칸 위에 2층 박스가 놓일 수 있음 | **고침**(d8c1d78) — pending #37 결정: 위층 박스를 빈 1층 칸에 당겨 놓고 위층 칸은 비움 |
| N2 | 하 | 게이트 D3 예시("1층 8칸 + 2층 1칸")가 구현된 채우기 순서(열마다 1층 2칸 → 2층 2칸)와 다름 | 게이트 문서에 같은 의도의 "1·2열 8칸(2층 4칸)" 제안 — D3 전원 결정 |
| N3 | 하 | 시연의 "판별 불가" 박스가 송장을 전혀 못 읽으면(UNKNOWN) 집지 않고 통과 → 보류 구역에 안 간다 | 대본 §2 에 "후보가 하나는 읽히게" 준비 조건 |
| N4 | 하 | 마이그레이션 전 DB 에서 새 sort_logger 가 모든 INSERT 를 실패할 위험 | **막음**(2c85b7f) — 연결 때 스키마를 보고 slot 없이 쓰며 경고 |

## 7. 명세 미정 항목
| 항목 | 구현 동작 | 팀이 정할 것 |
|---|---|---|
| 같은 층 줄 순서 (D6, pending #34) | 1줄 → 2줄 (명세 표·정답 생성기와 같음) | 이대로 고정할지 |
| 한 동 일부 적재 시 남길 박스 (pending #36) | 트레이 (구역, 칸) 앞 번호부터 싣고 뒤를 남김 | 하차 편의로 바꿀지 |
| FAILED 박스의 칸 (pending #37) | **결정(10/13 PL)**: 위층 박스를 빈 1층 칸에 당겨 놓는다. 위층이 없으면 비워 둔다 | — |
| 이력 질의 답에 보류 포함 (TR-PAL-12) | 남은 수 자체가 미구현(S2-T22) | 보류 1 을 말할지 |
| 대상 0개 | 시작 거부("옮길 박스가 없음") | 거부인가, 빈 계획으로 끝인가 |
| 분류 중 경로 없는 "팔레타이징 시작해" | intent_parser 가 먼저 "배송 순서를 다시 말씀해 주세요" | 분류 중이면 그 안내를 먼저 할지 |

## 8. 실기 검증 체크리스트 (사람이 비상정지 옆에서, BRD v1.5 S1)
> §1 선행 조건(트레이 D1·팔레트 교시·gateway S2-T03·마이그레이션)이 풀려야 시작할 수 있다. 로봇·벨트·그리퍼 명령은 사람이 실행한다(CLAUDE.md 규칙 6).

| # | 항목 | 확인 방법 | 통과 기준 | 결과 |
|---|---|---|---|---|
| 0-1 | 트레이 칸 수 | `voss_config.yaml` A·B·C grid, 실물 | A·B 8칸, C 6칸 이상(D1) | ☐ |
| 0-2 | 팔레트 교시·격자 | `zones.pallet` 값, sort_manager 기동 로그 "팔레트 교시 됨" | 4×2×2, 피치·layer_mm 27·여유 폭 값 | ☐ |
| 0-3 | gateway PICK·DROP·PALLET | `MoveToZone` 단독 호출(저속, 학민) | A·B·C 칸 PICK, 16칸 DROP(2층 포함) 각 1회 | ☐ |
| 0-4 | DB·sort_logger | 마이그레이션 적용, 로그에 "마이그레이션 필요" 없음, `ros2 service list \| grep list_placements` | 서비스 있음 | ☐ |
| 1 | 구역 배치 = 작업 로그 | 실물(역 7·대 6·청 6·보류 1) ↔ `sort_log` SELECT(slot 포함) | 박스·칸 일치 | ☐ |
| 2 | 팔레트 빔 | 눈 확인, `reset_zone PALLET` | 칸 카운터 0 | ☐ |
| 3 | 투입 예정 수량 | HMI | 20 | ☐ |
| 4 | 경로 설정 — 음성 | "헬로 로키, 역삼, 대치, 청담 순서로 실어줘" | 되읽기 "…첫 배송지 역삼동은 오른쪽입니다. 팔레트가 16칸이라 3개는…", PALLETIZING | ☐ |
| 5 | 경로 설정 — HMI | 웹 경로 입력·시작 | `Command` arg "역삼동,대치동,청담동" | ☐ (웹 화면 D5) |
| 6 | 계획 알림 | HMI·`ros2 topic echo /voss/pallet/state --once` | 첫 PICK 전에 `overflow_warning` true, 대치 초과 3, 16칸 배정 = S1 표 | ☐ |
| 7 | 적재 순서 | 영상·`/voss/pallet/result` | 청담 6 → 대치 3 → 역삼 7, 각 박스가 S1 표의 칸, 초과 3 은 OVERFLOW 행 | ☐ |
| 8 | 좌표 | 실물 | 1열 = 작업대 왼쪽 끝, 2층이 1층 위에 안정(+27 mm), 박스 방향 = 구역 적재 | ☐ |
| 9 | 손가락 간섭 | 근접 촬영 | 1층 2줄 사이 손가락 들어감, 2층에서 1층 윗면·옆 박스 안 밂, 4열 특히(R-20) | ☐ |
| 10 | 도달성 | 저속 실기 | 16칸 2층까지 특이점·관절 한계 없음, 4열 2층 특히(R-18), 구역 → 팔레트 관절 경유점(R-19) | ☐ |
| 11 | 남은 박스 | 실물 | 대치 3개가 대치 구역에 그대로, `pallet_log` 19행 | ☐ |
| 12 | 끝 TTS | 귀 | "역삼동 7개, 대치동 3개, 청담동 6개를 실었습니다. 초과로 못 실은 박스는 대치동 3개입니다." | ☐ |
| 13 | 이력 질의 | "지금 박스 몇 개 남았어?" | 대치 3 반영, 실은 16 제외 | ☐ (S2-T22) |
| 14 | 멈춤·재개 | 8번째 박스를 든 채 "멈춰" → "작업 재개해" | 그 박스를 8번 칸(slot 7)에, 9번 칸부터 이어짐 | ☐ |
| 15 | 파지 실패 | 1층 칸이 될 박스 하나를 비켜 놓음 | 3회 시도 뒤 FAILED, 다음 박스로 넘어가고, 그 위 2층 박스가 빈 1층 칸에 놓임(#37) | ☐ |
| 16 | 시간 | 로그(PICK 시작 → DROP 완료) | 박스당 ≤ 30 s(NFR-15), 16개 총 시간 기록 | ☐ |
| 17 | 반복성 | S1 3회 연속, S8 1회 | 회차별 시간·실패 기록, 전부 완주 | ☐ |
