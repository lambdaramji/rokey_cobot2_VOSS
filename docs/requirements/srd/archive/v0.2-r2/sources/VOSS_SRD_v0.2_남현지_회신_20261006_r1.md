# VOSS SRD v0.2 취합 회신서 — 남현지

**수신:** 남현지 · **취합:** 박병후
**담당 범위:** 비전·OCR·작업 관리자·설정·전체 통합
**대상 기능/노드 후보:** box_tracker, label_reader, sort_manager
**양식 버전:** v0.2 r1 · **기준일:** 2026-10-06(한국 시간) · **회신 버전:** r1

> 읽는 법: 상세는 §3 공통 인터페이스 카드(`IC-V-*`)와 §4 검증 카드(`VC-V-*`)에 한 번만 적고, 질문 답변은 카드를 참조합니다. **실측값은 아직 없습니다**(캘리브레이션은 김학민님이 측정 진행 중). 모든 수치는 목표/설정/실측을 구분해 표기했습니다.

## 0. 회신 정보·공통 기준

| 항목 | 답변 |
|---|---|
| 작성자·회신일·회신 버전 | 남현지 · 2026-10-06 · r1 |
| 확인한 코드/문서/장비 버전 | 레포 `main@668703e`(10/05) + 브랜치 `docs/10-interfaces-labelcrop-alias@386d632`(인터페이스 변경, **팀 승인 완료 10/06, main 반영 PR 대기**) + `feat/25-vision-belt-homography`(캘리브레이션 도구·ADR-0003). BRD v1.1(10/05). 공용 PC 사양은 회신 전달 내용(RTX 4060 Laptop 8 GB 등) 기준, measurements #5 미기록 |
| 구현됨/설계만/실측됨/미확인 범위 | **구현됨:** 픽셀→베이스 변환 순수 함수 `belt_plane.py`(pytest 6개, 가상 데이터만) · 캘리브레이션 계산 도구. **설계만:** box_tracker·label_reader·sort_manager(현재 골격). **실측됨:** 없음. **미확인:** 카메라 30 Hz·노출·GPU 컨테이너 실행 |
| 함께 확인한 담당자·확인 일시 | 김학민 — 10/06 오전, 캘리브레이션 방식(ADR-0003)·벨트 진행 방향(오른쪽)·관측 자세 담당. 그 외 상대와의 계약은 모두 **제안** |
| 추가 검토가 필요한 상대 | 박병후(IC-V-02·IC-V-05 액션·지연), 정의석(IC-V-06·07 명령·결과·DB 필드), 김학민(IC-V-08 설정 전달·재확인 구역 픽업) |

## 1. 담당 요구사항 검토

