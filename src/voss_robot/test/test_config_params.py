"""config_params.py 시험: 레포 config/voss_config.yaml(10/06 실측)과 null 규칙."""

from pathlib import Path

import pytest
from voss_robot.config_params import gateway_params, load_config

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config" / "voss_config.yaml"


def test_repo_config_values():
    cfg, sha = load_config(REPO_CONFIG)
    p = gateway_params(cfg, sha)
    assert p["tcp_offset_mm"] == pytest.approx([1.382, 2.684, 246.642])
    assert p["observe_pose"][:3] == pytest.approx([-11.51, -271.11, 450.16])
    assert p["zones.A.grid"] == [3.0, 1.0, 60.0, 0.0]
    assert p["zones.HOLD.grid"] == [2.0, 1.0, 60.0, 0.0]  # config 키 hold → 대문자 HOLD
    assert p["zones.C.grid"] == [3.0, 1.0, 50.0, -30.0]  # 10/08 칸 −80/−30/+20
    assert p["gripper.force_n"] == 14.0
    assert len(p["config_sha256"]) == 12


def test_null_values_are_left_out():
    cfg = {
        "version": 1,
        "robot": {"tcp_offset_mm": None},
        "observe_pose": None,
        "zones": {"A": {"pose": None, "grid": {"cols": 3, "rows": 1, "pitch_mm": 60}}},
        "gripper": {"force_n": None},
    }
    p = gateway_params(cfg, "abc")
    assert "tcp_offset_mm" not in p  # null = 미측정 → 넘기지 않는다
    assert "observe_pose" not in p
    assert "zones.A.pose" not in p
    assert "gripper.force_n" not in p
    assert p["zones.A.grid"] == [3.0, 1.0, 60.0, 0.0]


def test_layers_append_to_grid():
    z = {"grid": {"cols": 3, "rows": 2, "pitch_mm": 60, "layers": 2}}
    p = gateway_params({"zones": {"A": z, "B": {**z, "grid": {**z["grid"], "layer_mm": 30}}}}, "x")
    assert p["zones.A.grid"] == [3.0, 2.0, 60.0, 0.0, 2.0, 27.0]  # layer_mm 기본 27 = 박스 높이
    assert p["zones.B.grid"][4:] == [2.0, 30.0]
    q = gateway_params({"zones": {"C": {"grid": {"cols": 3, "rows": 2, "pitch_mm": 50, "pitch_y_mm": 44}}}}, "x")
    assert q["zones.C.grid"] == [3.0, 2.0, 50.0, 0.0, 1.0, 27.0, 44.0]


def test_in_tray_height_per_zone_and_order_ignored():
    z = {"grid": {"cols": 3, "rows": 2, "pitch_mm": 50, "order": [5, 2, 4, 1, 3, 0]}, "in_tray_tcp_z_mm": 40}
    p = gateway_params({"zones": {"C": z, "A": {"in_tray_tcp_z_mm": None}}}, "x")
    assert p["zones.C.in_tray_tcp_z_mm"] == 40.0 and "zones.A.in_tray_tcp_z_mm" not in p
    assert p["zones.C.grid"] == [3.0, 2.0, 50.0, 0.0]  # order 는 sort_manager 가 쓴다


def test_place_open_passes_when_set():
    p = gateway_params({"gripper": {"pre_open_mm": 90, "place_open_mm": 50}}, "x")
    assert (p["gripper.pre_open_mm"], p["gripper.place_open_mm"]) == (90.0, 50.0)
    assert "gripper.place_open_mm" not in gateway_params({"gripper": {"pre_open_mm": 90}}, "x")


def test_wrong_length_is_left_out():
    p = gateway_params({"robot": {"tcp_offset_mm": [1, 2]}, "observe_pose": [0, 0, 0]}, "x")
    assert "tcp_offset_mm" not in p and "observe_pose" not in p
