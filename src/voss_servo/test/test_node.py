"""belt_servo 노드를 프로세스 안에서 만들어 보는 시험 (spin 없이, 로봇·다른 노드 없음)."""

import os

import numpy as np
import pytest
import rclpy
from builtin_interfaces.msg import Time
from geometry_msgs.msg import PoseStamped
from rclpy.action import GoalResponse
from voss_servo.belt_servo import BeltServoNode

from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack

# 실행별 도메인 (RULES §2, 2026-10-10): 같은 PC 의 다른 세션·사용자 노드와 섞이지 않게.
# 고정값·환경 변수에 기대지 않는다 (예: 남이 /voss/robot/gripper 를 띄워 두면 '서비스 없음' 시험이 깨진다)
TEST_DOMAIN_ID = 150 + os.getpid() % 70


@pytest.fixture
def node(tmp_path):
    """파라미터 없이 띄운 노드 (로그는 임시 폴더로)."""
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]  # log.dir 만 주고 나머지는 미전달
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
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
    "grasp.hold_width_max_mm:=43.5",
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
    "input.pose_extrap_max_ms:=200.0",
    "input.blind_entry_max_age_s:=0.15",
    # U5 그리퍼 값 (design/U5-dd.md 5절)
    "grasp.close_time_max_s:=2.1",
    "grasp.room_margin_mm:=10.0",
    "gripper_timeout_s:=3.0",
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
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
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
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}", "-p", f"rate_hz:={bad_rate}"]
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
    try:
        n = BeltServoNode()  # 예외 없이 READY 거부 상태로 떠야 한다
        assert not n.ready and n._action is None
        n.destroy_node()
    finally:
        rclpy.try_shutdown()


def pose(sec: float, x: float) -> PoseStamped:
    """시험용 TCP pose."""
    msg = PoseStamped()
    msg.header.stamp = Time(sec=int(sec), nanosec=int(round((sec % 1) * 1e9)))
    msg.pose.position.x = x
    msg.pose.position.z = 0.2
    return msg


def test_pose_value_stamp_held_while_value_repeats(node) -> None:
    node._on_pose(pose(10.00, 0.0))
    rx_first = node._pose[1]
    node._on_pose(pose(10.02, 0.0))  # 같은 값 반복 (gateway service 0.1 s 갱신)
    assert node._pose_value[1] == pytest.approx(10.00)  # 외삽 기준은 처음 stamp
    assert node._pose[1] >= rx_first  # 끊김 판정용 수신 시각은 메시지마다 갱신
    node._on_pose(pose(10.10, 0.0048))  # 값이 바뀜
    assert node._pose_value == ((0.0048, 0.0, 0.2), pytest.approx(10.10))


def test_repeated_pose_value_extrapolates_until_pose_stale(ready_node) -> None:
    """같은 pose 값이 계속 와도(수신은 신선) pose_stale 전까지 FF_P 가 나가고, 외삽은 값의 실제 나이로."""
    from voss_servo.belt_servo import GoalCtx

    from voss_servo import control, fsm

    n = ready_node
    now = n._now()
    state, _ = fsm.start()
    ctx = GoalCtx(FakeHandle(), "g1", 7, state, start=now, vision_since=now)
    n._ctx = ctx
    n._last_cmd = np.array([0.048, 0.0, 0.0])  # 직전 명령 = 벨트 속도
    n._on_pose(pose(now - 0.10, 0.0))  # 값이 0.1 s 전에 처음 왔고
    n._on_pose(pose(now - 0.02, 0.0))  # 같은 값이 계속 온다 (수신 시각은 지금)
    b = box(7, 0)
    b.stamp = n.get_clock().now().to_msg()
    b.position_base.x = 0.01  # TCP 보다 10 mm 하류
    b.position_base.z = 0.16  # 윗면 + 접근 40 mm = pose z 0.2
    n._on_box(b)
    n._tick_goal(ctx, n._now())
    assert ctx.geo.tcp_horizon_s >= 0.10 + 0.06  # 마지막 메시지(0.02 s 전)가 아니라 값 나이로
    assert ctx.geo.tcp[0] == pytest.approx(0.048 * ctx.geo.tcp_horizon_s, abs=1e-4)
    assert ctx.cmd.rule == control.FF_P and ctx.cmd.vel[0] > 0.0  # pose_stale 아님 → 계속 추종
    assert not ctx.state.stopping and ctx.state.phase == fsm.PREPARE


