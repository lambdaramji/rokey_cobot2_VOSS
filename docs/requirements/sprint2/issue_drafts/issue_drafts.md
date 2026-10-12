# Sprint 2 이슈 초안 (2026-10-10, 미게시)

BRD v1.4 10장 기준. 레포 `.github/ISSUE_TEMPLATE/task.md` 형식. `create_issues.sh` 로 한 번에 만들 수 있다(게시 전 검토).

| 키 | 제목 | 담당 | 기한 | 의존 |
|---|---|---|---|---|
| S2-T01 | [통합] Sprint 2 인터페이스 변경안 (팔레타이징·음성 기동) — docs/interfaces + voss_msgs 한 PR | 남현지 | 10/11 | S2-T02 |
| S2-T02 | [로봇] 팔레트 구역 좌표 교시·9칸 도달성(ikin) 확인, 베이스 위치 재측정 | 김학민, 남현지 | 10/11 | — |
| S2-T03 | [로봇] MoveToZone PICK 구현(10/13→10/12, 재확인·팔레타이징 공용)·DROP 모드·PALLET 칸 계산·관절 경유점 | 김학민 | 10/12 | S2-T01, S2-T02 |
| S2-T04 | [팔레타이징] 배치 계획 순수 함수 pallet_plan + 단위 시험 | 남현지 | 10/12 | — |
| S2-T05 | [팔레타이징] sort_manager PALLETIZING 상태·palletize 명령·멈춤/재개 | 남현지 | 10/13 | S2-T03, S2-T04, S2-T07 |
| S2-T06 | [팔레타이징] 음성 palletize intent (route) — intent_parser·FastAPI 프롬프트 | 남현지 | 10/13 | S2-T01 |
| S2-T07 | [팔레타이징] 기록: SortResult.slot·sort_log.slot, PalletResult → pallet_log, ListPlacements 서비스 | 남현지 | 10/12 | S2-T01 |
| S2-T08 | [팔레타이징] HMI: 경로 입력·진행률·팔레트 칸별 배치도 (hmi_bridge·Spring Boot·React) | 남현지 | 10/14 | S2-T01, S2-T05 |
| S2-T09 | [음성] voss_launcher — 음성 시스템 기동·종료 (호출어·확인 대화·마이크 인계) | 정의석 | 10/13 | S2-T10 |
| S2-T10 | [음성·로봇] 기동 프로필: 수동 절차(g0-runbook)를 단계·준비 확인 스크립트로 묶기 | 정의석, 김학민 | 10/12 | — |
| S2-T11 | [인계] 리허설 중 검출·OCR 튜닝, 비전 코드 이슈 1차 대응 (남현지 T24 인계) | 박병후 | 10/14 | — |
| S2-T12 | [인계] 재확인·질문·보류 흐름 실기(흐린 송장 완주 3회), 시연 대본 운영·리허설 진행 (남현지 T23·T24 인계) | 김학민 | 10/14 | S2-T03 |
| S2-T13 | [PL] 시연 대본 v2(단계 0·9, 박스 구성)·10/13 18:00 Sprint 2 게이트·문서 갱신 | 남현지 | 10/13 | — |
| S2-T14 | [추종·파지] 하강·들기 사다리꼴 속도 프로파일 (3순위, 우선) | 박병후 | 10/13 | — |
| S2-T15 | [추종·파지] 온라인 벨트 속도 추정 (직선 맞춤, 단계 적용) (3순위, 우선) | 박병후 | 10/14 | — |
| S2-T16 | [비전] BoxTrack yaw 관측 (box_tracker 좌표 변환에 송장 각도 포함) (3순위, J6 선행) | 남현지 | 10/14 | — |
| S2-T17 | [로봇] gateway 회전 가속 10 → 90 deg/s² 이상·각속도 전달, 에뮬레이터 회전 기준점, 그리퍼-벨트 프레임 간섭 측정 (3순위, J6 선행) | 김학민 | 10/14 | — |
| S2-T18 | [추종·파지] J6 회전 파지 (TRACK 초반 회전, LIFT 원위치) (3순위, 후순위) | 박병후 | 10/14 | S2-T16, S2-T17 |
| S2-T19 | [인계] 로그·성공률 집계와 10/14 NFR-01~03 실측값 보고 (남현지 T23 인계, 10/12 PL 승인으로 박병후 → 정의석) | 정의석 | 10/14 | S2-T12, S2-T11 |

