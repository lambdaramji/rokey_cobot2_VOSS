# U3 기동 launch + fake_box 시뮬 — High-level design

- 이슈: #36 (T27) · 브랜치 `feat/36-voss_servo-u3-sim` · 작성 2026-10-10
- 상태: **HLD 승인(박병후, 10/10)**, r2 독립 재검 반영(10/10, 7절). Detail design: [U3-dd.md](U3-dd.md). 이 문서는 설계 작업 노트이고, 팀 계약은 docs/interfaces 가 우선이다.
- 범위: 1부 = 실기 기동 launch(`belt_servo.launch.py`)·파라미터 정리 함수(`launch_params.py`)·실기 값 예시(`belt_servo_real.yaml.example`). 2부 = 가짜 박스 노드(`fake_box.py`)·시뮬 launch(`sim.launch.py`)·시뮬 값(`belt_servo_sim.yaml`)·자동 판정 도구(`sim_check.py`). 절차서 `U3-run.md`.
- 하지 않는 것: belt_servo.py·params.py·fsm.py·control.py·log_schema.py 수정(U5 병렬), 그리퍼 호출(U5), gateway 수정(학민).
- 근거: DESIGN.md DEC-10(설정)·11(증거)·14(비동기)·16(watchdog), CONTRACT 값 규칙, 사전 실험(아래 2절).

## 0. 브리핑에서 정한 것 (10/09 승인)

| 항목 | 결정 |
|---|---|
| PR | 한 PR, 커밋 둘(launch / sim). launch 를 sim 이 include 해서 실제 연결로 검증한 뒤 리뷰 |
| 지문 | launch 는 `config_version`·`config_sha256`(voss_config 파일 sha256 앞 12자리, gateway 와 같은 형식)만 넘긴다. `params_sha256` 은 노드가 계산 |
| 실값 파일 | 레포 밖 `~/voss_ws/config/belt_servo_real.yaml`. 레포에는 `.example` 만 |
| example | 결정값은 값으로, 미측정만 null + 제안값 주석 |
| 시나리오 | lost·invalid·cancel·normal·two_boxes. U5 전에는 모두 PREPARE 안에서 끝난다 |
| 자동 판정 | `sim_check` 실행 파일. launch_testing 은 쓰지 않는다. phase 는 "표준 순서의 앞부분인가" 로 판정 |

## 1. 처음 보는 개념 다섯 개

**launch 파일** — 노드 여러 개와 그 설정을 한 번에 띄우는 "기동 대본"이다. `ros2 run` 은 노드 하나를 손으로 띄우는 것이고, `ros2 launch` 는 대본을 읽고 정해진 노드를 정해진 값으로 띄운다. 대본 안에서 파이썬 함수를 불러 값을 계산할 수도 있다(이번 1부가 그렇게 한다). 다른 launch 파일을 그대로 끌어다 쓰는 것을 **include** 라고 한다.

```
ros2 launch voss_servo sim.launch.py scenario:=lost
   └─ sim.launch.py ─┬─ fake_box 노드
                     ├─ include robot_gateway.launch.py (학민 것 그대로)
                     └─ include belt_servo.launch.py   (1부에서 만든 것)
```

**파라미터 파일(YAML)** — 노드에 넘길 값을 적은 표다. ROS 는 `노드이름: ros__parameters:` 아래 값을 읽는다. 중첩된 키는 점으로 이어 하나의 이름이 된다 (`grasp:` 아래 `tcp_z_below_top_mm` → `grasp.tcp_z_below_top_mm`). YAML 의 `null` 은 "아직 모름" 이지만, `--params-file` 로 넘기면 문자열 `"null"` 이 되어 버린다 → 1부의 정리 함수가 null 을 **넘기지 않도록 지워서** 노드가 "값 없음 = READY 거부" 로 정확히 판단하게 한다.

**sha256 지문** — 파일이나 값 묶음을 넣으면 나오는 64자리 "지문". 한 글자만 달라도 완전히 다른 지문이 나온다. 로그에 지문을 찍어 두면 "그날 어떤 설정으로 돌렸나" 를 나중에 정확히 맞춰 볼 수 있다. 여기에는 두 개가 있다.
- `config_sha256` — voss_config.yaml **파일**의 지문(앞 12자리). launch 가 계산해 넘긴다. gateway 도 같은 방식이라 두 로그를 나란히 대조할 수 있다.
- `params_sha256` — belt_servo 가 **받은 값 묶음**의 지문. 노드가 직접 계산한다(params.py). 그래서 launch 는 이것을 넘기지 않는다.

