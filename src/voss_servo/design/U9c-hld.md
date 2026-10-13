# U9-c HLD — 값·cause·로그 보강 (T28 #37)

근거: FIELD-1010-analysis(U-A) §4·§5 #1·#13·§6.1·§8 3·6, docs/measurements-1010 #13·§2. 지시서 U9c-37-values-cause-logs.
이 단위는 **관찰만 늘린다** — 제어 출력·FSM 전이는 바뀌지 않는다(값 두 개 제외).

## 0. 바뀌는 것 한눈에

| 묶음 | 무엇 | 제어에 영향 |
|---|---|---|
| ③ 값 | `reach.x_max_mm` 620 → 600, `grasp.close_time_max_s` 2.1 → 2.3 (yaml 3종·테스트) | 있음 — 추종 구간 끝이 20 mm 당겨지고, x 여유 필요 길이가 237.5 → 247.1 mm 로 늘어 하강 허용 TCP x 문턱이 382.5 → 352.9 로 내려간다(DD 1.1) |
| ④ cause | LOST 의 cause 를 `BOX_MISSING` / `VISION_DOWN` / `ROBOT_STALLED` 로 세분. reason 은 `LOST` 그대로 | 없음 (로그·결과 메시지 문자열만) |
| ④ 로그 | 틱: 박스 픽셀 u·v, 수신 기준 관측 나이, 측정 TCP 속도, 벨트 속도 추정, 원래 cause, 단계 진입 시각. gate_summary 하강 오차 = xy | 없음 |
| ⑥ 속도 추정 | goal 트랙 관측열 직선 맞춤 → 로그 + 2 % 차이 지속 시 WARN 1회 | **없음 — FF 는 설정값 그대로** |

## 1. 데이터 흐름

```
 /voss/vision/box ──► _on_box ──► _boxes[track]           (기존)
                         └──────► ctx.other_rx             (새: goal 중 다른 트랙 마지막 수신)
 /voss/robot/pose ──► _on_pose ─► _pose_value              (기존)
                         └──────► 직전 값·stamp 보관        (새: 측정 속도용)

 30 Hz 틱 (_tick_goal)
   ① _build_event ── fsm.step ──► Transition(reason, cause)      ← fsm.py 그대로
   ② [새] 진단 단계 (한 곳)
        ├ obs_hist ← goal 트랙의 새 유효 관측 (stamp, xyz)
        ├ v_meas  = diagnose.measured_velocity(직전 pose 값, 현재 pose 값)
        ├ stall_n = diagnose.stall_count(stall_n, |직전 명령|, |v_meas|)
        ├ v_est   = control.belt_speed_fit(obs_hist, 벨트 방향)    ─► 로그만
        ├ warn    = diagnose.speed_warn_step(...) ─► WARN 1회
        └ reason == LOST 이면 (cause_fsm = tr.cause 는 매 틱 보관)
             진단 = diagnose.lost_cause(발행자 수, 내·다른 트랙 수신 시각, stall_n, …)
             진단이 VISION_DOWN·ROBOT_STALLED 일 때만 tr.cause 를 그 값으로 (아니면 fsm cause 유지)
        ※ ② 전체를 try/except — 진단이 실패해도 goal 은 계속(진단 값 null + error 로그 1회)
   ③ control.command → 발행 → 틱 로그(새 필드) → ATTEMPT_END·GOAL_END → _finish(tr.cause)
```

- **cause 덮어쓰기는 ② 한 곳뿐**이고, fsm 이 낸 값은 `cause_fsm` 필드에 항상 남는다(fsm 판정 vs 진단 판정 구분). 진단이 특정 원인을 찾지 못하면 fsm cause 를 그대로 둔다 — U9-a 가 LOST cause 를 새로 만들어도 지워지지 않게.
- `Transition` 은 frozen dataclass → `dataclasses.replace` 로 cause 만 바꾼 새 값을 만든다. fsm.py 는 한 줄도 안 고친다.

## 2. 파일별 책임

