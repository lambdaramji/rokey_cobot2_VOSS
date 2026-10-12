# U9-a DESCEND LOST 경주 해소 — Pseudo code

[U9a-dd.md](U9a-dd.md)(승인 10/12)의 함수별 의사코드. `fsm.py`·`control.py`·`params.py` 는 ROS·시계·파일을 쓰지 않는다. 시각은 노드 시계 초(float), 높이 설정값 mm, 내부 길이 m. 최종은 코드가 기준이다.

- 상태: **pseudo 승인(박병후, 10/12)** — 재검 r2 반영본, (나) 유지 재확인

## 1. params.py — 상수

```text
BLIND_DWELL_MARGIN_S = 1.0     # 사각 체류 상한 = 예상 하강 시간 + 이 여유 (판단값, U9a-hld D3)
```

## 2. control.py — 사각 체류 상한

```text
from voss_servo import grip                       # descend_time_s 재사용 (grip 은 fsm 만 import → 순환 없음)
from voss_servo.params import BLIND_DWELL_MARGIN_S

함수 descend_blind_max_s(cutoff_m, cfg):
    """DESCEND 에서 사각에 들어간 뒤 파지 높이까지 걸릴 시간의 상한 (s)."""
    거리 = cutoff_m − cfg.grasp_dz                  # 사각 진입 높이 → 파지 높이 (grasp_dz 는 음수라 더해짐)
    예상 = grip.descend_time_s(거리, cfg.descend_speed, cfg.a_max, cfg.kp_z, cfg.height_tol_m)
                                                    # 정지 출발 가정 → 실제(이미 내려가는 중)보다 길다 = 안전 쪽
    반환 예상 + BLIND_DWELL_MARGIN_S
    # 예: cutoff 0.030, grasp −0.019 → 2.439 + 1.0 = 3.44 s
```

## 3. fsm.py — 사각 체류 판정

```text
DESCEND_BLIND_TIMEOUT = "DESCEND_BLIND_TIMEOUT"   # cause (로그용)

TickEvent 에 필드 추가:
    blind_overstay: bool = False                    # DESCEND 사각이 상한을 넘었나 (노드가 채움)

함수 blind_since_next(prev, phase, blind, now):
    """DESCEND 안에서 사각이 시작된 시각을 이어 간다. 아니면 None."""
    만약 phase != DESCEND 또는 blind 가 거짓:
        반환 None                                   # DESCEND 사각이 아니면 지운다 (GRASP·재시도 PREPARE 포함)
    만약 prev 가 None:
        반환 now                                    # 이번 틱에 DESCEND 사각이 시작됐다
    반환 prev                                       # 계속 사각: 처음 시각 유지

함수 blind_overstay(blind_since, now, limit_s):
    """사각 체류가 상한을 넘었나. 같으면 아직 아님."""
    만약 blind_since 가 None 또는 limit_s 가 None:
        반환 거짓                                   # 사각 아님 · 상한 모름(READY 아님 — 방어)
    반환 (now − blind_since) > limit_s
```

`step()` — 9 번 줄(REACH) 바로 뒤에 한 줄:
```text
    ... 6~9 (그대로) ...
    # 9b: 사각에서 로봇이 예상보다 오래 안 내려옴 → 로봇·gateway 이상
    만약 state.phase == DESCEND 이고 ev.blind_overstay:
        반환 _end(state, DEVICE_ERROR, DESCEND_BLIND_TIMEOUT)
    # 10~17: 정상 진행 (그대로)
    반환 _advance(...)
```
- docstring 의 전이표 설명(모듈 머리말 "설계: U1-dd 2절")에 "9b: U9a-dd 2.4" 를 덧붙인다.

## 4. belt_servo.py — 최소 수정 (범위 밖, HLD 승인)

```text
GoalCtx 에 필드 추가:
    blind_since: float | None = None                # DESCEND 에서 사각이 시작된 시각 (노드 시계)

__init__ (self._room_need_s 계산 바로 아래):
    self._blind_max_s = self._blind_dwell_max() if self.ready else None

메서드 _blind_dwell_max():
    """사각 체류 상한 (s). READY 때 한 번 계산하고 기동 로그에 남긴다."""
    cutoff_m = self._p("z.vision_cutoff_above_top_mm") / 1000
    상한 = control.descend_blind_max_s(cutoff_m, self._ctrl)
    INFO "사각 체류 상한: DESCEND 사각 {상한:.2f} s 넘으면 DEVICE_ERROR (하강 예상 {상한 − 여유:.2f} + 여유 {여유:g})"
    반환 상한

_build_event (ctx.blind = blind 바로 다음 줄):
    ctx.blind_since = fsm.blind_since_next(ctx.blind_since, ctx.state.phase, blind, now)

_build_event 의 TickEvent(...) 인자에 추가:
    blind_overstay = fsm.blind_overstay(ctx.blind_since, now, self._blind_max_s)
```
- `ctx.state.phase` 는 이번 틱 전이 **전** phase(이벤트를 먼저 모으고 step 이 뒤에 온다, belt_servo.py:392) — 사각 판정과 같은 기준.

## 5. 설정 파일 (3종)

