"""belt_servo 노드를 프로세스 안에서 만들어 보는 시험 (spin 없이, 로봇·다른 노드 없음)."""

import pytest
import rclpy
from builtin_interfaces.msg import Time
from rclpy.action import GoalResponse
from voss_servo.belt_servo import BeltServoNode

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack


@pytest.fixture
def node(tmp_path):
    """파라미터 없이 띄운 노드 (로그는 임시 폴더로)."""
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]  # log.dir 만 주고 나머지는 미전달
    rclpy.init(args=args)
    n = BeltServoNode()
    yield n
    n.destroy_node()
    rclpy.try_shutdown()


def box(track_id: int, sec: int, valid: bool = True) -> BoxTrack:
    """시험용 BoxTrack."""
    msg = BoxTrack()
    msg.track_id = track_id
    msg.stamp = Time(sec=sec, nanosec=0)
    msg.position_valid = valid
    return msg


def test_no_params_is_not_ready(node) -> None:
    assert node.ready is False  # 미전달 필수 키가 있으면 READY 거부


def test_no_action_server_when_not_ready(node) -> None:
    assert node._action is None  # sort_manager 가 SERVO 를 준비로 오인하지 않게


def test_goal_rejected_when_not_ready(node) -> None:
    goal = TrackAndGrasp.Goal()
    goal.track_id = 7
    assert node._on_goal(goal) == GoalResponse.REJECT
    assert node._busy is False  # 거부했으니 바쁘지 않다


def test_box_callback_safe_when_not_ready(node) -> None:
    node._on_box(box(7, 10))  # lost_timeout 이 None 이어도 예외 없이 보관
    assert 7 in node._boxes


def test_box_store_per_track_and_drop_backwards(node) -> None:
    node._on_box(box(7, 10, valid=True))
    node._on_box(box(8, 11, valid=True))  # 다른 박스가 내 박스를 덮어쓰지 않는다
    node._on_box(box(7, 9, valid=True))  # 같은 트랙에서 시각 역행 → 버림
    assert node._boxes[7].msg.stamp.sec == 10
    node._on_box(box(7, 12, valid=False))  # 최신은 invalid
    entry = node._boxes[7]
    assert entry.latest_invalid and entry.last_valid.stamp.sec == 10  # 마지막 유효 관측 보관


def test_box_nan_position_counts_as_invalid(node) -> None:
    node._on_box(box(7, 10, valid=True))
    bad = box(7, 11, valid=True)
    bad.position_base.x = float("nan")  # valid 라고 왔지만 좌표가 NaN
    node._on_box(bad)
    entry = node._boxes[7]
    assert (
        entry.latest_invalid and entry.last_valid.stamp.sec == 10
    )  # 마지막 유효 관측을 덮지 않는다


READY_ARGS = [
    "belt.speed_cmps:=4.8",
    "belt.direction_base:=[0.99992,-0.01292,0.0]",
    "gripper.pre_open_mm:=90.0",
    "gripper.grasp_width_mm:=39.0",
    "gripper.force_n:=14.0",
    "timing.latency_offset_ms:=0.0",
    "grasp.tcp_z_below_top_mm:=19.0",
    "grasp.hold_width_min_mm:=39.5",
    "grasp.hold_width_max_mm:=41.5",
    "reach.x_min_mm:=-107.0",
    "reach.x_max_mm:=638.0",
    "control.kp_per_s:=0.0",
    "limits.max_speed_mps:=0.08",
    "limits.max_acc_mps2:=0.1",
    "z.approach_above_top_mm:=40.0",
    "z.lift_above_top_mm:=50.0",
    "z.vision_cutoff_above_top_mm:=10.0",
    "input.stale_timeout_s:=0.3",
    "input.lost_timeout_s:=0.5",
    "retry.max_attempts:=1",
    "stop_timeout_s:=1.0",
    "rate_hz:=30.0",
    "zero_hold_s:=0.5",
    # U2 제어 값 (design/U2-dd.md 2절, 제안값)
    "control.kp_z_per_s:=2.0",
    "control.align_tol_along_mm:=3.0",
    "control.align_tol_cross_mm:=5.0",
    "z.descend_speed_mps:=0.05",
    "z.lift_speed_mps:=0.08",
    "z.height_tol_mm:=2.0",
    "input.pose_lag_ms:=60.0",
    "input.pose_extrap_max_ms:=120.0",
    "input.blind_entry_max_age_s:=0.15",
]


class FakeHandle:
    """ServerGoalHandle 대신 쓰는 최소 가짜 (feedback 만 모은다)."""

    is_cancel_requested = False

    def __init__(self) -> None:
        self.feedback = []

    def publish_feedback(self, fb) -> None:
        self.feedback.append(fb.phase)


@pytest.fixture
def ready_node(tmp_path):
    """시험용 값을 모두 넘겨 READY 인 노드."""
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]
    for item in READY_ARGS:
        args += ["-p", item]
    rclpy.init(args=args)
    n = BeltServoNode()
    yield n
    n.destroy_node()
    rclpy.try_shutdown()


def test_ready_node_tick_and_hold_logs_match_schema(ready_node) -> None:
    from voss_servo.belt_servo import GoalCtx

    from voss_servo import fsm

    n = ready_node
    assert n.ready
    assert n._action is not None  # READY 면 액션 서버가 있다
    state, _ = fsm.start()
    ctx = GoalCtx(FakeHandle(), "g1", 7, state, start=n._now(), vision_since=n._now())
    n._ctx = ctx
    n._on_box(box(7, 10))
    n._tick_goal(ctx, n._now())  # 틱 한 번: 키가 스키마와 다르면 ValueError
    assert n._tick_log.path.exists()
    n._finish(ctx, fsm.LOST, "BOX_MISSING", False, n._now())
    assert ctx.done.done() and ctx.done.result() == (False, fsm.LOST, 0)
    n._tick_hold(n._now())  # 0 유지 틱 로그도 스키마와 맞아야 한다
    # 틱 1 + (_finish 직접 호출이라) GOAL_END 스냅샷 틱 1 + 0 유지 틱 1
    assert n._tick_log.path.read_text(encoding="utf-8").count("\n") == 3
    assert '"event":"GOAL_END"' in n._attempt_log.path.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad_rate", ["abc", "-5.0"])
def test_bad_rate_does_not_crash_startup(tmp_path, bad_rate) -> None:
    rclpy.init(args=["--ros-args", "-p", f"log.dir:={tmp_path}", "-p", f"rate_hz:={bad_rate}"])
    try:
        n = BeltServoNode()  # 예외 없이 READY 거부 상태로 떠야 한다
        assert not n.ready and n._action is None
        n.destroy_node()
    finally:
        rclpy.try_shutdown()
