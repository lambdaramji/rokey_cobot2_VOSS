"""RobotState 판정 — voss_msgs.md RobotState (connected·state·action·error_code)."""

from voss_robot.state_logic import Inputs, decide


def ok(**kw) -> Inputs:
    base = dict(dsr_ok=True, ctrl_state=1, disconnected=False, rg2_ok=True, rg2_safety=False,
                servo_active=False, gripper_busy=False)  # fmt: skip
    base.update(kw)
    return Inputs(**base)


def test_ready_when_all_connected_and_idle():
    s = decide(ok())
    assert (s.connected, s.state, s.action, s.error_code) == (True, "READY", "", "")
    assert "STANDBY" in s.detail


def test_busy_actions():
    assert decide(ok(servo_active=True)).key() == (True, "BUSY", "SERVO", "")
    assert decide(ok(gripper_busy=True)).key() == (True, "BUSY", "GRIPPER", "")
    assert decide(ok(zone_action="MOVE_TO_ZONE:B", gripper_busy=True)).action == "MOVE_TO_ZONE:B"


def test_stopped_until_new_motion():
    assert decide(ok(stopped=True)).state == "STOPPED"
    assert decide(ok(stopped=True, servo_active=True)).state == "BUSY"


def test_estop_and_safety_stop():
    assert decide(ok(ctrl_state=6)).key()[2:] == ("", "ESTOP")
    assert decide(ok(ctrl_state=6)).state == "ERROR"
    for c in (3, 5, 9, 10):
        assert decide(ok(ctrl_state=c)).error_code == "SAFETY_STOP"


def test_doosan_problems_are_timeout_and_disconnect():
    s = decide(ok(dsr_ok=False))
    assert (s.connected, s.state, s.error_code) == (False, "ERROR", "TIMEOUT")
    assert decide(ok(disconnected=True)).error_code == "TIMEOUT"
    assert decide(ok(ctrl_state=0)).error_code == "TIMEOUT"  # INITIALIZING 은 운전 불가
    assert decide(ok(ctrl_state=None)).error_code == ""  # 아직 모름은 오류로 보지 않는다


def test_gripper_errors():
    s = decide(ok(rg2_ok=False))
    assert (s.connected, s.error_code) == (False, "GRIPPER_ERROR")
    assert decide(ok(rg2_safety=True)).error_code == "GRIPPER_ERROR"


def test_estop_wins_over_others():
    assert decide(ok(ctrl_state=6, rg2_ok=False, dsr_ok=False)).error_code == "ESTOP"


def test_alarm_only_in_detail():
    s = decide(ok(last_alarm="2/2/1206 NOT REACHABLE"))
    assert s.error_code == "" and "1206" in s.detail


def test_tcp_note_in_detail():
    """컨트롤러 TCP 등록이 없을 때(플랜지 모드) detail 에 보인다(#121)."""
    note = "TCP 등록 없음(플랜지 모드 — 펜던트 공간 제한이 핑거 끝을 못 막음)"
    st = decide(ok(tcp_note=note))
    assert note in st.detail and st.state == "READY"


def test_rg2_fake_note_in_detail():
    """두산 real + 가짜 RG2(rg2_dry_run)는 상태가 READY 여도 detail 에 보인다(#139)."""
    st = decide(ok(rg2_note="RG2 FAKE(rg2_dry_run)"))
    assert "RG2 FAKE" in st.detail and st.state == "READY"