---

### S2-T01 · [통합] Sprint 2 인터페이스 변경안 (팔레타이징·음성 기동) — docs/interfaces + voss_msgs 한 PR

labels: task, interface · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] BRD v1.4 10.7 표대로 docs/interfaces 를 먼저 고친다: voss_config.md(zones.pallet), voss_msgs.md(MoveToZone DROP·cols, Command palletize, Intent route, SortState PALLETIZING, PalletState·PalletResult·ListPlacements 신규, SortResult slot), intent_json.md(palletize), mqtt.md(voss/pallet/state), topics.md
- [ ] voss_msgs 변경은 기존 메시지 끝에만 필드 추가. 한 PR 로 묶어 머지(전체 재빌드 1회)
- [ ] DB: sort_log 에 slot 컬럼, pallet_log 테이블 스키마 초안(docker/db/init) — 정의석 리뷰

## 완료 기준 (측정 가능하게)
- interface 라벨 PR 머지, `colcon build` 전체 통과
- 각 파트 오너(김학민·정의석) 승인

## 관련 요구사항
TR-PAL-01~10, TR-VOICE-11~16 (BRD v1.4 10.7), CLAUDE.md 규칙 2

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T02 의 팔레트 크기·칸 피치 초안값(교시 전이면 그림값으로 두고 TBD 표시)

## 기한
10/11

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T02 · [로봇] 팔레트 구역 좌표 교시·9칸 도달성(ikin) 확인, 베이스 위치 재측정

labels: task · assignees: @rokeyhak, @lambdaramji

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak, 남현지 @lambdaramji

## 작업 내용
- [ ] 팔레트 트레이 중심을 record_pose 로 교시해 voss_config.yaml zones.pallet.pose 에 등록 (그림 계산값 사용 금지 — BRD 10.3 좌표 불일치)
- [ ] 3열 × 3칸 = 9칸 + 2열 배치 6칸에 대해 ikin 해·자기 충돌 확인, 오른쪽 열(베이스 최근접)은 저속 실기 접근
- [ ] A·B·C → 팔레트 이동이 베이스 근처를 지나는지 확인하고 관절 이동 경유점 후보 기록
- [ ] 로봇 베이스 중심 위치를 다시 재서 measurements 에 기록(실측 16 cm/24 cm 와 설정 좌표 12·9 cm 차이 원인)
- [ ] RG2 손가락 두께 실측 → 열 안 칸 피치·놓을 때 개방 폭 제안

## 완료 기준 (측정 가능하게)
- 9칸 모두 ikin 해 있음 또는 대안 배치 결정
- measurements 문서 PR

## 관련 요구사항
TR-PAL-06·07, R-18~21

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 로봇 시간 30분 (10/11 스탠드업에서 확정)

## 기한
10/11

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T03 · [로봇] MoveToZone PICK 구현(10/13→10/12, 재확인·팔레타이징 공용)·DROP 모드·PALLET 칸 계산·관절 경유점

labels: task · assignees: @rokeyhak

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak

## 작업 내용
- [ ] PICK: 기록된 zone·slot 위에서 pre_open → 하강 → 파지 → grip_detected 확인 → 안전 높이 (실패 GRIP_FAIL). 재확인 흐름(S2-T12)과 팔레타이징 공용이라 10/13 → 10/12 로 당김
- [ ] DROP: 칸 위 하강 → 최소 개방(박스 폭 + 여유) → 안전 높이 상승, OBSERVE 복귀 없음
- [ ] zone_motion: PALLET 칸 오프셋 = cols(n) 등분 열 중심 + 열 안 Y 피치. 순수 함수 단위 시험
- [ ] 베이스 근처 통과 구간은 관절 이동 경유점 사용

