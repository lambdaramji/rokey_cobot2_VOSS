"""sort_manager — 분류 작업 관리자. 인터페이스는 docs/interfaces/topics.md·voss_msgs.md.

전이 규칙은 `sort_fsm`(순수 함수), 준비 판단은 `readiness`. 이 노드는 입출력과 장비 호출 시간 초과만 맡는다.
콜백은 단일 스레드 executor 에서 차례로 돈다 → FSM 에 잠금이 필요 없다.

실행은 사람이 비상정지 옆에서 한다(TrackAndGrasp·MoveToZone·stop 을 부른다):
  ros2 launch voss_manager sort_manager.launch.py
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections import deque
from datetime import datetime

import rclpy
import yaml
from builtin_interfaces.msg import Time
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger

from voss_manager import sort_fsm as fsm
from voss_manager.readiness import ITEMS, ReadyInputs, ReadyLimits, log_warning, not_ready
from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import (
    BoxTrack,
    Intent,
    LabelRead,
    RobotState,
    SortResult,
    SortState,
    ZoneMap,
    ZoneMapEntry,
)
from voss_msgs.srv import Command, MoveToZone

DEFAULT_CONFIG_PATH = os.path.join(
    os.environ.get("VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/config")),
    "voss_config.yaml",
)


def _qos(depth: int, reliable: bool = True, latched: bool = False) -> QoSProfile:
    return QoSProfile(
        depth=depth,
        reliability=ReliabilityPolicy.RELIABLE if reliable else ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.TRANSIENT_LOCAL if latched else DurabilityPolicy.VOLATILE,
    )


def _ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


def _time(ns: int) -> Time:
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


class SortManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("sort_manager")
        p = self.declare_parameter
        self.config_path = p("config_path", DEFAULT_CONFIG_PATH).value
        self.check_label_stamp = p("check_label_stamp", True).value
        self.track_fresh_s = p("track_fresh_s", 0.5).value
        self.stop_timeout_s = p("stop_timeout_s", 3.0).value
        self.move_timeout_s = p("move_timeout_s", 60.0).value
        self.goal_response_timeout_s = p("goal_response_timeout_s", 5.0).value
        self.goal_result_timeout_s = p("goal_result_timeout_s", 120.0).value
        self.state_period_s = p("state_period_s", 0.4).value
        self.limits = ReadyLimits(
            pose_max_age_s=p("pose_max_age_s", 0.5).value,
            robot_state_max_age_s=p("robot_state_max_age_s", 1.5).value,
            log_max_age_s=p("log_max_age_s", 3.0).value,
        )
        home_first = p("home_first", True).value

        with open(self.config_path, "rb") as f:
            raw = f.read()
        cfg = fsm.load_config(yaml.safe_load(raw))  # 어긋나면 ValueError → 기동 거부
        self.ctx = fsm.new_ctx(cfg, home_first=home_first)
        self.get_logger().info(
            f"voss_config {self.config_path} version {cfg.version} sha256 {hashlib.sha256(raw).hexdigest()[:12]}, "
            f"구역 칸 {cfg.capacity}, confidence_min {cfg.confidence_min}, home_first {home_first}"
        )

        # 발행
        self.state_pub = self.create_publisher(SortState, "/voss/sort/state", _qos(10))
        self.result_pub = self.create_publisher(SortResult, "/voss/sort/result", _qos(10))
        self.zone_map_pub = self.create_publisher(
            ZoneMap, "/voss/sort/zone_map", _qos(1, latched=True)
        )
        self.say_pub = self.create_publisher(String, "/voss/voice/say", _qos(10))

        # 구독
        self.create_subscription(
            BoxTrack, "/voss/vision/box", self._on_box, _qos(10, reliable=False)
        )
        self.create_subscription(LabelRead, "/voss/vision/label", self._on_label, _qos(10))
        self.create_subscription(Intent, "/voss/voice/intent", self._on_intent, _qos(10))
        self.create_subscription(String, "/voss/log/status", self._on_log_status, _qos(1))
        self.create_subscription(
            PoseStamped, "/voss/robot/pose", self._on_pose, _qos(1, reliable=False)
        )
        self.create_subscription(
            RobotState, "/voss/robot/state", self._on_robot_state, _qos(1, latched=True)
        )

        # 서비스·액션
        self.create_service(Command, "/voss/sort/command", self._on_command)
        self.grasp_ac = ActionClient(self, TrackAndGrasp, "/voss/servo/track_and_grasp")
        self.move_cli = self.create_client(MoveToZone, "/voss/robot/move_to_zone")
        self.stop_cli = self.create_client(Trigger, "/voss/robot/stop")

        # 입력 기록
        self.tracks: dict[
            int, tuple[int, float]
        ] = {}  # track_id → (첫 BoxTrack 촬영 ns, 마지막 수신 monotonic)
        self.pose_rx = -1.0
        self.robot_state: RobotState | None = None
        self.robot_state_rx = -1.0
        self.log_status = ""
        self.log_rx = -1.0
        self.log_warned = ""
        self.nr: list[str] = list(ITEMS)  # 첫 tick 전에는 모두 미준비로 본다

        # 장비 호출: 한 번에 하나(goal 또는 이동) + stop. token 이 바뀌면 늦은 응답은 버린다
        self.token = 0
        self.dev: dict | None = None  # {kind, token, deadline, handle, cancel}
        self.stop_op: dict | None = None
        self.queue: deque = deque()
        self.pumping = False
        self.last_phase = ""
        self.last_pub_key: tuple = ()

        self._publish_zone_map()
        self.create_timer(0.1, self._tick)
        # 상태 주기 발행은 전용 타이머로 (0.1 s tick 에 얹으면 0.5 s 가 0.6 s 로 밀려 2 Hz 미만이 된다)
        self.create_timer(self.state_period_s, lambda: self._publish_state(force=True))

    # ------------------------------------------------------------ 시각·준비

    def _now_ns(self) -> int:
        return self.get_clock().now().nanoseconds

    def _ready_inputs(self) -> ReadyInputs:
        mono = time.monotonic()
        rs = self.robot_state

        def age(rx: float) -> float:
            return mono - rx if rx >= 0 else float("inf")

        return ReadyInputs(
            pose_age_s=age(self.pose_rx),
            move_srv=self.move_cli.service_is_ready(),
            robot_state_age_s=age(self.robot_state_rx),
            robot_connected=bool(rs and rs.connected),
            robot_state=rs.state if rs else "",
            robot_error=rs.error_code if rs else "",
            servo_server=self.grasp_ac.server_is_ready(),
            vision_pubs=self.count_publishers("/voss/vision/box"),
            ocr_pubs=self.count_publishers("/voss/vision/label"),
            log_age_s=age(self.log_rx),
            log_status=self.log_status,
        )

    def _update_ready(self) -> None:
        self.nr = not_ready(self._ready_inputs(), self.limits)

    # ------------------------------------------------------------ 입력

    def _on_box(self, msg: BoxTrack) -> None:
        first = self.tracks.get(msg.track_id, (_ns(msg.stamp), 0.0))[0]
        self.tracks[msg.track_id] = (first, time.monotonic())

    def _on_label(self, msg: LabelRead) -> None:
        now = self._now_ns()
        tr = self.tracks.get(msg.track_id)
        fresh = tr is not None and time.monotonic() - tr[1] <= self.track_fresh_s
        self._post(
            fsm.LabelSeen(
                track_id=msg.track_id,
                code=msg.code,
                dong=msg.dong,
                confidence=msg.confidence,
                stage=msg.stage,
                stamp_ns=_ns(msg.stamp) if self.check_label_stamp else now,
                raw_text=msg.raw_text,
                dong_alt=msg.dong_alt,
                now_ns=now,
                started_at_ns=tr[0] if tr else 0,
                track_fresh=fresh,
                not_ready=tuple(self.nr),
            )
        )

    def _on_intent(self, msg: Intent) -> None:
        cmd = fsm.intent_to_command(msg.type, msg.dong, msg.zone, msg.box_id)
        if cmd is None:
            self.get_logger().warn(f"intent {msg.type!r} 는 지원하지 않음 (raw: {msg.raw_text!r})")
            return
        ok, message = self._command(*cmd)
        self.get_logger().info(f"intent {msg.type} → {cmd[0]} {cmd[1]!r}: {ok} {message}")

    def _on_command(self, req: Command.Request, res: Command.Response) -> Command.Response:
        res.ok, res.message = self._command(req.command, req.arg)
        return res

    def _command(self, command: str, arg: str) -> tuple[bool, str]:
        self._update_ready()
        new_sid = ""
        if command.strip().lower() == "start":
            new_sid = fsm.make_session_id(datetime.now(), secrets.token_hex(2))
        reply = self._post(fsm.Command(command, arg, self._now_ns(), tuple(self.nr), new_sid))
        return reply or (False, "처리 안 됨")

    def _on_log_status(self, msg: String) -> None:
        self.log_status, self.log_rx = msg.data, time.monotonic()

    def _on_pose(self, _msg: PoseStamped) -> None:
        self.pose_rx = time.monotonic()

    def _on_robot_state(self, msg: RobotState) -> None:
        self.robot_state, self.robot_state_rx = msg, time.monotonic()

    # ------------------------------------------------------------ FSM 실행

    def _post(self, ev) -> tuple[bool, str] | None:
        """이벤트를 큐에 넣고 처리한다. 액션 실행 중 바로 생긴 이벤트는 큐 뒤로 간다."""
        self.queue.append(ev)
        if self.pumping:
            return None
        self.pumping = True
        reply, first = None, True
        try:
            while self.queue:
                out = fsm.step(self.ctx, self.queue.popleft())
                self.ctx = out.ctx
                if first:
                    reply, first = out.reply, False
                for a in out.actions:
                    self._run(a)
        finally:
            self.pumping = False
        self._publish_state()
        return reply

    def _run(self, a) -> None:
        log = self.get_logger()
        if isinstance(a, fsm.Log):
            # rclpy 는 호출 위치마다 심각도가 하나여야 한다 → 줄을 나눈다
            if a.level == "error":
                log.error(a.text)
            elif a.level == "warn":
                log.warn(a.text)
            else:
                log.info(a.text)
        elif isinstance(a, fsm.Result):
            self._publish_result(a)
        elif isinstance(a, fsm.Say):
            self.say_pub.publish(String(data=a.text))
        elif isinstance(a, fsm.SendGoal):
            self._send_goal(a.track_id)
        elif isinstance(a, fsm.CancelGoal):
            self._cancel_goal()
        elif isinstance(a, fsm.CallMove):
            self._call_move(a)
        elif isinstance(a, fsm.CallStop):
            self._call_stop()
        else:
            log.error(f"모르는 액션 {a}")

    def _new_op(self, kind: str, timeout_s: float) -> dict:
        self.token += 1
        return {
            "kind": kind,
            "token": self.token,
            "deadline": time.monotonic() + timeout_s,
            "handle": None,
            "cancel": False,
        }

    def _live(self, op: dict | None, token: int) -> bool:
        return op is not None and op["token"] == token

    # TrackAndGrasp
    def _send_goal(self, track_id: int) -> None:
        if not self.grasp_ac.server_is_ready():
            self._post(fsm.GoalDone(False, False, "", 0, self._now_ns()))
            return
        op = self.dev = self._new_op("goal", self.goal_response_timeout_s)
        self.last_phase = ""
        fut = self.grasp_ac.send_goal_async(
            TrackAndGrasp.Goal(track_id=track_id), feedback_callback=self._on_feedback
        )
        fut.add_done_callback(lambda f, t=op["token"]: self._on_goal_response(f, t))

    def _on_goal_response(self, fut, token: int) -> None:
        handle = fut.result()
        if not self._live(self.dev, token):
            if handle.accepted:
                self.get_logger().warn("시간 초과 뒤 늦게 수락된 goal 을 취소한다")
                handle.cancel_goal_async()
            return
        if not handle.accepted:
            self.dev = None
            self._post(fsm.GoalDone(False, False, "", 0, self._now_ns()))
            return
        self.dev["handle"] = handle
        self.dev["deadline"] = time.monotonic() + self.goal_result_timeout_s
        if self.dev["cancel"]:
            handle.cancel_goal_async()
        handle.get_result_async().add_done_callback(lambda f, t=token: self._on_goal_result(f, t))

    def _on_goal_result(self, fut, token: int) -> None:
        r = fut.result().result
        if not self._live(self.dev, token):
            self.get_logger().warn(
                f"시간 초과 뒤 늦은 TrackAndGrasp 결과 무시: {r.reason} grasped={r.grasped}"
            )
            return
        self.dev = None
        self._post(fsm.GoalDone(True, r.grasped, r.reason, r.attempts, self._now_ns()))

    def _on_feedback(self, fb) -> None:
        phase = fb.feedback.phase
        if phase != self.last_phase:
            self.last_phase = phase
            self.get_logger().info(
                f"servo {phase}"  # feedback 은 phase 만 (#102·#103, 오차는 belt_servo 로그)
            )

    def _cancel_goal(self) -> None:
        if self.dev is None or self.dev["kind"] != "goal":
            return
        self.dev["cancel"] = True
        if self.dev["handle"] is not None:
            self.dev["handle"].cancel_goal_async()

    # MoveToZone
    def _call_move(self, a: fsm.CallMove) -> None:
        if not self.move_cli.service_is_ready():
            self._post(fsm.MoveDone(False, "NO_SERVICE", 0, self._now_ns()))
            return
        op = self.dev = self._new_op("move", self.move_timeout_s)
        fut = self.move_cli.call_async(MoveToZone.Request(zone=a.zone, slot=a.slot, mode=a.mode))
        fut.add_done_callback(lambda f, t=op["token"], z=a.zone: self._on_move_response(f, t, z))
        self.get_logger().info(
            f"MoveToZone {a.zone} 칸 {a.slot} "
            + ("이동" if a.zone == "OBSERVE" else f"mode {a.mode or 'PLACE'}")
        )

    def _on_move_response(self, fut, token: int, zone: str) -> None:
        r = fut.result()
        if not self._live(self.dev, token):
            self.get_logger().error(
                f"시간 초과 뒤 늦은 MoveToZone({zone}) 응답: ok={r.ok} {r.message} placed_stamp={_ns(r.placed_stamp)} — 칸 수를 사람이 확인"
            )
            return
        self.dev = None
        self._post(fsm.MoveDone(r.ok, r.message, _ns(r.placed_stamp), self._now_ns()))

    # /voss/robot/stop
    def _call_stop(self) -> None:
        if not self.stop_cli.service_is_ready():
            self._post(fsm.StopDone(False, "NO_SERVICE", self._now_ns()))
            return
        op = self.stop_op = self._new_op("stop", self.stop_timeout_s)
        fut = self.stop_cli.call_async(Trigger.Request())
        fut.add_done_callback(lambda f, t=op["token"]: self._on_stop_response(f, t))

    def _on_stop_response(self, fut, token: int) -> None:
        r = fut.result()
        if not self._live(self.stop_op, token):
            self.get_logger().warn(f"시간 초과 뒤 늦은 stop 응답: {r.success} {r.message}")
            return
        self.stop_op = None
        self._post(fsm.StopDone(r.success, r.message, self._now_ns()))

    # ------------------------------------------------------------ 주기 처리

    def _tick(self) -> None:
        mono, now = time.monotonic(), self._now_ns()
        self._update_ready()

        if self.dev is not None and mono > self.dev["deadline"]:
            op, self.dev = self.dev, None
            if op["kind"] == "goal":
                self.get_logger().error("TrackAndGrasp 응답 시간 초과 → DEVICE_ERROR")
                if op["handle"] is not None:
                    op["handle"].cancel_goal_async()
                self._post(fsm.GoalDone(op["handle"] is not None, False, "DEVICE_ERROR", 0, now))
            else:
                self.get_logger().error("MoveToZone 응답 시간 초과")
                self._post(fsm.MoveDone(False, "TIMEOUT", 0, now))
        if self.stop_op is not None and mono > self.stop_op["deadline"]:
            self.stop_op = None
            self._post(fsm.StopDone(False, "TIMEOUT", now))

        warn = log_warning(self.log_status)
        if warn != self.log_warned:
            if warn:
                self.get_logger().warn(
                    f"sort_logger {warn} — 운전은 계속(MC-027), 이 회차는 G0 증거로 쓰지 않는다"
                )
            self.log_warned = warn

        for tid in [t for t, (_, rx) in self.tracks.items() if mono - rx > 10.0]:
            del self.tracks[tid]

    # ------------------------------------------------------------ 발행

    def _publish_state(self, force: bool = False) -> None:
        c = self.ctx
        nr = fsm.not_ready_items(c, self.nr)
        box_id = c.box.box_id if c.box else ""
        track_id = c.box.track_id if c.box else -1
        key = (c.state, box_id, track_id, c.session_id, tuple(nr))
        if not force and key == self.last_pub_key:
            return
        self.last_pub_key = key
        self.state_pub.publish(
            SortState(
                state=c.state,
                box_id=box_id,
                pending_question="",
                track_id=track_id,
                ready=not nr,
                not_ready=nr,
                session_id=c.session_id,
            )
        )

    def _publish_result(self, r: fsm.Result) -> None:
        self.result_pub.publish(
            SortResult(
                box_id=r.box_id,
                code=r.code,
                dong=r.dong,
                confidence=float(r.confidence),
                decided_by=r.decided_by,
                zone=r.zone,
                outcome=r.outcome,
                stamp=_time(r.stamp_ns),
                session_id=r.session_id,
                track_id=r.track_id,
                started_at=_time(r.started_at_ns),
                raw_text=r.raw_text,
                dong_alt=r.dong_alt,
                rule_version=r.rule_version,
                reason=r.reason,
                attempts=r.attempts,
            )
        )
        self.get_logger().info(
            f"SortResult {r.box_id} {r.outcome} {r.zone or '-'} reason={r.reason or '-'} attempts={r.attempts}"
        )

    def _publish_zone_map(self) -> None:
        entries = [
            ZoneMapEntry(dong=d, zone=z, code=c, aliases=a)
            for d, z, c, a in fsm.zone_map_entries(self.ctx.cfg)
        ]
        self.zone_map_pub.publish(ZoneMap(entries=entries, version=self.ctx.cfg.version))


def main(args=None) -> None:
    # Ctrl+C 를 파이썬 KeyboardInterrupt 로 받아 spin 도중 컨텍스트가 먼저 닫히는 경합을 피한다
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = SortManagerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
