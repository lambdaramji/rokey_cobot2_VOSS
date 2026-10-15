"""robot_gateway 단독 기동. voss_config.yaml 을 읽어 파라미터로 넘긴다(voss_config.md 값 규칙).

개인 PC (두산 없이):  ros2 launch voss_robot robot_gateway.launch.py [dry_run_object_mm:=40.5]
실기 (사람이 비상정지 옆에서, 브링업 뒤):  ... dry_run:=false [servo_z_min_mm:=<TCP z 하한 mm>]
J6 회전(S2-T18) 시험만:  ... servo_angular:=true — servo_cmd angular.z 를 speedl 로 넘긴다(기본 off, 시연 라인 금지).
config 기본 = ~/voss_ws/config/voss_config.yaml (레포 config/ 를 복사한 호스트 사본).
MoveToZone 기본 = 300 mm/s · 900 mm/s² · 위 모서리 블렌딩 30 mm (S2-T17). 450 은 A 칸 → OBSERVE 직선이
    J1 축 74 mm 옆을 지나 J1 이 150 deg/s 에 걸렸다가 급감속 → 두산 9015 충돌 감지(10/14 3/3). 350 은 10/10 OK → 여유 두고 300.
    느리게: zone_vel_mm_s:=100 zone_acc_mm_s2:=200 zone_blend_mm:=0 (옛 기본 — 첫 실기·교시 확인용)

[실기 금지] 두산 에뮬레이터(브링업 mode:=virtual, RG2 없음) 전용 — 두산 real + RG2 가짜:
    ... dry_run:=false rg2_dry_run:=true [dry_run_object_mm:=40.5]
    에뮬레이터 노드(/dsr01/virtual_node)가 없으면 gateway 가 기동을 거부한다(#139).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from voss_robot.config_params import gateway_params, load_config


def rg2_params(rg2_dry_run: str, host: str, port: str) -> dict:
    """RG2 launch 인자 → 노드 파라미터. 빈 값은 넘기지 않는다(노드 기본 192.168.1.1:502, 실 RG2)."""
    params = {}
    # 두산 에뮬레이터 + RG2 가짜 (가상 실험, #41). 이때 host·port 는 안 쓴다
    if rg2_dry_run.lower() == "true":
        params["rg2_dry_run"] = True
    if host:
        params["rg2_host"] = host
    if port:
        try:
            params["rg2_port"] = int(port)
        except ValueError:
            raise ValueError(f"rg2_port 는 정수(예 502): {port!r}") from None
    return params


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
    params.update(
        rg2_params(
            *(
                LaunchConfiguration(k).perform(context)
                for k in ("rg2_dry_run", "rg2_host", "rg2_port")
            )
        )
    )
    zone_vel = LaunchConfiguration("zone_vel_mm_s").perform(context)
    if zone_vel:  # MoveToZone 선속도(기본 300). 빈 값이면 노드 기본(100 mm/s, 45 deg/s)
        params["zone_vel"] = [float(zone_vel), 45.0]
    blend = LaunchConfiguration("zone_blend_mm").perform(context)
    if blend:  # 위쪽 모서리 블렌딩 mm(기본 30). 빈 값이면 노드 기본 0(모서리마다 멈춤)
        params["zone_blend_mm"] = float(blend)
    zone_acc = LaunchConfiguration("zone_acc_mm_s2").perform(context)
    if zone_acc:  # MoveToZone 선가속도(기본 900). 빈 값이면 노드 기본(200 mm/s², 90 deg/s²)
        params["zone_acc"] = [float(zone_acc), 90.0]
    if LaunchConfiguration("servo_angular").perform(context).lower() == "true":
        params["servo_angular_enable"] = True  # S2-T17. 비우면 노드 기본 false(각속도 자름)
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
            # 인자를 빼도 시연 속도(10/14 통합이 100 으로 떴음). 450 이면 J1 특이점 근처 9015(10/14)
            DeclareLaunchArgument("zone_vel_mm_s", default_value="300"),
            DeclareLaunchArgument("zone_acc_mm_s2", default_value="900"),
            DeclareLaunchArgument("zone_blend_mm", default_value="30"),
            DeclareLaunchArgument("servo_angular", default_value=""),
            DeclareLaunchArgument("pose_source", default_value=""),
            DeclareLaunchArgument("dry_run_object_mm", default_value=""),
            DeclareLaunchArgument("rg2_dry_run", default_value="false"),
            DeclareLaunchArgument("rg2_host", default_value=""),
            DeclareLaunchArgument("rg2_port", default_value=""),
            DeclareLaunchArgument("config", default_value="~/voss_ws/config/voss_config.yaml"),
            OpaqueFunction(function=_gateway),
        ]
    )
