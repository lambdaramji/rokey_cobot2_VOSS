# U3 기동 launch + fake_box 시뮬 — Pseudo code

[U3-dd.md](U3-dd.md)(승인 10/10)의 함수별 의사코드. 순수 함수(launch_params·fake_box 계산·sim_check 판정)는 ROS·시계·파일 쓰기를 하지 않는다(파일 읽기는 load_yaml·file_sha 만). 최종은 코드가 기준이다.

- 상태: **pseudo 승인(박병후, 10/10)** — r2 독립 재검 반영(8절)

## 1. launch_params.py

```text
import: hashlib, os, dataclass, yaml
from voss_servo.params import PARAM_SPECS, NULL_STRINGS       # 읽기만 (수정 금지 파일)

NODE_NAME = "belt_servo"
CONFIG_PREFIXES = ("belt", "gripper", "timing")
CONFIG_META_KEYS = ("config_version", "config_sha256")
SPEC_KIND = {spec.name: spec.kind for spec in PARAM_SPECS}            # 이름 → 종류
CONFIG_KEYS = (이름 for 이름 in SPEC_KIND if 이름.split(".")[0] in CONFIG_PREFIXES)   # 지금 6개
SHA_LEN = 12

클래스 LaunchParamsError(ValueError)

dataclass(frozen) BuildResult: params, dropped, warnings, config_sha, sources

함수 expand(path):
    반환 os.path.abspath(os.path.expanduser(str(path)))      # "~/x" → "/home/rokey/x"

함수 load_yaml(path):
    p = expand(path)
    파일이 없으면 → LaunchParamsError(f"파일 없음: {p} — 경로 확인")
    시도: doc = yaml.safe_load(파일 내용)
    YAML 오류면 → LaunchParamsError(f"YAML 오류: {p} — {오류 첫 줄}")
    doc 가 None 이면 doc = {}                                  # 빈 파일
    doc 가 dict 가 아니면 → LaunchParamsError(f"최상위가 표(dict)가 아님: {p}")
    반환 doc

함수 node_section(doc, node=NODE_NAME, where=""):
    sec = doc.get(node, {}).get("ros__parameters")             # 중간이 dict 아닐 때도 안전하게
    sec 가 dict 가 아니면 → LaunchParamsError(f"'{node}: ros__parameters:' 없음: {where}")
    반환 sec

함수 flatten(d, prefix=""):
    out = {}
    d 의 (키, 값) 마다:
        이름 = prefix + "." + 키  (prefix 가 비면 키)
        값이 dict 이면 out 에 flatten(값, 이름) 합침            # 더 들어간다
        아니면 out[이름] = 값                                    # 목록·숫자·문자열은 잎
    반환 out

함수 is_unset(v):
    v is None → 참
    v 가 문자열이고 strip() in NULL_STRINGS → 참               # "null", " null ", "~" (대소문자 구분 — 노드 params._is_null_string 과 같게)
    v 가 목록이고 비어 있음 → 참
    그 밖(0, False, "" 포함) → 거짓                             # 그 값의 옳고 그름은 노드가 판단

함수 drop_unset(flat):
    kept = {k: v for k, v in flat if not is_unset(v)}
    dropped = sorted(k for k, v in flat if is_unset(v))
    반환 kept, dropped

함수 forbidden_keys(flat):
    반환 sorted(k for k in flat if k.split(".")[0] in CONFIG_PREFIXES or k in CONFIG_META_KEYS)

함수 unknown_keys(flat):
    반환 sorted(k for k in flat if k not in SPEC_KIND)

함수 _is_num(v):  v 가 int 또는 float 이고 bool 이 아님           # True 는 숫자로 치지 않는다

함수 normalize(flat):
    out = dict(flat)
    out 의 (k, v) 마다:
        kind = SPEC_KIND.get(k)
        kind == "float" 이고 _is_num(v)             → out[k] = float(v)          # 90 → 90.0
        kind == "float3" 이고 v 가 목록·튜플이고 전부 _is_num → out[k] = [float(x) for x in v]
        kind == "int" 이고 v 가 float 이고 v.is_integer() → out[k] = int(v)      # 1.0 → 1
        그 밖은 그대로                                  # 틀린 형은 노드가 READY 거부
    반환 out

함수 file_sha(path):
    p = expand(path); 없으면 → LaunchParamsError(f"파일 없음: {p}")
    반환 hashlib.sha256(파일 바이트).hexdigest()[:SHA_LEN]      # gateway config_params.load_config 와 같음

함수 config_values(cfg_doc, sha):
    flat = flatten(cfg_doc)
    out = {k: flat[k] for k in CONFIG_KEYS if k in flat and not is_unset(flat[k])}
    cfg_doc 에 "version" 이 있고 비어 있지 않으면 out["config_version"] = cfg_doc["version"]
    out["config_sha256"] = sha
    반환 out

함수 _section_from(path, label):
    doc = load_yaml(path)
    flat = flatten(node_section(doc, NODE_NAME, expand(path)))
    반환 drop_unset(flat)                                       # (kept, dropped)

함수 build_params(params_path, config_path, overrides_path=None, log_dir=None):
    빈 문자열 params_path → LaunchParamsError("params 인자가 비었다 — params:=<yaml 경로>")
    warnings = []
    values, dropped = _section_from(params_path, "params")                         # ①
    overrides_path 가 있으면:                                                       # ②
        ov, ov_dropped = _section_from(overrides_path, "overrides")
        values.update(ov)
        dropped = sorted((set(dropped) | set(ov_dropped)) − set(ov))                # 값을 준 키는 dropped 아님
    bad = forbidden_keys(values)                                                    # ③
    bad 가 있으면 → LaunchParamsError(f"params/overrides 에 voss_config 키가 있다(규칙 5): {bad} — 지우기")
    log_dir 이 있으면 values["log.dir"] = expand(log_dir)                           # ④
    아니면 values 의 log.dir 이 상대 경로면 warnings += "log.dir 상대 경로 — 실행 위치 기준: <값>"
    sha = file_sha(config_path)                                                     # ⑤
    values.update(config_values(load_yaml(config_path), sha))
    values = normalize(values)                                                      # ⑥
    unk = unknown_keys(values)                                                      # ⑦
    unk 가 있으면 warnings += f"PARAM_SPECS 에 없는 키(노드가 무시): {unk}"
    sources = {"params": expand(params_path), "overrides": expand(overrides_path) 또는 "-", "config": expand(config_path)}
    반환 BuildResult(values, dropped, warnings, sha, sources)

함수 summary_line(result):                                     # launch 가 찍는 한 줄
    반환 f"belt_servo launch: params={…} overrides={…} config={…} config_sha256={sha} "
         f"넘김 {len(params)}개, null 로 뺀 키 {len(dropped)}개 {dropped}"
```