```text
belt_servo_sim.yaml:   vision_cutoff_above_top_mm: 30.0   # 카메라 실제 이탈 윗면 +27~37 (measurements-1010 '의도 시험', U9a-hld)
belt_servo.yaml / belt_servo_real.yaml.example:
                       vision_cutoff_above_top_mm: null   # 주석만: "제안 30 — (같은 출처). cutoff+5 < approach, height_tol < approach−(cutoff+5)"
3종 lost_timeout_s 주석:        "… 0.5. DESCEND 경주는 cutoff 30 으로 없앰 (U9a-hld)"
3종 blind_entry_max_age_s 주석:  "… 0.15. TRACK→DESCEND 전환에서만 씀 (cutoff 와 무관)"
```

## 6. fake_box.py — 높이로 끊기

```text
SCENARIOS = (기존 4개, "descend_cut", "approach_cut")
CUT_DEFAULT_MM = {"descend_cut": 37.0, "approach_cut": 45.0}   # 회전 박스 실측 최대 +36.7 / 접근 높이 +40 위

FakeBoxConfig 에 필드 추가:
    cut_above_top_m: float                          # 이 높이(윗면 기준) 아래로 TCP 가 오면 끊는다

make_config(..., cut_above_top_mm = None):
    만약 cut_above_top_mm 가 None:
        cut_mm = CUT_DEFAULT_MM.get(scenario, 0.0)  # cut 시나리오가 아니면 쓰이지 않는다
    아니면 cut_mm = float(cut_above_top_mm)
    만약 cut_mm < 0: ValueError("cut_above_top_mm 는 0 이상")
    ... cut_above_top_m = cut_mm / 1000

함수 cut_reached(cfg, box_z, tcp_z):
    """TCP 가 끊는 높이에 닿았나 (cut 시나리오만). pose 를 아직 모르면 거짓."""
    반환 cfg.scenario ∈ CUT_DEFAULT_MM 이고 tcp_z 가 None 아님 이고 tcp_z <= box_z + cfg.cut_above_top_m

samples_at(cfg, t, cut = False):
    ... 기존 분기 ...
    만약 cfg.scenario ∈ CUT_DEFAULT_MM:
        반환 [] (cut 이면) 아니면 [BoxSample(track, p1, 참)]   # 끊기 전에는 normal 과 같다

FakeBoxNode.__init__:
    cut_mm = 파라미터 "cut_above_top_mm" (기본 None, dynamic_typing)
    make_config(..., cut_mm)
    self._tcp_z = None ; self._cut = 거짓
    만약 cut 시나리오:
        구독 PoseStamped "/voss/robot/pose" (best_effort, depth 1) → _on_pose
    시작 로그에 cut 높이(mm) 추가

_on_pose(msg):
    self._tcp_z = msg.pose.position.z

_tick():
    t = 경과
    만약 self._cut 이 거짓 이고 cut_reached(cfg, cfg.start[2], self._tcp_z):   # 박스 높이는 움직여도 그대로 (벨트 z 속도 0)
        self._cut = 참                              # 래치: 다시 발행하지 않는다
        INFO "fake_box: TCP 윗면 +{(tcp_z − box_z)·1000:.1f} mm — 발행 중단 (cut)"
    samples_at(cfg, t, self._cut) 를 발행 (기존과 같음)
```

## 7. sim_check.py

```text
CASES 추가:
    "descend_lost": Case("descend_lost", "descend_cut", 40.5)
    "vanish":       Case("vanish", "approach_cut", 40.5)

EXPECT 추가:
    ("grasp", "descend_lost"): Expect(SUCCEEDED, "OK", "", 참, PHASES)
    ("grasp", "vanish"):       Expect(ABORTED, "LOST", "BOX_MISSING", 거짓, None, "TRACK")

PROFILE_CASES["grasp"] = ("normal", "empty", "cancel", "descend_lost", "vanish")

sim_values(): 반환 사전에 "lost_timeout_s": float(flat["input.lost_timeout_s"]) 추가

CUT_GAP_TICKS = 2           # 마지막 수신이 첫 사각 틱보다 이만큼(틱) 앞서야 "사각 전 끊김"
CUT_MIN_MARGIN_S = 0.2      # 지시서 목표 여유

함수 judge_descend_cut(progress, lost_timeout_s, min_margin_s = CUT_MIN_MARGIN_S):   # 판정 ID J12
    """J-cut: 하강 중 박스가 끊겼는데도 LOST 시계가 여유 있게 사각에 졌다."""
    d = [phase == DESCEND 이고 box_rx_s·t_calc_s 가 있는 틱]
    만약 d 가 비었으면: 반환 UNKNOWN("J-cut", "DESCEND 틱 없음")
    나이(r) = r.t_calc_s − r.box_rx_s
    첫사각 = d 중 vision_blind 가 참인 첫 틱 ; 없으면 반환 UNKNOWN("J-cut", "DESCEND 사각 틱 없음")
    마지막수신 = max(r.box_rx_s for r in d)
    만약 첫사각.t_calc_s − 마지막수신 < CUT_GAP_TICKS × (1/30):
        반환 FAIL("사각 전에 수신이 끊기지 않음 — 시나리오가 경주를 만들지 않았다")
    끊김 = d 중 box_rx_s == 마지막수신 인 **첫** 틱      # 끊긴 순간 (뒤 틱도 같은 box_rx_s 를 계속 갖는다 — 구현 중 버그 수정)
    보임 = [r ∈ d 이고 vision_blind 가 거짓]
    최대나이 = max(나이(r) for r in 보임), 보임이 비면 0
    여유 = lost_timeout_s − 최대나이
    detail = "끊긴 뒤 첫 틱 z {…} · 사각 전 최대 수신 나이 {최대나이:.3f} s · 여유 {여유:.3f} s"
    반환 PASS (여유 ≥ min_margin_s) 아니면 FAIL, detail 포함

judge_case 에 추가:
    만약 case.name == "descend_lost":
        v.append(judge_descend_cut(progress, self.sim["lost_timeout_s"]))
```
- 끊긴 높이를 detail 에 쓰려면 틱의 `tcp_now_m[2] − position_base_m[2]`(mm). 값이 없으면 "—".

