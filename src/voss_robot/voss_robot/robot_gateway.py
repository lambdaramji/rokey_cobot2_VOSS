"""robot_gateway — 인터페이스는 docs/interfaces/topics.md 참조.

두산 서비스는 SerialCallQueue 하나로만 부른다(CLAUDE.md 절대 규칙 3). dry_run 이면 두산·RG2 에
연결하지 않고 관측 자세에서 시작하는 가짜 로봇을 쓴다(개인 PC 개발용, speedl 을 적분해 움직인다).

지금 있는 것: /voss/robot/pose (TCP, base_link), /voss/robot/servo_cmd → speedl_stream(ADR-0010,
만료 watchdog → 0 속도 + 항상 move_stop, TCP z 하한·x 범위·속도 상한), /voss/robot/stop,
/voss/robot/gripper (RG2 Modbus 직접, ADR-0005), /voss/robot/state (RobotState),
/voss/robot/move_to_zone (PLACE·OBSERVE·VIEW·PICK — PICK 은 재확인 칸에서 집어 이동 높이로, #45).
"""

import math
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
from voss_robot.doosan import DEFAULT_PREFIX, DoosanError, DryRunDoosan, emulator_running
from voss_robot.geometry import (
    controller_tcp_offset,
    flange_to_ros_pose,
    flange_to_tcp,
    segment_distance_mm,
    tcp_to_flange,
    tool_yaw_deg,
)
from voss_robot.pose_source import StartupCheck, fresh
from voss_robot.rg2 import DryRunRg2, Rg2
from voss_robot.servo_guard import ServoGuard, ServoParams
from voss_robot.state_logic import Inputs, decide
from voss_robot.zone_motion import (
    SAFE_Z_MM,
    TravelCache,
    pick_grip_ok,
    pick_pose,
    plan_move,
    row_stage_slot,
    search_travel_z,
    slot_pose,
)


class _ZoneError(RuntimeError):
    """MoveToZone 단계 실패. 메시지가 대문자 코드로 시작한다."""


class RobotGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("robot_gateway")
        # dry_run 기본값 true: 실수로 띄워도 로봇이 움직이지 않게 한다
        self.dry_run = self.declare_parameter("dry_run", True).value
        prefix = self.declare_parameter("dsr_prefix", DEFAULT_PREFIX).value
        rate = self.declare_parameter("pose_rate_hz", 50.0).value
        # service(기본) = get_current_tool_flange_posx(응답 수신 시각 stamp). joint_states = /dsr01/joint_states 최신
        # 관절 → fkin(stamp = joint_states 시각) — 10/08 오후 service 값이 0.1 s 마다만 바뀌었다. stamp 의미가 달라
        # box_tracker pose_lag_ms 를 다시 잰 뒤 기본으로 바꾼다(#118 리뷰). 켜도 기동 교차 검사를 통과해야 쓴다
        self.pose_source = str(self.declare_parameter("pose_source", "service").value)
        self._js_check = StartupCheck() if self.pose_source == "joint_states" else None
        # fkin 은 컨트롤러 등록 TCP 기준 → 기동 TCP 확인(_ctrl_tcp)이 잰 오프셋으로 플랜지로 되돌린다.
        # 재기 전(None)에는 교차 검사를 미룬다(등록 없음이면 247 mm 차로 50번 실패가 1 s 만에 난다)
        self._js_off: list[float] | None = None
        self._js_tcp_busy, self._js_tcp_t = False, -1e9
        self._last_stamp_ns = None  # 같은 stamp 재발행 금지(#118 🟡3)
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
            # false = 컨트롤러 TCP 등록이 풀린 상태를 흉내(TCP 확인 시험용, 10/08 18:26 사고)
            self.dsr.tcp_registered = bool(
                self.declare_parameter("dry_run_tcp_registered", True).value
            )
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
            float(a) for a in self.declare_parameter("servo_acc", [100.0, 90.0]).value
        ]  # 각가속 10 → 90 (S2-T17, belt_servo rotate.alpha_dps2 제안 90). 각속도가 0 이면 쓰이지 않는다
        sp = ServoParams(
            lin_acc_mm_s2=self.servo_acc[0],
            watchdog_s=float(self.declare_parameter("servo_watchdog_s", 0.2).value),
            max_speed_mm_s=float(self.declare_parameter("servo_max_speed_mm_s", 100.0).value),
            z_min_mm=float(self.declare_parameter("servo_z_min_mm", 78.0).value),
            x_range_mm=tuple(self.declare_parameter("servo_x_range_mm", [-107.0, 638.0]).value),
            pose_max_age_s=float(self.declare_parameter("servo_pose_max_age_s", 0.1).value),
            pose_latency_s=float(self.declare_parameter("servo_pose_latency_s", 0.06).value),
            # 각속도 통과(S2-T17, topics.md robot_gateway 행). 기본 off = 지금처럼 자른다(시연 라인)
            angular_enable=bool(self.declare_parameter("servo_angular_enable", False).value),
            max_ang_dps=float(self.declare_parameter("servo_max_ang_dps", 60.0).value),
            ang_acc_dps2=self.servo_acc[1],
            yaw_center_deg=tool_yaw_deg(*observe[3:6]) if len(observe) == 6 else None,
            yaw_limit_deg=float(self.declare_parameter("servo_yaw_limit_deg", 100.0).value),
        )
        # joint_states 소스는 stamp 가 관절 읽은 시각이라 응답 지연(60 ms)을 다시 더하지 않는다. belt_servo 하강 상한과
        # 같이 정할 값(#118 리뷰 박병후) — 확인 통과 뒤 이 값으로 바꾼다
        self.servo_latency_js_s = float(
            self.declare_parameter("servo_pose_latency_js_s", 0.02).value
        )
        self.servo_latency_s = sp.pose_latency_s  # service 로 되돌릴 때 다시 쓴다
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
        # 두산은 에뮬레이터(mode:=virtual), RG2 만 가짜 — 에뮬레이터 가상 실험용(#41 박병후). 실기 금지
        self.rg2_dry_run = bool(self.declare_parameter("rg2_dry_run", False).value)
        # 두산 real 인데 RG2 가 가짜인 상태. 기동·RobotState.detail·5 초 로그에 계속 보인다(#139 리뷰 박병후)
        self.rg2_fake_note = (
            "RG2 FAKE(rg2_dry_run)" if self.rg2_dry_run and not self.dry_run else ""
        )
        if self.rg2_fake_note:
            self._require_emulator(prefix)
        if self.dry_run or self.rg2_dry_run:  # 가짜 RG2 에서는 rg2_host·rg2_port 를 쓰지 않는다
            # 가짜 물체 폭(RG2 보고값 mm, 0 이하 = 물체 없음). 닫힘 명령 폭보다 커야 grip_detected —
            # 실측 31 mm 면 파지는 명령 39 → 보고 40.3~40.6 mm(measurements #8)라 40.5 정도를 준다
            obj = float(self.declare_parameter("dry_run_object_mm", 0.0).value)
            self.rg2 = DryRunRg2(object_mm=obj if obj > 0.0 else None)
            if self.rg2_fake_note:
                self.get_logger().warn(
                    "RG2 가짜(rg2_dry_run) — 실제 그리퍼는 움직이지 않는다. 실기에서는 끈다"
                )
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
            # 구역별 트레이 안 이동 최저 TCP z(voss_config zones.<z>.in_tray_tcp_z_mm). 0 = 공통 값
            in_tray = float(self.declare_parameter(f"zones.{z}.in_tray_tcp_z_mm", 0.0).value)
            self.zones[z] = {
                "pose": pose if len(pose) == 6 else None,
                "grid": grid
                if len(grid) in (3, 4, 6, 7) or len(grid) == 7 + int(grid[0])
                else None,
                "view": view if len(view) == 6 else None,
                "in_tray": in_tray if in_tray > 0 else None,
            }
        self.pre_open = float(self.declare_parameter("gripper.pre_open_mm", 90.0).value)
        # 트레이 안에서 여는 폭(PLACE 개방·PICK 확인 실패 후퇴). 없으면 pre_open (voss_config.md gripper)
        self.place_open = float(
            self.declare_parameter("gripper.place_open_mm", self.pre_open).value
        )
        # 트레이에서 집기(PICK) 전 여는 폭(보고값). 옆 줄 박스까지 44.5 mm — 90 이면 핑거가 닿는다. 없으면 pre_open
        self.pick_open = float(self.declare_parameter("gripper.pick_open_mm", self.pre_open).value)
        self.grip_force = float(self.declare_parameter("gripper.force_n", 14.0).value)
        self.grasp_width = float(self.declare_parameter("gripper.grasp_width_mm", 39.0).value)
        # PICK(재확인 칸에서 집기): 놓기 칸 자세 + dz. 놓기 자세는 쥔 박스 밑면 +5 라 핑거 끝은 바닥 약 +13.
        # 10/11 실기 재확인 칸 0: dz 3·0 은 박스 윗모서리(집음 폭 39.9·39.8), −5·−8 은 몸통(40.6), −8 바닥 접촉 없음.
        # 성공 보고폭 범위는 belt_servo hold_width_min/max 와 같은 근거(빈손 최대 38.7, 10/10 쥔 폭 40.6~41.5·회전 최대 43.0)
        # 보고폭으로는 윗모서리 파지를 못 거른다(dz +3 이 39.9·grip True 로 통과) → 안전장치는 dz 다.
        # zones.recheck.pose z 를 다시 교시하면 dz 도 실기로 다시 확인한다(#148 리뷰 박병후)
        self.pick_dz = float(self.declare_parameter("zone_pick_dz_mm", -8.0).value)
        self.pick_width = [
            float(v) for v in self.declare_parameter("zone_pick_width_mm", [39.5, 44.0]).value
        ]
        if len(self.pick_width) != 2 or not self.pick_width[0] < self.pick_width[1]:
            raise RuntimeError(
                f"zone_pick_width_mm 는 [하한, 상한](하한 < 상한): {self.pick_width}"
            )
        self.safe_z = float(self.declare_parameter("zone_safe_z_mm", SAFE_Z_MM).value)
        # 먼 구역(C·HOLD)은 safe_z 에서 팔이 닿지 않는다(10/08 실기 1206). 수평 이동 높이를 구역마다 ikin 으로
        # 낮추되, 이 TCP z 보다 낮아지면 거부한다(박스 밑면 = TCP − 8, 트레이 테두리 ≈ TCP 50 → 약 60 mm 여유)
        self.min_travel_tcp_z = float(
            self.declare_parameter("zone_min_travel_tcp_z_mm", 120.0).value
        )
        # 트레이 안 이동: 먼 칸 위로 TCP 120 이 안 나오면 같은 줄 −X 끝 칸(칸 0·3) 위까지 높게 와서 내려간 뒤
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
        # move_line·ikin 은 컨트롤러 등록 TCP 기준인데 등록은 브링업마다 풀린다. 움직이기 전에 등록 TCP 위치와
        # 플랜지 + tcp_offset_mm 이 이 거리 안인지 본다(10/08 18:26: 등록 없이 OBSERVE → 246 mm 수직 하강)
        self.tcp_check_tol = float(self.declare_parameter("zone_tcp_check_tol_mm", 3.0).value)
        # move_line 은 TCP 직선 이동 — 출발–목표 선분에서 이만큼 벗어나면 move_stop 하고 LIMIT
        self.path_tol = float(self.declare_parameter("zone_path_tol_mm", 15.0).value)
        # 위쪽 모서리 블렌딩 거리(mm). 0 = 모서리마다 멈춤(예전). 상승→수평→하강을 멈추지 않고 잇는다(로컬 10/12)
        self.blend_mm = float(self.declare_parameter("zone_blend_mm", 0.0).value)
        self._cmd_off = list(self.tcp)  # _run_path 가 매번 잰 컨트롤러 TCP 오프셋으로 바꾼다
        # 이동 높이(_travel_z) 결과를 칸별로 다시 쓴다 — 닿지 않는 높이의 ikin 이 큐를 ~100 ms 씩 잡아 경로 계산
        # 2.5 s 동안 pose 가 10 Hz 로 떨어졌다(10/10 C2, #147). 기동 때 관측 자세에 있으면 구역 칸을 미리 계산
        self._tz_cache = (
            TravelCache() if self.declare_parameter("zone_travel_cache", True).value else None
        )
        self._tz_ik = 0  # ikin 호출 수 (미리 계산 로그용)
        self._warm_idle = (
            threading.Event()
        )  # 미리 계산 중엔 비움 → MoveToZone 이 끝날 때까지 기다린다
        self._warm_idle.set()
        self._tcp_note = ""  # RobotState.detail: 컨트롤러 TCP 가 voss_config 와 다를 때
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
            f"MoveToZone 구역 {ready}, safe z {self.safe_z} mm(플랜지), vel {self.zone_vel}, acc {self.zone_acc}, blend {self.blend_mm} mm"
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
        if self.rg2_fake_note:
            mode += f" + {self.rg2_fake_note}"
        self.get_logger().info(
            f"robot_gateway started: {mode}, pose {rate:.0f} Hz, servo watchdog "
            f"{1e3 * sp.watchdog_s:.0f} ms, max {sp.max_speed_mm_s:.0f} mm/s, TCP z ≥ "
            f"{sp.z_min_mm:.1f} mm, x {sp.x_range_mm[0]:.0f}~{sp.x_range_mm[1]:.0f} mm, acc {self.servo_acc}"
        )
        if sp.angular_enable:
            yc = "모름 → 각속도 0" if sp.yaw_center_deg is None else f"{sp.yaw_center_deg:.1f}"
            self.get_logger().warn(
                f"servo angular on · ω ≤ {sp.max_ang_dps:.0f} °/s · α {self.servo_acc[1]:.0f} °/s² · "
                f"yaw {yc} ± {sp.yaw_limit_deg:.0f}° (S2-T17 — 시연 라인에서는 끈다)"
            )
        else:
            self.get_logger().info("servo angular off (각속도는 0 으로 자름)")
        threading.Thread(target=self._startup_tcp_check, daemon=True).start()

    def _require_emulator(self, prefix: str, wait_s: float = 3.0) -> None:
        """rg2_dry_run 은 두산 에뮬레이터에서만. 그래프에 에뮬레이터 노드가 없으면(실기) 기동하지 않는다.

        실 로봇에 가짜 RG2 를 붙이면 개방이 OK 로 보고돼도 손가락이 안 열린다(비상정지 복구 ⑤). 그래프 조회는
        spin 없이 되지만 디스커버리에 시간이 걸려 wait_s 동안 다시 본다."""
        end = time.monotonic() + wait_s
        while True:
            if emulator_running(self.get_node_names_and_namespaces(), prefix):
                return
            if time.monotonic() > end:
                break
            time.sleep(0.2)
        msg = (
            f"rg2_dry_run 거부: 두산 에뮬레이터 노드({prefix.split('/')[1]}/virtual_node)가 없다 — "
            "실기로 보인다. 실기에서는 rg2_dry_run 을 빼고 띄운다(브링업 mode:=virtual 에서만)"
        )
        self.get_logger().fatal(msg)
        raise RuntimeError(msg)

    def _ctrl_tcp(self):
        """컨트롤러 등록 TCP 를 재서 move_line·ikin 에 보낼 오프셋을 정한다. 큐 작업 스레드에서.

        (오프셋 또는 None, 설명, 플랜지, solution space). 등록 = voss_config 면 tcp_offset_mm, 등록이 없으면
        (get_current_posx = 플랜지, 10/08 18:24 브링업 뒤) 0 — 플랜지 좌표로 보낸다. 둘 다 아니면 None(거부)."""
        flange = self.dsr.get_flange_posx()
        ctrl, sol = self.dsr.current_posx()
        off, d_cfg, d_none = controller_tcp_offset(ctrl, flange, self.tcp, self.tcp_check_tol)
        if off is None:
            why = f"voss_config 와 {d_cfg:.0f} mm, 플랜지와 {d_none:.0f} mm 다름"
        elif any(off):
            why = f"voss_config 와 같음 (차 {d_cfg:.1f} mm)"
        else:
            why = f"없음 → 플랜지 좌표로 명령 (차 {d_none:.1f} mm)"
        return off, why, flange, sol

    def _startup_tcp_check(self) -> None:
        """기동 때 한 번: 컨트롤러 TCP 상태를 로그로 알린다(MoveToZone 은 매번 다시 본다)."""
        time.sleep(1.0)  # executor 가 돌기 시작한 뒤
        try:
            off, why, _, _ = self.queue.submit(self._ctrl_tcp).result(timeout=5.0)
        except Exception as e:  # 큐 응답 없음 — pose 쪽 로그가 따로 알린다
            self.get_logger().warn(f"컨트롤러 TCP 확인 못 함: {e}")
            return
        if self.pose_source == "joint_states":
            if off is None:
                self._js_fallback(f"컨트롤러 TCP 를 모름({why})")
            else:
                self._js_off = off
        self._set_tcp_note(off)
        if off is not None:
            self.get_logger().info(f"컨트롤러 TCP 등록 {why}")
            self._prewarm_travel()
        else:
            self.get_logger().error(
                f"컨트롤러 TCP 등록이 {why} — 모르는 TCP 라 MoveToZone 을 거부한다(NOT_CONFIGURED). "
                "펜던트 툴·TCP 를 GripperDA_v1 또는 없음으로"
            )

    def _prewarm_travel(self) -> None:
        """기동 때 한 번: 관측 자세에 있으면 구역 칸·관측·VIEW 의 이동 높이를 미리 찾아 둔다(#147).
        그동안 큐가 ikin 으로 차서 pose 가 낮다 — MoveToZone 과 같이 모션을 잡고 state BUSY(action PREWARM)로
        둔다: servo_cmd 는 busy 로 거부, sort_manager 는 준비 안 됨(#153 리뷰). MoveToZone 요청은 끝날 때까지 기다린다."""
        if self._tz_cache is None or len(self.observe) != 6:
            return
        if not self._mlock.acquire(blocking=False):
            return
        self._warm_idle.clear()
        t0, n0 = time.monotonic(), self._tz_ik
        try:
            with self._glock:
                servo = self.guard.active
                if not servo:
                    self.guard.motion_busy = True
            if servo:
                self.get_logger().info("이동 높이 미리 계산 안 함: servo_cmd 추종 중")
                return
            self._zone_action = "PREWARM"
            self._update_state()
            off, _why, cur, sol = self.queue.submit(self._ctrl_tcp).result(timeout=5.0)
            if off is None:
                return
            if max(abs(a - b) for a, b in zip(cur[:3], self.observe[:3], strict=True)) > 30.0:
                self.get_logger().info(
                    "이동 높이 미리 계산 안 함: 관측 자세가 아님(MoveToZone 때 칸마다 찾음)"
                )
                return
            self._cmd_off = off
            targets = [list(self.observe)]
            slots = 0
            for zc in self.zones.values():
                if zc["view"] is not None:
                    targets.append(list(zc["view"]))
                if not (zc["pose"] and zc["grid"]):
                    continue
                stage = slot_pose(zc["pose"], zc["grid"], 0)
                for k in range(int(zc["grid"][0]) * int(zc["grid"][1])):
                    t = slot_pose(zc["pose"], zc["grid"], k)
                    slots += 1
                    if self._travel_z(t, sol) is None:
                        self._in_tray(t, stage, sol)
            for t in targets:
                self._travel_z(t, sol)
            self.get_logger().info(
                f"이동 높이 미리 계산: 칸 {slots}개, ikin {self._tz_ik - n0}회, "
                f"{time.monotonic() - t0:.1f} s (저장 {len(self._tz_cache)}개)"
            )
        except Exception as e:  # 큐 응답 없음 등 — MoveToZone 때 다시 찾는다
            self.get_logger().warn(f"이동 높이 미리 계산 실패: {e}")
        finally:
            with self._glock:
                self.guard.motion_busy = False
            self._zone_action = ""
            self._mlock.release()
            self._warm_idle.set()
            self._update_state()

    def _set_tcp_note(self, off) -> None:
        """잰 컨트롤러 TCP 를 RobotState.detail 에 남긴다(같음이면 비움)."""
        if off is None:
            note = "TCP 등록 모름(MoveToZone 거부)"
        elif any(off):
            note = ""
        else:
            note = "TCP 등록 없음(플랜지 모드 — 펜던트 공간 제한이 핑거 끝을 못 막음)"
        if note != self._tcp_note:
            self._tcp_note = note
            self._update_state()

    def _js_fallback(self, why: str) -> None:
        """joint_states pose 를 그만 쓰고 service(등록 TCP 와 무관)로 되돌린다."""
        if self.pose_source != "joint_states":
            return
        self.pose_source = "service"
        self._js_check = None
        with self._glock:
            self.guard.p.pose_latency_s = self.servo_latency_s
        self.get_logger().error(f"pose_source joint_states → service: {why}")

    def _js_tcp_done(self, fut) -> None:
        """joint_states 사용 중 2 s 마다: 컨트롤러 등록 TCP 가 바뀌면(펜던트 조작) fkin 이 틀어지므로 service 로.
        움직이는 중엔 두 서비스 값이 0.1 s 어긋날 수 있어 20 mm 로 본다(두 후보는 247 mm 떨어져 헷갈리지 않음)."""
        self._js_tcp_busy = False
        try:
            ctrl, flange = fut.result()
        except Exception:
            return
        off = controller_tcp_offset(ctrl, flange, self.tcp, 20.0)[0]
        if self._js_off is not None and off != self._js_off:
            self._js_fallback(f"컨트롤러 등록 TCP 가 바뀜 ({self._js_off} → {off})")

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
            if js is None or not fresh(now.nanoseconds, js[1], 0.1):
                raise DoosanError("joint_states 없음·0.1 s 넘게 오래됨")
            if self._js_check is not None:  # 기동 교차 검사 중: 서비스 플랜지를 내고 비교만 한다
                flange = self.dsr.get_flange_posx()
                if self._js_off is not None:
                    js_flange = tcp_to_flange(self.dsr.fkin_tcp(js[0]), self._js_off)
                    self._judge_js(self._js_check.feed(js_flange, flange))
                return self.get_clock().now(), flange, time.monotonic() - t0, self.queue.last_wait_s
            js_flange = tcp_to_flange(self.dsr.fkin_tcp(js[0]), self._js_off)
            if js[1] == self._last_stamp_ns:
                return None  # 새 관절 값이 아직 없다 → 같은 stamp 재발행 금지
            self._last_stamp_ns = js[1]
            stamp = Time(nanoseconds=js[1], clock_type=now.clock_type)  # joint_states 측정 시각
            return stamp, js_flange, time.monotonic() - t0, self.queue.last_wait_s
        flange = self.dsr.get_flange_posx()
        stamp = self.get_clock().now()  # MC-004: 응답 수신 시각 (측정 시각 아님)
        return stamp, flange, time.monotonic() - t0, self.queue.last_wait_s

    def _judge_js(self, verdict: str) -> None:
        """기동 교차 검사 결과: 통과면 joint_states 로, 실패면 service 로 되돌리고 ERROR."""
        c = self._js_check
        if verdict == "pass":
            self._js_check = None
            with self._glock:
                self.guard.p.pose_latency_s = self.servo_latency_js_s
            self.get_logger().info(
                f"pose_source joint_states 확인: 서비스 플랜지와 {c.last_diff_mm:.2f} mm → 사용 "
                f"(guard pose 지연 {self.servo_latency_js_s * 1e3:.0f} ms)"
            )
        elif verdict == "fail":
            self._js_check = None
            self.pose_source = "service"
            self.get_logger().error(
                f"pose_source joint_states 거부: 서비스 플랜지와 {c.last_diff_mm:.1f} mm 차이가 {c.fails}번 연속 "
                "— 컨트롤러 등록 TCP 를 잘못 쟀거나 바뀌었을 수 있다. service 로 되돌림"
            )

    def _pose_done(self, fut) -> None:
        self._pose_busy = False
        try:
            r = fut.result()
            if r is None:
                self._stats["skip"] += 1  # 같은 joint_states stamp — 발행하지 않는다
                return
            stamp, flange, rtt, wait = r
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
            self.guard.set_pose(
                stamp.nanoseconds * 1e-9, x * 1e3, y * 1e3, z * 1e3, tool_yaw_deg(*flange[3:6])
            )
        s = self._stats
        s["n"] += 1
        s["rtt"].append(rtt)
        s["wait"].append(wait)

    def _log_stats(self) -> None:
        """5 초마다 pose 발행 주기·RTT·큐 대기 (MC-004 로그)."""
        if self.rg2_fake_note:  # 기동 한 줄은 스크롤로 사라진다 → 계속 보이게
            self.get_logger().warn(f"{self.rg2_fake_note} — 실제 그리퍼는 움직이지 않는다")
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
        if (
            self.pose_source == "joint_states"
            and self._js_off is not None
            and not self._js_tcp_busy
            and now - self._js_tcp_t >= 2.0
        ):
            self._js_tcp_busy, self._js_tcp_t = True, now
            try:
                self.queue.submit(
                    lambda: (self.dsr.current_posx()[0], self.dsr.get_flange_posx())
                ).add_done_callback(self._js_tcp_done)
            except Exception:
                self._js_tcp_busy = False
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
            tcp_note=self._tcp_note,
            rg2_note=self.rg2_fake_note,
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
        PICK: 열고 → 칸 위 파지 높이로 → 닫아 확인 → 든 채 수직 상승(이동 높이)에서 응답. 확인 실패면 그 자리에서
        열고(박스는 칸에 그대로) 올라간 뒤 GRIP_FAIL. placed_stamp 0.
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

        if mode not in ("", "PLACE", "VIEW", "PICK", "DROP"):
            return fail(f"INVALID: mode {req.mode}")
        if zone == "OBSERVE" and mode:
            return fail('INVALID: OBSERVE 는 mode "" 만 (이동만, #96)')
        place = mode in ("", "PLACE", "DROP") and zone != "OBSERVE"
        # DROP = 놓고 OBSERVE 로 돌아가지 않고 칸 위로 올라가 멈춘다 — 팔레트에 놓은 뒤 바로 다음 박스 집기(BRD TR-PAL-06)
        drop = mode == "DROP"
        pick = mode == "PICK"
        if pick and zone not in (
            "A",
            "B",
            "C",
            "RECHECK",
            "HOLD",
        ):  # 재확인 칸(MC-017) + 팔레타이징: 구역 트레이에서 집어 팔레트로(BRD TR-PAL-05)
            return fail("INVALID: PICK 은 A·B·C·RECHECK·HOLD 만 (팔레트·OBSERVE 에서는 집지 않음)")
        stage, via = None, None
        in_tray_z = None  # 이 구역의 트레이 안 최저 높이(없으면 공통 zone_min_in_tray_tcp_z_mm)
        label = ("DROP" if drop else "PLACE") if place else (mode or "MOVE")
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
                # 트레이 안 이동의 출입구 = 같은 Y 줄의 −X 끝 칸(C 칸 2 → 칸 0, 칸 5 → 칸 3)
                via = row_stage_slot(zc["grid"], int(req.slot))
                stage = slot_pose(zc["pose"], zc["grid"], via)
                in_tray_z = zc["in_tray"]
                if pick:
                    target = pick_pose(target, self.pick_dz)
            except ValueError as e:
                return fail(f"INVALID: {e}")
        # 자원: 모션(servo·MoveToZone)과 RG2(PLACE·PICK 은 함께 점유). 같은 자원 두 번째 요청은 BUSY
        self._warm_idle.wait(30.0)  # 기동 직후 이동 높이 미리 계산 중이면 끝날 때까지
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
            if place or pick:
                if not self.rg2.try_hold():
                    return fail("BUSY: gripper 동작 중")
                held = True
            self._abort.clear()
            self.stopped = False
            self._zone_action = f"MOVE_TO_ZONE:{zone}"
            self._update_state()
            gate = f" (출입구 칸 {via})" if via is not None else ""
            self.get_logger().info(f"move_to_zone {zone} 칸 {req.slot} {label} 시작{gate}")
            placed = None
            try:
                rise = (
                    self._pick_lift(target, stage) if drop else None
                )  # 놓은 뒤 올라갈 곳(움직이기 전에)
                if pick:
                    # 상승 높이를 쥐기 전에 구한다 — 안 풀리면 쥔 채 멈추는 대신 움직이기 전에 거부(#148 리뷰 박병후)
                    lift = self._pick_lift(target, stage)
                    # 내려가기 전에 연다(VIEW·OBSERVE 높이 — 아래에 아무것도 없다)
                    try:
                        w, _busy, grip, _safety = self.rg2.status()
                    except Exception as e:
                        return fail(f"GRIP_FAIL: RG2 상태 읽기 {e}")
                    if grip:  # 무언가를 쥔 채면 사전 개방에서 떨어뜨린다(자동 개방 금지, MC-014)
                        return fail(f"GRIP_FAIL: 이미 쥐고 있다(폭 {w:.1f} mm) — 열지 않고 거부")
                    # 트레이 안 집기 개방 = pick_open (3×2 에서 90 이면 옆 줄 박스에 핑거가 닿는다, 10/12 실기 50)
                    g = self.rg2.command_held(self.pick_open, self.grip_force)
                    if not g.ok:
                        return fail(f"GRIP_FAIL: 사전 개방 {g.message}")
                self._run_path(target, stage, in_tray_z)
                if pick:
                    g = self.rg2.command_held(self.grasp_width, self.grip_force)
                    why = pick_grip_ok(
                        g.ok,
                        g.grip_detected,
                        g.width_actual,
                        self.pick_width[0],
                        self.pick_width[1],
                    )
                    if why:
                        back = self._pick_retreat(lift, stage, in_tray_z)
                        return fail(f"GRIP_FAIL: 집기 확인 실패 — {why}{back}")
                    self.get_logger().info(
                        f"move_to_zone {zone} 칸 {req.slot} PICK 집음: 폭 {g.width_actual:.1f} mm, grip True"
                    )
                    # 든 채 수직 상승. 실패하면 박스를 든 채 멈춘다(자동 개방 금지, MC-014)
                    try:
                        self._run_path(lift, stage, in_tray_z)
                    except _ZoneError as e:
                        return fail(f"{e} (박스를 쥔 채 멈춤)")
                if place:
                    g = self.rg2.command_held(self.place_open, self.grip_force)
                    if not g.ok:
                        return fail(f"GRIP_FAIL: 개방 {g.message}")
                    placed = self.get_clock().now()
                    res.placed_stamp = placed.to_msg()
                    try:
                        self._run_path(rise if drop else list(self.observe), stage, in_tray_z)
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

    def _lift_pose(self, flange):
        """flange x·y 위 이동 높이(_travel_z: safe_z 부터 닿는 곳까지). 움직이기 전에 부른다 — 컨트롤러 TCP 등록과
        관절 배치를 재고(_run_path 와 같은 확인), ikin 명령 좌표 기준(_cmd_off)을 맞춘다."""
        try:
            off, why, _, sol = self.queue.submit(self._ctrl_tcp).result(timeout=5.0)
        except Exception as e:  # 큐 응답 없음
            raise _ZoneError(f"TIMEOUT: 상승 높이 계산 {e}") from e
        if off is None:
            raise _ZoneError(f"NOT_CONFIGURED: 컨트롤러 TCP 등록이 {why}")
        self._cmd_off = off
        z = self._travel_z(flange, sol)
        if z is None:
            raise _ZoneError(
                f"LIMIT: 칸 위로 TCP z ≥ {self.min_travel_tcp_z:.0f} mm 까지 올라갈 수 없다"
            )
        return [flange[0], flange[1], z, *flange[3:]]

    def _pick_lift(self, target, stage):
        """PICK 뒤 올라갈 자세: 칸 바로 위(TCP ≥ 120)가 안 되면 출입구 칸 위(트레이 안으로 나와 올라감 — C 칸 2·5).
        움직이기 전에 구한다."""
        try:
            return self._lift_pose(target)
        except _ZoneError:
            if stage is None or all(
                abs(a - b) < 0.5 for a, b in zip(target[:2], stage[:2], strict=True)
            ):
                raise
            return self._lift_pose(stage)

    def _pick_retreat(self, lift, stage=None, in_tray_z=None) -> str:
        """PICK 확인 실패: 파지 높이(박스 밑면 = 바닥)에서 열어 박스를 칸에 그대로 두고 lift 까지 올라간다.
        문제가 생기면 그 자리에 멈추고 설명을 돌려준다(GRIP_FAIL 메시지 뒤에 붙임)."""
        g = self.rg2.command_held(self.place_open, self.grip_force)
        if not g.ok:
            return f" / 개방 실패 {g.message} — 칸 위 파지 높이에 멈춤"
        try:
            self._run_path(lift, stage, in_tray_z)
        except _ZoneError as e:
            return f" / 열었으나 상승 실패 {e}"
        return " / 열고 상승함(박스는 칸에 그대로)"

    def _travel_z(self, xy_pose, sol: int, min_tcp_z: float | None = None) -> float | None:
        """xy_pose(플랜지) 의 x·y 위에서 safe_z 부터 10 mm 씩 내려가며, 지금 관절 배치로 풀리고 J3 여유가 있는
        가장 높은 플랜지 z. TCP z 가 min_tcp_z(기본 최저 이동 높이)보다 낮아지면 None. ikin 은 한 번씩 큐로
        보낸다(그 사이 pose 읽기가 끊기지 않게)."""
        floor = self.min_travel_tcp_z if min_tcp_z is None else min_tcp_z

        def at(z):
            return [xy_pose[0], xy_pose[1], z, *xy_pose[3:]]

        ladder, z = [], self.safe_z
        # 툴 길이 246.642 라 10 mm 단계가 TCP 69.96 처럼 떨어진다
        while flange_to_tcp(at(z), self.tcp)[2] >= floor - 0.5:
            ladder.append(z)
            z -= 10.0
        cache = self._tz_cache
        # 같은 칸에서 찾은 값은 ikin 1회로만 다시 본다 — "닿지 않음"이면 하한에서(#147·#153)
        cached = (
            cache.get(xy_pose, sol, floor, self._cmd_off) if cache is not None else (False, None)
        )
        z, keep = search_travel_z(ladder, lambda z: self._ik_ok(at(z), sol), cached)
        if cache is not None and keep:
            cache.put(xy_pose, sol, floor, self._cmd_off, z)
        return z

    def _ik_ok(self, flange, sol: int) -> bool | None:
        """플랜지 posx 가 지금 관절 배치(sol)로 풀리고 J3 여유가 있는지. 두산 호출 실패면 None(닿지 않음과
        구분 — 이동 높이 캐시에 넣지 않는다, #153). ikin 은 컨트롤러 등록 TCP 기준이라 _run_path 가 잰
        오프셋(_cmd_off)으로 바꿔 보낸다."""
        cmd = flange_to_tcp(flange, self._cmd_off)
        self._tz_ik += 1
        try:
            j = self.queue.submit(lambda: self.dsr.ikin(cmd, sol)).result(timeout=3.0)
        except DoosanError as e:
            self.get_logger().warn(f"ikin 호출 실패: {e}")
            return None
        return j is not None and abs(j[2]) >= self.min_j3_deg

    def _in_tray(self, slot_flange, stage, sol: int, floor: float | None = None):
        """slot 위로 TCP ≥ 최저 이동 높이가 안 나올 때: (slot 위 트레이 안 높이 플랜지 z, 칸 0 위 이동 높이,
        칸 0 위 트레이 안 높이) 또는 None. floor = 트레이 안 최저 TCP z(없으면 zone_min_in_tray_tcp_z_mm).

        slot 위 높이가 공통 트레이 안 높이(60)보다 낮으면(구역 floor, C 칸 5 = TCP 40) 출입구 칸(C 칸 5 → 칸 3)
        위에서는 공통 높이까지만 내려가 slot 위로 비스듬히 내려간다 — 트레이 깊이 들어가지 않게(10/12 실기 요청).
        사선 위 점이 안 풀리면 예전처럼 같은 높이로 옆으로."""
        if stage is None or all(
            abs(a - b) < 0.5 for a, b in zip(slot_flange[:2], stage[:2], strict=True)
        ):
            return None
        zi = self._travel_z(slot_flange, sol, self.min_in_tray_tcp_z if floor is None else floor)
        zs = self._travel_z(stage, sol)
        if zi is None or zs is None:
            return None
        low = [slot_flange[0], slot_flange[1], zi, *slot_flange[3:]]
        ze = zi + max(0.0, self.min_in_tray_tcp_z - flange_to_tcp(low, self.tcp)[2])
        if ze > zi + 0.5 and not all(
            self._ik_ok(
                [s + k / 10 * (g - s) for s, g in zip([*stage[:2], ze], low[:3], strict=True)]
                + low[3:],
                sol,
            )
            for k in range(11)
        ):
            ze = zi
        return zi, zs, ze

    def _tray_stage(self, flange):
        """flange x·y 가 들어 있는 구역 트레이(안쪽 215 × 145 mm, measurements #6)의 칸 0, 없으면 None."""
        for zc in self.zones.values():
            if zc["pose"] and zc["grid"]:
                p = zc["pose"]
                if abs(flange[0] - p[0]) <= 107.5 and abs(flange[1] - p[1]) <= 72.5:
                    return slot_pose(p, zc["grid"], 0)
        return None

    def _run_path(self, target_flange, stage=None, in_tray_z: float | None = None) -> None:
        """현재 플랜지 → 목표: 수직 상승 → 수평 → 수직 하강, 단계마다 도착을 pose 로 확인.
        수평 이동 높이 = safe_z 와, 출발·도착 x·y 에서 닿는 최고 높이 중 낮은 것. 목표 자세 자체도 풀리는지
        움직이기 전에 확인한다. 먼 칸(출발·도착) 위로 최저 이동 높이가 안 나오면 stage(같은 줄 −X 끝 칸) 를
        거쳐 트레이 안에서만 낮게 옆으로 간다. 자세는 늘 수직(구역 자세 그대로)."""
        t_plan, n_plan = time.monotonic(), self._tz_ik
        try:
            off, why, cur, sol = self.queue.submit(self._ctrl_tcp).result(timeout=5.0)
            if off is None:
                # 두 서비스 값은 0.1 s 마다만 바뀌어 움직이는 중이면 어긋날 수 있다 → 0.2 s 뒤 한 번 더(#121 리뷰)
                time.sleep(0.2)
                off, why, cur, sol = self.queue.submit(self._ctrl_tcp).result(timeout=5.0)
            self._set_tcp_note(off)
            if off is None:
                raise _ZoneError(
                    f"NOT_CONFIGURED: 컨트롤러 TCP 등록이 {why} — 펜던트 툴·TCP 를 GripperDA_v1 또는 없음으로"
                )
            self._cmd_off = off  # move_line·ikin 좌표 기준 (MoveToZone 은 _mlock 으로 하나씩)
            if not any(off):
                self.get_logger().warn(
                    "MoveToZone 플랜지 모드 — 컨트롤러 TCP 등록 없음, 펜던트 공간 제한이 핑거 끝을 못 막음"
                )
            if not self._ik_ok(target_flange, sol):
                raise _ZoneError("LIMIT: 목표 자세에 팔이 닿지 않음 (구역·칸 위치 확인)")
            z0, z1 = self._travel_z(cur, sol), self._travel_z(target_flange, sol)
            pre, post = [], []
            tray = None  # 로그용 (칸 위 트레이 안 높이, 칸 0 위 높이)
            start, end = cur, target_flange
            if z0 is None and stage is None:
                stage = self._tray_stage(cur)  # 트레이 안에 멈춘 뒤 OBSERVE 복귀 등
            if z0 is None and (t := self._in_tray(cur, stage, sol, in_tray_z)) is not None:
                zi, z0, ze = (
                    t  # 놓은 칸에서 트레이 안 높이로 올라가 출입구 칸 위로(비스듬히) 옮긴 뒤 거기서 출발
                )
                low = [cur[0], cur[1], zi, *cur[3:]]
                start = [stage[0], stage[1], ze, *cur[3:]]
                pre = [("rise_in_tray", low)] if cur[2] < zi - 0.5 else []
                pre.append(("to_stage", start))
                tray = (zi, ze)
            if (
                z1 is None
                and (t := self._in_tray(target_flange, stage, sol, in_tray_z)) is not None
            ):
                zi, z1, ze = (
                    t  # 출입구 칸 위로 내려와 트레이 안 높이로 목표 칸 위까지(비스듬히) 옮긴 뒤 하강
                )
                end = [stage[0], stage[1], ze, *target_flange[3:]]
                post = [("in_tray", [target_flange[0], target_flange[1], zi, *target_flange[3:]])]
                post.append(("descend", list(target_flange)))
                tray = (zi, ze)
        except _ZoneError:
            raise
        except Exception as e:  # 큐 응답 없음
            raise _ZoneError(f"TIMEOUT: 경로 계산 {e}") from e
        if z0 is None or z1 is None:
            where = "출발" if z0 is None else "도착"
            raise _ZoneError(
                f"LIMIT: {where} 위에서 TCP z ≥ {self.min_travel_tcp_z:.0f} mm 로 수평 이동할 수 없다"
                f" (트레이 안 TCP ≥ {in_tray_z or self.min_in_tray_tcp_z:.0f} 도 안 됨 — 팔이 닿지 않음)"
            )
        hz = min(z0, z1)
        self.get_logger().info(
            f"경로 계산 {time.monotonic() - t_plan:.2f} s, ikin {self._tz_ik - n_plan}회 (#147)"
        )
        if hz < self.safe_z - 0.5:
            self.get_logger().info(
                f"수평 이동 높이 플랜지 z {hz:.1f} (TCP {hz - self.safe_z + 200:.0f}) — safe_z 에서 안 닿음"
            )
        if tray is not None:
            zi, ze = (z - self.safe_z + 200 for z in tray)
            how = (
                f"TCP {zi:.0f} 높이로 옆으로"
                if abs(ze - zi) < 0.5
                else f"TCP {ze:.0f} → {zi:.0f} 비스듬히"
            )
            self.get_logger().info(f"트레이 안 이동: 출입구 칸 위 거쳐 {how}")
        steps = pre + plan_move(start, end, hz) + post
        arcs = [p for n, p in steps if n.startswith("arc")]
        if arcs:
            try:
                reach = all(self._ik_ok(p, sol) for p in arcs)
            except Exception as e:  # 큐 응답 없음
                raise _ZoneError(f"TIMEOUT: 경유점 계산 {e}") from e
            if not reach:
                raise _ZoneError("LIMIT: 베이스 앞쪽으로 도는 경유점에 팔이 닿지 않음")
            self.get_logger().info(
                f"수평 이동이 베이스 뒤를 지나 앞쪽으로 돈다 (경유점 {len(arcs)}개, 스플라인 한 번)"
            )
            # 원호 경유점 + 다음 목표(over)를 move_spline 한 번으로 — 경유점마다 멈추지 않게(10/12 실기 요청)
            merged, i = [], 0
            while i < len(steps):
                if steps[i][0].startswith("arc"):
                    j = i
                    while steps[j][0].startswith("arc"):
                        j += 1
                    merged.append(("arc", [p for _, p in steps[i : j + 1]]))
                    i = j + 1
                else:
                    merged.append(steps[i])
                    i += 1
            steps = merged
        carry = 0.0  # 앞 구간에서 블렌딩으로 남긴 거리 — 이번 구간 경로 이탈 허용에 더한다
        for i, (name, step) in enumerate(steps):
            pts = step if name == "arc" else [step]  # arc = 경유점들 + 끝점 (스플라인)
            cmds = [flange_to_tcp(q, self._cmd_off) for q in pts]  # 컨트롤러 등록 TCP 기준 목표
            # 핑거 끝(/voss/robot/pose 와 같은 기준) — 도착 판정
            tcps = [flange_to_tcp(q, self.tcp)[:3] for q in pts]
            seq0 = self.dsr.alarm_seq
            # 블렌딩(zone_blend_mm): 위쪽 모서리(이동 높이에서 끝나는 구간 → 다음 직선 구간)만 — 남은 거리가
            # 이만큼일 때 다음 move_line 을 보내 멈추지 않고 꺾는다(두산 DUPLICATE). 트레이 안 낮은 모서리는 그대로
            # 두산은 스플라인(move_spline_task) 앞뒤로 다른 이동이 겹치면 거부한다(10/12 실기 450 mm/s: 1203
            # rejected eMoveL·1903 rejected eMoveSX) → 스플라인 구간은 블렌딩하지 않고, 보내기 전·직후 정지 확인
            nxt = steps[i + 1][0] if i + 1 < len(steps) else ""
            blend = (
                self.blend_mm
                if self.blend_mm > 0
                and name != "arc"
                and nxt
                and nxt != "arc"
                and pts[-1][2] >= hz - 0.5
                else 0.0
            )
            try:
                if name == "arc" or (i > 0 and steps[i - 1][0] == "arc"):
                    self._wait_idle(name)
                self._send_move(name, cmds)
                self._wait_arrive(name, tcps[-1], seq0, tcps[:-1], early=blend, carry=carry)
                carry = blend
            except _ZoneError as e:
                if not str(e).startswith("STOPPED"):  # stop 은 이미 move_stop 을 보냈다
                    self._zone_halt(f"{name}: {e}")
                raise

    def _wait_idle(self, name: str, timeout_s: float = 3.0) -> None:
        """컨트롤러 이동 명령이 끝날 때까지(check_motion = IDLE 0, 스플라인 앞뒤). 도착 판정(3 mm·0.3 s) 뒤에도,
        robot_state 가 STANDBY 여도 이동 명령이 남아 스플라인이 거부됐다(10/12 실기 450 mm/s, 1903)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._abort.is_set():
                raise _ZoneError(f"STOPPED: {name} 전 stop")
            try:
                st = self.queue.submit(self.dsr.check_motion).result(timeout=1.0)
            except Exception as e:  # 큐 응답 없음
                raise _ZoneError(f"TIMEOUT: {name} 전 컨트롤러 상태 {e}") from e
            if st == 0:
                return
            time.sleep(0.03)
        raise _ZoneError(f"TIMEOUT: {name} 전 컨트롤러가 {timeout_s:.0f} s 동안 이동 중 상태")

    def _send_move(self, name: str, cmds) -> None:
        """move_line(ASYNC) 한 구간을 큐로 보낸다. stop 이 먼저 왔으면 보내지 않고 STOPPED.

        stop 의 move_stop 은 그 순간 움직이는 것만 멈춘다. 그리퍼 동작(닫기 약 1.7 s) 중에 온 stop 뒤에 다음 구간을
        보내면 아무도 멈추지 않아 끝까지 간다 → 큐 작업 안에서 확인해 stop 과 송신 사이 틈을 없앤다. stop 전에 큐에
        이미 들어가 있던 move_line 도 여기서 막힌다(#148 리뷰 박병후)."""

        def send():
            if self._abort.is_set():
                raise _ZoneError(f"STOPPED: {name} 전 stop")
            if len(cmds) == 1:
                self.dsr.move_line_async(cmds[0], self.zone_vel, self.zone_acc)
            else:
                self.dsr.move_spline_async(cmds, self.zone_vel, self.zone_acc)

        try:
            self.queue.submit(send).result(timeout=2.0)
        except _ZoneError:
            raise
        except Exception as e:
            raise _ZoneError(f"TIMEOUT: move_line({name}) {e}") from e

    def _zone_halt(self, why: str) -> None:
        """MoveToZone 이동 중 실패: move_line 이 계속 가지 않게 move_stop (speedl 은 보내지 않는다)."""
        self.get_logger().warn(f"MoveToZone 중단 → move_stop ({why})")

        def done(ok: bool, message: str) -> None:
            if not ok:
                self.get_logger().error(f"move_stop 실패(MoveToZone): {message}")

        self.dsr.move_stop_async(done)

    def _wait_arrive(
        self, name: str, tcp_xyz, seq0: int, via=(), early: float = 0.0, carry: float = 0.0
    ) -> None:
        """도착 확인. via = 스플라인 경유점(핑거 끝 xyz) — 경로 이탈은 경유점을 잇는 꺾은선 기준, 스플라인이 현을
        벗어나는 만큼(40° 원호 r 300 이면 약 18 mm) 허용을 넓힌다. early > 0 = 남은 거리가 이만큼이면 바로 돌려준다
        (다음 구간과 블렌딩). carry = 앞 구간이 블렌딩으로 남긴 거리 — 그만큼 경로 이탈 허용을 넓힌다."""
        with self._glock:
            p = self.guard._pose
        start = p[1:] if p else tcp_xyz
        line = [list(start), *[list(v) for v in via], list(tcp_xyz)]
        dist = sum(math.dist(a, b) for a, b in zip(line, line[1:], strict=False))
        tol = self.path_tol + (25.0 if via else 0.0) + carry
        # pose 는 config 오프셋으로 바꾼 TCP 라 등록 TCP 가 달라도(검사를 지나친 경우) 여기서 잡힌다
        seg_a = p[1:] if p else None
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
            if fresh and seg_a is None:
                seg_a = p[1:]  # 시작 때 pose 가 없었으면 처음 받은 pose 부터
                line[0] = list(seg_a)
            # 전제: 구역 자세는 모두 툴 수직·yaw 거의 같음(rx−rz ≈ 90° ±1.3°) → 단계 중 회전이 없어 컨트롤러가
            # 직선으로 보내는 점(TCP 든 플랜지 모드의 플랜지든)과 핑거 끝이 함께 직선으로 간다(#121 리뷰 남현지)
            if (
                fresh
                and (
                    off := min(
                        segment_distance_mm(a, b, p[1:])
                        for a, b in zip(line, line[1:], strict=False)
                    )
                )
                > tol
            ):
                raise _ZoneError(
                    f"LIMIT: {name} 중 경로 이탈 {off:.0f} mm (직선 이동이어야 함 — TCP 등록·충돌 확인)"
                )
            if early > 0.0 and fresh and math.dist(p[1:], tcp_xyz) <= early:
                return  # 블렌딩: 다음 구간을 바로 보낸다
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
            "clamp": {
                "speed": 0,
                "z_min": 0,
                "x_min": 0,
                "x_max": 0,
                "angular": 0,
                "ang_speed": 0,
                "yaw_limit": 0,
            },
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
        self.dsr.speedl(r.vel_mm_s, self.servo_acc, r.wz_dps)
        ss["pub"] += 1
        if self.stopped or not self._was_active:
            self.stopped = False  # 새 모션 → STOPPED 해제
            self._update_state()
        self._was_active = True

    def _on_servo_tick(self) -> None:
        with self._glock:
            action, vel = self.guard.on_tick(self._now())
            wz = self.guard.last_wz
        if action == "clamp":  # 명령 사이에 한계에 닿음 → 자른 속도로 바로 다시 보낸다
            self.dsr.speedl(vel, self.servo_acc, wz)
            self._sstats["pub"] += 1
        elif action == "expire":
            self._was_active = False
            self._update_state()
            self._sstats["expire"] += 1
            self.get_logger().warn("servo_cmd 끊김(watchdog) → 0 속도 + move_stop")
            self._halt("watchdog")

    def _halt(self, why: str, done=None) -> None:
        """① 속도 0 speedl(각속도도 0) ② 이어서 항상 move_stop (정지 판별 안 함, ADR-0010 조건 2·#53 MC-014)."""
        self.dsr.speedl([0.0, 0.0, 0.0], self.servo_acc, 0.0)

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
        zone = self._zone_action  # MoveToZone 의 move_line 도 gateway 가 죽으면 계속 간다
        if not moving and not zone:
            return None
        ev = threading.Event()

        def done(ok: bool, message: str) -> None:
            if ok:
                self.get_logger().info("종료 정지: move_stop OK")
            ev.set()

        if moving:
            self.get_logger().warn("종료 중 servo 활성 → 0 속도 + move_stop")
            self._halt("exit", done)
        else:
            self.get_logger().warn(f"종료 중 {zone} 진행 → move_stop")
            self._abort.set()
            self.dsr.move_stop_async(done)
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
