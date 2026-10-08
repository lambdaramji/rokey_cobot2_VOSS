"""액션 경로 시험: belt_servo 와 가짜 클라이언트를 한 프로세스·한 executor 에서 돌린다.

로봇·다른 프로세스 없음. 가짜 pose(50 Hz)와 가짜 stop 서비스만 같은 프로세스 안에 둔다.
다른 기기·사람의 노드와 섞이지 않게 전용 도메인을 쓴다. U3 fake end-to-end 전까지의 안전망.
"""

import json
import time

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, TwistStamped
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger
from test_node import READY_ARGS
from voss_servo.belt_servo import BeltServoNode

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack

TEST_DOMAIN_ID = 101  # 시험 전용 도메인 (팀 30~34 와 겹치지 않게)


class FakeClient(Node):
    """sort_manager 역할(액션 클라이언트) + gateway 역할(pose 발행·stop 서비스)."""

    def __init__(self, stop_ok: bool | None) -> None:
        super().__init__("u1_fake_client")
        self.ac = ActionClient(self, TrackAndGrasp, "/voss/servo/track_and_grasp")
        qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.cmds: list[TwistStamped] = []  # 받은 servo_cmd
        self.create_subscription(TwistStamped, "/voss/robot/servo_cmd", self.cmds.append, qos)
        self.feedback: list[str] = []  # 받은 feedback.phase
        self.stop_calls = 0
        self.pose_pub = self.create_publisher(PoseStamped, "/voss/robot/pose", qos)
        self.create_timer(0.02, self._pub_pose)  # 50 Hz 가짜 pose (z 0.2 m)
        if stop_ok is not None:  # None 이면 stop 서비스 없음
            self.create_service(Trigger, "/voss/robot/stop", self._on_stop)
        self._stop_ok = stop_ok

    def _on_stop(self, request, response):
        self.stop_calls += 1
        response.success = bool(self._stop_ok)
        response.message = "" if self._stop_ok else "TIMEOUT"
        return response

    def _pub_pose(self) -> None:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.pose.position.z = 0.2
        self.pose_pub.publish(msg)


@pytest.fixture
def env(tmp_path, request):
    """READY 노드 + 가짜 클라이언트를 한 executor 에. request.param = stop 서비스 응답."""
    stop_ok = getattr(request, "param", None)
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]
    for item in READY_ARGS:
        args += ["-p", item]
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
    node = BeltServoNode()
    client = FakeClient(stop_ok)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    ex.add_node(client)
    yield node, client, ex, tmp_path
    ex.shutdown()
    node.destroy_node()
    client.destroy_node()
    rclpy.try_shutdown()


