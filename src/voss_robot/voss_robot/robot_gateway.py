"""robot_gateway — 인터페이스는 docs/interfaces/topics.md 참조.

두산 서비스는 SerialCallQueue 하나로만 부른다(CLAUDE.md 절대 규칙 3). dry_run 이면 두산·RG2 에
연결하지 않고 관측 자세에서 시작하는 가짜 로봇을 쓴다(개인 PC 개발용, speedl 을 적분해 움직인다).

지금 있는 것: /voss/robot/pose (TCP, base_link), /voss/robot/servo_cmd → speedl_stream(ADR-0010,
만료 watchdog → 0 속도 + 항상 move_stop, TCP z 하한·x 범위·속도 상한), /voss/robot/stop,
/voss/robot/gripper (RG2 Modbus 직접, ADR-0005), /voss/robot/state (RobotState),
/voss/robot/move_to_zone (PLACE·OBSERVE·VIEW, PICK 은 10/13).
"""

import threading
import time

import rclpy
from builtin_interfaces.msg import Time as TimeMsg
from geometry_msgs.msg import PoseStamped, TwistStamped
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_srvs.srv import Trigger

from voss_msgs.msg import RobotState
from voss_msgs.srv import Gripper, MoveToZone
from voss_robot.call_queue import SerialCallQueue
from voss_robot.config_params import ZONES
from voss_robot.doosan import DEFAULT_PREFIX, DoosanError, DryRunDoosan
from voss_robot.geometry import flange_to_ros_pose, flange_to_tcp, tcp_to_flange
from voss_robot.rg2 import DryRunRg2, Rg2
from voss_robot.servo_guard import ServoGuard, ServoParams
from voss_robot.state_logic import Inputs, decide
from voss_robot.zone_motion import SAFE_Z_MM, plan_move, slot_pose


class _ZoneError(RuntimeError):
    """MoveToZone 단계 실패. 메시지가 대문자 코드로 시작한다."""


class RobotGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("robot_gateway")
        # dry_run 기본값 true: 실수로 띄워도 로봇이 움직이지 않게 한다
        self.dry_run = self.declare_parameter("dry_run", True).value
        prefix = self.declare_parameter("dsr_prefix", DEFAULT_PREFIX).value
        rate = self.declare_parameter("pose_rate_hz", 50.0).value
        # service = get_current_tool_flange_posx(응답 수신 시각 stamp), joint_states = /dsr01/joint_states 최신 관절
        # → fkin(stamp = joint_states 시각, 기본). 10/08 오후 service 값이 0.1 s 마다만 바뀌었다
        self.pose_source = str(self.declare_parameter("pose_source", "joint_states").value)
        timeout = self.declare_parameter("call_timeout_s", 0.5).value
        max_misses = self.declare_parameter("max_call_misses", 3).value  # 연속 응답 없음 → FAULT
        # voss_config 값은 launch 가 넘긴다(config_params.py). 빈 배열 = 미측정
        self.tcp = list(self.declare_parameter("tcp_offset_mm", [0.0]).value)
        observe = list(self.declare_parameter("observe_pose", [0.0]).value)
        version = self.declare_parameter("config_version", "").value
        sha = self.declare_parameter("config_sha256", "").value
        self.get_logger().info(f"voss_config version={version} sha256={sha}")
        if len(self.tcp) != 3:
            raise RuntimeError(
                "tcp_offset_mm 가 없다(voss_config robot.tcp_offset_mm) — 시작 안 함"
            )

        self.queue = SerialCallQueue()  # 두산 서비스 호출은 전부 이 큐 하나로
        if self.dry_run:
            if len(observe) != 6:
                raise RuntimeError("dry_run 에는 observe_pose 가 필요하다(가짜 로봇 시작 자세)")
            self.dsr = DryRunDoosan(observe, self.tcp)
        else:
            from voss_robot.doosan import RosDoosan  # dsr_msgs2 는 실기·에뮬레이터에서만

            self.dsr = RosDoosan(self, prefix, timeout, max_misses)
            if not self.dsr.wait_ready(5.0):
                self.get_logger().error(f"두산 서비스가 안 보인다: {prefix} — 브링업 확인")

        # /voss/robot/pose: best_effort·volatile·depth 1 (topics.md QoS)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pose_pub = self.create_publisher(PoseStamped, "/voss/robot/pose", qos)
        self._pose_busy = False  # 앞 조회가 끝나기 전엔 새로 넣지 않는다(큐 밀림 방지)
        self._stats = {"n": 0, "fail": 0, "rtt": [], "wait": [], "skip": 0}
        self.create_timer(1.0 / rate, self._on_pose_timer)
        self.create_timer(5.0, self._log_stats)

        # ---- servo_cmd → speedl (ADR-0010). 값은 gateway 파라미터(voss_config.md 값 규칙) ----
        # [선 mm/s², 각 deg/s²]. 선가속은 time 보다 우선(조건 4). 추종 속도 값은 T26·T27 에서 정한다
        self.servo_acc = [
            float(a) for a in self.declare_parameter("servo_acc", [100.0, 10.0]).value
        ]
        sp = ServoParams(
            lin_acc_mm_s2=self.servo_acc[0],
            watchdog_s=float(self.declare_parameter("servo_watchdog_s", 0.2).value),
            max_speed_mm_s=float(self.declare_parameter("servo_max_speed_mm_s", 100.0).value),
            z_min_mm=float(self.declare_parameter("servo_z_min_mm", 78.0).value),
            x_range_mm=tuple(self.declare_parameter("servo_x_range_mm", [-107.0, 638.0]).value),
            pose_max_age_s=float(self.declare_parameter("servo_pose_max_age_s", 0.1).value),
            pose_latency_s=float(self.declare_parameter("servo_pose_latency_s", 0.06).value),
        )
        self.guard = ServoGuard(sp)
        # guard 는 servo 콜백·watchdog 타이머·pose 완료(큐 스레드)가 같이 쓴다
        self._glock = threading.Lock()
        self._sstats = self._empty_servo_stats()
        # 명령과 watchdog 을 한 줄로 (서로 끼어들지 않게)
        g_servo = MutuallyExclusiveCallbackGroup()
        self.create_subscription(
            TwistStamped, "/voss/robot/servo_cmd", self._on_servo_cmd, qos, callback_group=g_servo
        )
        self.create_timer(0.02, self._on_servo_tick, callback_group=g_servo)  # 50 Hz watchdog 점검
        self._was_active = False  # RobotState 갱신용 (servo 시작·끝)
        self.create_service(
            Trigger, "/voss/robot/stop", self._on_stop, callback_group=ReentrantCallbackGroup()
        )
        # ---- RG2: Compute Box Modbus TCP 직접 (ADR-0005). 모션과 다른 자원, 동시에 하나 ----
        host = self.declare_parameter("rg2_host", "192.168.1.1").value
        port = int(self.declare_parameter("rg2_port", 502).value)
        rg2_timeout = float(self.declare_parameter("rg2_timeout_s", 6.0).value)
        if self.dry_run:
            self.rg2 = DryRunRg2()
        else:
            from pymodbus.client import ModbusTcpClient

            self.rg2 = Rg2(ModbusTcpClient(host, port=port, timeout=1.0), timeout_s=rg2_timeout)
            try:
                w, _busy, grip, safety = self.rg2.status()
                self.get_logger().info(
                    f"RG2 {host}:{port} 폭 {w:.1f} mm, grip {grip}, safety_err {safety}"
                )
            except Exception as e:  # 연결 실패여도 노드는 뜬다(호출 때 COMM_ERROR)
                self.get_logger().error(
                    f"RG2 {host}:{port} 연결 실패: {e} — 툴체인저 전원·유선 확인"
                )
        self.create_service(
            Gripper,
            "/voss/robot/gripper",
            self._on_gripper,
            callback_group=ReentrantCallbackGroup(),
        )
        # ---- MoveToZone: voss_config zones·observe_pose(플랜지), 경로는 수직 상승 → 수평 → 수직 하강 ----
        self.observe = observe
        self.zones = {}
        for z in ZONES:
            pose = list(self.declare_parameter(f"zones.{z}.pose", [0.0]).value)
            grid = list(self.declare_parameter(f"zones.{z}.grid", [0.0]).value)
            view = list(self.declare_parameter(f"zones.{z}.view_pose", [0.0]).value)
            self.zones[z] = {
                "pose": pose if len(pose) == 6 else None,
                "grid": grid if len(grid) in (3, 4) else None,
                "view": view if len(view) == 6 else None,
            }
        self.pre_open = float(self.declare_parameter("gripper.pre_open_mm", 90.0).value)
        self.grip_force = float(self.declare_parameter("gripper.force_n", 14.0).value)
        self.safe_z = float(self.declare_parameter("zone_safe_z_mm", SAFE_Z_MM).value)
        # 먼 구역(C·HOLD)은 safe_z 에서 팔이 닿지 않는다(10/08 실기 1206). 수평 이동 높이를 구역마다 ikin 으로
        # 낮추되, 이 TCP z 보다 낮아지면 거부한다(박스 밑면 = TCP − 8, 트레이 테두리 ≈ TCP 50 → 약 60 mm 여유)
        self.min_travel_tcp_z = float(
            self.declare_parameter("zone_min_travel_tcp_z_mm", 120.0).value
        )
        # 트레이 안 이동: 먼 칸 위로 TCP 120 이 안 나오면 같은 구역 칸 0(−X 끝) 위까지 높게 와서 내려간 뒤
        # 트레이 안에서만 낮게 옆으로 간다(수직 자세 그대로). 이 높이 = 들고 가는 박스 밑면(TCP − 8)이 이미
        # 놓인 박스 윗면(≈ z 28)보다 약 24 mm 위 — 10/08 ikin: C 칸 2(+20) 61, 보류 +30 은 70
        self.min_in_tray_tcp_z = float(
            self.declare_parameter("zone_min_in_tray_tcp_z_mm", 60.0).value
        )
        self.min_j3_deg = float(
            self.declare_parameter("zone_min_j3_deg", 15.0).value
        )  # 팔꿈치 특이점 여유
        # [선 mm/s, 각 deg/s], [선 mm/s², 각 deg/s²]. 첫 실기는 낮게, 5구역 확인 뒤 올린다
        self.zone_vel = [float(v) for v in self.declare_parameter("zone_vel", [100.0, 45.0]).value]
        self.zone_acc = [float(v) for v in self.declare_parameter("zone_acc", [200.0, 90.0]).value]
        self.servo_settle_s = float(self.declare_parameter("zone_servo_settle_s", 1.5).value)
        self._mlock = threading.Lock()  # 모션 자원(MoveToZone)
        self._zone_action = ""
        self._abort = threading.Event()  # /voss/robot/stop 이 세운다
        self.create_service(
            MoveToZone,
            "/voss/robot/move_to_zone",
            self._on_move_to_zone,
            callback_group=ReentrantCallbackGroup(),
        )
        ready = [z for z, c in self.zones.items() if c["pose"] and c["grid"]]
        self.get_logger().info(
            f"MoveToZone 구역 {ready}, safe z {self.safe_z} mm(플랜지), vel {self.zone_vel}, acc {self.zone_acc}"
        )

        # ---- /voss/robot/state: reliable·transient_local·depth 1, 바뀔 때 + 2 Hz (#55 MC-019) ----
        from rclpy.qos import DurabilityPolicy

        self.state_pub = self.create_publisher(
            RobotState,
            "/voss/robot/state",
            QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self._last_pose_t = -1e9  # 마지막 pose 발행 (monotonic)
        self._ctrl = (None, -1e9)  # (두산 ROBOT_STATE, 읽은 시각)
        self._ctrl_busy = False
        self._rg2 = {"ok": False, "width": 0.0, "safety": False, "t": -1e9}
        self.stopped = False  # /voss/robot/stop 뒤 새 모션 명령 전
        self._state_key = None
        self._slock = threading.Lock()
        g_state = MutuallyExclusiveCallbackGroup()
        self.create_timer(0.5, self._on_state_timer, callback_group=g_state)
        mode = "dry_run (두산·RG2 연결 안 함)" if self.dry_run else f"real {prefix}"
        self.get_logger().info(
            f"robot_gateway started: {mode}, pose {rate:.0f} Hz, servo watchdog "
            f"{1e3 * sp.watchdog_s:.0f} ms, max {sp.max_speed_mm_s:.0f} mm/s, TCP z ≥ "
            f"{sp.z_min_mm:.1f} mm, x {sp.x_range_mm[0]:.0f}~{sp.x_range_mm[1]:.0f} mm, acc {self.servo_acc}"
        )

    # ---------------- pose ----------------
    def _on_pose_timer(self) -> None:
        if self._pose_busy:
            self._stats["skip"] += 1  # 앞 조회가 아직 큐에 있다
            return
        self._pose_busy = True
        self.queue.submit(self._read_pose).add_done_callback(self._pose_done)

    def _read_pose(self):
        """큐 작업: 플랜지 posx 를 읽어 (응답 수신 시각, 값, RTT) 를 돌려준다."""
        t0 = time.monotonic()
        if self.pose_source == "joint_states" and not self.dry_run:
            js = self.dsr.latest_joints()
            now = self.get_clock().now()
            if js is None or (now.nanoseconds - js[1]) * 1e-9 > 0.1:
                raise DoosanError("joint_states 없음·0.1 s 넘게 오래됨")
            flange = tcp_to_flange(self.dsr.fkin_tcp(js[0]), self.tcp)
            stamp = Time(nanoseconds=js[1], clock_type=now.clock_type)  # joint_states 측정 시각
        else:
            flange = self.dsr.get_flange_posx()
            stamp = self.get_clock().now()  # MC-004: 응답 수신 시각 (측정 시각 아님)
        return stamp, flange, time.monotonic() - t0, self.queue.last_wait_s

    def _pose_done(self, fut) -> None:
        self._pose_busy = False
        try:
            stamp, flange, rtt, wait = fut.result()
        except DoosanError as e:
            self._stats["fail"] += 1  # 실패 주기는 발행하지 않는다(옛 값 재발행 금지)
            if str(e).startswith("FAULT"):
                self.get_logger().error(f"두산 호출 중단: {e}", throttle_duration_sec=5.0)
            else:
                self.get_logger().warn(f"pose 조회 실패: {e}", throttle_duration_sec=2.0)
            return
        except Exception as e:  # 큐 종료 등
            self.get_logger().debug(f"pose 작업 종료: {e}")
            return
        (x, y, z), (qx, qy, qz, qw) = flange_to_ros_pose(flange, self.tcp)
        msg = PoseStamped()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = "base_link"
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = x, y, z
        o = msg.pose.orientation
        o.x, o.y, o.z, o.w = qx, qy, qz, qw
        self.pose_pub.publish(msg)
        self._last_pose_t = time.monotonic()
        with self._glock:  # servo 작업 영역 판단용 (mm, 응답 수신 시각)
            self.guard.set_pose(stamp.nanoseconds * 1e-9, x * 1e3, y * 1e3, z * 1e3)
        s = self._stats
        s["n"] += 1
        s["rtt"].append(rtt)
        s["wait"].append(wait)

    def _log_stats(self) -> None:
        """5 초마다 pose 발행 주기·RTT·큐 대기 (MC-004 로그)."""
        s = self._stats
        if s["n"]:
            rtt, wait = s["rtt"], s["wait"]
            self.get_logger().info(
                f"pose {s['n'] / 5.0:.1f} Hz, rtt avg {1e3 * sum(rtt) / len(rtt):.1f} "
                f"max {1e3 * max(rtt):.1f} ms, queue wait max {1e3 * max(wait):.1f} ms, "
                f"fail {s['fail']}, skip {s['skip']}"
            )
        elif s["fail"]:
            self.get_logger().warn(f"pose 0 Hz, fail {s['fail']}")
        self._stats = {"n": 0, "fail": 0, "rtt": [], "wait": [], "skip": 0}
        ss = self._sstats
        if ss["rx"] or ss["expire"] or ss["stop"]:
            rej = {k: v for k, v in ss["rej"].items() if v} or 0
            clamp = {k: v for k, v in ss["clamp"].items() if v} or 0
            self.get_logger().info(
                f"servo rx {ss['rx'] / 5.0:.1f} Hz, speedl {ss['pub']}, 거부 {rej}, 자름 {clamp}, "
                f"watchdog {ss['expire']}, "
                f"stop {ss['stop']}, move_stop {ss['ms_ok']} ok / {ss['ms_fail']} fail"
            )
        self._sstats = self._empty_servo_stats()

    # ---------------- /voss/robot/state (voss_msgs.md RobotState) ----------------
    def _on_state_timer(self) -> None:
        """2 Hz: RG2 상태 읽기, 두산 ROBOT_STATE 1 Hz 조회(큐), 판정해 발행."""
        now = time.monotonic()
        if self.rg2.busy:  # 명령·MoveToZone 점유 중엔 그쪽이 상태를 읽는다 → 연결은 정상으로 유지
            self._rg2 = {**self._rg2, "t": now}
        else:
            try:
                w, _b, _g, safety = self.rg2.status()
                self._rg2 = {"ok": True, "width": w, "safety": safety, "t": now}
            except Exception:
                self._rg2 = {**self._rg2, "ok": False, "t": now}
        if not self._ctrl_busy and now - self._ctrl[1] >= 1.0:
            self._ctrl_busy = True
            try:
                self.queue.submit(self.dsr.get_robot_state).add_done_callback(self._ctrl_done)
            except Exception:
                self._ctrl_busy = False
        self._update_state(force=True)

    def _ctrl_done(self, fut) -> None:
        self._ctrl_busy = False
        try:
            self._ctrl = (int(fut.result()), time.monotonic())
        except Exception:
            pass  # 실패는 값이 오래돼 None 이 되는 것으로 드러난다(dsr_ok·TIMEOUT)

    def _update_state(self, force: bool = False) -> None:
        """판정해서, 바뀌었거나 force 면 발행한다. 이벤트(stop·servo·gripper)에서도 부른다."""
        now = time.monotonic()
        ctrl, t_ctrl = self._ctrl
        with self._glock:
            servo_active = self.guard.active
        i = Inputs(
            dsr_ok=not self.dsr.faulted and now - self._last_pose_t < 0.5,
            ctrl_state=ctrl if now - t_ctrl < 3.0 else None,
            disconnected=self.dsr.disconnected,
            rg2_ok=self._rg2["ok"] and now - self._rg2["t"] < 3.0,
            rg2_safety=self._rg2["safety"],
            servo_active=servo_active,
            gripper_busy=self.rg2.busy,
            zone_action=self._zone_action,
            stopped=self.stopped,
            last_alarm=self.dsr.last_alarm,
        )
        st = decide(i)
        with self._slock:
            changed = st.key() != self._state_key
            if not (changed or force):
                return
            self._state_key = st.key()
        m = RobotState()
        m.header.stamp = self.get_clock().now().to_msg()
        m.header.frame_id = "base_link"
        m.connected, m.state, m.action, m.error_code, m.detail = (
            st.connected,
            st.state,
            st.action,
            st.error_code,
            st.detail,
        )
        m.gripper_width_mm = float(self._rg2["width"])
        self.state_pub.publish(m)
        if changed:
            self.get_logger().info(
                f"RobotState {st.state} connected={st.connected} action={st.action or '-'} "
                f"error={st.error_code or '-'} ({st.detail})"
            )

    # ---------------- MoveToZone (voss_msgs.md) ----------------
    def _on_move_to_zone(self, req, res):
        """PLACE: 구역 칸에 놓고 OBSERVE 로 돌아온 뒤 응답(placed_stamp = RG2 개방 완료). OBSERVE·VIEW: 이동만.
        실패 message: BUSY / INVALID / NOT_CONFIGURED / LIMIT(컨트롤러 알람) / TIMEOUT / GRIP_FAIL /
        RETURN_FAILED(개방 후 복귀 실패, placed_stamp 채움) / STOPPED(stop 이 끊음, 개방 후면 placed_stamp 채움)."""
        zone, mode = req.zone.strip().upper(), req.mode.strip().upper()
        res.placed_stamp = TimeMsg()
        t0 = time.monotonic()

        def fail(msg: str):
            res.ok, res.message = False, msg
            kind = "PLACE" if mode in ("", "PLACE") and zone != "OBSERVE" else (mode or "MOVE")
            self.get_logger().warn(f"move_to_zone {zone} 칸 {req.slot} {kind} → {msg}")
            return res

        if mode not in ("", "PLACE", "VIEW", "PICK"):
            return fail(f"INVALID: mode {req.mode}")
        if zone == "OBSERVE" and mode:
            return fail('INVALID: OBSERVE 는 mode "" 만 (이동만, #96)')
        if mode == "PICK":
            return fail("NOT_CONFIGURED: PICK 은 아직 구현 전 (10/13 재확인 흐름)")
        place = mode in ("", "PLACE") and zone != "OBSERVE"
        stage = None
        label = "PLACE" if place else (mode or "MOVE")
        if zone == "OBSERVE":
            if len(self.observe) != 6:
                return fail("NOT_CONFIGURED: observe_pose 없음")
            target = list(self.observe)
        elif zone not in self.zones:
            return fail(f"INVALID: zone {req.zone}")
        elif mode == "VIEW":
            if self.zones[zone]["view"] is None:
                return fail(f"NOT_CONFIGURED: zones.{zone}.view_pose 가 null")
            target = list(self.zones[zone]["view"])
        else:
            zc = self.zones[zone]
            if zc["pose"] is None or zc["grid"] is None:
                return fail(f"NOT_CONFIGURED: zones.{zone}.pose·grid")
            try:
                target = slot_pose(zc["pose"], zc["grid"], int(req.slot))
                stage = slot_pose(zc["pose"], zc["grid"], 0)  # 트레이 안 이동의 출입구(−X 끝 칸)
            except ValueError as e:
                return fail(f"INVALID: {e}")
        # 자원: 모션(servo·MoveToZone)과 RG2(PLACE 는 함께 점유). 같은 자원 두 번째 요청은 BUSY
        if not self._mlock.acquire(blocking=False):
            return fail("BUSY: move_to_zone 진행 중")
        held = False
        try:
            # belt_servo 는 goal 결과를 낸 뒤 0 을 zero_hold_s(0.5 s) 더 보내고 끊는다 → watchdog 200 ms 뒤 끝.
            # 결과 직후 오는 PLACE 가 BUSY 로 튕기지 않게 그동안(최대 servo_settle_s) 기다린다(#109, 10/08)
            deadline = time.monotonic() + self.servo_settle_s
            while True:
                with self._glock:
                    if not self.guard.active:
                        self.guard.motion_busy = True
                        break
                if time.monotonic() >= deadline:
                    return fail("BUSY: servo_cmd 추종 중")
                time.sleep(0.02)
            if place:
                if not self.rg2.try_hold():
                    return fail("BUSY: gripper 동작 중")
                held = True
            self._abort.clear()
            self.stopped = False
            self._zone_action = f"MOVE_TO_ZONE:{zone}"
            self._update_state()
            self.get_logger().info(f"move_to_zone {zone} 칸 {req.slot} {label} 시작")
            placed = None
            try:
                self._run_path(target, stage)
                if place:
                    g = self.rg2.command_held(self.pre_open, self.grip_force)
                    if not g.ok:
                        return fail(f"GRIP_FAIL: 개방 {g.message}")
                    placed = self.get_clock().now()
                    res.placed_stamp = placed.to_msg()
                    try:
                        self._run_path(list(self.observe), stage)
                    except _ZoneError as e:
                        return fail(f"RETURN_FAILED: {e}")
            except _ZoneError as e:
                return fail(str(e))
            res.ok, res.message = True, "OK"
            self.get_logger().info(
                f"move_to_zone {zone} 칸 {req.slot} {label} → OK, {time.monotonic() - t0:.1f} s"
            )
            return res
        finally:
            if held:
                self.rg2.release()
            with self._glock:
                self.guard.motion_busy = False
            self._zone_action = ""
            self._mlock.release()
            self._update_state()

    def _travel_z(self, xy_pose, sol: int, min_tcp_z: float | None = None) -> float | None:
        """xy_pose(플랜지) 의 x·y 위에서 safe_z 부터 10 mm 씩 내려가며, 지금 관절 배치로 풀리고 J3 여유가 있는
        가장 높은 플랜지 z. TCP z 가 min_tcp_z(기본 최저 이동 높이)보다 낮아지면 None. ikin 은 한 번씩 큐로
        보낸다(그 사이 pose 읽기가 끊기지 않게)."""
        floor = self.min_travel_tcp_z if min_tcp_z is None else min_tcp_z
        z = self.safe_z
        while True:
            tcp = flange_to_tcp([xy_pose[0], xy_pose[1], z, *xy_pose[3:]], self.tcp)
            if tcp[2] < floor - 0.5:  # 툴 길이 246.642 라 10 mm 단계가 TCP 69.96 처럼 떨어진다
                return None
            if self._ik_ok(tcp, sol):
                return z
            z -= 10.0

    def _ik_ok(self, tcp, sol: int) -> bool:
        """TCP posx 가 지금 관절 배치(sol)로 풀리고 J3 여유가 있는지."""
        j = self.queue.submit(lambda: self.dsr.ikin(tcp, sol)).result(timeout=3.0)
        return j is not None and abs(j[2]) >= self.min_j3_deg

    def _in_tray(self, slot_flange, stage, sol: int):
        """slot 위로 TCP ≥ 최저 이동 높이가 안 나올 때: (트레이 안 높이 플랜지 z, 칸 0 위 이동 높이) 또는 None."""
        if stage is None or all(
            abs(a - b) < 0.5 for a, b in zip(slot_flange[:2], stage[:2], strict=True)
        ):
            return None
        zi = self._travel_z(slot_flange, sol, self.min_in_tray_tcp_z)
        zs = self._travel_z(stage, sol)
        return None if zi is None or zs is None else (zi, zs)

    def _tray_stage(self, flange):
        """flange x·y 가 들어 있는 구역 트레이(안쪽 215 × 145 mm, measurements #6)의 칸 0, 없으면 None."""
        for zc in self.zones.values():
            if zc["pose"] and zc["grid"]:
                p = zc["pose"]
                if abs(flange[0] - p[0]) <= 107.5 and abs(flange[1] - p[1]) <= 72.5:
                    return slot_pose(p, zc["grid"], 0)
        return None

    def _run_path(self, target_flange, stage=None) -> None:
        """현재 플랜지 → 목표: 수직 상승 → 수평 → 수직 하강, 단계마다 도착을 pose 로 확인.
        수평 이동 높이 = safe_z 와, 출발·도착 x·y 에서 닿는 최고 높이 중 낮은 것. 목표 자세 자체도 풀리는지
        움직이기 전에 확인한다. 먼 칸(출발·도착) 위로 최저 이동 높이가 안 나오면 stage(같은 구역 칸 0) 를
        거쳐 트레이 안에서만 낮게 옆으로 간다. 자세는 늘 수직(구역 자세 그대로)."""
        try:
            cur, sol = self.queue.submit(
                lambda: (self.dsr.get_flange_posx(), self.dsr.current_solution_space())
            ).result(timeout=5.0)
            if not self._ik_ok(flange_to_tcp(target_flange, self.tcp), sol):
                raise _ZoneError("LIMIT: 목표 자세에 팔이 닿지 않음 (구역·칸 위치 확인)")
            z0, z1 = self._travel_z(cur, sol), self._travel_z(target_flange, sol)
            pre, post = [], []
            start, end = cur, target_flange
            if z0 is None and stage is None:
                stage = self._tray_stage(cur)  # 트레이 안에 멈춘 뒤 OBSERVE 복귀 등
            if z0 is None and (t := self._in_tray(cur, stage, sol)) is not None:
                zi, z0 = t  # 놓은 칸에서 트레이 안 높이로 올라가 칸 0 위로 옮긴 뒤 거기서 출발
                low = [cur[0], cur[1], zi, *cur[3:]]
                start = [stage[0], stage[1], zi, *cur[3:]]
                pre = [("rise_in_tray", low)] if cur[2] < zi - 0.5 else []
                pre.append(("to_stage", start))
            if z1 is None and (t := self._in_tray(target_flange, stage, sol)) is not None:
                zi, z1 = t  # 칸 0 위로 내려와 트레이 안 높이로 목표 칸 위까지 옮긴 뒤 하강
                end = [stage[0], stage[1], zi, *target_flange[3:]]
                post = [("in_tray", [target_flange[0], target_flange[1], zi, *target_flange[3:]])]
                post.append(("descend", list(target_flange)))
        except _ZoneError:
            raise
        except Exception as e:  # 큐 응답 없음
            raise _ZoneError(f"TIMEOUT: 경로 계산 {e}") from e
        if z0 is None or z1 is None:
            where = "출발" if z0 is None else "도착"
            raise _ZoneError(
                f"LIMIT: {where} 위에서 TCP z ≥ {self.min_travel_tcp_z:.0f} mm 로 수평 이동할 수 없다"
                f" (트레이 안 TCP ≥ {self.min_in_tray_tcp_z:.0f} 도 안 됨 — 팔이 닿지 않음)"
            )
        hz = min(z0, z1)
        if hz < self.safe_z - 0.5:
            self.get_logger().info(
                f"수평 이동 높이 플랜지 z {hz:.1f} (TCP {hz - self.safe_z + 200:.0f}) — safe_z 에서 안 닿음"
            )
        if pre or post:
            zi = (post or pre)[0][1][2]
            self.get_logger().info(
                f"트레이 안 이동: 칸 0 위 거쳐 TCP {zi - self.safe_z + 200:.0f} 높이로 옆으로"
            )
        steps = pre + plan_move(start, end, hz) + post
        for name, step in steps:
            tcp = flange_to_tcp(step, self.tcp)
            seq0 = self.dsr.alarm_seq
            try:
                self.queue.submit(
                    lambda t=tcp: self.dsr.move_line_async(t, self.zone_vel, self.zone_acc)
                ).result(timeout=2.0)
            except Exception as e:
                raise _ZoneError(f"TIMEOUT: move_line({name}) {e}") from e
            self._wait_arrive(name, tcp[:3], seq0)

    def _wait_arrive(self, name: str, tcp_xyz, seq0: int) -> None:
        with self._glock:
            p = self.guard._pose
        start = p[1:] if p else tcp_xyz
        dist = sum((a - b) ** 2 for a, b in zip(start, tcp_xyz, strict=True)) ** 0.5
        deadline = time.monotonic() + dist / max(self.zone_vel[0], 1.0) + 8.0
        still = None
        while time.monotonic() < deadline:
            if self._abort.is_set():
                raise _ZoneError(f"STOPPED: {name} 중 stop")
            if self.dsr.alarm_seq != seq0:
                raise _ZoneError(f"LIMIT: {name} 중 알람 {self.dsr.last_alarm}")
            with self._glock:
                p = self.guard._pose
            fresh = p is not None and self._now() - p[0] < 0.3
            # 3 mm: 팔을 거의 다 뻗은 자세(J3 ≈ 18°)에서 move_line 이 1.1 mm 덜 가고 멈췄다(10/08 HOLD 칸 1)
            if fresh and sum((a - b) ** 2 for a, b in zip(p[1:], tcp_xyz, strict=True)) < 9.0:
                still = still or time.monotonic()
                if time.monotonic() - still > 0.3:
                    return
            else:
                still = None
            time.sleep(0.02)
        raise _ZoneError(f"TIMEOUT: {name} 도착 안 함")

    # ---------------- RG2 gripper (ADR-0005) ----------------
    def _on_gripper(self, req, res):
        """응답은 RG2 busy 해제(동작 완료) 뒤. 동작 중 두 번째 요청은 BUSY (topics.md 자원 규칙)."""
        t0 = time.monotonic()
        threading.Timer(0.05, self._update_state).start()  # action GRIPPER 를 바로 알린다
        r = self.rg2.command(float(req.width), float(req.force))
        dt = time.monotonic() - t0
        if r.width_actual:
            self._rg2 = {**self._rg2, "width": float(r.width_actual)}
        self._update_state()
        res.ok, res.width_actual, res.grip_detected, res.message = (
            r.ok,
            float(r.width_actual),
            r.grip_detected,
            r.message,
        )
        line = (
            f"gripper 요청 {req.width:.1f} mm·{req.force:.1f} N → {r.message}, "
            f"폭 {r.width_actual:.1f} mm, grip {r.grip_detected}, {1e3 * dt:.0f} ms"
        )
        # rclpy 는 같은 호출 위치에서 로그 단계를 바꾸면 예외를 낸다 → 호출을 나눈다
        if r.ok:
            self.get_logger().info(line)
        else:
            self.get_logger().warn(line)
        return res

    # ---------------- servo_cmd → speedl (ADR-0010) ----------------
    @staticmethod
    def _empty_servo_stats() -> dict:
        return {
            "rx": 0,
            "pub": 0,
            "rej": {"stop": 0, "old": 0, "no_pose": 0, "busy": 0},
            "clamp": {"speed": 0, "z_min": 0, "x_min": 0, "x_max": 0, "angular": 0},
            "expire": 0,
            "stop": 0,
            "ms_ok": 0,
            "ms_fail": 0,
        }

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_servo_cmd(self, msg: TwistStamped) -> None:
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        lin, ang = msg.twist.linear, msg.twist.angular
        with self._glock:
            r = self.guard.on_cmd(self._now(), stamp, (lin.x, lin.y, lin.z), (ang.x, ang.y, ang.z))
        ss = self._sstats
        ss["rx"] += 1
        if r.vel_mm_s is None:
            ss["rej"][r.reason] += 1  # 토픽이라 응답 대신 무시·로그 (topics.md 자원 규칙)
            self.get_logger().warn(f"servo_cmd 거부: {r.reason}", throttle_duration_sec=2.0)
            return
        for c in r.clamps:
            ss["clamp"][c] += 1
        if r.clamps:
            self.get_logger().warn(f"servo_cmd 자름: {r.clamps}", throttle_duration_sec=2.0)
        self.dsr.speedl(r.vel_mm_s, self.servo_acc)
        ss["pub"] += 1
        if self.stopped or not self._was_active:
            self.stopped = False  # 새 모션 → STOPPED 해제
            self._update_state()
        self._was_active = True

    def _on_servo_tick(self) -> None:
        with self._glock:
            action, vel = self.guard.on_tick(self._now())
        if action == "clamp":  # 명령 사이에 한계에 닿음 → 자른 속도로 바로 다시 보낸다
            self.dsr.speedl(vel, self.servo_acc)
            self._sstats["pub"] += 1
        elif action == "expire":
            self._was_active = False
            self._update_state()
            self._sstats["expire"] += 1
            self.get_logger().warn("servo_cmd 끊김(watchdog) → 0 속도 + move_stop")
            self._halt("watchdog")

    def _halt(self, why: str, done=None) -> None:
        """① 속도 0 speedl ② 이어서 항상 move_stop (정지 판별 안 함, ADR-0010 조건 2·#53 MC-014)."""
        self.dsr.speedl([0.0, 0.0, 0.0], self.servo_acc)

        def finished(ok: bool, message: str) -> None:
            self._sstats["ms_ok" if ok else "ms_fail"] += 1
            if not ok:
                self.get_logger().error(f"move_stop 실패({why}): {message}")
            if done is not None:
                done(ok, message)

        self.dsr.move_stop_async(finished)

    def _on_stop(self, _req, res):
        """/voss/robot/stop: 멱등. 이전 stamp 의 servo_cmd 를 버리고 0 속도 + move_stop.
        success = move_stop 정상 응답, 아니면 message = TIMEOUT / DEVICE_ERROR (topics.md, #53 MC-014)."""
        with self._glock:
            self.guard.stop(self._now())
        self._was_active = False
        self.stopped = True
        self._abort.set()  # 진행 중 MoveToZone 을 끊는다 → STOPPED
        self._update_state()
        self._sstats["stop"] += 1
        ev, out = threading.Event(), {}

        def done(ok: bool, message: str) -> None:
            out.update(ok=ok, message=message)
            ev.set()

        self._halt("stop", done)
        ev.wait(5.0)  # move_stop_async 가 자체 타임아웃으로 반드시 부른다
        res.success = bool(out.get("ok", False))
        res.message = out.get("message", "TIMEOUT")
        self.get_logger().info(f"/voss/robot/stop → {res.message}")
        return res

    def halt_on_exit(self) -> threading.Event | None:
        """종료 직전: 움직이는 중이었으면 0 속도 + move_stop. 응답 대기용 Event 를 돌려준다(없으면 None).
        이때 executor 는 이미 멈춰 있어 응답 처리는 main() 이 spin_once 로 돌린다(10/08 F-04: 안 돌리면 TIMEOUT)."""
        with self._glock:
            moving = self.guard.active
            self.guard.stop(self._now())
        if not moving:
            return None
        self.get_logger().warn("종료 중 servo 활성 → 0 속도 + move_stop")
        ev = threading.Event()

        def done(ok: bool, message: str) -> None:
            if ok:
                self.get_logger().info("종료 정지: move_stop OK")
            ev.set()

        self._halt("exit", done)
        return ev

    def destroy_node(self) -> None:
        self.queue.close()  # 대기 작업을 버리고 작업 스레드를 끝낸다
        self.rg2.close()
        super().destroy_node()


def main(args=None) -> None:
    # rclpy 기본 SIGINT 처리는 컨텍스트를 먼저 내려 종료 때 0 속도·move_stop 을 못 보낸다.
    # 그래서 SIGINT 는 KeyboardInterrupt 로 받고, 정지 명령을 보낸 뒤 직접 내린다.
    rclpy.init(args=args, signal_handler_options=rclpy.signals.SignalHandlerOptions.NO)
    node = RobotGatewayNode()
    executor = MultiThreadedExecutor(
        num_threads=6
    )  # 두산 응답 콜백·긴 서비스(MoveToZone)가 따로 돌아야 한다
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Ctrl-C·launch 종료는 정상 종료
    finally:
        try:
            # speedl 은 끊겨도 마지막 속도로 계속 간다(ADR-0010) → 먼저 멈추고 move_stop 응답을 받는다
            ev = node.halt_on_exit()
            end = time.monotonic() + 1.0
            while ev is not None and not ev.is_set() and time.monotonic() < end:
                executor.spin_once(timeout_sec=0.05)
            executor.shutdown(timeout_sec=1.0)  # 실행 스레드를 먼저 멈춘 뒤 노드를 정리한다
            node.destroy_node()
        except KeyboardInterrupt:
            pass  # 정리 중 두 번째 Ctrl-C
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
