"""G0 모의 상대 — 로봇 없이 sort_manager 를 끝까지 돌려 보는 개발용. 아무 장비도 움직이지 않는다.

진짜 노드가 아직 없는 쪽만 골라 띄운다. 같은 이름의 진짜 서버·발행자가 이미 있으면 그 부분은 띄우지 않는다.
**ROS_DOMAIN_ID 30(공용 PC 로봇 도메인)에서는 기동을 거부한다** — 진짜 로봇 옆에 가짜 pose·응답을 섞지 않도록
공용 PC 에서도 다른 도메인(예 77)에서만 쓴다.
  --servo   /voss/servo/track_and_grasp 액션 서버 (belt_servo 대역)
  --robot   /voss/robot/move_to_zone·/voss/robot/stop 서비스, /voss/robot/pose 50 Hz (robot_gateway 대역)
  --robot-state  (--robot 와 함께) /voss/robot/state 2 Hz + 바뀔 때 — 이동·서보 중 BUSY, 서보 끝난 뒤 0.7 s 더 BUSY
            (belt_servo 0 유지 + watchdog), stop 뒤 STOPPED. 없으면 sort_manager 는 ROBOT 과도 규칙(pose + 서비스)
  --log     /voss/log/status 1 Hz (sort_logger 대역)
  --vision  /voss/vision/box 30 Hz + /voss/vision/label stage 1 (box_tracker·label_reader 대역, 박스 1개)
  --read    /voss/vision/read_label 서비스 (label_reader 3단계 재판독 대역) — 재확인·질문 흐름 시험용

예 (개인 PC, ROS_DOMAIN_ID=31, 터미널 두 개):
  python3 tools/mock/g0_mock.py --servo --robot --log --vision --code S07-02 --dong 대치동
  python3 -m voss_manager.sort_manager   # 또는 ros2 launch voss_manager sort_manager.launch.py
  ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: start}"
"""

from __future__ import annotations

import argparse
import os
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack, LabelRead, RobotState
from voss_msgs.srv import MoveToZone, ReadLabel

BEST_EFFORT = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
RELIABLE = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