def test_nan_pose_value_gives_no_pose_zero(ready_node) -> None:
    from voss_servo.belt_servo import GoalCtx

    from voss_servo import control, fsm

    n = ready_node
    now = n._now()
    state, _ = fsm.start()
    ctx = GoalCtx(FakeHandle(), "g1", 7, state, start=now, vision_since=now)
    n._ctx = ctx
    n._on_pose(pose(now, float("nan")))  # 위치에 NaN
    n._tick_goal(ctx, n._now())
    assert ctx.geo is None and ctx.cmd.rule == control.ZERO_NO_POSE
    assert not np.any(ctx.cmd.vel)


# --- U5 그리퍼 호출 (가짜 future, spin 없이 — design/U5-dd.md 6.4) ---


class FakeGripperCli:
    """그리퍼 클라이언트 대신: 요청을 기록하고 우리가 직접 채울 future 를 돌려준다."""

    def __init__(self) -> None:
        self.requests = []  # (폭, 힘)
        self.futures = []
        self.ready = True  # False 로 바꾸면 서비스가 사라진 것처럼

    def service_is_ready(self) -> bool:
        return self.ready

    def call_async(self, req):
        from rclpy.task import Future

        self.requests.append((req.width, req.force))
        fut = Future()  # executor 없음 → done 콜백은 set_result 때 바로 불린다
        self.futures.append(fut)
        return fut


def gripper_resp(ok=True, width=40.9, grip=True, message="OK"):
    from voss_msgs.srv import Gripper

    r = Gripper.Response()
    r.ok, r.width_actual, r.grip_detected, r.message = ok, width, grip, message
    return r


def new_ctx(n, goal_id="g1"):
    """진행 중 goal 상태 하나 (PREPARE)."""
    from voss_servo.belt_servo import GoalCtx

    from voss_servo import fsm

    now = n._now()
    state, _ = fsm.start()
    ctx = GoalCtx(FakeHandle(), goal_id, 7, state, start=now, vision_since=now)
    n._ctx = ctx
    return ctx


def test_gripper_service_missing_gives_unavailable_once(ready_node) -> None:
    from voss_servo import fsm, grip

    n = ready_node
    ctx = new_ctx(n)
    n._request_gripper(ctx, fsm.GRIPPER_OPEN, 1.0)  # 진짜 클라이언트, 서비스 없음 (HLD D5)
    reply = n._poll_gripper(ctx, 1.03)
    assert reply.message == grip.UNAVAILABLE  # → FSM 이 DEVICE_ERROR(GRIPPER_UNAVAILABLE)
    assert ctx.grip_log["state"] == grip.UNAVAILABLE
    assert n._poll_gripper(ctx, 1.06) is None  # 한 번만 넘긴다


def test_reply_after_goal_end_is_discarded(ready_node) -> None:
    from voss_servo import fsm

    n = ready_node
    cli = FakeGripperCli()
    n._gripper_cli = cli
    ctx = new_ctx(n)
    ctx.state = fsm.FsmState(fsm.GRASP, 1, False)
    n._request_gripper(ctx, fsm.GRIPPER_CLOSE, 1.0)
    n._finish(ctx, fsm.CANCELED, "STOP_OK", False, 1.2)  # 닫는 중에 goal 끝 → 고아
    assert ctx.grip_call is None and n.grip_late_discarded == 0
    cli.futures[0].set_result(gripper_resp())  # 늦게 온 닫기 응답
    assert n.grip_late_discarded == 1  # 버리고 센다
    ctx2 = new_ctx(n, "g2")  # 다음 goal 은 그 응답을 보지 않는다
    assert n._poll_gripper(ctx2, 1.5) is None
    assert cli.requests == [(39.0, 14.0)]  # 끝난 뒤 개방 요청 없음


