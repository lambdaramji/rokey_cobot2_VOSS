"""액션 경로 시험: belt_servo 와 가짜 클라이언트를 한 프로세스·한 executor 에서 돌린다.

로봇·다른 프로세스 없음. 가짜 pose(50 Hz, 선택: 받은 servo_cmd 적분)·가짜 박스·가짜 stop 서비스는
같은 executor, 가짜 그리퍼(응답 지연 흉내)는 별도 스레드 executor 에 둔다 (design/U5-dd.md E11).
다른 기기·사람의 노드와 섞이지 않게 전용 도메인을 쓴다.
"""

import json
import threading
import time

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, TwistStamped
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger
from test_node import READY_ARGS
from voss_servo.belt_servo import BeltServoNode

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack
from voss_msgs.srv import Gripper

TEST_DOMAIN_ID = 101  # 시험 전용 도메인 (팀 30~34 와 겹치지 않게)
BELT_V = (0.048 * 0.99992, 0.048 * -0.01292, 0.0)  # 벨트 속도 m/s (READY_ARGS 와 같은 방향·크기)
BOX_TOP_Z = 0.16  # 박스 윗면 z — 접근 +40 mm = 가짜 pose 시작 z 0.2

# 가짜 그리퍼 응답 = (지연 s, ok, 폭 mm, grip_detected, message)
OPENED = (0.0, True, 90.0, False, "OK")
HELD = (0.0, True, 40.9, True, "OK")  # T34 0° 보고 폭 근처
DEFAULT_SCRIPT = {"OPEN": [OPENED], "CLOSE": [HELD], "VERIFY": [HELD]}


class FakeGripper(Node):
    """gateway 의 /voss/robot/gripper 역할. 별도 스레드에서 돌아 응답 지연(sleep)이 belt_servo 를 막지 않는다."""

    def __init__(self, script: dict) -> None:
        super().__init__("u5_fake_gripper")
        self.script = {**DEFAULT_SCRIPT, **script}  # 종류별 응답 목록
        self.requests: list[tuple[float, float, float]] = []  # (폭, 힘, 받은 시각)
        self._used = {"OPEN": 0, "CLOSE": 0, "VERIFY": 0}  # 종류별 꺼낸 응답 수
        self._closes = 0  # 닫기 폭 요청 수 (1번째 CLOSE, 2번째부터 VERIFY — U9 재시도 때 바꿀 것)
        self.create_service(
            Gripper,
            "/voss/robot/gripper",
            self._on_gripper,
            callback_group=ReentrantCallbackGroup(),
        )

    def widths(self) -> list[float]:
        return [round(w, 1) for w, _, _ in self.requests]

    def _on_gripper(self, request, response):
        self.requests.append((request.width, request.force, time.monotonic()))
        if request.width >= 60.0:
            kind = "OPEN"
        else:
            self._closes += 1
            kind = "CLOSE" if self._closes == 1 else "VERIFY"
        replies = self.script[kind]
        reply = replies[min(self._used[kind], len(replies) - 1)]  # 목록 끝이면 마지막 것 반복
        self._used[kind] += 1
        delay, ok, width, grip, message = reply
        time.sleep(delay)  # 이 스레드만 잔다
        response.ok, response.width_actual = ok, width
        response.grip_detected, response.message = grip, message
        return response