**액션 클라이언트** — 액션 서버(belt_servo)에 "이 트랙을 잡아" 라고 goal 을 보내고, 진행 소식(feedback: phase)과 최종 결과(result: reason)를 받는 쪽. 실제 시스템에서는 sort_manager 가 클라이언트다. sim_check 는 sort_manager 대신 클라이언트 역할을 하고, 끝난 뒤 로그를 채점한다. "취소(cancel)" 도 클라이언트가 보낸다.

**시나리오 노드(fake_box)** — 카메라·box_tracker 대신 `/voss/vision/box` 를 30 Hz 로 보내는 가짜 노드. 박스 하나를 벨트 속도로 움직이면서, 시나리오에 따라 "몇 초 뒤 invalid 로 바꾸기", "몇 초 뒤 보내기 멈추기", "다른 박스 하나 더 보내기" 를 한다. 로봇 쪽 가짜는 이미 있는 gateway `dry_run` 이 맡는다(가짜 로봇이 speedl 을 적분해 pose 를 내고, 가짜 RG2 가 응답).

## 2. 사전 실험 결과 (10/09 23:50~, main 309af67, 레포 수정 없음)

gateway dry_run(launch) + belt_servo(`--params-file`, 제안값·kp 1.0·접근 높이 40 mm) + scratch 박스 발행기(x −0.100, y −0.271, z 0.1008, 48 mm/s) + scratch 액션 클라이언트.

| 시나리오 | 결과 | 시각 |
|---|---|---|
| normal | ABORTED / OUT_OF_REACH (`REACH_X_MAX`), feedback [PREPARE] | goal 뒤 13.0 s, TCP x 621.3 mm |
| 박스 끊김 | ABORTED / LOST (`BOX_MISSING`) | 끊긴 뒤 ≈0.5 s |
| invalid 지속 (gateway 새로 띄움) | ABORTED / STALE_INPUT (`BOX_INVALID`) | 첫 invalid 틱 뒤 0.27 s |
| cancel | CANCELED (`STOP_OK`) | cancel 뒤 0.08 s |

공통: PREPARE 에서 FF+P 로 따라감(z 203.6 → 140.8 mm, 오차 → 0, 벨트 방향 48 mm/s) · 종료 틱 0 + `cause == "ZERO_HOLD"` 틱 15개(0.5 s) 모두 0 · 틱 Δt 평균 33.3 ms(28.2~38.3) · gateway watchdog 종료 0.71 s 뒤 1회 · cancel 은 move_stop 2회(stop + watchdog).

설계를 바꾼 발견:
1. **dry_run 가짜 로봇은 goal 뒤 제자리에 남는다.** 같은 gateway 로 이어 돌린 invalid 는 x 618 mm 에서 시작해 FF 로 0.17 s 만에 620 을 넘어 OUT_OF_REACH 로 끝났다 → **시나리오마다 sim 전체를 새로 띄운다**(4절 B).
2. **같은 값이라도 `90` 과 `90.0` 이면 params_sha256 이 다르다**(2f6b… vs 9fa3…). voss_config 에는 `pre_open_mm: 90` 처럼 정수가 있다 → launch 가 **params.py 의 PARAM_SPECS 종류(float 등)대로 형을 맞춘다**(params.py 는 읽기만).
3. gateway 쪽 사실(watchdog·move_stop·stop)은 **gateway 출력 텍스트에만** 있다 → sim_check 는 gateway 출력을 파일로 받아 읽는다.

## 3. 모듈 구성

### 3.1 그림

