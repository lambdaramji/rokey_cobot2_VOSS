"""rg2_dry_run(두산 에뮬레이터 + 가짜 RG2) 가드와 launch 인자 매핑 (#139)."""

import importlib.util
from pathlib import Path

import pytest
from voss_robot.doosan import emulator_running

LAUNCH = Path(__file__).resolve().parents[1] / "launch" / "robot_gateway.launch.py"


def _launch():
    spec = importlib.util.spec_from_file_location("robot_gateway_launch", LAUNCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_emulator_running_needs_virtual_node_in_robot_namespace():
    emu = [("dsr_controller2", "/dsr01"), ("virtual_node", "/dsr01")]
    assert emulator_running(emu)
    assert not emulator_running([("dsr_controller2", "/dsr01")])  # 실기(mode:=real)
    assert not emulator_running([("virtual_node", "/dsr02")])  # 다른 로봇 이름
    assert emulator_running([["virtual_node", "/dsr02"]], prefix="/dsr02/dsr_controller2/")


def test_launch_rg2_params():
    rg2_params = _launch().rg2_params
    assert rg2_params("false", "", "") == {}  # 실기 기본: 실 RG2 192.168.1.1:502
    assert rg2_params("True", "", "") == {"rg2_dry_run": True}
    assert rg2_params("false", "127.0.0.1", "5020") == {"rg2_host": "127.0.0.1", "rg2_port": 5020}
    with pytest.raises(ValueError, match="rg2_port"):
        rg2_params("false", "", "50x")
