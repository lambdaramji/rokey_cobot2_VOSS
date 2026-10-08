"""robot_gateway 단독 기동. voss_config.yaml 을 읽어 파라미터로 넘긴다(voss_config.md 값 규칙).

개인 PC (두산 없이):  ros2 launch voss_robot robot_gateway.launch.py
실기 (사람이 비상정지 옆에서, 브링업 뒤):  ... dry_run:=false
config 기본 = ~/voss_ws/config/voss_config.yaml (레포 config/ 를 복사한 호스트 사본).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from voss_robot.config_params import gateway_params, load_config


def _gateway(context):
    cfg, sha = load_config(LaunchConfiguration("config").perform(context))
    params = gateway_params(cfg, sha)
    params["dry_run"] = LaunchConfiguration("dry_run").perform(context).lower() == "true"
    return [
        Node(
            package="voss_robot",
            executable="robot_gateway",
            name="robot_gateway",
            output="screen",
            parameters=[params],
        )
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("dry_run", default_value="true"),
            DeclareLaunchArgument("config", default_value="~/voss_ws/config/voss_config.yaml"),
            OpaqueFunction(function=_gateway),
        ]
    )