```
[1부: 실기 경로 — 공용 PC, 사람이 비상정지 옆에서]
  ~/voss_ws/config/belt_servo_real.yaml ─┐
  (overrides.yaml, 선택) ────────────────┤  launch_params.build_params()
  ~/voss_ws/config/voss_config.yaml ─────┤   ① 읽기·평탄화 ② null 지우기 ③ 덮어쓰기
  log_dir:=<레포>/data/servo ────────────┘   ④ voss_config 키·지문 ⑤ 형 맞추기 ⑥ 검사
                                                     │ dict
                                       belt_servo.launch.py ─▶ belt_servo 노드 ─▶ "READY" / "READY 거부: missing=[…]"

[2부: sim 경로 — 개인 PC, Claude 가 voss-ros 로]
  sim_check --case lost
     ├─(0) 사전 점검: ROS_DOMAIN_ID ≠ 30, 그래프에 robot_gateway·belt_servo·fake_box 가 이미 떠 있지 않음 (아니면 종료 2)
     ├─(1) 자식 프로세스로 `ros2 launch voss_servo sim.launch.py scenario:=lost …` 기동, 출력 → run 폴더/launch.log
     │        sim.launch.py ─┬─ fake_box (scenario, 시작 위치, 벨트 속도 ← voss_config)
     │                       ├─ include robot_gateway.launch.py (dry_run:=true, dry_run_object_mm, config:=레포 config)
     │                       └─ include belt_servo.launch.py (params:=belt_servo_sim.yaml, overrides:=kp, log_dir:=run 폴더)
     ├─(2) 액션 서버 대기 → goal 전송 → feedback·result 수집 (cancel 시나리오는 N 초 뒤 cancel)
     ├─(3) zero_hold·watchdog 이 끝날 만큼 기다린 뒤 launch 프로세스에 SIGINT(launch 가 자식에 전파) → 종료 대기
     ├─(4) 판정: result·feedback · 틱 로그(JSONL) · launch.log 의 gateway 줄
     └─(5) 표 출력 + 종료 코드 (0 = 전부 통과, 1 = 하나라도 불일치, 2 = 판정 불가)
```

### 3.2 책임 나눔

| 파일 | 하는 일 | 하지 않는 일 | ROS 의존 |
|---|---|---|---|
| `voss_servo/launch_params.py` | YAML 읽기·평탄화·null 제거·덮어쓰기·voss_config 키 추출·파일 지문·형 맞추기·이상한 키 경고 | 값의 의미 검사(그건 노드의 params.py) | 없음 (순수, pytest) |
| `launch/belt_servo.launch.py` | 인자 받기 → `build_params()` → belt_servo 노드 1개 | 계산 로직 (전부 launch_params 로) | launch·launch_ros |
| `config/belt_servo_real.yaml.example` | 실기 값 파일의 틀 (결정값 + null) | 실제 값 보관 (레포 밖) | — |
| `voss_servo/fake_box.py` | 시나리오 계산(순수 함수) + 30 Hz 발행 노드 | 판정, 로봇·액션 | 노드 부분만 rclpy |
| `config/belt_servo_sim.yaml` | sim 전용 제안값 (머리 주석 "실기 금지") | — | — |
| `launch/sim.launch.py` | fake_box + gateway include + belt_servo include, 인자 전달 | 판정 | launch·launch_ros |
| `voss_servo/sim_check.py` | sim 기동·종료, 액션 클라이언트, 로그 수집, 판정(순수 함수), 표 출력 | 노드 로직 수정·재시도 | 실행 부분만 rclpy |
| `design/U3-run.md` | (A) 공용 PC 실기 기동 절차 (B) 개인 PC sim 절차 | 로봇을 움직이는 명령 | — |

판정 함수(`judge_*`)·시나리오 함수(`box_at` 등)·정리 함수(`build_params` 등)는 모두 ROS 없이 돌아가는 순수 함수로 두고 pytest 로 확인한다. ROS 가 필요한 부분(노드·launch·액션)은 얇게.

## 4. 데이터 흐름 규칙

### A. 파라미터 합치기 (1부, 위에서 아래로 덮어씀)

