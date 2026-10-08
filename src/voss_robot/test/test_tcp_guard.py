"""TCP 등록 확인·경로 이탈 (10/08 18:26: 등록 풀린 채 OBSERVE → 246 mm 수직 하강)."""

import pytest
from voss_robot.doosan import DryRunDoosan
from voss_robot.geometry import (
    controller_tcp_offset,
    flange_to_tcp,
    segment_distance_mm,
    tcp_mismatch_mm,
)

OBS = [-11.51, -271.11, 450.16, 85.25, -179.07, -6.03]  # voss_config observe_pose (플랜지)
TCP = [1.382, 2.684, 246.642]  # voss_config robot.tcp_offset_mm


def test_segment_distance():
    a, b = [0.0, 0.0, 0.0], [100.0, 0.0, 0.0]
    assert segment_distance_mm(a, b, [50.0, 0.0, 0.0]) == pytest.approx(0.0)
    assert segment_distance_mm(a, b, [50.0, 0.0, -20.0]) == pytest.approx(20.0)
    assert segment_distance_mm(a, b, [130.0, 0.0, 0.0]) == pytest.approx(30.0)  # 지나침
    assert segment_distance_mm(a, a, [0.0, 0.0, -5.0]) == pytest.approx(5.0)  # 제자리 목표


def test_mismatch_zero_when_registered():
    d = DryRunDoosan(OBS, TCP)
    ctrl, sol = d.current_posx()
    assert sol == 2
    assert tcp_mismatch_mm(ctrl, d.get_flange_posx(), TCP) == pytest.approx(0.0, abs=1e-6)


def test_mismatch_is_tool_length_when_unregistered():
    d = DryRunDoosan(OBS, TCP)
    d.tcp_registered = False
    ctrl, _ = d.current_posx()
    assert tcp_mismatch_mm(ctrl, d.get_flange_posx(), TCP) == pytest.approx(246.67, abs=0.1)


def test_unregistered_move_line_to_observe_goes_straight_down():
    """사고 재현: 홈에서 OBSERVE(TCP 좌표)로 move_line → 플랜지가 툴 길이만큼 수직으로 내려가는 목표."""
    d = DryRunDoosan(OBS, TCP)
    d.tcp_registered = False
    d.move_line_async(flange_to_tcp(OBS, TCP), [30.0, 45.0], [200.0, 90.0])
    tgt = d._target  # 플랜지 목표 = TCP 좌표 그대로 (−14.5, −276.5, 203.6): x·y 6 mm, z −246.6
    assert tgt[:3] == pytest.approx(flange_to_tcp(OBS, TCP)[:3])
    assert OBS[2] - tgt[2] == pytest.approx(246.6, abs=0.5)
    # gateway pose(config 오프셋 TCP)로 보면 출발=목표인데 내려간다 → 경로 이탈로 잡힌다
    start = flange_to_tcp(OBS, TCP)[:3]
    later = flange_to_tcp([OBS[0], OBS[1], OBS[2] - 20.0, *OBS[3:]], TCP)[:3]
    assert segment_distance_mm(start, start, later) > 15.0


def test_controller_tcp_offset_picks_frame():
    d = DryRunDoosan(OBS, TCP)
    ctrl, _ = d.current_posx()
    assert controller_tcp_offset(ctrl, OBS, TCP, 3.0)[0] == TCP  # 등록 = voss_config
    d.tcp_registered = False
    ctrl, _ = d.current_posx()
    assert controller_tcp_offset(ctrl, OBS, TCP, 3.0)[0] == [0.0, 0.0, 0.0]  # 등록 없음 → 플랜지
    other = flange_to_tcp(OBS, [0.0, 0.0, 200.0])  # 다른 툴이 걸려 있음
    off, d_cfg, d_none = controller_tcp_offset(other, OBS, TCP, 3.0)
    assert off is None and d_cfg > 40 and d_none > 190


def test_unregistered_flange_commands_reach_same_place():
    """등록 없음 + 플랜지 좌표로 보내면 등록 있음 + TCP 좌표와 같은 곳으로 간다(ikin 근사도 같음)."""
    tgt = [446.08, 160.78, 300.0, 14.28, 180.0, -75.33]  # B 구역 위 (플랜지)
    reg, unreg = DryRunDoosan(OBS, TCP), DryRunDoosan(OBS, TCP)
    unreg.tcp_registered = False
    reg.move_line_async(flange_to_tcp(tgt, TCP), [100.0, 45.0], [200.0, 90.0])
    unreg.move_line_async(tgt, [100.0, 45.0], [200.0, 90.0])
    assert unreg._target[:3] == pytest.approx(reg._target[:3])
    assert unreg.ikin(tgt, 2) == reg.ikin(flange_to_tcp(tgt, TCP), 2)