## 완료 기준 (측정 가능하게)
- A·B·C 각 칸 PICK 10회 성공
- 팔레트 9칸 DROP 각 1회 실기, 옆 박스 밀림 0
- zone_motion 단위 시험 통과

## 관련 요구사항
TR-PAL-05~07

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01 인터페이스 머지
- S2-T02 좌표

## 기한
10/12

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T04 · [팔레타이징] 배치 계획 순수 함수 pallet_plan + 단위 시험

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] 입력: route(첫 배송지부터), 적재 목록(box_id, dong, zone, slot, 이미 이동 여부). 출력: 옮길 순서(마지막 배송지부터)와 각 박스의 팔레트 열·칸
- [ ] 규칙: 열 수 = 경로 동 수(1~3), 첫 배송지 = 오른쪽(+X) 열, 열 안 최대 3칸, 대상 = PLACED·A/B/C·경로 동·미이동, 동별 3개 초과 시 오류
- [ ] 같은 입력이면 같은 결과(결정적). ROS·로봇 import 없음

## 완료 기준 (측정 가능하게)
- 시험: 경로 3/2/1개, 경로 밖 동, 보류·실패 제외, 3개 초과 거부, 재개 시 남은 목록
- colcon test 통과

## 관련 요구사항
TR-PAL-03·04

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/12

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T05 · [팔레타이징] sort_manager PALLETIZING 상태·palletize 명령·멈춤/재개

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] Command palletize 수신 → 시작 조건 검사(처리 중 박스 없음, 팔레트 비어 있음) → ListPlacements 로 대상 조회 → pallet_plan
- [ ] 박스마다 PICK(최대 2회 재시도) → DROP → PalletResult 발행, PalletState 갱신, 원래 구역 칸 비움
- [ ] stop → PAUSED(진행 정보 유지), resume → 남은 박스부터. 든 채 멈춘 박스는 grip 확인 후 놓기/FAILED
- [ ] 시작·종료 TTS 문장(순서 되읽기, 결과·실패 안내)

## 완료 기준 (측정 가능하게)
- 단독 시험(가짜 gateway)으로 전이 통과
- 실기: 1개 동 → 3개 동 경로 완주, 멈춤·재개 1회
- 10/13 18:00 게이트 판정

## 관련 요구사항
TR-PAL-02·05·06·08·10

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T03 PICK·DROP
- S2-T04
- S2-T07 ListPlacements

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T06 · [팔레타이징] 음성 palletize intent (route) — intent_parser·FastAPI 프롬프트

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] "역삼, 대치, 청담 순서로 실어줘" → type palletize, route[정식 동 이름]
- [ ] 허용 목록 검증: zone_map 등록 동, 중복 없음, 1~3개. 실패 시 되묻기
- [ ] 정답 세트에 palletize 5문장 추가(intent_cases.json)

## 완료 기준 (측정 가능하게)
- palletize 5문장 중 5 정확, 허용 외 100% 거부
- 음성 → sort_manager 수락 1회

## 관련 요구사항
TR-PAL-01

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T07 · [팔레타이징] 기록: SortResult.slot·sort_log.slot, PalletResult → pallet_log, ListPlacements 서비스

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] sort_manager 가 SortResult 에 slot 채움, sort_logger 가 sort_log.slot 기록
- [ ] sort_logger: /voss/pallet/result → pallet_log INSERT, ListPlacements(session_id) 서비스 제공
- [ ] DB 장애 시 ListPlacements 실패 → 팔레타이징 시작 거부(TR-PAL-03)

## 완료 기준 (측정 가능하게)
- 결과 1건 → sort_log.slot 기록 확인
- PalletResult 1건 → pallet_log 1행
- ListPlacements 가 이동 여부 반영

## 관련 요구사항
TR-PAL-03·09

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01