| 순서 | 출처 | 규칙 |
|---|---|---|
| 1 | `params` YAML (`belt_servo: ros__parameters:` 아래) | 평탄화 → null·`"null"`·`"~"`·빈 배열 지움 |
| 2 | `overrides` YAML (선택, 같은 모양) | 같은 규칙으로 정리 → 같은 키를 덮어씀 |
| 3 | `log_dir` 인자 (선택) | 있으면 `log.dir` 을 덮어씀. 경로는 `~` 를 펼쳐 절대 경로로 |
| 4 | voss_config.yaml | `belt.speed_cmps`·`belt.direction_base`·`gripper.pre_open_mm`·`grasp_width_mm`·`force_n`·`timing.latency_offset_ms` + `version` → `config_version` + 파일 sha256 앞 12자리 → `config_sha256` |
| 5 | 형 맞추기 | PARAM_SPECS 종류대로: float → float(90 → 90.0), float3 → float 3개 목록, int → int |

- **voss_config 키(4번)는 voss_config 에서만** 온다. params·overrides 에 `belt.*`·`gripper.*`·`timing.*`·`config_*` 가 있으면 launch 를 **오류로 멈춘다** (CLAUDE.md 규칙 5 — 같은 값이 두 곳에 있으면 어느 쪽이 쓰였는지 모른다).
- PARAM_SPECS 에 없는 키(오타 등)는 **경고 로그**를 남기고 넘긴다(노드가 선언하지 않으니 무시된다). U5 가 새 키를 PARAM_SPECS 에 넣으면 자동으로 정상 키가 된다.
- 파일이 없거나 YAML 이 깨졌으면 launch 를 **오류로 멈춘다**(노드가 반쯤 뜨는 것보다 낫다). 값이 비어서 READY 거부되는 것은 노드의 일이다.
- 경로 인자는 모두 `~` 를 펼친다 (`params:=~/…` 는 셸이 펼치지 않는다).

### B. sim 실행 (2부)

- **한 시나리오 = sim 한 번 기동.** 가짜 로봇 위치·gateway 통계·belt_servo 틱 로그가 시나리오끼리 섞이지 않는다(2절 발견 1).
- run 폴더 하나에 그 시나리오의 전부를 모은다: `launch.log`(모든 노드 출력), `ticks/`·`attempts/`(belt_servo 로그), `result.json`(sim_check 가 받은 result·feedback·시각), `verdict.txt`(판정 표).
- fake_box 의 시각은 **fake_box 시작 기준**이다. sim_check 는 goal 을 "액션 서버가 생기고 **이번 case 시작 뒤 stamp 의** 박스 메시지가 오기 시작한 뒤" 보낸다. invalid·lost 시각을 goal 보다 넉넉히 뒤(기본 **8 s** — 콜드 스타트가 길어져도 lost case 의 첫 박스를 놓치지 않게, r2)로 두면 goal 이 조금 늦어도 결과가 같다(lost·invalid 판정은 goal 시작부터 다시 센다 — fsm.py `vision_since`, belt_servo.py:291).
- 시간 판정은 모두 **ROS 시계(벽시계) 값끼리** 비교한다: 틱 로그 `t_pub_s` 와 gateway 로그 `[1791557437.56]` 는 같은 시계다.

### C. 판정 항목 (기대값은 DD 의 표로 확정)

| 항목 | 근거 데이터 | 규칙 (요지) |
|---|---|---|
| result | 액션 result | 시나리오별 기대 reason·grasped·status |
| phase | feedback 목록 | PREPARE→TRACK→DESCEND→GRASP→LIFT→VERIFY 의 앞부분 |
| 마지막 0 | 틱 로그 | 종료 틱(terminal) cmd 0 + 그 뒤 ZERO_HOLD 틱이 zero_hold_s 동안 전부 0 |
| 주기 | 틱 로그 `t_pub_s` | Δt 평균 33 ms ±3 |
| 추종 | 틱 로그 (normal) | 보일 때 cmd ≠ 0 · 벨트 방향 성분 ≥ 0 · tcp·predicted·error 채워짐 |
| 트랙 고정 | 틱 로그 (two_boxes) | `position_base` 가 goal 트랙 궤적과 맞음 (다른 트랙 값이 섞이지 않음) |
| watchdog | launch.log gateway 줄 | 종료 뒤 0.7 s 근처에 watchdog 1회. move_stop 합계 = 1 (cancel 은 2). 집계는 [종료 틱, SIGINT 보낸 시각) 창 안만 (종료 처리 중 생기는 줄 제외, r2) |

## 5. 선택과 대안