## 8. 시험 보조 — test_race.py (새)

```text
상수: TOP = 0.1008, APPROACH = 0.040, GRASP_DZ = −0.019, DT = 1/30, LOST = 0.5
      cfg = 시연 값 ControlConfig (kp_z 1.5, descend 0.05, lift 0.08, acc 0.1, tol 0.002)

함수 descend_track(cutoff_mm):
    """접근 높이에서 DESCEND 시작 → 틱별 (t, tcp_z) 목록 (control.z_speed·clamp 그대로)."""
    z = TOP + 0.0405 ; v = [0.048, 0, 0] ; t = 0 ; 목록 = []   # 현장 DESCEND 시작 +40.4~41.1, xy 는 이미 벨트 FF 로 움직이는 중
                                                             # (v=0 시작이면 +30 통과 0.533 s 로 현장 0.467~0.500 과 1~2틱 어긋남 — 재검 r2)
    반복 (z > TOP + GRASP_DZ + tol 이고 t < 5):
        vz = control.z_speed(TOP + GRASP_DZ, z, kp_z, descend, 0.0)
        v, _ = control.clamp([벨트 0.048, 0, vz], v, v_max, a_max, DT)
        z += v.z × DT ; t += DT ; 목록.append((t, z))
    반환 목록

함수 replay(track, cut_mm, last_rx_above_mm, cutoff_mm):
    """틱마다 is_vision_blind → input_flags. 반환 (LOST 났나, 사각 진입 t, 여유 s)."""
    마지막 수신 시각 = TCP 가 TOP + last_rx_above_mm 를 처음 지나는 t
    blind = 거짓 ; prev_age = 0.0                             # 첫 틱부터 사각이어도 예외 없게
    각 (t, z):
        blind = fsm.is_vision_blind(DESCEND, z, TOP, cutoff_mm, blind)
        rx = min(t, 마지막 수신)                               # 이 틱까지 받은 마지막 메시지 시각
        lost, _, _ = fsm.input_flags(now=t, last_box_rx=rx, last_valid_rx=rx, latest_invalid=거짓,
                                     last_pose_rx=t, goal_start=0, vision_since=0,
                                     blind=blind, lost_timeout=LOST, stale_timeout=0.3)
        만약 lost: 반환 (참, None, None)
        만약 blind: 반환 (거짓, t, LOST − prev_age)
        prev_age = t − rx
    반환 (거짓, None, None)

test_race_cutoff30_no_lost:      replay(+37, cutoff 30) → LOST 거짓, 여유 ≥ 0.2
test_race_cutoff10_lost_regression: replay(+37, cutoff 10) → LOST 참
test_track_matches_field:        descend_track 의 +30 통과 t ∈ [0.43, 0.53] (원본 0.47~0.50 ±1틱)
test_true_vanish_at_approach_lost: TRACK, z = TOP+0.040 고정, 수신 t=0 에서 끊김 → t ≤ 0.5 는 lost 거짓, 0.5 초과 첫 틱에서 참
test_descend_dwell_within_cap:   사각 진입 t → 파지 높이 도달 t 차이(약 2.13) < control.descend_blind_max_s(0.030, cfg)(3.44) — 정상에서 S 가 안 걸림
```

## 9. 그 밖의 pytest (DD 6절 표 그대로)
- test_fsm: blind_since_next 3건 + 재시도 순서 1건 · blind_overstay 경계(같음·±1틱·None) · step 9b 순서 5건 · cutoff 30 TRACK 띠(was_blind 거짓·참) · 재시도 상승 +35 해제
- test_control: descend_blind_max_s 값(30 → 3.44, 10 → 2.78, ±0.01)
- test_params: cutoff 30 통과 · 33 height_tol 실패 · 35 approach 실패
- test_fake_box: cut_reached 경계 · cut 뒤 [] · 기본 높이 · 음수 ValueError
- test_sim_check: judge_descend_cut PASS/FAIL(여유 부족)/FAIL(사각 전 끊김 없음)/UNKNOWN(사각 틱 없음) · grasp 프로필에 새 case 2개
