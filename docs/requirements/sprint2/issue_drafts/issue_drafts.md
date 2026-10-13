# Sprint 2 이슈 초안 (2026-10-10, 미게시)

BRD v1.4 10장 기준. 레포 `.github/ISSUE_TEMPLATE/task.md` 형식. `create_issues.sh` 로 한 번에 만들 수 있다(게시 전 검토).

| 키 | 제목 | 담당 | 기한 | 의존 |
|---|---|---|---|---|
| S2-T01 | [통합] Sprint 2 인터페이스 변경안 (팔레타이징 v1.5·음성 기동) — docs/interfaces + voss_msgs 한 PR | 남현지 | 10/13 | S2-T21, S2-T02 |
| S2-T02 | [로봇] 팔레트 구역 좌표 교시·16칸 2층 도달성(ikin) 확인, 베이스 위치 재측정 | 김학민, 남현지 | 10/13 | — |
| S2-T03 | [로봇] MoveToZone PICK(재확인·팔레타이징 공용)·DROP 2층·PALLET slot 0~15·관절 경유점 | 김학민 | 10/13 | S2-T01, S2-T02, S2-T21 |
| S2-T04 | [팔레타이징] 배치 계획 순수 함수 pallet_plan (v1.5: 16칸 2층·초과 처리) + 단위 시험 | 남현지 | 10/13 | — |
| S2-T05 | [팔레타이징] sort_manager PALLETIZING 상태·palletize 명령·멈춤/재개·완료 안내 | 남현지 | 10/13 | S2-T03, S2-T04, S2-T07 |
| S2-T06 | [팔레타이징] 음성 palletize intent (route) — intent_parser·FastAPI 프롬프트 | 남현지 | 10/13 | S2-T01 |
| S2-T07 | [팔레타이징] 기록: SortResult.slot·sort_log.slot, PalletResult(DONE·FAILED·OVERFLOW·EXCLUDED) → pallet_log, ListPlacements | 남현지 | 10/13 | S2-T01 |
| S2-T08 | [팔레타이징] HMI: 경로 입력·3D 팔레트(4×2×2)·실을 수/초과/경로 제외·경고·진행률 | 남현지 | 10/14 | S2-T01, S2-T05 |
| S2-T09 | [음성] voss_launcher — 음성 시스템 기동·종료 (호출어·확인 대화·마이크 인계) | 정의석 | 10/13 | S2-T10 |
| S2-T10 | [음성·로봇] 기동 프로필: 수동 절차(g0-runbook)를 단계·준비 확인 스크립트로 묶기 | 정의석, 김학민 | 10/12 | — |
| S2-T11 | [인계] 리허설 중 검출·OCR 튜닝, 비전 코드 이슈 1차 대응 (남현지 T24 인계) | 박병후 | 10/14 | — |
| S2-T12 | [인계] 재확인·질문·보류 흐름 실기(흐린 송장 완주 3회), 시연 대본 운영·리허설 진행 (남현지 T23·T24 인계) | 김학민 | 10/14 | S2-T03 |
| S2-T13 | [PL] 시연 대본 v2(20개 박스, 단계 0·9), 결정 D3·D4·D6·D7, 게이트 판정·문서 갱신 | 남현지 | 10/13 | — |
| S2-T14 | [추종·파지] 하강·들기 사다리꼴 속도 프로파일 (3순위, 우선) | 박병후 | 10/13 | — |
| S2-T15 | [추종·파지] 온라인 벨트 속도 추정 (직선 맞춤, 단계 적용) (3순위, 우선) | 박병후 | 10/14 | — |
| S2-T16 | [비전] BoxTrack yaw 관측 (box_tracker 좌표 변환에 송장 각도 포함) (3순위, J6 선행) | 남현지 | 10/14 | — |
| S2-T17 | [로봇] gateway 회전 가속 10 → 90 deg/s² 이상·각속도 전달, 에뮬레이터 회전 기준점, 그리퍼-벨트 프레임 간섭 측정 (3순위, J6 선행) | 김학민 | 10/14 | — |
| S2-T18 | [추종·파지] J6 회전 파지 (TRACK 초반 회전, LIFT 원위치) (3순위, 후순위) | 박병후 | 10/14 | S2-T16, S2-T17 |
| S2-T19 | [인계] 로그·성공률 집계와 10/14 NFR-01~03 실측값 보고 (남현지 T23 인계, 10/12 PL 승인으로 박병후 → 정의석) | 정의석 | 10/14 | S2-T12, S2-T11 |
| S2-T21 | [로봇·1순위] A·B·C 트레이 칸 수 3 → 동별 7개 이상 (결정 D1, 20개 시연 선행) | 김학민 | 10/13 | — |
| S2-T22 | [음성·HMI] 투입 예정 수량 기본 20, "몇 개 남았어?"에 팔레타이징 결과 반영 (TR-PAL-12) | 정의석 | 10/14 | S2-T07 |