class FakeClient(Node):
    """sort_manager 역할(액션 클라이언트) + gateway 역할(pose 발행·stop 서비스) + box_tracker 역할(선택)."""

    def __init__(
        self, stop_ok: bool | None, box: str | None = None, integrate: bool = False
    ) -> None:
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
        self.tcp = [0.0, 0.0, 0.2]  # 가짜 TCP 위치 m
        self._integrate = (
            integrate  # True 면 받은 servo_cmd 속도로 TCP 를 움직인다 (DryRunDoosan 처럼)
        )
        self._last_pose_t = time.monotonic()
        self.pose_pub = self.create_publisher(PoseStamped, "/voss/robot/pose", qos)
        self.create_timer(0.02, self._pub_pose)  # 50 Hz 가짜 pose
        if stop_ok is not None:  # None 이면 stop 서비스 없음
            self.create_service(Trigger, "/voss/robot/stop", self._on_stop)
        self._stop_ok = stop_ok
        self._box = box  # None | "moving" | "still"
        self._box_t0 = time.monotonic()
        if box is not None:
            box_qos = QoSProfile(
                depth=5,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.box_pub = self.create_publisher(BoxTrack, "/voss/vision/box", box_qos)
            self.create_timer(1.0 / 30.0, self._pub_box)  # 30 Hz 가짜 box_tracker

    def _on_stop(self, request, response):
        self.stop_calls += 1
        response.success = bool(self._stop_ok)
        response.message = "" if self._stop_ok else "TIMEOUT"
        return response

    def _pub_pose(self) -> None:
        now = time.monotonic()
        if self._integrate and self.cmds:
            v = self.cmds[-1].twist.linear  # 마지막으로 받은 속도로 그동안 움직였다고 본다
            dt = now - self._last_pose_t
            self.tcp = [self.tcp[0] + v.x * dt, self.tcp[1] + v.y * dt, self.tcp[2] + v.z * dt]
        self._last_pose_t = now
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = self.tcp
        self.pose_pub.publish(msg)

    def _pub_box(self) -> None:
        t = time.monotonic() - self._box_t0 if self._box == "moving" else 0.0
        msg = BoxTrack()
        msg.track_id = 7
        msg.stamp = self.get_clock().now().to_msg()  # 지금 촬영
        msg.position_valid = True
        msg.position_source = BoxTrack.SOURCE_HAND_EYE
        msg.position_base.x = 0.01 + BELT_V[0] * t  # TCP(x 0) 보다 10 mm 하류에서 시작
        msg.position_base.y = BELT_V[1] * t
        msg.position_base.z = BOX_TOP_Z
        self.box_pub.publish(msg)


def _ready_args(overrides: dict) -> list[str]:
    """READY_ARGS 에 덮어쓸 값을 반영한 -p 목록."""
    values = dict(item.split(":=", 1) for item in READY_ARGS)
    values.update({k: str(v) for k, v in overrides.items()})
    return [f"{k}:={v}" for k, v in values.items()]


# 움직이는 박스를 실제로 잡는 시험의 값 (DD E12): P 가 있어야 가속 제한으로 생긴 뒤처짐을 따라잡는다.
# 가짜 pose 는 지연이 없으므로 pose_lag 0.
MOVING = {
    "box": "moving",
    "integrate": True,
    "params": {"control.kp_per_s": 1.5, "input.pose_lag_ms": 0.0},
}


@pytest.fixture
def env(tmp_path, request):
    """READY 노드 + 가짜 클라이언트(한 executor) + 가짜 그리퍼(별도 스레드).

    request.param: stop 응답(bool/None, 옛 형식) 또는 dict(stop_ok, gripper=스크립트|"none", box, integrate, params).
    """
    param = getattr(request, "param", None)
    cfg = param if isinstance(param, dict) else {"stop_ok": param}
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]
    for item in _ready_args(cfg.get("params", {})):
        args += ["-p", item]
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
    node = BeltServoNode()
    client = FakeClient(cfg.get("stop_ok"), cfg.get("box"), cfg.get("integrate", False))
    gripper_cfg = cfg.get("gripper", {})
    gripper, g_ex, g_thread = None, None, None
    if gripper_cfg != "none":
        gripper = FakeGripper(gripper_cfg)
        g_ex = MultiThreadedExecutor()
        g_ex.add_node(gripper)
        g_thread = threading.Thread(target=g_ex.spin, daemon=True)
        g_thread.start()
        # 서비스가 보인 뒤 시작 — 아니면 첫 요청이 거짓 UNAVAILABLE (DD E12)
        assert node._gripper_cli.wait_for_service(timeout_sec=2.0)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    ex.add_node(client)
    yield node, client, ex, tmp_path, gripper
    # 정리 순서 고정 (DD E11): 그리퍼 스레드 먼저 멈추고 나서 context 를 내린다
    if g_ex is not None:
        g_ex.shutdown(timeout_sec=2.0)
        g_thread.join(timeout=2.0)
        gripper.destroy_node()
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


def spin_until_true(ex, cond, timeout: float) -> None:
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        ex.spin_once(timeout_sec=0.02)
    assert cond(), "조건 시간 초과"


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


def last_cmd_zero(client) -> bool:
    last = client.cmds[-1].twist.linear
    return (last.x, last.y, last.z) == (0.0, 0.0, 0.0)


def test_no_box_ends_lost_then_zero_hold_then_free(env) -> None:
    node, client, ex, tmp, _ = env
    handle = send(client, ex)
    assert handle.accepted
    res = spin_until(ex, handle.get_result_async(), 5.0)
    assert res.status == GoalStatus.STATUS_ABORTED
    assert (res.result.grasped, res.result.reason, res.result.attempts) == (False, "LOST", 0)
    assert client.feedback == ["PREPARE", "TRACK"]  # 개방 응답 → TRACK (U5)
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
    node, client, ex, tmp, _ = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "STOP_UNAVAILABLE"


