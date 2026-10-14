"""belt_servo — 컨베이어 박스 추종·파지 노드 (U1 뼈대 + U2 제어 계산 + U5 그리퍼 호출·판정).

계약 (docs/interfaces/topics.md belt_servo 행, voss_msgs.md TrackAndGrasp 행):
- 구독 /voss/vision/box (BoxTrack: position_base = 촬영 시각 관측 박스 윗면 중심 m, base_link),
       /voss/robot/pose (PoseStamped, TCP, base_link, stamp = 응답 수신 시각). best_effort·volatile.
- 발행 /voss/robot/servo_cmd (TwistStamped, TCP 선속도 m/s, frame base_link, 각속도 0) 30 Hz.
- 액션 /voss/servo/track_and_grasp. READY 일 때만 서버를 만들고, 바쁘면 reject. goal 1개당 result 1건.
- 서비스 호출 /voss/robot/stop (취소 시), /voss/robot/gripper (PREPARE 개방·GRASP 닫기·VERIFY 확인).
  비동기: 보내고 틱마다 들여다본다. goal 이 끝난 뒤 그리퍼 요청은 보내지 않는다(자동 개방 금지).
- ADR-0010: speedl 은 스트림이 끊겨도 마지막 속도로 계속 간다 → 어떤 종료든 마지막 명령은 0.
구조 (design/U1-hld.md): 콜백은 최신값만 보관 → 30 Hz 타이머 한 곳에서 판단·발행·로그.
판단 로직은 순수 모듈 params·fsm·control·grip·log_schema·diagnose 에 있다
(control 설계: design/U2-*.md, grip 설계: design/U5-*.md, 진단(로그 전용): design/U9c-*.md).
"""

from __future__ import annotations

import math
import signal
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from rclpy.task import Future
from std_srvs.srv import Trigger

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack
from voss_msgs.srv import Gripper
from voss_servo import control, diagnose, fsm, grip, rotate
from voss_servo import log_schema as ls
from voss_servo.params import (
    BLIND_DWELL_MARGIN_S,
    PARAM_SPECS,
    Z_PROFILE_TRAP,
    check_params,
    params_digest,
    ready_log_line,
    rot_cfg_from_values,
    rotate_line,
    rotate_on,
)

# QoS (topics.md QoS 표). box 구독 depth 5 는 소비자 재량: 박스마다 메시지가 따로 와서
# depth 1 이면 같은 프레임의 다른 박스 메시지에 내 박스가 밀려날 수 있다 (depth 는 QoS 호환 조건 아님)
QOS_BOX = QoSProfile(
    depth=5, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
)
QOS_FAST = QoSProfile(
    depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
)
BOX_TOPIC = "/voss/vision/box"  # 구독 + LOST 때 발행자 수 조회 (U9-c)
BOX_PRUNE_S = 2.0  # 이만큼 갱신 없는 다른 트랙 항목은 지운다 (파라미터와 무관한 상수)
DEFAULT_RATE_HZ = 30.0  # rate_hz 가 없을 때 (READY 아님) 타이머 주기
ZERO = (0.0, 0.0, 0.0)  # 속도 0
# 0 유지·예외 경로 로그에서 null 로 두는 U2 키
SNAPSHOT_NULL_KEYS = (
    "tcp_now_m",
    "tcp_extrap_s",
    "tcp_extrap_capped",
    "predict_horizon_s",
    "predict_dt_clipped",
    "obs_age_s",
    "visible",
    "err_along_m",
    "err_cross_m",
    "dt_s",
    "aligned",
    "at_grasp_height",
    "at_lift_height",
    "reach",
    "z_v_cmd_mps",  # S2-T14
)
# 진단 값 키 (U9-c, 로그 전용). 0 유지·예외 경로에서는 null
DIAG_KEYS = (
    "obs_rx_age_s",
    "other_box_rx_age_s",
    "box_pub_count",
    "tcp_vel_meas_mps",
    "stall_ticks",
    "belt_speed_est_mps",
    "belt_speed_est_span_s",
    "cause_fsm",
)
# 안전 후퇴·재시도 로그 키 (U9b-dd 5절). 0 유지·예외 경로에서는 goal 끝 때 값(스냅샷)
RETREAT_KEYS = ("retreat", "retreat_reason", "retreat_done", "retry_room_ok")


def yaw_log_values(box: Any) -> tuple[float | None, bool | None]:
    """BoxTrack 의 yaw 를 틱 로그용 (도, valid) 로 바꾼다 (로그 전용, 제어에 쓰지 않음, S2-T18 0단계).

    yaw 필드가 없는 옛 BoxTrack(S2-T16 전 빌드)과 yaw_valid=false, 박스 없음을 로그에서 구별한다:
    박스 없음·필드 없음 → (None, None), yaw_valid=false → (None, False), 값이 유한하지 않음 → (None, True).
    """
    if box is None:  # 이 트랙의 메시지를 아직 못 받음
        return None, None
    valid = getattr(box, "yaw_valid", None)  # 옛 메시지에는 필드가 없어 None
    if valid is None:  # 필드 없음 = yaw 없는 빌드
        return None, None
    if not valid:  # 비전이 이 프레임 yaw 를 쓰지 말라고 함 (값은 0)
        return None, False
    yaw = getattr(box, "yaw_base", None)  # rad, 베이스 +X 에서 반시계 양
    if not isinstance(yaw, float | int) or not math.isfinite(yaw):  # NaN·무한대·이상한 타입
        return None, True
    return math.degrees(yaw), True  # 사람이 읽기 쉽게 도 단위


def _as_list(a: Any) -> list[float] | None:
    """NumPy 벡터 → float 목록 (None 이면 None)."""
    return None if a is None else [float(x) for x in a]


def _as_float(x: Any) -> float | None:
    """NumPy 숫자 → float (None 이면 None)."""
    return None if x is None else float(x)


def pose_lag_note(lag_ms: Any) -> str:
    """READY 다음 줄 문구: pose_lag_ms 값으로 어느 gateway pose_source 짝인지 알려 준다 (로그 전용).

    0 = joint_states 운용 시험값, 60 = service 임시값, 그 밖 = 값만 (measurements-1010 #10).
    """
    head = f"pose_lag_ms={lag_ms}"  # 값은 언제나 찍는다
    if lag_ms == 0:  # gateway pose_source: joint_states 와 짝
        return head + " — joint_states 운용 시험값(0)"
    if lag_ms == 60:  # gateway pose_source: service 와 짝
        return head + " — service 임시값(60, 영상 기준 lag 차용)"
    return head  # 짝이 정해지지 않은 값은 설명을 붙이지 않는다


def stamp_s(stamp: Any) -> float:
    """builtin_interfaces/Time → 초."""
    return stamp.sec + stamp.nanosec * 1e-9


def plain(value: Any) -> Any:
    """ROS 파라미터 값의 배열(array.array)을 list 로 바꾼다."""
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


@dataclass
class BoxEntry:
    """track_id 하나의 최신 관측과 마지막 유효 관측."""

    msg: BoxTrack  # 가장 최근 메시지
    rx: float  # 그 메시지를 받은 시각
    latest_invalid: bool  # 가장 최근 메시지가 position_valid=false 인가
    last_valid: BoxTrack | None  # 마지막 position_valid=true 메시지 (사각 구간 예측에 씀)
    last_valid_rx: float | None  # 그 메시지를 받은 시각


@dataclass
class GoalCtx:
    """진행 중 goal 하나의 상태."""

    handle: Any  # rclpy ServerGoalHandle
    goal_id: str  # goal UUID 16진수
    track_id: int
    state: fsm.FsmState
    start: float  # goal 시작 시각 (pose 끊김 판정의 기준 시각, 노드 시계)
    vision_since: float  # 비전 필요 구간이 시작된 시각 (box 끊김 판정의 기준 시각, 노드 시계)
    done: Future = field(default_factory=Future)  # 결과 봉투 (타이머가 채운다)
    blind: bool = False  # 지난 틱의 사각 판정
    blind_since: float | None = None  # DESCEND 에서 사각이 시작된 시각 (U9a 체류 상한, 노드 시계)
    # --- 안전 후퇴·재시도 (U9b-dd 4절) ---
    lift_since: float | None = None  # LIFT 상승 시작 시각 (후퇴 상한·정상 들기 경고)
    hold_since: float | None = None  # 개방 대기(hold_z) 시작 시각
    retry_room_ok: bool | None = None  # 마지막 GRASP 실패 때 재시도 x 여유 (로그)
    retreat_done: bool | None = None  # 후퇴로 끝났나: 끝 틱에 정한다 (로그)
    lift_warned: bool = False  # 정상 LIFT 체류 경고를 냈나 (goal 당 1회)
    last_phase: str = ""  # 마지막으로 feedback 보낸 phase
    stop_future: Any = None  # stop 서비스 call_async 결과
    stop_sent: float | None = None  # stop 요청 보낸 시각
    stop_result: fsm.StopResult | None = None  # 정해진 stop 결과
    last_calc: float | None = None  # 지난 틱 계산 시각 (dt 용)
    dt: float | None = None  # 이번 틱 dt (로그용)
    geo: control.Geometry | None = None  # 이번 틱 기하 계산 (로그용)
    cmd: control.Command | None = None  # 이번 틱 명령 (로그용)
    source: int | None = None  # 마지막 유효 관측의 position_source (바뀌면 경고)
    # 지금 기다리는 그리퍼 호출 (BUSY 재요청 대기 중에도 남음)
    grip_call: grip.GripCall | None = None
    grip_future: Any = None  # 그 호출의 future (진동벨). 응답을 소비했으면 None
    grip_seq: int = 0  # 이 goal 에서 보낸 그리퍼 요청 수
    grip_ready_reply: fsm.GripperReply | None = None  # 요청 순간 정해진 응답 (서비스 없음)
    grip_log: dict[str, Any] | None = None  # 로그 gripper 칸 (진행 중 또는 마지막 끝난 호출)
    # --- U9-c 진단 (로그·경고 전용, 제어·전이에는 쓰지 않는다. design/U9c-dd.md 5절) ---
    # 내 트랙 유효 관측열 (촬영 stamp, 위치) — 벨트 속도 추정용, 시도마다 새로
    obs_hist: deque = field(default_factory=lambda: deque(maxlen=diagnose.FIT_MAX_POINTS))
    stall_n: int = 0  # 명령 ≠ 0 인데 로봇이 안 움직인 연속 틱 수
    speed_run: int = 0  # 벨트 속도 차이가 큰 새 관측 연속 수
    speed_warned: bool = False  # 이 goal 에서 벨트 속도 WARN 을 냈나 (goal 당 1회)
    other_rx: float | None = None  # 이 goal 중 다른 트랙 메시지를 마지막으로 받은 시각
    phase_t: dict[str, float] = field(default_factory=dict)  # 이 시도의 phase 진입 시각
    phase_t_next: dict[str, float] | None = None  # 재시도 때 다음 틱에 바꿔 넣을 새 시도 시각
    phase_seen: str = ""  # 지난 틱에 단계 시각을 기록한 phase
    diag: dict[str, Any] = field(default_factory=dict)  # 이번 틱 진단 값 (로그용)
    diag_failed: bool = False  # 진단 예외를 이미 로그했나 (goal 당 1회)
    # --- S2-T18 J6 회전 (회전 off 면 rot 은 None, 나머지는 쓰이지 않음) ---
    rot: Any = None  # rotate.RotState — 회전 하위 상태
    wz: float = 0.0  # 이번 틱에 발행할 베이스 Z 각속도 rad/s
    rot_floor: float | None = None  # 이번 틱 z 하한 m (회전 중 시야 보험)
    rot_warn: str | None = None  # 이번 틱 회전 경고 원인 (로그)
    rot_io: tuple[Any, Any, Any] = (
        None,
        None,
        None,
    )  # (공구 yaw 원값, 외삽값, 측정 각속도) — 로그용
    rot_dead: bool = False  # 회전 계산 예외로 이 goal 의 회전을 껐나
    rot_still_n: int = 0  # rot_dead 일 때 정지 확인 연속 틱


