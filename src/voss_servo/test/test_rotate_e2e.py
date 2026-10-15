"""S2-T18 J6 회전 액션 경로 시험 (DD 9절 #23~#26, pseudo r2 10절).

test_action_e2e 의 가짜 클라이언트를 이어받아 두 가지만 바꾼다:
- pose: 받은 servo_cmd 각속도를 로봇 각가속(robot_alpha) 램프로 적분해, 공구가 아래를 보는 쿼터니언
  Rz(ψ)·Rx(π) 로 낸다 (integrate_angular=False 면 자세 고정 = T17 전 gateway·dry_run 흉내).
- 박스: TCP 보다 60 mm 상류에서 출발(DOWNSTREAM 회피), BoxTrack yaw_base·yaw_valid 를 채운다.
실행별 도메인(150 + pid % 70)은 test_action_e2e 와 같다.
"""

import math
import threading
import time

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from test_action_e2e import (
    BELT_V,
    BOX_TOP_Z,
    MOVING,
    SIX_PHASES,
    TEST_DOMAIN_ID,
    FakeClient,
    FakeGripper,
    _ready_args,
    goal_ends,
    read_jsonl,
    send,
    spin_for,
    spin_until,
    spin_until_true,
)
from voss_servo.belt_servo import BeltServoNode

from voss_msgs.msg import BoxTrack
from voss_servo import rotate as rt

HOME_DEG = -88.72  # 관측 자세 공구 yaw
BELT_YAW = math.atan2(BELT_V[1], BELT_V[0])  # 시험 벨트 방향 각 (≈ −0.74°)
ROT_PARAMS = {
    "rotate.enable": "true",  # -p 문자열 (ROS 가 bool 로 읽는다)
    "rotate.deadband_deg": 4.0,
    "rotate.min_deg": 10.0,
    "rotate.max_deg": 45.0,
    "rotate.n_min": 5,
    "rotate.buffer_n": 15,
    "rotate.r_min": 0.97,
    "rotate.decide_max_s": 0.5,
    "rotate.start_tol_deg": 3.0,
    "rotate.omega_max_dps": 60.0,
    "rotate.alpha_dps2": 90.0,
    "rotate.tol_deg": 1.5,
    "rotate.omega_floor_dps": 3.0,
    "rotate.hold_dz_mm": 50.0,
    "rotate.settle_s": 0.3,
    "rotate.stall_s": 0.6,
    "rotate.still_dps": 2.0,
    "rotate.return_min_dz_mm": 10.0,
    "rotate.pose_fresh_s": 0.05,
}
ROT_ON = {**MOVING["params"], **ROT_PARAMS, "input.pose_lag_ms": 0.0}  # joint_states 짝


class RotFakeClient(FakeClient):
    """각속도를 적분해 공구 yaw 를 바꾸는 가짜 gateway + yaw 를 내는 가짜 box_tracker."""

    def __init__(self, box_yaw_deg: float, integrate_angular: bool, robot_alpha_dps2: float):
        super().__init__(stop_ok=True, box="moving", integrate=True)
        self.psi = math.radians(HOME_DEG)  # 가짜 공구 yaw
        self.w = 0.0  # 가짜 J6(베이스 Z) 각속도
        self.alpha = math.radians(robot_alpha_dps2)  # 가짜 로봇 각가속 램프
        self.integrate_angular = integrate_angular
        self.box_yaw = rt.fold_half(BELT_YAW + math.radians(box_yaw_deg))
        self._last_rot_t = time.monotonic()

    def _pub_pose(self) -> None:
        now = time.monotonic()
        dt = now - self._last_rot_t
        self._last_rot_t = now
        if self.integrate_angular and self.cmds:
            want = self.cmds[-1].twist.angular.z  # 마지막 지령
            step = self.alpha * dt
            self.w += max(-step, min(step, want - self.w))  # 로봇 램프
            self.psi += self.w * dt
        super()._pub_pose()  # 위치 적분·발행은 부모가. 자세는 _patch_orientation 이 발행 직전에 넣는다

    def _pub_box(self) -> None:
        t = time.monotonic() - self._box_t0
        msg = BoxTrack()
        msg.track_id = 7
        msg.stamp = self.get_clock().now().to_msg()
        msg.position_valid = True
        msg.position_source = BoxTrack.SOURCE_HAND_EYE
        msg.position_base.x = -0.060 + BELT_V[0] * t  # TCP(x 0) 보다 60 mm 상류에서 출발
        msg.position_base.y = BELT_V[1] * t
        msg.position_base.z = BOX_TOP_Z
        msg.yaw_base = self.box_yaw
        msg.yaw_valid = True
        self.box_pub.publish(msg)


