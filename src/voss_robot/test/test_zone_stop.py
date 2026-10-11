"""MoveToZone 구간 송신: stop 뒤에는 move_line 을 보내지 않는다(#148 리뷰 박병후)."""

import threading
from types import SimpleNamespace

import pytest
from voss_robot.call_queue import SerialCallQueue
from voss_robot.robot_gateway import RobotGatewayNode, _ZoneError


class _FakeDsr:
    def __init__(self):
        self.sent = []

    def move_line_async(self, cmd, vel, acc):
        self.sent.append(cmd)


def _gw(abort: bool):
    ev = threading.Event()
    if abort:
        ev.set()
    return SimpleNamespace(
        _abort=ev,
        dsr=_FakeDsr(),
        queue=SerialCallQueue(),
        zone_vel=[100.0, 45.0],
        zone_acc=[200.0, 90.0],
    )


def test_send_move_after_stop_sends_nothing():
    gw = _gw(abort=True)
    try:
        with pytest.raises(_ZoneError, match="^STOPPED"):
            RobotGatewayNode._send_move(gw, "rise", [1.0] * 6)
        assert gw.dsr.sent == []
    finally:
        gw.queue.close()


def test_send_move_without_stop_sends_once():
    gw = _gw(abort=False)
    try:
        RobotGatewayNode._send_move(gw, "rise", [1.0] * 6)
        assert gw.dsr.sent == [[1.0] * 6]
    finally:
        gw.queue.close()
