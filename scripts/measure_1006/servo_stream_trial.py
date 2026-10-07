#!/usr/bin/env python3
"""U7 #34 — 서보 스트림 저속 시험 (⚠ 로봇이 움직인다).

speedl_stream(1순위) 또는 servol_stream 으로 30 Hz 명령을 보내 ±10 mm 이내를 5 mm/s 이하로
왕복하고, 퍼블리시를 끊었을 때 로봇이 멈추는지 본다. 결과는 CSV 와 요약으로 남긴다.

    # 실로봇: 사람이 비상정지 옆에서 직접 실행. robot_gateway 는 끈다. --z-min 은 학민과 정한 값
    python3 servo_stream_trial.py speedl --z-min <mm>
    python3 servo_stream_trial.py servol --z-min <mm>
    python3 servo_stream_trial.py speedl --z-min <mm> --time 0.1   # time 의미 비교
    python3 servo_stream_trial.py speedl --z-min <mm> --acc 100    # 가속도 비교 (반응 속도)
    # 에뮬레이터 (개인 PC): voss-dsr-virtual-exec py <이 파일> speedl --yes
    python3 servo_stream_trial.py analyze <CSV 경로>                 # 저장된 CSV 다시 요약

단계 (모두 한 축, 기본 base x)
  out    +v 로 travel 만큼   → hold   0 (speedl: 0 속도 / servol: 현재 목표 유지)
  back   −v 로 travel 만큼   → hold
  cut    +v 로 CUT_MOVE_S 초 → silent 퍼블리시 중단 CUT_OBSERVE_S 초 (멈추는지 관찰) → hold
  return 원위치로 되돌림      → 끝 (move_stop 소프트 정지)
각 hold 끝(스트리밍이 멈춘 때)에만 get_current_posx 를 부른다 (스트림과 직렬 큐를 다투지 않게).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import math
import os
import sys
import time
from pathlib import Path

# ── 안전 상수 (바꾸려면 PR 로. 실로봇 값은 학민과 확인) ─────────────────────
PREFIX = "/dsr01/dsr_controller2/"  # #55 · record_pose.py 와 같음
RATE_HZ = 30.0  # belt_servo 와 같은 명령 주기
MAX_SPEED_MMS = 5.0  # 선속도 상한 (mm/s)
MAX_TRAVEL_MM = 10.0  # 시작점에서 한 방향 최대 이동 (mm)
ABORT_DEV_MM = 14.0  # TF 로 본 시작점 편차가 이것을 넘으면 즉시 정지 (mm)
LIN_ACC_MMS2 = 20.0  # 선가속도 기본값 (speedl acc[0], servol 상한)
MAX_LIN_ACC_MMS2 = 100.0  # --acc 상한. 컨트롤러는 time 보다 acc 를 우선한다(에뮬레이터 알람 1216)
ANG_ACC_DEGS2 = 10.0  # 각가속도 (각속도는 0 으로만 보낸다)
SERVOL_VEL_LIMIT = [10.0, 10.0]  # servol 속도 상한 [mm/s, deg/s]
HOLD_S = 1.0  # 각 단계 뒤 정지 관찰 시간 (s)
CUT_MOVE_S = 0.6  # 끊김 시험: 움직이는 시간 (≈ 3 mm)
CUT_OBSERVE_S = 1.0  # 끊김 시험: 퍼블리시 없이 지켜보는 시간 (계속 가도 +5 mm 이내)
X_RANGE_MM = (-107.0 + 30.0, 638.0 - 30.0)  # #6 추종 구간 TCP x (안쪽 30 mm 여유)
MOVE_EPS_RAD = 2e-4  # joint 가 이만큼 바뀌면 "움직였다" (≈ 0.01°)
STOP_SSTO = 2  # move_stop stop_mode: DR_SSTO (소프트 정지)

DATA_DIR = Path(os.environ.get("VOSS_MEASURE_DIR", Path.home() / "voss_ws" / "measure_1006_data"))
AXES = {"x": 0, "y": 1}  # 움직일 base 축
FIELDS = [
    "t",
    "kind",
    "phase",
    "seq",
    "cmd",
    "j1",
    "j2",
    "j3",
    "j4",
    "j5",
    "j6",
    "tf_x",
    "tf_y",
    "tf_z",
]


# ─────────────────────────────────────────────── 순수 함수 (로봇 없이 확인 가능)
def check_limits(speed: float, travel: float, acc: float = LIN_ACC_MMS2) -> None:
    """속도·이동량·가속도가 안전 상수 안인지 확인한다."""
    if not 0 < acc <= MAX_LIN_ACC_MMS2:
        raise SystemExit(f"--acc 는 0 < a ≤ {MAX_LIN_ACC_MMS2} mm/s²")
    if not 0 < speed <= MAX_SPEED_MMS:
        raise SystemExit(f"--speed 는 0 < v ≤ {MAX_SPEED_MMS} mm/s")
    if not 0 < travel <= MAX_TRAVEL_MM:
        raise SystemExit(f"--travel 은 0 < d ≤ {MAX_TRAVEL_MM} mm")


def check_start_pose(posx: list[float], z_min: float | None) -> None:
    """시작 위치가 추종 구간 안이고 안전 높이 위인지 확인한다."""
    x, z = posx[0], posx[2]
    if not X_RANGE_MM[0] <= x <= X_RANGE_MM[1]:
        raise SystemExit(f"시작 x={x:.1f} mm 가 구간 {X_RANGE_MM} 밖이다")
    if z_min is not None and z < z_min:
        raise SystemExit(f"시작 z={z:.1f} mm 가 --z-min {z_min} 보다 낮다")


def build_plan(speed: float, travel: float) -> list[tuple[str, float, float]]:
    """(단계 이름, 지속 시간 s, 부호 있는 속도 mm/s) 목록. 속도 0 은 정지 유지."""
    t_move = travel / speed  # 예: 10 mm / 5 mm/s = 2 s
    return [
        ("out", t_move, +speed),
        ("hold", HOLD_S, 0.0),
        ("back", t_move, -speed),
        ("hold", HOLD_S, 0.0),
        ("cut", CUT_MOVE_S, +speed),
        ("silent", CUT_OBSERVE_S, math.nan),  # nan = 아무것도 퍼블리시하지 않음
        ("hold", HOLD_S, 0.0),  # 끊김 관찰 뒤 다시 정지 명령
    ]


def speedl_vel(axis: int, v: float) -> list[float]:
    """한 축 선속도만 있는 speedl vel[6] (mm/s, deg/s). 각속도는 0."""
    vel = [0.0] * 6
    vel[axis] = v
    return vel


def servol_target(start: list[float], axis: int, offset_mm: float) -> list[float]:
    """시작 posx 에서 한 축만 offset 만큼 옮긴 servol 목표 pos[6]."""
    pos = list(start)
    pos[axis] = start[axis] + offset_mm
    return pos


def summarize(
    rows: list[dict], posx_log: list[tuple[str, list[float]]], speed: float, travel: float
) -> dict:
    """CSV 행으로 지연·이동량·끊김 뒤 정지를 계산한다."""
    js = [r for r in rows if r["kind"] == "js"]  # joint_states 수신 행
    cmds = [r for r in rows if r["kind"] == "cmd"]  # 보낸 명령 행
    out: dict = {}
    if len(cmds) > 1:  # 우리 쪽 퍼블리시 간격
        dts = [
            b["t"] - a["t"]
            for a, b in zip(cmds, cmds[1:], strict=False)
            if a["phase"] == b["phase"]
        ]
        if dts:
            out["cmd_period_ms_mean"] = round(1000 * sum(dts) / len(dts), 1)
            out["cmd_period_ms_max"] = round(1000 * max(dts), 1)
    first_out = next((r["t"] for r in cmds if r["phase"] == "out"), None)
    if first_out is not None and js:
        base = next((r for r in reversed(js) if r["t"] <= first_out), js[0])  # 명령 직전 자세
        moved = next(
            (r for r in js if r["t"] > first_out and joint_dev(r, base) > MOVE_EPS_RAD), None
        )
        out["start_latency_ms"] = round(1000 * (moved["t"] - first_out), 1) if moved else None
    last_cut = max((r["t"] for r in cmds if r["phase"] == "cut"), default=None)
    if last_cut is not None:  # 끊은 뒤(silent 동안) 마지막으로 움직인 시각
        after = [r for r in js if r["phase"] == "silent"]
        last_move = None
        for a, b in zip(after, after[1:], strict=False):
            if joint_dev(a, b) > MOVE_EPS_RAD / 4:  # 연속 두 샘플 사이 변화
                last_move = b["t"]
        out["stop_after_cut_ms"] = round(1000 * (last_move - last_cut), 1) if last_move else 0.0
        # silent 마지막 0.2 s 에도 움직였으면 "끊겨도 계속 감" 으로 본다
        out["still_moving_at_silent_end"] = bool(
            last_move and after and last_move > after[-1]["t"] - 0.2
        )
        tf_after = [r for r in after if r["tf_x"] != ""]
        if len(tf_after) > 1:
            out["drift_after_cut_mm"] = round(tf_dist(tf_after[0], tf_after[-1]), 2)
    d = {k: v for k, v in posx_log}  # 단계 끝 posx
    if "start" in d and "out" in d:
        out["out_travel_mm_cmd"] = travel
        out["out_travel_mm_actual"] = round(dist3(d["start"], d["out"]), 2)
    if "out" in d and "back" in d:
        out["back_travel_mm_actual"] = round(dist3(d["out"], d["back"]), 2)
    if "back" in d and "cut" in d:
        out["cut_travel_mm_cmd"] = round(speed * CUT_MOVE_S, 2)
        out["cut_travel_mm_actual"] = round(dist3(d["back"], d["cut"]), 2)
    return out


def joint_dev(a: dict, b: dict) -> float:
    """두 joint 샘플의 최대 관절 차이 (rad)."""
    return max(abs(float(a[f"j{i}"]) - float(b[f"j{i}"])) for i in range(1, 7))


def tf_dist(a: dict, b: dict) -> float:
    """두 TF 샘플 사이 거리 (mm)."""
    return math.dist(
        [float(a[k]) for k in ("tf_x", "tf_y", "tf_z")],
        [float(b[k]) for k in ("tf_x", "tf_y", "tf_z")],
    )


def dist3(p: list[float], q: list[float]) -> float:
    """posx 앞 3개(x,y,z mm) 사이 거리."""
    return math.dist(p[:3], q[:3])


# ─────────────────────────────────────────────── ROS 부분 (로봇·에뮬레이터 필요)
class Trial:
    """한 번의 시험: 사전 점검 → 단계별 스트리밍 → 기록."""

    def __init__(self, mode: str, axis: int, cmd_time: float, acc: float = LIN_ACC_MMS2):
        import rclpy
        from dsr_msgs2.msg import ServolStream, SpeedlStream
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState
        from tf2_ros import Buffer, TransformListener

        self.rclpy, self.mode, self.axis, self.cmd_time = rclpy, mode, axis, cmd_time
        self.acc = acc  # 선가속도 (mm/s²)
        rclpy.init()
        self.node = rclpy.create_node("voss_servo_stream_trial")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)  # 컨트롤러 구독과 호환
        msg_type = SpeedlStream if mode == "speedl" else ServolStream
        self.Msg = msg_type
        self.pub = self.node.create_publisher(msg_type, PREFIX + f"{mode}_stream", qos)
        self.joint: list[float] | None = None  # 최신 joint (rad)
        self.rows: list[dict] = []  # CSV 행
        self.t0 = time.monotonic()  # 상대 시각 기준
        self.phase = "init"
        self.node.create_subscription(JointState, "/dsr01/joint_states", self._on_joint, 50)
        self.tf_buf = Buffer()
        self._tf = TransformListener(self.tf_buf, self.node)  # 잡아 둬야 구독 유지
        self.tf_start: list[float] | None = None
        self.armed = False  # 첫 명령을 보낸 뒤 True → 예외 때 정지를 부른다

    # ── 기록 ──
    def _tf_xyz(self) -> list[float] | None:
        """TF base_link → link_6 위치 (mm). 없으면 None."""
        from rclpy.time import Time

        if not self.tf_buf.can_transform("base_link", "link_6", Time()):
            return None
        t = self.tf_buf.lookup_transform("base_link", "link_6", Time()).transform.translation
        return [t.x * 1000, t.y * 1000, t.z * 1000]

    def _row(self, kind: str, seq: int | str = "", cmd: float | str = "") -> None:
        """현재 joint·TF 를 붙여 한 행을 남긴다."""
        j = self.joint or [math.nan] * 6
        tf = self._tf_xyz()
        self.rows.append(
            {"t": time.monotonic() - self.t0, "kind": kind, "phase": self.phase, "seq": seq, "cmd": cmd,
             **{f"j{i + 1}": j[i] for i in range(6)},
             "tf_x": tf[0] if tf else "", "tf_y": tf[1] if tf else "", "tf_z": tf[2] if tf else ""}
        )  # fmt: skip

    def _on_joint(self, msg) -> None:
        """joint_states 를 받을 때마다 기록한다 (DRFL 호출이 없는 관찰 수단)."""
        self.joint = list(msg.position[:6])
        self._row("js")

    # ── 서비스 (스트리밍이 멈춘 때만) ──
    def call(self, srv_type, name: str, timeout: float = 3.0, **kw):
        """두산 서비스를 한 번 부른다. 실패하면 None."""
        cli = self.node.create_client(srv_type, PREFIX + name)
        if not cli.wait_for_service(timeout_sec=timeout):
            return None
        fut = cli.call_async(srv_type.Request(**kw))
        self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
        self.node.destroy_client(cli)
        return fut.result() if fut.done() else None

    def posx(self) -> list[float]:
        """현재 TCP posx (base, mm·deg)."""
        from dsr_msgs2.srv import GetCurrentPosx

        r = self.call(GetCurrentPosx, "aux_control/get_current_posx", ref=0)
        if r is None or not r.success:
            raise RuntimeError("get_current_posx 실패")
        return list(r.task_pos_info[0].data[:6])

    def stop(self) -> None:
        """소프트 정지 (DR_SSTO). 시험 중단·끝에 부른다."""
        from dsr_msgs2.srv import MoveStop

        self.call(MoveStop, "motion/move_stop", stop_mode=STOP_SSTO)

    def robot_status(self) -> dict:
        """시스템·모드·상태를 읽는다."""
        from dsr_msgs2.srv import GetRobotMode, GetRobotState, GetRobotSystem

        s = self.call(GetRobotSystem, "system/get_robot_system")
        m = self.call(GetRobotMode, "system/get_robot_mode")
        st = self.call(GetRobotState, "system/get_robot_state")
        return {"system": s.robot_system if s else None, "mode": m.robot_mode if m else None,
                "state": st.robot_state if st else None}  # fmt: skip

    def gateway_running(self) -> bool:
        """robot_gateway(또는 /voss 노드)가 떠 있으면 True."""
        return any(
            "robot_gateway" in n or ns.startswith("/voss")
            for n, ns in self.node.get_node_names_and_namespaces()
        )

    # ── 스트리밍 ──
    def spin_for(self, sec: float) -> None:
        """sec 초 동안 콜백만 처리한다 (퍼블리시 없음)."""
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.rclpy.spin_once(self.node, timeout_sec=0.002)
            self._guard()

    def _guard(self) -> None:
        """TF 로 본 시작점 편차가 한계를 넘으면 즉시 정지하고 끝낸다."""
        if self.tf_start is None:
            return
        now = self._tf_xyz()
        if now is not None and math.dist(now, self.tf_start) > ABORT_DEV_MM:
            self.stop()
            raise SystemExit(
                f"중단: 시작점에서 {math.dist(now, self.tf_start):.1f} mm 벗어남 (> {ABORT_DEV_MM})"
            )

    def _msg(self, start: list[float], offset: float, v: float):
        """단계의 한 틱 명령 메시지를 만든다."""
        m = self.Msg()
        if self.mode == "speedl":
            m.vel = speedl_vel(self.axis, v)  # 속도 그대로 (mm/s)
            m.acc = [self.acc, ANG_ACC_DEGS2]
        else:
            m.pos = servol_target(start, self.axis, offset)  # 적분한 목표 위치
            m.vel = list(SERVOL_VEL_LIMIT)  # 상한 (목표 속도 아님)
            m.acc = [self.acc, ANG_ACC_DEGS2]
        m.time = float(self.cmd_time)
        return m

    def stream(self, phase: str, sec: float, v: float, start: list[float], offset: float) -> float:
        """phase 를 sec 초 동안 30 Hz 로 보낸다. 끝난 시점의 누적 지령 오프셋(mm)을 돌려준다."""
        self.phase = phase
        if math.isnan(v):  # silent: 아무것도 보내지 않고 지켜본다
            self.spin_for(sec)
            return offset
        self.armed = True
        period = 1.0 / RATE_HZ
        n = max(1, round(sec * RATE_HZ))  # 보낼 틱 수
        nxt = time.monotonic()
        for k in range(n):
            offset += v * period  # servol 용 누적 목표 (speedl 은 기록용)
            self.pub.publish(self._msg(start, offset, v))
            self._row("cmd", k, v if self.mode == "speedl" else start[self.axis] + offset)
            nxt += period
            while time.monotonic() < nxt:  # 다음 틱까지 콜백 처리
                self.rclpy.spin_once(
                    self.node, timeout_sec=max(0.0, min(0.002, nxt - time.monotonic()))
                )
            self._guard()
        return offset

    def close(self) -> None:
        self.node.destroy_node()
        self.rclpy.shutdown()


def confirm(args, status: dict) -> None:
    """실행 전 확인. 에뮬레이터는 --yes, 실로봇은 직접 'MOVE' 입력."""
    target = os.environ.get("VOSS_DSR_TARGET", "")
    real = status["system"] == 0  # 0 = real
    if real and target == "emulator":
        raise SystemExit("거부: 래퍼는 에뮬레이터라고 했는데 robot_system 이 real 이다")
    if not real:
        if not args.yes:
            raise SystemExit("virtual 대상: --yes 로 실행한다")
        return
    if args.yes:
        raise SystemExit("실로봇에서는 --yes 를 쓰지 않는다. 사람이 MOVE 를 입력한다")
    if args.z_min is None:
        raise SystemExit("실로봇에서는 --z-min (학민과 정한 안전 높이, mm) 이 필요하다")
    print("\n⚠ 실로봇이 움직인다. 비상정지 옆에 사람이 있고, robot_gateway 가 꺼져 있는가?")
    if input("계속하려면 MOVE 입력: ").strip() != "MOVE":
        raise SystemExit("취소")


def run(args) -> int:
    check_limits(args.speed, args.travel, args.acc)
    axis = AXES[args.axis]
    tr = Trial(args.mode, axis, args.time, args.acc)
    posx_log: list[tuple[str, list[float]]] = []
    try:
        time.sleep(1.0)  # DDS 발견 대기
        if tr.gateway_running():
            raise SystemExit(
                "거부: robot_gateway(/voss 노드)가 떠 있다. 끄고 다시 (CLAUDE.md 규칙 3)"
            )
        st = tr.robot_status()
        print(f"robot system={st['system']} mode={st['mode']} state={st['state']}")
        if st["mode"] != 1 or st["state"] != 1:  # AUTONOMOUS, STANDBY
            raise SystemExit("거부: 모드가 AUTONOMOUS(1), 상태가 STANDBY(1) 여야 한다")
        start = tr.posx()
        check_start_pose(start, args.z_min)
        print(f"시작 TCP posx = {[round(v, 1) for v in start]}")
        print(
            f"계획: {args.mode} 축 {args.axis} ±{args.travel} mm @ {args.speed} mm/s, time={args.time}, acc={args.acc}"
        )
        confirm(args, st)
        tr.spin_for(0.5)  # joint·TF 를 먼저 채운다
        tr.tf_start = tr._tf_xyz()
        if tr.tf_start is None:
            print("⚠ TF 없음: 편차 감시는 시간 제한(속도×시간)에만 의존한다")
        posx_log.append(("start", start))
        offset = 0.0
        labels = iter(["out", "back", "cut"])  # hold 가 끝날 때마다 붙일 이름
        for phase, sec, v in build_plan(args.speed, args.travel):
            offset = tr.stream(phase, sec, v, start, offset)
            if phase == "hold":  # 0 명령 뒤(스트리밍이 멈춘 때)만 위치 조회
                posx_log.append((next(labels), tr.posx()))
        tr.phase = "return"
        now = posx_log[-1][1]  # 끊김 시험 뒤 위치
        back = now[axis] - start[axis]  # 남은 편차 (mm)
        if abs(back) > 0.2:  # 원위치로 되돌린다
            v = -math.copysign(args.speed, back)
            tr.stream("return", abs(back) / args.speed, v, start, back)
            tr.stream("hold", HOLD_S, 0.0, start, 0.0)
        tr.stop()
        posx_log.append(("end", tr.posx()))
    except BaseException:
        if tr.armed:  # 명령을 보낸 뒤라면 어떤 예외든 먼저 정지
            try:
                tr.stop()
            except Exception as e:  # 정지 호출마저 실패하면 비상정지로
                print(f"⚠ move_stop 실패: {e} → 비상정지 버튼", file=sys.stderr)
        raise
    finally:
        rows = tr.rows
        tr.close()
    save_and_report(rows, posx_log, args)
    return 0


def save_and_report(rows: list[dict], posx_log, args) -> None:
    """CSV 저장 후 요약을 출력한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    path = DATA_DIR / f"servo_stream_{args.mode}_{stamp}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with path.with_suffix(".posx.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "x", "y", "z", "rx", "ry", "rz"])
        w.writerows([[k, *(round(v, 3) for v in p)] for k, p in posx_log])
    print_summary(summarize(rows, posx_log, args.speed, args.travel), args)
    print(f"\n저장: {path}")