@pytest.mark.parametrize("env", [True], indirect=True)
def test_cancel_with_stop_ok_is_canceled(env) -> None:
    node, client, ex, tmp, _ = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_CANCELED and res.result.reason == "CANCELED"
    assert client.stop_calls == 1
    assert goal_ends(tmp)[-1]["cause"] == "STOP_OK"


@pytest.mark.parametrize("env", [False], indirect=True)
def test_cancel_with_stop_failed_keeps_gateway_message(env) -> None:
    node, client, ex, tmp, _ = env
    handle = send(client, ex)
    spin_for(ex, 0.1)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "STOP_FAILED_TIMEOUT"


def test_internal_exception_aborts_and_logs_goal_end(env, monkeypatch) -> None:
    node, client, ex, tmp, _ = env

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


@pytest.mark.parametrize(
    "env", [{"stop_ok": True, "gripper": {"OPEN": [(2.0, True, 90.0, False, "OK")]}}], indirect=True
)
def test_prepare_with_visible_box_moves_then_cancel_zero(env) -> None:
    """보이는 박스 → PREPARE 에서 벨트 방향으로 움직이는 명령 → 취소 → CANCELED, 마지막 명령 0 (U2)."""
    node, client, ex, tmp, _ = env
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


# --- U5 파지 시퀀스 (design/U5-dd.md 6.5): 지시서 4 케이스 + 4 ---

SIX_PHASES = ["PREPARE", "TRACK", "DESCEND", "GRASP", "LIFT", "VERIFY"]
EMPTY = (0.0, True, 38.4, False, "OK")  # 빈손 (T34 빈손 38.0~38.7)
LATE_CLOSE = (1.0, True, 40.9, True, "OK")  # 1 s 늦게 오는 닫기 응답
BUSY = (0.0, False, 0.0, False, "BUSY")


@pytest.mark.parametrize("env", [MOVING], indirect=True)
def test_u5_normal_grasp_ok(env) -> None:
    """① 정상: 움직이는 박스를 따라가 잡고 들어 확인 → OK·grasped=true, 6 phase, 그리퍼 90→39→39."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)  # 박스가 먼저 들어오게
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 15.0)
    assert res.status == GoalStatus.STATUS_SUCCEEDED
    assert (res.result.grasped, res.result.reason, res.result.attempts) == (True, "OK", 1)
    assert client.feedback == SIX_PHASES
    assert gripper.widths() == [90.0, 39.0, 39.0]  # 개방 → 닫기 → 확인(닫기 한 번 더)
    spin_for(ex, 0.6)  # 0 유지 구간까지
    assert node.grip_late_discarded == 0 and last_cmd_zero(client)
    end = goal_ends(tmp)[-1]
    assert end["gripper"]["kind"] == "VERIFY" and end["gripper"]["verdict"] == "HELD"


@pytest.mark.parametrize("env", [{**MOVING, "gripper": {"CLOSE": [EMPTY]}}], indirect=True)
def test_u5_empty_hand_grasp_failed_no_open(env) -> None:
    """② 빈손: 닫았는데 감지 없음 → GRASP_FAILED, 그 뒤 개방 요청 없음."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 15.0)
    assert res.status == GoalStatus.STATUS_ABORTED
    assert (res.result.grasped, res.result.reason, res.result.attempts) == (
        False,
        "GRASP_FAILED",
        1,
    )
    assert goal_ends(tmp)[-1]["cause"] == "NOT_DETECTED"
    spin_for(ex, 0.6)
    assert gripper.widths() == [90.0, 39.0]  # grasped=false 여도 자동 개방 없음
    assert node.grip_late_discarded == 0 and last_cmd_zero(client)


LATE = {
    **MOVING,
    "gripper": {"CLOSE": [LATE_CLOSE]},
    "params": {**MOVING["params"], "gripper_timeout_s": 0.5, "grasp.close_time_max_s": 0.4},
}