| 결정 | 고른 것 | 대안과 버린 이유 |
|---|---|---|
| 계산 위치 | launch 는 얇게, 계산은 `launch_params.py` 순수 함수 | launch 안에 직접 쓰기 — pytest 로 확인하기 어렵다 |
| 형 맞추기 근거 | `voss_servo.params.PARAM_SPECS` 를 import 해서 사용 (읽기만) | 키 목록 복사 — U5 가 키를 더할 때 두 곳을 고쳐야 한다 |
| 시나리오 사이 초기화 | sim 전체 재기동 | gateway MoveToZone 으로 관측 자세 복귀 — 로봇·gateway 상태(통계·STOPPED)가 남고, 시나리오가 gateway 동작에 묶인다 |
| sim 기동 주체 | sim_check 가 `ros2 launch` 를 자식 프로세스로 띄우고 끈다. **`--no-launch` 는 두지 않는다**(r2) | 사람이 launch 를 따로 띄우고 sim_check 는 클라이언트만 — 시나리오마다 두 명령·두 터미널, gateway 출력 파일 경로를 따로 맞춰야 해서 실수 여지가 크고, 이미 떠 있는 gateway 가 dry_run 인지 보장할 수 없다(공용 PC 에서 실기 gateway 에 goal 이 갈 위험). 단계별로 보고 싶을 때는 U3-run.md (B) 의 수동 절차(launch + `ros2 action send_goal`)를 쓴다 |
| gateway 사실 수집 | launch 출력 텍스트를 정규식으로 읽음 (패턴은 한 곳에 상수로) | `/voss/robot/state` 구독 — move_stop 횟수·watchdog 은 상태에 안 나온다. gateway 문구가 바뀌면 깨지므로 패턴을 못 찾으면 "판정 불가(2)" 로 드러낸다 |
| U5 전후 기대값 | `--profile` 인자: `pre_u5`(기본, 지금 main) / `grasp`(U5 뒤: normal → OK·grasped, object 0 → GRASP_FAILED) | phase 를 보고 자동 선택 — U5 가 고장 나 PREPARE 에 머물면 pre_u5 기대로 통과해 버려 고장을 숨긴다 |
| sim 의 kp | sim yaml 에 kp 1.0 (사전 실험 값, "sim 전용 제안값") + `kp:=` 인자로 덮어씀 | kp 0(FF 만) — PREPARE 에서 박스로 다가가지 않아 U5 뒤 TRACK→DESCEND 정렬이 성립하지 않는다 |
| fake_box 시나리오 제어 | 시작 파라미터로만 (실행 중 바꾸지 않음) | 실행 중 서비스로 바꾸기 — `/voss/` 아래 새 서비스는 인터페이스 변경(규칙 2) |

## 6. Detail design 에서 정할 것

1. `launch_params.py` 함수 목록·입출력·오류 종류(예외 이름·메시지), 경고 형식.
2. launch 인자 표(이름·기본값·필수 여부), 노드 옵션(name·output·emulate_tty).
3. example·sim yaml 의 키별 값 표 (결정값/null/제안값과 출처). 세 YAML(belt_servo.yaml·example·sim)의 **키 집합이 같은지** 검사하는 테스트.
4. fake_box 파라미터 표·시나리오별 동작 표(two_boxes 의 두 번째 박스 위치 포함), 발행 QoS.
5. sim_check 인자, run 폴더 구조, 시나리오별 기대값 표(profile 2개), 판정 함수 목록과 허용치, gateway 로그 패턴, 대기 시간(goal 상한·zero_hold 뒤 대기), 종료 코드.
6. 테스트 목록 (L1: launch_params ≥ 8, fake_box ≥ 6, sim_check ≥ 8).
7. package.xml exec_depend·setup.py entry_points·data_files.

## 7. 변경 기록
- 2026-10-10 r1: 초안 (사전 실험 반영). 승인.
- 2026-10-10 r2: 독립 재검 반영 — sim_check 사전 점검(도메인 30·중복 노드 거부), `--no-launch` 삭제, fake_box 시각 기본 8 s·case 시작 뒤 stamp 만 인정, SIGINT 는 launch 프로세스에만, gateway 집계 창 제한.
