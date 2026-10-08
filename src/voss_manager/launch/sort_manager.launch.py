"""sort_manager 기동 (호스트). 실행은 사람이 비상정지 옆에서 한다 — TrackAndGrasp·MoveToZone·stop 을 부른다.

  ros2 launch voss_manager sort_manager.launch.py
  ros2 launch voss_manager sort_manager.launch.py config_dir:=$HOME/voss_ws/config

voss_config.yaml 은 config_dir(기본: 환경 변수 VOSS_CONFIG_DIR, 없으면 레포 config/)에서 읽는다.
sort_logger 를 먼저 띄운다 — LOG 미준비면 start 를 거부한다(SortResult 는 volatile 이라 늦게 뜬 logger 는 못 받는다).
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
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_dir", default_value=DEFAULT_CONFIG_DIR),
            DeclareLaunchArgument("home_first", default_value="true"),
            Node(
                package="voss_manager",
                executable="sort_manager",
                name="sort_manager",
                output="screen",
                parameters=[
                    PathJoinSubstitution(
                        [FindPackageShare("voss_manager"), "config", "sort_manager.yaml"]
                    ),
                    {
                        "config_path": PathJoinSubstitution(
                            [LaunchConfiguration("config_dir"), "voss_config.yaml"]
                        ),
                        "home_first": LaunchConfiguration("home_first"),
                    },
                ],
            ),
        ]
    )