## 2. launch/belt_servo.launch.py

```text
함수 _setup(context):
    인자 4개를 문자열로 읽는다 (LaunchConfiguration(...).perform(context))
    result = build_params(params, config, overrides 또는 None, log_dir 또는 None)   # 오류면 그대로 올라가 launch 가 멈춤
    actions = [LogInfo(msg=summary_line(result))]
    result.warnings 마다 actions += LogInfo(msg="경고: " + w)
    actions += Node(package="voss_servo", executable="belt_servo", name="belt_servo",
                    output="screen", parameters=[result.params])          # emulate_tty 없음 (색 코드 방지)
    반환 actions

함수 generate_launch_description():
    반환 LaunchDescription([
        DeclareLaunchArgument("params", default_value="", description="belt_servo 파라미터 YAML (필수)"),
        DeclareLaunchArgument("config", default_value="~/voss_ws/config/voss_config.yaml"),
        DeclareLaunchArgument("overrides", default_value=""),
        DeclareLaunchArgument("log_dir", default_value=""),
        OpaqueFunction(function=_setup)])
```

## 3. fake_box.py

```text
SCENARIOS = ("normal", "invalid_after_s", "lost_after_s", "two_boxes")

dataclass(frozen) BoxSample: track_id, xyz(튜플 3), valid
dataclass(frozen) FakeBoxConfig: scenario, track_id, start(3), vel(3, m/s), invalid_after_s, lost_after_s,
                                 second_track_id, second_offset(3)

함수 belt_velocity(speed_cmps, direction):
    d = np.asarray(direction, float); n = ‖d‖
    n ≤ 1e-9 이면 → ValueError("direction_base 길이 0")
    반환 speed_cmps / 100 × d / n                             # cm/s → m/s, 방향만 사용

함수 position_at(start, vel, t):
    반환 start + vel × t

함수 make_config(scenario, track_id, start, speed_cmps, direction, invalid_after_s, lost_after_s,
                 second_track_id, second_offset):
    scenario not in SCENARIOS → ValueError(f"모르는 scenario: {scenario}")
    반환 FakeBoxConfig(…, vel=belt_velocity(speed_cmps, direction), …)

함수 samples_at(cfg, t):
    p1 = position_at(cfg.start, cfg.vel, t)
    cfg.scenario 별:
        "normal"          → [BoxSample(cfg.track_id, p1, True)]
        "invalid_after_s" → [BoxSample(cfg.track_id, p1, t < cfg.invalid_after_s)]   # 위치는 계속 움직인다
        "lost_after_s"    → t < cfg.lost_after_s 이면 [BoxSample(cfg.track_id, p1, True)] 아니면 []
        "two_boxes"       → [BoxSample(cfg.track_id, p1, True),
                             BoxSample(cfg.second_track_id, p1 + cfg.second_offset, True)]

클래스 FakeBoxNode(Node "fake_box"):
    __init__:
        파라미터 선언: scenario="normal", track_id=1, start_xyz_m=[-0.100,-0.271,0.1008],
                       speed_cmps(기본 없음, dynamic_typing), direction_base(기본 없음, dynamic_typing),
                       rate_hz=30.0, invalid_after_s=8.0, lost_after_s=8.0,
                       second_track_id=2, second_offset_m=[0.060,0.040,0.0]
        speed_cmps 또는 direction_base 가 None 이면 → ValueError("speed_cmps·direction_base 필수 (sim.launch 가 voss_config 에서 넘김)")
        self.cfg = make_config(...)                            # 틀리면 ValueError
        self.pub = create_publisher(BoxTrack, "/voss/vision/box", QoS best_effort·volatile·keep_last 1)
        self.t0 = time.monotonic()
        create_timer(1 / rate_hz, self._tick)
        로그: f"fake_box: scenario={…} start={mm} vel={mm/s} invalid_after={…} lost_after={…}"
    _tick:
        t = time.monotonic() − self.t0
        samples_at(self.cfg, t) 마다:
            msg = BoxTrack(); msg.track_id = s.track_id
            msg.stamp = 지금 ROS 시각                            # 촬영 시각 역할
            msg.position_base = Point(*s.xyz); msg.position_valid = s.valid
            msg.position_source = BoxTrack.SOURCE_HAND_EYE; msg.calib_version = "fake"   # u·v·bbox 는 기본 0
            self.pub.publish(msg)

함수 main():
    rclpy.init()
    시도: node = FakeBoxNode()
    ValueError 면: ERROR 로그(rclpy 로거 "fake_box") → rclpy.shutdown() → sys.exit(1)
    시도: rclpy.spin(node)
    KeyboardInterrupt·ExternalShutdownException 은 조용히 → node.destroy_node() → rclpy.try_shutdown()
```