def _patch_orientation(client: RotFakeClient) -> None:
    """부모 _pub_pose 가 만드는 PoseStamped 에 자세를 넣도록 발행기를 감싼다."""
    pub = client.pose_pub
    original = pub.publish

    def publish(msg):
        x, y, z, w = rt.down_quat(client.psi)
        o = msg.pose.orientation
        o.x, o.y, o.z, o.w = x, y, z, w
        original(msg)

    pub.publish = publish


@pytest.fixture
def renv(tmp_path, request):
    """회전 시험용 READY 노드 + 회전 가짜 클라이언트 + 가짜 그리퍼(별도 스레드)."""
    cfg = request.param
    args = ["--ros-args", "-p", f"log.dir:={tmp_path}"]
    for item in _ready_args(cfg["params"]):
        args += ["-p", item]
    rclpy.init(args=args, domain_id=TEST_DOMAIN_ID)
    node = BeltServoNode()
    client = RotFakeClient(cfg["yaw"], cfg.get("integrate_angular", True), cfg.get("alpha", 90.0))
    _patch_orientation(client)
    gripper = FakeGripper({})
    g_ex = MultiThreadedExecutor()
    g_ex.add_node(gripper)
    g_thread = threading.Thread(target=g_ex.spin, daemon=True)
    g_thread.start()
    assert node._gripper_cli.wait_for_service(timeout_sec=2.0)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    ex.add_node(client)
    yield node, client, ex, tmp_path
    g_ex.shutdown(timeout_sec=2.0)
    g_thread.join(timeout=2.0)
    gripper.destroy_node()
    ex.shutdown()
    node.destroy_node()
    client.destroy_node()
    rclpy.try_shutdown()


def goal_ticks(tmp) -> list[dict]:
    """0 유지 행을 뺀 goal 진행 틱."""
    return [t for t in read_jsonl(tmp / "ticks") if t["cause"] != "ZERO_HOLD"]


def states_in_order(ticks: list[dict]) -> list[str]:
    """바뀐 순서의 회전 상태. goal 전에 프레임이 차 있으면 첫 틱에 결정해 COLLECT 가 안 남는다(A 안) → 뺀다."""
    out: list[str] = []
    for t in ticks:
        s = t.get("rot_state")
        if s and (not out or out[-1] != s):
            out.append(s)
    return [x for x in out if x != "COLLECT"]


@pytest.mark.parametrize("renv", [{"params": ROT_ON, "yaw": 30.0}], indirect=True)
def test_rotation_success_then_return(renv) -> None:
    """#23 30° 박스: 돌고 → 정착 → DESCEND 때 남은 각 ≤ tol → OK, LIFT·VERIFY 에서 되돌림.
    각속도는 PREPARE·TRACK·LIFT·VERIFY 틱에서만 (D0 문안)."""
    node, client, ex, tmp = renv
    spin_for(ex, 0.4)  # goal 전 yaw 프레임이 버퍼에 쌓이게
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 20.0)
    assert res.status == GoalStatus.STATUS_SUCCEEDED, res.result.reason
    assert client.feedback == SIX_PHASES
    ticks = goal_ticks(tmp)
    seq = states_in_order(ticks)
    assert seq[:3] == ["ROTATING", "SETTLING", "DONE"], seq
    assert "RETURNED" in seq or "RETURNING" in seq
    first_descend = next(t for t in ticks if t["phase"] == "DESCEND")
    assert abs(first_descend["rot_err_deg"]) <= 1.5
    assert first_descend["rot_delta_deg"] == pytest.approx(30.0, abs=0.5)
    moving = {t["phase"] for t in ticks if abs(t["wz_cmd_dps"] or 0.0) > 1e-9}
    assert moving <= {"PREPARE", "TRACK", "LIFT", "VERIFY"}, moving
    end = goal_ends(tmp)[-1]
    assert end["rot_time_s"] is not None and 0.8 < end["rot_time_s"] < 2.5