## 기한
10/12

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T08 · [팔레타이징] HMI: 경로 입력·진행률·팔레트 칸별 배치도 (hmi_bridge·Spring Boot·React)

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] hmi_bridge: /voss/pallet/state → MQTT voss/pallet/state, voss/command palletize → Command
- [ ] React: 등록 동을 순서대로 고르는 경로 입력, 시작 버튼, 진행률(n개 중 m개), 배치도(열 = 동·배송 순번, 칸 = 빈 칸·적재·실패)
- [ ] 우선순위: 경로 입력·진행률 → 배치도(시간 부족 시 진행률만, R-26)

## 완료 기준 (측정 가능하게)
- HMI 버튼으로 팔레타이징 1회 완주
- 배치도가 실제 팔레트와 일치, 반영 ≤ 1초

## 관련 요구사항
TR-PAL-10

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01
- S2-T05

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T09 · [음성] voss_launcher — 음성 시스템 기동·종료 (호출어·확인 대화·마이크 인계)

labels: task · assignees: @EuiseokJeongNZ

## 파트 / 담당
음성·웹·HMI / 정의석 @EuiseokJeongNZ

## 작업 내용
- [ ] ROS 비의존 데몬, 로그인 때 자동 실행(systemd user 서비스 제안). ROS 스택이 꺼져 있는 동안만 마이크 사용
- [ ] 호출어 + 로컬 키워드("시스템 켜줘"/"로봇 켜줘"/"시스템 꺼줘"), LLM 미사용. STT 는 AI 컨테이너 /stt
- [ ] 확인 질문(비상정지 담당 준비) → 10초 무응답 취소. 기동은 로봇 무동작, 종료는 IDLE·PAUSED 에서만 역순
- [ ] 단계별 TTS 안내, 실패 단계 이름·원인 안내, 재명령 시 실패 단계부터
- [ ] 음성 3노드 기동 시 마이크를 voice_listener 에 넘기고, 종료 후 다시 잡기

## 완료 기준 (측정 가능하게)
- 실기 기동 3회 중 3회 "준비를 마쳤습니다", 3분 이내
- 종료 3회
- 오인식 시 확인 질문에서 취소됨

## 관련 요구사항
TR-VOICE-11~16, NFR-16, R-22·23

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T10 기동 프로필
- 남은 결정 #3(음성 기동 범위)

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T10 · [음성·로봇] 기동 프로필: 수동 절차(g0-runbook)를 단계·준비 확인 스크립트로 묶기

labels: task · assignees: @EuiseokJeongNZ, @rokeyhak

## 파트 / 담당
음성·웹·HMI / 정의석 @EuiseokJeongNZ, 김학민 @rokeyhak

## 작업 내용
- [ ] 단계: AI·DB 컨테이너 → 두산 브링업 → robot_gateway(툴·TCP) → 비전 컨테이너 → belt_servo → sort_manager·sort_logger·hmi_bridge → 음성 3노드
- [ ] 단계마다 준비 확인 명령과 제한 시간, 역순 종료 명령
- [ ] 수동 기동과 같은 launch 파일·환경 파일(voss_g0_env.sh) 공유 — 폴백 유지

## 완료 기준 (측정 가능하게)
- 스크립트만으로 수동 기동과 같은 상태(not_ready 빔) 재현
- voss_bringup 에 프로필 문서화

## 관련 요구사항
TR-VOICE-13·16

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/12

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T11 · [인계] 리허설 중 검출·OCR 튜닝, 비전 코드 이슈 1차 대응 (남현지 T24 인계)

labels: task · assignees: @ok778ts123

## 파트 / 담당
추종·파지 / 박병후 @ok778ts123

## 작업 내용
- [ ] T24 인계(비전 부분): 노출·전처리·신뢰도 임계값 튜닝, 리허설 OCR 실패 원인 분석(NFR-02 값은 S2-T19 집계에 넘김)
- [ ] 리허설 중 비전 코드 이슈 1차 대응(남현지 리뷰)
- [ ] 본인 T29 타이밍 튜닝·리허설, 추종·파지 고도화(S2-T14~18)와 병행

## 완료 기준 (측정 가능하게)
- 리허설 OCR 실패 원인 표
- 리허설 통과