| 요구사항·단계 / 검증 ID | 검토 답변·검증 카드 연결 |
| --- | --- |
| SYS-FR-002 / A / VT-002 | **수용.** 카메라 header.stamp를 촬영 시각으로 끝까지 보존(IC-V-01). VC-V-01, 미수행·10/08(공용 PC) |
| SYS-FR-003 / A / VT-003 | **수용.** 중심 = bbox 중심(픽셀), bbox = x,y,w,h(IC-V-02). VC-V-01, 미수행·10/08 |
| SYS-FR-004 / A / VT-004 | **수용.** 공통 식별: 비전은 `track_id`, 관리자부터 `box_id`(투입 회차별)·`attempt`(IC-V-07). VC-V-03, 미수행·10/10 |
| SYS-FR-005 / A / VT-005 | **수용.** `LabelCrop`(track_id·stage·촬영 시각)으로 대응(IC-V-03, 팀 승인). VC-V-03, 미수행·10/10 |
| SYS-FR-006 / A / VT-006 | **수용.** 코드 우선 판정 + 기본 매핑 A/B/C(IC-V-04). VC-V-04, 미수행·10/07(정지 송장) |
| SYS-FR-007 / A / VT-007 | **수정제안(문장 유지, 방법 명시).** "합의한 로봇 좌표계" = 두산 베이스 좌표 mm, 관측 자세에서 벨트 평면 호모그래피(ADR-0003). 변환은 소비자(belt_servo·manager)가 공용 함수로 수행. VC-V-02, 미수행·10/06(측정 진행 중) |
| SYS-FR-018 / B / VT-018 | **수용.** start는 IDLE·PAUSED에서만 유효(IC-V-06). VC-V-05, 미수행·10/10 |
| SYS-FR-019 / B / VT-019 | **수용.** 정지 단계별 재개 규칙 IC-V-06 표. 이중 파지·이중 기록 방지 = box_id 단일 결과. VC-V-05, 미수행·10/10 |
| SYS-FR-020 / B / VT-020 | **수용.** priority(dong) / 전체 = priority(dong="")(IC-V-06, 정의석 확인 필요). VC-V-05 |
| SYS-FR-021 / B / VT-021 | **수용.** 1단계 OCR이 비대상이면 goal 미발행, outcome=`passed` 기록(변경 제안 NEW-V-02). VC-V-05 |
| SYS-FR-023 / B / VT-023 | **수용.** 2단계 프레임 선택은 box_tracker가 단독 판단(서보 신호 불필요), OCR은 별도 노드·컨테이너. VC-V-04 (3)(4)는 VC-V-01 지연 측정과 함께, 미수행·10/10 |
| SYS-FR-024 / B / VT-024 | **수용.** 규칙 IC-V-04. VC-V-04 |
| SYS-FR-025 / B / VT-025 | **수용.** `/voss/vision/read_label` 서비스(팀 승인). VC-V-05·VC-V-04, 미수행·10/12 |
| SYS-FR-026 / B / VT-026 | **수용.** 후보 1·2위 필드 필요 → NEW-V-01(LabelRead 확장). VC-V-05, 미수행·10/12 |
| SYS-FR-027 / B / VT-027 | **수용.** 유효 답 = 현재 질문의 후보 2개 + 보류(IC-V-06). VC-V-05 |
| SYS-FR-028 / B / VT-028 | **수용.** 30초 타이머 = 질문 발화 발행 시각 시작, 무효 응답으로 재설정 안 함(IC-V-06). VC-V-05 |
| SYS-FR-033 / A / VT-033 | **수용.** 단일 원본 `config/voss_config.yaml`, 쓰기는 sort_manager만(IC-V-08). VC-V-06, 미수행·10/09 |
| SYS-FR-034 / B / VT-034 | **수용.** 업무 오류/장비 오류 분리, SortResult `reason` 필드 필요 → NEW-V-02. VC-V-05 |
| SYS-OP-001 / C / VT-035 | **채택 제안.** 기본 흐름 승인 후 구현(10/11~13), 계약 V-08. VC-V-08, 미수행·10/13 |
| SYS-IF-001 / A / VT-037 | **수용.** IC-V-01~04 데이터 예시. 검사로 검증(VC-V-03) |
| SYS-IF-007 / A / VT-043 | **수용.** 소비자별 값·전달 경로 표 IC-V-08. VC-V-06 |
| SYS-PF-002 / B / VT-046 | **수용(BRD 목표).** 90% / 흐린 송장 제외 95%. VC-V-04, 미수행·10/10(추종 중)·10/14(리허설) |
| SYS-SF-004 / B / VT-056 | **수용.** 오류 분류표 IC-V-06. VC-V-05 |
| SYS-CT-002 / A / VT-061 | **수용.** 깊이 미사용, 박스 윗면 = 벨트+27 mm 평면(ADR-0003). VC-V-02 |
| SYS-PF-009 / B / VT-067 | **수용(BRD NFR-07).** 집계 규칙 VC-V-07. 미수행·10/15 |
| SYS-EN-001 / A / VT-068 | **수용(BRD 목표 5~8 ms).** 노출값 실측은 김학민 T33(measurements #9). VC-V-01 (5), 미수행·10/07 |

**성능 후보 처리(공통):** BRD 값만 요구사항으로 수용 — 검출 30 Hz(TR-PICK-02), 관측 지연 ≤100 ms(TR-PICK-03·NFR-06), 1차 OCR ≤300 ms(TR-OCR-01), OCR 90/95%(NFR-02). SRD v0.1의 **검출 ≤20 ms·크롭 OCR ≤100 ms는 요구사항이 아닌 비전 내부 예산**으로 두고 측정만 보고. **위치 오차 ≤5 mm는 제안값**(pending #4 승인 전, ADR-0003 검증점으로 측정).

## 2. 질문별 회신

### V-01 — 영상·검출 사양 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 영상 입력 / A | IC-V-01. `/camera/color/image_raw` sensor_msgs/Image, **설정** 1920×1080 rgb8 30 fps, 수동 노출 5~8 ms(**목표**, 값은 #9 실측 예정), 화이트밸런스 고정. 촬영 시각 = header.stamp. camera_info는 왜곡 보정 파라미터로만 사용(캘리브레이션 파일에 저장). **실측 없음** |
| 검출 출력 / A/B | IC-V-02. 방식은 **결정(10/06, 남현지, pending #7, ADR-0004)**(아래), 출력 계약은 방식과 무관. 주기 = 입력 프레임마다(목표 30 Hz). 검출 실패 프레임은 **발행하지 않음**(빈 메시지 없음). track_id 규칙 IC-V-07 |
| 첫 흐름 입력 / A | 명확한 송장 박스 1개(S07-02 대치동), 관측 자세 정지, 벨트 정지→저속 순. 정답 = (code S07-02, dong 대치동, zone B). 시험 영상은 10/06 촬영분 `data/recordings/`(레포 밖), 파일명 규칙은 촬영 후 공유 |
| BRD 확인 / A | BRD v1.1과 일치: 박스 46×31×27 mm, 송장 40×25 mm, 코드 5.5 mm, 매핑 S07-01 역삼/A, 02 대치/B, 03 청담/C(pending #15 결정). **변경 필요:** 벨트 진행 방향 = 오른쪽(상류 = 왼쪽·로봇 쪽) 명시. NFR-10(투입 위치와 대기 위치 분리) 확인 필요(김학민) |

**검출 방식 결정(pending #7, 결정 담당 남현지, 2026-10-06, ADR-0004):**
- 우리 조건: 박스 1종·한 번에 1개, 고정 벨트 배경, 손목 카메라(하강 시 크기 변화), 개인 PC GPU 없음, 2주.
- **1단계 — OpenCV 색·형태 분할을 먼저 구현:** 학습·라벨링이 없어 10/07에 A 흐름을 바로 연결할 수 있고, CPU에서도 수 ms 수준(추정)이라 개인 PC에서 녹화 재생으로 개발할 수 있음. 약점은 조명 변화·그리퍼 손가락·그림자.
- **2단계 — 분할 결과를 자동 라벨로 써서 YOLO nano를 Colab에서 학습:** 사람 라벨링은 검수만 하면 됨. 과제 필수 기술 "객체 탐지"(BRD 2.3)도 충족. 공용 PC에서 검출률·지연을 측정해(10/08) 기준을 넘으면 YOLO를 기본으로 하고 분할은 폴백으로 둠.
- 두 방식 모두 출력 계약(BoxTrack)은 동일하므로 상대 파트에는 영향이 없음.

A 상태: **확정(계약·방식)** — 영상·BoxTrack 필드·stamp 의미, 검출 방식(분할 우선 → YOLO 전환 판단) · B 상태: **미정** — 30 Hz·검출률·지연 실측(10/08 공용 PC) · C: 해당 없음
근거: BRD TR-PICK-01·02, NFR-13, `docs/interfaces/topics.md` · 미정 담당·예정일: YOLO 기본 채택 여부 남현지 10/08(공용 PC 측정 후), 노출값 김학민 10/07

### V-02 — 좌표 변환·캘리브레이션 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 좌표 경계 / A | box_tracker는 **픽셀만** 발행(BoxTrack 변경 없음). 픽셀→베이스 변환은 **소비자**(belt_servo, 필요 시 sort_manager)가 `config/belt_homography.yaml` + 공용 함수 `voss_vision.belt_plane.apply_homography`로 수행. 사유: 서보가 자기 루프 안에서 최신 pose와 함께 계산해야 하고, 변환 결과를 토픽으로 한 번 더 보내면 지연이 늘어남 |
| 변환 데이터 / A | 파일 `config/belt_homography.yaml`(스키마 `docs/interfaces/calibration.md`). 출력 단위 mm, 좌표계 = 두산 베이스(posx와 같은 축), z = `plane_z_mm`(박스 윗면) 고정. orientation 없음(파지 자세는 관측 자세의 rx, ry, rz 유지). 전달 = 읽기 전용 마운트 / launch 파라미터 경로 |
| RGB 위치 가정 / A | 깊이 미사용. 박스 윗면이 벨트+27 mm의 한 평면이라는 가정. **관측 자세에서만 유효.** 가정이 깨지는 경우(관측 자세 변경·카메라 해상도 변경·벨트 높이 변경)에는 재측정. 추종 중(카메라 이동) 좌표가 필요해지면 정식 핸드아이(10/07, 체커보드)로 보완 |
| 캘리브레이션 증거 / A/B | VC-V-02. 방법: 관측 자세 정지, 박스를 9곳(계산 6 + 검증 3)에 놓고 사진 + TCP 수직 터치 posx. **실측: 진행 중(김학민 10/06), 값 없음.** 가상 데이터 시험(클릭 ±2 px, 터치 ±0.5 mm)에서 검증점 최대 1.72 mm — 시뮬레이션이며 실측 아님. ≤5 mm는 **제안값** 수용(근거: 그리퍼 사전 개방 여유 ±22 mm 중 캘리브레이션 몫) |

A 상태: **확정(방식·파일 형식, 김학민 확인)**, 값 미정 · B 상태: **미정** — 정식 핸드아이 10/07, 박병후 사용 확인 필요 · C: 해당 없음
근거: ADR-0003, `tools/calib/fit_belt_homography.py`, `src/voss_vision/test/test_belt_plane.py` · 미정 담당·예정일: 측정값 남현지·김학민 10/06, 핸드아이 남현지 10/07

### V-03 — 식별·시간·크롭·OCR 단계 연결 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 식별자 / A | IC-V-07. track_id(비전, 화면에 박스가 새로 나타날 때 +1, 15프레임(0.5 s) 연속 미검출 시 만료) → box_id(sort_manager가 RUNNING에서 새 track_id를 처음 받을 때 발급, **투입 회차별**) → attempt(같은 box_id의 파지 시도 1~3). 물리 박스 번호는 시스템이 알 수 없으므로 시험 기록지에 사람이 기입. session_id = `start` 명령 시각(box_id 접두) |
| 촬영·처리 시각 / A | 촬영 시각 = 카메라 header.stamp(공용 PC 시스템 시계, 컨테이너도 같은 호스트 시계). BoxTrack.stamp·LabelCrop.header.stamp·LabelRead.stamp(제안) 모두 **원본 프레임 촬영 시각**. 발행·수신 시각은 메시지에 넣지 않고 각 노드 지연 로그(CSV)에 기록 |
| 크롭과 단계 연결 / A/B | **팀 승인된 변경:** `/voss/vision/label_crop` 타입 Image → `voss_msgs/LabelCrop`(header, track_id, stage, sharpness, image). stage는 box_tracker가 `/voss/sort/state`로 결정(RUNNING→1, PICKING→2). 예시 IC-V-03 |
| 2·3단계 요청 / B | 2단계: **별도 신호 없음** — box_tracker가 PICKING 중 박스가 화면 목표점 근처(수렴 구간)이고 선명도가 높은 프레임 3~5장을 골라 보냄. 서보(박병후)에 추가 요구 없음. 3단계: sort_manager → label_reader `/voss/vision/read_label`(srv/ReadLabel, 팀 승인), 재확인 구역에 놓은 뒤 호출 |
| 오래된 결과 / A/B | sort_manager는 LabelRead를 `track_id == 현재 박스` **그리고** `stamp ≥ 해당 단계 시작 시각`일 때만 채택. 이전 박스·이전 단계 결과는 버리고 로그만 남김. 2단계 중복은 다수결 표로 흡수. 3단계는 서비스 응답만 채택(토픽 사본은 HMI·로그용). 시간 역전(stamp가 앞선 메시지가 늦게 도착)은 stamp 기준으로 판단 |

A 상태: **확정(LabelCrop·read_label 팀 승인)**, LabelRead.stamp 추가는 제안(NEW-V-01) · B 상태: **미정** — 2단계 선택 기준값(선명도 임계·프레임 수) 10/10 튜닝 · C: 해당 없음
근거: 브랜치 `docs/10-interfaces-labelcrop-alias`(`LabelCrop.msg`, `ReadLabel.srv`) · 미정 담당·예정일: 남현지 10/10

### V-04 — OCR 판정·후보·재판독 계약 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| OCR 출력 / A/B | IC-V-04. 현재 LabelRead(track_id, code, dong, confidence, stage) + **제안 NEW-V-01**: stamp, raw_text(원문), dong_alt·confidence_alt(2위 후보) |
| 판정 규칙 / A/B | confidence ∈ [0, 1]. 코드: 정규식 `S?0?7-0[1-3]` 계열 정규화 후 끝 두 자리로 동 결정. 동: 등록 동·별칭 목록(zone_map)과 편집거리 퍼지 매칭, 점수 = 1 − 거리/길이. 코드·동 일치 → max(두 점수 × OCR 엔진 점수). 불일치 → **코드 우선**, 신뢰도 × 0.5(TR-OCR-05). 둘 다 후보 없음 → code="", dong="", confidence=0. 임계 `ocr.confidence_min` = **0.6(설정값, 미튜닝)**, 10/07 정지 송장 50장으로 조정 |
| 단계별 조건 / B | 1단계: RUNNING에서 박스가 송장을 읽을 수 있는 크기로 보이면 1회(목표 ≤300 ms). 2단계: PICKING 수렴 구간 3~5프레임 다수결(동 기준, 득표 수/프레임 수를 신뢰도에 곱함), 파지 완료 시 마감. 3단계: read_label(max_frames 기본 5, timeout 기본 2.0 s). goal 취소 시 2단계 표 폐기 |
| 성능 후보 / B | 1차 ≤300 ms: **수용(BRD 목표)**. 크롭 ≤100 ms: **내부 예산(요구사항 아님)**. 서보 독립 실행: **수용** — label_reader는 별도 노드(비전 컨테이너), 서보 루프는 호스트. 측정 미수행(VC-V-01·04) |
| 연동 상대 / B | 박병후: 2단계 OCR을 위해 서보에 요구하는 추가 신호 없음. 다만 수렴 구간에서 박스가 화면 안에 0.3 s 이상 머무는 것이 필요(추정, 10/10 확인). 정의석: 질문 문장은 sort_manager가 `/voss/voice/say`로 완성된 문장으로 보내고, 후보는 SortState.pending_question에 표시(IC-V-06) |

A 상태: **확정 제안** — 명확한 송장의 코드 우선 판정 · B 상태: **미정** — 임계값 튜닝·후보 필드(NEW-V-01) 정의석 확인 · C: 해당 없음
근거: BRD TR-OCR-01~07, `config/voss_config.yaml` ocr · 미정 담당·예정일: 남현지 10/07(임계), 10/10(2단계)

**OCR 엔진(참고):** PaddleOCR 한국어 모델 우선(TR-OCR-04). 10/07 T18에서 정지 송장 50장으로 검증하고 결과를 ADR로 남김. **VLM API 폴백은 기본 흐름에서 미사용 제안** — 3단계 재판독과 작업자 질문으로 이미 저신뢰가 처리되고, 외부 API 지연·비용·인터넷 의존이 늘기 때문. 10/10 OCR 정확도가 목표에 못 미치면 재검토.

### V-05 — 관리자 동작·예외·정지·재개 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 상태·이벤트 / A/B | 6상태 **수용**(일렬 전이 아님). 전이표와 상태별 허용 명령 IC-V-06 |
| 작업 명령 / A/B | IC-V-06. `/voss/sort/command` 응답(≤200 ms)은 **접수 의미**(ok = 현재 상태에서 유효), 완료는 SortState·SortResult로 알림 |
| 예외 응답 / B | IC-V-06 "질문 처리". 유효 = 후보 1·2위 동 이름 또는 "보류". 질문 ID = box_id. 무효 → 1회 재안내, 타이머 유지. 30 s 만료 → hold. 만료 후 늦은 응답 → 무시 + 안내 |
| 정지·재개 / A/B | IC-V-06 정지 표. stop = 소프트웨어 정지(안전 등급 아님, 최종 수단은 티치펜던트 비상정지) |
| 업무/장비 오류 / A/B | IC-V-06 오류 분류. 업무 오류는 재시도·재확인·질문·보류로 계속, 장비 오류는 PAUSED + 음성·HMI 알림 |

A 상태: **확정 제안** — IDLE→RUNNING→PICKING→적재→RUNNING 기본 전이 · B 상태: **미정** — 정지·재개 세부는 박병후(액션 취소 동작)·김학민(이동 정지) 확인 필요 · C: 해당 없음
근거: BRD TR-SYS-01·02, TR-OCR-06·07, TR-VOICE-05·07 · 미정 담당·예정일: 남현지 10/08(FSM 초안 pytest), 상대 확인 10/08

### V-06 — 설정의 읽기·쓰기·전달 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 단일 설정 기준 / A | IC-V-08. 원본 `config/voss_config.yaml`(version 필드, 레포 관리). 호스트 `~/voss_ws/config/`에 복사, 비전 컨테이너 읽기 전용 마운트. **런타임 쓰기 = sort_manager만**(zone_map 변경, C). 초기 좌표·속도·힘은 사람이 실측 후 PR로 입력(김학민, measurements-1006.md 근거). 미측정 값은 0이 아니라 **null**로 두고 sort_manager가 기동 시 거부(제안) |
| 소비자별 값 / A | IC-V-08 표 |
| 전달 방법 / A | 런타임 변경 값(동→구역, 코드, 별칭) = `/voss/sort/zone_map`(transient_local, 팀 승인으로 code·aliases 추가). 정적 값(구역 좌표·관측 자세·벨트 속도·그리퍼·지연 오프셋·캘리브레이션 파일 경로) = **bringup launch가 YAML을 읽어 노드 파라미터로 전달**(제안, 노드가 파일을 직접 읽지 않음) |
| 일관성 / A/B | 늦게 뜬 노드는 transient_local로 마지막 zone_map 수신. ZoneMap.version = YAML version + 변경 회차. 재기동 시 sort_manager가 YAML을 다시 읽어 재발행. 설정 누락(null) → 기동 실패 로그. **QoS 충돌 해소 제안:** `/voss/sort/state`는 topics.md대로 reliable·volatile(≥2 Hz 주기 발행이라 늦은 노드도 0.5 s 안에 받음), conventions.md의 "상태도 transient_local" 문구를 수정 |

A 상태: **확정 제안** — 김학민 확인 필요(gateway 구역 좌표 전달) · B 상태: 해당 없음(런타임 변경은 C) · C: 채택 제안(V-08)
근거: `docs/interfaces/voss_config.md`, BRD TR-SYS-06 · 미정 담당·예정일: launch 전달 방식 남현지·김학민 10/08

### V-07 — 처리 결과·식별·집계 의미 (A)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 결과 확정 / A | box_id마다 **SortResult 1건**. 발행 시점 = 최종 위치에서 그리퍼 개방 성공 응답 직후(복귀 전). held·failed·passed도 해당 처리가 끝난 시점에 1건. DB 저장 완료는 sort_logger 책임이며 sort_manager는 저장 완료를 기다리지 않음(로거는 box_id 유일키로 멱등 저장 제안) |
| 필드 의미 / A | IC-V-07 표. 원문은 NEW-V-02(raw_text 추가) |
| 중복/재투입 / A/B | 재투입 = 새 box_id. 파지 재시도 = 같은 box_id의 attempt 증가(결과 1건). passed(비대상 통과)는 처리 수에 포함하지 않음. 남은 수 = 투입 예정 수 − (placed + held + failed)(제안, 정의석 TBD-008과 합의 필요) |
| 예시 / A/B | IC-V-07 예시 4건(제안) |
| DB 상대 확인 / A | **미확인(정의석)**. 필요한 것: box_id 유일키, raw_text·reason·attempts 추가 필드(NEW-V-02) |

A 상태: **확정 제안** — placed 1건 발행 · B 상태: **미정** — held/failed/passed 집계·NEW-V-02 정의석 확인 · C: 해당 없음
근거: BRD TR-SYS-04, NFR-07, TR-PICK-07 · 미정 담당·예정일: 정의석 확인 10/08

### V-08 — 선택 매핑 변경 (C)

| 답변 항목·단계 | 답변·카드 참조 |
| --- | --- |
| 채택 상태 / C | **채택 제안.** BRD 8.1 시연 4단계이고 sort_manager 쪽 작업량이 작음. 단, 최초 전체 흐름(A) 완주 이후 10/11부터 구현 |
| 채택 시 계약 / C | 입력: Intent(type=update_zone_map, dong, zone) 또는 `/voss/sort/update_zone_map`(entries[]). 교환("역삼 B, 대치 A")은 entries 2개를 **한 번에 원자 적용**. 검증: 동·구역이 허용 목록에 있어야 함, 아니면 ok=false. 적용 시점: **다음에 구역을 결정하는 박스부터**(이미 PICKING 중인 박스는 결정된 구역 유지). 확인: say "역삼동은 B구역, 대치동은 A구역으로 바꿨습니다" + zone_map 재발행(version +1). 저장: YAML 임시 파일 작성 후 교체, 직전 파일 백업. 저장 실패 → 메모리 매핑 원복 + ok=false |
| 영향 / C | 기본 적재·OCR: 영향 없음(zone_map 구독만). intent: update_zone_map 유형(정의석). HMI: zone_map 표시. 로그: SortResult.zone이 변경 후 구역. 예상 작업량: sort_manager 0.5일(추정) |

A: 해당 없음 · B: 해당 없음 · C: **채택 제안**
근거: BRD 2.4·8.1 4단계, TR-VOICE-09 · 미정 담당·예정일: 채택 결정 팀 10/11(기본 흐름 완주 후)

## 3. 인터페이스 카드

### 커버리지

| 관련 IC-ID / 연결 | 역할 | 카드 ID / 상태 |
| --- | --- | --- |
| IC-VISION-01 / camera→box_tracker | 주 작성 / 남현지 | IC-V-01 |
| IC-VISION-02 / box_tracker→manager/servo | 주 작성 / 남현지 | IC-V-02 (박병후 확인 필요) |
| IC-VISION-03 / box_tracker→label_reader | 주 작성 / 남현지 | IC-V-03 (팀 승인) |
| IC-VISION-04 / label_reader→manager | 주 작성 / 남현지 | IC-V-04 (+ IC-V-04b read_label, 팀 승인) |
| IC-PICK-01 / manager↔servo | 주 작성 / 남현지 | IC-V-05 (박병후 확인 필요, B-01 회신과 대조) |
| IC-ROBOT-03 / manager/servo↔gateway | 상대 확인 / 김학민 | IC-V-05·06의 호출 주체 제안: 파지 중 그리퍼 닫기 = servo, 적재 이동·개방·재확인 구역 픽업 = manager. **재확인 구역에서 다시 집는 동작 필요**(MoveToZone이 집기 높이를 지원해야 함) — 김학민 R-02/R-04 회신과 대조 |
| IC-CMD-01 / 음성/HMI→manager | 상대 확인 / 정의석 | IC-V-06 명령 표. 전체 분류 = priority(dong=""), 이력 질의는 manager가 아닌 Stats 경로(정의석 TBD-008) |
| IC-VOICE-01 / manager→speech_out | 상대 확인 / 정의석 | 차이: manager가 **완성된 한국어 문장**을 String으로 발행(예시 IC-V-06). 발화 우선순위·중복 억제는 speech_out 결정 |
| IC-STATE-01 / manager→HMI | 주 작성 / 남현지 | IC-V-06 (SortState) |
| IC-RESULT-01 / manager→logger/HMI | 주 작성 / 남현지 | IC-V-07 |
| IC-CONFIG-01 / 설정→각 소비자 | 주 작성 / 남현지 | IC-V-08 |
| IC-STATS-01 / 조회 기능→음성/HMI | 상대 확인 / 정의석 | 차이: `/voss/sort/stats` 서비스는 현재 sort_manager 제공 후보. **제안: DB 기준 조회는 정의석 측이 담당, manager의 Stats는 현재 세션 메모리 집계(백업용)** — 정의석 TBD-008 결정에 따름 |
| IC-DB-01 / logger↔DB/조회 | 상대 확인 / 정의석 | IC-V-07 필드를 그대로 저장, 유일키 box_id. DB 종류는 정의석 결정 |
| IC-OPTION-01 / 명령↔설정/로봇 | 주 작성 / 남현지 | V-08 표로 대체(채택 제안) |

### IC-V-01 — camera → box_tracker

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC / 질문·TBD | IC-V-01 / IC-VISION-01 / V-01·V-03, TBD-001·003 |
| 상태 | 기존 유지(외부 드라이버). 설정값만 제안 |
| 생산자 → 소비자 | realsense2_camera(bringup, 김학민) → box_tracker(남현지) |
| 이름 / 타입 | `/camera/color/image_raw` sensor_msgs/Image, `/camera/color/camera_info` |
| 필드 / 범위 | 1920×1080, rgb8, 30 fps(설정). 수동 노출 5~8 ms 목표, 화이트밸런스 고정 |
| 식별·시각 | header.stamp = 촬영 시각(호스트 시계), frame_id = 카메라 광학 프레임(사용 안 함) |
| QoS | 드라이버 기본(sensor data, best_effort) |
| 실패 | 1 s 이상 프레임 없음 → box_tracker 경고 로그, manager는 장비 오류로 PAUSED(IC-V-06) |
| 실행 위치 | 공용 PC 호스트, USB 3.0 |
| 상대 변경 | 김학민: launch 인자로 해상도·노출·화이트밸런스 고정(SYS-EN-001) |
| A / B / C | A 확정 제안 / B 실측(30 Hz·노출) 10/07~08 / C 해당 없음 |

### IC-V-02 — box_tracker → sort_manager, belt_servo

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC / 질문·TBD | IC-V-02 / IC-VISION-02 / V-01·V-02·V-03, TBD-001·002·003 |
| 상태 | 기존 유지(필드 변경 없음), 의미만 명시 |
| 생산자 → 소비자 | box_tracker(남현지) → sort_manager(남현지), belt_servo(박병후) |
| 이름 / 타입 | `/voss/vision/box` voss_msgs/BoxTrack |
| 필드 | track_id(int32, ≥1), u·v(float32 px, bbox 중심, 원본 1920×1080 기준, 왜곡 보정 전), bbox(int32[4] x,y,w,h px), stamp(원본 프레임 촬영 시각) |
| 단위 변환 | 픽셀→mm는 소비자가 `belt_homography.yaml`로(V-02) |
| 주기 / QoS | 검출된 프레임마다(목표 30 Hz). best_effort, volatile, depth 1 |
| 실패 | 미검출 프레임은 발행 없음. 소비자는 stamp 기준 오래된 값(예: 100 ms 초과) 무시 — 임계는 박병후 TBD-020 |
| 중복·순서 | 한 번에 박스 1개 전제. 2개 이상 보이면 가장 큰 박스만 발행하고 경고 로그 |
| 실행 위치 | 비전 컨테이너(`--network host`) |
| 상대 변경 | 박병후: 오래된 데이터 임계·지연 오프셋(`timing.latency_offset_ms`) 사용 확인 |

```yaml
# /voss/vision/box (예시)
track_id: 7
u: 1012.5
v: 540.0
bbox: [782, 375, 461, 330]
stamp: {sec: 1791264012, nanosec: 133000000}
```

### IC-V-03 — box_tracker → label_reader (팀 승인 10/06)

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC | IC-V-03 / IC-VISION-03, TBD-003·004 |
| 상태 | **변경**: Image → voss_msgs/LabelCrop. 팀 승인 10/06, main 반영 PR 대기(브랜치 `docs/10-interfaces-labelcrop-alias`) |
| 생산자 → 소비자 | box_tracker → label_reader (둘 다 남현지, 같은 컨테이너) |
| 필드 | header(stamp = 원본 촬영 시각), track_id, stage(1/2/3), sharpness(float, 클수록 선명), image(송장 영역 크롭, 전처리 전) |
| 발행 조건 | stage 1: RUNNING 중 송장 판독 가능한 크기·선명도일 때 1~2장. stage 2: PICKING 수렴 구간 3~5장. stage 3는 read_label 서비스가 내부에서 처리 |
| QoS | reliable, volatile, depth 5 |

```yaml
# /voss/vision/label_crop (예시, image 생략)
header: {stamp: {sec: 1791264012, nanosec: 133000000}, frame_id: camera_color_optical_frame}
track_id: 7
stage: 1
sharpness: 412.3
image: {height: 300, width: 480, encoding: rgb8, ...}
```

### IC-V-04 — label_reader → sort_manager (+ IC-V-04b read_label)

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC | IC-V-04 / IC-VISION-04, TBD-003·004 |
| 상태 | 기존 LabelRead 유지 + **NEW-V-01 필드 추가 제안**. read_label 서비스는 팀 승인 |
| 이름 / 타입 | `/voss/vision/label` voss_msgs/LabelRead · `/voss/vision/read_label` srv/ReadLabel(track_id −1 = 아무 박스, max_frames 0=5, timeout_s 0=2.0 → ok, label(stage 3), message: timeout/no_box/no_text) |
| 필드(현행) | track_id, code("S07-02", 정규화), dong("대치동", 등록 이름), confidence 0~1, stage |
| 필드(제안) | stamp, raw_text(OCR 원문 그대로, 줄바꿈 \n), dong_alt·confidence_alt(2위 후보, 없으면 ""·0) |
| QoS | reliable, volatile, depth 10 |
| 상대 변경 | 정의석: HMI OCR 결과 표시에 raw_text·confidence 사용 가능 |

```yaml
# /voss/vision/label (예시, NEW-V-01 반영 시)
track_id: 7
code: "S07-02"
dong: "대치동"
confidence: 0.91
stage: 1
stamp: {sec: 1791264012, nanosec: 133000000}   # 제안
raw_text: "S07-02\n대치동\n받는분 홍길동"         # 제안
dong_alt: "청담동"                               # 제안
confidence_alt: 0.12                             # 제안
```

### IC-V-05 — sort_manager ↔ belt_servo (TrackAndGrasp)

| 항목 | 답변 |
|---|---|
| 카드 ID / SRD IC | IC-V-05 / IC-PICK-01, TBD-019 (주 결정은 박병후 B-01) |
| 상태 | 기존 액션 유지. 의미는 **제안**(박병후 확인 전) |
| 이름 / 타입 | `/voss/servo/track_and_grasp` voss_msgs/action/TrackAndGrasp |
| goal | track_id(1단계 OCR로 대상 확정된 박스) |
| feedback | err_u, err_v(px), phase(approach/track/descend/grasp) — manager는 로그·HMI 표시용으로만 사용 |
| result | grasped(bool), reason(제안 값: ok / lost / timeout / grasp_fail / canceled / robot_error) |
| 그리퍼 | 파지 단계의 닫기는 servo가 gateway에 요청, 들어 올린 상태로 result 반환(제안) |
| 재시도 | manager가 판단: grasp_fail·lost이고 박스가 아직 보이면 같은 box_id로 attempt +1, 최대 2회 재시도(TR-PICK-07). robot_error는 재시도 없이 장비 오류 |
| cancel | stop 명령 시 manager가 cancel. **취소 수락 ≠ 로봇 정지 완료** — servo는 속도 명령 0 발행 후 결과 canceled 반환(제안), 실제 정지는 gateway가 보장(김학민 TBD-017) |
| A/B 전환 | 10/10 게이트로 B안이 돼도 이 계약은 동일(ADR-0002) |

### IC-V-06 — sort_manager 상태·명령·질문·오류 (IC-STATE-01, IC-CMD-01 대조, IC-VOICE-01 대조)

**상태별 허용 명령·전이(제안)**

| 상태 | 의미 | start | stop | resume | priority / 전체 | answer | 다음 상태(주요 이벤트) |
|---|---|---|---|---|---|---|---|
| IDLE | 대기 | ✔ → RUNNING(관측 자세 이동) | 무시(ok) | ✗ | ✔ 저장만 | ✗ | — |
| RUNNING | 관측·1단계 판독 | ✗(이미 운전) | ✔ → PAUSED | ✗ | ✔ 다음 박스부터 | ✗ | 대상 확정 → PICKING / 비대상 → passed 기록 후 RUNNING |
| PICKING | 추종·파지·적재 | ✗ | ✔ → PAUSED(goal 취소) | ✗ | ✔ 다음 박스부터 | ✗ | 적재 완료 → RUNNING / 저신뢰 → 재확인 구역 적재 후 RECHECK / 재시도 초과 → failed |
| RECHECK | 재확인 구역 재판독 | ✗ | ✔ → PAUSED | ✗ | ✔ | ✗ | 확정 → 목적 구역 이동 → RUNNING / 미확정 → ASKING |
| ASKING | 작업자 답 대기(30 s) | ✗ | ✔ → PAUSED(타이머 정지) | ✗ | ✗ | ✔ 후보·보류만 | 유효 답 → 이동 → RUNNING / 만료 → hold → RUNNING |
| PAUSED | 정지 | ✗ | 무시(ok) | ✔ 아래 표 | ✔ 저장만 | ✗ | resume → 이전 상태 규칙 |

**정지 단계별 재개(제안)**

| 정지 시점 | 정지 시 처리 | resume 시 |
|---|---|---|
| RUNNING(벨트 위 박스 미파지) | 대기 | RUNNING 재개. 정지 중 지나간 박스는 passed(reason=stopped), 작업자 재투입 |
| PICKING 추종 중(미파지) | goal cancel | 박스가 아직 보이면 새 attempt, 아니면 passed(stopped) |
| PICKING 파지 후 이동 중 | gateway 정지 요청 | 구역 확정이면 같은 구역으로 이동 계속, 아니면 재확인 구역 |
| RECHECK | 재판독 중단 | 재판독 처음부터 |
| ASKING | 타이머 정지 | 질문 다시 발화, 타이머 30 s 새로 시작 |

**질문 처리:** 질문 대상 = 현재 box_id 하나. 30 s 타이머는 질문 문장을 `/voss/voice/say`로 발행한 시각부터. 유효 답 = 후보 1·2위의 동 이름 또는 "보류". 무효 답 → "역삼동, 청담동, 보류 중에 말씀해 주세요" 1회 재안내, 타이머 재설정 없음. 만료 후 도착한 답 → 무시 + "이미 보류 구역에 놓았습니다" 안내.

**오류 분류(SYS-SF-004·FR-034):**

| 구분 | 오류 | 처리 |
|---|---|---|
| 업무 오류(계속 운전) | OCR 저신뢰·불일치 | 재확인 → 질문 → 보류 |
| | 파지 실패·추적 상실(lost) | 최대 2회 재시도 → failed |
| | 질문 무응답 | hold |
| | 비대상 박스 | passed |
| 장비 오류(PAUSED + 알림) | gateway 서비스 실패·timeout, 액션 result=robot_error, 카메라 1 s 이상 무입력, 비전 노드 부재 | 진행 중 박스는 결과 보류, 작업자 확인 후 resume |

```yaml
# /voss/sort/state (예시, ASKING)
state: "ASKING"
box_id: "1006T0930-009"
pending_question: "역삼동|청담동"   # 후보를 | 로 구분 (제안)
---
# /voss/voice/say (예시)
data: "라벨이 번져서 역삼동인지 청담동인지 불확실합니다. 어디로 보낼까요?"
---
# /voss/sort/command 요청·응답 (예시)
{command: "priority", arg: "대치동"}   → {ok: true,  message: "대치동부터 분류합니다"}
{command: "resume",   arg: ""}         → {ok: false, message: "지금은 운전 중입니다"}
```

### IC-V-07 — 처리 결과·식별 (IC-RESULT-01, IC-DB-01 대조)

| 필드 | 의미(제안) |
|---|---|
| box_id | 투입 회차별 유일 ID. `<세션 시작 MMDD'T'HHMM>-<3자리 순번>`, 예 `1006T0930-007` |
| code / dong | 최종 판정(정규화). 작업자 결정이면 작업자 답 |
| confidence | 최종 판정에 쓴 OCR 신뢰도(작업자 결정이면 마지막 OCR 값 유지) |
| decided_by | ocr(1·2단계) / recheck(3단계) / operator(작업자 답) |
| zone | 실제 놓은 구역 A/B/C/recheck/hold. passed면 "" |
| outcome | placed / held / failed + **passed 추가 제안**(NEW-V-02) |
| stamp | 결과 확정 시각 |
| raw_text·reason·attempts | **추가 제안**(NEW-V-02): OCR 원문, 실패·보류 사유(low_conf / no_answer / grasp_fail / lost / stopped / non_target), 파지 시도 횟수 |

```yaml
# 정상 적재 (제안 필드 포함)
{box_id: "1006T0930-004", code: "S07-02", dong: "대치동", confidence: 0.93, decided_by: "ocr",
 zone: "B", outcome: "placed", raw_text: "S07-02\n대치동", reason: "", attempts: 1}
# 질문 무응답 보류
{box_id: "1006T0930-009", code: "S07-0?", dong: "", confidence: 0.41, decided_by: "recheck",
 zone: "hold", outcome: "held", raw_text: "S07-0\n?삼동", reason: "no_answer", attempts: 1}
# 최종 파지 실패
{box_id: "1006T0930-005", code: "S07-01", dong: "역삼동", confidence: 0.88, decided_by: "ocr",
 zone: "", outcome: "failed", raw_text: "S07-01\n역삼동", reason: "grasp_fail", attempts: 3}
# 비대상 통과 (대치동 우선 중 역삼동 박스)
{box_id: "1006T0930-002", code: "S07-01", dong: "역삼동", confidence: 0.90, decided_by: "ocr",
 zone: "", outcome: "passed", raw_text: "S07-01\n역삼동", reason: "non_target", attempts: 0}
```

### IC-V-08 — 설정 → 각 소비자 (IC-CONFIG-01)

| 소비자 | 필요한 값 | 전달 경로(제안) |
|---|---|---|
| sort_manager | 전체(zone_map·aliases·codes·zones·ocr·belt) | YAML 직접 읽기·쓰기(유일) |
| belt_servo(박병후) | belt.speed_cmps·direction_axis, timing.latency_offset_ms, observe_pose, gripper.pre_open_mm, 캘리브레이션 파일 경로 | launch 파라미터(정적) |
| robot_gateway(김학민) | zones.*.pose·grid, observe_pose, gripper.force_n·grasp_width_mm | launch 파라미터(정적). 신규 구역 교시(C) 채택 시 재전달 방식 별도 |
| box_tracker·label_reader | zone_map(코드·동·별칭), 캘리브레이션 파일 경로 | zone_map 토픽 + 파라미터 |
| intent_parser(정의석) | 동·구역·별칭 허용 목록 | zone_map 토픽(팀 승인: code·aliases 추가) |
| hmi_bridge(정의석) | 동→구역 매핑 | zone_map 토픽 |

```yaml
# /voss/sort/zone_map (예시, 팀 승인 필드)
version: "1.0"
entries:
  - {dong: "역삼동", zone: "A", code: "S07-01", aliases: ["역삼", "역삼동"]}
  - {dong: "대치동", zone: "B", code: "S07-02", aliases: ["대치", "대치동"]}
  - {dong: "청담동", zone: "C", code: "S07-03", aliases: ["청담", "청담동"]}
```

## 4. 검증 카드

| 카드 | 관련 SYS / VT | 방법·조건 | 횟수·분모 | 합격 기준 | 상태·증거 |
|---|---|---|---|---|---|
| **VC-V-01** 영상·검출·지연 | FR-002·003, EN-001 / VT-002·003·068, (PF-007 VT-051 참여) | 시험(실기 영상). 공용 PC GPU 컨테이너, 녹화 재생 + 실시간. 측정점: 카메라 stamp → BoxTrack 발행 → 서보 수신(박병후 로그) | 박스 통과 영상 20회, 프레임 단위 | 30 Hz 유지·관측 지연 ≤100 ms(BRD 목표). 검출률 ≥99%는 T17 완료 기준(내부). 노출 5~8 ms 설정 확인 | **미수행** · 10/08 · 남현지 · 지연 CSV·영상 |
| **VC-V-02** 좌표 변환 | FR-007, CT-002 / VT-007·061 | 시험(실기). 관측 자세, 계산점 6·검증점 3, TCP 수직 터치 | 검증점 3(+10/07 추가) | 검증점 최대 오차 ≤5 mm(**제안값**), 평균 함께 보고 | **측정 진행 중(김학민)** · 10/06 · 증거 `config/belt_homography.yaml`, measurements #7, 사진. 가상 시험 최대 1.72 mm(시뮬레이션, 판정에 안 씀) |
| **VC-V-03** 식별·크롭 연결 | FR-004·005, IF-001 / VT-004·005·037 | 검사 + 시험(녹화 재생). 박스 3개 연속, LabelCrop·LabelRead·SortResult의 track_id·box_id 대조 | 박스 10개 | 잘못 연결 0건 | 미수행 · 10/10 · rosbag·로그 |
| **VC-V-04** OCR 정확도 | FR-006·023·024, PF-002 / VT-006·023·024·046 | 시험. (1) 정지 송장(실기 카메라, 관측 자세) (2) 추종 중 (3) 단계·식별 일치 (4) OCR 실행 중 서보 주기 영향 | (1) 50장(T18) (2) 50장(T19) — 흐린 송장 포함/제외 분모 별도 | 분류코드 정답률 ≥90%, 흐린 송장 제외 ≥95%(BRD). 정답 = 송장 인쇄값 | 미수행 · (1) 10/07 (2) 10/10 · 결과 CSV |
| **VC-V-05** 관리자 FSM·예외 | FR-018~021·025~028·034, SF-004 / VT-018~021·025~028·034·056 | 단독 시험(모의): 순수 함수 전이표 pytest + fake_servo·mock 서비스. 이후 실기 흐린 송장 완주 | 전이표 전 행 1회 이상, 흐린 송장 완주 3회(T23) | 기대 전이·기록 일치, 이중 파지·이중 기록 0 | 미수행 · 모의 10/10, 실기 10/14 · pytest 리포트·로그 |
| **VC-V-06** 설정 일관성 | FR-033, IF-007 / VT-033·043 | 시험(모의): 늦게 뜬 구독자가 zone_map 수신, 재기동, null 값 거부 | 각 1회 | 모든 소비자 값 일치 | 미수행 · 10/09 |
| **VC-V-07** 시연 완주 | PF-009 / VT-067 | 시연(실기) BRD 8.1 8단계. 분모 = 물리 박스 10개(시험 기록지로 box_id↔물리 번호 대응). passed는 재투입 후 최종 결과로 집계, 흐린 송장은 유효 응답 후 올바른 적재 시 성공 | 리허설 10/13~14, 시연 10/15 | 10개 중 ≥8개 올바른 구역 | 미수행 · 10/15 · 영상·DB |
| **VC-V-08** 매핑 변경(C) | OP-001 / VT-035 | 시험: 교환 명령 → 확인 발화 → 다음 박스 적용 → 저장 실패 원복 | 각 1회 | 시연 4단계 통과 | 채택 시 10/13 |

**사이클 측정(참여, TBD-025 박병후):** sort_manager가 box_id별 이벤트 시각(detected, ocr1, goal_sent, grasped, placed, result)을 로그로 남김. 정상 자동 사이클 = detected → result(placed, decided_by=ocr). 예외 박스는 RECHECK 진입·질문 발화·답 수신 시각을 별도 기록하고 정상 사이클에 넣지 않음.

## 5. 미정·의존·범위 제안

### 5.1 필수 변경 제안 카드

| 항목 | NEW-V-01 |
|---|---|
| 제안 ID·담당 / 유형 | NEW-V-01 · 남현지 / 인터페이스 필드 추가 |
| 대상 | IC-VISION-04, voss_msgs/LabelRead |
| 변경 전 → 후 | (track_id, code, dong, confidence, stage) → 뒤에 `builtin_interfaces/Time stamp`, `string raw_text`, `string dong_alt`, `float32 confidence_alt` 추가(기존 필드 유지) |
| 꼭 필요한 이유 | SYS-FR-026(1·2위 후보 질문)에 2위 후보가 필요. V-03 오래된 결과 판정에 stamp 필요(SRD 5.2도 지적). V-07·TR-SYS-04 OCR 원문 기록에 raw_text 필요. 없으면 VT-026·VT-004 검증 불가 |
| 영향 | label_reader·sort_manager(남현지), hmi_bridge 표시(정의석, 선택 사용). docs/interfaces/voss_msgs.md 먼저 수정 |
| 이행 | 필드 끝에 추가라 기존 구독 코드 영향 없음. 10/07 PR |
| 의견·상태 | **제안**. 정의석 확인 필요 |

| 항목 | NEW-V-02 |
|---|---|
| 제안 ID·담당 / 유형 | NEW-V-02 · 남현지 / 인터페이스 필드·enum 추가 |
| 대상 | IC-RESULT-01·IC-DB-01, voss_msgs/SortResult |
| 변경 전 → 후 | outcome(placed/held/failed) → **passed 추가**. 뒤에 `string raw_text`, `string reason`, `int32 attempts` 추가 |
| 꼭 필요한 이유 | TR-SYS-04 "OCR 원문 기록"을 DB에 남길 경로가 없음. SYS-FR-034 오류 구분 보고에 reason 필요. 비대상 통과(SYS-FR-021)·재투입 집계(SYS-PF-009, VT-067)에 passed가 없으면 처리 수 계산이 틀림 |
| 영향 | sort_manager(남현지), sort_logger·DB 스키마·HMI 집계(정의석), 남은 수 계산(TBD-008) |
| 이행 | 필드 끝에 추가. DB 컬럼 3개 + outcome 값 1개 |
| 의견·상태 | **제안**. 정의석 확인 필요 |

| 항목 | NEW-V-03 (문서 정정) |
|---|---|
| 대상 | SRD 5.2 IC-VISION-03 현재 후보 "Image", IC-CONFIG-01 "추가 설정 경로 미정" |
| 변경 | IC-VISION-03 = voss_msgs/LabelCrop, 신규 `/voss/vision/read_label`(srv/ReadLabel), ZoneMapEntry에 code·aliases — **10/06 팀 승인**(main 반영 PR 대기) |
| 이유 | SRD 5.2가 지적한 "크롭에 track_id/stage 없음", "ZoneMap 정보 부족"을 해소한 결정의 반영 |
| 영향 | 없음(이미 승인). intent_parser는 zone_map에서 별칭을 받음(정의석) |

### 5.2 미정·의존 사항

| 관련 ID | 미정 내용·이유 | 결정 담당·예정일 | 다른 파트 영향·먼저 필요한 입력 | 제안 |
|---|---|---|---|---|
| TBD-001 | YOLO 기본 채택 여부(검출 방식은 10/06 결정, ADR-0004) | 남현지 · 10/08 | 없음(출력 계약 동일) | 공용 PC 검출률·지연이 분할보다 나으면 YOLO |
| TBD-001·EN-001 | 노출 실측값 | 김학민 T33 · 10/07 | OCR 정확도 | 5~8 ms 범위에서 송장 대비 기준으로 선택 |
| TBD-002 | 캘리브레이션 실측 오차 | 남현지·김학민 · 10/06 | 박병후 T26 시작 조건 | 측정 중 |
| TBD-002 | 정식 핸드아이(추종 중 좌표) | 남현지 · 10/07 | 박병후 A안 | 체커보드 준비 후 |
| TBD-004 | confidence_min 튜닝 | 남현지 · 10/07 | 재확인 빈도 | 0.6에서 시작 |
| TBD-005 | 정지 시 servo·gateway 동작 | 박병후·김학민 · 10/08 | 재개 규칙 | IC-V-05·06 제안 |
| IC-ROBOT-03 | 재확인 구역에서 다시 집기(MoveToZone 집기 높이) | 김학민 · 10/08 | RECHECK→목적 구역 이동 | MoveToZone에 pick 모드 또는 별도 서비스 |
| TBD-006 | 정적 설정의 launch 파라미터 전달 | 남현지·김학민 · 10/08 | servo·gateway | bringup에서 YAML 읽어 전달 |
| TBD-007·008 | 남은 수 계산식·DB 유일키 | 정의석 · 10/08 | HMI·음성 집계 | 투입 예정 − (placed+held+failed) |
| SYS-PF-* | 수치 목표 승인(pending #4) | 전원 · 10/06 | 모든 VT 합격 기준 | BRD 값 수용 |

## 6. 회신 전 확인

- [x] 내 담당 요구사항의 수용/수정/미정을 표시했습니다.
- [x] 내 질문 ID의 각 답변을 채웠거나 미정/해당 없음과 이유를 적었습니다.
- [x] 실제 데이터 예시·단위·식별·시간·실패 처리와 상대에게 필요한 정보를 적었습니다.
- [x] IC 커버리지 목록과 담당 VT 행에 카드 참조 또는 미정/미채택·이유를 연결했습니다.
- [x] 혼합 질문의 A 완료와 B 후속 미완료를 별도 표시했습니다.
- [x] 수정·추가가 꼭 필요한 경우 변경 카드를 작성하고 기존 ID를 유지했습니다.
- [x] 시험 목표와 실측 결과를 구분했고(실측 없음), 미정 담당·기한을 적었습니다.
- [x] 선택 기능을 기본 전체 흐름의 선행조건으로 넣지 않았습니다(V-08은 10/11 이후).
- [x] 비밀번호·API 키 값·개인 연락처 등은 넣지 않았습니다.

**증거 경로:** 레포 `yujh5537/rokey_cobot2_VOSS` — 브랜치 `docs/10-interfaces-labelcrop-alias`(`docs/interfaces/*`, `src/voss_msgs/msg/LabelCrop.msg`, `srv/ReadLabel.srv`), 브랜치 `feat/25-vision-belt-homography`(`docs/adr/0003-belt-plane-homography.md`, `docs/interfaces/calibration.md`, `src/voss_vision/voss_vision/belt_plane.py`, `src/voss_vision/test/test_belt_plane.py`, `tools/calib/`).
