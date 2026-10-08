# U1 belt_servo 뼈대 — High-level design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u1-skeleton` · 작성 2026-10-07~08
- 상태: **HLD 승인(박병후)**, 10/08 리뷰 반영(아래 6절). Detail design 검토 중 — 이 문서는 설계 단계 작업 노트다. 팀 계약은 docs/interfaces 가 우선이다.
- 범위: 30 Hz 타이머·최신값 보관·액션 서버 골격, 기동 검사(null → READY 거부, version·sha256 로그), phase 전이 순수 함수, 로그 스키마. 제어 계산(U2)·파지 동작(U5)은 자리만 둔다.

## 0. 이 작업에서 정한 것 (브리핑 단계 승인)

| 항목 | 결정 |
|---|---|
| 로그 위치 | ① 틱 로그(30 Hz, JSON Lines) `data/servo/ticks/` → git 미추적(.gitignore 는 PL 에게 요청) ② 시도 로그(attempt 당 1줄) `data/servo/attempts/` → 커밋 대상. 게이트 집계(ADR-0002)는 ② 만 쓴다. ② 의 키는 ① 의 부분집합 |
| grip_detected | #92 로 Gripper.srv 응답에 `grip_detected`·`message` 가 들어왔다 → 필드명 파라미터 없이 직접 쓴다. 로그의 gripper 항목에 `message` 포함 |
| U1 출력 | 항상 속도 0 (제어는 U2) |
| 미측정 값 | null → READY 거부 |

## 1. 개념 세 개

- **순수 함수**: 같은 입력이면 항상 같은 출력, ROS·시계·파일을 건드리지 않는 함수. 계산기처럼 숫자만 넣고 빼므로 pytest 로 로봇 없이 시험한다.
- **액션 서버**: 주문 접수 창구. 손님(sort_manager)이 "track 7번 집어 줘"라고 주문(goal)하면 ① 받을지 거절할지 정하고 ② 진행 상황(feedback: 지금 TRACK 중)을 알려 주고 ③ 마지막에 결과 봉투(result: grasped·reason·attempts)를 한 번 건넨다. 손님은 중간에 취소(cancel)할 수 있다.
- **Future / async**: 아직 비어 있는 결과 봉투. 액션 실행 함수는 봉투를 들고 기다리기만 하고, 실제 일은 30 Hz 타이머가 한다. 타이머가 "끝났다"며 봉투를 채우면 실행 함수가 깨어나 결과를 돌려준다. 실행기(executor) 하나로도 기다리는 동안 타이머가 막히지 않는다(DESIGN.md DEC-14).

## 2. 모듈 구성

```
┌──────────────────────── belt_servo.py (ROS 껍데기, 판단 없음) ────────────────────────┐
│                                                                                        │
│  /voss/vision/box ─▶ on_box()  ─▶ latest_box[track_id] (+수신 시각)  best_effort·구독 depth 5 │
│  /voss/robot/pose ─▶ on_pose() ─▶ latest_pose (+수신 시각)            best_effort·depth 1  │
│                                                                                        │
│  액션 /voss/servo/track_and_grasp                                                      │
│    goal_cb   ─▶ "READY 인가? 바쁜가?" ─▶ ACCEPT / REJECT                                │
│    cancel_cb ─▶ 취소 표시만 세움 (실제 처리는 타이머)                                    │
│    execute   ─▶ 결과 봉투(Future) 들고 대기 ◀───────────── 타이머가 채움                 │
│                                                                                        │
│  30 Hz timer ─▶ ① 이벤트 모으기(입력 나이·valid·취소 표시 …)                            │
│                 ② fsm.step(상태, 이벤트)          ── 순수 ──▶ 다음 phase·reason        │
│                 ③ 속도 계산 = 0 (U2 에서 control.py 로 교체)                            │
│                 ④ servo_cmd 발행 (TwistStamped, base_link)                             │
│                 ⑤ feedback 발행 (phase 만 — err_u/err_v 는 #102 로 삭제)               │
│                 ⑥ log_schema 로 틱 레코드 → data/servo/ticks/*.jsonl                    │
│                 ⑦ 시도 종료면 시도 레코드 → data/servo/attempts/*.jsonl                 │
│                 ⑧ 종료면 봉투 채움 + 0 속도 유지 구간 시작                               │
│                                                                                        │
│  service client: /voss/robot/gripper, /voss/robot/stop (U1 은 만들기만, 호출은 U5)       │
└────────────────────────────────────────────────────────────────────────────────────────┘
        ▲ 기동 시 한 번
        │
  params.py (순수)            fsm.py (순수)                  log_schema.py (순수 + 작은 파일 쓰기)
  ─ 키 표(이름·단위·필수)      ─ Phase 6종 + IDLE·종료        ─ 틱 레코드 필드 = 지시서 스키마 전부
  ─ null/미전달 → 거부 키 목록 ─ 이벤트 → 다음 상태 + reason  ─ 시도 레코드 필드 ⊂ 틱 필드
  ─ direction 노름 1±0.01     ─ attempts 카운터(≤3)          ─ dict → JSON 한 줄
  ─ version·sha256 계산       ─ grasped 조건(닫힘만으로 ✗)   ─ JsonlWriter(파일 열기·한 줄 쓰기)
  → ReadyReport               → Transition
```