## 관련 요구사항
NFR-02, T24

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 남현지 10/11 전체 루프 통합·인계 메모

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T12 · [인계] 재확인·질문·보류 흐름 실기(흐린 송장 완주 3회), 시연 대본 운영·리허설 진행 (남현지 T23·T24 인계)

labels: task · assignees: @rokeyhak

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak

## 작업 내용
- [ ] T23 인계: 재확인 구역 VIEW → 재판독 → 질문 → 답대로 PICK·적재 / 무응답 보류 흐름을 실기로 완주. sort_manager 수정이 필요하면 남현지님 리뷰
- [ ] T23 인계: 시연 대본(8.1 8단계) 운영, Sprint 2 단계 0·9 는 S2-T13 에서 받아 붙임
- [ ] T24 인계(진행 부분): 전체 리허설(T05) 진행표·로봇 시간표, 회차별 판정 기록
- [ ] 본인 T37 리허설 지원·환경 재점검과 병행

## 완료 기준 (측정 가능하게)
- 흐린 송장 박스 완주 3회
- 리허설 회차별 판정 기록

## 관련 요구사항
TR-OCR-06·07, TR-VOICE-07, T23·T24

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T03 PICK
- 남현지 10/11 인계 메모

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T13 · [PL] 시연 대본 v2(단계 0·9, 박스 구성)·10/13 18:00 Sprint 2 게이트·문서 갱신

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] 남은 결정 #1: 흐린 송장 박스가 들어가는 동이 4개가 되는 문제 → 동별 3개·총 9개 구성안을 김학민님(대본 운영, S2-T12)과 확정
- [ ] 단계 0(음성 기동)·9(팔레타이징, 경로 대치 → 역삼 → 청담) 문안을 대본에 추가
- [ ] 10/13 18:00 게이트 판정·ADR 기록, plan.md·개발일정.xlsx 에 Sprint 1/2 반영, BRD v1.4 레포 반영(md 재변환)

## 완료 기준 (측정 가능하게)
- 대본 v2 PR
- 게이트 결정 기록

## 관련 요구사항
BRD v1.4 10.2·10.8

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T14 · [추종·파지] 하강·들기 사다리꼴 속도 프로파일 (3순위, 우선)

labels: task · assignees: @ok778ts123

## 파트 / 담당
추종·파지 / 박병후 @ok778ts123

## 작업 내용
- [ ] DESCEND·LIFT z 속도를 max_acc 안의 사다리꼴로 바꿔 P 제어 꼬리 제거 (예상 약 −2.0 s, 계산값)
- [ ] TCP z 하한 clamp·높이 도달 판정·비전 사각 판정 유지, sim.launch 로 먼저 확인
- [ ] T29(Kp·들기 높이 튜닝)와 같은 날 4.8 cm/s 에서 단계별 시간 비교 기록 (기준 11.4 s 실측, measurements-1010 #6)

## 완료 기준 (측정 가능하게)
- 시뮬레이션 통과
- 실기에서 G1 수준 파지 성공률 유지 + 단계별 시간 표 (measurements)
- 못 미치면 기존 프로파일로 되돌림

## 관련 요구사항
TR-SERVO-01, R-27

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 원래 기능·팔레타이징 다음 순위 (BRD 10.2)

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T15 · [추종·파지] 온라인 벨트 속도 추정 (직선 맞춤, 단계 적용) (3순위, 우선)

labels: task · assignees: @ok778ts123

## 파트 / 담당
추종·파지 / 박병후 @ok778ts123

## 작업 내용
- [ ] 트랙마다 BoxTrack position_base·촬영 시각으로 직선 맞춤, 관측 자세 정지 중 기록 우선
- [ ] ① 로그만(추정값 − 설정값) → ② 실기 정확도 확인 → ③ 2 % 이상 차이면 FF 대체, 10 % 이상이면 goal 거부
- [ ] 설정 파일은 바꾸지 않음 (belt_servo 내부, 인터페이스 변경 없음)

## 완료 기준 (측정 가능하게)
- ① 로그 10회 이상
- ② 정확도 보고
- ③ 적용 여부를 리허설 전 결정

## 관련 요구사항
TR-SERVO-02·03

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T16 · [비전] BoxTrack yaw 관측 (box_tracker 좌표 변환에 송장 각도 포함) (3순위, J6 선행)

labels: task, interface · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] docs/interfaces 먼저: BoxTrack.msg 끝에 yaw 추가(베이스 기준, 범위·0 기준 정의)
- [ ] box_detect 의 minAreaRect 각도를 픽셀 → 베이스 변환에 포함 (카메라 자세 반영)
- [ ] J6 회전 시 핸드아이 오차 측정(±30·45°) 함께 수행