def print_summary(s: dict, args) -> None:
    """measurements #3 기록 칸에 옮길 값."""
    target = os.environ.get("VOSS_DSR_TARGET", "real?")
    print(f"\n== 요약 ({args.mode}, 대상 {target}) ==")
    for k, v in s.items():
        print(f"  {k}: {v}")
    if target == "emulator":
        print("  ※ 에뮬레이터: 지연·주기는 측정값으로 쓰지 않는다 (명령 수용·움직임 여부만)")


def analyze(path: str, speed: float, travel: float) -> int:
    """저장된 CSV 를 다시 요약한다."""
    p = Path(path)
    with p.open() as f:
        rows = [{**r, "t": float(r["t"])} for r in csv.DictReader(f)]
    posx_log = []
    px = p.with_suffix(".posx.csv")
    if px.exists():
        with px.open() as f:
            posx_log = [
                (r["label"], [float(r[k]) for k in ("x", "y", "z", "rx", "ry", "rz")])
                for r in csv.DictReader(f)
            ]
    for k, v in summarize(rows, posx_log, speed, travel).items():
        print(f"  {k}: {v}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["speedl", "servol", "analyze"])
    ap.add_argument("csv", nargs="?", help="analyze 할 CSV")
    ap.add_argument("--axis", choices=list(AXES), default="x", help="움직일 base 축 (기본 x)")
    ap.add_argument("--speed", type=float, default=MAX_SPEED_MMS, help=f"mm/s (≤ {MAX_SPEED_MMS})")
    ap.add_argument("--travel", type=float, default=MAX_TRAVEL_MM, help=f"mm (≤ {MAX_TRAVEL_MM})")
    ap.add_argument("--time", type=float, default=0.0, help="메시지 time 필드 (s). 의미 비교용")
    ap.add_argument(
        "--acc", type=float, default=LIN_ACC_MMS2, help=f"선가속도 mm/s² (≤ {MAX_LIN_ACC_MMS2})"
    )
    ap.add_argument(
        "--z-min", type=float, default=None, help="실로봇 안전 높이 TCP z (mm, 학민 확인)"
    )
    ap.add_argument("--yes", action="store_true", help="에뮬레이터 전용 확인 생략")
    args = ap.parse_args(argv)
    if args.mode == "analyze":
        if not args.csv:
            raise SystemExit("analyze <CSV>")
        return analyze(args.csv, args.speed, args.travel)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
