# G1 게이트 — 추종 파지 20사례 (10/10 오후, 공용 PC)

> **10/10 결과: 통과** — s1 20사례 중 20 성공(최초 시도 20, 무효 6), A안 유지. 회차표는 `docs/measurements-1010.md`, 판정은 ADR-0002 "판정".

**판정 기준**(ADR-0002, SRD v1.0 SYS-PF-001·VT-045): **재시도 포함 이동 중 픽업 20사례 중 14 이상(70 %)**. 최초 시도와 재시도를 구분해 기록하고 **분모를 고정**한다. 미달이어도 자동 전환하지 않는다 — 측정 직후 게이트 회의에서 전원이 정하고 PL 이 ADR-0002 에 기록한다.

> 로봇·벨트·그리퍼를 움직이는 명령은 모두 사람이 비상정지 옆에서 실행한다(CLAUDE.md 규칙 6). 역할·비상정지·벨트 정지 담당과 기동 순서는 `docs/g0-runbook.md` 그대로다. **G0 를 통과한 뒤에 G1 을 한다.**

## 1. 측정 전에 합의할 정의 (측정 중 바꾸지 않는다)
| 항목 | 정의 |
|---|---|
| 사례 | 벨트 위 박스 1개에 보낸 `TrackAndGrasp` goal 1개. goal 안 재시도는 최대 3회(belt_servo 단독 카운터, `attempts`) |
| 성공 | result `reason=OK`·`grasped=true`(LIFT·VERIFY 완료 = 인계) **그리고** 영상에서 박스가 안전 높이까지 들려 있음. 적재(PLACE)는 G1 판정에 넣지 않는다(G0·G2 에서 본다) |
| 최초 시도 성공 | 성공이면서 `attempts=1` — 따로 센다(VT-045) |
| 분모 | "본 측정 시작"을 말한 뒤 보낸 goal **20개**. 연습은 선언 전에만. 선언 뒤의 실패·시간 초과·장치 오류는 빼지 않는다 |
| 무효(다시 한 회) | 측정 전에 정한 두 경우만: ① 박스를 정한 위치·방향과 다르게 놓음 ② goal 이 거부돼(belt_servo 미준비) 로봇이 움직이지 않음. 무효도 표에 남긴다 |
| 실행 경로 문제 | speedl·watchdog·호출 큐 같은 실행 경로 고장은 분모에 넣되 원인 `X` 로 표시해 폐루프 성능과 구분한다(ADR-0002) |
| goal 보내는 방법 | sort_manager(start → 판독 → goal → PLACE) 또는 박병후 시험 도구(track_id 지정). 회차표에 적는다. sort_manager 경로는 `move_to_zone` 이 있어야 하고, 없으면 시험 도구 + 사람이 박스 회수 |

