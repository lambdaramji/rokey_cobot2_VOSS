"""box_tracker 기동 (비전 컨테이너 또는 호스트). 실행은 사람이 한다.

  ros2 launch voss_vision box_tracker.launch.py                     # 카메라 실시간
  ros2 launch voss_vision box_tracker.launch.py playback:=<bag 폴더>  # 녹화 재생(로봇 없이)

재생은 녹화 좌표를 /voss/vision/box 로 내보내므로 **운용과 다른 ROS_DOMAIN_ID 에서만** 띄운다(30 이면 노드가 거부).

캘리브레이션 파일은 config_dir(기본: 환경 변수 VOSS_CONFIG_DIR, 없으면 레포 config/)의
belt_homography.yaml·hand_eye.yaml 을 읽는다. 컨테이너에서는 config/ 를 읽기 전용으로 마운트한다.
detector 는 여기서 넘기고 노드가 기동 로그에 남긴다(ADR-0004). 게이트 측정 중에는 바꾸지 않는다.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

DEFAULT_CONFIG_DIR = os.environ.get(
    "VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/config")
)


def generate_launch_description() -> LaunchDescription:
    cfg = LaunchConfiguration("config_dir")
    return LaunchDescription(
        [
            DeclareLaunchArgument("detector", default_value="seg"),
            DeclareLaunchArgument("playback", default_value=""),
            DeclareLaunchArgument("playback_rate", default_value="1.0"),
            DeclareLaunchArgument("config_dir", default_value=DEFAULT_CONFIG_DIR),
            Node(
                package="voss_vision",
                executable="box_tracker",
                name="box_tracker",
                output="screen",
                parameters=[
                    PathJoinSubstitution(
                        [FindPackageShare("voss_vision"), "config", "box_tracker.yaml"]
                    ),
                    {
                        "detector": LaunchConfiguration("detector"),
                        "playback": LaunchConfiguration("playback"),
                        "playback_rate": LaunchConfiguration("playback_rate"),
                        "homography_path": PathJoinSubstitution([cfg, "belt_homography.yaml"]),
                        "hand_eye_path": PathJoinSubstitution([cfg, "hand_eye.yaml"]),
                    },
                ],
            ),
        ]
    )