@pytest.mark.parametrize(
    "renv", [{"params": ROT_ON, "yaw": 30.0, "integrate_angular": False}], indirect=True
)
def test_stall_fallback_then_normal_grasp(renv) -> None:
    """#24 자세가 안 바뀌는 gateway(T17 전·dry_run): STALL → 정지 확인 → FALLBACK → 지금 방식으로 OK."""
    node, client, ex, tmp = renv
    spin_for(ex, 0.4)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 20.0)
    assert res.status == GoalStatus.STATUS_SUCCEEDED, res.result.reason
    ticks = goal_ticks(tmp)
    seq = states_in_order(ticks)
    assert seq[:3] == ["ROTATING", "STOPPING", "FALLBACK"], seq
    assert any(t["rot_cause"] == "STALL" for t in ticks)
    stop = [t for t in ticks if t["rot_state"] == "STOPPING"]
    assert all(t["wz_cmd_dps"] == 0.0 for t in stop)  # STOPPING 의 각속도는 즉시 0
    assert all(t["phase"] in ("PREPARE", "TRACK") for t in ticks if t["rot_state"] == "ROTATING")


@pytest.mark.parametrize("renv", [{"params": MOVING["params"], "yaw": 30.0}], indirect=True)
def test_rotate_off_regression(renv) -> None:
    """#25 회전 off(키 없음): 박스에 yaw 가 있어도 각속도 전부 0, 회전 로그 null, 결과·phase 같음."""
    node, client, ex, tmp = renv
    spin_for(ex, 0.4)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 15.0)
    assert res.status == GoalStatus.STATUS_SUCCEEDED and client.feedback == SIX_PHASES
    spin_for(ex, 0.6)  # 0 유지 구간까지
    assert all(c.twist.angular.z == 0.0 for c in client.cmds)
    rows = read_jsonl(tmp / "ticks")
    assert any(r["cause"] == "ZERO_HOLD" for r in rows)  # 0 유지 행이 남는다 (r1-1 회귀)
    assert all(r[k] is None for r in rows for k in ("rot_state", "rot_cause", "wz_cmd_dps"))
    assert not node._rot_on


@pytest.mark.parametrize("renv", [{"params": ROT_ON, "yaw": 40.0}], indirect=True)
def test_cancel_during_rotation_zeroes_angular(renv) -> None:
    """#26 ROTATING 중 취소 → 취소 뒤 발행은 각속도 0, CANCELED."""
    node, client, ex, tmp = renv
    spin_for(ex, 0.4)
    handle = send(client, ex)
    spin_until_true(ex, lambda: node._ctx is not None and node._ctx.rot.state == rt.ROTATING, 3.0)
    spin_for(ex, 0.2)  # 각속도가 나오기 시작하게
    assert any(c.twist.angular.z != 0.0 for c in client.cmds)
    n_before = len(client.cmds)
    spin_until(ex, handle.cancel_goal_async(), 2.0)
    res = spin_until(ex, handle.get_result_async(), 5.0)
    assert res.status == GoalStatus.STATUS_CANCELED
    after = client.cmds[n_before + 1 :]  # 취소 요청이 처리된 다음 틱부터
    assert after and all(c.twist.angular.z == 0.0 for c in after)


@pytest.mark.parametrize("renv", [{"params": ROT_ON, "yaw": 30.0}], indirect=True)
def test_no_home_after_rotation_means_no_rotation(renv) -> None:
    """주관 검수 a: 이 노드가 이미 돈 뒤 기준이 비어 있으면(늦게 잡지 않음) NO_POSE_YAW, 각속도 0, 결과 OK."""
    node, client, ex, tmp = renv
    node._rot_ever, node._home_ref = True, None  # 앞 goal 이 돌았고 기준을 못 잡은 상황
    spin_for(ex, 0.4)
    handle = send(client, ex)
    res = spin_until(ex, handle.get_result_async(), 15.0)
    assert res.status == GoalStatus.STATUS_SUCCEEDED
    ticks = goal_ticks(tmp)
    assert {t["rot_state"] for t in ticks} <= {"COLLECT", "SKIP"}
    assert any(t["rot_cause"] == "NO_POSE_YAW" for t in ticks)
    assert all(c.twist.angular.z == 0.0 for c in client.cmds) and node._home_ref is None