@pytest.mark.parametrize("env", [LATE], indirect=True)
def test_u5_late_reply_timeout_then_discarded(env) -> None:
    """③ 늦은 응답: 닫기 응답이 한계(0.5 s)를 넘김 → DEVICE_ERROR(GRIPPER_TIMEOUT), 나중 응답은 버림."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 15.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "GRIPPER_TIMEOUT"
    spin_for(ex, 1.2)  # 늦은 응답이 도착할 시간
    assert node.grip_late_discarded == 1
    assert gripper.widths() == [90.0, 39.0] and last_cmd_zero(client)


@pytest.mark.parametrize(
    "env", [{**MOVING, "stop_ok": False, "gripper": {"CLOSE": [LATE_CLOSE]}}], indirect=True
)
def test_u5_cancel_in_grasp_stop_failed(env) -> None:
    """④ 정지 실패: 닫는 중 취소 → stop 실패 → DEVICE_ERROR(STOP_FAILED_TIMEOUT), 닫기 응답은 버림."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    spin_until_true(ex, lambda: "GRASP" in client.feedback, 15.0)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "STOP_FAILED_TIMEOUT"
    spin_for(ex, 1.2)
    assert client.stop_calls == 1 and node.grip_late_discarded == 1
    assert gripper.widths() == [90.0, 39.0] and last_cmd_zero(client)


@pytest.mark.parametrize(
    "env", [{"box": "still", "stop_ok": True, "gripper": {"OPEN": [BUSY, OPENED]}}], indirect=True
)
def test_u5_busy_once_retries_after_delay(env) -> None:
    """⑤ BUSY 1회: 0.5 s 뒤 한 번 더 → 개방 성공 → TRACK. 끝에 취소로 goal 을 정리한다."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    spin_until_true(ex, lambda: "TRACK" in client.feedback, 3.0)
    assert gripper.widths() == [90.0, 90.0]
    gap = gripper.requests[1][2] - gripper.requests[0][2]
    assert gap >= 0.45  # 0.5 s 지연 (틱 위상 여유)
    assert node._ctx.grip_log["busy_retries"] == 1 and node._ctx.grip_log["seq"] == 2
    spin_until(ex, handle.cancel_goal_async(), 2.0)  # 진행 중인 goal 을 남기지 않는다
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.result.reason == "CANCELED"


@pytest.mark.parametrize("env", [{"box": "still", "gripper": {"OPEN": [BUSY]}}], indirect=True)
def test_u5_busy_twice_device_error(env) -> None:
    """⑥ BUSY 2회 → DEVICE_ERROR(GRIPPER_BUSY)."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.result.reason == "DEVICE_ERROR" and goal_ends(tmp)[-1]["cause"] == "GRIPPER_BUSY"
    assert gripper.widths() == [90.0, 90.0]


@pytest.mark.parametrize(
    "env", [{"gripper": {"OPEN": [(0.0, False, 0.0, False, "INVALID: width")]}}], indirect=True
)
def test_u5_invalid_is_device_error(env) -> None:
    """⑦ INVALID → DEVICE_ERROR(GRIPPER_INVALID) (설정 오류 로그는 노드가 ERROR 로)."""
    node, client, ex, tmp, gripper = env
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.result.reason == "DEVICE_ERROR" and goal_ends(tmp)[-1]["cause"] == "GRIPPER_INVALID"
    assert goal_ends(tmp)[-1]["gripper"]["message"] == "INVALID: width"  # 원문은 로그에


@pytest.mark.parametrize("env", [{"gripper": "none"}], indirect=True)
def test_u5_no_gripper_service_is_device_error(env) -> None:
    """⑧ 그리퍼 서비스 없음 → 기다리지 않고 DEVICE_ERROR(GRIPPER_UNAVAILABLE)."""
    node, client, ex, tmp, _ = env
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 3.0)
    assert res.result.reason == "DEVICE_ERROR"
    assert goal_ends(tmp)[-1]["cause"] == "GRIPPER_UNAVAILABLE"


NO_ROOM = {**MOVING, "params": {**MOVING["params"], "reach.x_max_mm": 200.0}}


@pytest.mark.parametrize("env", [NO_ROOM], indirect=True)
def test_u5_no_x_room_ends_before_descend(env) -> None:
    """⑨ x 여유 부족: x_max 200 mm 면 정렬 순간 남은 길 < 필요(≈216 mm) → DESCEND 전 OUT_OF_REACH."""
    node, client, ex, tmp, gripper = env
    spin_for(ex, 0.2)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 10.0)
    assert res.status == GoalStatus.STATUS_ABORTED and res.result.reason == "OUT_OF_REACH"
    end = goal_ends(tmp)[-1]
    assert end["cause"] == "REACH_GRASP_ROOM" and end["phase"] == "TRACK"
    assert client.feedback == ["PREPARE", "TRACK"]  # 내려가지 않았다
    spin_for(ex, 0.6)
    assert gripper.widths() == [90.0] and last_cmd_zero(client)  # 닫기 요청도 없다