class BeltServoNode(Node):
    """기동 검사·액션 골격·30 Hz 제어 발행·로그."""

    def __init__(self) -> None:
        super().__init__("belt_servo")
        self._ctx: GoalCtx | None = None  # 진행 중 goal
        self._last_goal: dict[str, Any] | None = None  # 끝난 goal 스냅샷 (0 유지 틱 로그용)
        self._busy = False  # goal 진행 중 또는 0 유지 중
        self._hold_until: float | None = None  # 0 유지 끝 시각
        self._boxes: dict[int, BoxEntry] = {}  # track_id 별 최신 관측
        self._pose: tuple[PoseStamped, float] | None = None  # (최신 pose, 받은 시각) — 끊김 판정용
        # (위치 값, 그 값이 처음 온 stamp) — 외삽 기준. 값이 0.1 s 마다만 바뀌는 pose 대응 (PR #122 리뷰)
        self._pose_value: tuple[tuple[float, float, float], float] | None = None
        # 그 직전 (위치 값, 처음 온 stamp) — 값 차분으로 TCP 속도를 잰다 (U9-c 진단)
        self._pose_prev_value: tuple[tuple[float, float, float], float] | None = None
        self._last_cmd = control.zero_cmd()  # 마지막 발행 속도 (TCP 외삽·가속 제한 입력)
        self.values = self._declare_params()  # {이름: 값 또는 None}
        self.ready = self._startup_check()  # READY 여부 (기동 때 한 번)
        # 제어 설정 묶음 (단위 변환 한 곳). READY 일 때만 goal 이 돌아서 그때만 만든다
        self._ctrl = control.config_from_values(self.values) if self.ready else None
        self.grip_late_discarded = 0  # 버린 늦은 그리퍼 응답 수 (U5 DD E8)
        if self.ready:
            self.get_logger().info(self._z_profile_line())  # 모드를 READY 줄들 맨 앞에 (S2-T14)
        self._room_need_s = self._grasp_room_need() if self.ready else None  # x 여유 계산용 시간
        self._blind_max_s = self._blind_dwell_max() if self.ready else None  # 사각 체류 상한 (U9a)
        self._retry_need_s = self._retry_need() if self.ready else None  # 재시도 x 여유 시간 (U9b)
        self._lift_max_s = self._lift_max() if self.ready else None  # 후퇴 체류 상한 (U9b)
        self._setup_rotate()  # S2-T18 J6 회전 (off 면 값만 None 으로)
        self._setup_logs()
        self._setup_ros()

    # ------------------------------------------------------------------ 기동

    def _declare_params(self) -> dict[str, Any]:
        """표의 모든 이름을 '기본값 없음·타입 자유'로 선언하고 값을 읽는다 (안 왔으면 None)."""
        values: dict[str, Any] = {}
        for spec in PARAM_SPECS:
            desc = ParameterDescriptor(description=spec.unit, dynamic_typing=True)
            self.declare_parameter(spec.name, None, desc)
            values[spec.name] = plain(self.get_parameter(spec.name).value)
        return values

    def _startup_check(self) -> bool:
        """파라미터 검사 → 로그 2줄 (설정 지문 / READY 여부)."""
        report = check_params(self.values)
        self.params_sha256 = params_digest(self.values)
        version = self.values.get("config_version")
        sha = self.values.get("config_sha256")
        line = f"config_version={version} config_sha256={sha} params_sha256={self.params_sha256}"
        if version is None or sha is None:
            self.get_logger().warning(line + " (config_version·sha256 미전달)")
        else:
            self.get_logger().info(line)
        if report.ready:
            self.get_logger().info("READY")
            # pose_lag_ms 는 gateway pose_source 와 짝이 맞아야 한다 (joint_states → 0, service → 60)
            self.get_logger().info(pose_lag_note(self.values.get("input.pose_lag_ms")))
        else:
            # 어떤 키가 문제인지 이름으로. READY 가 아니면 액션 서버를 만들지 않는다 (_setup_ros)
            self.get_logger().error(ready_log_line(report) + " — 액션 서버 미생성")
        return report.ready

    def _z_profile_line(self) -> str:
        """기동 로그 첫 줄: z 프로파일과 하강·들기 예상 시간 (S2T14-dd 3.1, sim_check 가 파싱한다)."""
        cfg = self._ctrl
        desc = control.z_move_time_s(
            cfg.approach_dz - cfg.grasp_dz, cfg.descend_speed, cfg, control.z_law(fsm.DESCEND, cfg)
        )  # 접근 높이 → 파지 높이
        lift = control.z_move_time_s(
            cfg.lift_dz - cfg.grasp_dz, cfg.lift_speed, cfg, control.z_law(fsm.LIFT, cfg)
        )  # 파지 높이 → 들기 높이
        times = f"하강 예상 {desc:.2f} s · 들기 예상 {lift:.2f} s"
        if cfg.z_profile == Z_PROFILE_TRAP:
            return (
                f"z 프로파일: trapezoid — DESCEND·LIFT 사다리꼴(감속 {cfg.a_dec:.3f} m/s², "
                f"최소 {control.TRAP_V_FLOOR_MPS * 1000.0:g} mm/s), PREPARE·TRACK·후퇴는 P. "
                f"{times} (되돌림: z.profile: p)"
            )
        head = f"z 프로파일: p — 모든 phase P(kp_z {cfg.kp_z:g})."
        return f"{head} {times} (켜기: z.profile: trapezoid)"

    def _setup_rotate(self) -> None:
        """J6 회전 파지 상태 준비 (S2-T18). off 면 _rot_on 이 False 라 어떤 경로도 회전을 쓰지 않는다."""
        self._rot_on = bool(self.ready and rotate_on(self.values))  # 회전을 켰나
        cfg = rot_cfg_from_values(self.values, self._ctrl.belt_dir_xy) if self._rot_on else None
        self._rot_cfg = cfg
        self._yaw_hist: dict[int, deque] = {}  # track_id → (촬영 stamp, yaw) 최근 프레임
        self._yaw_field: bool | None = None  # BoxTrack 에 yaw 필드가 있나 (None = 아직 모름)
        self._yaw_value: tuple[float, float] | None = None  # (공구 yaw, 그 값이 처음 온 stamp)
        self._yaw_prev: tuple[float, float] | None = None  # 그 직전 값 (측정 각속도)
        self._tilt: float | None = None  # 공구 z 축 기울기
        self._home_ref = cfg.home_fixed if cfg else None  # 기준 공구 yaw (없으면 첫 goal 에서)
        # 이 노드가 한 번이라도 돌았나 — 돈 뒤에는 기준을 새로 잡지 않는다 (돌아간 손목을 기준 삼기 방지)
        self._rot_ever = False
        self._last_wz = 0.0  # 마지막 발행 각속도 (외삽·변화 제한 입력)
        if self.ready:
            self.get_logger().info(rotate_line(self.values))

    def _grasp_room_need(self) -> float:
        """정렬 뒤 하강 + 닫힘에 걸릴 시간 (s). x 여유 검사(HLD D6)에 쓴다."""
        cfg = self._ctrl
        close_s = float(self._p("grasp.close_time_max_s"))  # 닫힘 최대 시간
        need_s = control.grasp_room_need_s(cfg, close_s)  # 하강 예상(프로파일별) + 닫힘
        t_desc = need_s - close_s  # 로그용 하강 예상
        belt = float(np.linalg.norm(cfg.belt_v))  # 벨트 속도 m/s
        need_m = belt * need_s + float(self._p("grasp.room_margin_mm")) / 1000.0
        self.get_logger().info(
            f"x 여유: 하강 예상 {t_desc:.2f} s + 닫힘 {need_s - t_desc:.2f} s → 정렬 때 "
            f"x_max 까지 {need_m * 1000.0:.0f} mm 이상 남아야 DESCEND"
        )
        return need_s

    def _blind_dwell_max(self) -> float:
        """DESCEND 사각 체류 상한 s. READY 때 한 번 계산하고 기동 로그에 남긴다 (U9a-dd 2.5)."""
        cutoff_m = float(self._p("z.vision_cutoff_above_top_mm")) / 1000.0  # 사각 진입 높이
        limit = control.descend_blind_max_s(cutoff_m, self._ctrl)
        self.get_logger().info(
            f"사각 체류 상한: DESCEND 사각이 {limit:.2f} s 넘으면 DEVICE_ERROR "
            f"(하강 예상 {limit - BLIND_DWELL_MARGIN_S:.2f} + 여유 {BLIND_DWELL_MARGIN_S:g})"
        )
        return limit

    def _retry_need(self) -> float:
        """GRASP 실패 뒤 재시도 1회에 걸릴 시간 s. 기동 로그에 실패 x 문턱을 남긴다 (U9b-dd 4절)."""
        cfg = self._ctrl
        need_s = control.retry_need_s(cfg, self._room_need_s)  # 재상승 + 하강 + 닫힘 상한
        margin_m = float(self._p("grasp.room_margin_mm")) / 1000.0
        need_m = float(np.linalg.norm(cfg.belt_v)) * need_s + margin_m  # 그동안 벨트를 따라갈 길
        self.get_logger().info(
            f"재시도 x 여유: 실패 때 x_max 까지 {need_m * 1000.0:.0f} mm 이상 남아야 재시도 "
            f"(실패 TCP x ≤ {(cfg.x_max - need_m) * 1000.0:.0f} mm, 아니면 안전 후퇴)"
        )
        return need_s

    def _lift_max(self) -> float:
        """후퇴 상승 체류 상한 s. 정상 들기는 넘어도 경고만 한다 (U9b-dd 4절, 재검 r1)."""
        limit = control.lift_max_s(self._ctrl)
        self.get_logger().info(
            f"후퇴 체류 상한: 후퇴 상승이 {limit:.2f} s 넘으면 DEVICE_ERROR (정상 들기는 경고만)"
        )
        return limit

    def _setup_logs(self) -> None:
        """틱·시도 로그 파일 경로를 정하고 기동 로그에 절대 경로를 남긴다."""
        log_dir = self.values.get("log.dir") or "data/servo"
        ticks, attempts = ls.log_paths(str(log_dir), datetime.now())
        self._tick_log = ls.JsonlWriter(ticks)  # 파일은 처음 쓸 때 생긴다
        self._attempt_log = ls.JsonlWriter(attempts)
        self._log_fail_warned = False  # 로그 쓰기 실패 경고는 한 번만
        self.get_logger().info(f"로그: ticks={ticks} attempts={attempts}")

    def _setup_ros(self) -> None:
        """구독·발행·클라이언트·액션 서버·타이머."""
        self.create_subscription(BoxTrack, BOX_TOPIC, self._on_box, QOS_BOX)
        self.create_subscription(PoseStamped, "/voss/robot/pose", self._on_pose, QOS_FAST)
        self._cmd_pub = self.create_publisher(TwistStamped, "/voss/robot/servo_cmd", QOS_FAST)
        self._stop_cli = self.create_client(Trigger, "/voss/robot/stop")
        self._gripper_cli = self.create_client(Gripper, "/voss/robot/gripper")
        # READY 일 때만 액션 서버를 만든다. sort_manager 는 SERVO 준비를 "액션 서버 있음"으로
        # 판단하므로(voss_manager readiness.py), READY 아닌 서버가 떠 있으면 goal → reject → PAUSED 가 된다.
        # 기동 때 한 번 판정 (DEC-10, 운전 중 재판정 없음). design/U1-dd.md 5절
        self._action: ActionServer | None = None
        if self.ready:
            self._action = ActionServer(
                self,
                TrackAndGrasp,
                "/voss/servo/track_and_grasp",
                execute_callback=self._execute,
                goal_callback=self._on_goal,
                cancel_callback=self._on_cancel,
            )
        # READY 가 아니면 rate_hz 가 없거나 잘못됐을 수 있다 → 기본 주기로 (기동 중 죽지 않게)
        rate = self._p("rate_hz") if self.ready else DEFAULT_RATE_HZ
        self.create_timer(1.0 / float(rate), self._on_tick)

    # ------------------------------------------------------------------ 값 꺼내기

    def _now(self) -> float:
        """지금 시각 (초, 노드 시계)."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _p(self, name: str) -> Any:
        """파라미터 값. READY 일 때만 goal 이 돌아서 필수 값은 None 이 아니다."""
        return self.values[name]

    # ------------------------------------------------------------------ 구독 콜백

    def _on_box(self, msg: BoxTrack) -> None:
        """track_id 별 최신값만 보관한다 (계산 없음)."""
        try:
            now = self._now()
            prev = self._boxes.get(msg.track_id)
            if prev is not None and stamp_s(msg.stamp) < stamp_s(prev.msg.stamp):
                return  # 같은 트랙에서 시각이 뒤로 간 메시지는 버린다
            p = msg.position_base
            finite = control.finite_vec((p.x, p.y, p.z)) is not None
            valid = bool(msg.position_valid) and finite  # NaN 좌표는 valid 라도 invalid 로 본다
            last_valid = msg if valid else (prev.last_valid if prev else None)
            last_valid_rx = now if valid else (prev.last_valid_rx if prev else None)
            self._boxes[msg.track_id] = BoxEntry(msg, now, not valid, last_valid, last_valid_rx)
            self._yaw_field = hasattr(msg, "yaw_valid")  # S2-T16 yaw 필드가 있는 빌드인가
            if self._rot_on:
                self._push_yaw(msg, valid)  # 목표 각 결정용 프레임 (S2-T18)
            ctx = self._ctx
            if ctx is not None and msg.track_id != ctx.track_id:
                ctx.other_rx = now  # goal 중 다른 트랙 수신 (LOST 원인 판정, U9-c)
            self._prune_boxes(now)
        except Exception as exc:  # 콜백 예외로 노드가 죽지 않게
            self.get_logger().error(f"_on_box 예외: {exc!r}")

    def _prune_boxes(self, now: float) -> None:
        """오래 갱신 안 된 다른 트랙 항목을 지운다 (현재 goal 트랙은 남긴다)."""
        keep = self._ctx.track_id if self._ctx else None
        old = [t for t, e in self._boxes.items() if t != keep and now - e.rx > BOX_PRUNE_S]
        for t in old:
            del self._boxes[t]
            self._yaw_hist.pop(t, None)  # 같은 트랙의 yaw 프레임도 (S2-T18)

    def _push_yaw(self, msg: BoxTrack, valid: bool) -> None:
        """yaw_valid 이고 position 도 valid 인 프레임만 트랙별 버퍼에 (stamp 가 앞으로 갈 때만)."""
        if not (valid and getattr(msg, "yaw_valid", False)):
            return
        yaw = float(msg.yaw_base)  # rad, 접힌 값
        if not math.isfinite(yaw):
            return
        st = stamp_s(msg.stamp)  # 촬영 시각
        hist = self._yaw_hist.setdefault(msg.track_id, deque(maxlen=self._rot_cfg.buffer_n))
        if hist and st <= hist[-1][0]:
            return  # 같은 메시지 반복이거나 시각이 뒤로 감
        hist.append((st, yaw))

    def _update_yaw(self, msg: PoseStamped, stamp: float) -> None:
        """pose 쿼터니언 → 공구 yaw. 같은 값이면 처음 stamp 를 유지 (위치 값과 같은 규칙)."""
        o = msg.pose.orientation
        r = rotate.tool_yaw((o.x, o.y, o.z, o.w))
        if r is None:
            self._tilt = None  # 자세를 모른다 → pose_ok 거짓
            return
        yaw, self._tilt = r
        cur = self._yaw_value
        if cur is not None and abs(rotate.wrap_pi(yaw - cur[0])) < rotate.YAW_SAME:
            return  # 값 그대로
        self._yaw_prev, self._yaw_value = cur, (yaw, stamp)

    def _on_pose(self, msg: PoseStamped) -> None:
        """최신 TCP pose 와 받은 시각, 그리고 위치 값이 바뀐 첫 stamp 를 보관한다."""
        try:
            self._pose = (msg, self._now())  # 수신 시각은 메시지마다 (pose_stale 판정)
            p = msg.pose.position
            stamp = stamp_s(msg.header.stamp)
            # 같은 값이 반복되면 처음 stamp 유지 → 외삽 지평에 값의 실제 나이가 들어간다
            value = control.pose_value_stamp(self._pose_value, (p.x, p.y, p.z), stamp)
            if self._pose_value is not None and value is not self._pose_value:
                # 값이 바뀜 → 직전 값 보관 (측정 속도, U9-c)
                self._pose_prev_value = self._pose_value
            self._pose_value = value
            if self._rot_on:
                self._update_yaw(msg, stamp)  # S2-T18 공구 yaw
        except Exception as exc:
            self.get_logger().error(f"_on_pose 예외: {exc!r}")

    # ------------------------------------------------------------------ 액션 콜백

    def _on_goal(self, request: TrackAndGrasp.Goal) -> GoalResponse:
        """받을지 거절할지만 정한다."""
        if not self.ready:
            self.get_logger().warning("goal 거부: READY 아님 (기동 로그의 READY 거부 참고)")
            return GoalResponse.REJECT
        if self._busy:
            self.get_logger().warning("goal 거부: 진행 중 또는 0 유지 중")
            return GoalResponse.REJECT
        if request.track_id <= 0:
            self.get_logger().warning(f"goal 거부: track_id={request.track_id}")
            return GoalResponse.REJECT
        self._busy = True  # 두 번째 goal 이 끼어들지 못하게 여기서 세운다
        return GoalResponse.ACCEPT

    def _on_cancel(self, handle: Any) -> CancelResponse:
        """취소는 받기만 한다. 처리는 타이머가 handle.is_cancel_requested 를 보고 한다."""
        return CancelResponse.ACCEPT

    async def _execute(self, handle: Any) -> TrackAndGrasp.Result:
        """goal 상태를 만들고 결과 봉투를 기다린다. 실제 일은 _on_tick 이 한다."""
        ctx: GoalCtx | None = None
        try:
            state, actions = fsm.start()
            now = self._now()
            ctx = GoalCtx(
                handle=handle,
                goal_id=bytes(handle.goal_id.uuid).hex(),
                track_id=handle.request.track_id,
                state=state,
                start=now,
                vision_since=now,
                phase_t={state.phase: now},  # 첫 PREPARE 진입 = goal 시작 (U9-c)
                phase_seen=state.phase,
            )
            if self._rot_on:
                self._start_rotate(ctx, now)  # S2-T18 회전 하위 상태 시작
            self._ctx = ctx
            self._handle_actions(ctx, actions, now)
            self._send_feedback(ctx)
            grasped, reason, attempts = await ctx.done  # 타이머가 채울 때까지 기다림
            if reason == fsm.OK:
                handle.succeed()
            elif reason == fsm.CANCELED:
                handle.canceled()  # 취소 요청이 있을 때만 이 reason 이 나온다
            else:
                handle.abort()
            return self._result(grasped, reason, attempts)
        finally:
            self._execute_cleanup(ctx)

    def _start_rotate(self, ctx: GoalCtx, now: float) -> None:
        """기준 공구 yaw 를 정할 수 있으면 정하고(노드 기동 뒤 첫 goal), COLLECT 로."""
        self._try_home_ref(now)
        ctx.rot = rotate.RotState(rotate.COLLECT, t_goal=now)

    def _pose_ok(self, now: float) -> bool:
        """공구 자세가 유효하고 신선한가: 값 있음 · 기울기 ≤ 5° · 마지막 수신이 외삽 상한 안."""
        rx_age = now - self._pose[1] if self._pose else math.inf
        return (
            self._yaw_value is not None
            and self._tilt is not None
            and self._tilt <= rotate.TILT_MAX
            and rx_age <= self._rot_cfg.extrap_max_s
        )

    def _try_home_ref(self, now: float) -> None:
        """기준 공구 yaw 가 없고, 이 노드가 아직 한 번도 돌지 않았고, 자세가 유효할 때만 지금 공구 yaw 로.

        돈 뒤(되돌리기 실패로 손목이 돌아간 채일 수 있음)에는 새로 잡지 않는다 → 그 goal 들은
        rotate.pre_checks 가 NO_POSE_YAW 로 돌리지 않는다 (주관 검수 a).
        """
        if self._home_ref is not None or self._rot_ever or not self._pose_ok(now):
            return
        self._home_ref = self._yaw_value[0]
        self.get_logger().info(
            f"회전 기준 공구 yaw = {math.degrees(self._home_ref):.2f}° (노드 기동 뒤 첫 goal)"
        )

    def _execute_cleanup(self, ctx: GoalCtx | None) -> None:
        """비정상으로 빠져나왔을 때 busy 가 영구히 남지 않게 한다."""
        if ctx is None:
            self._busy = False  # goal 상태도 못 만들었다
        elif not ctx.done.done():
            # 결과 없이 빠져나왔다: 내부 예외로 끝낸다 (GOAL_END 로그·0 유지 포함)
            self._finish(ctx, fsm.DEVICE_ERROR, "INTERNAL_EXCEPTION", False, self._now())

    @staticmethod
    def _result(grasped: bool, reason: str, attempts: int) -> TrackAndGrasp.Result:
        """action result 메시지."""
        result = TrackAndGrasp.Result()
        result.grasped = grasped
        result.reason = reason
        result.attempts = attempts
        return result

    def _send_feedback(self, ctx: GoalCtx) -> None:
        """phase 가 바뀌었을 때만 보낸다 (feedback 은 phase 하나, #102·PR #103)."""
        if ctx.state.phase == ctx.last_phase:
            return
        feedback = TrackAndGrasp.Feedback()
        feedback.phase = ctx.state.phase
        ctx.handle.publish_feedback(feedback)
        ctx.last_phase = ctx.state.phase

    # ------------------------------------------------------------------ 30 Hz 타이머

    def _on_tick(self) -> None:
        """한 틱: (0 유지 | IDLE | goal 진행) 중 하나."""
        now = self._now()
        if self._hold_until is not None:
            self._tick_hold(now)
            return
        ctx = self._ctx
        if ctx is None:
            return  # IDLE: 발행·로그 없음
        try:
            self._tick_goal(ctx, now)
        except Exception as exc:  # 예외 경로: 0 발행 → 봉투·0 유지가 최우선
            self.get_logger().error(f"틱 예외: {exc!r}")
            self._safe_zero()
            if self._ctx is ctx:
                self._finish(ctx, fsm.DEVICE_ERROR, "INTERNAL_EXCEPTION", False, now)

    def _tick_goal(self, ctx: GoalCtx, now: float) -> None:
        """goal 진행 틱: 이벤트 → 전이 → 행동 → 발행 → 로그."""
        ev = self._build_event(ctx, now)
        tr = fsm.step(
            ctx.state,
            ev,
            self._p("grasp.hold_width_min_mm"),
            self._p("grasp.hold_width_max_mm"),
            self._p("retry.max_attempts"),
        )
        tr = self._diagnose(ctx, tr, now)  # U9-c: 로그 값 + LOST 세부 원인 (전이·제어 불변)
        if tr.terminal or tr.state.stopping:
            ctx.wz = 0.0  # 끝·취소면 각속도 즉시 0 (S2-T18)
        self._note_retreat(ctx, ev, tr, now)  # U9b: 재시도 여유·후퇴 끝 기록, 정상 들기 경고
        ctx.state = tr.state
        self._handle_actions(ctx, tr.actions, now)
        cfg = self._ctrl
        ctx.dt = control.effective_dt(ctx.last_calc, now, cfg.dt_nominal)  # ① dt 먼저
        ctx.last_calc = now  # ② 그 다음 갱신
        # ③ 새 phase 기준 속도. stopping·terminal 이면 command 첫 줄에서 항상 0
        ctx.cmd = control.command(
            tr.state.phase,
            tr.state.stopping,
            tr.terminal,
            ctx.geo,
            self._last_cmd,
            ctx.dt,
            cfg,
            retreat=fsm.is_retreat(tr.state),  # 안전 후퇴면 xy 는 retreat_xy (U9b)
            hold_z=tr.state.hold_z,  # 개방 기다리는 동안 높이 유지
            z_floor=ctx.rot_floor,  # 회전 중 z 하한 (S2-T18, off 면 None)
        )
        vel = tuple(float(x) for x in ctx.cmd.vel)
        t_pub = self._publish(vel, ctx.wz)
        self._send_feedback(ctx)
        tick = ls.make_tick(**self._tick_values(ctx, ev, tr, now, t_pub, vel))
        self._write_log(self._tick_log, tick)
        if tr.attempt_ended:
            self._write_log(self._attempt_log, ls.to_attempt(tick, ls.ATTEMPT_END))
        if tr.terminal:
            self._write_log(self._attempt_log, ls.to_attempt(tick, ls.GOAL_END))
            self._finish(ctx, tr.reason, tr.cause, tr.grasped, now, goal_end_logged=True)

    def _note_retreat(
        self, ctx: GoalCtx, ev: fsm.TickEvent, tr: fsm.Transition, now: float
    ) -> None:
        """재시도 여유 판단값·후퇴로 끝났나를 기록하고, 정상 들기가 늦으면 경고 1회 (U9b-dd 4절)."""
        if tr.retry_room_ok is not None:  # GRASP 실패를 판단한 틱
            ctx.retry_room_ok = tr.retry_room_ok
        if (
            tr.terminal
        ):  # 후퇴를 끝까지 했으면 True, 후퇴 중 다른 이유로 끝나면 False, 후퇴 없으면 None
            was_retreat = fsm.is_retreat(ctx.state)  # 전이 전 상태
            ctx.retreat_done = True if tr.retreat_done else (False if was_retreat else None)
        normal_lift = tr.state.phase == fsm.LIFT and not fsm.is_retreat(tr.state)
        if ev.lift_overstay and normal_lift and not ctx.lift_warned:
            # 박스를 쥔 성공 경로는 끊지 않는다 — 원인을 보이게만 (재검 r1 MAJOR-2)
            lifted = now - ctx.lift_since if ctx.lift_since is not None else float("nan")
            self.get_logger().warning(
                f"들기 체류 {lifted:.2f} s > 상한 {self._lift_max_s:.2f} s — 로봇 속도·펜던트 "
                "오버라이드 확인 (goal 은 계속)"
            )
            ctx.lift_warned = True

    @staticmethod
    def _retreat_values(ctx: GoalCtx, state: fsm.FsmState) -> dict[str, Any]:
        """로그 후퇴·재시도 4키 (U9b-dd 5절)."""
        stage = None
        if fsm.is_retreat(state):
            stage = "OPENING" if state.hold_z else "RISING"  # 개방 기다림 / 올라가는 중
        return {
            "retreat": stage,
            "retreat_reason": state.exit_reason,
            "retreat_done": ctx.retreat_done,
            "retry_room_ok": ctx.retry_room_ok,
        }

    def _tick_hold(self, now: float) -> None:
        """goal 종료 뒤 0 유지 틱: 0 발행 + 로그, 시간이 다 되면 busy 해제."""
        try:
            t_pub = self._publish(ZERO)
            if self._last_goal is not None:
                values = self._snapshot_values(self._last_goal, now, t_pub, "ZERO_HOLD", False)
                self._write_log(self._tick_log, ls.make_tick(**values))
        except Exception as exc:
            self.get_logger().error(f"0 유지 틱 예외: {exc!r}")
        if now >= self._hold_until:
            self._hold_until = None
            self._busy = False

    def _build_event(self, ctx: GoalCtx, now: float) -> fsm.TickEvent:
        """이번 틱의 사실들을 모은다: 보정 TCP → 사각 → 입력 끊김 → 기하·전환 플래그 → 그리퍼."""
        cfg = self._ctrl
        entry = self._boxes.get(ctx.track_id)
        tcp_est = self._tcp_estimate(now)  # (보정 TCP, 지평, 잘림) 또는 None
        obs = entry.last_valid if entry else None  # 마지막 유효 관측 (사각 구간 예측에 씀)
        obs_xyz = self._obs_xyz(obs)
        tcp_z = float(tcp_est[0][2]) if tcp_est else None
        top_z = float(obs_xyz[2]) if obs_xyz is not None else None
        # 사각 판정에도 보정 TCP z 를 쓴다 (U2 DD 0절 — 모든 플래그가 같은 TCP 를 보게)
        blind = fsm.is_vision_blind(
            ctx.state.phase, tcp_z, top_z, self._p("z.vision_cutoff_above_top_mm"), ctx.blind
        )
        if ctx.blind and not blind:
            ctx.vision_since = now  # 사각 → 보임: LOST/STALE 시계를 다시 센다
        ctx.blind = blind
        # DESCEND 사각 시작 시각 (전이 전 phase 기준 — 사각 판정과 같은 기준)
        ctx.blind_since = fsm.blind_since_next(ctx.blind_since, ctx.state.phase, blind, now)
        # LIFT 상승 시작·개방 대기 시작 (전이 전 상태 기준, U9b)
        ctx.lift_since = fsm.lift_since_next(ctx.lift_since, ctx.state, now)
        ctx.hold_since = (ctx.hold_since or now) if ctx.state.hold_z else None
        box_lost, box_stale, pose_stale = fsm.input_flags(
            now,
            entry.rx if entry else None,
            entry.last_valid_rx if entry else None,
            entry.latest_invalid if entry else False,
            self._pose[1] if self._pose else None,
            ctx.start,
            ctx.vision_since,
            blind,
            self._p("input.lost_timeout_s"),
            self._p("input.stale_timeout_s"),
        )
        self._check_source(ctx, obs)
        # 보인다 = 사각 아님 + 이 트랙 최신 메시지 valid + 유효 관측 있음
        visible = (not blind) and entry is not None and not entry.latest_invalid
        visible = visible and obs_xyz is not None
        obs_stamp = stamp_s(obs.stamp) if obs is not None else None
        ctx.geo = (
            control.geometry(tcp_est, obs_xyz, obs_stamp, visible, now, cfg) if tcp_est else None
        )
        geo = ctx.geo
        gripper = None
        if not ctx.state.stopping:  # 취소 뒤에는 보지도, 재요청하지도 않는다 (U5 DD E2)
            gripper = self._poll_gripper(ctx, now)
        rot_ready = self._rot_tick(ctx, geo, now)  # S2-T18: 회전 한 틱 (off 면 True)
        return fsm.TickEvent(
            rot_ready=rot_ready,
            cancel_requested=bool(ctx.handle.is_cancel_requested),
            stop_result=self._poll_stop(ctx, now),
            box_lost=box_lost,
            box_stale=box_stale,
            pose_stale=pose_stale,
            vision_blind=blind,
            reach=geo.reach if geo else None,
            aligned=bool(geo.aligned) if geo else False,
            at_grasp_height=bool(geo.at_grasp_height) if geo else False,
            at_lift_height=bool(geo.at_lift_height) if geo else False,
            gripper=gripper,
            grasp_room=self._grasp_room(geo),
            blind_overstay=fsm.blind_overstay(ctx.blind_since, now, self._blind_max_s),
            retry_room=self._retry_room(geo),
            hold_expired=self._hold_expired(ctx, geo, now),
            lift_overstay=fsm.lift_overstay(ctx.lift_since, now, self._lift_max_s),
        )

    def _rot_tick(self, ctx: GoalCtx, geo: control.Geometry | None, now: float) -> bool:
        """회전 하위 상태 한 틱 → 정렬 허용 여부. 예외면 이 goal 의 회전을 끄고 정지 확인 뒤 허용."""
        ctx.rot_floor, ctx.rot_warn = None, None
        if not self._rot_on or ctx.rot is None:
            return True  # 회전 off — 지금과 같다
        try:
            if ctx.rot.state == rotate.COLLECT:
                self._try_home_ref(now)  # goal 수락 때 pose 가 없었으면 첫 틱들에서 (돌기 전에만)
            inp = self._rot_inputs(ctx, geo, now)
            ctx.rot_io = (inp.psi_raw, inp.psi_est, inp.w_meas)
            if ctx.rot_dead:  # 예외로 끈 goal: 0 을 내고 실제로 멈춘 것이 2틱 이어지면 진행
                ctx.wz = 0.0
                still = inp.w_meas is not None and abs(inp.w_meas) < self._rot_cfg.still
                ctx.rot_still_n = ctx.rot_still_n + 1 if still else 0
                return ctx.rot_still_n >= rotate.STILL_TICKS
            out = rotate.rot_step(ctx.rot, inp, self._rot_cfg)
        except Exception as exc:  # 회전 계산이 goal 을 끊지 않게 (DD 12절)
            if not ctx.rot_dead:
                self.get_logger().error(
                    f"회전 예외 — 이 goal 의 회전을 끄고 정지 확인 뒤 진행: {exc!r}"
                )
            ctx.rot_dead, ctx.wz = True, 0.0
            ctx.rot = replace(ctx.rot, cause=rotate.INTERNAL)
            return False
        ctx.rot, ctx.wz, ctx.rot_floor, ctx.rot_warn = out.state, out.wz, out.z_floor, out.warn
        if out.state.state == rotate.ROTATING:
            self._rot_ever = True  # 이제부터 기준을 새로 잡지 않는다
        if out.warn == rotate.ACC_MISMATCH:
            a = math.degrees(out.state.alpha_eff)
            self.get_logger().warning(
                f"회전 가속이 설정보다 느림 — 측정 {a:.0f}°/s² 로 제동 "
                "(gateway servo_acc[1] ≥ rotate.alpha_dps2 확인)"
            )
        return out.ready

    def _rot_inputs(
        self, ctx: GoalCtx, geo: control.Geometry | None, now: float
    ) -> rotate.RotInputs:
        """회전 한 틱에 넘길 사실들 (pseudo r2 8절). geo 가 없으면 기하 값은 None."""
        cfg = self._rot_cfg
        hist = self._yaw_hist.get(ctx.track_id) if ctx.rot.state == rotate.COLLECT else None
        yaws = [y for _, y in hist] if hist else []  # 결정용 프레임 (COLLECT 일 때만)
        cur = self._yaw_value
        psi_raw = cur[0] if cur else None
        psi_est = None
        if cur is not None:  # 지금으로 외삽 (TCP 위치 외삽과 같은 규칙)
            psi_est = rotate.yaw_estimate(
                cur[0], cur[1], cfg.lag_s, self._last_wz, now, cfg.extrap_max_s
            )
        rx_age = now - self._pose[1] if self._pose else math.inf  # 마지막 pose 수신 나이
        pose_ok = self._pose_ok(now)
        return rotate.RotInputs(
            now=now,
            phase=ctx.state.phase,
            retreat=fsm.is_retreat(ctx.state),
            hold_z=ctx.state.hold_z,
            yaws=yaws,
            has_field=self._yaw_field,
            home_ref=self._home_ref,
            psi_raw=psi_raw,
            psi_est=psi_est,
            tilt=self._tilt,
            pose_ok=pose_ok,
            w_meas=rotate.omega_meas(self._yaw_prev, cur, now, rx_age, cfg.pose_fresh_s),
            wz_prev=self._last_wz,
            dt=control.effective_dt(ctx.last_calc, now, self._ctrl.dt_nominal),  # 이번 틱 dt
            err_along=_as_float(geo.err_along) if geo else None,
            tcp_z=float(geo.tcp[2]) if geo else None,
            top_z=_as_float(geo.top_z) if geo else None,
        )

    def _rot_values(self, ctx: GoalCtx, terminal: bool) -> dict[str, Any]:
        """틱 로그의 회전 키 12개 (회전 off 면 전부 None)."""
        if not self._rot_on or ctx.rot is None:
            return dict.fromkeys(ls.ROT_KEYS)
        psi_raw, psi_est, w_meas = ctx.rot_io
        wz = 0.0 if terminal else ctx.wz
        return rotate.log_values(
            ctx.rot, wz, w_meas, psi_raw, psi_est, terminal, ctx.rot_warn, self._rot_cfg.tol
        )

    def _retry_room(self, geo: control.Geometry | None) -> bool:
        """지금 TCP x 에서 재시도 1회를 끝낼 x 여유가 있나. TCP 를 모르면 False = 후퇴 (U9b)."""
        cfg = self._ctrl
        return control.retry_room_ok(
            float(geo.tcp[0]) if geo is not None else None,  # 보정 TCP x (다른 판정과 같은 TCP)
            self._retry_need_s,
            float(np.linalg.norm(cfg.belt_v)),
            cfg,
            float(self._p("grasp.room_margin_mm")) / 1000.0,  # mm → m
        )

    def _hold_expired(self, ctx: GoalCtx, geo: control.Geometry | None, now: float) -> bool:
        """개방 대기가 상한(닫힘 상한 대용)을 넘었거나 TCP 가 x_max 에 닿았나 (U9b-dd 2.4, 재검 r1)."""
        if ctx.hold_since is None:
            return False  # 개방을 기다리고 있지 않다
        limit_s = float(self._p("grasp.close_time_max_s"))  # 개방 시간 미측정 → 닫힘 상한을 대용
        waited = now - ctx.hold_since > limit_s  # 같으면 아직 (다른 상한과 같은 규칙)
        at_end = geo is not None and float(geo.tcp[0]) >= self._ctrl.x_max  # x 끝 가드
        return waited or at_end

    def _grasp_room(self, geo: control.Geometry | None) -> bool:
        """정렬 순간 하강·닫힘을 끝낼 x 여유가 있나 (TCP 를 모르면 True — 그때는 정렬도 안 된다)."""
        if geo is None:
            return True
        cfg = self._ctrl
        return grip.grasp_room_ok(
            float(geo.tcp[0]),  # 보정 TCP x (다른 판정과 같은 TCP, U5 DD E6)
            cfg.x_max,
            float(np.linalg.norm(cfg.belt_v)),
            self._room_need_s,
            float(self._p("grasp.room_margin_mm")) / 1000.0,  # mm → m
        )

    def _tcp_estimate(self, now: float) -> tuple[np.ndarray, float, bool] | None:
        """최신 pose → control.tcp_now (pose 없음·NaN 이면 None)."""
        if self._pose_value is None:
            return None
        position, stamp = self._pose_value  # stamp = 이 값이 처음 온 메시지의 stamp (실제보다 늦음)
        pose = control.finite_vec(position)
        if pose is None:
            return None  # NaN pose 는 없는 것으로
        cfg = self._ctrl
        return control.tcp_now(
            pose, stamp, cfg.pose_lag_s, self._last_cmd, now, cfg.pose_extrap_max_s
        )

    @staticmethod
    def _obs_xyz(obs: BoxTrack | None) -> np.ndarray | None:
        """유효 관측의 position_base → 배열 (없으면 None)."""
        if obs is None:
            return None
        p = obs.position_base
        return control.finite_vec((p.x, p.y, p.z))

    def _check_source(self, ctx: GoalCtx, obs: BoxTrack | None) -> None:
        """goal 중 좌표 출처가 바뀌면 경고만 (예측 리셋은 U9, U2 HLD 4절 규칙 8)."""
        if obs is None:
            return
        src = int(obs.position_source)
        if ctx.source is not None and src != ctx.source:
            self.get_logger().warning(
                f"goal 중 position_source 변경 {ctx.source}→{src} — 예측 리셋은 U9"
            )
        ctx.source = src

    # ------------------------------------------------------------------ 진단 (U9-c, 로그 전용)

    def _diagnose(self, ctx: GoalCtx, tr: fsm.Transition, now: float) -> fsm.Transition:
        """로그용 진단 값을 채우고, LOST 면 세부 원인을 찾는다. 실패해도 goal 은 계속한다."""
        try:
            if ctx.phase_t_next is not None:  # 지난 틱에 재시도로 예약한 새 시도 시각
                ctx.phase_t, ctx.phase_t_next = ctx.phase_t_next, None
            entry = self._boxes.get(ctx.track_id)
            new_obs = self._push_obs(ctx, entry)  # 관측열에 새 점이 들어갔나
            v_meas = diagnose.measured_velocity(
                self._pose_prev_value, self._pose_value, now, diagnose.POSE_HOLD_MAX_S
            )
            cmd_speed = float(np.linalg.norm(self._last_cmd))  # 직전 틱에 발행한 명령 크기
            ctx.stall_n = diagnose.stall_count(ctx.stall_n, cmd_speed, diagnose.speed_of(v_meas))
            est, span = self._speed_estimate(ctx, new_obs)
            self._record_phase(ctx, tr, now)
            ctx.diag = {
                "tcp_vel_meas_mps": v_meas,
                "belt_speed_est_mps": est,
                "belt_speed_est_span_s": span,
                "cause_fsm": tr.cause,  # 덮어쓰기 전 fsm 의 cause (매 틱)
                "box_pub_count": None,  # LOST 틱에서만 조회
            }
            if tr.reason == fsm.LOST:
                tr = self._refine_lost(ctx, tr, entry)
            if tr.terminal:  # goal 끝: 벨트 속도 추정 한 줄 (B안, 로그 전용)
                note = diagnose.speed_note(est, self._belt_speed(), span, len(ctx.obs_hist))
                self.get_logger().info(note)
        except Exception as exc:  # 진단이 제어를 끊지 않게 (재검 F6)
            ctx.diag = {}  # 이번 틱 진단 값은 null 로
            if tr.attempt_ended:  # 재시도 틱이면 새 시도 준비는 빠뜨리지 않는다 (재검 R2)
                ctx.phase_t_next = {fsm.PREPARE: now}
                ctx.obs_hist.clear()
                ctx.speed_run = 0
            if not ctx.diag_failed:
                self.get_logger().error(f"진단 예외 (goal 은 계속): {exc!r}")
                ctx.diag_failed = True
        return tr

    def _push_obs(self, ctx: GoalCtx, entry: BoxEntry | None) -> bool:
        """내 트랙의 새 유효 관측을 관측열에 넣는다. 넣었으면 True."""
        obs = entry.last_valid if entry else None
        xyz = self._obs_xyz(obs)
        if obs is None or xyz is None:
            return False  # 유효 관측이 없음
        st = stamp_s(obs.stamp)  # 촬영 시각
        if ctx.obs_hist and st <= ctx.obs_hist[-1][0]:
            return False  # 이미 넣은 관측 (틱 사이에 새 메시지가 없었다)
        ctx.obs_hist.append((st, xyz))
        return True

    def _belt_speed(self) -> float:
        """설정 벨트 속도 크기 m/s (FF 에 쓰는 값)."""
        return float(np.linalg.norm(self._ctrl.belt_v))

    def _speed_estimate(self, ctx: GoalCtx, new_obs: bool) -> tuple[float | None, float | None]:
        """벨트 속도 추정 + 큰 차이가 이어지면 WARN 1회 (B안 10 %). FF 에는 쓰지 않는다."""
        est, span = control.belt_speed_fit(
            ctx.obs_hist,
            self._ctrl.belt_dir_xy,
            diagnose.FIT_MAX_POINTS,
            diagnose.FIT_MIN_POINTS,
            diagnose.FIT_MIN_SPAN_S,
        )
        belt = self._belt_speed()
        ctx.speed_run, fire = diagnose.speed_warn_step(
            ctx.speed_run, ctx.speed_warned, est, belt, span, new_obs, diagnose.SPEED_WARN_RATIO
        )
        if fire and est is not None and span is not None:
            self.get_logger().warning(diagnose.speed_warn_text(est, belt, span))
            ctx.speed_warned = True
        return est, span

    @staticmethod
    def _record_phase(ctx: GoalCtx, tr: fsm.Transition, now: float) -> None:
        """이 시도의 phase 진입 시각. 재시도면 새 시도는 다음 틱에 바꿔 넣는다 (재검 F1)."""
        phase = tr.state.phase
        if phase != ctx.phase_seen:
            ctx.phase_t.setdefault(phase, now)  # 이 시도에서 처음 들어간 시각만
        if tr.attempt_ended:
            # 이 틱의 틱·ATTEMPT_END 행은 끝난 시도의 시각을 담아야 한다 → 지금 지우지 않는다
            ctx.phase_t_next = {fsm.PREPARE: now}
            ctx.obs_hist.clear()  # 실패한 파지가 박스를 밀었을 수 있다 (재검 F13)
            ctx.speed_run = 0
        ctx.phase_seen = phase

    def _refine_lost(
        self, ctx: GoalCtx, tr: fsm.Transition, entry: BoxEntry | None
    ) -> fsm.Transition:
        """LOST 의 세부 원인. 특정 원인이 있을 때만 cause 를 바꾼다 (fsm.py 는 그대로)."""
        pubs = self._box_publishers()
        ctx.diag["box_pub_count"] = pubs
        cause = diagnose.lost_cause(pubs, entry.rx if entry else None, ctx.other_rx, ctx.stall_n)
        return replace(tr, cause=cause) if cause else tr  # 없으면 fsm cause 유지 (U9-a 호환)

    def _box_publishers(self) -> int | None:
        """/voss/vision/box 발행자 수 (조회 실패면 None)."""
        try:
            return int(self.count_publishers(BOX_TOPIC))
        except Exception:
            return None

    # ------------------------------------------------------------------ 행동·서비스

    def _handle_actions(self, ctx: GoalCtx, actions: tuple[str, ...], now: float) -> None:
        """FSM 이 시킨 행동을 한다."""
        for action in actions:
            if action == fsm.REQUEST_STOP:
                self._request_stop(ctx, now)
            elif action in grip.ACTION_KIND:
                self._request_gripper(ctx, action, now)
            else:
                self.get_logger().warning(f"모르는 행동 {action}")

    def _request_gripper(self, ctx: GoalCtx, action: str, now: float) -> None:
        """FSM 행동 → 새 그리퍼 요청을 만들어 보낸다 (기다리지 않는다)."""
        kind, width = grip.request_for(
            action, self._p("gripper.pre_open_mm"), self._p("gripper.grasp_width_mm")
        )
        # attempts 는 전이 뒤 값 (CLOSE 는 이번 시도 번호, OPEN 은 0)
        force = self._p("gripper.force_n")
        seq = ctx.grip_seq + 1  # 이 goal 의 다음 순번
        call = grip.new_call(ctx.goal_id, ctx.state.attempts, kind, width, force, seq, now)
        self._send_gripper(ctx, call, now)

    def _send_gripper(self, ctx: GoalCtx, call: grip.GripCall, now: float) -> None:
        """call_async 로 보내고 future 를 보관한다 (처음·BUSY 재요청 공통). 콜백은 달지 않는다 (DD E8).

        서비스가 없으면 보내지 않고 다음 틱에 실패(GRIPPER_UNAVAILABLE)로 넘긴다 (HLD D5) — 재요청도 같다.
        """
        ctx.grip_seq = (
            call.seq
        )  # 보낸(또는 보내려던) 순번 = 이 goal 의 마지막 순번 (BUSY 재요청 포함)
        if not self._gripper_cli.service_is_ready():
            ctx.grip_call, ctx.grip_future = None, None  # 기다릴 호출이 없다
            ctx.grip_ready_reply = grip.unavailable_reply()  # 다음 틱 FSM 이 DEVICE_ERROR 로 끝낸다
            ctx.grip_log = grip.call_record(call, grip.UNAVAILABLE, now, code=grip.UNAVAILABLE)
            self.get_logger().error(
                f"gripper 서비스 없음 — {call.kind} seq={call.seq} 요청 못 보냄"
            )
            return
        req = Gripper.Request()
        req.width = float(call.width_mm)  # mm
        req.force = float(call.force_n)  # N
        ctx.grip_future = self._gripper_cli.call_async(req)
        ctx.grip_call = call
        ctx.grip_log = grip.call_record(call, grip.PENDING, call.sent_s)
        self.get_logger().info(
            f"gripper 요청 {call.kind} {call.width_mm:.1f} mm {call.force_n:.1f} N "
            f"seq={call.seq} attempt={call.attempt}"
        )

    @staticmethod
    def _raw_of(fut: Any) -> tuple[bool, grip.RawReply | None, bool, str]:
        """future → (끝났나, 응답, 예외로 끝났나, 예외 글). ROS 응답을 순수 모듈용으로 옮긴다."""
        if fut is None or not fut.done():
            return False, None, False, ""
        try:
            resp = fut.result()
            raw = grip.RawReply(
                bool(resp.ok), float(resp.width_actual), bool(resp.grip_detected), str(resp.message)
            )
            return True, raw, False, ""
        except Exception as exc:  # 서비스 호출 자체가 실패 → COMM_ERROR 로 본다 (DD E3)
            return True, None, True, repr(exc)

    def _poll_gripper(self, ctx: GoalCtx, now: float) -> fsm.GripperReply | None:
        """기다리던 그리퍼 호출을 들여다본다. 결론이 났으면 FSM 에 넘길 응답, 아니면 None.

        BUSY 재요청(0.5 s 뒤 1회)은 여기서 나간다 — _build_event 가 부르므로 틱마다 한 번.
        """
        if ctx.grip_ready_reply is not None:  # 요청 순간 정해진 응답(서비스 없음)을 한 번 넘긴다
            reply, ctx.grip_ready_reply = ctx.grip_ready_reply, None
            return reply
        call = ctx.grip_call
        if call is None:
            return None  # 기다리는 호출이 없다
        done, raw, failed, exc_text = self._raw_of(ctx.grip_future)
        res = grip.poll(call, done, raw, failed, now, self._p("gripper_timeout_s"))
        if res.status == grip.PENDING:
            return None
        if res.status == grip.BUSY_WAIT:  # BUSY 첫 번째: 조금 기다렸다 한 번 더 (HLD D3)
            self.get_logger().warning(
                f"gripper BUSY — {grip.BUSY_RETRY_DELAY_S} s 뒤 한 번 더 {call.kind} seq={call.seq}"
            )
            ctx.grip_call = grip.busy_marked(call, now)
            ctx.grip_future = None  # BUSY 응답은 소비했다 (고아로 세지 않게)
            ctx.grip_log = grip.call_record(
                ctx.grip_call, grip.BUSY_WAIT, now, code=res.code, raw=res.raw_message
            )
            return None
        if res.status == grip.RETRY:
            self._send_gripper(ctx, grip.retried(call, now), now)
            return None
        # 여기부터 REPLY 또는 TIMED_OUT: 이 호출은 끝 → 기다리는 호출을 비운다
        if res.status == grip.TIMED_OUT:
            self._orphan_gripper(ctx)  # 비우면서, 나중에 오는 응답은 버린 것으로 세게 한다
        else:
            ctx.grip_call, ctx.grip_future = None, None  # 응답을 받았으니 그냥 비운다
        verdict = None
        if call.kind in (grip.CLOSE, grip.VERIFY):  # 개방 응답은 판정하지 않는다 (DD E14)
            verdict = fsm.judge_grip(
                res.reply, self._p("grasp.hold_width_min_mm"), self._p("grasp.hold_width_max_mm")
            )[0]
        ctx.grip_log = grip.call_record(
            call, res.status, now, res.reply, res.code, res.raw_message or exc_text or None, verdict
        )
        self._log_grip_reply(call, res, exc_text)
        return res.reply

    def _log_grip_reply(self, call: grip.GripCall, res: grip.PollResult, exc_text: str) -> None:
        """응답 한 줄 로그. INVALID 는 설정 오류로 따로 알린다 (HLD D3)."""
        r = res.reply
        line = (
            f"gripper 응답 {call.kind} seq={call.seq} → {res.code} "
            f"폭 {r.width_mm:.1f} mm grip {r.grip_detected} (원문: {res.raw_message or exc_text})"
        )
        if res.code == "INVALID":
            self.get_logger().error(line + " — 설정 오류(폭·힘) 확인")
        elif not r.ok or res.code != "OK":
            self.get_logger().warning(line)
        else:
            self.get_logger().info(line)

    def _orphan_gripper(self, ctx: GoalCtx) -> None:
        """기다리던 호출을 내려놓는다 (취소는 못 한다). 나중에 오는 응답은 버리고 센다 (HLD D7, DD E8)."""
        call, fut = ctx.grip_call, ctx.grip_future
        ctx.grip_call, ctx.grip_future = None, None
        if call is not None and fut is not None:
            # 이미 끝난 future 면 곧바로 불린다 (응답이 와 있었지만 소비하지 않음 = 버림)
            fut.add_done_callback(lambda f, c=call: self._on_grip_late(c, f))

    def _on_grip_late(self, call: grip.GripCall, fut: Any) -> None:
        """고아 호출의 응답 = 무조건 버린다. 세고 한 줄 남긴다."""
        try:
            self.grip_late_discarded += 1
            _, raw, failed, exc_text = self._raw_of(fut)
            code = "COMM_ERROR" if failed or raw is None else grip.message_code(raw.message)
            text = exc_text if failed or raw is None else raw.message
            self.get_logger().info(
                f"gripper_late_discarded goal={call.goal_id} attempt={call.attempt} "
                f"kind={call.kind} seq={call.seq} code={code} message={text}"
            )
        except Exception as exc:  # 콜백 예외로 노드가 죽지 않게
            self.get_logger().error(f"_on_grip_late 예외: {exc!r}")

    def _request_stop(self, ctx: GoalCtx, now: float) -> None:
        """gateway 에 정지를 요청한다 (기다리지 않는다)."""
        if not self._stop_cli.service_is_ready():
            ctx.stop_result = fsm.StopResult(fsm.STOP_UNAVAILABLE)  # 서비스가 없다
            return
        ctx.stop_future = self._stop_cli.call_async(Trigger.Request())
        ctx.stop_sent = now

    def _poll_stop(self, ctx: GoalCtx, now: float) -> fsm.StopResult | None:
        """stop 결과를 확인한다. 아직이면 None."""
        if ctx.stop_result is not None:
            return ctx.stop_result
        fut = ctx.stop_future
        if fut is not None and fut.done():
            try:
                resp = fut.result()
                status = fsm.STOP_OK if resp.success else fsm.STOP_FAILED
                ctx.stop_result = fsm.StopResult(status, resp.message)
            except Exception:
                ctx.stop_result = fsm.StopResult(fsm.STOP_FAILED, "EXCEPTION")
        elif ctx.stop_sent is not None and now - ctx.stop_sent > self._p("stop_timeout_s"):
            ctx.stop_result = fsm.StopResult(fsm.STOP_TIMEOUT)
        return ctx.stop_result

    # ------------------------------------------------------------------ 종료

    def _finish(
        self,
        ctx: GoalCtx,
        reason: str,
        cause: str,
        grasped: bool,
        now: float,
        goal_end_logged: bool = False,
    ) -> None:
        """goal 을 끝낸다: 경고 로그 → 스냅샷 → (GOAL_END 로그) → 0 유지 시작 → 봉투 채우기."""
        if reason != fsm.OK:
            stop_failed = cause.startswith("STOP_") and cause != "STOP_OK"
            note = " (정지 요청 응답 없음/오류)" if stop_failed else ""
            self.get_logger().warning(f"goal 종료 reason={reason} cause={cause}{note}")
        if ctx.retreat_done is None and fsm.is_retreat(ctx.state):
            ctx.retreat_done = False  # 후퇴 중 예외·노드 종료로 끝남 (정상 틱 경로는 _note_retreat)
        self._last_goal = {
            "goal_id": ctx.goal_id,
            "track_id": ctx.track_id,
            "attempt": ctx.state.attempts,
            "phase": ctx.state.phase,
            "reason": reason,
            "cause": cause,
            "grasped": grasped,
            "gripper": ctx.grip_log,  # 마지막 그리퍼 호출 기록 (GOAL_END 스냅샷에도)
            "phase_t": dict(ctx.phase_t),  # 마지막 시도의 단계 시각 (스냅샷 행에도, U9-c)
            "retreat": self._retreat_values(ctx, ctx.state),  # 후퇴·재시도 4키 (스냅샷 행에도, U9b)
            "rot": self._rot_values(ctx, True),  # 회전 키 (스냅샷 행에도, S2-T18 r1-1)
        }
        # 진행 중 그리퍼 호출은 취소하지 않고 내려놓는다 → 응답이 오면 버린다 (HLD D7, 자동 개방 금지)
        self._orphan_gripper(ctx)
        if not goal_end_logged:
            self._log_goal_end_snapshot(now)  # 예외 경로도 게이트 분모(GOAL_END)에 남긴다
        if self._ctx is ctx:
            self._ctx = None
        self._start_hold(now)
        if not ctx.done.done():
            ctx.done.set_result((grasped, reason, ctx.state.attempts))  # _execute 가 깨어난다

    def _start_hold(self, now: float) -> None:
        """0 유지 구간을 시작한다. busy 는 구간이 끝날 때 해제된다."""
        hold = self.values.get("zero_hold_s") or 0.0
        self._hold_until = now + float(hold)

    # ------------------------------------------------------------------ 발행·로그

    def _publish(self, vel: tuple[float, float, float], wz: float = 0.0) -> float:
        """TwistStamped 발행 (TCP 선속도 m/s, 베이스 Z 각속도 rad/s, base_link). 발행 시각을 돌려준다.

        wz 는 J6 회전 틱만 넘긴다 (S2-T18). 0 유지·예외·종료 경로는 인자 없이 불러 각속도 0.
        """
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z = vel
        msg.twist.angular.z = float(wz)  # x·y 는 늘 0
        self._last_wz = float(wz)
        self._cmd_pub.publish(msg)
        self._last_cmd = np.array(vel, dtype=float)  # 0 유지·예외 경로 포함 모든 발행을 기억
        return stamp_s(msg.header.stamp)

    def _safe_zero(self) -> None:
        """예외·종료 경로의 0 발행. 실패해도 예외를 내지 않는다."""
        try:
            self._publish(ZERO)
        except Exception as exc:
            self.get_logger().error(f"0 발행 실패: {exc!r}")

    def _write_log(self, writer: ls.JsonlWriter, record: dict[str, Any]) -> None:
        """로그 한 줄. 실패해도 goal 은 계속하고 경고는 한 번만."""
        try:
            writer.write(record)
        except Exception as exc:
            if not self._log_fail_warned:
                self.get_logger().error(f"로그 쓰기 실패 — 게이트 증거 누락: {writer.path} {exc!r}")
                self._log_fail_warned = True

    def _common_values(self) -> dict[str, Any]:
        """모든 틱에 같은 설정 값."""
        speed = self.values.get("belt.speed_cmps")
        belt_mps = speed / 100.0 if speed is not None else None  # cm/s → m/s
        # 제어(FF)에 실제로 쓴 벨트 속도 벡터와 같은 값 (수평 정규화, z = 0). READY 아니면 None
        belt_vel = _as_list(self._ctrl.belt_v) if self._ctrl is not None else None
        return {
            "belt_vel_mps": belt_vel,
            "belt_speed_mps": belt_mps,
            "z_profile": self._ctrl.z_profile if self._ctrl is not None else None,  # S2-T14
            "config_version": self.values.get("config_version"),
            "config_sha256": self.values.get("config_sha256"),
            "params_sha256": self.params_sha256,
        }

    def _input_values(self, track_id: int | None) -> dict[str, Any]:
        """box·pose 관측 값 (없으면 None)."""
        entry = self._boxes.get(track_id) if track_id is not None else None
        box = entry.msg if entry else None
        pose = self._pose[0] if self._pose else None
        p = box.position_base if box else None
        t = pose.pose.position if pose else None
        yaw_deg, yaw_ok = yaw_log_values(box)  # position_base_m 과 같은 메시지의 yaw
        return {
            "box_stamp_s": stamp_s(box.stamp) if box else None,
            "box_rx_s": entry.rx if entry else None,
            "box_u_px": float(box.u) if box else None,  # 같은 메시지의 픽셀 (U9-c)
            "box_v_px": float(box.v) if box else None,
            "pose_stamp_s": stamp_s(pose.header.stamp) if pose else None,
            "pose_rx_s": self._pose[1] if self._pose else None,
            "position_base_m": [p.x, p.y, p.z] if p else None,
            "position_valid": bool(box.position_valid) if box else None,
            "position_source": int(box.position_source) if box else None,
            "calib_version": box.calib_version if box else None,
            "yaw_base_deg": yaw_deg,  # S2-T18 0단계: 관측 기록만
            "yaw_valid": yaw_ok,
            "tcp_pose_m": [t.x, t.y, t.z] if t else None,
        }

    @staticmethod
    def _stop_text(stop: fsm.StopResult | None) -> str | None:
        """stop 결과를 로그 문자열로 ("FAILED:TIMEOUT" 처럼)."""
        if stop is None:
            return None
        return f"{stop.status}:{stop.message}" if stop.message else stop.status

    def _tick_values(
        self,
        ctx: GoalCtx,
        ev: fsm.TickEvent,
        tr: fsm.Transition,
        now: float,
        t_pub: float,
        vel: tuple[float, float, float],
    ) -> dict[str, Any]:
        """goal 진행 틱의 로그 값."""
        return {
            "event": None,
            "goal_id": ctx.goal_id,
            "track_id": ctx.track_id,
            "attempt": tr.state.attempts,
            "phase": tr.state.phase,
            "stopping": tr.state.stopping,
            "terminal": tr.terminal,
            "t_calc_s": now,
            "t_pub_s": t_pub,
            "cmd_vel_mps": list(vel),
            "vision_blind": ev.vision_blind,
            "box_lost": ev.box_lost,
            "box_stale": ev.box_stale,
            "pose_stale": ev.pose_stale,
            "cancel_requested": ev.cancel_requested,
            "stop_result": self._stop_text(ev.stop_result),
            "reason": tr.reason,
            "cause": tr.cause,
            "grasped": tr.grasped,
            "gripper": ctx.grip_log,  # 진행 중 또는 마지막 끝난 호출 (U5 DD 4절)
            **self._diag_values(ctx, now),
            **self._retreat_values(ctx, tr.state),
            **self._phase_t_values(ctx.phase_t),
            **self._rot_values(ctx, tr.terminal),  # S2-T18 회전 키
            **self._control_values(ctx, ev),
            **self._input_values(ctx.track_id),
            **self._common_values(),
        }

    def _diag_values(self, ctx: GoalCtx, now: float) -> dict[str, Any]:
        """U9-c 진단 로그 값. 진단이 실패한 틱은 ctx.diag 값(측정 속도·추정·pub 수·cause_fsm)만 null."""
        entry = self._boxes.get(ctx.track_id)
        valid_rx = entry.last_valid_rx if entry else None
        d = ctx.diag
        return {
            "obs_rx_age_s": now - valid_rx if valid_rx is not None else None,  # 수신 기준 나이
            "other_box_rx_age_s": now - ctx.other_rx if ctx.other_rx is not None else None,
            "box_pub_count": d.get("box_pub_count"),
            "tcp_vel_meas_mps": d.get("tcp_vel_meas_mps"),
            "stall_ticks": ctx.stall_n,
            "belt_speed_est_mps": d.get("belt_speed_est_mps"),
            "belt_speed_est_span_s": d.get("belt_speed_est_span_s"),
            "cause_fsm": d.get("cause_fsm"),
        }

    @staticmethod
    def _phase_t_values(phase_t: dict[str, float]) -> dict[str, Any]:
        """단계 진입 시각 6키 (아직 안 들어간 단계는 null)."""
        return {key: phase_t.get(phase) for phase, key in ls.PHASE_T_KEYS.items()}

    @staticmethod
    def _control_values(ctx: GoalCtx, ev: fsm.TickEvent) -> dict[str, Any]:
        """U2 제어 계산 값 (없으면 null). NumPy 는 list·float·bool 로 바꿔 JSON 에 넣는다."""
        geo, cmd = ctx.geo, ctx.cmd
        return {
            "predicted_m": _as_list(geo.p_pred) if geo else None,
            "tcp_target_m": _as_list(cmd.tcp_target) if cmd else None,
            "error_m": _as_list(cmd.error) if cmd else None,
            "clamped": bool(cmd.clamped) if cmd else False,
            "cmd_rule": cmd.rule if cmd else None,
            "tcp_now_m": _as_list(geo.tcp) if geo else None,
            "tcp_extrap_s": float(geo.tcp_horizon_s) if geo else None,
            "tcp_extrap_capped": bool(geo.tcp_extrap_capped) if geo else None,
            "predict_horizon_s": _as_float(geo.pred_horizon_s) if geo else None,
            "predict_dt_clipped": bool(geo.dt_clipped) if geo else None,
            "obs_age_s": _as_float(geo.obs_age_s) if geo else None,
            "visible": bool(geo.visible) if geo else None,
            "err_along_m": _as_float(geo.err_along) if geo else None,
            "err_cross_m": _as_float(geo.err_cross) if geo else None,
            "dt_s": ctx.dt,
            "aligned": ev.aligned,
            "at_grasp_height": ev.at_grasp_height,
            "at_lift_height": ev.at_lift_height,
            "reach": ev.reach,
            "z_v_cmd_mps": _as_float(cmd.z_v_req) if cmd else None,  # clamp 전 z 요구 (S2-T14)
        }

    def _snapshot_values(
        self, g: dict[str, Any], now: float, t_pub: float | None, cause: str, terminal: bool
    ) -> dict[str, Any]:
        """goal 스냅샷 기준 로그 값 (0 유지 틱 / 예외 경로의 GOAL_END 에 쓴다)."""
        return {
            "event": None,
            "goal_id": g.get("goal_id"),
            "track_id": g.get("track_id"),
            "attempt": g.get("attempt"),
            "phase": g.get("phase"),
            "stopping": False,
            "terminal": terminal,
            "t_calc_s": now,
            "t_pub_s": t_pub,
            "predicted_m": None,
            "tcp_target_m": None,
            "error_m": None,
            "cmd_vel_mps": list(ZERO),
            "clamped": False,
            "cmd_rule": control.ZERO_STOP,  # 0 유지·예외 경로
            **{k: None for k in SNAPSHOT_NULL_KEYS},  # U2 계산 값은 이 경로에 없다
            "vision_blind": None,
            "box_lost": None,
            "box_stale": None,
            "pose_stale": None,
            "cancel_requested": None,
            "stop_result": None,
            "reason": g.get("reason"),
            "cause": cause,  # ZERO_HOLD = 종료 뒤 0 유지 구간 표시
            "grasped": g.get("grasped"),
            "gripper": g.get("gripper"),
            **{k: None for k in DIAG_KEYS},  # 진단 값은 fsm 틱에만 (cause_fsm 도 null, 재검 F8)
            **{k: (g.get("retreat") or {}).get(k) for k in RETREAT_KEYS},  # goal 끝 때 값 (U9b)
            **self._phase_t_values(g.get("phase_t") or {}),
            **{k: (g.get("rot") or {}).get(k) for k in ls.ROT_KEYS},  # goal 끝 때 회전 값 (S2-T18)
            **self._input_values(g.get("track_id")),
            **self._common_values(),
        }

    def _log_goal_end_snapshot(self, now: float) -> None:
        """정상 틱을 거치지 않고 끝난 goal(예외 경로)의 틱·GOAL_END 를 스냅샷으로 남긴다."""
        try:
            g = self._last_goal or {}
            tick = ls.make_tick(**self._snapshot_values(g, now, None, g.get("cause", ""), True))
            self._write_log(self._tick_log, tick)
            self._write_log(self._attempt_log, ls.to_attempt(tick, ls.GOAL_END))
        except Exception as exc:
            self.get_logger().error(f"GOAL_END 스냅샷 기록 실패: {exc!r}")

    def _finish_on_shutdown(self) -> None:
        """진행 중인 goal 을 cause NODE_SHUTDOWN 으로 끝낸다 (reason 은 계약 7종 중 DEVICE_ERROR).

        이렇게 하지 않으면 노드가 내려가며 실행 코루틴이 정리될 때 INTERNAL_EXCEPTION 으로 남아
        게이트 로그에서 진짜 내부 오류와 구분되지 않는다 (10/09 SIGINT 스모크).
        """
        ctx = self._ctx
        if ctx is None or ctx.done.done():
            return
        try:
            self._finish(ctx, fsm.DEVICE_ERROR, "NODE_SHUTDOWN", False, self._now())
        except Exception as exc:  # 종료 경로는 계속 간다 (0 발행이 더 중요)
            self.get_logger().error(f"종료 중 goal 정리 실패: {exc!r}")

    def destroy_node(self) -> None:
        """종료: 0 을 한 번 보내고(best-effort) 파일을 닫는다.

        Ctrl+C·SIGTERM 은 main() 이 context 를 살려 둔 채 여기로 오게 한다(0 이 실제로 나간다).
        프로세스가 강제로 죽으면(SIGKILL 등) 0 이 나가지 않으므로 그때의 정지는
        robot_gateway watchdog 책임이다 (ADR-0010 조건 2·리스크).
        """
        self._finish_on_shutdown()  # goal 중이면 원인을 남기고 끝낸다 (로그 파일이 열려 있을 때)
        if self.ready:
            self._safe_zero()  # READY 가 아니면 한 번도 발행하지 않았으므로 보낼 것도 없다
        self._tick_log.close()
        self._attempt_log.close()
        super().destroy_node()


def _ignore_stop_signals() -> None:
    """정리(0 발행·로그 닫기) 중에 오는 SIGINT·SIGTERM 은 무시한다."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def _on_stop_signal(signum: int, frame: Any) -> None:
    """첫 SIGINT·SIGTERM: 뒤따르는 신호를 먼저 막고 KeyboardInterrupt 로 정리 경로에 보낸다.

    래퍼 timeout 은 프로세스 그룹에 SIGINT 를, ros2 launch 는 자식에 SIGINT 를 한 번 더(그 뒤 5 s 에 SIGTERM)
    보낸다. 막지 않으면 destroy_node 가 0 을 보내는 도중 두 번째 KeyboardInterrupt 로 죽는다 (U3 실측).
    처리기 안에서 바로 막아 "첫 신호 → finally 진입" 사이의 틈도 없앤다.
    """
    _ignore_stop_signals()
    raise KeyboardInterrupt


def main(args: list[str] | None = None) -> None:
    # rclpy 기본 시그널 처리기(ALL)는 Ctrl+C·SIGTERM 때 context 를 먼저 내려 버려서
    # destroy_node 의 마지막 0 발행이 "context is invalid" 로 실패했다 (10/09 U2 스모크에서 발견).
    # → 처리기를 끄고 KeyboardInterrupt 로 받아, context 가 살아 있을 때 0 을 먼저 보낸다.
    #   30 Hz 타이머가 대기를 깨우므로 신호는 늦어도 한 틱(33 ms) 안에 처리된다.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, _on_stop_signal)
    signal.signal(signal.SIGTERM, _on_stop_signal)
    node = BeltServoNode()
    try:
        rclpy.spin(node)  # 단일 executor (DEC-14)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        _ignore_stop_signals()  # 신호가 아닌 종료 경로에서도 정리 중에는 끊기지 않게
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