## 4. launch/sim.launch.py

```text
함수 _setup(context):
    인자 읽기: config, scenario, object_mm, kp, log_dir, invalid_after_s, lost_after_s
    config 가 비면 → RuntimeError("sim.launch 는 config:=<레포>/config/voss_config.yaml 필수")
    cfg = config_values(load_yaml(config), file_sha(config))          # belt 값 (launch_params 재사용)
    servo_share = get_package_share_directory("voss_servo")
    robot_share = get_package_share_directory("voss_robot")
    overrides = ""
    kp 가 있으면:
        폴더 = expand(log_dir) 또는 tempfile.mkdtemp(prefix="voss_sim_")
        폴더 만들기; overrides = 폴더/sim_overrides.yaml
        파일 쓰기: {"belt_servo": {"ros__parameters": {"control": {"kp_per_s": float(kp)}}}}
    fake = Node(package="voss_servo", executable="fake_box", name="fake_box", output="screen",
                parameters=[{"scenario": scenario, "speed_cmps": float(cfg["belt.speed_cmps"]),
                             "direction_base": [float(x) for x in cfg["belt.direction_base"]],
                             "invalid_after_s": float(…), "lost_after_s": float(…)}])
    # Jazzy: launch_arguments 는 (이름, 값) 쌍 목록 → dict 면 .items() (dict 그대로면 키만 남아 깨진다)
    gateway = IncludeLaunchDescription(PythonLaunchDescriptionSource(robot_share/launch/robot_gateway.launch.py),
                launch_arguments={"dry_run": "true",                  # 항상 고정 — 인자로 받지 않는다
                                  "dry_run_object_mm": object_mm, "config": config}.items())
    servo = IncludeLaunchDescription(PythonLaunchDescriptionSource(servo_share/launch/belt_servo.launch.py),
                launch_arguments={"params": servo_share/config/belt_servo_sim.yaml, "config": config,
                                  "overrides": overrides, "log_dir": log_dir}.items())
    반환 [LogInfo("sim.launch: scenario=… object_mm=… kp=… (dry_run 고정)"), fake, gateway, servo]

generate_launch_description: DeclareLaunchArgument 7개(config "", scenario "normal", object_mm "40.5",
                             kp "", log_dir "", invalid_after_s "8.0", lost_after_s "8.0") + OpaqueFunction(_setup)
```