**고정 조건**(바뀌면 측정을 멈추고 새 시리즈로 다시 20회):
- 벨트 h250(10/08 실측 4.77 cm/s, measurements-1008 #10). 아두이노는 레포 `conveyor_test` 스케치
- 박스 방향: 46 mm 변 = 벨트 방향, 송장 위(ADR-0009). 투입: 상류 표시선, 앞 박스 처리가 끝난 뒤
- 카메라 1920×1080·노출 6 ms·WB 4600. box_tracker `detector: seg`(ADR-0011)·`observe_source: hand_eye`·`pose_lag_ms: 15`(#140, gateway `pose_source:=joint_states` 기준 — 60 은 `service` 기준이던 #140 전 값), `config/hand_eye.yaml`·`belt_homography.yaml` 그대로
- belt_servo 파라미터 파일과 sha256, main 커밋 해시 — 시작 전에 기록

## 2. 시작 전 확인
- [ ] G0 통과 기록(g0-runbook 5절)
- [ ] g0-runbook 3절 **박스 회차 Go/No-Go** 전부 ✅ (F-04 기록·gateway 제한값·펜던트 공간 제한·TrackAndGrasp 1회 인계)
- [ ] 비상정지(학민)·벨트 12 V(병후)·기록과 촬영(의석) 자리
- [ ] 박스 5개 이상 준비(정식 송장 세트, 흐린 송장 제외), 회수·재투입 담당
- [ ] 녹화 시작 — 2단계 OCR(T19)용 `label_crop` 을 함께 받는다
```bash
mkdir -p ~/voss_data/1010
ros2 bag record -s mcap -o ~/voss_data/1010/g1_s1 --include-hidden-topics \
  /voss/sort/state /voss/sort/result /voss/vision/box /voss/vision/label /voss/vision/label_crop \
  /voss/robot/pose /voss/robot/state /voss/robot/servo_cmd /voss/log/status /rosout \
  /voss/servo/track_and_grasp/_action/feedback /voss/servo/track_and_grasp/_action/status \
  /camera/color/image_raw/compressed /camera/color/camera_info
```

## 3. 회차 기록표 (측정하면서 채우고 `docs/measurements-1010.md` 로 옮긴다)
시리즈: `s1` · 시작 시각 ____ · main ____ · belt_servo 파라미터 sha ____ · goal 경로(sort_manager / 시험 도구) ____

| # | 시각 | 박스(송장) | track_id | reason | attempts | 성공 | 최초 시도 성공 | 원인 | bag 시각 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | | |
| 2 | | | | | | | | | | |
| 3 | | | | | | | | | | |
| 4 | | | | | | | | | | |
| 5 | | | | | | | | | | |
| 6 | | | | | | | | | | |
| 7 | | | | | | | | | | |
| 8 | | | | | | | | | | |
| 9 | | | | | | | | | | |
| 10 | | | | | | | | | | |
| 11 | | | | | | | | | | |
| 12 | | | | | | | | | | |
| 13 | | | | | | | | | | |
| 14 | | | | | | | | | | |
| 15 | | | | | | | | | | |
| 16 | | | | | | | | | | |
| 17 | | | | | | | | | | |
| 18 | | | | | | | | | | |
| 19 | | | | | | | | | | |
| 20 | | | | | | | | | | |
| 합계 | | | | | | __/20 | __/20 | | | 무효 __회 |

**원인 분류**(실패마다 하나, 영상·로그로 박병후가 판정):
| 코드 | 원인 | 단서 |
|---|---|---|
| A | 접근 오차(좌표·지연) — 핑거가 박스 옆으로 빗나감 | 영상, BoxTrack `position_base` 와 TCP 차이 |
| T | 하강·닫힘 타이밍 | phase 시각, 영상 |
| G | 그립 판정(`grip_detected`·보고폭 범위) | `GRASP_FAILED`, gripper 응답 |
| R | 도달 한계 | `OUT_OF_REACH` |
| L | 입력 상실(검출 끊김·pose 끊김) | `LOST`·`STALE_INPUT`, box_tracker 5초 로그 |
| D | 장치(gripper·gateway·stop 응답) | `DEVICE_ERROR` |
| X | 실행 경로(speedl·watchdog·큐) — 성능 판단과 구분 | gateway 로그 |
| S | 시험 준비(놓은 위치·방향) — 무효 후보 | 영상 |

## 4. 게이트 회의 (측정 직후 30분, 전원, 기록 PL)
**보는 것:** 위 표, 원인 분포, 최초 시도 성공 비율, 실패 회차 영상.

| 결과 | 결정 |
|---|---|
| 성공 ≥ 14 | **통과 — A안(폐루프 FF+P) 유지.** ADR-0002 "판정" 절 기록 |
| 성공 < 14 | 셋 중 하나를 전원이 정한다: **① B안 개루프** — belt_servo 내부만 바뀌고 액션 인터페이스(`/voss/servo/track_and_grasp`)는 같아 sort_manager·비전은 그대로(ADR-0002 결과) · **② 범위 축소** — 벨트 감속(h500 = 2.38 cm/s)·여유 확대 · **③ A안 10/12 연장** — 10/12 오후 재측정, 그때도 미달이면 ① 또는 ② |
| 측정 불가(G0 미통과·파지 시퀀스 미완 등) | 사유를 적고 ③ 일정(10/12 측정)을 기본으로, ①·② 준비를 같이 시작할지 정한다 |

**판단 참고(PL 제안, 회의에서 확정):**
- 실패가 대부분 `X`(실행 경로)면 폐루프 성능 판단을 미루고 경로를 고친 뒤 다시 잰다(③ 일정).
- 대부분 `A`·`T`(제어)이고 14 에 가까우면 ③, 크게 미달이면 ①.
- `L` 이 많으면 비전 쪽(검출 끊김·지연)부터 본다(남현지).
- 10/13 통합·10/15 시연까지 남은 시간과, ① 전환에 걸리는 시간(박병후 추정)을 같이 본다. 일정이 밀리면 줄이는 순서(PL 제안): 신규 구역 교시(Should) → 규칙 변경 → B안 → 범위 축소.

**산출물:** ADR-0002 "판정" 절 · `docs/plan.md` G1 줄 · `docs/measurements-1010.md` 표 · Slack 공지.

## 5. ADR-0002 갱신 문구 초안 (회의 뒤 PL 이 채운다)
```
## 판정 (2026-10-10, G1 게이트)
- 측정: 20사례 중 __회 성공(__ %), 최초 시도 성공 __회, 무효 __회. 벨트 h250(4.77 cm/s), main ____, belt_servo 파라미터 sha ____ (measurements-1010 #__)
- 실패 원인: A __ · T __ · G __ · R __ · L __ · D __ · X __ · S __
- 결정: 통과(A안 유지) | ① B안 개루프 | ② 범위 축소: ____ | ③ A안 10/12 연장, 재측정 ____
- 이유: ____
- 영향: belt_servo 내부만(액션 인터페이스 동일) / 일정 ____
- 결정자 전원, 기록 PL
```