class G0Mock(Node):
    def __init__(self, a: argparse.Namespace) -> None:
        super().__init__("g0_mock")
        self.a = a
        self.cb = ReentrantCallbackGroup()
        time.sleep(1.0)  # 그래프 발견 대기 후 진짜 노드가 있는지 본다
        log = self.get_logger()

        if a.servo and self._free_action("/voss/servo/track_and_grasp"):
            ActionServer(
                self,
                TrackAndGrasp,
                "/voss/servo/track_and_grasp",
                execute_callback=self._execute,
                goal_callback=lambda _g: (
                    GoalResponse.REJECT if a.grasp == "REJECT" else GoalResponse.ACCEPT
                ),
                cancel_callback=lambda _g: CancelResponse.ACCEPT,
                callback_group=self.cb,
            )
            log.info(f"[servo] TrackAndGrasp 모의: {a.grasp}, {a.grasp_s} s")

        if a.robot and self._free_service("/voss/robot/move_to_zone"):
            self.create_service(
                MoveToZone, "/voss/robot/move_to_zone", self._move, callback_group=self.cb
            )
            log.info(f"[robot] MoveToZone 모의: {a.place}, {a.place_s} s")
        if a.read and self._free_service("/voss/vision/read_label"):
            self.create_service(
                ReadLabel, "/voss/vision/read_label", self._read, callback_group=self.cb
            )
            log.info(
                f"[read] ReadLabel 모의: {a.read_result} {a.read_code}/{a.read_dong} conf {a.read_conf}"
            )
        if a.robot and self._free_service("/voss/robot/stop"):
            self.create_service(Trigger, "/voss/robot/stop", self._stop, callback_group=self.cb)
            log.info("[robot] stop 모의")
        self.action, self.servo_tail, self.stopped = "", 0.0, False
        self.state_pub = None
        if a.robot and a.robot_state and self._free_topic("/voss/robot/state"):
            self.state_pub = self.create_publisher(
                RobotState,
                "/voss/robot/state",
                QoSProfile(
                    depth=1,
                    reliability=ReliabilityPolicy.RELIABLE,
                    durability=DurabilityPolicy.TRANSIENT_LOCAL,
                ),
            )
            self.create_timer(0.5, self._state, callback_group=self.cb)
            self.create_timer(0.05, self._state_tail, callback_group=self.cb)
            log.info("[robot] RobotState 2 Hz 모의 (BUSY·STOPPED·READY)")
        if a.robot and self._free_topic("/voss/robot/pose"):
            self.pose_pub = self.create_publisher(PoseStamped, "/voss/robot/pose", BEST_EFFORT)
            self.create_timer(0.02, self._pose, callback_group=self.cb)
            log.info("[robot] pose 50 Hz 모의")

        if a.log and self._free_topic("/voss/log/status"):
            self.log_pub = self.create_publisher(String, "/voss/log/status", QoSProfile(depth=1))
            self.create_timer(
                1.0, lambda: self.log_pub.publish(String(data=a.log_status)), callback_group=self.cb
            )
            log.info(f"[log] /voss/log/status {a.log_status} 1 Hz")

        if (
            a.vision
            and self._free_topic("/voss/vision/box")
            and self._free_topic("/voss/vision/label")
        ):
            self.box_pub = self.create_publisher(BoxTrack, "/voss/vision/box", BEST_EFFORT)
            self.label_pub = self.create_publisher(LabelRead, "/voss/vision/label", RELIABLE)
            self.vision_t0: float | None = None
            self.track_id = a.track_id
            self.create_timer(1 / 30, self._box, callback_group=self.cb)
            self.create_timer(0.5, self._label, callback_group=self.cb)
            log.info(
                f"[vision] track {a.track_id} {a.code}/{a.dong} conf {a.conf}, 박스는 {a.box_s} s 마다 새로 들어온다"
            )

    def _free_action(self, name: str) -> bool:
        """액션 서버는 <name>/_action/send_goal 서비스로 보인다."""
        return self._free_service(name + "/_action/send_goal")

    def _free_service(self, name: str) -> bool:
        # 서버만 센다(클라이언트만 있어도 이름 목록에는 보인다)
        busy = self.count_services(name) > 0
        if busy:
            self.get_logger().error(f"{name} 진짜 서비스가 이미 있다 — 모의를 띄우지 않는다")
        return not busy

    def _free_topic(self, name: str) -> bool:
        busy = self.count_publishers(name) > 0
        if busy:
            self.get_logger().error(f"{name} 진짜 발행자가 이미 있다 — 모의를 띄우지 않는다")
        return not busy

    # robot_gateway RobotState 대역 (state_logic.decide 와 같은 우선순위, 오류 없음)
    def _state(self) -> None:
        if self.state_pub is None:
            return
        action = self.action or ("SERVO" if time.monotonic() < self.servo_tail else "")
        msg = RobotState(connected=True, action=action, gripper_width_mm=90.0)
        msg.state = "BUSY" if action else ("STOPPED" if self.stopped else "READY")
        msg.header.stamp = self.get_clock().now().to_msg()
        self.state_pub.publish(msg)

    def _state_tail(self) -> None:
        if self.servo_tail and time.monotonic() >= self.servo_tail and not self.action:
            self.servo_tail = 0.0
            self._state()  # 서보 꼬리가 끝나면 READY 를 바로 알린다

    def _set_action(self, action: str) -> None:
        if action:
            self.stopped = False  # 새 모션 명령이 STOPPED 를 푼다
        self.action = action
        self._state()

    # belt_servo 대역
    def _execute(self, gh) -> TrackAndGrasp.Result:
        res = TrackAndGrasp.Result()
        self.get_logger().info(f"[servo] goal track {gh.request.track_id}")
        self._set_action("SERVO")
        try:
            return self._run_goal(gh, res)
        finally:
            self.servo_tail = (
                time.monotonic() + 0.7
            )  # belt_servo 0 유지 0.5 s + gateway watchdog 0.2 s
            self._set_action("")

    def _run_goal(self, gh, res: TrackAndGrasp.Result) -> TrackAndGrasp.Result:
        a = self.a
        phases = ["PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY"]
        t_end = time.monotonic() + a.grasp_s
        while time.monotonic() < t_end:
            if gh.is_cancel_requested:
                gh.canceled()
                res.grasped, res.reason, res.attempts = False, "CANCELED", 1
                return res
            k = int((1 - (t_end - time.monotonic()) / a.grasp_s) * len(phases))
            gh.publish_feedback(TrackAndGrasp.Feedback(phase=phases[min(k, 5)]))
            time.sleep(0.1)
        res.grasped, res.reason, res.attempts = a.grasp == "OK", a.grasp, a.attempts
        if a.grasp == "OK":
            gh.succeed()
        else:
            gh.abort()
        return res

    # robot_gateway 대역
    def _move(self, req: MoveToZone.Request, res: MoveToZone.Response) -> MoveToZone.Response:
        mode = "이동" if req.zone == "OBSERVE" else (req.mode or "PLACE")
        self.get_logger().info(f"[robot] MoveToZone {req.zone} 칸 {req.slot} {mode}")
        self._set_action(f"MOVE_TO_ZONE:{req.zone}")
        try:
            return self._run_move(req, res, mode)
        finally:
            self._set_action("")  # 진짜 gateway 처럼 응답 전에 READY 를 먼저 낸다

    def _run_move(
        self, req: MoveToZone.Request, res: MoveToZone.Response, mode: str
    ) -> MoveToZone.Response:
        a = self.a
        time.sleep(a.place_s if mode in ("PLACE", "PICK") else 0.5)
        if mode == "VIEW":  # 재확인 구역을 보는 자세로 이동만
            res.ok, res.message = (False, "INVALID view_pose null") if a.view_fail else (True, "OK")
            return res
        if mode == "PICK":  # 재확인 칸에서 집어 안전 높이로 — placed_stamp 0
            res.ok, res.message = (False, "GRIP_FAIL") if a.pick_fail else (True, "OK")
            return res
        if req.zone == "OBSERVE" or a.place == "ok":
            res.ok, res.message = True, "OK"
        else:
            res.ok, res.message = False, a.place
        if mode == "PLACE" and req.zone != "OBSERVE" and a.place in ("ok", "RETURN_FAILED"):
            res.placed_stamp = self.get_clock().now().to_msg()
        return res

    def _read(self, req: ReadLabel.Request, res: ReadLabel.Response) -> ReadLabel.Response:
        a = self.a
        self.get_logger().info(
            f"[read] ReadLabel track {req.track_id} 칸 {req.slot} → {a.read_result}"
        )
        time.sleep(0.5)
        if a.read_result == "fail":
            res.ok, res.message = False, "no_text"
            return res
        res.ok, res.message = True, ""
        res.label.track_id, res.label.stage = req.track_id, 3
        res.label.code, res.label.dong, res.label.dong_alt = a.read_code, a.read_dong, a.read_alt
        res.label.confidence = a.read_conf if a.read_result == "ok" else min(a.read_conf, 0.3)
        res.label.raw_text = f"{a.read_code}\n{a.read_dong}"
        res.label.stamp = self.get_clock().now().to_msg()
        return res

    def _stop(self, _req: Trigger.Request, res: Trigger.Response) -> Trigger.Response:
        self.get_logger().info("[robot] stop")
        res.success, res.message = not self.a.stop_fail, "TIMEOUT" if self.a.stop_fail else ""
        if res.success:
            self.stopped = True
            self._state()
        return res

    def _pose(self) -> None:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.pose.orientation.w = 1.0
        self.pose_pub.publish(msg)

    # box_tracker·label_reader 대역: box_s 마다 새 트랙 하나가 시야를 지나간다
    def _box(self) -> None:
        now = time.monotonic()
        if self.vision_t0 is None or now - self.vision_t0 > self.a.box_s:
            if self.vision_t0 is not None:
                self.track_id += 1
            self.vision_t0 = now
        if now - self.vision_t0 > self.a.box_s * 0.8:
            return  # 박스가 시야 밖으로 나감
        msg = BoxTrack(
            track_id=self.track_id, u=960.0, v=540.0, bbox=[900, 480, 120, 120], position_valid=True
        )
        msg.stamp = self.get_clock().now().to_msg()
        msg.position_source = BoxTrack.SOURCE_OBSERVE_HOMOGRAPHY
        self.box_pub.publish(msg)

    def _label(self) -> None:
        if self.vision_t0 is None or time.monotonic() - self.vision_t0 < self.a.label_after:
            return
        msg = LabelRead(
            track_id=self.track_id,
            code=self.a.code,
            dong=self.a.dong,
            confidence=self.a.conf,
            stage=1,
        )
        msg.stamp = self.get_clock().now().to_msg()
        msg.raw_text = f"{self.a.code}\n{self.a.dong}"
        self.label_pub.publish(msg)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--servo", action="store_true")
    ap.add_argument("--robot", action="store_true")
    ap.add_argument(
        "--robot-state", action="store_true", help="--robot 와 함께 /voss/robot/state 모의"
    )
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--vision", action="store_true")
    ap.add_argument(
        "--grasp",
        default="OK",
        help="OK | GRASP_FAILED | LOST | OUT_OF_REACH | STALE_INPUT | DEVICE_ERROR | REJECT",
    )
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--grasp-s", type=float, default=3.0)
    ap.add_argument("--place", default="ok", help="ok | RETURN_FAILED | GRIP_FAIL | TIMEOUT")
    ap.add_argument("--place-s", type=float, default=2.0)
    ap.add_argument("--stop-fail", action="store_true", help="/voss/robot/stop 이 success=false")
    ap.add_argument(
        "--view-fail", action="store_true", help="MoveToZone VIEW 가 실패(view_pose 미교시 흉내)"
    )
    ap.add_argument(
        "--pick-fail", action="store_true", help="MoveToZone PICK(재확인 칸에서 집기)이 실패"
    )
    ap.add_argument("--read", action="store_true")
    ap.add_argument(
        "--read-result", default="ok", help="ok(확실) | low(불확실 → 질문) | fail(판독 실패 → 질문)"
    )
    ap.add_argument("--read-code", default="S07-02")
    ap.add_argument("--read-dong", default="대치동")
    ap.add_argument("--read-alt", default="청담동")
    ap.add_argument("--read-conf", type=float, default=0.95)
    ap.add_argument("--log-status", default="OK")
    ap.add_argument("--track-id", type=int, default=1)
    ap.add_argument("--code", default="S07-02")
    ap.add_argument("--dong", default="대치동")
    ap.add_argument("--conf", type=float, default=0.9)
    ap.add_argument("--label-after", type=float, default=1.0, help="트랙이 나타난 뒤 첫 판독까지 s")
    ap.add_argument("--box-s", type=float, default=20.0, help="박스 하나가 시야를 지나가는 주기 s")
    a = ap.parse_args()
    if not (a.servo or a.robot or a.log or a.vision or a.read):
        ap.error("--servo/--robot/--log/--vision/--read 중 하나 이상")

    if os.environ.get("ROS_DOMAIN_ID", "0") == "30":
        ap.error("ROS_DOMAIN_ID=30 은 공용 PC 로봇 도메인 — 다른 도메인(예 77)에서 실행")

    rclpy.init(
        signal_handler_options=SignalHandlerOptions.NO
    )  # Ctrl+C 를 KeyboardInterrupt 로 받아 깔끔히 끈다
    node = G0Mock(a)
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    try:
        ex.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