---

### S2-T01 · [통합] Sprint 2 인터페이스 변경안 (팔레타이징 v1.5·음성 기동) — docs/interfaces + voss_msgs 한 PR

labels: task, interface · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] BRD v1.5 10.7 표대로 docs/interfaces 를 먼저 고친다: voss_config.md(zones.pallet cols 4·lanes 2·layers 2·피치·층 높이 27, A·B·C 칸 수), voss_msgs.md(MoveToZone DROP·PALLET slot 0~15, Command palletize, Intent route, SortState PALLETIZING, PalletState·PalletResult·ListPlacements 신규, SortResult slot), intent_json.md(palletize), mqtt.md(voss/pallet/state), topics.md
- [ ] PALLET slot = (열−1)×4 + (층−1)×2 + (줄−1), z 오프셋 (층−1)×27 mm (결정 D2). v1.4안 cols 는 넣지 않음 — 이미 머지됐으면 지우지 말고 미사용 표시
- [ ] PalletResult 결과 DONE·FAILED·OVERFLOW·EXCLUDED, PalletState 에 구역별 실을 수·초과 수·경로 제외 수·경고
- [ ] voss_msgs 변경은 기존 메시지 끝에만 필드 추가. 한 PR 로 묶어 머지(전체 재빌드 1회)
- [ ] DB: sort_log.slot, pallet_log(미적재 행 포함) 스키마 — 정의석 리뷰

## 완료 기준 (측정 가능하게)
- interface 라벨 PR 머지, `colcon build` 전체 통과
- 각 파트 오너(김학민·정의석) 승인

## 관련 요구사항
TR-PAL-01~12, TR-VOICE-11~16 (BRD v1.5 10.7), CLAUDE.md 규칙 2

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T21 트레이 칸 수(D1)
- S2-T02 팔레트 피치 초안값

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T02 · [로봇] 팔레트 구역 좌표 교시·16칸 2층 도달성(ikin) 확인, 베이스 위치 재측정

labels: task · assignees: @rokeyhak, @lambdaramji

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak, 남현지 @lambdaramji

## 작업 내용
- [ ] 팔레트 트레이 중심을 record_pose 로 교시해 voss_config.yaml zones.pallet.pose 에 등록 (그림 계산값 사용 금지 — BRD 10.3 좌표 불일치)
- [ ] 4열 × 2줄 × 2층 = 16칸 ikin 해·자기 충돌 확인. 4열(문 쪽, 베이스 최근접)·2층부터 저속 실기 접근
- [ ] A·B·C → 팔레트 이동이 베이스 근처를 지나는지 확인하고 관절 이동 경유점 후보 기록
- [ ] 로봇 베이스 중심 위치를 다시 재서 measurements 에 기록(실측 16 cm/24 cm 와 설정 좌표 12·9 cm 차이 원인)
- [ ] RG2 손가락 두께 실측 → X·Y 피치(4 × 2)·놓을 때 개방 폭 제안(결정 5), 2층 놓기 때 손가락 끝 높이 확인(R-20)

## 완료 기준 (측정 가능하게)
- 16칸 모두 ikin 해 있음 또는 대안 배치 결정
- measurements 문서 PR

## 관련 요구사항
TR-PAL-06·07, R-18~21

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 로봇 시간 (스탠드업에서 확정)

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T03 · [로봇] MoveToZone PICK(재확인·팔레타이징 공용)·DROP 2층·PALLET slot 0~15·관절 경유점

labels: task · assignees: @rokeyhak

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak

## 작업 내용
- [ ] PICK: 기록된 zone·slot 위에서 pre_open → 하강 → 파지 → grip_detected 확인 → 안전 높이 (실패 GRIP_FAIL). 재확인 흐름(S2-T12)과 공용
- [ ] DROP: 칸 위 하강 → 최소 개방(박스 폭 + 여유) → 안전 높이 상승, OBSERVE 복귀 없음. 2층은 z +27 mm
- [ ] zone_motion: PALLET slot → (열, 층, 줄) → X·Y 피치·z 오프셋. 1열 = −X 끝. 순수 함수 단위 시험
- [ ] 베이스 근처 통과 구간은 관절 이동 경유점 사용

## 완료 기준 (측정 가능하게)
- A·B·C 각 칸 PICK 10회 성공
- 팔레트 16칸 DROP 각 1회 실기(2층 포함), 옆 박스 밀림·쓰러짐 0
- zone_motion 단위 시험 통과

## 관련 요구사항
TR-PAL-05~07

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01 인터페이스 머지
- S2-T02 좌표
- S2-T21 트레이 칸

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T04 · [팔레타이징] 배치 계획 순수 함수 pallet_plan (v1.5: 16칸 2층·초과 처리) + 단위 시험

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] 입력: route(첫 배송지부터), ListPlacements 목록. 출력: 구역별 실을 수·초과 수·경로 제외 수, 칸(slot 0~15)별 박스, 옮길 순서(= 칸 순서)
- [ ] 수량: 16개 이하면 전부, 넘으면 물량 많은 순(동률이면 먼저 방문하는 동이 후순위)으로 min(물량, 남은 칸)
- [ ] 위치: 수량과 따로, 마지막 방문 동부터 1열, 열 안 1층 2칸 → 2층 2칸
- [ ] 시험: 검증 프롬프트 v2 의 정답 생성기·S1~S8·불변식 6개(무작위 500회 이상)·입력 검증

## 완료 기준 (측정 가능하게)
- S1~S8 정답 일치(줄 대칭 허용)
- 불변식 500회 이상 통과
- colcon test 통과

## 관련 요구사항
TR-PAL-03·04

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T05 · [팔레타이징] sort_manager PALLETIZING 상태·palletize 명령·멈춤/재개·완료 안내

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] Command palletize 수신 → 시작 조건 검사(처리 중 박스 없음, 팔레트 비어 있음) → ListPlacements 로 대상 조회 → pallet_plan
- [ ] 계획 직후(첫 PICK 전) PalletState 발행: 칸 배정, 구역별 실을 수·초과·경로 제외, 초과 경고. 시작 TTS(순서·첫 배송지 위치)
- [ ] 칸 순서대로 PICK(최대 2회 재시도) → DROP → PalletResult 발행, 원래 구역 칸 비움. 미적재 박스는 OVERFLOW·EXCLUDED 로 기록하고 그대로 둠
- [ ] stop → PAUSED(진행 정보 유지), resume → 다음 칸부터. 든 채 멈춘 박스는 grip 확인 후 놓기/FAILED
- [ ] 완료 TTS: 구역별 실은 수, 초과로 못 실은 수, 경로 제외 수, 실패 박스

## 완료 기준 (측정 가능하게)
- 단독 시험(가짜 gateway)으로 전이 통과
- 실기: 게이트 기준(D3) 완주, 멈춤·재개 1회
- 10/13 18:00 게이트 판정

## 관련 요구사항
TR-PAL-02·05·06·08·10·11

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

### S2-T07 · [팔레타이징] 기록: SortResult.slot·sort_log.slot, PalletResult(DONE·FAILED·OVERFLOW·EXCLUDED) → pallet_log, ListPlacements

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] sort_manager 가 SortResult 에 slot 채움, sort_logger 가 sort_log.slot 기록
- [ ] sort_logger: /voss/pallet/result → pallet_log INSERT (미적재 박스도 사유와 함께 한 행), ListPlacements(session_id) 서비스
- [ ] DB 장애 시 ListPlacements 실패 → 팔레타이징 시작 거부(TR-PAL-03)

## 완료 기준 (측정 가능하게)
- 결과 1건 → sort_log.slot 기록
- S1 기준 pallet_log 19행(DONE 16 + OVERFLOW 3)
- ListPlacements 가 이동 여부 반영

## 관련 요구사항
TR-PAL-03·09

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T08 · [팔레타이징] HMI: 경로 입력·3D 팔레트(4×2×2)·실을 수/초과/경로 제외·경고·진행률

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] hmi_bridge: /voss/pallet/state → MQTT voss/pallet/state, voss/command palletize → Command
- [ ] React: 경로 입력, 시작 버튼, 3D 팔레트(트럭 머리 왼쪽·문 오른쪽, 계획 칸 배정 → 놓을 때마다 채움, 동별 색), 진행률(n개 중 m개)
- [ ] 계획 직후 구역별 실을 수·초과 수·경로 제외 수, 초과면 "배송 물량 남음" 경고
- [ ] 폴백(결정 D5): 3D가 늦으면 2D 배치도 + 진행률

