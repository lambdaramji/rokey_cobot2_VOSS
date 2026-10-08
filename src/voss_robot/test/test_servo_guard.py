"""ServoGuard — ADR-0010 robot_gateway 적용 조건 (watchdog·stop·z 하한·x 범위·속도 상한)."""

import pytest
from voss_robot.servo_guard import ServoGuard, ServoParams


def guard(**kw) -> ServoGuard:
    g = ServoGuard(ServoParams(**kw))
    g.set_pose(10.0, 0.0, -276.0, 200.0)  # 관측 자세 근처 TCP (mm)
    return g


def test_converts_m_s_to_mm_s():
    g = guard()
    r = g.on_cmd(10.01, 10.0, (0.005, 0.0, 0.0))
    assert r.vel_mm_s == pytest.approx([5.0, 0.0, 0.0])
    assert r.reason == "" and r.clamps == []
    assert g.active


def test_rejects_stamp_older_than_watchdog():
    g = guard(watchdog_s=0.2)
    assert g.on_cmd(10.05, 9.8, (0.005, 0, 0)).reason == "old"


def test_rejects_without_fresh_pose():
    g = guard(pose_max_age_s=0.1)
    assert g.on_cmd(10.2, 10.19, (0.005, 0, 0)).reason == "no_pose"
    g2 = ServoGuard()
    assert g2.on_cmd(1.0, 1.0, (0.005, 0, 0)).reason == "no_pose"


def test_rejects_when_motion_busy():
    g = guard()
    g.motion_busy = True
    assert g.on_cmd(10.01, 10.0, (0.005, 0, 0)).reason == "busy"


def test_speed_limit_keeps_direction():
    g = guard(max_speed_mm_s=100.0)
    r = g.on_cmd(10.01, 10.0, (0.3, 0.4, 0.0))  # 500 mm/s
    assert r.vel_mm_s == pytest.approx([60.0, 80.0, 0.0])
    assert "speed" in r.clamps


def test_angular_is_dropped_and_flagged():
    g = guard()
    r = g.on_cmd(10.01, 10.0, (0.005, 0, 0), (0.0, 0.0, 0.1))
    assert r.vel_mm_s == pytest.approx([5.0, 0.0, 0.0])
    assert "angular" in r.clamps


def test_z_min_cuts_only_downward():
    g = ServoGuard(ServoParams(z_min_mm=78.0, lin_acc_mm_s2=0.0))
    g.set_pose(10.0, 0.0, -276.0, 78.0)
    r = g.on_cmd(10.01, 10.0, (0.01, 0.0, -0.02))
    assert r.vel_mm_s == pytest.approx([10.0, 0.0, 0.0])
    assert r.clamps == ["z_min"]
    up = g.on_cmd(10.02, 10.01, (0.0, 0.0, 0.02))  # 위로는 그대로
    assert up.vel_mm_s == pytest.approx([0.0, 0.0, 20.0]) and up.clamps == []


def test_x_range_cuts_outward_only():
    g = ServoGuard(ServoParams(x_range_mm=(-107.0, 638.0), lin_acc_mm_s2=0.0))
    g.set_pose(10.0, 640.0, -276.0, 200.0)
    r = g.on_cmd(10.01, 10.0, (0.05, 0.0, 0.0))
    assert r.vel_mm_s[0] == 0.0 and "x_max" in r.clamps
    back = g.on_cmd(10.02, 10.01, (-0.05, 0.0, 0.0))
    assert back.vel_mm_s[0] == pytest.approx(-50.0)


def test_tick_clamps_when_prediction_reaches_z_min():
    g = ServoGuard(
        ServoParams(z_min_mm=78.0, pose_max_age_s=0.2, pose_latency_s=0.0, lin_acc_mm_s2=0.0)
    )
    g.set_pose(10.0, 0.0, -276.0, 80.0)
    g.on_cmd(10.0, 10.0, (0.0, 0.0, -0.02))  # −20 mm/s, 80 → 78 mm 까지 0.1 s
    assert g.on_tick(10.05) == ("", None)
    action, vel = g.on_tick(10.11)  # 예측 z = 77.8
    assert action == "clamp" and vel == pytest.approx([0.0, 0.0, 0.0])
    assert g.on_tick(10.12) == ("", None)  # 한 번만


def test_watchdog_expires_once_then_idle():
    g = guard(watchdog_s=0.2, pose_max_age_s=1.0)
    g.on_cmd(10.0, 10.0, (0.005, 0, 0))
    assert g.on_tick(10.19)[0] == ""
    assert g.on_tick(10.21) == ("expire", None)
    assert not g.active
    assert g.on_tick(10.3) == ("", None)


def test_watchdog_also_after_intentional_zero():
    g = guard(watchdog_s=0.2, pose_max_age_s=1.0)
    g.on_cmd(10.0, 10.0, (0.0, 0.0, 0.0))  # belt_servo 의 마지막 0 명령
    assert g.on_tick(10.25) == ("expire", None)  # 그래도 0 속도 + move_stop 은 항상


def test_lost_pose_while_moving_stops():
    g = guard(pose_max_age_s=0.1)
    g.on_cmd(10.01, 10.0, (0.005, 0, 0))
    assert g.on_tick(10.15) == ("expire", None)


def test_stop_drops_older_stamps_and_accepts_new():
    g = guard(pose_max_age_s=1.0)
    g.on_cmd(10.0, 10.0, (0.005, 0, 0))
    g.stop(10.05)
    assert not g.active
    assert g.on_cmd(10.06, 10.04, (0.005, 0, 0)).reason == "stop"  # stop 이전 stamp
    assert g.on_cmd(10.07, 10.06, (0.005, 0, 0)).vel_mm_s == pytest.approx([5.0, 0, 0])


def test_stop_is_idempotent():
    g = guard()
    g.stop(10.0)
    g.stop(10.0)
    assert not g.active and g.on_tick(10.5) == ("", None)


def test_pose_latency_clamps_earlier():
    # −20 mm/s, pose 80 mm. 지연 0.06 s 를 더하면 0.04 s 만에 예측 z 가 78 에 닿는다
    g = ServoGuard(
        ServoParams(z_min_mm=78.0, pose_max_age_s=0.2, pose_latency_s=0.06, lin_acc_mm_s2=0.0)
    )
    g.set_pose(10.0, 0.0, -276.0, 80.0)
    g.on_cmd(10.0, 10.0, (0.0, 0.0, -0.02))
    assert g.on_tick(10.03) == ("", None)
    assert g.on_tick(10.05)[0] == "clamp"


def test_braking_distance_cuts_before_limit():
    # 50 mm/s 하강, acc 100 → 감속 12.5 mm. 하한 78 + 12.5 = 90.5 위에서 이미 잘라야 한다
    g = ServoGuard(ServoParams(z_min_mm=78.0, lin_acc_mm_s2=100.0, pose_latency_s=0.0))
    g.set_pose(10.0, 0.0, -276.0, 95.0)
    assert g.on_cmd(10.0, 10.0, (0.0, 0.0, -0.05)).clamps == []
    g.set_pose(10.0, 0.0, -276.0, 90.0)
    r = g.on_cmd(10.0, 10.0, (0.0, 0.0, -0.05))
    assert r.vel_mm_s[2] == 0.0 and r.clamps == ["z_min"]
    slow = g.on_cmd(10.0, 10.0, (0.0, 0.0, -0.005))  # 5 mm/s 는 감속 0.125 mm 라 계속 내려간다
    assert slow.vel_mm_s[2] == -5.0