def test_timed_out_call_late_reply_is_discarded(ready_node) -> None:
    from voss_servo import fsm

    n = ready_node
    cli = FakeGripperCli()
    n._gripper_cli = cli
    ctx = new_ctx(n)
    n._request_gripper(ctx, fsm.GRIPPER_OPEN, 1.0)
    assert n._poll_gripper(ctx, 2.0) is None  # 아직
    reply = n._poll_gripper(ctx, 4.01)  # 3.0 s 넘음
    assert reply.message == "TIMEOUT" and ctx.grip_call is None
    cli.futures[0].set_result(gripper_resp(width=90.0, grip=False))
    assert n.grip_late_discarded == 1


def test_busy_waits_then_retries_once(ready_node) -> None:
    from voss_servo import fsm, grip

    n = ready_node
    cli = FakeGripperCli()
    n._gripper_cli = cli
    ctx = new_ctx(n)
    n._request_gripper(ctx, fsm.GRIPPER_OPEN, 1.0)
    cli.futures[0].set_result(gripper_resp(ok=False, width=0.0, grip=False, message="BUSY"))
    assert n._poll_gripper(ctx, 1.25) is None  # BUSY 첫 번째 → 기다린다
    assert ctx.grip_call.busy_at == 1.25 and ctx.grip_future is None
    assert n._poll_gripper(ctx, 1.625) is None and len(cli.requests) == 1  # 0.5 s 전
    assert n._poll_gripper(ctx, 1.75) is None and len(cli.requests) == 2  # 0.5 s 뒤 재요청
    assert ctx.grip_call.seq == 2 and ctx.grip_call.busy_retries == 1
    cli.futures[1].set_result(gripper_resp(width=90.0, grip=False))
    reply = n._poll_gripper(ctx, 1.9)
    assert reply.ok and reply.message == "OK"
    # 개방은 판정하지 않는다 (verdict null)
    assert ctx.grip_log["state"] == grip.REPLY and ctx.grip_log["verdict"] is None
    assert n.grip_late_discarded == 0  # 소비한 BUSY 응답은 늦은 응답이 아니다
    n._request_gripper(ctx, fsm.GRIPPER_CLOSE, 2.0)
    assert ctx.grip_call.seq == 3  # 순번은 재요청까지 센다 (OPEN 1, 재요청 2, CLOSE 3)


def test_busy_retry_when_service_gone_is_unavailable(ready_node) -> None:
    from voss_servo import fsm, grip

    n = ready_node
    cli = FakeGripperCli()
    n._gripper_cli = cli
    ctx = new_ctx(n)
    n._request_gripper(ctx, fsm.GRIPPER_OPEN, 1.0)
    cli.futures[0].set_result(gripper_resp(ok=False, width=0.0, grip=False, message="BUSY"))
    assert n._poll_gripper(ctx, 1.25) is None  # BUSY → 기다림
    cli.ready = False  # 기다리는 사이 서비스가 사라짐
    assert n._poll_gripper(ctx, 1.75) is None and len(cli.requests) == 1  # 보내지 않는다
    reply = n._poll_gripper(ctx, 1.8)
    assert reply.message == grip.UNAVAILABLE  # 3 s 시간초과를 기다리지 않고 바로 실패 (HLD D5)
    assert ctx.grip_call is None and ctx.grip_log["seq"] == 2


def test_stopping_does_not_poll_gripper(ready_node) -> None:
    from voss_servo import fsm

    n = ready_node
    cli = FakeGripperCli()
    n._gripper_cli = cli
    ctx = new_ctx(n)
    n._request_gripper(ctx, fsm.GRIPPER_OPEN, n._now())
    cli.futures[0].set_result(gripper_resp(ok=False, width=0.0, grip=False, message="BUSY"))
    ctx.state = fsm.FsmState(fsm.PREPARE, 0, True)  # 취소 후 stop 응답 대기
    ev = n._build_event(ctx, n._now())
    assert ev.gripper is None  # 보지 않는다
    assert ctx.grip_call.busy_at is None and len(cli.requests) == 1  # BUSY 재요청 준비도 안 함