## 완료 기준 (측정 가능하게)
- S1 계획·적재 이벤트 재생으로 3D 화면 확인
- HMI 버튼으로 1회 완주, 반영 ≤ 1초

## 관련 요구사항
TR-PAL-10

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T01
- S2-T05
- D5 담당 결정

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

### S2-T13 · [PL] 시연 대본 v2(20개 박스, 단계 0·9), 결정 D3·D4·D6·D7, 게이트 판정·문서 갱신

labels: task · assignees: @lambdaramji

## 파트 / 담당
비전·OCR·통합 / 남현지 @lambdaramji

## 작업 내용
- [ ] 박스 20개 구성(역삼·대치·청담 각 6 + 흐린 1 + 판별 불가 1)으로 8.1 대본의 박스 번호·투입 수를 다시 짬 (김학민 S2-T12 대본 운영과 함께)
- [ ] 단계 0(음성 기동)·9(팔레타이징) 문안. 9의 경로는 D4 (대치 → 역삼 → 청담이면 대치 3개 초과)
- [ ] D3 게이트 기준, D6 줄 순서, D7 NFR-07 "20개 중 16개" 전원 승인
- [ ] 10/13 18:00 게이트 판정·ADR 기록, plan.md·개발일정·BRD 반영

## 완료 기준 (측정 가능하게)
- 대본 v2 PR
- D3·D4·D6·D7 결정 기록
- 게이트 결정 기록

## 관련 요구사항
BRD v1.5 10.8·10.10·10.12

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

---

### S2-T21 · [로봇·1순위] A·B·C 트레이 칸 수 3 → 동별 7개 이상 (결정 D1, 20개 시연 선행)

labels: task, interface · assignees: @rokeyhak

## 파트 / 담당
로봇 제어·환경 설정 / 김학민 @rokeyhak

## 작업 내용
- [ ] 22 × 15 cm 트레이에 46 × 31 mm 박스 4 × 2 = 8칸 격자(X 4 · Y 2), zone_motion 칸 오프셋·voss_config grid 수정 (docs/interfaces 먼저)
- [ ] C 트레이는 수직 자세로 +X 도달 한계(10/08 ikin, 칸 +20 mm) — 4열이 안 되면 3 × 2 = 6칸(청담 6개와 같음)으로 두고 역삼(7)을 C 로 보내는 규칙 변경 금지 (R-31)
- [ ] sort_manager capacity 와 맞춤(남현지 리뷰)

## 완료 기준 (측정 가능하게)
- A·B 8칸·C 6칸 이상 PLACE·PICK 각 1회 실기
- 설정·문서 PR

## 관련 요구사항
TR-PICK-08, BRD v1.5 10.12, R-31

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- 없음

## 기한
10/13

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_

---

### S2-T22 · [음성·HMI] 투입 예정 수량 기본 20, "몇 개 남았어?"에 팔레타이징 결과 반영 (TR-PAL-12)

labels: task · assignees: @EuiseokJeongNZ

## 파트 / 담당
음성·웹·HMI / 정의석 @EuiseokJeongNZ

## 작업 내용
- [ ] HMI 투입 예정 수량 기본값 10 → 20
- [ ] /api/stats remaining_count 와 intent_parser 답변에 pallet_log 반영: 실은 박스는 남은 수에서 빼고, 구역에 남은 미적재 박스(OVERFLOW·EXCLUDED)는 넣음. 보류 포함 여부는 명세 미정 — 동작을 기록
- [ ] 정답 세트에 이력 질의 문장 추가

## 완료 기준 (측정 가능하게)
- S1 적재 후 "지금 박스 몇 개 남았어?" 답이 실제와 일치
- HMI 숫자와 음성 답 일치

## 관련 요구사항
TR-PAL-12, TR-VOICE-08

## 의존하는 것 (다른 파트에서 먼저 되어야 하는 것)
- S2-T07 pallet_log

## 기한
10/14

_Sprint 2 (10/12~10/14) · 출처: BRD v1.4 10장_