def spin_for(ex, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ex.spin_once(timeout_sec=0.02)


def spin_until(ex, fut, timeout: float):
    end = time.monotonic() + timeout
    while not fut.done() and time.monotonic() < end:
        ex.spin_once(timeout_sec=0.02)
    assert fut.done(), "시간 초과"
    return fut.result()


def send(client, ex, track_id: int = 7):
    """goal 을 보내고 goal handle 을 돌려준다."""
    assert client.ac.wait_for_server(timeout_sec=2.0)
    fut = client.ac.send_goal_async(
        TrackAndGrasp.Goal(track_id=track_id),
        feedback_callback=lambda fb: client.feedback.append(fb.feedback.phase),
    )
    return spin_until(ex, fut, 3.0)


def read_jsonl(folder):
    files = sorted(folder.iterdir()) if folder.exists() else []
    return [json.loads(line) for f in files for line in f.read_text().splitlines()]


def goal_ends(tmp):
    return [a for a in read_jsonl(tmp / "attempts") if a["event"] == "GOAL_END"]


def test_no_box_ends_lost_then_zero_hold_then_free(env) -> None:
    node, client, ex, tmp = env
    handle = send(client, ex)
    assert handle.accepted
    res = spin_until(ex, handle.get_result_async(), 5.0)
    assert res.status == GoalStatus.STATUS_ABORTED
    assert (res.result.grasped, res.result.reason, res.result.attempts) == (False, "LOST", 0)
    assert client.feedback == ["PREPARE"]
    assert not send(client, ex, 8).accepted  # 0 유지 중 새 goal 은 거부
    spin_for(ex, 0.7)
    assert not node._busy  # 0 유지가 끝나면 다시 받는다
    h3 = send(client, ex, 9)
    assert h3.accepted
    spin_until(ex, h3.get_result_async(), 5.0)  # 두 번째 goal 도 끝까지 (LOST)
    assert client.cmds and all(  # 발행한 servo_cmd 는 전부 0, base_link
        (m.twist.linear.x, m.twist.linear.y, m.twist.linear.z) == (0.0, 0.0, 0.0)
        and m.header.frame_id == "base_link"
        for m in client.cmds
    )
    ends = goal_ends(tmp)
    assert len(ends) == 2 and all(
        e["reason"] == "LOST" and e["cause"] == "BOX_MISSING" for e in ends
    )
    assert any(t["cause"] == "ZERO_HOLD" for t in read_jsonl(tmp / "ticks"))


def test_cancel_without_stop_service_is_device_error(env) -> None:
    node, client, ex, tmp = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "STOP_UNAVAILABLE"


@pytest.mark.parametrize("env", [True], indirect=True)
def test_cancel_with_stop_ok_is_canceled(env) -> None:
    node, client, ex, tmp = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_CANCELED and res.result.reason == "CANCELED"
    assert client.stop_calls == 1
    assert goal_ends(tmp)[-1]["cause"] == "STOP_OK"


@pytest.mark.parametrize("env", [False], indirect=True)
def test_cancel_with_stop_failed_keeps_gateway_message(env) -> None:
    node, client, ex, tmp = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "STOP_FAILED_TIMEOUT"


def test_internal_exception_aborts_and_logs_goal_end(env, monkeypatch) -> None:
    node, client, ex, tmp = env

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(node, "_build_event", boom)  # 틱 안에서 예외
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    ends = goal_ends(tmp)
    assert len(ends) == 1 and ends[0]["cause"] == "INTERNAL_EXCEPTION"  # 게이트 분모에 남는다
    spin_for(ex, 0.7)
    assert not node._busy


@pytest.mark.parametrize("env", [True], indirect=True)
def test_prepare_with_visible_box_moves_then_cancel_zero(env) -> None:
    """보이는 박스 → PREPARE 에서 벨트 방향으로 움직이는 명령 → 취소 → CANCELED, 마지막 명령 0 (U2)."""
    node, client, ex, tmp = env
    qos = QoSProfile(
        depth=5, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
    )
    box_pub = client.create_publisher(BoxTrack, "/voss/vision/box", qos)

    def pub_box() -> None:
        msg = BoxTrack()
        msg.track_id = 7
        msg.stamp = client.get_clock().now().to_msg()  # 지금 촬영
        msg.position_valid = True
        msg.position_source = BoxTrack.SOURCE_HAND_EYE
        msg.position_base.x = 0.01  # TCP(x 0) 보다 10 mm 하류
        msg.position_base.z = 0.16  # 윗면 + 접근 40 mm = 가짜 pose z 0.2
        box_pub.publish(msg)

    client.create_timer(1.0 / 30.0, pub_box)  # 30 Hz 가짜 box_tracker
    spin_for(ex, 0.2)  # box 가 먼저 들어오게
    handle = send(client, ex)
    spin_for(ex, 0.5)
    moving = [m for m in client.cmds if m.twist.linear.x > 0.0]
    assert moving, "PREPARE 에서 벨트 방향으로 움직이는 명령이 있어야 한다"
    assert all(m.twist.linear.x <= 0.08 + 1e-9 for m in client.cmds)  # 속도 상한
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_CANCELED and res.result.reason == "CANCELED"
    spin_for(ex, 0.2)  # 0 유지 구간 명령까지 받기
    last = client.cmds[-1].twist.linear
    assert (last.x, last.y, last.z) == (0.0, 0.0, 0.0)  # 끝은 반드시 0 (ADR-0010)
    ticks = read_jsonl(tmp / "ticks")
    assert any(t["cmd_rule"] == "FF_P" and t["phase"] == "PREPARE" for t in ticks)
    assert any(t["cmd_rule"] == "ZERO_STOP" for t in ticks)