## 5. sim_check.py — 표·상수

```text
STATUS = {SUCCEEDED: 4, CANCELED: 5, ABORTED: 6}            # action_msgs/GoalStatus
PHASES = ("PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY")

dataclass Case: name, scenario, object_mm, cancel_after(None|초)
CASES = {lost: (lost_after_s, 40.5, None), invalid: (invalid_after_s, 40.5, None), cancel: (normal, 40.5, 3.0),
         normal: (normal, 40.5, None), two_boxes: (two_boxes, 40.5, None), empty: (normal, 0.0, None)}

dataclass Expect: status, reason, cause, grasped, phases_exact(목록|None), phases_prefix_last(문자열|None)
EXPECT = {
  ("pre_u5","lost"):      Expect(6, "LOST", "BOX_MISSING", False, ["PREPARE"], None),
  ("pre_u5","invalid"):   Expect(6, "STALE_INPUT", "BOX_INVALID", False, ["PREPARE"], None),
  ("pre_u5","cancel"):    Expect(5, "CANCELED", "STOP_OK", False, ["PREPARE"], None),
  ("pre_u5","normal"):    Expect(6, "OUT_OF_REACH", "REACH_X_MAX", False, ["PREPARE"], None),
  ("pre_u5","two_boxes"): Expect(6, "OUT_OF_REACH", "REACH_X_MAX", False, ["PREPARE"], None),
  ("grasp","normal"):     Expect(4, "OK", "", True, list(PHASES), None),
  ("grasp","empty"):      Expect(6, "GRASP_FAILED", "NOT_DETECTED", False, None, "GRASP"),
  ("grasp","cancel"):     Expect(5, "CANCELED", "STOP_OK", False, None, None) }       # 접두사면 무엇이든
PROFILE_CASES = {"pre_u5": [lost, invalid, cancel, normal, two_boxes], "grasp": [normal, empty, cancel]}

허용치: PERIOD_NOMINAL_MS = 1000/30, PERIOD_TOL_MS = 3, WATCHDOG_DELAY_S = (0.6, 0.9),
        TRACK_LOCK_TOL_M = 0.005, FOLLOW_MIN_TICKS = 30, ZERO_EPS = 1e-9
대기: DISCOVERY_S = 2, GW_START_S = 15, SERVER_S = 20, FIRST_BOX_S = 5, SETTLE_S = 8, STOP_S = 15
사전 점검: REAL_DOMAIN = "30", SIM_NODES = ("robot_gateway", "belt_servo", "fake_box")
패턴 (DD 6.8): GW_STARTED = r"robot_gateway started: (\S+)"   # 첫 단어: "dry_run" | "real" (robot_gateway.py:239) → "dry_run" 이어야 한다
               GW_WATCHDOG, GW_STOP, GW_STATS, TS = r"\[(\d+\.\d+)\] \[robot_gateway\]"

dataclass Verdict: id, item, expected(문자열), actual(문자열), status ∈ PASS·FAIL·UNKNOWN
함수 _v(id, item, ok, exp, act):  반환 Verdict(id, item, exp, act, "PASS" if ok else "FAIL")
```

