"""robot_gateway — 인터페이스는 docs/interfaces/topics.md 참조.

두산 서비스는 SerialCallQueue 하나로만 부른다(CLAUDE.md 절대 규칙 3). dry_run 이면 두산·RG2 에
연결하지 않고 관측 자세에 멈춘 가짜 로봇을 쓴다(개인 PC 개발용).

지금 있는 것: /voss/robot/pose (TCP, base_link). 다음 단계: gripper → servo_cmd → move_to_zone → stop
(10/08 게이트 1차에 servo_cmd 가 필요해 move_to_zone 보다 앞당김, 남현지 10/07).
"""

import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from voss_robot.call_queue import SerialCallQueue
from voss_robot.doosan import DEFAULT_PREFIX, DoosanError, DryRunDoosan
from voss_robot.geometry import flange_to_ros_pose


class RobotGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("robot_gateway")
        # dry_run 기본값 true: 실수로 띄워도 로봇이 움직이지 않게 한다
        self.dry_run = self.declare_parameter("dry_run", True).value
        prefix = self.declare_parameter("dsr_prefix", DEFAULT_PREFIX).value
        rate = self.declare_parameter("pose_rate_hz", 50.0).value
        timeout = self.declare_parameter("call_timeout_s", 0.5).value
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

            self.dsr = RosDoosan(self, prefix, timeout)
            if not self.dsr.wait_ready(5.0):
                self.get_logger().error(f"두산 서비스가 안 보인다: {prefix} — 브링업 확인")

        # /voss/robot/pose: best_effort·volatile·depth 1 (topics.md QoS)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pose_pub = self.create_publisher(PoseStamped, "/voss/robot/pose", qos)
        self._pose_busy = False  # 앞 조회가 끝나기 전엔 새로 넣지 않는다(큐 밀림 방지)
        self._stats = {"n": 0, "fail": 0, "rtt": [], "wait": [], "skip": 0}
        self.create_timer(1.0 / rate, self._on_pose_timer)
        self.create_timer(5.0, self._log_stats)
        mode = "dry_run (두산·RG2 연결 안 함)" if self.dry_run else f"real {prefix}"
        self.get_logger().info(f"robot_gateway started: {mode}, pose {rate:.0f} Hz")

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

    def destroy_node(self) -> None:
        self.queue.close()  # 대기 작업을 버리고 작업 스레드를 끝낸다
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RobotGatewayNode()
    executor = MultiThreadedExecutor(num_threads=4)  # 두산 응답 콜백이 따로 돌아야 한다
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # Ctrl-C·launch 종료는 정상 종료
    finally:
        try:
            executor.shutdown(timeout_sec=1.0)  # 실행 스레드를 먼저 멈춘 뒤 노드를 정리한다
            node.destroy_node()
        except KeyboardInterrupt:
            pass  # 정리 중 두 번째 Ctrl-C
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
