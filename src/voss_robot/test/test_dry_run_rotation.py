"""dry_run 가짜 로봇이 speedl 각속도를 TCP 둘레로 적분하는지 (S2-T17 — 시뮬에서 belt_servo 회전이 보이게)."""

import time

import pytest
from voss_robot.doosan import DryRunDoosan
from voss_robot.geometry import flange_to_tcp, tool_yaw_deg

OBS = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]
OFF = [1.382, 2.684, 246.642]


def test_fake_rotates_about_tcp_and_stops():
    d = DryRunDoosan(OBS, OFF)
    t0 = flange_to_tcp(d.get_flange_posx(), OFF)
    d.speedl([0.0, 0.0, 0.0], [100.0, 90.0], 30.0)
    t_start = time.monotonic()
    time.sleep(0.2)
    d.speedl([0.0, 0.0, 0.0], [100.0, 90.0], 0.0)
    dt = time.monotonic() - t_start
    p = d.get_flange_posx()
    assert tool_yaw_deg(*p[3:]) - tool_yaw_deg(*OBS[3:]) == pytest.approx(30.0 * dt, abs=1.0)
    assert flange_to_tcp(p, OFF)[:3] == pytest.approx(t0[:3], abs=1e-6)
    time.sleep(0.05)
    assert d.get_flange_posx() == pytest.approx(p)  # 0 지령 뒤 멈춤


def test_move_stop_zeroes_rotation():
    d = DryRunDoosan(OBS, OFF)
    d.speedl([0.0, 0.0, 0.0], [100.0, 90.0], 30.0)
    d.move_stop_async(lambda ok, msg: None)
    p = d.get_flange_posx()
    time.sleep(0.05)
    assert d.get_flange_posx() == pytest.approx(p)
