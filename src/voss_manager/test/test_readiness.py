"""readiness — ROBOT 과도 규칙·RobotState 규칙, SERVO·VISION·OCR, LOG 신선도와 비차단 경고."""

from voss_manager.readiness import ReadyInputs, log_warning, not_ready

ALL_OK = ReadyInputs(
    pose_age_s=0.1,
    move_srv=True,
    servo_server=True,
    vision_pubs=1,
    ocr_pubs=1,
    log_age_s=1.0,
    log_status="OK",
)


def with_(**kw) -> ReadyInputs:
    return ReadyInputs(**{**ALL_OK.__dict__, **kw})


def test_all_ready() -> None:
    assert not_ready(ALL_OK) == []


def test_robot_transitional_rule() -> None:
    assert not_ready(with_(pose_age_s=0.6)) == ["ROBOT"]
    assert not_ready(with_(move_srv=False)) == ["ROBOT"]


def test_robot_state_rule_replaces_transitional() -> None:
    rs = dict(
        robot_state_age_s=0.5,
        robot_connected=True,
        robot_state="READY",
        move_srv=False,
        pose_age_s=9.0,
    )
    assert not_ready(with_(**rs)) == []  # RobotState 를 받으면 pose·서비스 존재는 보지 않는다
    assert not_ready(with_(**{**rs, "robot_state": "STOPPED"})) == []
    assert not_ready(with_(**{**rs, "robot_state": "BUSY"})) == ["ROBOT"]
    assert not_ready(with_(**{**rs, "robot_state": "ERROR", "robot_error": "ESTOP"})) == ["ROBOT"]
    assert not_ready(with_(**{**rs, "robot_connected": False})) == ["ROBOT"]
    assert not_ready(with_(**{**rs, "robot_state_age_s": 2.0})) == ["ROBOT"]


def test_robot_busy_ready_only_for_own_motion() -> None:
    """운전 중(우리가 보낸 goal·MoveToZone) BUSY 는 준비, 남이 움직이는 BUSY 는 미준비. 오류·끊김은 늘 미준비."""
    rs = dict(robot_state_age_s=0.5, robot_connected=True, robot_state="BUSY")
    assert not_ready(with_(**rs, own_motion=True)) == []
    assert not_ready(with_(**rs, own_motion=False)) == ["ROBOT"]
    assert not_ready(
        with_(**{**rs, "robot_state": "ERROR", "robot_error": "ESTOP"}, own_motion=True)
    ) == ["ROBOT"]
    assert not_ready(with_(**{**rs, "robot_connected": False}, own_motion=True)) == ["ROBOT"]
    assert not_ready(with_(**{**rs, "robot_state_age_s": 2.0}, own_motion=True)) == ["ROBOT"]


def test_servo_vision_ocr() -> None:
    assert not_ready(with_(servo_server=False, vision_pubs=0, ocr_pubs=0)) == [
        "SERVO",
        "VISION",
        "OCR",
    ]


def test_log_starting_or_stale_blocks_but_db_error_only_warns() -> None:
    assert not_ready(with_(log_status="STARTING")) == ["LOG"]
    assert not_ready(with_(log_age_s=3.5)) == ["LOG"]
    assert not_ready(with_(log_status="")) == ["LOG"]
    assert not_ready(with_(log_status="DB_ERROR")) == []
    assert log_warning("DB_ERROR") == "DB_ERROR" and log_warning("SPOOL_FULL") == "SPOOL_FULL"
    assert log_warning("OK") == ""