| 모듈 | 책임 | 하지 않는 것 | 테스트 |
|---|---|---|---|
| `params.py` | 파라미터 키 정의, 기동 검사, version·sha256 계산 | ROS 파라미터 선언(노드가 함) | `test_params.py` |
| `fsm.py` | phase 전이, reason 결정, attempts 세기, grasped 판정 | 이벤트 계산(입력 나이 등), 속도 계산 | `test_fsm.py` |
| `log_schema.py` | 레코드 모양 정의, 직렬화, 파일에 한 줄 쓰기 | 값 계산 | `test_log_schema.py` |
| `belt_servo.py` | 구독·발행·액션·타이머 연결, 이벤트 모으기 | 판단 로직(위 모듈에 위임) | 프로세스 안 기동 시험 + `ros2 run` 실물 로그 |
| `config/belt_servo.yaml` | servo 전용 값(미측정 null, 제안값은 주석) | belt·gripper 값의 원본(bringup 이 voss_config 에서 넘김) | — |

## 3. 데이터 흐름 규칙

1. **콜백은 보관만.** 구독 콜백은 계산하지 않고 최신값과 받은 시각만 저장한다. box 는 **track_id 별 사전**에 트랙마다 최신 하나를 둔다 — 트래커는 박스마다 메시지를 따로 보내므로(한 프레임에 박스 2개 = 메시지 2개) 최신값 하나만 두면 다른 박스가 내 박스를 덮어쓴다. 같은 이유로 box 구독 depth 는 5 로 둔다(발행 쪽 best_effort·depth 1 과 호환, depth 는 QoS 호환 조건이 아니다). 같은 트랙에서 stamp 가 뒤로 간 메시지는 버린다. 오래된 트랙 항목은 지운다. pose 는 하나뿐이라 depth 1.
2. **판단은 타이머 한 곳.** 상태가 바뀌는 곳이 하나라 순서 꼬임이 없고, 틱 하나 = 로그 한 줄이 된다.
3. **FSM 은 이벤트만 본다.** "pose 가 0.5 s 넘게 안 왔다" 같은 판단은 노드가 이벤트 플래그로 만들어 넘기고, FSM 은 플래그 → 전이만 한다. FSM 테스트에 ROS 가 필요 없다.
4. **READY 는 기동 때 한 번.** 정적 파라미터는 정지 상태에서만 바뀌므로(MC-009) 실행 중 재검사하지 않는다. READY=false 면 모든 goal reject, 기동 로그에 빠진 키 이름.
5. **끝은 반드시 0 속도.** goal 이 어떻게 끝나든(성공·중단·취소·예외) 이후 일정 구간 0 속도를 반복 발행한다(ADR-0010: 스트림이 끊겨도 로봇이 계속 간다). U1 은 원래 항상 0 이지만 이 구조는 지금 만든다.
6. **비전 사각 구간(10/08 반영).** 카메라가 공구축에서 약 8 cm 옆이라 핑거 끝이 박스 윗면에 닿는 높이부터 송장이 화면 아래 끝에 걸리고, box_tracker 는 가장자리에 걸린 송장을 내지 않는다(`border_px`). 그래서 마지막 약 19~20 mm 하강·GRASP·LIFT·VERIFY 동안 박스 관측이 없다. 이 구간에서는 박스 미수신·invalid 를 LOST/STALE 로 보지 않고, 마지막 유효 관측 + 벨트 속도 예측(FF)으로 간다. 사각 구간에 들어가기 직전 관측이 충분히 새로워야 한다. 비전이 다시 필요한 단계(재시도 PREPARE)로 돌아오면 LOST/STALE 시계를 그 시점부터 다시 센다. pose 끊김은 사각 구간에서도 STALE 이다.

