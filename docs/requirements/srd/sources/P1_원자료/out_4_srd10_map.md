# 입력 ④ — SRD v1.0 카드 목록과 1차 영향 판단 (SRD v2.0 잠정 개정용)

- 기준: 레포 main `fe11ded`(읽기 전용), SRD v1.0 = `docs/requirements/srd/markdown/01~05`, BRD v1.7(`scratchpad/p1/in/brd_v1.7.txt`, 변경표 `BRD_v1.5_to_v1.7_변경표.md`).
- 작성 2026-10-16. 1차 판단이며 확정이 아니다. 담당자·PL 확인 전에는 "제안"이다.
- **판정 정의(이 문서에서 쓰는 뜻)**
  - 유지: 요구 문장·단계·담당·VT 합격 기준이 그대로다. 반영 문단의 상태·근거만 갱신한다.
  - 수정: 요구 문장, 수치, BRD 근거 판, VT 합격 기준, 계약 필드 중 하나가 바뀐다.
  - 종결: 요구가 다른 결정으로 소멸·대체돼 더 추적하지 않는다(ID는 남김). SYS 카드에는 해당 없음.
  - 미구현 유지: 요구는 남기되 구현·채택이 없어 수락 대상에서 빠진 상태로 둔다.
  - 판단 보류: 근거가 부족하거나 PL 결정이 필요하다.
- **근거 약어**: m1008·m1010·m1012·m1013·m1015 = `docs/measurements-10xx.md` / pd#n = `docs/pending-decisions.md` #n / RM = `docs/requirements/README.md` "v1.7 이후 바뀐 값" / vm = `src/voss_manager/CLAUDE.md` / cfg = `config/voss_config.yaml` / BRD = BRD v1.7 / VT표 = `04_검증카드_70개요구사항_추적표.md`.
- **PR·이슈 번호 표기**: `old#n` = lambdaramji/rokey_cobot2_VOSS, `_2#n` = rokeyhak/rokey_cobot2_VOSS_2(10/13~10/15, ADR-0015). G절 참고.

---

## A. SYS 70 카드 표 + 1차 영향

원문 출처: `01_VOSS_SRD_v1.0.md` §4~§7 카드와 §9 추적표. 요약은 원문 요구 문장을 줄였다.

