"""robot_gateway — 인터페이스는 docs/interfaces/topics.md 참조.

두산 서비스는 SerialCallQueue 하나로만 부른다(CLAUDE.md 절대 규칙 3). dry_run 이면 두산·RG2 에
연결하지 않고 관측 자세에서 시작하는 가짜 로봇을 쓴다(개인 PC 개발용, speedl 을 적분해 움직인다).

지금 있는 것: /voss/robot/pose (TCP, base_link), /voss/robot/servo_cmd → speedl_stream(ADR-0010,
만료 watchdog → 0 속도 + 항상 move_stop, TCP z 하한·x 범위·속도 상한), /voss/robot/stop,
/voss/robot/gripper (RG2 Modbus 직접, ADR-0005), /voss/robot/state (RobotState). 다음 단계: move_to_zone.
"""

import threading
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger

from voss_msgs.msg import RobotState
from voss_msgs.srv import Gripper
from voss_robot.call_queue import SerialCallQueue
from voss_robot.doosan import DEFAULT_PREFIX, DoosanError, DryRunDoosan
from voss_robot.geometry import flange_to_ros_pose
from voss_robot.rg2 import DryRunRg2, Rg2
from voss_robot.servo_guard import ServoGuard, ServoParams
from voss_robot.state_logic import Inputs, decide


class RobotGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("robot_gateway")
        # dry_run 기본값 true: 실수로 띄워도 로봇이 움직이지 않게 한다
        self.dry_run = self.declare_parameter("dry_run", True).value
        prefix = self.declare_parameter("dsr_prefix", DEFAULT_PREFIX).value
        rate = self.declare_parameter("pose_rate_hz", 50.0).value
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
            self.dsr = DryRunDoosan(observe)
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
        if not self.rg2.busy:  # 명령 중엔 command() 가 상태를 읽고 있다
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
    executor = MultiThreadedExecutor(num_threads=4)  # 두산 응답 콜백이 따로 돌아야 한다
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