| 파일 | 책임 | 비고 |
|---|---|---|
| `diagnose.py` **(새, 순수)** | 진단 상수(제안값·근거 주석)를 머리에 모음 · `measured_velocity` · `stall_count` · `lost_cause` · `speed_warn_step` | ROS import 없음. 주관 승인(10/12) |
| `control.py` | `belt_speed_fit` **추가만** (최근 N 점 직선 맞춤, 벨트 방향 성분) | 기존 함수·시그니처 변경 없음. 2차에서 FF 치환 후보라 control 에 둔다 |
| `log_schema.py` | 새 틱 키, 시도 키(부분집합 유지), `obs_age_s` 의미 주석 명시 | `obs_age_s` 이름 유지(10/10 원본 호환) |
| `belt_servo.py` | 관측열·직전 pose·다른 트랙 수신 시각·stall 계수·단계 진입 시각 보관, ② 진단 단계 호출, 틱 값 채우기 | 전이·제어 경로 변경 없음 |
| `gate_summary.py` | 하강 오차 열 → `err_along`·`err_cross` 최대(mm) 두 열, 힌트 VISION_DOWN→L·ROBOT_STALLED→X | 10/10 틱 로그에도 두 필드가 있어 과거 로그 그대로 집계 가능 |
| `config/*.yaml` 3종 | 값 2개 + 출처 주석 | src/voss_servo/config 만 |
| `sim_check.py` | 기대값 갱신(필요한 것만) | |
| test | 값·cause·스키마·속도 추정·gate_summary | |

수정하지 않음: `fsm.py`(U9-a·b), `grip.py`, `params.py` 의 검사 규칙(새 필수 키 없음 — 진단 문턱은 코드 상수라 실기 yaml 이 READY 거부되지 않는다), docs/interfaces·voss_msgs·레포 config.

## 3. cause 세분 규칙 (우선순위 위부터)

| cause | 뜻 | 판정 재료 | 힌트 |
|---|---|---|---|
| `VISION_DOWN` | 비전 전체가 끊김 (추정) | `/voss/vision/box` 발행자 0, 또는 다른 트랙이 내 트랙과 0.2 s 안에 함께 끊김 (DD D1 — box_tracker 는 미검출 프레임을 발행하지 않아 "모든 트랙 끊김"만으로는 박스 1개 LOST 와 구별 불가) | L |
| `ROBOT_STALLED` | 명령은 나가는데 로봇이 안 움직임 | 측정 TCP 속도 ≈ 0 이고 직전 명령 ≠ 0 인 틱이 N 연속 | X (gateway 로그로 X·D 구분) |
| `BOX_MISSING` | 내 트랙만 없음 (기존 그대로) | 위 둘이 아님 — fsm 의 cause 를 그대로 둔다 | L |

비전이 통째로 죽었으면 로봇 정지 여부와 무관하게 박스는 안 보이므로 VISION_DOWN 이 먼저다.

## 4. 벨트 속도 추정 (그림)

```
 벨트 방향 위치 s (mm)
   │                  ●  ●
   │            ●  ●            기울기 = 속도
   │      ●  ●                  (최근 N 점, 촬영 stamp 기준)
   │  ●
   └──────────────────────► 촬영 시각 t (s)
```
관측점 (t, 위치) 를 벨트 방향으로 투영한 s 에 직선 s = a + v·t 를 맞춰 v 를 얻는다. 점이 모자라거나 시간 폭이 짧으면 null. 새 관측이 들어온 틱마다 설정 속도와 비교해 2 % 넘게 다른 것이 M 번 연속이면 goal 당 WARN 1회. 관측열은 시도마다 새로 시작한다.

## 5. 위험·확인

- x_max 600·close 2.3: 정상 정렬 x 85~91 은 영향 없음. 문턱이 352.9 로 내려가는 것은 재시도 재접근(U9-b) 입력 — DD 1.1.
- 측정 속도: pose 소스가 `service` 면 값이 0.1 s 계단 → "값이 바뀐 시점" 기준 차분으로 계산(기존 `pose_value_stamp` 와 같은 생각), stall 문턱 N 은 계단 한 칸보다 길게.
- `count_publishers` 는 LOST 틱에서만 호출(매 틱 그래프 조회 안 함).
- 새 필드는 모두 "모르면 null". 시도 키 ⊂ 틱 키 assert 유지.