## 완료 기준 (측정 가능하게)
- 정지 박스 0·15·30·45° 에서 yaw 오차 기록
- interface PR 머지 (리뷰 박병후·김학민)

## 관련 요구사항
TR-SERVO-04·06

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 팔레타이징 10/13 게이트 뒤

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T17 · [로봇] gateway 회전 가속 10 → 90 deg/s² 이상·각속도 전달, 에뮬레이터 회전 기준점, 그리퍼-벨트 프레임 간섭 측정 (3순위, J6 선행)

labels: task · assignees: @rokeyhak

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak

## 작업 내용
- [ ] servo_guard 의 각속도 0 clamp 해제·상한 설정, 회전 가속 상향
- [ ] 두산 에뮬레이터로 회전 기준점(TCP 기준 회전인지) 확인
- [ ] J6 ±30·45·90° 에서 돌린 그리퍼와 벨트 프레임 간섭 실측

## 완료 기준 (측정 가능하게)
- 에뮬레이터 확인 기록
- 간섭 측정값 measurements 기록
- watchdog·z 하한 clamp 기존 시험 통과

## 관련 요구사항
TR-SERVO-06, R-28

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 원래 기능·PICK·DROP 다음 순위 (BRD 10.2)

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T18 · [추종·파지] J6 회전 파지 (TRACK 초반 회전, LIFT 원위치) (3순위, 후순위)

labels: task · assignees: @ok778ts123

## 파트 / 담당
추종·파지 / 박병후 @ok778ts123

## 작업 내용
- [ ] goal 전 목표 각 결정 → TRACK 초반·정렬 전 회전 완료, 접근 높이에서는 회전 안 함, LIFT 에서 원래 각도로
- [ ] 회전량 최대 90°, 2° 미만 데드밴드, 처음엔 10° 초과만 → 확인 뒤 전체
- [ ] 단계: 경주 제거(T28) → J6 없이 회전 박스 실험 → yaw 관측만 → 에뮬레이터 → 실기

## 완료 기준 (측정 가능하게)
- 단계별 결과 measurements 기록
- 10/14 리허설 결과로 시연 장면 포함 여부 결정

## 관련 요구사항
TR-SERVO-05·07, R-29

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- T28 경주 제거 (#37 하위)
- S2-T16 yaw
- S2-T17 gateway

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T19 · [인계] 로그·성공률 집계와 10/14 NFR-01~03 실측값 보고 (남현지 T23 인계, 10/12 PL 승인으로 박병후 → 정의석)

labels: task · assignees: @EuiseokJeongNZ

## 파트 / 담당
음성·웹·HMI / 정의석 @EuiseokJeongNZ

## 작업 내용
- [ ] 리허설 로그·DB(sort_log, export.csv)로 이동 중 픽업 성공률(NFR-01)·OCR 정확도(NFR-02)·지시 해석(NFR-03, 본인 측정) 집계
- [ ] belt_servo 로그(박병후)·리허설 판정 기록(김학민, S2-T12)을 받아 회차별 표로 합침
- [ ] **10/14 파트별 역할 완료** 마일스톤의 NFR-01~03 실측값 보고

## 완료 기준 (측정 가능하게)
- 10/14 NFR-01~03 실측값 표 PR
- 회차별 집계 스크립트 또는 export.csv 절차 문서

## 관련 요구사항
NFR-01~03, T23

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T12 리허설 판정 기록
- S2-T11 OCR 원인 분석

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_