## 6. sim_check.py — 순수 판정 함수

```text
함수 select_goal_rows(rows, goal_id):  반환 [r for r in rows if r.get("goal_id") == goal_id]

함수 split_goal_ticks(ticks):                            # ticks = kind "tick" 인 goal 행, 시각 순
    i = 첫 terminal==true 인 위치 (없으면 None)
    진행 = ticks[:i], 종료 = ticks[i], hold = [r for r in ticks[i+1:] if r.get("cause") == "ZERO_HOLD"]
    반환 (진행, 종료, hold)   # 종료가 없으면 (ticks, None, [])

함수 norm(v):  반환 √(Σ x²)  (v 가 None 이면 None)

함수 judge_result(exp, status, reason, grasped):
    ok = status == exp.status and reason == exp.reason and grasped == exp.grasped
    반환 _v("J1", "result", ok, f"{exp.status}/{exp.reason}/grasped={exp.grasped}", f"{status}/{reason}/grasped={grasped}")

함수 judge_cause(exp, goal_end_row):
    goal_end_row 가 없으면 → Verdict J2 UNKNOWN("GOAL_END 없음")
    반환 _v("J2", "cause", goal_end_row["cause"] == exp.cause, exp.cause, goal_end_row["cause"])

함수 judge_phases(exp, phases):
    is_prefix = phases == list(PHASES[:len(phases)])                  # 표준 순서의 앞부분
    exp.phases_exact 가 있으면 ok = phases == exp.phases_exact
    아니면 ok = is_prefix and (exp.phases_prefix_last 없음 또는 (phases 있고 phases[-1] == exp.phases_prefix_last))
    반환 _v("J3", "phases", ok, …, phases)

함수 judge_last_zero(terminal_row):
    없으면 → J4 UNKNOWN
    반환 _v("J4", "마지막 cmd 0", norm(cmd) ≤ ZERO_EPS, "0", norm(cmd)·1000 mm/s)

함수 judge_zero_hold(terminal_row, hold, zero_hold_s, rate_hz):
    terminal_row 없으면 → J5 UNKNOWN
    need_n = round(zero_hold_s × rate_hz) − 1                          # 0.5 s·30 Hz → 14
    all_zero = 모든 hold 행 norm(cmd) ≤ ZERO_EPS
    span = (hold[-1].t_pub − terminal.t_pub) if hold else 0
    ok = all_zero and len(hold) ≥ need_n and span ≥ zero_hold_s − 1/rate_hz
    반환 _v("J5", "0 유지", ok, f"≥{need_n}틱·{zero_hold_s}s 전부 0", f"{len(hold)}틱·{span:.3f}s·전부0={all_zero}")

함수 judge_period(ticks):
    t = [r.t_pub_s for r in ticks]; len < 2 → J6 UNKNOWN
    mean_ms = 평균(차이) × 1000
    반환 _v("J6", "주기", |mean_ms − PERIOD_NOMINAL_MS| ≤ PERIOD_TOL_MS, "33.3±3 ms", f"{mean_ms:.1f} ms (최소 …, 최대 …)")

함수 judge_follow(progress, align_along_m):
    대상 = [r for r in progress if r.visible and not r.stopping and not r.terminal]
    len(대상) < FOLLOW_MIN_TICKS → J11 UNKNOWN(f"보이는 틱 {n}개")
    나쁜 것 = []
    대상 마다:
        c = r.cmd_vel_mps; b = r.belt_vel_mps; d = b / ‖b‖
        c·d < −1e-6        → 나쁜 것 += "벨트 반대"                 # 상류로 돌진 금지 (항상)
        tcp_now_m·predicted_m·error_m 중 None → 나쁜 것 += "빈 필드"
        r.err_along_m ≥ −align_along_m 이고 norm(c) ≤ ZERO_EPS → 나쁜 것 += "cmd 0"   # 박스가 상류면 0 이 정상(기다리기)
    반환 _v("J11", "추종", 나쁜 것 없음, f"{len(대상)}틱: 벨트방향≥0·필드 채움·(박스 상류 아님→cmd≠0)", 첫 나쁜 것 몇 개)

함수 line_distance(p, start, d):                        # 점 p 와 (start, 방향 d) 직선 사이 거리
    w = p − start; 반환 ‖w − (w·d̂) d̂‖

함수 judge_track_lock(rows, start, belt_dir):
    대상 = [r for r in rows if r.position_base_m 이 있음]
    없으면 → J12 UNKNOWN
    worst = max(line_distance(r.position_base_m, start, belt_dir))
    반환 _v("J12", "트랙 고정", worst ≤ TRACK_LOCK_TOL_M, "≤ 5 mm", f"{worst·1000:.1f} mm")

함수 in_window(t, start, end):  반환 start ≤ t < end              # end 가 None 이면 끝 없음

함수 parse_gateway(lines):                                  # 사건마다 시각을 남긴다 (창으로 거르려고)
    facts = GatewayFacts(mode=None, watchdogs=[], stops=[(시각, 결과)], stats=[(시각, watchdog, stop, ms_ok, ms_fail)])
    줄 마다:
        GW_STARTED 맞으면 facts.mode = 잡힌 첫 단어
        GW_WATCHDOG 맞으면 watchdogs += 시각
        GW_STOP 맞으면 stops += (시각, 결과)
        GW_STATS 맞으면 stats += (시각, N, N, N, N)
    반환 facts

함수 judge_watchdog(facts, terminal_t, win):             # win = (goal 수락 ROS 시각, SIGINT ROS 시각)
    terminal_t 없음 → J7 UNKNOWN
    ws = [t for t in facts.watchdogs if in_window(t, *win)]
    ws 없음 → J7 UNKNOWN("창 안에 watchdog 줄 없음")
    d = ws[0] − terminal_t
    ok = len(ws) == 1 and WATCHDOG_DELAY_S[0] ≤ d ≤ WATCHDOG_DELAY_S[1]
    반환 _v("J7", "watchdog", ok, "1회·종료 뒤 0.6~0.9 s", f"{len(ws)}회·{d:.3f} s")

함수 _stats_in(facts, win):  반환 [s for s in facts.stats if in_window(s.시각, *win)]

함수 judge_move_stop(facts, cancel, win):
    st = _stats_in(facts, win); 없음 → J8 UNKNOWN
    want = 2 if cancel else 1; ok_n = Σ ms_ok; fail_n = Σ ms_fail
    반환 _v("J8", "move_stop", ok_n == want and fail_n == 0, f"ok {want}·fail 0", f"ok {ok_n}·fail {fail_n}")

함수 judge_stop(facts, cancel, win):
    st = _stats_in(facts, win); 없음 → J9 UNKNOWN
    want = 1 if cancel else 0
    lines = [r for (t, r) in facts.stops if in_window(t, *win)]
    ok = Σ stop == want and len(lines) == want and all(r == "OK" for r in lines)
    반환 _v("J9", "stop", ok, …, …)

함수 judge_dry_run(mode):                                 # mode = 시작 줄 첫 단어 (None = 줄 없음)
    mode 가 None → J10 UNKNOWN("gateway 시작 줄 없음")
    반환 _v("J10", "gateway dry_run", mode == "dry_run", "dry_run", mode)

함수 preflight_problems(domain_id, node_names):         # 순수 — 사전 점검 J0
    문제 = []
    domain_id == REAL_DOMAIN → 문제 += "ROS_DOMAIN_ID=30 (공용 PC·실로봇 도메인)"
    node_names 중 SIM_NODES 에 든 것 → 문제 += f"이미 떠 있는 노드: {그것들}"
    반환 문제

함수 exit_code(verdicts):
    FAIL 하나라도 → 1;  아니면 UNKNOWN 하나라도 → 2;  아니면 0

함수 worst_code(codes):                                 # 여러 case 종합: 1 > 2 > 0 (숫자 max 아님)
    1 in codes → 1;  2 in codes → 2;  아니면 0

함수 format_table(case_name, verdicts):
    머리: f"== {case_name} =="  + "| ID | 항목 | 기대 | 실제 | 판정 |"
    줄마다 판정은 PASS→"✅", FAIL→"❌", UNKNOWN→"⚠️ 판정 불가"
    반환 문자열
```