### A-1. 기능 §4.1 최초 전체 흐름(A)

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-FR-001 | A | 남현지 | 카메라·로봇·그리퍼·설정·로그 준비를 확인해 실행 가능 여부 표시 | 통합 파생 | 001 | 018 | 019·009·029 | **수정** | ready 구현(old#96)·G0 사용. 단 VISION·OCR 은 발행자 존재만 보고 stale 판정 불가(vm "준비 판단 한계") → VT-001 의 "stale 입력으로 start 차단" 범위를 고쳐야 함. ROBOT ready = RobotState READY·STOPPED+connected(vm)로 확정. 음성 기동(TR-VOICE-13)이 `SortState.not_ready` 를 완료 판정에 씀 |
| SYS-FR-002 | A | 남현지 | 손목 RGB 영상을 촬영 시각과 함께 비전에 제공 | TR-PICK-01·02 | 002 | 001 | 004·032 | 유지 | 1080p/6 ms/WB4600 그대로. 파지 중 23 Hz·USB 프레임 손상 관측(m1015 §6) 은 검증 기록으로 |
| SYS-FR-003 | A | 남현지 | 벨트 위 박스 검출, 픽셀 중심·영역 제공 | TR-PICK-02 | 003 | 001 | 001·003·028·031 | 유지 | 검출기 seg 확정(ADR-0011, pd#17), 검출률 ≈99.9 %(m1008 #8). yaw 출력은 신규 카드로(E절) |
| SYS-FR-004 | A | 남현지 | 검출·OCR·픽업·적재·기록을 공통 식별 규약으로 연결 | TR-SYS-04 파생 | 004 | 003·007 | 003·004·020 | 유지 | G0 에서 box/track/goal/DB 연결 확인(m1010 G0 1회차). 팔레타이징 run_id 는 신규 카드 쪽 |
| SYS-FR-005 | A | 남현지 | 송장 판독 영상을 해당 박스와 대응시켜 OCR 에 제공 | TR-OCR-03 | 005 | 003 | 007·034 | 유지 | LabelCrop 규약 그대로, stage 2 실기(m1015 §6) |
| SYS-FR-006 | A | 남현지 | 명확한 송장의 코드·동 판독, 기본 매핑 구역 결정 | TR-OCR-04·05, TR-PICK-08 | 006 | 004 | 020·032 | 유지 | 0.6 이 BRD TR-OCR-06 에 명시됨. 시연 20/20(m1015) |
| SYS-FR-007 | A | 남현지 | RGB+캘리브레이션으로 픽업 위치를 로봇 좌표로 제공 | TR-PICK-03 | 007 | 002 | 001·002·004·010 | 유지 | 이동 중 좌표 최대 2.73 mm, moving_verified(m1008 #5). ≤5 mm 는 여전히 제안값(ADR-0012 범위 밖). J6 회전 시 오차는 신규 카드 쪽 |
| SYS-FR-008 | A | 박병후 | 움직이는 벨트 위 박스를 선택한 추종 방식으로 따라가 도달 | TR-PICK-04 | 008 | 019·021 | 002·008·011 | 유지 | G1 20/20, A안 유지(ADR-0002 판정, docs/g1-gate.md) |
| SYS-FR-009 | A | 박병후 | 하강·그리퍼 파지 동작 수행 | TR-PICK-06 | 009 | 015·019 | 006·012·013 | **수정** | TR-PICK-06 이 v1.7 에서 "벨트·트레이 50 mm 개방, 39 mm·14 N" 으로 바뀜. 코드 벨트 사전 개방은 90 mm(cfg `pre_open_mm`, RM) — 근거 판 갱신 + 값 충돌은 PL 확인 대기(판단 일부 보류). J6 회전 파지는 신규 카드 |
| SYS-FR-010 | A | 박병후 | 그리퍼 피드백으로 파지 성공 판정 | TR-PICK-07 | 010 | 015·019 | 006·012 | 유지 | grip_detected+폭, VERIFY 재닫기 24/24(m1010 #4). hold_width_max 44.0 은 pd#28(문서상 미정) |
| SYS-FR-012 | A | 김학민 | 파지 박스를 결정 구역의 유효 적재 위치에 놓음 | TR-PICK-08 | 012 | 016 | 010·016·018 | **수정** | 격자가 ABC 3×1 → 3×2×2층(12칸, C 피치 50·오프셋 −30), 채우기 2→5→1→4→0→3→6, 시연은 칸 0~6(BRD TR-PICK-08·10.3, cfg). VT-012 의 "5 구역 유효 슬롯" 기준 갱신 |
| SYS-FR-013 | A | 김학민 | 적재 뒤 다음 박스 관측 대기 자세로 복귀 | TR-PICK-08 | 013 | 016·018 | 016·019 | 유지 | PLACE→OBSERVE 복귀 그대로. 팔레타이징 DROP(복귀 없음)은 신규 카드. 이동 속도 값은 SF-002 |
| SYS-FR-014 | A | 정의석 | 박스별 최종 결과를 작업 로그에 기록 | TR-SYS-04 | 014 | 007·012 | 003·016·020·027 | 유지 | G0 commit 로그+SELECT 확인(m1010). `sort_log.slot` 추가는 IF-004 쪽 |
| SYS-FR-033 | A | 남현지 | 단일 설정 기준의 동·코드·구역·좌표를 일관 제공 | TR-SYS-06 | 033 | 006 | 009·019·034 | **수정** | TR-SYS-06 v1.7: 공용 PC 설정을 레포 config 로, 기본 경로 `~/voss_ws/config` 통일. 설정 범위에 zones.pallet·view_pose·layers 추가(cfg). UpdateZoneMap(쓰기)은 미구현 |

### A-2. 기능 §4.2 최종 시연 필수(B)

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-FR-011 | B | 박병후 | 파지 실패 시 최대 2회 재시도, 이후 미분류 확정 | TR-PICK-07 | 011 | 019 | 005·006 | **수정** | 재시도는 x 여유가 있을 때만(U9-b, 4464eee), 실패 결과는 FAILED+PAUSED·사람 확인(vm). "미분류로 확정" 뒤 운전을 이어 가지 않음 → SF-004 와 같이 정리 |
| SYS-FR-015 | B | 정의석 | 호출어 "헬로, 로키" 감지 시 명령 수집 시작 | TR-VOICE-01 | 015 | 010 | 028 | 유지 | ADR-0007(에너지 VAD+전사 매칭, "헬로 로키야" 수용), 1 m 증거(old#126). 시연은 음성 명령 미사용(m1015) — 검증 미완 |
| SYS-FR-016 | B | 정의석 | 한국어 음성 명령을 텍스트로 | TR-VOICE-02 | 016 | 010 | 028·029 | 유지 | Whisper 모델 크기 pd#6 미정. 녹음 20개 시험 증거 못 찾음 |
| SYS-FR-017 | B | 정의석 | 텍스트→intent, 실행 전 유형·인자 검증 | TR-VOICE-03 | 017 | 009 | 023·024·026 | **수정** | type 확장(palletize+route, recheck, query_history — `intent_json.md`). TR-VOICE-07 v1.7 "송장 확인 불가"=보류·로컬 규칙, TR-PAL-01 시연 문형 로컬 규칙. intent 20/20(pd#18) |
| SYS-FR-018 | B | 남현지 | 유효한 시작 명령으로 분류 시작 | TR-VOICE-05 | 018 | 005·009 | 014·023 | 유지 | start 구현·"작업을 시작합니다"(vm). IDLE 중 stop 처리 차이는 IC-CMD-01 |
| SYS-FR-019 | B | 남현지 | 재개 명령에 정지 단계·박스 상태별 재개 조건 적용 | TR-VOICE-05 | 019 | 005·017 | 015·024 | **수정** | TR-SYS-01·TR-PAL-08 v1.7: PALLETIZING 중 멈춤 → PAUSED → 재개 시 PALLETIZING. 위층 박스 3회 실패 PAUSED 뒤 재개(TR-PAL-05). 시연 속도에서 멈춤·재개 미확인(m1015 §1) |
| SYS-FR-020 | B | 남현지 | 특정 동 우선·전체 분류 지시 | TR-VOICE-06 | 020 | 005·009 | 023 | 유지 | 구현(vm priority). 시연 2회차에서 단계 2 안 함 |
| SYS-FR-021 | B | 남현지 | 비대상 박스는 픽업하지 않고 통과 | TR-PICK-09 | 021 | 005 | 003·021·023 | 유지 | PASSED·NON_TARGET 구현(vm) |
| SYS-FR-022 | B | 정의석 | 지시 확인·완료·예외 질문을 음성으로 | TR-VOICE-04 | 022 | 010 | 024·025 | 유지 | TTS = OpenAI gpt-4o-mini-tts(ADR-0013, pd#12). 발행자 확대는 IC-VOICE-01 |
| SYS-FR-023 | B | 남현지 | 1차 입구 OCR·2차 추종 중 다수결 OCR, 서보와 분리 | TR-OCR-01·02 | 023 | 003·004 | 007·017·031 | **수정** | 2단계 기본 켬, 선명도 가중 투표·발행 = 같은 동 2장+반대표 없음, 1단계 무판독 트랙은 180° 먼저, 집으러 간 트랙의 1단계 중단(old#171·#181, ADR-0008, m1015 §6). BRD "3~5 프레임 다수결" 과 표현 정합 필요 |
| SYS-FR-024 | B | 남현지 | 코드·동 교차 검증, 불일치·저신뢰 규칙 | TR-OCR-05 | 024 | 004 | 020·031 | 유지 | 규칙 그대로(ADR-0008) |
| SYS-FR-025 | B | 남현지 | 신뢰도 미달 박스를 재확인 구역에서 정지 재판독 | TR-OCR-06 | 025 | 004·005 | 017 | **수정** | TR-OCR-06 v1.7: 판독 실패(UNKNOWN) 포함, 즉시 재판독(`defer_recheck: false`, v1.6 보관 흐름 원복). view_pose 교시(518ca41)·stage 3(old#113). 시연 재확인 4건 ✅(m1015) |
| SYS-FR-026 | B | 남현지 | 재판독 미확정 시 1·2위 후보로 작업자 판단 요청 | TR-OCR-07 | 026 | 004·005 | 024 | **수정** | TR-OCR-07 v1.7: 판독 결과가 없으면 등록 동 전체를 후보로(시연 3지 질문, m1015 box 010) |
| SYS-FR-027 | B | 남현지 | 유효 후보·보류 답만 받아 목적지 결정 | TR-VOICE-07 | 027 | 005·009 | 017·023·024 | **수정** | TR-VOICE-07 v1.7: "송장 확인 불가" = 보류 답, LLM 없이 로컬 규칙. "재확인 시작" 명령은 BRD 에서 삭제(intent_json 에는 `recheck` 잔존) |
| SYS-FR-028 | B | 남현지 | 30초 무응답이면 보류 구역 | TR-OCR-07 | 028 | 005·025 | 024 | 유지 | 시연 box 016 NO_ANSWER 30.0 s → HOLD(m1015) |
| SYS-FR-029 | B | 정의석 | 로그 기준 동별·보류·남은 수를 음성·HMI 로 | TR-VOICE-08, TR-SYS-04 | 029 | 008 | 021·022 | 유지 | REST `/api/stats` 구현. 남은 수 정의 변경은 FR-032 로 흡수. 시연 단계 6·8 안 함 |
| SYS-FR-030 | B | 정의석 | 음성 불가 시 HMI 버튼으로 같은 제어 | TR-VOICE-02, TR-SYS-03 | 030 | 009·011 | 023·026 | 유지 | 시연은 HMI 버튼으로 진행(m1015) |
| SYS-FR-031 | B | 정의석 | HMI 에 운전 상태·지시·OCR·로봇 상태·집계·보류 목록 | TR-SYS-03 | 031 | 011 | 019·026·031 | 유지 | 6항목 그대로. 3D 팔레트 표시는 신규 카드(FR-043 제안) |
| SYS-FR-032 | B | 정의석 | 투입 예정 수량 입력, 남은 수 계산 | TR-VOICE-08, TR-SYS-03 | 032 | 007·008·011 | 003·021·022 | **수정** | 기본 10 → 20(BRD 10.12), 남은 수에 팔레타이징 결과 반영(TR-PAL-12, 미구현 — BRD 10.13). `web_api.md` 는 아직 기본 10·식 그대로 |
| SYS-FR-034 | B | 남현지 | OCR·파지·적재·로그 오류를 구분 보고 | TR-SYS-02, TR-SYS-04 파생 | 034 | 005·007·017 | 006·014·016·020·027 | 유지 | 문장 그대로. STOPPED reason 추가(old#100). RETURN_FAILED outcome·ZONE_FULL 기록은 여전히 미정(F-06·F-07) |

### A-3. 기능 §4.3 선택(C)

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-OP-001 | C | 남현지 | 자연어로 동→구역 매핑 변경·확인 | TR-VOICE-09 | 035 | 023 | 033 | **미구현 유지** | UpdateZoneMap 처리 없음(vm "C 범위라 None"), 시연 단계 4 제외(m1015 §1). 채택/미채택 기록 없음 |
| SYS-OP-002 | C | 김학민 | 직접교시 좌표로 새 구역 등록 | TR-VOICE-10(Should) | 036 | 024 | 033 | **미구현 유지** | TeachZone.srv 만 있고 서버 구현 없음(src 검색 0건) |

### A-4. 인터페이스 §5.1

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-IF-001 | A | 남현지 | 영상·검출·OCR 인터페이스가 박스 식별·단계·촬영 시각 연계 | TR-PICK-02, TR-OCR-01~06 | 037 | 003 | 001·003·004·007·034 | **수정** | BoxTrack `yaw_base`·`yaw_valid` 추가(945c67d, S2-T16), stage 2 발행 규칙(ADR-0008) |
| SYS-IF-002 | A | 박병후 | 픽업 인터페이스: 대상·진행·결과·취소 | TR-PICK-04~07 | 038 | 019 | 005·006·014 | **수정** | feedback `err_u/err_v` 삭제(old#103), LOST 정의·U9 문구(_2#29, 282a665) |
| SYS-IF-003 | A | 김학민 | 로봇 인터페이스: 좌표·속도·그리퍼 단위·좌표계·응답·오류 | TR-PICK-03·05·06·08 | 039 | 014·015·016 | 004·010~014·016·017 | **수정** | RobotState·Gripper 확장·stop 이 main 반영(old#92·#104). MoveToZone mode PICK·DROP·zone PALLET·STOPPED·NOT_CONFIGURED, servo_cmd `header.stamp` 규칙(old#138), angular.z(J6, _2#48·old#164, 기본 off), TCP 불일치 거부(old#121) |
| SYS-IF-004 | A | 정의석 | 처리 결과 저장 경로(원문·동·신뢰도·주체·구역·결과·ID·시각) | TR-SYS-04 | 040 | 007·012 | 003·016·020 | **수정** | SortResult `slot` 추가·`sort_log.slot`(S2-T07), pallet_log 는 신규 카드 |
| SYS-IF-005 | B | 정의석 | 명령 인터페이스: 운전·분류·질의·응답의 유형·인자·무효 처리 | TR-VOICE-03·05~08 | 041 | 009·011 | 023·024·026 | **수정** | Command `palletize`·`recheck`, Intent `route`, MQTT/REST palletize args(`web_api.md`) |
| SYS-IF-006 | B | 정의석 | HMI 인터페이스: 데이터·회신·정기 상태·결과 이벤트 | TR-SYS-03 | 042 | 011 | 019·026 | **수정** | MQTT 토픽 확대(pallet/state, box_track, robot_pose, robot_joints, voice_status, log_status — topics.md 10/14), SSE `pallet_state`. 시연 빌드의 `voss/voice/text`·`voice/request` 는 main 미반영(m1015 §0) |
| SYS-IF-007 | A | 남현지 | 설정·좌표·벨트 속도·별칭·코드의 소비자·전달 규약 | TR-SYS-06 | 043 | 006 | 009·019·034 | **수정** | zones.pallet·recheck.view_pose·layers, belt.speed_cmps 4.56(a7d9dd6), MoveToZone 300 mm/s launch 기본(RM) |
| SYS-IF-008 | A | 박병후 | 노드 간 계약을 송수신 양쪽 확인 버전으로 관리 | docs/interfaces 규칙 | 044 | 003·014·019 | 034 | 유지 | 규칙 그대로. 시연 빌드에 main 밖 인터페이스가 있었던 점은 검증 기록으로(m1015 §0) |

### A-5. 성능 §6.1

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-PF-001 | B | 박병후 | 재시도 포함 이동 중 픽업 ≥70 % | NFR-01 | 045 | 021·022 | 008·031 | 유지 | G1 20/20(최초 시도 20, ADR-0002·m1010). 실측값 보고 담당은 정의석으로 이관(pd#25) — 담당 표기만 |
| SYS-PF-002 | B | 남현지 | OCR 전체 ≥90 %, 흐린 제외 ≥95 % | NFR-02 | 046 | 022 | 007·031 | 유지 | 정지 50/50(ADR-0012 배경). 추종 실기는 31장(+오프라인 105장, m1015 §6) — VT-046 추종 50장 미충족 |
| SYS-PF-003 | B | 정의석 | 지시 해석 ≥95 % | NFR-03 | 047 | 009·022 | 031 | 유지 | intent 20/20(pd#18). palletize 8건은 별도 판정(intent_json.md) |
| SYS-PF-004 | B | 박병후 | 정상 자동 사이클 ≤30 s | NFR-04 | 048 | 025 | 016·024·030·031 | 유지 | 시연 최장 18.4 s(m1015). 새 사이클 목표 pd#26 미정 — NFR-04 유지 |
| SYS-PF-005 | B | 정의석 | 발화 종료→TTS 시작 ≤3 s | NFR-05 | 049 | 010·022 | 025·028·031 | 유지 | 미실측(ADR-0013, pd#12) |
| SYS-PF-006 | B | 박병후 | 30 Hz 서보 갱신 유지 | NFR-06 | 050 | 020 | 011·028·031 | 유지 | 틱 평균 33.3 ms, 36.3 ms 초과 0.2 %(m1015 §6, 정식 집계 전) |
| SYS-PF-007 | B | 박병후 | 관측 지연 ≤100 ms | TR-PICK-03, NFR-06 | 051 | 003·020 | 004·011·031 | 유지 | 카메라→발행 p95 49~61 ms(m1008 #1·#8). capture→servo 소비 전체 구간 측정 증거 못 찾음 |
| SYS-PF-008 | B | 정의석 | HMI 상태 변경 ≤1 s 반영 | 기존 SRD 제안(MC-031) | 052 | 011·022 | 019·026·031 | 유지 | 미실측 |
| SYS-PF-009 | B | 남현지 | 서로 다른 물리 박스 10개 중 8개 이상 올바른 최종 적재 | NFR-07 | 067 | 007·022 | 003·021·031 | **수정** | **20개 중 16개 이상**(D7, pd#35, ADR-0012 시연 행 변경, BRD 10.12). 시연 20/20(m1015) |

### A-6. 안전 §6.3

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-SF-001 | A | 김학민 | 정지 명령·입력 상실 시 승인된 안전 중단 | TR-VOICE-05, NFR-09 | 053 | 017·020 | 014 | 유지 | stop·watchdog 200 ms 구현·실측(old#104, m1010 #12). 450 mm/s 에서 stop 응답 4/5 TIMEOUT 미해결, 시연 속도 미확인(m1015) — 검증 미완 |
| SYS-SF-002 | A | 김학민 | 로봇 동작에 작업 영역·속도 제한 적용 | NFR-09 | 054 | 017 | 009·010·014 | **수정** | NFR-09 v1.7: 구역 이동 450 mm/s·900 mm/s² 시연 전 점검. 코드는 300 mm/s(RM, _2#57 J1 특이점 9015). BRD 6.1 v1.7: 컨트롤러 TCP 미등록·불일치면 MoveToZone 거부(old#121 구현). 펜던트 공간 제한(m1010 #2) |
| SYS-SF-003 | A | 김학민 | 물리 비상정지는 음성·웹과 독립 접근 | NFR-09 | 055 | 017 | 014·019 | 유지 | 변경 없음 |
| SYS-SF-004 | B | 남현지 | 판독·파지 실패를 재시도·재확인·질문·보류로 처리 | TR-SYS-02, NFR-08 | 056 | 005·017 | 005·014·015·017·024 | **수정(PL 판단 필요)** | 구현은 파지 실패·적재 실패 → FAILED+PAUSED(vm), 팔레타이징 위층 3회 실패 → PAUSED(TR-PAL-05 v1.7). BRD NFR-08 "정지 없이" 와 충돌 — 요구 문장 또는 구현 중 하나를 정해야 함 |

### A-7. 데이터·제약·유지보수·환경 §7

| ID | 단계 | 담당 | 요구 요약 | BRD 근거 | VT | TBD | MC | 1차 판단 | 이유·근거 |
|---|---|---|---|---|---|---|---|---|---|
| SYS-DT-001 | A | 정의석 | 동일 박스 결과 중복 수신으로 이중 집계 안 함 | TR-SYS-04 파생 | 057 | 007·012 | 003·020·021 | 유지 | PK box_id·DO NOTHING 구현(old#94) |
| SYS-DT-002 | B | 정의석 | 로그 저장 실패를 확인할 오류 정보 제공 | NFR-12 파생 | 058 | 012 | 019·027 | 유지 | `/voss/log/status`·MQTT `voss/log_status` 구현. 장애 시험 증거 없음(F-12) |
| SYS-DT-003 | B | 정의석 | 승인 보존 기간·재기동 조건에 따라 로그 보존 | TR-SYS-04, 운영 파생 | 059 | 012 | 027·029 | **판단 보류** | 반영 문단의 "10/16 발표까지 전체 보존" 기한이 오늘로 끝남. 이후 보존 정책·데이터(bag·기록표는 레포 밖) 처리 결정 필요 |
| SYS-CT-001 | A | 김학민 | 지정 M0609·RG2·D435i·컨베이어와 ROS 2 Jazzy 에서 동작 | BRD 6.1 | 060 | 013·026 | 028·029 | **수정** | BRD 6.1 v1.7 장비에 천장 CCTV(관제용, 검출 보조 아님) 추가. 시연은 Web PC+Nodes PC 2대 구성(`deployment_two_pc_trial.md` 제안, ADR-0016 제안) |
| SYS-CT-002 | A | 남현지 | 깊이 대신 RGB+알려진 박스 높이 | TR-PICK-02, BRD 6.2 | 061 | 002 | 002 | 유지 | 변경 없음 |
| SYS-CT-003 | A | 김학민 | 두산 호출은 gateway 단일 직렬 경로, stream·stop 은 별도 경로 | TR-PICK-05, BRD 6.2 | 062 | 014 | 011·013·014 | 유지 | speedl_stream 결정(ADR-0010, pd#8), 큐 연속 78/78(m1008 #15) |
| SYS-CT-004 | A | 김학민 | 한 번에 1박스, 벨트 자동 제어 안 함 | BRD 2.2·6.2 | 063 | 013 | 032 | 유지 | 벨트 설정값만 4.8 → 4.56(FF 상쇄값, a7d9dd6) — 반영 문단 갱신 |
| SYS-CT-005 | B | 남현지·정의석·김학민 | 비전·DB 를 컨테이너로 실행, 호스트와 통신 | TR-SYS-05 | 064 | 018·026 | 028·029 | 유지 | GPU 비전 컨테이너 빌드 수정이 10/16(fe11ded, old#31). T19 실기는 호스트 CPU venv(m1015 §6) — 시연에서 비전 컨테이너 사용 여부 확인 필요 |
| SYS-CT-006 | B | 정의석 | API 키를 코드·설정·문서에 넣지 않음 | BRD 6.1 | 065 | 026 | 026·029 | 유지 | 변경 없음 |
| SYS-MT-001 | B | 박병후 | 녹화·녹음·모의·dry-run 으로 단독 검증 경로 | 유지보수 제안 | 066 | 022 | 031 | 유지 | fake_box·sim_check·g0_mock·rg2_dry_run·에뮬레이터(old#132·#139, voss_servo design) |
| SYS-EN-001 | A | 남현지 | 수동 노출 5~8 ms·고정 WB, 글자 대비 확보 | NFR-13 | 068 | 001·013 | 032 | 유지 | 변경 없음 |
| SYS-EN-002 | A | 김학민 | 투입 위치가 관측·대기 위치와 겹치지 않음 | NFR-10 | 069 | 013·017 | 032 | 유지 | 변경 없음(작업대 120×65 배치도는 BRD 10.3) |
| SYS-EN-003 | A | 김학민 | 배치·케이블이 동작 범위에서 간섭·당김 없음 | BRD 6.2 | 070 | 013·017 | 010·018·032 | **수정** | 반영 문단의 "pre_open 90 mm 벽 간섭" 전제가 바뀜: 트레이 50 mm·벨트 90 mm 분리, 트레이 3×2×2·팔레트 구역·원호 경로(R-18~20), J6 회전 그리퍼와 벨트 프레임 간섭(TR-SERVO-06) |

---

## B. IC 18 (§5.2)

| IC-ID | 연결 SYS | v1.0 요지 | 1차 판정 | 현재 상태 | 근거 |
|---|---|---|---|---|---|
| IC-VISION-01 | IF-001 | 카메라→tracker Image·CameraInfo, 원본 stamp | 유지 | 진행 | 파지 중 23 Hz·USB 프레임 손상(m1015 §6, m1010 사건). 실제 FPS 기록 남음 |
| IC-VISION-02 | IF-001 | `/voss/vision/box` BoxTrack 30 Hz, 윗면 중심 base_link | 수정 | 종결 가능 | yaw_base·yaw_valid 추가(945c67d). HAND_EYE 이동 좌표 G0·G1·시연 사용 |
| IC-VISION-03 | IF-001 | `/voss/vision/label_crop` LabelCrop | 유지 | 종결 가능 | 2차 영상 실기(m1015 §6) |
| IC-VISION-04 | IF-001 | `/voss/vision/label` LabelRead·`read_label` | 수정 | 종결 가능 | stage 2 발행 규칙·기본 켬(old#181), stage 3 구현(old#113), view_pose 교시(518ca41) |
| IC-PICK-01 | IF-002 | TrackAndGrasp goal1/box, 최대 3회, phase/reason | 수정 | 종결 가능 | feedback err 삭제(old#103), LOST·U9 문구(_2#29). G1 20/20 |
| IC-ROBOT-01 | IF-003 | servo_cmd TwistStamped 30 Hz | 수정 | 진행 | header.stamp=발행 시각·gateway 옛 stamp 거부(old#138), angular.z(J6) 기본 off(old#164) |
| IC-ROBOT-02 | IF-003 | `/voss/robot/pose` ~50 Hz | 유지 | 진행 | pose_source joint_states(old#118), 5 s 창 45 Hz 미달 13/727(m1010 #9) |
| IC-ROBOT-03 | IF-003 | move_to_zone·gripper·stop(미반영)·state(타입 미정의) | 수정 | 남음 | stop·state·Gripper 확장 main 반영(old#92·#104), PICK·DROP·PALLET. 남음: 450 mm/s stop TIMEOUT 4/5, RETURN_FAILED 업무 결과 |
| IC-CMD-01 | IF-005 | intent·Command canonical | 수정 | 진행 | palletize·recheck 추가, IDLE 중 stop 은 IDLE 유지(vm — v1.0 표 "모든 상태 → PAUSED" 와 다름) |
| IC-VOICE-01 | IF-005 | `/voss/voice/say` 발행자 manager·intent_parser | 수정 | 진행 | voice_listener(TIMED_OUT, topics.md), 시연 빌드 hmi_bridge 도 발행(main 밖, m1015 §0) |
| IC-STATE-01 | IF-006 | SortState·RobotState·log/status | 수정 | 진행 | SortState PALLETIZING, RobotState IDL 반영. VISION·OCR heartbeat 없음(vm) |
| IC-RESULT-01 | IF-004 | SortResult 최종 1건 | 수정 | 진행 | slot 추가. RETURN_FAILED outcome 제안 상태(F-06) |
| IC-CONFIG-01 | IF-007 | YAML·ZoneMap(transient_local) | 수정 | 진행 | zones.pallet·view_pose. 기본 경로 통일·UpdateZoneMap(C) 미완 |
| IC-STATS-01 | IF-004 | GET /api/stats | 수정 | 남음 | remaining 에 팔레타이징 반영(TR-PAL-12) 미구현, planned 기본 10 → 20 미반영(`web_api.md`) |
| IC-MQTT-01 | IF-006 | MQTT `voss/*` 6토픽·ack·TTL | 수정 | 진행 | mqtt.md 확정(old#105) 후 토픽 확대. voice/text 경로 main 미반영 |
| IC-DB-01 | IF-004 | logger→PostgreSQL→Spring | 수정 | 남음 | pallet_log·sort_log.slot·ListPlacements 추가. 장애·스풀 시험 현장 증거 없음(F-12, 단위 시험만) |
| IC-DEVICE-01 | IF-003 | gateway↔두산·RG2 Modbus | 유지 | 종결 가능 | speedl_stream(ADR-0010), RG2 Modbus(ADR-0005), 큐 78/78 |
| IC-OPTION-01 | OP-001/002 | update_zone_map·teach_zone | 미구현 유지 | 남음 | 둘 다 미구현, 채택 결정 기록 없음 |

신규 IC 제안: IC-PALLET-01(sort_manager→HMI/logger: PalletState·PalletResult, MQTT `voss/pallet/state`), IC-PALLET-02(sort_manager↔sort_logger: `/voss/log/list_placements`, pallet_log), IC-LAUNCH-01(voss_launcher↔기동 프로필·준비 확인·마이크 인계). 표시 전용 텔레메트리(box_track·robot_pose·joints·voice_status)는 IC-MQTT-01 수정에 넣는다.

---

## C. TBD-001~026 (§10)

| TBD | 원 질문 | 상태 | 근거·남은 것 |
|---|---|---|---|
| 001 | 영상·검출 | 종결 가능 | seg 확정·YOLO 비교 생략(ADR-0011), 30 Hz·p95 49 ms(m1008 #1) |
| 002 | 좌표·캘리브레이션 | 종결 가능 | 이동 중 최대 2.73 mm·moving_verified(m1008 #5). ≤5 mm 는 승인 목록 밖(ADR-0012) — 값 표기만 정리 |
| 003 | 식별·시각·OCR 연결 | 종결 가능 | G0 에서 box/track/label 연결 확인(m1010) |
| 004 | OCR 판정·후보 | 진행 | stage 2 규칙 확정(ADR-0008). 추종 50장 실기 미달(31장) |
| 005 | FSM·정지·예외 | 진행 | RECHECK·ASKING·PALLETIZING 구현. 시연 속도 멈춤·재개 미확인 |
| 006 | 설정 전달 | 진행 | 레포 config 승격(4ef1a1a), sha 기록. 기본 경로 통일 확인 필요 |
| 007 | 결과·업무 ID | 남음 | RETURN_FAILED outcome 제안 상태(vm, F-06) |
| 008 | 이력·남은 수 | 남음 | TR-PAL-12·planned 20 미반영 |
| 009 | 명령 schema | 진행 | palletize 반영. 같은 box 늦은 답 수락 창 미정(intent_json.md 63행, F-09) |
| 010 | 음성 | 진행 | 호출어 ADR-0007·TTS ADR-0013 결정. Whisper 크기 pd#6 미정, 3 s 미측정 |
| 011 | HMI/MQTT | 진행 | mqtt.md 확정, 3D 시연. DOM 1 s 미측정 |
| 012 | DB | 남음 | 장애 시험 각 3회 증거 없음 |
| 013 | 장비/벨트/환경 | 종결 가능 | 버전·벨트 실측 기록(old#120, m1010 #11, m1013 §5). 배치 변경 시 재검증 조건은 유지 |
| 014 | robot API/큐 | 종결 가능 | speedl_stream·실측(ADR-0010, pd#8) |
| 015 | gripper | 종결 가능 | T34 10회 등(m1008 #14), ADR-0009, Gripper IDL. 새 값 충돌(50 vs 90)은 TBD-027 로 분리 제안 |
| 016 | pose/grid/적재 | 진행 | 격자 3×2×2 로 대체(HOLD 2칸 vs 누적 3 문제는 RECHECK·HOLD 2×1 로 정리). RETURN_FAILED 남음 |
| 017 | stop/limits/recovery | 남음 | watchdog·멱등 확인. 450 mm/s stop TIMEOUT 4/5, 시연 속도 미확인 |
| 018 | 배포/READY | 진행 | ROBOT ready 확정. heartbeat 없음, voss_launcher 미구현 |
| 019 | 픽업 action | 종결 가능 | G1 20/20, 계약 반영 |
| 020 | 주기/age/상실 | 진행 | 틱 측정(정식 집계 전), 전체 지연 구간 미측정 |
| 021 | 추종/게이트 | 종결 가능 | ADR-0002 판정 통과·A안 유지 |
| 022 | 시험세트/증거 | 진행 | STT 20·TTS·HMI·DB 장애·추종 OCR 50 미완 |
| 023 | 선택 매핑 | 남음 | 미구현. 채택/미채택 결정 기록 필요 |
| 024 | 선택 teach | 남음 | 위와 같음 |
| 025 | 사이클 | 종결 가능 | `cycle_s = finished_at − started_at`(web_api.md), 시연 18.4 s(m1015) |
| 026 | PC/GPU/resources | 진행 | GPU 비전 컨테이너 빌드 수정 10/16(fe11ded), 동시 부하 미확인 |

---

## D. F-01~16 (03 대장)

| F | 주제 | 상태 | 근거·남은 것 |
|---|---|---|---|
| F-01 | 동적 좌표·촬영/pose 정합 | 종결 가능 | m1008 #4~#6, pose_lag 0(m1010 #10), G0 HAND_EYE |
| F-02 | 제어 API·최신 목표·동시성 | 종결 가능 | ADR-0010, pd#8 결정, m1008 #15 |
| F-03 | 파지 방향·폭/힘/높이 | 종결 가능 | ADR-0009(old#88), T34(m1008 #14). BRD v1.7 의 50 mm 와 코드 90 mm 차이는 새 F 로 |
| F-04 | 기본 stop·입력 상실·limit | 남음 | 구현·실측(old#104, m1010 #5·#12). 450 mm/s stop TIMEOUT 4/5, 시연 속도 정지·재개 미확인(m1015) |
| F-05 | 초기 설정·ready·기동 | 진행 | ROBOT ready·sha 기록. VISION·OCR 신선도 미판정 |
| F-06 | 복귀 실패 업무 결과 | 남음 | outcome 제안 상태(vm) |
| F-07 | 격자·용량·RECHECK 점유 | 진행 | 격자 3×2×2·slot 규칙 구현. ZONE_FULL 기록 미구현(vm) |
| F-08 | 정상 DB commit·조회 | 종결 가능 | G0 commit 로그+SELECT, DB_ERROR 0(m1010) |
| F-09 | 질문 회차·수락 창 | 남음 | 같은 box 재질문 늦은 답 처리 미정 |
| F-10 | 2차 OCR·재확인/재픽업 | 종결 가능 | stage 2·3, view_pose, PICK(old#148), 시연 재확인 4건 |
| F-11 | 웹·음성·집계·현재 세션 | 진행 | mqtt·web_api 확정. voice/text 경로·TR-PAL-12 미완 |
| F-12 | 저장 장애·스풀 | 남음 | 단위 시험만(src/voss_hmi/test), 현장 시험 기록 없음 |
| F-13 | PC·네트워크·GPU 부하 | 진행 | GPU 컨테이너 빌드 10/16, 동시 부하 미확인 |
| F-14 | 시험 정답·분모·수락자 | 진행 | G1 완료, 나머지 VT 다수 미실측 |
| F-15 | BRD 판·공동 기준선 | 진행 | BRD v1.7 기준판(old#165·#166). SRD v2.0 개정이 이 항목 |
| F-16 | 매핑 변경·교시 채택 | 남음 | 미구현 사실만 있고 채택 결정 기록 없음 |

---

## E. 대응 카드가 없는 BRD v1.7 요구 · 새 ID 제안

번호는 v1.0 마지막 번호를 잇는다(FR-034·IF-008·PF-009·SF-004·DT-003·CT-006·MT-001·EN-003, VT-070, TBD-026, F-16). 단계 표기는 v1.0 의 A/B/C 와 별도로 **"S2"(Sprint 2 확장, 게이트 통과 기능만 수락 대상)** 를 제안한다 — PL 결정 필요. 대안은 C 로 넣고 "게이트 통과로 채택"을 기록하는 것.

### E-1. 신규 SYS 카드 제안

| 제안 ID | 넣을 곳 | BRD 근거 | 요구 요지 | 구현·실기 상태(근거) |
|---|---|---|---|---|
| SYS-FR-035 | §4.4 팔레타이징(신설) | TR-PAL-01 | 경로 입력(HMI·음성, route 1~3, 별칭 정규화, 시연 문형 로컬 규칙) | 구현, 시연은 HMI 입력(m1015 §2) |
| SYS-FR-036 | §4.4 | TR-PAL-02, TR-SYS-01 | 시작 조건·PALLETIZING 상태·팔레트 칸 0 확인 | 구현(vm) |
| SYS-FR-037 | §4.4 | TR-PAL-03 | 대상 선정(ListPlacements, PLACED A·B·C, DB 불가 시 미시작) | 구현 |
| SYS-FR-038 | §4.4 | TR-PAL-04 | 배치 계획(16칸, 초과 규칙, pd#36) | 구현(`pallet_plan`) |
| SYS-FR-039 | §4.4 | TR-PAL-05 | 집기·재시도·위층 3회 실패 PAUSED·1층 FAILED 당겨 놓기(pd#37) | 구현, 실패 경로 실기 기록 미확인 |
| SYS-FR-040 | §4.4 | TR-PAL-06 | DROP 놓기, 50 mm 개방, 2층 +27 mm | 구현·시연 |
| SYS-FR-041 | §4.4 | TR-PAL-07 | 원호 경유점·스플라인·IDLE 확인 | 구현(10/12 실기) |
| SYS-FR-042 | §4.4 | TR-PAL-08 | 팔레타이징 멈춤·재개(PAUSED↔PALLETIZING) | 미확인(m1015) |
| SYS-FR-043 | §4.4 | TR-PAL-10 | HMI 3D·계획 표시·되읽기·완료 안내 | 시연 ✅(3D·TTS) |
| SYS-FR-044 | §4.4 | TR-PAL-11 | 미적재 박스는 원래 구역 유지 | 구현·시연(OVERFLOW 3) |
| SYS-DT-004 | §7.1 | TR-PAL-09 | 팔레타이징 기록(PalletResult·pallet_log, OVERFLOW·EXCLUDED) | 구현, 19행(m1015) |
| SYS-FR-045 | §4.5 음성 기동(신설) | TR-VOICE-11 | voss_launcher 상시 청취·로컬 키워드 기동 명령 | 미구현(ADR-0014 D) |
| SYS-SF-005 | §6.3 | TR-VOICE-12 | 기동 전 확인 질문·10초 취소·로봇 무동작 | 미구현 |
| SYS-FR-046 | §4.5 | TR-VOICE-13 | 단계별 준비 확인·실패 안내·이어 하기 | 미구현 |
| SYS-FR-047 | §4.5 | TR-VOICE-14 | 시스템 종료(IDLE·PAUSED 만) | 미구현 |
| SYS-CT-007 | §7.2 | TR-VOICE-15 | 마이크 동시 점유 금지·인계 | 미구현 |
| SYS-MT-002 | §7.3 | TR-VOICE-16 | 수동 기동 폴백(같은 launch·환경 파일) | 수동 기동만 사용 |
| SYS-FR-048 | §4.6 추종·파지 고도화(신설) | TR-SERVO-02·03 | 벨트 속도 온라인 추정·단계 적용(2 % 대체, 10 % goal 거부) | 구현(855b92c 등), 적용 단계는 voss_servo 설계 확인 |
| SYS-FR-049 | §4.6 | TR-SERVO-04 | 박스 yaw 관측 제공(BoxTrack) | 구현(945c67d) |
| SYS-FR-050 | §4.6 | TR-SERVO-05 | J6 회전 파지(범위 −110°, flip 70°, pd#27) | 구현·기본 off(rotate.enable), 현장 14/14 |
| SYS-SF-006 | §6.3 | TR-SERVO-06 | 회전 가속 한계·각속도 전달 조건·벨트 프레임 간섭 측정 | 각속도 전달 기본 off(old#164) |
| SYS-PF-010 | §6.1 | NFR-14 | 팔레트 배치 정확도 100 % | 시연 16/16 계획 칸(m1015) |
| SYS-PF-011 | §6.1 | NFR-15 | 팔레타이징 박스당 ≤30 s | 최대 15.3 s(m1015) |
| SYS-PF-012 | §6.1 | NFR-16 | 음성 기동 3/3, ≤3분 | 미시험 |
| SYS-IF-009 | §5.1 | BRD 10.7 | 팔레타이징 인터페이스(PalletState·PalletResult·ListPlacements·Command palletize·Intent.route·MoveToZone PALLET·DROP) | main 반영 |
| SYS-IF-010 | §5.1 | BRD 10.6 | 음성 기동 인터페이스(기동 프로필·준비 확인 신호·마이크) | 미정 |

- VT 제안: 위 26개에 VT-071~VT-096 을 순서대로.
- 카드로 만들지 않고 흡수·이관하는 것:
  - TR-PAL-12 → SYS-FR-032 수정(필요하면 독립 추적용 SYS-FR-051 예약).
  - TR-SERVO-01(사다리꼴 z) → SDD(`src/voss_servo/DESIGN.md`)로 이관. SRD §1.2 "제어 게인·내부 알고리즘은 SDD" 원칙. 외부 효과는 PF-004·새 사이클 목표(pd#26)로.
  - TR-SERVO-07(J6 단계 실험) → §8 검증 절차.
  - BRD 6.1 TCP 미등록 시 MoveToZone 거부 → SYS-SF-002 수정. 천장 CCTV → SYS-CT-001 수정. 박스 20개·판별 불가 1 → §2.4 가정 수정. TR-SYS-01 PALLETIZING → §3.3 상태 + FR-036·FR-042.

### E-2. 신규 TBD·F 제안(값 충돌·미정)

| 제안 ID | 내용 | 근거 |
|---|---|---|
| TBD-027 | 벨트 사전 개방: BRD 50 mm vs 코드 90 mm | RM, PL 확인 대기 |
| TBD-028 | 구역 이동 속도: BRD 450 mm/s vs 코드 300 | RM, _2#57 |
| TBD-029 | NFR-08 "정지 없이" vs 파지 실패 FAILED+PAUSED | vm, SF-004 |
| TBD-030 | 음성 기동 범위·실행 방식(pd#21·#22 미정) | pd |
| TBD-031 | 새 사이클 목표(pd#26 미정) | pd |
| TBD-032 | 시연 빌드의 main 밖 인터페이스(voice/text·voice/request·hmi_bridge say) | m1015 §0·§5 |
| TBD-033 | 로그·녹화 보존 정책(10/16 이후) | DT-003 |
| F-17 | 시연 속도 stop·멈춤·재개 확인(450 TIMEOUT 원인 포함) | m1015 §5 |
| F-18 | 팔레타이징 실패 경로(위층 3회 실패·당겨 놓기) 실기 | TR-PAL-05 |

---

## F. 29148 SyRS 항목 ↔ v1.0 구조 대응표 초안

(표준 원문이 없어 조항 번호는 쓰지 않는다. ○ 있음, △ 일부, ✗ 없음)

| SyRS 항목 | v1.0 위치 | 대응 | v2.0 메모 |
|---|---|---|---|
| 목적 | §1.1 | ○ | |
| 범위 | §2.1·§2.2 | ○ | Sprint 2 범위·S2 단계 추가 |
| 개요 — 시스템 문맥 | §2.1·§3.1·§3.2 그림 | ○ | 그림이 v0.3. `docs/requirements/architecture/` 그림으로 교체 검토 |
| 개요 — 시스템 기능 | §3.2 | ○ | voss_launcher·팔레타이징 할당 추가 |
| 개요 — 사용자 특성 | §2.3 | △ | 역할만 있음. 숙련·교육 수준(BRD 3.1 "조작 교육 시간 없음") 없음 |
| 용어 | §1.4 | ○ | pallet_slot·cell·run_id·PALLETIZING 추가 |
| 참조 | §1.3 | ○ | BRD v1.7·ADR 0010~0016·measurements 1008~1015 로 갱신 |
| 기능 요구 | §4 | ○ | §4.4~4.6 신설 |
| 사용성 요구 | — | ✗ | 음성 문형 고정·HMI 버튼 폴백·질문 문장 등 흩어져 있음 |
| 성능 요구 | §6.1·§6.2 | ○ | PF-010~012 |
| 시스템 인터페이스 | §5 | ○ | IC 신규 3개 |
| 시스템 운영 | §7.5·§3.3 | △ | 기동·종료(음성 기동), 리허설·시연 절차 링크 |
| 모드와 상태 | §3.3 | △ | 전용 절 없음. sort_manager 7상태·RobotState·logger 상태를 한 절로 |
| 물리 특성 | §2.4·SYS-CT-001·004 | △ | 박스·트레이·팔레트 치수, 작업대 120×65 |
| 환경 조건 | §7.4 EN-001~003 | ○ | |
| 보안 | SYS-CT-006·§7.5 ACL | △ | BRD 2.2 는 보안을 제외 범위로 둠 — 최소 범위 명시 |
| 정보 관리 | §7.1·§5.8 | ○ | DT-004 |
| 정책과 규정 | — | ✗ | 교육장 안전 규칙·비상정지 운용(CLAUDE.md 규칙 6) 등. 없으면 "해당 없음" 명시 |
| 수명주기 유지 | §7.3 MT-001·§9.2 | △ | 시연 뒤 유지 범위 미정 |
| 포장·취급·운송 | — | ✗ | 해당 없음 명시 권장 |
| 검증 | §8·04 문서 | ○ | G0/G1/S2 게이트/시연 결과 반영 |
| 가정·종속성 | §2.4 | ○ | |
| 약어 | §1.4 일부 | △ | 별도 약어표 없음 |
| (추적성) | §9 | ○ | 표준 항목명은 아니지만 유지 |
| (미정 대장) | §10·03 문서 | ○ | |

---

## G. 링크·번호 주의점

**표본 확인 결과(10/16, gh api 읽기만)**
- v1.0 의 URL 은 거의 모두 `github.com/yujh5537/rokey_cobot2_VOSS`(markdown+manifest 165회). 계정 이름이 lambdaramji 로 바뀌었고(old#98) GitHub 가 넘겨 준다. 표본: issue #51 댓글 permalink 정상, PR #77 정상. 넘겨 주기는 같은 이름의 새 계정이 생기면 깨진다.
- 상대 경로 `../assets/VOSS_v0.3_논리구조.png`, `sources/current_main/` 는 존재.
- **경로는 같은데 내용이 바뀐 곳**: v1.0 §1.3 은 `VOSS_BRD.md` 를 v1.3 사본이라 적었으나 지금은 v1.7 사본이다.

**표본 확인 방침(제안)**
1. 링크 종류별 2~3개씩: 이슈 댓글 permalink(#50~#55), PR 번호(#63~#89), blob 링크(e8dd5e5 BRD v1.2), 상대 경로.
2. v2.0 에서는 URL 을 `lambdaramji` 로 바꾸거나 v1.0 링크는 그대로 두고 "옛 이름, 넘겨 주기로 열림" 각주.
3. 번호는 레포를 붙여 쓴다: `old#50`, `_2#57`, 가능하면 커밋 해시.

**`_2` 번호와 섞이는 지점**
- `_2` 레포(10/13~10/15) PR·이슈 #1~#62 가 옛 레포 #1~#62 와 겹친다. 10/15 복귀 뒤 커밋은 다시 옛 레포 번호다(#163 이후, 예 fe11ded "(#31) (#204)" 의 #31 = 옛 T22).
- 같은 번호, 다른 뜻 표본: `old#28` T19 label_reader 이슈 / `_2#28` 파지력·벨트 속도 제안 · `old#31` T22 비전 컨테이너 / `_2#31` GRASP 진입 오차 · `old#47` LabelCrop 문서 PR / `_2#47` Sprint 2 팔레타이징 통합 PR · `old#57` 10/06 실측 PR / `_2#57` MoveToZone 450→300.
- **SRD 와 직접 겹치는 곳**: v1.0 의 #50~#55 는 상호 확인 이슈인데, m1015·ADR-0014 의 "#50 실기(10/14, 450 mm/s stop 4/5 TIMEOUT)" 는 `_2#50`(MoveToZone 450 mm/s 기본값 PR) 이다. BRD v1.7 "PR #32"(cc1d0fe 통합)도 `_2` 번호.
- 10/12~10/15 커밋 메시지는 "(옛 #37)" 처럼 앞에 붙여 구분한 것과 안 붙인 것이 섞여 있다. 변경 대장에 번호를 옮길 때 커밋 날짜로 레포를 판정한다.

**문서끼리 어긋난 곳(변경 대장에 넣을 후보)**
- pd#29(D1)·pd#28(hold_width 44.0)이 `pending-decisions.md` 에는 "미정"인데 BRD v1.7 은 D1 결정, 코드에는 44.0 반영(dbbdca8).
- `intent_json.md`·`web_api.md` 에 `recheck` 명령이 남아 있으나 BRD v1.7 은 "재확인 시작"을 삭제.

---

## H. 통계

| 대상 | 유지 | 수정 | 신규 | 종결 | 미구현 유지 | 판단 보류 | 합계 |
|---|---|---|---|---|---|---|---|
| SYS 카드(v1.0) | 43 | 24 | — | 0 | 2 | 1 | 70 |
| SYS 카드(제안 신규) | — | — | 26 | — | — | — | 26 |
| IC | 4 | 13 | 3(제안) | 0 | 1 | 0 | 18(+3) |

SYS 수정 24개 = FR-001·009·011·012·017·019·023·025·026·027·032·033, IF-001~007, PF-009, SF-002·SF-004, CT-001, EN-003.

| 대상 | 종결 가능 | 진행 | 남음 | 합계 |
|---|---|---|---|---|
| IC 상태 | 5 | 9 | 4 | 18 |
| TBD | 9 | 11 | 6 | 26 |
| F | 5 | 6 | 5 | 16 |

신규 제안: SYS 26(FR-035~050, DT-004, SF-005·006, CT-007, MT-002, PF-010~012, IF-009·010), VT-071~096, IC 3, TBD-027~033(7), F-17·18.
