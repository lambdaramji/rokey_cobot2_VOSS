"""belt_servo — 컨베이어 박스 추종·파지 노드 (U1 뼈대: 속도는 항상 0).

계약 (docs/interfaces/topics.md belt_servo 행, voss_msgs.md TrackAndGrasp 행):
- 구독 /voss/vision/box (BoxTrack: position_base = 촬영 시각 관측 박스 윗면 중심 m, base_link),
       /voss/robot/pose (PoseStamped, TCP, base_link, stamp = 응답 수신 시각). best_effort·volatile.
- 발행 /voss/robot/servo_cmd (TwistStamped, TCP 선속도 m/s, frame base_link, 각속도 0) 30 Hz.
- 액션 /voss/servo/track_and_grasp. READY 일 때만 서버를 만들고, 바쁘면 reject. goal 1개당 result 1건.
- 서비스 호출 /voss/robot/stop (취소 시), /voss/robot/gripper (U5).
- ADR-0010: speedl 은 스트림이 끊겨도 마지막 속도로 계속 간다 → 어떤 종료든 마지막 명령은 0.
구조 (design/U1-hld.md): 콜백은 최신값만 보관 → 30 Hz 타이머 한 곳에서 판단·발행·로그.
판단 로직은 순수 모듈 params·fsm·log_schema 에 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.task import Future
from std_srvs.srv import Trigger

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack
from voss_msgs.srv import Gripper
from voss_servo import fsm
from voss_servo import log_schema as ls
from voss_servo.params import PARAM_SPECS, check_params, params_digest, ready_log_line

# QoS (topics.md QoS 표). box 구독 depth 5 는 소비자 재량: 박스마다 메시지가 따로 와서
# depth 1 이면 같은 프레임의 다른 박스 메시지에 내 박스가 밀려날 수 있다 (depth 는 QoS 호환 조건 아님)
QOS_BOX = QoSProfile(
    depth=5, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
)
QOS_FAST = QoSProfile(
    depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
)
BOX_PRUNE_S = 2.0  # 이만큼 갱신 없는 다른 트랙 항목은 지운다 (파라미터와 무관한 상수)
DEFAULT_RATE_HZ = 30.0  # rate_hz 가 없을 때 (READY 아님) 타이머 주기
ZERO = (0.0, 0.0, 0.0)  # 속도 0


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
    last_phase: str = ""  # 마지막으로 feedback 보낸 phase
    stop_future: Any = None  # stop 서비스 call_async 결과
    stop_sent: float | None = None  # stop 요청 보낸 시각
    stop_result: fsm.StopResult | None = None  # 정해진 stop 결과


class BeltServoNode(Node):
    """U1: 기동 검사·액션 골격·30 Hz 0 속도 발행·로그."""

    def __init__(self) -> None:
        super().__init__("belt_servo")
        self._ctx: GoalCtx | None = None  # 진행 중 goal
        self._last_goal: dict[str, Any] | None = None  # 끝난 goal 스냅샷 (0 유지 틱 로그용)
        self._busy = False  # goal 진행 중 또는 0 유지 중
        self._hold_until: float | None = None  # 0 유지 끝 시각
        self._boxes: dict[int, BoxEntry] = {}  # track_id 별 최신 관측
        self._pose: tuple[PoseStamped, float] | None = None  # (최신 pose, 받은 시각)
        self.values = self._declare_params()  # {이름: 값 또는 None}
        self.ready = self._startup_check()  # READY 여부 (기동 때 한 번)
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
        else:
            # 어떤 키가 문제인지 이름으로. READY 가 아니면 액션 서버를 만들지 않는다 (_setup_ros)
            self.get_logger().error(ready_log_line(report) + " — 액션 서버 미생성")
        return report.ready

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
        self.create_subscription(BoxTrack, "/voss/vision/box", self._on_box, QOS_BOX)
        self.create_subscription(PoseStamped, "/voss/robot/pose", self._on_pose, QOS_FAST)
        self._cmd_pub = self.create_publisher(TwistStamped, "/voss/robot/servo_cmd", QOS_FAST)
        self._stop_cli = self.create_client(Trigger, "/voss/robot/stop")
        self._gripper_cli = self.create_client(Gripper, "/voss/robot/gripper")  # 호출은 U5
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
            valid = bool(msg.position_valid)
            last_valid = msg if valid else (prev.last_valid if prev else None)
            last_valid_rx = now if valid else (prev.last_valid_rx if prev else None)
            self._boxes[msg.track_id] = BoxEntry(msg, now, not valid, last_valid, last_valid_rx)
            self._prune_boxes(now)
        except Exception as exc:  # 콜백 예외로 노드가 죽지 않게
            self.get_logger().error(f"_on_box 예외: {exc!r}")

    def _prune_boxes(self, now: float) -> None:
        """오래 갱신 안 된 다른 트랙 항목을 지운다 (현재 goal 트랙은 남긴다)."""
        keep = self._ctx.track_id if self._ctx else None
        old = [t for t, e in self._boxes.items() if t != keep and now - e.rx > BOX_PRUNE_S]
        for t in old:
            del self._boxes[t]

    def _on_pose(self, msg: PoseStamped) -> None:
        """최신 TCP pose 와 받은 시각만 보관한다."""
        try:
            self._pose = (msg, self._now())
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
            )
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
        ctx.state = tr.state
        self._handle_actions(ctx, tr.actions, now)
        vel = ZERO  # U2: stopping·terminal 이 아닐 때만 control 계산으로 바꾼다
        t_pub = self._publish(vel)
        self._send_feedback(ctx)
        tick = ls.make_tick(**self._tick_values(ctx, ev, tr, now, t_pub, vel))
        self._write_log(self._tick_log, tick)
        if tr.attempt_ended:
            self._write_log(self._attempt_log, ls.to_attempt(tick, ls.ATTEMPT_END))
        if tr.terminal:
            self._write_log(self._attempt_log, ls.to_attempt(tick, ls.GOAL_END))
            self._finish(ctx, tr.reason, tr.cause, tr.grasped, now, goal_end_logged=True)

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
        """이번 틱의 사실들을 모은다. U2·U5 몫(reach·aligned·높이·gripper)은 기본값."""
        entry = self._boxes.get(ctx.track_id)
        tcp_z = self._pose[0].pose.position.z if self._pose else None
        top_z = entry.last_valid.position_base.z if entry and entry.last_valid else None
        blind = fsm.is_vision_blind(
            ctx.state.phase, tcp_z, top_z, self._p("z.vision_cutoff_above_top_mm"), ctx.blind
        )
        if ctx.blind and not blind:
            ctx.vision_since = now  # 사각 → 보임: LOST/STALE 시계를 다시 센다
        ctx.blind = blind
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
        return fsm.TickEvent(
            cancel_requested=bool(ctx.handle.is_cancel_requested),
            stop_result=self._poll_stop(ctx, now),
            box_lost=box_lost,
            box_stale=box_stale,
            pose_stale=pose_stale,
            vision_blind=blind,
        )

    # ------------------------------------------------------------------ 행동·서비스

    def _handle_actions(self, ctx: GoalCtx, actions: tuple[str, ...], now: float) -> None:
        """FSM 이 시킨 행동을 한다."""
        for action in actions:
            if action == fsm.REQUEST_STOP:
                self._request_stop(ctx, now)
            else:
                self.get_logger().debug(f"{action}: U5 에서 구현")  # 그리퍼 호출은 U5

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
        self._last_goal = {
            "goal_id": ctx.goal_id,
            "track_id": ctx.track_id,
            "attempt": ctx.state.attempts,
            "phase": ctx.state.phase,
            "reason": reason,
            "cause": cause,
            "grasped": grasped,
        }
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

    def _publish(self, vel: tuple[float, float, float]) -> float:
        """TwistStamped 발행 (TCP 선속도 m/s, base_link, 각속도 0). 발행 시각을 돌려준다."""
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z = vel
        self._cmd_pub.publish(msg)  # 각속도는 기본값 0
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
        direction = self.values.get("belt.direction_base")
        belt_mps = speed / 100.0 if speed is not None else None  # cm/s → m/s
        belt_vel = [belt_mps * d for d in direction] if belt_mps is not None and direction else None
        return {
            "belt_vel_mps": belt_vel,
            "belt_speed_mps": belt_mps,
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
        return {
            "box_stamp_s": stamp_s(box.stamp) if box else None,
            "box_rx_s": entry.rx if entry else None,
            "pose_stamp_s": stamp_s(pose.header.stamp) if pose else None,
            "pose_rx_s": self._pose[1] if self._pose else None,
            "position_base_m": [p.x, p.y, p.z] if p else None,
            "position_valid": bool(box.position_valid) if box else None,
            "position_source": int(box.position_source) if box else None,
            "calib_version": box.calib_version if box else None,
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
            "predicted_m": None,  # U2
            "tcp_target_m": None,  # U2
            "error_m": None,  # U2
            "cmd_vel_mps": list(vel),
            "clamped": False,  # U2
            "vision_blind": ev.vision_blind,
            "box_lost": ev.box_lost,
            "box_stale": ev.box_stale,
            "pose_stale": ev.pose_stale,
            "cancel_requested": ev.cancel_requested,
            "stop_result": self._stop_text(ev.stop_result),
            "reason": tr.reason,
            "cause": tr.cause,
            "grasped": tr.grasped,
            "gripper": None,  # U5: {ok, width_actual_mm, grip_detected, message}
            **self._input_values(ctx.track_id),
            **self._common_values(),
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
            "vision_blind": None,
            "box_lost": None,
            "box_stale": None,
            "pose_stale": None,
            "cancel_requested": None,
            "stop_result": None,
            "reason": g.get("reason"),
            "cause": cause,  # ZERO_HOLD = 종료 뒤 0 유지 구간 표시
            "grasped": g.get("grasped"),
            "gripper": None,
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

    def destroy_node(self) -> None:
        """종료: 0 을 한 번 보내고(best-effort) 파일을 닫는다.

        프로세스가 죽거나 Ctrl+C 로 컨텍스트가 먼저 내려가면 0 이 나가지 않을 수 있다.
        그때의 정지는 robot_gateway watchdog 책임이다 (ADR-0010 조건 2·리스크).
        """
        if self.ready:
            self._safe_zero()  # READY 가 아니면 한 번도 발행하지 않았으므로 보낼 것도 없다
        self._tick_log.close()
        self._attempt_log.close()
        super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = BeltServoNode()
    try:
        rclpy.spin(node)  # 단일 executor (DEC-14)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