## 7. sim_check.py — 실행 부분 (ROS·프로세스·파일)

```text
함수 parse_args(argv):  DD 6.1 표대로 argparse. --case 기본 "all", --profile 기본 "pre_u5"

함수 default_config():
    top = `git rev-parse --show-toplevel` (실패 시 None)
    반환 top/config/voss_config.yaml (있을 때만) 아니면 None

함수 start_launch(case, args, run_dir):
    cmd = ["ros2", "launch", "voss_servo", "sim.launch.py", f"config:={args.config}", f"scenario:={case.scenario}",
           f"object_mm:={case.object_mm}", f"log_dir:={run_dir}"] (+ f"kp:={args.kp}")
    log = open(run_dir/launch.log, "w")
    반환 Popen(cmd, stdout=log, stderr=STDOUT, start_new_session=True,
               env=os.environ + PYTHONUNBUFFERED=1 + RCUTILS_COLORIZED_OUTPUT=0), log

함수 stop_launch(node, proc):                              # 반환: SIGINT 보낸 ROS 시각
    t_int = 지금 ROS 시각
    proc 가 이미 끝났으면 반환 t_int
    proc.send_signal(SIGINT)                                   # launch 에만 — launch 가 자식에 SIGINT→SIGTERM→SIGKILL 로 전파
    STOP_S 동안 기다림
    아직이면 os.killpg(proc.pid, SIGKILL) 하고 "SIGKILL 사용" 기록      # 마지막 수단만 그룹 전체
    반환 t_int

함수 preflight(node):                                      # ROS 부분 — 그래프를 보고 순수 함수로 판단
    DISCOVERY_S 동안 spin_once 로 그래프 탐색
    반환 preflight_problems(os.environ.get("ROS_DOMAIN_ID", "0"), node.get_node_names())

함수 wait_for_text(path, pattern, timeout, after_t=None):     # 로그 파일을 0.2 s 마다 다시 읽는다
    deadline 까지: 파일 줄에서 pattern 맞는 것(after_t 가 있으면 그 시각 이후)을 찾으면 반환, 없으면 0.2 s 쉼
    반환 None (시간 초과)

함수 run_goal(node, client, case, args, t_case):               # ROS 부분 (t_case = case 시작 ROS 시각)
    client.wait_for_server(SERVER_S) 실패 → 반환 Outcome(error="액션 서버 없음")
    first_box 기다림: node 의 /voss/vision/box 구독(best_effort, depth 5)에 **stamp ≥ case 시작 ROS 시각** 인 메시지가 올 때까지 spin_once(≤ FIRST_BOX_S)   # 앞 case 의 남은 메시지 배제
    goal 수락 ROS 시각 t_goal 을 기록 (J7~J9 창의 시작)
    phases = []
    send = client.send_goal_async(Goal(track_id=1), feedback_callback=λ fb: phases.append(fb.feedback.phase))
    수락 대기 (spin_until_future_complete, ≤ 5 s); 거부 → Outcome(error="goal 거부")
    goal_id = bytes(handle.goal_id.uuid).hex()
    t_acc = time.monotonic(); res_f = handle.get_result_async(); cancel_sent = False
    res_f 가 끝날 때까지 spin_once(0.05):
        case.cancel_after 이고 아직 안 보냈고 경과 ≥ cancel_after → handle.cancel_goal_async(); cancel_sent = True
        경과 > goal_timeout → Outcome(error="goal 시간 초과", goal_id, phases)
    r = res_f.result()
    반환 Outcome(goal_id, t_goal, phases, r.status, r.result.reason, r.result.grasped, r.result.attempts, cancel_sent)

함수 read_jsonl(dir, sub):  dir/sub/*.jsonl 모든 줄 → dict 목록 (파일 없으면 [])

함수 run_case(node, client, case, args, out_root, hold_cfg):   # hold_cfg = sim yaml 의 zero_hold_s·rate_hz·align_tol_along
    run_dir = out_root/case.name 만들기; verdicts = []
    문제 = preflight(node)
    문제가 있으면 → verdicts += J0 FAIL(문제); 출력; 반환 (sim 을 띄우지 않는다)   # 종료 코드는 main 이 2 로
    t_case = 지금 ROS 시각; proc = None; t_int = None
    시도:
        proc, log = start_launch(case, args, run_dir)
        mode = wait_for_text(launch.log, GW_STARTED, GW_START_S) 의 첫 단어 (없으면 None)
        verdicts += judge_dry_run(mode)
        mode != "dry_run" → 즉시 반환 (finally 에서 sim 정지)        # 안전: 실기 gateway 로 goal 을 보내지 않는다
        out = run_goal(node, client, case, args, t_case)
        result.json 저장 (out 의 모든 값 + 시각)
        out.error 가 없으면:
            wd = wait_for_text(launch.log, GW_WATCHDOG, SETTLE_S)
            wd 가 있으면 wait_for_text(launch.log, GW_STATS, SETTLE_S, after_t=wd 시각)   # 그 뒤 통계 줄까지
    마지막에(finally): proc 가 있으면 t_int = stop_launch(node, proc), log 닫기
    # ── 판정 ──
    ticks = select_goal_rows(read_jsonl(run_dir, "ticks"), out.goal_id)
    goal_end = select_goal_rows(read_jsonl(run_dir, "attempts"), …) 중 event == "GOAL_END" 첫 행
    progress, terminal, hold = split_goal_ticks(ticks)
    exp = EXPECT[(args.profile, case.name)]
    out.error 면 J1 UNKNOWN(out.error) 아니면 judge_result
    + judge_cause, judge_phases, judge_last_zero, judge_zero_hold(…, zero_hold_s·rate_hz — 설치된 belt_servo_sim.yaml 을 launch_params 로 읽은 값 (+ --kp 처럼 바뀔 수 있는 값은 쓰지 않음)), judge_period(progress + [terminal] + hold)
    facts = parse_gateway(launch.log 줄); win = (out.t_goal, t_int)
    + judge_watchdog(facts, terminal.t_pub_s, win), judge_move_stop(facts, case.cancel_after, win), judge_stop(facts, case.cancel_after, win)
    case 가 normal·two_boxes 이고 profile pre_u5 → judge_follow(progress, hold_cfg.align_along_m)
    case 가 two_boxes → judge_track_lock(progress + [terminal], fake 시작 위치, belt 방향(틱 로그 belt_vel_mps))
    verdict.json 저장, format_table 출력
    반환 verdicts

함수 main(argv=None):
    args = parse_args(argv)
    args.config 없으면 default_config(); 그래도 없으면 → "config 를 못 찾음 (--config)" 출력, 종료 2
    case 목록 = PROFILE_CASES[args.profile] (args.case == "all") 또는 [args.case]
    args.case 가 profile 에 없는 조합(EXPECT 에 없음)이면 → 안내 출력, 종료 2
    out_root = args.out 또는 /tmp/voss_sim/<YYYYmmdd_HHMMSS>
    hold_cfg = 설치된 belt_servo_sim.yaml 을 launch_params 로 읽어 zero_hold_s·rate_hz·align_tol_along_mm
    rclpy.init(); node = Node("sim_check"); client = ActionClient(node, TrackAndGrasp, "/voss/servo/track_and_grasp")
    시도: case 마다 v = run_case(...); 결과[case] = 2 if J0 FAIL 이 있으면 else exit_code(v)   # 사전 점검 거부는 2
          J0 거부가 나오면 남은 case 는 돌리지 않는다
    마지막에: node.destroy_node(); rclpy.try_shutdown()
    요약 표 출력 (case | 종료 코드 | run 폴더)
    sys.exit(worst_code(결과 값))                               # 1 > 2 > 0
```

## 8. 변경 기록
- 2026-10-10 r1: 초안.
- 2026-10-10 r2: 독립 재검 반영 — Include `PythonLaunchDescriptionSource`·`.items()`, NULL 비교 strip 만, emulate_tty 삭제·색 끔, fake_box T 8 s, `--no-launch` 삭제, 사전 점검 J0(`preflight_problems`), 첫 박스는 case 시작 뒤 stamp 만, SIGINT 는 launch 에만·STOP 15 s·SIGINT 시각 기록, J7~J9 창 [goal 수락, SIGINT), J10 은 시작 줄 첫 단어, J11 정의 보정(박스 상류면 0 허용), SKIP 상태 삭제, `worst_code`.
