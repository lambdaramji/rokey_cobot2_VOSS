"""종료 신호 시험: 실제 belt_servo 프로세스에 SIGINT·SIGTERM 을 보내면 마지막 0 속도가 실제로 나가는가.

rclpy 기본 시그널 처리기는 context 를 먼저 내려 마지막 0 발행이 실패했다(10/09 U2 스모크).
main() 이 처리기를 끄고 KeyboardInterrupt 로 정리하는지 프로세스 밖에서 확인한다 (로봇 없음, 전용 도메인).
"""

import os
import signal
import subprocess
import sys
import time

import pytest
import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from test_node import READY_ARGS

# 시험 전용 도메인: 실행마다 다르게(150~219) — 팀 30~34·스모크 77·e2e 101 과 겹치지 않고,
# 같은 PC 의 다른 세션·이전 실행의 참가자가 servo_cmd 발행자로 잡히지 않게 (10/10 간헐 실패 대응)
TEST_DOMAIN_ID = 150 + os.getpid() % 70


@pytest.fixture
def listener():
    """servo_cmd 를 모으는 시험용 노드."""
    rclpy.init(domain_id=TEST_DOMAIN_ID)
    node = rclpy.create_node("shutdown_listener")
    qos = QoSProfile(
        depth=50, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE
    )
    cmds: list[TwistStamped] = []
    node.create_subscription(TwistStamped, "/voss/robot/servo_cmd", cmds.append, qos)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    yield node, ex, cmds
    ex.shutdown()
    node.destroy_node()
    rclpy.try_shutdown()


def start_servo(tmp_path) -> subprocess.Popen:
    """READY 값으로 belt_servo 를 별도 프로세스로 띄운다."""
    args = [sys.executable, "-m", "voss_servo.belt_servo", "--ros-args"]
    for item in [*READY_ARGS, f"log.dir:={tmp_path}"]:
        args += ["-p", item]
    env = {**os.environ, "ROS_DOMAIN_ID": str(TEST_DOMAIN_ID), "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def spin_until(ex, cond, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        ex.spin_once(timeout_sec=0.02)
    return cond()


@pytest.mark.parametrize(
    "sigs",
    [
        [signal.SIGINT],
        [signal.SIGTERM],
        [signal.SIGINT, signal.SIGINT],  # 래퍼 timeout(그룹) + launch(자식) 가 한 번씩 (U3 실측)
        [signal.SIGINT, signal.SIGTERM],  # launch: SIGINT 뒤 SIGTERM
    ],
    ids=["INT", "TERM", "INT_INT", "INT_TERM"],
)
def test_signal_publishes_final_zero(listener, tmp_path, sigs) -> None:
    node, ex, cmds = listener
    proc = start_servo(tmp_path)
    try:
        # belt_servo 의 servo_cmd 발행자가 보일 때까지 (IDLE 에서는 아무것도 발행하지 않는다)
        found = spin_until(ex, lambda: node.count_publishers("/voss/robot/servo_cmd") > 0, 10.0)
        assert found, "belt_servo 가 뜨지 않음"
        spin_until(ex, lambda: False, 0.5)  # 구독 연결이 자리 잡게
        assert not cmds, f"IDLE 인데 servo_cmd {len(cmds)}개 (다른 발행자?)"
        t_sig = time.monotonic()
        for i, sig in enumerate(sigs):
            if i:
                time.sleep(0.05)  # 50 ms 간격으로 한 번 더
            proc.send_signal(sig)
        spin_until(ex, lambda: proc.poll() is not None and bool(cmds), 5.0)
        exit_s = time.monotonic() - t_sig  # 첫 신호 → 프로세스 끝
    finally:
        if proc.poll() is None:
            proc.kill()
        out = proc.communicate(timeout=5)[0]
    info = (
        f"exit {exit_s:.2f}s rc={proc.returncode} cmds={len(cmds)} domain={TEST_DOMAIN_ID}\n{out}"
    )
    assert proc.returncode == 0, info  # 정상 종료 (예외·강제 종료 아님)
    assert cmds, "종료 때 0 속도가 오지 않음 " + info
    last = cmds[-1].twist.linear
    assert (last.x, last.y, last.z) == (0.0, 0.0, 0.0)
    assert "0 발행 실패" not in out and "context is invalid" not in out
    assert "Traceback" not in out, info  # 두 번째 신호로 정리 중에 죽지 않는다
    assert exit_s < 5.0, info  # ros2 launch 는 5 s 뒤 SIGTERM, 다시 5 s 뒤 SIGKILL
