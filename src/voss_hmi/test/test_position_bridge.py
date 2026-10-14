"""위치 메시지는 장비 구동 없이 기존 MQTT 브리지에서만 직렬화한다."""

from datetime import UTC, datetime
from unittest.mock import Mock

from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import JointState
from voss_hmi.hmi_bridge import HmiBridgeNode

from voss_msgs.msg import BoxTrack


def test_box_track_keeps_observed_position_and_limits_rate():
    bridge = Mock(_last_box_sent={})
    track = BoxTrack()
    track.track_id = 7
    track.stamp.sec = int(datetime.now(UTC).timestamp())
    track.position_valid = True
    track.position_source = BoxTrack.SOURCE_HAND_EYE
    track.position_base.x = 0.431
    track.position_base.y = -0.082
    track.position_base.z = 0.102
    track.calib_version = "test-calibration"

    HmiBridgeNode._on_box_track(bridge, track)
    args, kwargs = bridge._publish_json.call_args
    assert args[0] == "voss/box_track"
    assert args[1]["track_id"] == 7
    assert args[1]["position_base"]["x"] == 0.431
    assert kwargs == {"qos": 0, "retain": False}
    HmiBridgeNode._on_box_track(bridge, track)
    assert bridge._publish_json.call_count == 1


def test_robot_pose_uses_base_link_and_drops_other_frames():
    bridge = Mock(_last_pose_sent=0.0)
    pose = PoseStamped()
    pose.header.stamp.sec = int(datetime.now(UTC).timestamp())
    pose.header.frame_id = "base_link"
    pose.pose.position.x = 0.21
    pose.pose.position.y = -0.27
    pose.pose.position.z = 0.11

    HmiBridgeNode._on_robot_pose(bridge, pose)
    args, kwargs = bridge._publish_json.call_args
    assert args[0] == "voss/robot_pose"
    assert args[1]["position"] == {"x": 0.21, "y": -0.27, "z": 0.11}
    assert kwargs == {"qos": 0, "retain": False}
    pose.header.frame_id = "camera"
    HmiBridgeNode._on_robot_pose(bridge, pose)
    assert bridge._publish_json.call_count == 1


def test_robot_joints_are_ordered_by_name_and_invalid_samples_are_dropped():
    bridge = Mock(_last_joints_sent=0.0)
    joints = JointState()
    joints.header.stamp.sec = int(datetime.now(UTC).timestamp())
    joints.name = ["joint_3", "joint_1", "joint_2", "joint_4", "joint_5", "joint_6"]
    joints.position = [0.3, 0.1, 0.2, 0.4, 0.5, 0.6]
    HmiBridgeNode._on_robot_joints(bridge, joints)
    args, kwargs = bridge._publish_json.call_args
    assert args[0] == "voss/robot_joints"
    assert args[1]["name"] == ("joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6")
    assert args[1]["position"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert kwargs == {"qos": 0, "retain": False}
    joints.name[0] = "other"
    HmiBridgeNode._on_robot_joints(bridge, joints)
    assert bridge._publish_json.call_count == 1


def test_publish_failure_warning_is_throttled():
    from voss_hmi.hmi_bridge import mqtt as bridge_mqtt

    bridge = Mock()
    bridge._mqtt.publish.return_value.rc = bridge_mqtt.MQTT_ERR_NO_CONN
    HmiBridgeNode._publish_json(bridge, "voss/robot_pose", {}, qos=0, retain=False)
    kwargs = bridge.get_logger.return_value.warning.call_args.kwargs
    assert kwargs["throttle_duration_sec"] == 5.0