## 4. 선택과 대안

| 선택 | 이유 | 미채택 대안 |
|---|---|---|
| 단일 executor + async execute(봉투 대기) | DEC-14, 스레드가 없어 경쟁 상태 없음 | MultiThreadedExecutor + 락: 근거가 생기면 |
| 판단 로직을 순수 모듈 3개로 분리 | 로봇 없이 pytest, U2·U5 가 같은 자리에 끼움 | 노드 클래스 안에 전부: 시험이 어려움 |
| FSM 은 표 기반 함수(직접 작성) | DEC-13 명시적 FSM, 의존성 없음 | transitions 라이브러리·Behavior Tree: 미도입 |
| 로그는 타이머 안에서 동기 한 줄 쓰기 | 30 Hz × 짧은 한 줄은 부담이 작음 | 별도 스레드 큐: 지터가 측정되면 |

## 5. Detail design 에서 정할 것

- `err_u`·`err_v`(px)의 기준점 → **필드 자체를 삭제하기로 결정(10/08, #102, PR 진행 중).** 제어는 베이스 좌표 오차로 하고 쓰는 곳이 없으며 기준 픽셀을 belt_servo 가 알 방법이 없다. belt_servo 는 feedback 에 phase 만 채우고(머지 전에도 err_u/err_v 는 건드리지 않아 기본값 0), 기준점 파라미터와 남현지 확인 항목은 두지 않는다.
- 종료 후 0 속도 유지 시간 → `zero_hold_s` 0.5 s 제안(watchdog 200 ms + 정지 0.15~0.41 s 보다 길게). 이 구간에는 새 goal reject.
- READY 조건 → 파라미터만. gripper/stop 서비스는 호출 때 실패로 처리.
- 틱 로그 구간 → goal 진행 중 + 0 유지 구간. IDLE 틱은 쓰지 않는다.
- 비전 사각 구간 시작 높이(규칙 6) → 파라미터 `z.vision_cutoff_above_top_mm`(박스 윗면 기준 TCP 높이, null·제안 10 mm). 이 높이 아래에서는 박스 관측을 기다리지 않는다.

---

## 부록 A. 파라미터는 각각 무슨 뜻인가 (후보 목록 — 이름·기본값은 Detail design 에서 확정)

파라미터 = 노드를 켤 때 바깥에서 넣어 주는 설정값(재료표). `params.py` 는 재료표 검수원이다. 빠진 재료(null)나 이상한 값(방향 벡터 길이 ≠ 1)이 있으면 "READY 아님".

### A-1. bringup 이 넘겨주는 팀 공용 값 (원본 `config/voss_config.yaml`, 규칙 5 로 belt_servo 가 직접 읽지 않음)

| 파라미터 | 값 | 쉬운 뜻 | 쓰는 곳 |
|---|---|---|---|
| `belt.speed_cmps` | 4.8 | 벨트가 1초에 4.8 cm 움직인다 | 피드포워드(FF): 박스가 이 속도로 갈 걸 아니까 로봇도 미리 그만큼 따라 움직인다 (U2) |
| `belt.direction_base` | [0.99992, −0.01292, 0.0] | 벨트가 흐르는 방향 화살표, 로봇 바닥 좌표 기준, 길이 1 | 속도 × 방향 = 벨트 속도 벡터. 기동 때 길이 1±0.01 검사 |
| `gripper.pre_open_mm` | 90 | 다가가기 전 90 mm 벌림 | PREPARE (U5) |
| `gripper.grasp_width_mm` | 39 | 닫을 때 목표 폭(RG2 보고값, 실제 약 29 mm) | GRASP (U5) |
| `gripper.force_n` | 14 | 쥐는 힘 14 N | GRASP (U5) |
| `timing.latency_offset_ms` | 0 | 지연만큼 박스 위치를 미리 당겨 예측. 0 = 보정 없음(유효값) | 예측 위치 (U2, 튜닝 U10) |
| `config_version`·`config_sha256` | bringup 계산 | voss_config 판 번호와 지문 | 로그에 남겨 어떤 설정으로 한 시도인지 추적 |

sha256(지문): 파일 내용을 64자리 문자열로 요약한 것. 글자 하나만 바뀌어도 완전히 다른 값이 나온다.

### A-2. belt_servo 전용 값 (`src/voss_servo/config/belt_servo.yaml`)

| 파라미터 (후보) | 값 | 쉬운 뜻 |
|---|---|---|
| `grasp.tcp_z_below_top_mm` | 19 (확정) | 박스 윗면보다 19 mm 아래까지 핑거 끝을 내린다(27 − 8) |
| `reach.x_min_mm`·`x_max_mm` | −107 · 638 | 따라갈 수 있는 구간(748 mm). 넘으면 OUT_OF_REACH |
| `control.kp_per_s` | null | P 게인: 남은 오차 1 m 당 몇 m/s 로 더 밀어 줄까(1/s). 실기에서 정함 |
| `limits.max_speed_mps` | null(또는 제안값) | 보낼 속도 상한. 넘으면 자름(clamp) |
| `limits.max_acc_mps2` | null | 한 틱 사이 속도 변화 상한 |
| `z.approach_height_mm` | null | 하강 전 박스 위 대기 높이 |
| `z.lift_height_mm` | null | 집은 뒤 들어 올릴 안전 높이(grasped=true 조건) |
| `input.stale_timeout_s` | null | valid=false·pose 끊김이 이만큼 지속되면 STALE_INPUT. 로그 원인은 `BOX_INVALID`·`POSE_MISSING` 으로 나눈다 |
| `input.lost_timeout_s` | null (제안 0.5 = 트래커 15프레임) | 내 track_id 가 이만큼 안 보이면 LOST. **GRASP 가림(약 1.2 s)과 마지막 하강 사각 구간은 timeout 을 늘려서가 아니라 사각 구간에서 LOST 를 보지 않는 것으로 처리한다** — 1.2 s 보다 길게 잡으면 TRACK 중 진짜 LOST 를 늦게(박스 약 58 mm 이동 뒤) 안다 |
| `z.vision_cutoff_above_top_mm` | null (제안 10) | 박스 윗면 + 이 높이 아래로 TCP 가 내려가면 비전 사각 구간(규칙 6) |
| `rate_hz` | 30 | 타이머 주기 |
| `zero_hold_s` | 제안값 | goal 종료 후 0 속도를 계속 보낼 시간 |
| `log.dir` | `data/servo` | `ticks/`·`attempts/` |

- 재시도 최대 3회는 계약(TrackAndGrasp)값이라 파라미터가 아니라 상수.
- null 이 하나라도 있으면 READY=false, 로그에 그 키 이름. 개인 PC 시험은 sim.launch(U3)가 테스트 값을 넘긴다.

## 부록 B. 타이머 30 Hz 는 적절한가

결론: 적절하다. 지금 근거로는 올리거나 내릴 이유가 없다. 실제 주기·지터는 공용 PC 로그로 확인한다.

| 고려 요소 | 사실 (출처) | 의미 |
|---|---|---|
| 입력 `/voss/vision/box` | 30 Hz (topics.md, D435i RGB 30 fps) | 새 관측이 33 ms 마다 하나. 더 빨라도 새 정보 없음 |
| 입력 `/voss/robot/pose` | ~50 Hz, 스트리밍 중 `get_current_posx` 와 직렬 (ADR-0010 조건 5) | 오히려 느려질 수 있다 |
| 출력 speedl_stream | 30 Hz 명령 100 % 수용, 33.3 ms(최대 33.7) (measurements #3, PR #87) | 실로봇에서 검증된 유일한 주기 |
| 컨트롤러 큐 | speedl 구독 depth 10, 처리가 주기보다 느리면 밀림 (#3 주의점 2) | 주기를 올리면 밀림 위험 증가 |
| 로봇 반응 | 가속 한계가 `time` 보다 우선, 시작 지연 62 ms(acc 100)~114 ms(acc 20) (#3 주의점 5) | 33 ms 보다 촘촘한 명령은 대부분 뭉개진다 |
| 지연 예산 | 서보 루프 100 ms (architecture.md) | 30 Hz 평균 샘플링 지연 ≈ 17 ms, 50 Hz 로 올려도 7 ms 감소. 큰 지연은 카메라·YOLO·로봇 시작 |
| 틱당 박스 이동 | 48 mm/s ÷ 30 = 1.6 mm | 작다. 15 Hz 면 3.2 mm 에 관측 절반 버림 |
| gateway watchdog | 200 ms 제안 (F-04) | 6틱 손실까지 버팀 |
| Python·rclpy 지터 | 실시간 보장 없음 (DEC-13) | 30 Hz 는 여유, 100 Hz 는 어려움 |
| 계약 | topics.md·architecture.md "30 Hz" | 바꾸려면 interface 변경(규칙 2) |

주의: 타이머와 카메라 박자가 맞지 않아 관측 나이가 0~33 ms 로 달라진다. DEC-03 예측(촬영 시각 + 벨트 속도 × 경과 시간)이 stamp 로 보정하므로 문제 없고, 틱 로그에 box stamp·계산 시각·발행 시각을 남겨 공용 PC 에서 분포를 잰다. `rate_hz` 를 파라미터로 둔 이유.

## 부록 C. "판단 로직을 순수 모듈 3개로 분리" 란

순수 모듈 3개 = `params.py`, `fsm.py`, `log_schema.py`.

- `belt_servo.py` = 홀 직원: 주문 받기(goal), 손님 보기(구독), 서빙(발행). 바깥세상(ROS)과 닿는 일은 여기서만.
- 순수 모듈 = 주방 레시피 카드: 재료(입력) → 요리(출력). 손님도 홀도 모른다.

| 모듈 | 넣는 것 | 나오는 것 | 예 |
|---|---|---|---|
| `params.py` | 파라미터 값 묶음 | READY 인가? 아니면 어떤 키가 문제인가 | `{belt.speed_cmps: None}` → `ready=False, missing=["belt.speed_cmps"]` |
| `fsm.py` | 지금 단계 + 이번 틱 이벤트 | 다음 단계 + (끝이면) reason | `(TRACK, 박스 잃음)` → `끝, LOST` |
| `log_schema.py` | 이번 틱 값들 | JSON 한 줄 | `{phase: "TRACK", …}` → `'{"phase":"TRACK",…}'` |

왜 나누나: ① 로봇 없이 pytest 로 1초 만에 시험 ② 테스트는 통과했는데 실기에서 틀리면 문제를 ROS 연결·타이밍으로 좁힘 ③ U2 `control.py` 도 네 번째 카드로 같은 자리에 끼움.

```python
# test_fsm.py 한 케이스 모양 (예시)
result = fsm.step(state_in_track, Event(track_lost=True))   # TRACK 중 박스를 잃었다
assert result.terminal and result.reason == "LOST"          # 끝나고 이유는 LOST
```

덧붙임: `log_schema.py` 의 파일 쓰기(`JsonlWriter`)는 엄밀히 순수하지 않다. 레코드 만들기·JSON 변환(순수)과 파일에 한 줄 쓰기(작은 클래스)를 나누고, 테스트는 임시 폴더(`tmp_path`)에 쓴다.

---

## 6. 변경 기록

| 날짜 | 변경 |
|---|---|
| 10/07 | HLD 승인 (박병후) |
| 10/08 | PR #95(box_tracker) 검토 의견 반영: box 를 track_id 별 사전 + 구독 depth 5 로(규칙 1·그림), 틱 로그에 `position_source`·`calib_version` 추가, `err_u`·`err_v` 기준 픽셀은 비전에서 받음(남현지 확인 항목) → 같은 날 필드 삭제로 대체(#102). `lost_timeout_s` 를 GRASP 가림보다 길게 하자는 의견은 사각 구간 규칙으로 대신함(부록 A-2). 비전 사각 구간 규칙 6 추가(팀원 알림: 카메라가 공구축에서 약 8 cm 옆, 마지막 약 20 mm 하강은 비전 없이). STALE_INPUT 의 원인을 로그에서 박스·pose 로 구분 |
