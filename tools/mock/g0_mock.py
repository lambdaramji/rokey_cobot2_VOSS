"""G0 모의 상대 — 로봇 없이 sort_manager 를 끝까지 돌려 보는 개발용. 아무 장비도 움직이지 않는다.

진짜 노드가 아직 없는 쪽만 골라 띄운다. 같은 이름의 진짜 서버·발행자가 이미 있으면 그 부분은 띄우지 않는다.
**ROS_DOMAIN_ID 30(공용 PC 로봇 도메인)에서는 기동을 거부한다** — 진짜 로봇 옆에 가짜 pose·응답을 섞지 않도록
공용 PC 에서도 다른 도메인(예 77)에서만 쓴다.
  --servo   /voss/servo/track_and_grasp 액션 서버 (belt_servo 대역)
  --robot   /voss/robot/move_to_zone·/voss/robot/stop 서비스, /voss/robot/pose 50 Hz (robot_gateway 대역)
  --log     /voss/log/status 1 Hz (sort_logger 대역)
  --vision  /voss/vision/box 30 Hz + /voss/vision/label stage 1 (box_tracker·label_reader 대역, 박스 1개)

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
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack, LabelRead
from voss_msgs.srv import MoveToZone

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
        if a.robot and self._free_service("/voss/robot/stop"):
            self.create_service(Trigger, "/voss/robot/stop", self._stop, callback_group=self.cb)
            log.info("[robot] stop 모의")
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

    # belt_servo 대역
    def _execute(self, gh) -> TrackAndGrasp.Result:
        a, res = self.a, TrackAndGrasp.Result()
        self.get_logger().info(f"[servo] goal track {gh.request.track_id}")
        phases = ["PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY"]
        t_end = time.monotonic() + a.grasp_s
        while time.monotonic() < t_end:
            if gh.is_cancel_requested:
                gh.canceled()
                res.grasped, res.reason, res.attempts = False, "CANCELED", 1
                return res
            k = int((1 - (t_end - time.monotonic()) / a.grasp_s) * len(phases))
            gh.publish_feedback(
                TrackAndGrasp.Feedback(err_u=3.0, err_v=-2.0, phase=phases[min(k, 5)])
            )
            time.sleep(0.1)
        res.grasped, res.reason, res.attempts = a.grasp == "OK", a.grasp, a.attempts
        if a.grasp == "OK":
            gh.succeed()
        else:
            gh.abort()
        return res

    # robot_gateway 대역
    def _move(self, req: MoveToZone.Request, res: MoveToZone.Response) -> MoveToZone.Response:
        a = self.a
        mode = "이동" if req.zone == "OBSERVE" else (req.mode or "PLACE")
        self.get_logger().info(f"[robot] MoveToZone {req.zone} 칸 {req.slot} {mode}")
        time.sleep(a.place_s if req.zone != "OBSERVE" else 0.5)
        if req.zone == "OBSERVE" or a.place == "ok":
            res.ok, res.message = True, "OK"
        else:
            res.ok, res.message = False, a.place
        if mode == "PLACE" and req.zone != "OBSERVE" and a.place in ("ok", "RETURN_FAILED"):
            res.placed_stamp = self.get_clock().now().to_msg()
        return res

    def _stop(self, _req: Trigger.Request, res: Trigger.Response) -> Trigger.Response:
        self.get_logger().info("[robot] stop")
        res.success, res.message = not self.a.stop_fail, "TIMEOUT" if self.a.stop_fail else ""
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
    ap.add_argument("--log-status", default="OK")
    ap.add_argument("--track-id", type=int, default=1)
    ap.add_argument("--code", default="S07-02")
    ap.add_argument("--dong", default="대치동")
    ap.add_argument("--conf", type=float, default=0.9)
    ap.add_argument("--label-after", type=float, default=1.0, help="트랙이 나타난 뒤 첫 판독까지 s")
    ap.add_argument("--box-s", type=float, default=20.0, help="박스 하나가 시야를 지나가는 주기 s")
    a = ap.parse_args()
    if not (a.servo or a.robot or a.log or a.vision):
        ap.error("--servo/--robot/--log/--vision 중 하나 이상")

    if os.environ.get("ROS_DOMAIN_ID", "0") == "30":
        ap.error("ROS_DOMAIN_ID=30 은 공용 PC 로봇 도메인 — 다른 도메인(예 77)에서 실행")

    rclpy.init()
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
