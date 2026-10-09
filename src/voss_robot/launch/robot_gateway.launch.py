"""robot_gateway 단독 기동. voss_config.yaml 을 읽어 파라미터로 넘긴다(voss_config.md 값 규칙).

개인 PC (두산 없이):  ros2 launch voss_robot robot_gateway.launch.py [dry_run_object_mm:=40.5]
실기 (사람이 비상정지 옆에서, 브링업 뒤):  ... dry_run:=false [servo_z_min_mm:=<TCP z 하한 mm>]
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
    z_min = LaunchConfiguration("servo_z_min_mm").perform(context)
    if z_min:  # 시험 때 하한을 높여 잡는다(F-04). 비우면 노드 기본값(78 mm)
        params["servo_z_min_mm"] = float(z_min)
    pose_source = LaunchConfiguration("pose_source").perform(context)
    if pose_source:  # service(노드 기본) | joint_states — 10/08 오후 service 값이 0.1 s 마다만 바뀜
        params["pose_source"] = pose_source
    obj = LaunchConfiguration("dry_run_object_mm").perform(context)
    if obj:  # dry_run 가짜 RG2 의 물체 폭(보고값 mm). 비우면 물체 없음 → grip_detected 항상 false
        params["dry_run_object_mm"] = float(obj)
    zone_vel = LaunchConfiguration("zone_vel_mm_s").perform(context)
    if zone_vel:  # MoveToZone 선속도. 첫 실기는 낮게. 비우면 노드 기본값(100 mm/s, 45 deg/s)
        params["zone_vel"] = [float(zone_vel), 45.0]
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
            DeclareLaunchArgument("servo_z_min_mm", default_value=""),
            DeclareLaunchArgument("zone_vel_mm_s", default_value=""),
            DeclareLaunchArgument("pose_source", default_value=""),
            DeclareLaunchArgument("dry_run_object_mm", default_value=""),
            DeclareLaunchArgument("config", default_value="~/voss_ws/config/voss_config.yaml"),
            OpaqueFunction(function=_gateway),
        ]
    )
