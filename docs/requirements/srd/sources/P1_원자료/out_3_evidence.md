# SRD v2.0(잠정) 변경 대장 입력 ③ — 검증 증거

- 기준: 레포 `/home/rokey/cobot2/cobot2_voss` main **`fe11ded`**(2026-10-15 19:21). 시연 10/15 11:58~12:16(2회차). 읽기 전용으로 작성.
- 출처 구분(measurements-1015 관례): **[레포]** = main 에 커밋된 문서·로그 / **[밖]** = 레포 밖 원본(공용 PC `~/voss_data/…`, 팀 Drive `raw/…`, bag) — 경로만 적고 커밋 대상 아님 / **[보고]** = Slack·현장 보고만 있는 값(문서가 "보고값"으로 표시한 것 포함) / **[태그]** = main 에는 없고 태그 `demo-20261015`(25a726e)에만 있는 파일.
- PR·이슈 번호: 10/13~10/14 커밋(73ed548~32f9366)의 `(#n)` 은 임시 레포 PR → **`_2#n`** 으로 표기(ADR-0015 종료 절). 10/15 09:55(42ba57d, #163) 이후는 옛 레포(lambdaramji) 번호 그대로 `#n`. 10/11 이전 `#n` 도 옛 레포.
- 숫자는 원문 그대로 옮겼다. 계산하지 않았다(예외는 "Claude 줄 수 세기"로 표시한 1곳 — 판정 아님). 애매한 것은 "확인 필요".
- 판정 용어: **충족** = 승인값(또는 명시 요구값)을 문서화된 실측이 만족 / **미달** = 실측이 못 미침 또는 시도 불가 / **미측정** = 실측 기록 없음 / **부분** = 일부 조건·일부 구간·참고 조건만 실측, 또는 측정 방법이 요구와 다름.

---

## A. 수치 요구 대비 실측

### A-1. 요약 표

| # | 요구 (ID) | 요구값 (최신 승인값·출처) | 실측값 (날짜·조건·분모) — 대표값 **굵게** | 판정 | 증거 (파일:절, 출처 구분) |
|---|---|---|---|---|---|
| 1 | 이동 중 픽업 성공률 (NFR-01 / SYS-PF-001 / VT-045) | 재시도 포함 ≥ 70 %, **20 중 14 이상**, 분모 고정 — ADR-0012 승인(10/08). BRD v1.7 측정 방법은 "리허설 20회 중 성공 횟수" | **10/10 G1 s1: 20사례 중 20 성공(100 %), 최초 시도 20, 무효 6**(17:01 회차를 넣어도 19/20). 그 밖(게이트 아님): 10/12 s2 미니 게이트 5/5(+1)·비스듬 3/3·s3 5/5 / 10/13 S4 36/36 OK / 10/15 S2-T18 6단계 14/14 / 10/15 T19 고친 판 5/5 첫 시도 | 충족 (G1 기준). 리허설 20회 기준 집계는 없음 | measurements-1010 "G1 시리즈 s1"·"gate_summary 최종 집계" [레포]; ADR-0002 "판정" [레포]; g1-gate.md [레포]; 원본 `~/voss_data/1010/g1_s1/`·`g1_s1_gate_summary_final.md`, Drive `raw/1010/` [밖]; measurements-1012 §2·§3, -1013 §1 [레포]; S2T18-result §1 [레포]; measurements-1015 §6 [보고] |
| 2 | OCR 분류코드 정확도 (NFR-02 / SYS-PF-002 / VT-046) | 전체 ≥ 90 %, 흐린 송장 제외 ≥ 95 %; 정지 50장(흐린 5 포함)·추종 50장 구분, 두 조건 모두 — ADR-0012 | 정지(T18, 10/06, 개인 PC CPU): **50/50 = 100 %**(흐린 제외 45/45, 흐린 5/5). 공용 PC 녹화 재생(10/08 #9): 10트랙 모두 정답. 추종(10/15, T19): 실기 21장 + 고친 판 10장 + 10/10 G1 녹화 크롭 오프라인 105장 **모두 정답, "실기만으로는 31장"** | 부분 (정지 충족 / 추종 실기 분모 50 미달, 공식 VT-046 표 없음) | ADR-0008 "결과 (T18…)"·2026-10-15 추가 [레포]; measurements-1008 #9 [레포]; measurements-1015 §6 [보고]; 원본 공용 PC `~/voss_data/1015/t19s2/`·`t19s2b/` [밖] |
| 3 | 지시 해석 정확도 (NFR-03 / SYS-PF-003 / VT-047) | ≥ 95 %, 4종 × 5 = **20 중 19 이상**, API 오류·timeout 도 분모 — ADR-0012. 허용 외 입력 거부 100 % | 실측 기록 없음. palletize intent 는 LLM 없이 6건 통과(오프라인), "실제 LLM 정확도 미측정". 시연은 HMI 입력(`/voss/voice/intent` 0건) | 미측정 | palletizing_report §3 TR-PAL-01 [레포]; measurements-1015 §1·§3 [레포] |
| 4 | 사이클 (NFR-04 / SYS-PF-004 / VT-048) | 정상 자동 **≤ 30 s**(감지→적재 완료), 예외 세트 별도 — ADR-0012 | **10/15 시연: 바로 분류 최장 18.4 s**(004, 다음 18.2 s 011), 재확인 포함 최장 67.5 s(016, 무응답 30 s 대기 포함). 정의 `cycle_s = finished_at − started_at`, "첫 `/voss/vision/box` 기준으로 재도 같다". 현장 보고 21.9 s·68.8 s 는 "쓰지 않는다". 참고: TrackAndGrasp 한 건 11.4 s(10/10 ②), G0 10.8 s, G1 20회차 11.37 s; T19 고친 판 박스당 약 19 s [보고] | 충족 (정상 세트). SRD 정의(첫 유효 촬영→placed_stamp, attempts1·OCR·PLACED 필터)와 문서 정의가 같은지 확인 필요 | measurements-1015 요약·§1 "사이클" [레포, bag 대조]; 원본 `~/voss_data/1015/demo2` [밖]; measurements-1010 #6·G0·G1 20회차 [레포] |
| 5 | 음성 응답 (NFR-05 / SYS-PF-005 / VT-049) | 발화 종료 → TTS 시작 **≤ 3 s**(각 회차) | 실측 없음. 예비: ROS 수신 → 첫 PCM 전달 3회 1,860ms / 1,096ms / 1,265ms — "VT-049 합격 근거로 사용하지 않는다" | 미측정 | ADR-0013 "결과" [레포]; src/voss_voice/CLAUDE.md "VT-049 … 미실측" [레포] |
| 6 | 서보 루프 30 Hz (NFR-06 / SYS-PF-006 / VT-050) | 30 Hz 유지(BRD NFR-06). VT-050: 통합 부하(Whisper+vision)에서 주기·지터·누락, 발행과 장비 적용 구분 | 10/07 speedl 시험 스크립트 퍼블리시 33.3 ms(최대 33.7). **10/12 belt_servo 틱: 중앙값 33.3 ms·p99 34.2·최대 37.4 ms, 36.3 ms 초과 3틱/2102**(s3 최대 36.6, FIELD-1012 정정 "36.3 초과 1틱"). 10/15 T19 ④(정식 집계 전): 평균 33.3·최대 39.8 ms, 36.3 초과 2~3 %; 고친 판 평균 33.3·최대 38.3 ms·0.2 % [보고]. pose 50 Hz | 부분 (발행 주기만, 통합 부하·장비 적용 미측정) | measurements-1006 #3 [레포]; measurements-1012 §2 A·요약 E [레포]; FIELD-1012 §1 표 6 [레포]; measurements-1015 §6 [보고] |
| 7 | 관측 지연 100 ms (NFR-06 / SYS-PF-007 / VT-051) | capture → servo 소비 **≤ 100 ms**(BRD "지연 합계 100 ms"), capture→비전 발행 부분 구간 따로 | 부분 구간만: box_tracker **카메라→발행 p95 49 ms**(10/08 #1), 벨트 흘리기 p95 52~61 ms(#8), 10/10 p95 55~57 ms, 10/13 p95 ≈ 49 ms. 전체 구간(capture→servo 소비) 보고 없음. 참고: 영상-pose 지연 약 60 ms(10/08 #6), joint_states pose lag 15 ms(10/10 #3) | 부분 | measurements-1008 #1·#6·#8 [레포]; measurements-1010 #3·#5 [레포]; measurements-1013 §0 [레포] |
| 8 | HMI 반영 (SYS-PF-008 / VT-052) | manager 상태 변경 → DOM **≤ 1 s**(각 회차, 공용 PC 브라우저 시계) | 실측 없음. 음성 상태→웹 아이콘은 Web PC 격리 E2E 1회씩 PASS(지연 수치 아님). 팔레트 3D "반영 ≤ 1초는 공용 PC 재생" 미기록 | 미측정 | docs/testing/voice_web_link.md (10/13, Web PC 로컬, 결과 txt 는 레포 밖) [레포/밖]; palletizing_report TR-PAL-10 [레포] |
| 9 | 시연 완주율 (NFR-07 / SYS-PF-009 / VT-067) | **20개 중 16개 이상(80 %) 올바른 구역** — ADR-0012 변경(10/13 D7). (SRD v1.0·BRD 표는 아직 "10개 중 8개") | **10/15: 올바른 구역 20/20** — A 역삼 7 · B 대치 6 · C 청담 6 · HOLD 1(016 NO_ANSWER), bag `/voss/sort/result` 20건·실물 대조 | 충족 (단계 2 통과·재투입 없음 → 재투입 대응표 해당 없음) | measurements-1015 요약 [레포, bag]; ADR-0014 "시연 결과" [레포]; 원본 `~/voss_data/1015/demo2`·`demo2_rows.md` [밖] |
| 10 | 신뢰성 (NFR-08) | 실패 시 정지 없이 재시도·재확인·질문·보류, "리허설 중 정지 횟수" | 10/15 시연 2회차: 멈춤·비상정지 0회(PAUSED 0), 재확인 4건 모두 질문·답·무응답 보류까지 감. 단, 파지 실패·적재 시간 초과는 설계상 FAILED → PAUSED(10/10 G1 첫 박스 DEVICE_ERROR, 10/12 C-1 3회). 리허설 정지 횟수 집계 없음 | 부분 | measurements-1015 요약·§3 [레포, bag]; measurements-1010 "G1 첫 박스" [레포]; measurements-1012 §2 C [레포] |
| 11 | 안전 (NFR-09) | 속도 제한·작업 영역 SW 리밋·"멈춰"·HMI 정지·물리 비상정지 접근, v1.6 구역 이동 450 mm/s·900 mm/s² 시연 전 점검 | gateway real·max 100 mm/s·z ≥ 78·x −107~638(10/10); 펜던트 공간 제한 조그 하강 77.45 에서 정지(10/10); MoveToZone 450 → **300 mm/s**(J1 근처 9015, `_2#57`), 시연 300 mm/s·900·블렌딩 30 [보고]; 10/08 18:26 벨트 충돌 직전 비상정지(사건). "멈춰"는 시연 속도에서 미확인, 10/14 stop 응답 4/5 TIMEOUT [보고]. 시연 전 점검표 레포에 없음 | 부분 | measurements-1010 #0·#2 [레포]; measurements-1008 "사건 18:26" [레포]; measurements-1015 §0·§1 [레포/보고]; commit 43318d4 (`_2#57`) [레포] |
| 12 | 투입 위치 분리 (NFR-10 / SYS-EN-002) | 벨트 상류 투입 끝이 로봇 대기 위치와 겹치지 않음(배치 확인) | 10/06: 추종 가능 구간 748 mm(TCP x −107 → 638), "이보다 상류의 벨트 시작 구간은 로봇이 닿지 않음". 10/12: OBSERVE 시야 박스 x −184~+13 mm | 부분 (배치 기록 있음, 시연 배치 재확인 기록 없음) | measurements-1006 #6 [레포]; measurements-1012 §2 B-2 [레포] |
| 13 | 설정 단일화 (NFR-11 / SYS-FR-033) | YAML 하나로 구역·좌표·별칭·매핑 변경, 모든 노드 동시 반영 | 노드별 voss_config sha 일치 기록: 10/10 T2·T6·T8 모두 `db97243ec6ef`; 10/13 `c829cb0f3e21`; 시연 `844f45cfc0a2`. 실행 중 매핑 변경(UpdateZoneMap)은 미구현 → 시연 단계 4 제외 | 부분 | measurements-1010 "전체 재기동" 표 [레포]; ADR-0014 근거 [레포]; measurements-1015 §0·§1 [레포] |
| 14 | 로그 (NFR-12) | 지시·OCR·파지 결과 로그·DB로 성공률 집계 | G0: DB commit 뒤 SELECT 1행, `/voss/log/status` OK 521·DB_ERROR 0. 시연: sort_log PLACED 19 · HELD 1 [보고], pallet_log 19행. belt_servo 시도 로그 `data/servo/attempts/` | 충족 (지시 로그는 시연에서 음성 경로 미사용) | measurements-1010 "G0 1회차" [레포]; measurements-1015 §2 [레포/보고]; `data/servo/attempts/*.jsonl` [레포] |
| 15 | 카메라 노출 (NFR-13 / SYS-EN-001) | 수동 노출 5~8 ms, 고정 WB | **6.0 ms(값 60), WB 4600**, 1920×1080, 포화 0.33 %, 보조 LED 불필요 | 충족 | measurements-1006 #9 [레포]; measurements-1010 #3 조건 [레포] |
| 16 | 팔레트 배치 정확도 (NFR-14) | 경로대로 놓인 박스 100 %, **리허설 3회** 배치도·pallet_log 대조 | 10/13 게이트: 완주 16/16 DONE, FAILED 0, pallet_log 19행. 10/15: DONE 16·FAILED 0·OVERFLOW 3, "기록표 16행 모두 계획 칸 = 놓은 칸(2층 8)", 실물 계획 칸대로·밀림 0(보고값). 10/14 리허설 3회 기록 레포에 없음 | 부분 (2회 기록, 리허설 3회 대조 없음) | ADR-0014 "판정" [레포]; measurements-1015 §2 [레포/보고]; `~/voss_data/1013/s2gate_pal`·`s2gate_rows.auto.md` [밖] |
| 17 | 팔레타이징 사이클 (NFR-15) | 박스당 **≤ 30 s** | 10/12 v1.6 "박스당 9.6초, 16개 153초"(BRD v1.7 NFR-15 문구, measurements 없음) [보고]. 10/13 게이트 **박스당 최대 15.0 s**. **10/15 박스당 8.8~15.3 s(최대 15.3), 전체 2분 56.6초** | 충족 | ADR-0014 판정 표 [레포]; measurements-1015 §2 [레포, bag]; BRD v1.7 10.8 [레포 밖 사본: scratchpad brd_v1.7.txt] |
| 18 | 음성 시스템 기동 (NFR-16) | 3회 중 3회, 명령 → "준비를 마쳤습니다" 3분 이내(실측 후 조정). 게이트 기준: 실기 1회 성공 | **시도 0** — "단계 0 이전 — voss_launcher(S2-T09) 미구현", 같은 날 AI 컨테이너 꺼짐·TTS 무음·GPU 커널 문제 | 미달 (미구현으로 시도 불가) | ADR-0014 판정 표 [레포, 출처 김학민 Slack 10/13 17:54 = 보고] |
| 19 | 핸드아이·좌표 오차 (제안 ≤ 5 mm, ADR-0012 범위 밖) | ≤ 5 mm(제안값) | 호모그래피 검증점 **최대 2.63 mm**(10/06·07), 재터치 최대 2.92 mm(10/08). 핸드아이 T16 최대 4.56 · 터치 최대 2.44 mm. **이동 중 좌표 최대 4.08 mm(지연 0) / 2.73 mm(지연 60 ms 보정)**(20 mm/s, 1601 프레임). TCP 바로 아래 4.07 mm. 별도: 10/13 S4 벨트 방향 파지 오프셋 b_phys ≈ +3.1 mm(출처 미확인) | 충족 (제안값 기준). b_phys 출처 미확인 | measurements-1006 #7 [레포]; measurements-1008 #2~#5 [레포]; measurements-1013 요약·§2 [레포] |
| 20 | 벨트 속도 (≤ 10 cm/s, SYS-CT-004) | ≤ 10 cm/s, 개발 설정 4.8 | h250: 4.89(10/06, 5분 뒤 4.79) · 4.77(10/08) · 4.76(10/10) · 4.73(10/12) · **4.73 ×3(10/13)** cm/s. 추종 중 추정 4.68~4.70(10/12), v_box 46.92 ± 0.07 mm/s(10/13) | 충족 | measurements-1006 #1·-1008 #10·-1010 #11·-1012 §0·-1013 §5 [레포] |
| 21 | STT 전사 (SRD 6.2, #54 제안) | 녹음 20개 중 정확 ≥ 18(90 %) | 실측 없음. Whisper 모델 크기 pending #6 미정 | 미측정 | SRD 01 §6.2 [레포]; pending-decisions #6 [레포] |
| 22 | 호출어 1 m 인식 (SR-HW-11, measurements-1006 #10) | 공용 PC 내장 마이크 1 m | 10/08 **개인 PC 참고**: 호출어 포함 10회 → 발행 10(순수 호출어 9/9 + 정지 예외 1), 미포함 10회 → 0. "공용 PC 기준은 아직 미충족" | 부분 (참고 조건만) | measurements-1006 #10 [레포]; 원본 Drive `raw/1008/wake_1m/` [밖] |
| 23 | 검출 30 Hz·검출률 ≥ 99 %·지연 ≤ 100 ms (T17, SRD 6.2 "검출/1차 OCR BRD 30Hz") | 30 Hz, 검출률 ≥ 99 % | **29.8~30.0 Hz**, 확정 트랙 구간 **검출률 ≈ 99.9 %(1255/1256)**, 박스 10개 → 트랙 10개 | 충족 | measurements-1008 #1·#8 [레포]; bag `t17_live_02` Drive `raw/1008/` [밖] |
| 24 | 1단계 OCR 지연 (TR-OCR-01, SRD 6.2 "≤ 300 ms") | ≤ 300 ms (BRD; SRD 6.2 는 새 SYS 요구로 추가 안 함) | 공용 PC **CPU OCR 평균 2.06 s·최대 2.55 s**(10/08); OCR 3064·2995 ms(G0); 10/15 장당 1.9~2.7 s(고친 판, 호스트 CPU) [보고]. GPU 실측 없음(10/12 GPU 드라이버 통신 불가) | 미달 (CPU 기준). GPU 미측정 | measurements-1008 #9 [레포]; measurements-1010 G0 [레포]; measurements-1012 §0 GPU [레포]; measurements-1015 §6 [보고] |
| 25 | servo_cmd watchdog 200 ms (제안, SRD 6.2 "좌표/안전 후보") | 200 ms(제안) — 정지 거리·지연 기준값 없음 | 10/10 f04: 20 mm/s 0.24 s·4.98 mm, 48 mm/s 끊긴 뒤 약 0.25 s 정지·10.3 mm. 10/07: 속도 0 재전송 → 정지 acc 20 ≈ 0.41 s, acc 100 ≈ 0.15 s. 취소 정지: 0.099 s·0.97 mm / 0.083 s·0.74 mm(10/10 ①). 회전: 0.2~0.3 s, 2.3~2.6°(10/15) | 부분 (기록만, 합격 기준 미정) | measurements-1010 #5·#12 [레포]; measurements-1006 #3 [레포]; S2T18-result §2 [레포] |
| 26 | gateway 연속 운전 (T32 30 분 / #41 60 분·pose ≥ 45 Hz) | 30 분 무정지(10/09 PL 승인), 1시간 연속·FAULT 0·`max_call_misses` 0·pose ≥ 45 Hz | 10/08: 30.4 분 **78/78 OK**, WARN·ERROR·FAULT 0. 10/10 G1 세션: **64.5 분 재시작 없음, FAULT 0, 응답 없음 0**, pose 5초 창 최소 **30.2 Hz → "pose ≥ 45 Hz" 미달**(C2·HOLD1 트레이 안 이동). 10/11 c90623f(#153) 개선 뒤 재측정 기록 없음 | 부분 | measurements-1008 #15 [레포]; measurements-1010 #9·"#41 판정용 확인" [레포] |
| 27 | 추종·파지 새 사이클 목표 (pending #26) | 미정 — NFR-04 30 s 유지 | 기준 11.4 s(10/10), 사다리꼴 회차 전체 8.1~9.0 s(10/13), J6 6단계 goal 8.0~8.9 s(10/15) | 해당 없음(목표 미정) | pending-decisions #26 [레포]; measurements-1013 §4 [레포]; S2T18-result §1 [레포] |

### A-2. 집계 (27행)

| 판정 | 수 | 행 |
|---|---|---|
| 충족 | **9** | 1(NFR-01, G1 기준), 4(NFR-04), 9(NFR-07), 14(NFR-12), 15(NFR-13), 17(NFR-15), 19(핸드아이 제안값), 20(벨트 ≤ 10 cm/s), 23(검출 30 Hz·99 %) |
| 미달 | **2** | 18(NFR-16), 24(1단계 OCR 300 ms, CPU 기준) |
| 미측정 | **4** | 3(NFR-03), 5(NFR-05), 8(SYS-PF-008 HMI 1 s), 21(STT 20개) |
| 부분 | **11** | 2(NFR-02), 6(30 Hz), 7(100 ms), 10(NFR-08), 11(NFR-09), 12(NFR-10), 13(NFR-11), 16(NFR-14), 22(호출어 1 m), 25(watchdog), 26(gateway 연속 운전) |
| 해당 없음 | 1 | 27(새 사이클 목표 미정) |

승인 5개(ADR-0012)만 보면: SYS-PF-001 충족 · PF-002 부분 · PF-003 미측정 · PF-004 충족 · PF-009 충족(D7 기준).

### A-3. 같은 항목의 날짜별 측정 (대표값 외)

| 항목 | 날짜·조건 | 값 | 출처 |
|---|---|---|---|
| 파지 성공 | 10/10 G1 s1 (Kp 1.0, h250 4.76, FF 4.8, sort_manager 경로, params `215e6274f074`) | 20/20, 최초 시도 20, 무효 6 (**대표**) | measurements-1010 [레포] |
| | 10/10 의도 시험(기울임·뒤집기, 분모 밖) | goal 6개 중 OK 1, LOST 5(DESCEND 3, TRACK 2) | measurements-1010 "의도 시험" [레포] |
| | 10/12 s2 (U9 코드 c187334, params `88867330885a`) | A 5/5(+1 = 6/6), B-1 비스듬 3/3(10·5·20° 눈대중), C-1 폭 밖 GRASP_FAILED 3/3 → 후퇴 3/3 | measurements-1012 §1·§2 [레포]; `data/servo/attempts/servo_attempts_20261012_180722.jsonl` [레포] |
| | 10/12 s3 (FF 4.73) | 5/5 | measurements-1012 §3 [레포]; `…_190046.jsonl` [레포] |
| | 10/13 S4 (시험 도구 goal, FF 4.56~4.80, p·비스듬·사다리꼴) | 36/36 OK, attempts 1 | measurements-1013 §1·gate_summary [레포]; `data/servo/attempts/servo_attempts_20261013_*.jsonl` 9개 [레포] |
| | 10/15 S2-T18 6단계 (J6 회전, 단독 액션) | 14/14 | S2T18-result §1 [레포]; `~/voss_data/1015/u14/` [밖] |
| | 10/13~10/15 리허설·게이트 시도 로그 10개 | **Claude 줄 수 세기(판정 아님, 연습·무효 포함 가능)**: 10/13 144556 OK 10·DEVICE_ERROR 1 / 151111 OK 20 / 10/14 155341 OK 20·CANCELED 2 / 201409 OK 17 / 204011 OK 21·LOST 1 / 210527 OK 20 / 212336 OK 14·LOST 2 / 10/15 093245 OK 1 / 093824 OK 15 / 103029 OK 20·LOST 1 | [태그] `demo-20261015` 의 `data/servo/attempts/` — main 에 없음, 문서 집계 없음 |
| OCR 추종 | 10/12 E (s2 크롭 입력) | 회차당 15~20 입력, 판독은 s1 만(2단계 미구현) | measurements-1012 §2 E [레포] |
| | 10/15 ① 바로 선 5 / ② 거꾸로 5 / ③ 흐린 2 (377e972) | 5/5 맞는 구역(2단계 0건) / 확정 0·goal 뒤 도착 5 → 재확인 → 맞는 구역, 틀린 구역 0, 2단계 판독 10장 정답 / 2/2 HOLD | measurements-1015 §6 [보고] |
| | 10/15 고친 판 (a120bc7, #181) | goal 안 확정 5/5, 장당 1.9~2.7 s, 틀린 구역 0 | measurements-1015 §6 [보고] |
| 사이클 | 10/15 시연 | 18.4 s (**대표**) / 재확인 포함 67.5 s | measurements-1015 [레포, bag] |
| 팔레타이징 | 10/12 (v1.6) / 10/13 게이트 / 10/15 시연 | 9.6 s·153 s [보고] / 최대 15.0 s / 최대 15.3 s·2분 56.6초 (**대표**) | BRD v1.7; ADR-0014; measurements-1015 |

---

## B. 게이트·시연

### B-1. 게이트

| 게이트 | 일시·코드 | 기준 | 결과 | 제외·무효·남은 점 | 증거 |
|---|---|---|---|---|---|
| **G0** 최초 전체 흐름 (SRD 8.2) | 10/10 16:08~16:13, main `9aa1162`, voss_config `db97243ec6ef`, belt_servo params `215e6274f074…` | 실물 1박스 인식 → 이동 중 픽업 → 기본 구역 적재 → DB commit·같은 box_id SELECT → OBSERVE 복귀, DB_ERROR 0 | box `20261010T160835-e8c7-001` 대치동(S07-02 1.00 AGREE 2/2) → **B 칸 0 PLACED**, TrackAndGrasp OK·grasped true·시도 1·10.8 s, 좌표 HAND_EYE, 닫기 1998 ms 폭 40.7 grip True, PLACE 52.9 s(30 mm/s), DB SELECT 1행, bag `/voss/log/status` OK 521·DB_ERROR 0, state 16:13:10.124 RUNNING 복귀 → stop → PAUSED | G0 판독·추종이 카메라 25.0~26.6 Hz 저하 구간에서 진행. 휴대폰 영상 ↔ finished_at 16:12:43.4 대조는 "영상 원본으로" — **대조 결과 미기록**. g0-runbook §5 체크표 미기입, "G0 통과" 판정 문구 레포 문서에 없음(servo README "G0 1회차 완주") — 확인 필요 | measurements-1010 "G0 1회차" [레포]; g0-runbook §5 [레포]; `~/voss_data/1010/g0_01/`, Drive `raw/1010/g0_01/` [밖] |
| **G1** 20사례 게이트 (ADR-0002) | 10/10 16:44~17:15, main `9aa1162`, h250 실측 4.76, gateway 16:41:52 기동 | 20사례 중 14 이상(70 %), 분모 고정, 자동 전환 없음 | **통과 — 20/20(100 %), 최초 시도 20, 무효 6, A안 유지**(전원 확인 4/4, 10/11 Slack). 적재 PLACED 19, 10회차는 재확인 칸 뒤 PICK 미구현으로 HELD(파지와 무관) | 무효 6 = 의도 시험(기울임 4·뒤집기 2). 17:01 회차 포함 시 19/20. 선언 전 첫 박스(16:33)는 PLACE `move_timeout_s` 60 초과로 FAILED DEVICE_ERROR(분모 밖). "영상에서 안전 높이" 회차별 기록 없음 → 적재 결과로 대신. **회귀 조건(ADR-0002): 파라미터 변경 뒤 h250 반듯한 박스 10회 이상 재측정** — U9 s2 반듯 6회(FIELD-1012 "4회 모자람"), 시연 조합(FF 4.56 + 사다리꼴) 5회(U13 "5회 부족") → PL 판단 기록 없음 | ADR-0002 "판정" [레포]; measurements-1010 [레포]; FIELD-1010 §1 재현 [레포]; FIELD-1012 §3, U13 §6.6 [레포] |
| **Sprint 2 게이트** (ADR-0014) | 10/13 18:00 판정, 실행 코드 cc1d0fe(= 4b3f66c + 커밋 전 변경), voss_config `c829cb0f3e21` | 팔레타이징 = 16칸 3개 동(S8) 실기 1회 완주(D3), 음성 기동 = 실기 1회 성공 | **팔레타이징: 통과 — 조건부**(회차 1, 15:25:24, run `20261013T152524-29d8`, 16/16 DONE·FAILED 0, 2층 8칸, 대치 3개 초과, 박스당 최대 15.0 s, pallet_log 19행) / **음성 기동: 성공 없음(시도 0) → 단계 0 제외**(D) | 조건 ① cc1d0fe 통합 → 10/13 ✅ ② HMI 3D·MQTT·음성 되읽기·멈춤·재개 10/14 리허설 1회차 확인 → 10/15 시연에서 MQTT·HMI 버튼·3D ✅(3D 보고값)·되읽기 TTS ✅(bag), **멈춤·재개 시연 속도 미확인** ③ 즉시 재확인 실기 1회 → 10/15 ✅(4건) | ADR-0014 [레포]; sprint2-gate.md [레포]; `~/voss_data/1013/s2gate_pal`·`s2gate_rows.auto.md` [밖]; 김학민 Slack 10/13 17:54 [보고] |
| G2 최종 필수 수락 (SRD 8.2) | — | B 음성/HMI/다단 OCR/예외/보류/이력/정지·재개·성능·컨테이너 + 물리 박스 ≥ 8/10 | 공식 G2 판정 기록 없음. 시연 결과(아래 B-2)로 일부만 증거 | 이력 질의·우선 분류·정지·재개·음성 명령·성능표(NFR-03·05·08) 미증거 | measurements-1015 [레포] |

### B-2. 10/15 시연 단계 0~9 (2회차 11:58~12:16, session `20261015T120322-c690`, 빌드 25a726e / 태그 `demo-20261015` = main 32f9366 + 코드 5파일, voss_config `844f45cfc0a2`, MoveToZone 300 mm/s·900·블렌딩 30, `defer_recheck: False`)

| 단계 | 결과 | 제외·미실시 사유 / 비고 | 증거 |
|---|---|---|---|
| 0 음성 시스템 기동 | **제외 — 수동 기동** | ADR-0014 D(voss_launcher 미구현) | measurements-1015 §1 [레포] |
| 1 운전 시작 | ✅ | 입력은 HMI(음성 명령 미사용, `/voss/voice/intent` 0건) | measurements-1015 §1·§3 [레포, bag] |
| 2 우선 분류 | **이번 회차 안 함** | 사유 기록 없음 → PASSED·재투입 증거 없음 | measurements-1015 §1 [레포] |
| 3 전체 분류 | ✅ | 20/20 올바른 구역 | 같음 |
| 4 규칙 변경 | **제외** | 미구현(UpdateZoneMap 없음) | 같음; demo-script §2 [레포] |
| 5 예외 처리 | ✅ | 재확인 4건: 020 흐린 송장(3단계 역삼 conf 0.2947) → "역삼동입니까?" → 작업자 답 → A(OPERATOR) / 016 판별 불가 → 질문 12:10:18 → 30.0 s 무응답 → HOLD(NO_ANSWER) / 012 거꾸로 송장 → 재판독 → A(RECHECK) / 010 거꾸로 송장 → 3지 질문 → 작업자 답 → A(OPERATOR) | measurements-1015 §1 "재확인 4건" [레포, bag] |
| 6·8 집계 질의 | **이번 회차 안 함** | intent_parser 문장이 `/voss/voice/say` 9건에 없음, `/voss/voice/intent` 0건 | measurements-1015 §1 [레포, bag] |
| 7 멈춤·재개 | **이번 회차 안 함** | 시연 속도(300 mm/s)에서 정지·재개 미확인, PAUSED 0. 참고: 10/14 18:45(450 mm/s) stop 응답 4/5 TIMEOUT 미해결 | measurements-1015 §1·§5 [레포/보고] |
| 9 팔레타이징 | ✅ | run `20261015T121315-0193`: DONE 16 · FAILED 0 · OVERFLOW 3(청담), 박스당 최대 15.3 s, 2분 56.6초, pallet_log 19행. **입력 경로 청담 → 역삼 → 대치 = D4(대치 → 역삼 → 청담)와 반대** → 초과가 청담에서 남(코드는 규칙대로, 입력 이유 없음). 되읽기 TTS bag 12:13:15.369 | measurements-1015 §2 [레포, bag·기록표] |
| (종합) | 멈춤·비상정지 0회 | 영상 없음(시연 영상 찍지 않음, 김학민 10/15 14:12) | measurements-1015 요약·§4 [레포] |

- 웹·음성(정의석 PC)의 시연 시점 커밋은 **확인 필요**(스냅샷 a9debbb 위 커밋들이 시연 뒤 12:24~12:33, 시연 시점은 fe146fd + 미커밋 변경으로 보임 — 정의석 확인 대기). measurements-1015 §0 [레포].
- 시연 빌드 코드 5파일(hmi_bridge `/voss/voice/text`·MQTT `voss/voice/request` → `/voss/voice/say` 새 발행자 등)은 main 에 없음(인터페이스 문서 미반영). measurements-1015 §0·§5 [레포].
- 1차 리허설(10/14 3회) 결과·시연 1회차 결과는 레포에 없음.

---

## C. 기능별 실기 확인 기록

| 기능 | 날짜·조건 | 결과 | 남은 점 | 증거 |
|---|---|---|---|---|
| 재확인 → 질문 → 보류 (SYS-FR-025~028) | 10/10 G1 10회차 | LOW_CONF(0.60→0.65 CODE_ONLY) → RECHECK 칸 0 PLACE → VIEW → 재판독 → 질문 16:50:33 → 30 s 무응답 → NONE → HOLD 로 옮기려 PICK → `NOT_CONFIGURED: PICK 은 아직 구현 전` → HELD RECHECK DEVICE_ERROR → PAUSED | PICK 은 10/11 구현(6557179, 옛 #148) | measurements-1010 "본 측정 s1" [레포] |
| | 10/10 17:28 VIEW 자세 | OK 8.0 s, pose 교시값과 차 ≤ 0.04 mm | — | measurements-1010 #7 [레포] |
| | 10/15 시연 | 4건 모두 질문·답·30 s 무응답 보류 (B-2) | S2-T12 "흐린 송장 완주 3회" 기록 레포에 없음 | measurements-1015 §1 [레포, bag] |
| | 10/15 T19 ③ | 흐린 송장 2/2 → 재확인 → HOLD, 틀린 구역 0 | — | measurements-1015 §6 [보고] |
| 팔레타이징 16칸·초과 | 10/12 (v1.6, 이전 적재 순서) | 16칸 2층 완주 1회, 박스당 9.6 s·16개 153 s | measurements 없음 | BRD v1.7 D3·NFR-15 [보고] |
| | 10/13 오프라인 검증 (integ/1013-gate-v15, 로봇 없음) | 통과 6(TR-PAL-02·03·04·08·09·11), 구현·확인 전 2, 미구현 4(05·06·07·12), S1~S8 정답 일치, 불변식 500회 실패 0 | §8 실기 체크리스트 17항목 모두 ☐ | palletizing_report [레포] |
| | 10/13 게이트 / 10/15 시연 | 16/16 DONE·초과 3 / 16 DONE·OVERFLOW 3(청담) | 10/15 경로가 D4 와 반대 | ADR-0014, measurements-1015 §2 |
| 위층 실패(#37 당겨 놓기)·파지 실패 3회·팔레타이징 중 멈춤·재개 | 10/13 | 코드 수정 d8c1d78 + 단위 시험 `test_layer2_box_pulled_down_onto_failed_slot`·`test_resume_continues_at_next_slot` | **실기 없음**(체크리스트 14·15 ☐) | palletizing_report §2·§6·§8 [레포] |
| 2단계 OCR (T19, SYS-FR-023) | 10/12 E | s2 크롭 입력 회차당 15~20, 판독 안 됨(미구현), belt_servo 주기 영향 없음 | — | measurements-1012 §2 E; FIELD-1012 §3 [레포] |
| | 10/15 16:35~16:50 (377e972) / 17:25~17:27 (a120bc7, #181) | ①②③ (A-3) / 고친 판 goal 안 확정 5/5, 장당 1.9~2.7 s, 박스당 약 19 s, 틱 최대 38.3 ms·36.3 초과 0.2 % → **기본 켬 결정(PL, ADR-0008)** | LOST 2건은 손목 카메라 USB 프레임 손상. 틱 정식 집계(박병후) 미완 | measurements-1015 §6 [보고]; ADR-0008 2026-10-15 추가 [레포]; `~/voss_data/1015/t19s2/`·`t19s2b/` [밖] |
| J6 회전 파지 (S2-T18) | 10/15 13:00~16:10, FF 4.56 | R1~R3 저속 ✅(부호 +, 회전 중 TCP xy ≤ 0.20 mm, 지령→pose 40~52 ms), 1단계 9/9, 5단계 − 12/12·+ 19/29(+67° 이상 9/18), **6단계(flip 70·LOST 1.2 s·max 110) 14/14** → 판정 "기능 시험·적용 완료"(사용자 10/15 16:10), pending #27 결정 | 시연에는 미사용(rotate 기본 off). sort_manager 전체 흐름 회차 없음. gateway 한계 130 은 확인 범위(카메라 −109.4°, 케이블 −123° 육안) 밖. RETURN_INCOMPLETE 큰 회전에서 정상 | S2T18-result [레포]; pending-decisions #27 [레포]; `~/voss_data/1015/u14/` [밖] |
| 사다리꼴 z (S2-T14) | 10/13 S4 블록 8 (FF 4.56) | **5/5 OK**, 착지 TCP z 82.9 mm(≥ 80), DESCEND 1.57~1.60 s(p 2.60), LIFT 1.63 s(p 2.70~2.73), 회차 8.1~9.0 s, 핑거–벨트 접촉 없음(육안), 닫힘 2.57 s > close_time_max 2.5 (1/5) | 공용 PC 설정으로 남김(`f7e210107413`). 시연 때 z 프로파일 실제 값 measurements-1015 에 없음 — 확인 필요. 폭 밖 후퇴(C) 미시험 | measurements-1013 §4·§7 [레포]; S2T14-run §6(에뮬레이터·sim) [레포] |
| 속도 추정·FF (S2-T15) | 10/12 s2·s3 / 10/13 S4 | 추종 중 추정 4.68~4.70 vs 정지 4.73(약 1 % 차, 원인 미확인) / FF 4.56~4.80 × 36회, y_phys = 0 at FF 4.573, b_phys ≈ +3.1 mm → **FF 4.56 + 사다리꼴 공용 PC 설정**(팀 합의), 레포 반영 a7d9dd6(`_2#46`). ③ 자동 대체는 **미적용** | b_phys 출처 미확인(핸드아이 x / 패드 중심) | measurements-1012 §3, -1013 [레포]; U13 §6.6·§6.8 [레포] |
| 안전 후퇴·재시도 (U9-b, SYS-FR-011) | 10/12 C-1 | GRASP_FAILED/WIDTH_OUT 3/3 → OPENING 1.13~1.20 s → RISING 2.27~2.30 s → 끝 윗면 +48, retry_room_ok false 3/3 | **재시도는 실기에서 한 번도 발생하지 않음**(실패 x 282~319 > 225, sim 만). max_attempts 1. C-2 빈손 NOT_DETECTED 미실시 | measurements-1012 §2 C [레포]; FIELD-1012 §3 [레포] |
| DESCEND LOST 해소 (U9-a) | 10/12 B-1 / 10/13 비스듬 | 3/3 LOST 0 / 25°·≈26°·33.0° 3/3 OK | — | measurements-1012, -1013 §3 [레포] |
| 멈춤·재개·stop·cancel (SYS-SF-001, SYS-FR-019) | 10/08 #7 (도메인 77 모의) | stop → PAUSED | 모의 | measurements-1008 #7 [레포] |
| | 10/10 ① Kp 0 cancel | CANCELED/STOP_OK 2/2, 정지 0.099 s·0.97 mm / 0.083 s·0.74 mm, gateway move_stop ok | — | measurements-1010 #5 [레포] |
| | 10/10 G0 | stop → PAUSED, gateway `/voss/robot/stop → OK` | — | measurements-1010 G0 [레포] |
| | 10/12 | FAILED → PAUSED → 사람 확인 뒤 resume, 18:53:27 resume → OBSERVE 복귀 | — | measurements-1012 §2 C·D [레포] |
| | 10/14 18:45 (450 mm/s) | **stop 응답 4/5 TIMEOUT 미해결** | 번호 "#50" 은 `_2#50`(MoveToZone 450 mm/s, S2-T17)로 보임 — 확인 필요. 원본 레포 밖 | measurements-1015 §1 [보고] |
| | 10/15 시연 | 멈춤·재개 미실시(PAUSED 0) | 시연 속도 확인 기록 없음 | measurements-1015 §1·§5 [레포] |
| 음성 명령 | 10/08 (개인 PC) | 호출어 1 m 참고 9/9 + 정지 예외 1 | 공용 PC 미측정(#24) | measurements-1006 #10 [레포] |
| | 10/15 시연 | **음성 명령 미사용**(HMI 입력, `/voss/voice/intent` 0건) | — | measurements-1015 §1·§3 [레포, bag] |
| HMI·MQTT | 10/13 Web PC 격리 E2E | 음성 상태 → MQTT → SSE → DOM 12개 검증 PASS(각 1회) | 결과 txt·E2E 스크립트는 Web PC 로컬(레포 없음) | docs/testing/voice_web_link.md [레포/밖] |
| | 10/15 시연 | MQTT·HMI 버튼 ✅, 3D 배치도 ✅(보고값) | 시연 빌드 hmi_bridge 변경 main 미반영 | measurements-1015 §0·§3 [레포/보고] |
| TTS | 10/08~10/11 (ADR-0013) | 한국어 출력·FIFO 순차 재생 확인, 첫 PCM 예비 3회 | 3 s 루프 미측정 | ADR-0013 [레포] |
| | 10/13 게이트 날 | OpenAI 연결 실패로 무음 | — | ADR-0014 [보고] |
| | 10/15 시연 | 되읽기 TTS ✅ bag `/voss/voice/say` 12:13:15.369, 재확인 질문 say 발행(9건) | 스피커 출력은 bag 밖 | measurements-1015 §2·§3 [레포, bag] |
| 그리퍼 파지력·폭 (ADR-0009) | 10/06 / 10/08 T34 | 14 N 채택(12 N 부터 미끄러짐 없음) / 0° 10/10·15° 5/5·30° 5/5·벨트 방향 ±10 mm 12/12 | 10/10 ② 박스 조금 찌그러짐 1건(정도 미기록) | measurements-1006 #8, -1008 #14, -1010 #6 [레포] |
| 적재·복귀 (SYS-FR-012·013) | 10/08 #12 / 10/10 #8 | 구역별 도달 OK / **15칸 15/15 OK**(17.4~32.3 s, 100 mm/s) | C2 32.3 s(> 30 s) | measurements-1008 #12, -1010 #8 [레포] |
| VERIFY 재닫기 | 10/10 | 벨트 위 24회 모두 OK·grip True, 폭 40.6~41.5, DROPPED 0 | — | measurements-1010 #4 [레포] |
| 카메라 USB | 10/08 10:52 / 10/10 14:25·16:11~16:22 / 10/15 15:44 | 끊김·프레임 손상 사건 반복 | 원인 미확인(케이블·커넥터 추측) | measurements-1008, -1010 "사건", S2T18-result §2 [레포] |

---

## D. 증거 없음·미측정 목록

| # | 무엇이 없나 | 요구 | 담당(문서 근거) | 비고 |
|---|---|---|---|---|
| 1 | **NFR-01~03 실측값 보고(S2-T19) — main 에 없음** (10/14 마일스톤 "NFR-01~03 실측값 표 PR") | NFR-01~03 | 정의석 (plan.md S2-T19, BRD v1.7 10.2) | 리허설 belt_servo 시도 로그 10개는 [태그]에만 있고 집계 문서 없음 |
| 2 | NFR-02 추종 50장 실기 분모(실기 31장), 흐린 송장 포함 전체 집합 기준 VT-046 공식 표 | NFR-02 / VT-046 | 남현지(SYS-PF-002) · 박병후(S2-T11 OCR 튜닝) · 집계 정의석(S2-T19) | 오프라인 105장은 녹화 크롭 |
| 3 | NFR-03 지시 해석 20문장(API 오류 포함)·허용 외 입력 거부 100 %·palletize 실제 LLM 정확도 | NFR-03 / VT-047 | 정의석 | — |
| 4 | **NFR-05 음성 응답 3 s**(발화 종료 → TTS 시작 전체 구간) | NFR-05 / VT-049 | 정의석 | 예비 첫 PCM 3회만 |
| 5 | STT 녹음 20개 ≥ 18, 공용 PC 내장 마이크 1 m 호출어 재측정 | SRD 6.2, SR-HW-11 | 정의석 (#24, Whisper 크기 pending #6 미정) | — |
| 6 | **NFR-16 음성 시스템 기동** — voss_launcher 미구현, 시도 0 | NFR-16 / TR-VOICE-11~16 | 정의석·김학민 (S2-T09·T10) | 단계 0 제외 |
| 7 | **멈춤·재개 시연 속도(300 mm/s) 확인**, 10/14 stop 응답 4/5 TIMEOUT 해결, 음성 "멈춰" 실기 | SYS-SF-001, SYS-FR-019, 시연 단계 7, ADR-0014 조건 ② | 김학민(stop·gateway) · 남현지(sort_manager) | measurements-1015 §5 "다음 과제" |
| 8 | 서보 30 Hz 의 통합 부하(Whisper+vision)·장비 적용(speedl 실제 적용) 측정, 10/15 T19 틱 정식 집계 | SYS-PF-006 / VT-050 | 박병후 | 발행 주기만 있음 |
| 9 | capture → servo 소비 전체 관측 지연 | SYS-PF-007 / VT-051 | 박병후 | capture→비전 발행 p95 만 있음 |
| 10 | HMI 상태 변경 → DOM ≤ 1 s (공용 PC 브라우저) | SYS-PF-008 / VT-052, S2-T08 "반영 ≤ 1초" | 정의석 (S2-T08 남현지) | — |
| 11 | 1단계 OCR ≤ 300 ms 의 GPU 측정 (CPU 2.06 s 만) / 비전 컨테이너(GPU) 실기 운용 증거 | TR-OCR-01, SYS-CT-005 | 남현지 | 10/12 GPU 드라이버 통신 불가, 10/15 T19 는 호스트 CPU venv. measurements-1006 #5 "GPU 컨테이너 실행 테스트 전" |
| 12 | 이력 질의(동별·보류·남은 수) 음성 = HMI = DB 대조 | SYS-FR-029·032, 시연 단계 6·8, TR-PAL-12 | 정의석 (S2-T22) | 시연 6·8 미실시 |
| 13 | 우선 분류·비대상 PASSED·재투입 | SYS-FR-020·021, 시연 단계 2 | 남현지 | 시연 2 미실시 |
| 14 | 규칙 변경·신규 구역 교시 | SYS-OP-001·002, 시연 단계 4 | 남현지·김학민 | 미구현 |
| 15 | **ADR-0002 회귀 "h250 반듯한 박스 10회 이상"**(U9 s2 6회, 시연 조합 FF 4.56 + 사다리꼴 5회) — PL 판단 기록 없음 | ADR-0002 판정 "남은 위험" | 박병후 → PL 남현지 | U13 §6.6 "PL 판단 요청 문안" |
| 16 | 실기 재시도(attempts ≥ 2) 발생 기록, C-2 빈손 NOT_DETECTED | SYS-FR-011 (최대 2회 재시도) | 박병후 | max_attempts 1, sim 만 |
| 17 | 10/14 리허설 3회 기록, NFR-14 "리허설 3회" 배치도 대조, S2-T12 흐린 송장 완주 3회 | NFR-14, S2-T12 | 김학민 (S2-T12) | measurements-1014 없음 |
| 18 | G0 영상 개방 순간 ↔ finished_at 대조 결과, g0-runbook §5 체크표·"G0 통과" 판정 문구 | SRD 8.2 G0 | 남현지(PL) · 김학민 | 영상 Drive `raw/1010/g0_01/` |
| 19 | 시연 영상 (찍지 않음) | 증거 기록 | 김학민 (시연 기록) | bag·기록표·사진으로 대신 |
| 20 | 웹·음성 PC 시연 시점 커밋 | 재현성 | 정의석 | fe146fd + 미커밋 변경 추정 |
| 21 | DB 장애·스풀 시험(정상 10·중복 5·장애 3·재기동 3), 중복 수신 멱등, 보존 | SYS-DT-001~003 / VT-057~059 | 정의석 | G0 정상 commit 만 |
| 22 | 팔레타이징 위층 당겨 놓기(#37)·파지 실패 3회·팔레타이징 중 멈춤·재개 실기 | TR-PAL-05·08, pending #37 | 남현지·김학민 | 단위 시험만 |
| 23 | J6 회전의 sort_manager 전체 흐름 회차, gateway 한계 −125~−130° 카메라 끊김 | S2-T18 | 박병후 · 김학민(130 결정 대기) | S2T18-result §6, S2T18-run 9.2 |
| 24 | b_phys ≈ +3 mm 출처(핸드아이 x / 패드 중심) 정지 실험 | 핸드아이 ≤ 5 mm(제안) | 김학민·남현지(캘리브레이션), 박병후(분석) | U13 §6.7 |
| 25 | #41 pose ≥ 45 Hz 재측정(10/11 c90623f 이후) | T32/#41 | 김학민 | 10/10 최소 30.2 Hz |
| 26 | NFR-09 시연 전 안전 점검 기록(구역 이동 300/450 mm/s 포함) | NFR-09 | 김학민 | — |
| 27 | API 키·보안 점검 기록 | SYS-CT-006 | 정의석 | ADR-0015 "10/13 전체 이력 검사에서 키·토큰 없음" 만 |
| 28 | 공용 PC USB 포트 육안 확인 | measurements-1006 #5 | 정의석 | "육안 확인 필요" |
| 29 | 1차 리허설·시연 1회차 결과 | — | 김학민 | measurements-1015 는 2회차만 |

---

## E. VT-001~070 증거 매핑

표기: 결과 요약은 원문 수치. "없음" = 연결 가능한 실측 증거 없음(문서·IDL 반영만 있는 경우 포함).

| VT | SYS | 증거 (파일:절, 출처) | 결과 요약 |
|---|---|---|---|
| VT-001 | FR-001 | measurements-1008 #7 [레포]; measurements-1010 "G0-2"·"전체 재기동" [레포] | 10/08 도메인 30: not_ready [ROBOT, SERVO, OCR, LOG]; 10/10 16:07 IDLE·ready true·not_ready [] |
| VT-002 | FR-002 | measurements-1006 #9 [레포]; -1010 #3·"사건" [레포] | 1920×1080 30 fps·노출 6.0 ms·WB 4600; 카메라 30.1 Hz; USB 끊김 사건 3회 |
| VT-003 | FR-003 | measurements-1008 #1·#8 [레포] | 29.8~30.0 Hz, 검출률 ≈ 99.9 %, 박스 10 → 트랙 10 |
| VT-004 | FR-004 | measurements-1010 "G0 1회차"(bag 확인) [레포] | box_id·track 1·goal `a494dab6`·attempts 1·SortResult·DB 1행 연결 |
| VT-005 | FR-005 | measurements-1008 #9 [레포]; -1010 G0 (`/voss/vision/label` 2개) [레포] | 녹화 재생 10트랙 정답; G0 label 2건 track 1 |
| VT-006 | FR-006 | ADR-0008 결과 [레포]; measurements-1010 G0 [레포] | 정지 50/50; G0 대치동 1.00 AGREE → B |
| VT-007 | FR-007 | measurements-1008 #4·#5 [레포] | 핸드아이 T16 최대 4.56·터치 2.44 mm; 이동 중 최대 4.08(지연 0)·2.73 mm(60 ms) → `moving_verified` true |
| VT-008 | FR-008 | ADR-0002 판정; measurements-1010 G1 [레포] | G1 20/20, FF+P A안 유지 |
| VT-009 | FR-009 | measurements-1010 #6·G0 [레포] | 닫기 1685 ms·1998 ms, 닫히는 동안 추종(GRASP 중 TCP x 이동) |
| VT-010 | FR-010 | measurements-1010 #4 [레포]; -1012 §2 C [레포] | VERIFY 24회 grip True·폭 40.6~41.5·DROPPED 0; 폭 밖 55.5~55.9 → WIDTH_OUT 3/3 |
| VT-011 | FR-011 | measurements-1012 §2 C [레포]; FIELD-1012 §3 [레포] | 재시도 실기 0회(retry_room_ok false 3/3, sim 만), max_attempts 1 |
| VT-012 | FR-012 | measurements-1008 #12 [레포]; -1010 #8 [레포] | 15칸 15/15 OK 17.4~32.3 s |
| VT-013 | FR-013 | measurements-1010 G0 (RUNNING 복귀)·#7 [레포] | PLACE 52.9 s(OBSERVE 복귀 포함), VIEW·OBSERVE 각 8.0 s |
| VT-014 | FR-014 | measurements-1010 G0 [레포]; -1015 §2 [보고] | G0 commit 뒤 SELECT 1행; 시연 sort_log PLACED 19·HELD 1 |
| VT-015 | FR-015 | measurements-1006 #10 [레포] | 개인 PC 참고 9/9 + 정지 예외 1, 미포함 10 → 0 |
| VT-016 | FR-016 | 없음 | STT 녹음 20개 미측정 (#10 의 STT 322~350 ms 는 지연값) |
| VT-017 | FR-017 | palletizing_report TR-PAL-01 [레포] | 오프라인(LLM 없이) 6건 통과만 |
| VT-018 | FR-018 | measurements-1010 G0·G1 [레포]; -1015 §1 [레포] | start → RUNNING(G0·G1), 시연 단계 1 ✅(HMI) |
| VT-019 | FR-019 | measurements-1012 §2 C·D [레포]; -1010 "사건" [레포] | FAILED → PAUSED → resume → OBSERVE; PAUSED 에서 start 거부 기록. 시연 단계 7 미실시 |
| VT-020 | FR-020 | 없음 | 시연 단계 2 미실시 |
| VT-021 | FR-021 | 없음 | PASSED·NON_TARGET 실기 없음 |
| VT-022 | FR-022 | measurements-1015 §2·§3 [레포, bag]; ADR-0013 [레포] | 되읽기 TTS bag 12:13:15, 질문 say 발행; FIFO 재생 확인 |
| VT-023 | FR-023 | measurements-1012 §2 E [레포]; -1015 §6 [보고]; ADR-0008 [레포] | 서보 비간섭(주기 최대 37.4 ms); 2단계 고친 판 goal 안 확정 5/5, 기본 켬 |
| VT-024 | FR-024 | measurements-1010 G1 10회차 [레포]; -1015 §1 [레포] | CODE_ONLY 0.60→0.65 LOW_CONF → 재확인; 020 conf 0.2947 → 재확인 |
| VT-025 | FR-025 | measurements-1010 G1 10회차·#7 [레포]; -1015 §1 [레포] | 10/10 VIEW·재판독 후 PICK 미구현; 10/15 재확인 4건 |
| VT-026 | FR-026 | measurements-1015 §1 [레포, bag] | "역삼동입니까?"·3지 질문 |
| VT-027 | FR-027 | measurements-1015 §1 [레포, bag] | 020·010 작업자 답 → A(OPERATOR) |
| VT-028 | FR-028 | measurements-1015 §1 [레포, bag]; -1010 G1 10회차 [레포] | 016 30.0 s 무응답 → HOLD(NO_ANSWER); 10/10 30 s → NONE |
| VT-029 | FR-029 | 없음 | 시연 6·8 미실시 |
| VT-030 | FR-030 | measurements-1015 §1·§3 [레포, bag] | 시연 전체를 HMI 입력으로(`/voss/voice/intent` 0건), MQTT·HMI 버튼 ✅ |
| VT-031 | FR-031 | measurements-1015 §3 [레포/보고]; palletizing_report TR-PAL-10 [레포] | HMI 버튼·3D 배치도 ✅(보고값). 6개 표시·3초 UNKNOWN 실기 확인 기록 없음 |
| VT-032 | FR-032 | palletizing_report §1 [레포] | 투입 예정 기본값 10(S2-T22 미구현 시점), 실기 남은 수 기록 없음 |
| VT-033 | FR-033 | measurements-1010 "전체 재기동" [레포] | T2·T6·T8 sha `db97243ec6ef` 일치 |
| VT-034 | FR-034 | measurements-1010 "G1 첫 박스" [레포]; -1012 선택·C2 [레포] | PLACE 시간 초과 → FAILED DEVICE_ERROR; LOST cause BOX_MISSING(VISION_DOWN 오분류 0) |
| VT-035 | OP-001 | 없음 | 미구현(시연 4 제외) |
| VT-036 | OP-002 | 없음 | — |
| VT-037 | IF-001 | measurements-1010 G0 bag [레포] | track/stage/stamp 연결 실기 1회(G0) |
| VT-038 | IF-002 | measurements-1010 #5·#6 [레포] | 액션 OK·CANCELED/STOP_OK 2/2 |
| VT-039 | IF-003 | measurements-1006 #3 [레포]; -1008 #14 [레포] | speedl 단위 mm/s 실로봇 확인(5 mm/s × 2 s = 10.01 mm), RG2 보고 폭 ≈ 실제 + 10 mm |
| VT-040 | IF-004 | measurements-1010 G0 [레포] | SortResult·DB 행 필드(code·dong·zone·attempts) |
| VT-041 | IF-005 | 없음 | 시연에서 intent 경로 미사용 |
| VT-042 | IF-006 | measurements-1015 §0·§3 [레포]; voice_web_link.md [레포/밖] | MQTT 실기 ✅; 시연 빌드 MQTT 새 토픽(`voss/voice/text` 등) main 문서 미반영 |
| VT-043 | IF-007 | measurements-1010 #0·-1012 §3 [레포] | config sha 기록, `belt.speed_cmps` 소비자 = belt_servo 뿐 확인 |
| VT-044 | IF-008 | measurements-1006 #3 주의점 1 [레포] | 두산 구독 reliable/depth 10·20, best_effort 퍼블리셔 불연결 |
| VT-045 | PF-001 | ADR-0002·measurements-1010 [레포] | 20/20 (A 행 1) |
| VT-046 | PF-002 | ADR-0008; measurements-1015 §6 [레포/보고] | 정지 50/50; 추종 실기 31장 + 오프라인 105장 모두 정답 (A 행 2) |
| VT-047 | PF-003 | 없음 | 미측정 |
| VT-048 | PF-004 | measurements-1015 [레포, bag] | 정상 최장 18.4 s, 재확인 포함 67.5 s |
| VT-049 | PF-005 | ADR-0013 (예비만) [레포] | 미측정 |
| VT-050 | PF-006 | measurements-1012 §2 A [레포]; -1015 §6 [보고] | 중앙 33.3·최대 37.4 ms; 10/15 최대 39.8 / 38.3 ms |
| VT-051 | PF-007 | measurements-1008 #1·#8, -1010 #5 [레포] | 카메라→발행 p95 49~61 ms(부분 구간) |
| VT-052 | PF-008 | 없음 | 미측정 |
| VT-053 | SF-001 | measurements-1006 #3, -1010 #5·#12 [레포]; -1015 §1 [보고] | speedl 끊겨도 계속 감 → watchdog 0 속도 + move_stop; 정지 0.24 s·4.98 mm 등; 10/14 stop 4/5 TIMEOUT |
| VT-054 | SF-002 | measurements-1010 #0·#2, -1008 사건 18:26 [레포] | z ≥ 78·x −107~638·100 mm/s, 공간 제한 77.45 정지, TCP 미등록 NOT_CONFIGURED 가드 |
| VT-055 | SF-003 | measurements-1008 사건 18:26 [레포]; g0-runbook 역할 [레포] | 실제 비상정지 사용 1회(벨트 충돌 직전), 비상정지 담당 배치 |
| VT-056 | SF-004 | measurements-1015 §1, -1012 §2 C [레포] | 재확인 4건 처리; 파지 실패 → FAILED·PAUSED·후퇴 |
| VT-057 | DT-001 | 없음 | 중복 시험 없음 |
| VT-058 | DT-002 | measurements-1010 G0 bag [레포] | `/voss/log/status` OK 521·DB_ERROR 0(정상만) |
| VT-059 | DT-003 | 없음 | — |
| VT-060 | CT-001 | measurements-1006 #2·#5 [레포] | DRCF GF02120100·DRFL GL013303, MSI Katana·RTX 4060 8 GB·RAM 32 GB, USB 육안 미완 |
| VT-061 | CT-002 | measurements-1006 #7, -1008 #4 [레포] | 깊이 끔, 벨트 평면 z 100.8, RGB + 핸드아이 |
| VT-062 | CT-003 | measurements-1008 #15, -1010 #9 [레포] | 큐 30.4 분 78/78; 64.5 분 FAULT 0, pose 최소 30.2 Hz |
| VT-063 | CT-004 | measurements-1006 #1, -1013 §5 [레포] | h250 4.89 → 4.73 cm/s, 수동 운전, 한 번에 1박스(g1-gate 고정 조건) |
| VT-064 | CT-005 | measurements-1010 "G0 준비 상태" [레포] | DB 컨테이너 postgres:16 healthy; 비전은 호스트 venv 실행 기록 — 비전 컨테이너 실기 증거 없음 |
| VT-065 | CT-006 | ADR-0015 결정 1 [레포]; measurements-1010 G0 준비(`.env` 값 기록 안 함) [레포] | 10/13 이력 검사 키·토큰 없음(검사 기록 상세 없음) |
| VT-066 | MT-001 | U3-run B, U-E-run §1, S2T14-run §6, S2T18-run 2.5, palletizing_report, voice_web_link [레포] | sim_check·에뮬레이터·오프라인 시험·녹화 재생 경로 존재(실기와 구분 표기) |
| VT-067 | PF-009 | measurements-1015 [레포, bag] | 20/20 올바른 구역(D7 ≥ 16/20) |
| VT-068 | EN-001 | measurements-1006 #9 [레포] | 노출 6.0 ms·WB 4600, 포화 0.33 % |
| VT-069 | EN-002 | measurements-1006 #6, -1012 §2 B-2 [레포] | 상류 벨트 시작 구간은 로봇 미도달, OBSERVE 시야 x −184~+13 |
| VT-070 | EN-003 | measurements-1010 #1·#2, -1008 #13·#15, S2T18-result §2 [레포] | 벨트 프레임 접촉 높이, 트레이 벽 비간섭(90 mm 개방), 케이블 ±91°·−123° 육안 이상 없음, USB 끊김 사건 |

연결 증거 "없음" VT: 016, 020, 021, 029, 035, 036, 041, 047, 049(예비만), 052, 057, 059 — 12개(049 포함).

---

## F. 증거 원천 목록

| 파일 / 위치 | 날짜(내용) | 마지막 반영 | 출처 구분 | 비고 |
|---|---|---|---|---|
| docs/measurements-1006.md | 10/06~10/08 | — | 레포 | 원본 `~/voss_ws/measure_1006_data/`, Drive `raw/1006/`·`raw/1007/`·`raw/1008/wake_1m/` [밖] |
| docs/measurements-1008.md | 10/08 | — | 레포 | Drive `raw/1008/`, `~/voss_data/1008/grip/`·`soak/` [밖] |
| docs/measurements-1010.md | 10/10 (G0·G1·VIEW·15칸·#41) | 10/11 PR 옛 #145 | 레포 | Drive `raw/1010/`(bag 약 60 GB), `~/voss_data/1010/` [밖] |
| docs/measurements-1012.md | 10/12 U9 s2·s3 | 10/13 4464eee | 레포 | `~/voss_data/1012/u9_tools/`, Drive `raw/1012/` [밖] |
| docs/measurements-1013.md | 10/13 19:32~21:32 S4 | 10/14 `_2#36` | 레포 | 묶음 `S4-1013-u13.tar.gz`(`~/voss_data/1014/u13/`) [밖] |
| docs/measurements-1015.md | 10/15 시연 2회차·T19 | 10/15 #174 | 레포(bag 대조값) + 보고(§6 전체, 3D·DB 행 등) | `~/voss_data/1015/demo2`·`demo2_rows.md`·`t19s2/`·`t19s2b/`, Drive `1015/` [밖] |
| docs/g1-gate.md | 10/10 절차·결과 머리말 | — | 레포 | — |
| docs/g0-runbook.md | 10/10 절차(§5 증거표 미기입) | — | 레포 | — |
| docs/sprint2-gate.md | 10/13 절차(§5 기록표 미기입) | — | 레포 | — |
| docs/verification/palletizing_report.md | 10/13 오프라인 검증(로봇 없음) | — | 레포 | §8 실기 체크리스트 미기입 |
| docs/demo-script.md | 대본 v2 + 10/15 결과 한 줄 | — | 레포 | §5 기록표 미기입 |
| docs/adr/0002-grasp-method-gate.md | G1 판정 10/10(확인 10/11) | — | 레포 | — |
| docs/adr/0012-numeric-targets-approved.md | 승인 10/08, 변경 10/13(D7) | — | 레포 | — |
| docs/adr/0014-sprint2-gate.md | 판정 10/13, 시연 결과 10/15 | — | 레포 + 보고(음성 기동 판정 근거 Slack) | — |
| docs/adr/0008·0013 | OCR 결과(10/06, 10/15 추가)·TTS 예비 | — | 레포 | — |
| docs/adr/0015-repo-migration.md | `_2#n` 번호 대응 | 10/15 종료 | 레포 | — |
| docs/testing/voice_web_link.md | 10/13 Web PC E2E | 10/14 `_2#40` | 레포(결과 txt 는 Web PC 로컬 = 밖) | — |
| src/voss_servo/design/FIELD-1010-analysis.md | 10/10 분석 | 10/13 | 레포 | — |
| src/voss_servo/design/FIELD-1012-analysis.md | 10/12 분석·T28 판정 문안 | 10/13 `_2#21` | 레포 | — |
| src/voss_servo/design/U13-belt-along.md | 10/13 S4 분석·FF 4.56 근거 | 10/14 | 레포 | — |
| src/voss_servo/design/S2T18-result.md | 10/15 J6 실기 | 10/15 #179 | 레포 | `~/voss_data/1015/u14/` [밖] |
| src/voss_servo/design/S2T14-run.md | 절차 + 개인 PC sim·에뮬레이터 결과 | 10/14 | 레포(에뮬레이터 = 보조 근거) | 실기 결과는 measurements-1013 §4 |
| src/voss_servo/design/U-E-run.md, U3-run.md, S2T18-run.md 2.5 | 에뮬레이터·sim | 10/10~10/15 | 레포(실기 아님) | — |
| data/servo/attempts/*.jsonl (13개) | 10/12 4개·10/13 9개 | 10/13·10/14 | 레포 | 10/10 시도 로그는 레포에 없음(Drive `raw/1010/logs/servo/`) |
| 태그 demo-20261015 `data/servo/attempts/` (10개) | 10/13 14:45~10/15 10:30 | 25a726e | 태그(main 아님) | 리허설·게이트 시도 로그, 집계 문서 없음 |
| BRD v1.7 (scratchpad `p1/in/brd_v1.7.txt`) | NFR-01~16, 10.8 | — | 요구 원천(실측 10/12 팔레타이징 9.6 s 는 보고값) | — |
| docs/requirements/srd/markdown/01·04 | SRD v1.0 §6·§8, VT 표 | — | 요구 원천 | — |
