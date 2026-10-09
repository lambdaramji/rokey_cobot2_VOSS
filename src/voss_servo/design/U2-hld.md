# U2 제어 순수 함수 — High-level design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u2-control` · 작성 2026-10-08
- 상태: **HLD 승인(박병후, 10/08)**, r2 독립 재검 반영 승인(10/08). Detail design: [U2-dd.md](U2-dd.md). 이 문서는 설계 단계 작업 노트다. 팀 계약은 docs/interfaces 가 우선이다.
- 범위: `control.py`(예측·현재 TCP 추정·FF+P·clamp·영역·Z 계획·0 명령) + `belt_servo.py` 의 `vel = ZERO` 자리 연결 + 새 파라미터. 그리퍼 호출(U5)·fake 노드(U3)·재시도 동작(U9)은 하지 않는다.
- 선행: U1(#109, main `13947a5`). 설계 근거 카드: DESIGN.md DEC-03(예측)·04(FF+P)·16(clamp)·17(Z 단계).

## 0. 이 작업에서 정한 것 (브리핑 단계 승인, 10/08)

| 항목 | 결정 | 근거 |
|---|---|---|
| P 항을 켜는 조건 | **박스가 지금 보일 때만** (사각 아님 + 이 트랙의 가장 최근 메시지 `position_valid=true`). 안 보이면 FF 만 | 사각 직전 오차는 신선하지 않다 (박병후) |
| PREPARE | 박스가 보이면 접근 높이에서 FF+P 추종 시작. 개방 완료 전에는 하강하지 않는다. (재검 r2: 안 보일 때 0 → TRACK 과 같은 FF) | 관측 자세 유효 좌표 창 약 2.1 s (measurements-1008 #11) |
| GRASP | **FF 만**(벨트 속도로 같이 감), z 는 파지 높이에 고정 | GRASP 에 왔다 = 정렬 완료. RG2 개폐는 약 1.2 s(measurements-1006 #4: open 90 → 1.21 s) — 그동안 멈추면 박스가 48 mm/s × 1.2 s ≈ 58 mm 밀려 나간다 |
| LIFT | x·y 0, z 만 위로 | U1 회신 ⑤ |
| 정렬 허용치 | 벨트 방향(`along`)·가로(`cross`) 둘로 나눔. cross 도 여유롭게 두지 않는다 | 그리퍼 여유는 가로 ±24.5 mm 뿐, 벨트 방향은 0 (ADR-0009) |
| 새 파라미터 | `input.pose_lag_ms` 60(측정값) 외 전부 null + 제안값 주석 | 값 규칙(voss_config.md), 미측정 제안값(ADR-0012 범위 밖) |
| Δt 음수 | 0 으로 자르고 로그에 표시 | 시계 차이로 미래 stamp 가 올 수 있음 |
| clamp | 벡터 크기 기준(방향 유지). 정지(0) 명령에는 가속 제한 없음 | ADR-0010: 끊기면 계속 간다 → 멈출 때는 바로 0 |
| 영역 판정 | 현재 TCP x 기준 (U2 지시서) | |
| Kp = 0 | FF 만 나간다 (개루프 = 프리셋, 별도 모드 없음) | B안 시작 위치 맞추기는 U4·U8a |
| **pose 값 갱신 0.1 s 대응** (r4, PR #122 학민 리뷰) | 외삽 기준 stamp = 위치 값이 바뀐 첫 메시지의 stamp | gateway service 소스는 50 Hz 로 보내도 값은 0.1 s 마다만 바뀐다(ADR-0010) → 메시지 stamp 로는 TCP 추정이 0~4.8 mm 톱니 |
| **파지 바닥·x 끝** (r4) | 파지 도달 문턱 < gateway z 하한 78 + 1 mm 이면 OUT_OF_REACH(`REACH_Z_MIN`) — 박스 z 는 plane_z 상수라 설정 불일치 때만 걸림. x_max 유효값 620 | gateway 가 자르면 at_grasp·X_MAX 판정이 확정적이지 않다. DESCEND 시간 상한은 U9 |
| **벨트 방향은 기다린다** (재검 r2) | xy 속도의 벨트 방향 성분 하한 0 — 박스가 TCP 보다 상류에 있어도 로봇은 상류로 가지 않고 기다린다. 가로 성분은 양방향 P 그대로 | 관측 자세(x −14.5)에서 박스는 x −97~−170 mm 에서 처음 보인다. 부호 제한이 없으면 P 가 상류로 돌진: Kp 4·오차 −170 mm 시뮬레이션에서 x −124 mm(한계 −107) → OUT_OF_REACH. 기다리기 규칙이면 상류 이동 0, 정렬 2~4 s 뒤 x ≈ −13~+7 mm (scratchpad sim_along.py) |

## 1. 개념 다섯 개 (처음 보는 것만)

**① 예측 (predict).** 사진은 과거다. 박스 사진을 찍은 시각(stamp)에서 지금까지 박스는 벨트를 타고 더 갔다.
```
촬영 시각 박스 위치 ●─────── 벨트 속도 × (지금 − 촬영 시각 + latency_offset) ───────▶ ◎ 지금 박스는 여기쯤
```
`position_base` 는 box_tracker 가 이미 pose 지연(60 ms)을 보정한 값이라 belt_servo 는 **다시 보정하지 않는다**(이중 보정 금지, measurements-1008 #6).

**② 현재 TCP 외삽 (tcp_now).** 로봇 pose 도 늦게 온다. pose 의 stamp 는 "응답을 받은 시각"인데 실제 로봇 상태는 그보다 약 60 ms 전 것이다.
```
pose 가 말한 위치 ●  (실제로는 stamp − 60 ms 의 위치)
                    └─ 마지막으로 보낸 속도 × (지금 − (stamp − 60 ms)) ─▶ ◎ 지금 TCP 는 여기쯤
```
pose 값은 50 Hz 로 와도 0.1 s 마다만 바뀔 수 있어서, 시작 시각은 **그 위치 값이 처음 온 메시지의 stamp** 로 잡는다(r4). 외삽(extrapolation) = 마지막 값과 속도로 앞을 추정. 너무 오래 외삽하면 엉뚱해지므로 상한(`pose_extrap_max_ms`)까지만 외삽하고 거기서 멈춘다(`min(h, 상한)`, 로그에 표시). 원본 pose 로 돌아가면 48 mm/s 에서 TCP 추정이 약 5.8 mm 뒤로 튀어 P 에 속도 계단이 생기므로 그렇게 하지 않는다(r2, 박병후 승인 — 지시서의 "상한 초과 시 외삽 없음"에서 바꿈). 48 mm/s 에서 60 ms ≈ 2.9 mm.

**③ 피드포워드 + P (ff_p).** 버스를 따라 뛰는 사람을 생각한다.
```
속도 명령 = 벨트 속도(FF: 버스가 이 속도로 가니까 나도 이만큼은 그냥 뛴다)
          + Kp × 오차(P: 아직 버스 문까지 남은 거리만큼 조금 더 빨리 뛴다)
```
Kp 단위는 1/s: 오차 10 mm, Kp 2 /s → 20 mm/s 를 더한다. Kp = 0 이면 FF 만(개루프).

**④ clamp (자르기).** 계산값이 너무 크면 상한으로 자른다. 두 가지.
- 속도 상한: ‖v‖ > v_max 면 같은 방향으로 길이만 v_max 로 줄인다(방향이 틀어지지 않게 축별로 자르지 않는다).
- 가속 상한: 한 틱 사이 속도 변화 ‖v − v_직전‖ 이 a_max × dt 를 넘으면 그만큼만 바꾼다(갑자기 홱 움직이지 않게). **0 으로 멈추는 명령은 예외** — 멈출 때는 바로 0.

**⑤ 벨트 방향·가로 분해.** 오차 화살표를 벨트 흐름 방향 성분과 그에 수직인(가로) 성분으로 나눈다.
```
           가로(cross) ▲
                       │   ● 박스
                       │  ╱ 오차 e
                       │ ╱
            TCP ◎──────┼────────▶ 벨트 방향(along) = belt.direction_base
along = e · d (내적)   cross = e − along·d 의 길이
```
그리퍼는 가로로 닫히므로 가로 오차는 조금 견디지만 벨트 방향 오차는 핑거가 박스 앞·뒤 면을 친다 → along 을 더 엄격하게.

## 2. 모듈 구성

```
┌──────────────────── belt_servo.py (ROS 껍데기) — 30 Hz 틱 한 번 ────────────────────┐
│ ① 최신 box(내 track_id)·pose·마지막 발행 속도를 꺼낸다                              │
│ ② geo = control.geometry(...)        ── 순수 ──▶ 예측 박스·보정 TCP·목표·오차·플래그 │
│        (aligned · at_grasp_height · at_lift_height · reach · visible)                 │
│ ③ ev = TickEvent(U1 입력 플래그 + ②의 플래그)                                        │
│ ④ tr = fsm.step(state, ev)           ── 순수 (U1 그대로) ──▶ 다음 phase              │
│ ⑤ vel = control.command(tr, geo, …)  ── 순수 ──▶ 새 phase 기준 속도 (+clamped 표시)  │
│        stopping·terminal → 항상 0                                                    │
│ ⑥ servo_cmd 발행 → 마지막 발행 속도로 기억 (다음 틱 ②·⑤ 의 입력)                     │
│ ⑦ 틱 로그: predicted · tcp_target · error · clamped · 원본 pose · 보정 TCP           │
└──────────────────────────────────────────────────────────────────────────────────────┘

control.py (순수, ROS·시계·파일 없음, NumPy 벡터, 단위 m·m/s·s)
  predict()      관측 + 벨트 속도 × (Δt + offset)
  tcp_now()      pose + 마지막 명령 속도 × min(지금 − (stamp − lag), 상한) — 상한까지 외삽(tcp_extrap_capped)
  tcp_target()   예측 박스 윗면 → TCP 목표 (z 는 phase 별: 접근·파지·LIFT 높이)
  split_error()  오차 → (벨트 방향 along, 가로 cross)  (z 는 뺀다)
  ff_p()         FF + Kp·e  (XY, 벨트 방향 성분 하한 0 = 기다리기)  ·  z_speed()  Z 는 kp_z
  z_plan()       phase → 목표 높이와 z 속도 상한
  clamp()        속도·가속 상한
  in_reach()     TCP x 가 구간 안인가 → None | X_MIN | X_MAX
  zero_cmd()     0 벡터
  geometry() · command()   위 함수를 묶은 틱 단위 입구 2개 (노드는 이 둘만 부른다)
```

**왜 두 번 부르나 (②와 ⑤).** FSM 이 "정렬됐나?"를 알아야 다음 phase 를 정하고(②→④), 속도는 **바뀐 phase** 기준으로 내야 한다(④→⑤). 예: 이번 틱에 TRACK → DESCEND 로 바뀌면 이번 틱부터 하강 속도를 낸다. 기하 계산(예측·오차)은 ②에서 한 번만 하고 ⑤는 그 결과를 재사용한다.

| 모듈 | 책임 | 하지 않는 것 | 테스트 |
|---|---|---|---|
| `control.py` (신규) | 위 함수들, 단계별 속도 규칙(3절), 전환 플래그 계산 | phase 결정(fsm), ROS 메시지 다루기, 시계 읽기 | `test_control.py` |
| `fsm.py` | U1 그대로. TickEvent 의 `aligned`·`at_grasp_height`·`at_lift_height`·`reach` 를 이제 실제 값으로 받는다 | — | `test_fsm.py`(변경 없음 예상) |
| `params.py` | 새 키 9개 추가 + 교차 검사 | — | `test_params.py` 에 추가 |
| `belt_servo.py` | 메시지 → 숫자 변환, 마지막 발행 속도 보관, ②⑤ 호출, 로그 채우기 | 계산 | `test_node.py`·`test_action_e2e.py` 갱신 |
| `log_schema.py` | 보정 TCP·외삽 여부 등 키 추가 | — | `test_log_schema.py` |

## 3. 단계별 속도 규칙 (승인된 표)

| phase | XY | Z |
|---|---|---|
| PREPARE | 보이면 FF+P, 안 보이면 FF (재검 r2) | 접근 높이로 |
| TRACK | 보이면 FF+P, 잠깐 안 보이면 FF 만 (길어지면 FSM 이 LOST·STALE 로 끝냄) | 접근 높이 유지 |
| DESCEND | 사각 진입 전 FF+P, 사각 구간 **FF 만** | 하강 속도 상한 지키며 파지 높이로 |
| GRASP | **FF 만** | 파지 높이 고정 (z 속도 0 — 벨트를 누르지 않게) |
| LIFT | 0 | LIFT 높이로 상승 |
| VERIFY · stopping · terminal | 0 | 0 |

- 박스 유효 관측이 한 번도 없거나 pose 가 없으면 모든 phase 에서 0.
- FF+P 의 벨트 방향 성분은 0 아래로 내려가지 않는다(기다리기, 0절).
- 사각에서도 새 유효 관측이 오면 예측 기준을 그것으로 바꾼다(U1 `_on_box` 그대로). 실제 관측이므로 쓰되, P 는 꺼져 있어 제어에는 FF·z 목표로만 영향.
- "보인다" = 사각 아님(U1 `is_vision_blind`) + 이 트랙 최신 메시지 valid. "잠깐 안 보임" 동안에도 예측은 마지막 유효 관측 기준으로 계속한다.
- 목표 높이는 **마지막 유효 관측의 박스 윗면 z** 기준: 접근 = 윗면 + `approach_above_top`, 파지 = 윗면 − 19 mm, LIFT = 윗면 + `lift_above_top`.

**전환 플래그 (②에서 계산 → FSM 이 사용)**

| 플래그 | 참 조건 | 쓰는 전이 |
|---|---|---|
| `aligned` | 보임 + 벨트 방향 오차 ≤ `align_tol_along` + 가로 오차 ≤ `align_tol_cross` + 접근 높이 ± `height_tol` + **마지막 유효 관측 나이 ≤ `blind_entry_max_age_s`** | TRACK → DESCEND. 개방 완료 전이면 FSM 이 아직 PREPARE 라 하강 안 함(U1 전이표 그대로) |
| `at_grasp_height` | 보정 TCP z ≤ 파지 높이 + `height_tol` | DESCEND → GRASP |
| `at_lift_height` | 보정 TCP z ≥ LIFT 높이 − `height_tol` | LIFT → VERIFY |
| `reach` | 보정 TCP x < x_min → X_MIN, > x_max → X_MAX | OUT_OF_REACH |

`blind_entry_max_age_s` 를 aligned 에 넣는 이유: DESCEND 에 들어가면 곧 사각이 되고 그 뒤로는 마지막 관측 + FF 로만 간다. 들어가는 순간의 관측이 오래됐으면 사각 구간 내내 그 오차를 안고 간다.

## 4. 데이터 흐름 규칙

1. **단위는 안에서 m·m/s·s 하나.** 파라미터의 mm·ms·cm/s 는 노드가 control 을 부르기 전 한 곳(설정 묶음 만들 때)에서 바꾼다. control.py 안에는 mm 가 없다.
2. **position_base 는 그대로, TCP 만 외삽.** 이중 보정 금지(measurements-1008 #6).
3. **외삽에 쓰는 속도 = 마지막으로 발행한 명령.** 실제 로봇 속도가 아니다 — 가속 중(시작 지연 62 ms, measurements #3)에는 실제보다 앞서 본다. 한계로 적고 U4 에서 "명령 → pose 반영 지연"으로 검증.
4. **예측은 마지막 유효 관측 기준.** invalid 메시지의 좌표는 쓰지 않는다. 새 유효 관측이 오면 그것으로 다시 예측(DEC-03).
5. **끝은 반드시 0.** stopping·terminal 틱, 0 유지 구간(U1), 관측 없음, VERIFY, 예외 → 0. clamp 의 가속 제한은 0 명령에 걸지 않는다.
6. **clamp 는 마지막.** 단계 규칙으로 만든 속도를 마지막에 한 번 자르고, 잘렸는지(`clamped`)를 로그에 남긴다. 속도 상한은 gateway 속도 자르기(100 mm/s)보다 **작게**(같으면 어디서 잘렸는지 구분 불가), 가속 상한은 로봇 speedl 램프(gateway `servo_acc` 100 mm/s²) **이하** — gateway 는 가속을 자르지 않고 로봇에 램프로 넘기므로, 더 크면 로봇이 명령을 못 따라와 외삽(규칙 3)이 더 틀린다(DD 2절).
7. **stamp 나이만으로 멈추지 않는다(MC-031).** 끊김 판정은 U1 `input_flags` 그대로(수신 시각 기준). 큰 Δt 는 예측을 멀리 보낼 뿐이고, 그 경우는 LOST·STALE 이 먼저 끝낸다.
8. **전제: 박스 좌표 출처는 핸드아이(`SOURCE_HAND_EYE`, `moving_verified=true`).** PREPARE 첫 틱부터 TCP 가 관측 자세를 떠나 접근 높이로 움직인다. `OBSERVE_HOMOGRAPHY` 출처는 관측 자세에서 1 mm·0.5° 만 벗어나도 `position_valid=false` 라(calibration.md) 곧 STALE_INPUT 이 된다. 10/08 hand_eye.yaml `moving_verified=true`·box_tracker(#95) 기본 출처 HAND_EYE 로 성립. goal 중 `position_source` 가 바뀌면 경고 로그만 남기고(U2), 예측 리셋 규칙은 U9.

## 5. 선택과 대안

| 선택 | 이유 | 미채택 대안 |
|---|---|---|
| FF + P, Kp 하나(XY) + Kp 하나(Z) | DEC-04. 튜닝 요소가 적다 | 전체 PID: 근거 없음. 축별 Kp: 필요 근거가 생기면 |
| 일정 속도 예측 | DEC-03·12 | 칼만 필터: 실측 근거 없음 |
| P 는 보일 때만 | 사각 직전 오차는 신선하지 않다 | 사각에서도 예측 오차로 P 유지(주관 세션 초안): 새 정보 없이 고정 보정만 됨 |
| 벨트 방향 하한 0 (기다리기) | 상류 돌진·오버슈트·x_min 이탈 방지. Kp 튠이 아니라 구조라 U2 에서 정함 | 부호 제한 없는 P: Kp 에 따라 OUT_OF_REACH |
| 벡터 크기 clamp | 방향 보존 → 추종 궤적이 틀어지지 않음 | 축별 clamp: 방향이 바뀐다 |
| geometry/command 두 입구 | 노드 연결이 두 줄, 테스트는 함수 단위 + 입구 단위 | 노드 안에서 함수 7개 조립: 노드가 판단을 갖게 됨 |
| Z 는 GRASP 에서 속도 0 | 높이 허용치 안에서 멈춤, 벨트·박스를 누르지 않음 | z P 유지: 핑거가 벨트에 닿을 위험 |

## 6. Detail design 에서 정할 것

- 함수 시그니처·반환 모양(dataclass `Geometry`, `Command`), 설정 묶음(`ControlConfig`, mm → m 변환 한 곳).
- dt 의 정의: 실제 틱 간격(지난 계산 시각과의 차) vs 1/rate_hz. 첫 틱·간격 이상(0·음수·너무 큼) 처리.
- Z 속도: `kp_z × 높이 오차` 를 phase 별 상한(접근 이동·`descend_speed`·`lift_speed`)으로 자르는 방식.
- 사각 판정에 원본 pose z 를 쓰는 U1 코드를 보정 TCP z 로 바꿀지 (지금은 원본).
- 새 파라미터 9개 표(이름·단위·제안값·교차 검사: `align_tol_along ≤ align_tol_cross`, `max_speed` < 0.1 m/s 등).
- 로그 키 추가분과 `log_schema` 변경.
- 테스트 목록(지시서 완료 기준 ↔ 테스트 이름 1:1).

## 부록 A. 새 파라미터 (이름 승인됨, 값·교차 검사는 DD)

| 파라미터 | 값 | 쉬운 뜻 |
|---|---|---|
| `input.pose_lag_ms` | **60** (측정값, measurements-1008 #6. gateway pose 방식이 바뀌면 재측정) | pose stamp 가 실제보다 늦은 시간 |
| `input.pose_extrap_max_ms` | null (제안 200, r4) | TCP 외삽을 허용하는 최대 시간. 지평 = 값 나이(0.1 s 갱신 + 메시지 20 ms) + lag 60 → 최대 약 180 ms |
| `input.blind_entry_max_age_s` | null (제안 0.15, 재검 r2 — 근거 DD 7절) | 하강(사각 진입) 직전 마지막 유효 관측 나이 상한 |
| `control.kp_z_per_s` | null | Z 축 P 게인 |
| `control.align_tol_along_mm` | null (제안 3) | 벨트 방향 정렬 허용치 |
| `control.align_tol_cross_mm` | null (제안 5 — 가로 여유 ±24.5 mm 보다 훨씬 좁게) | 가로 정렬 허용치 |
| `z.descend_speed_mps` | null | 하강 속도 상한 |
| `z.lift_speed_mps` | null | 들기 속도 상한 |
| `z.height_tol_mm` | null (제안 2) | "높이에 도달했다" 허용치 |

모든 제안값은 미측정 제안값이다(ADR-0012 승인 수치 목표의 범위 밖). null 이 하나라도 있으면 READY 거부(U1 규칙).

## 7. 변경 기록

| 날짜 | 변경 |
|---|---|
| 10/08 | 초안. 브리핑 승인 결정(0절) 반영 |
| 10/08 | HLD 승인 (박병후). GRASP z 속도 0·aligned 에 관측 나이 조건 포함 확인 |
| 10/09 | r4 PR #122 학민 리뷰 반영(0절 r4 두 줄, DD 0·7.3절) |
| 10/08 | r2 승인(박병후): 아래 r2 + 외삽 상한 초과 시 상한까지 외삽(원본 복귀 아님) |
| 10/08 | r2 독립 재검(Fable 5.1) 반영: 벨트 방향 기다리기(하한 0), PREPARE 안 보임 → FF, 전제(핸드아이 출처) 명시, RG2 개폐 1.2 s 정정, ready_to_blind 삭제, 사각 중 관측 갱신 명시 |
