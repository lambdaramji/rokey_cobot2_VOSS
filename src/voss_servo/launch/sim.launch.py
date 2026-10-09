"""개인 PC 시뮬 (sim 전용): fake_box + robot_gateway dry_run + belt_servo (design/U3-dd.md 5절).

보통은 sim_check 가 이 launch 를 case 마다 띄우고 끈다 (U3-run.md B). 직접 띄울 때:
  cd ~/cobot2/cobot2_voss
  voss-ros ros2 launch voss_servo sim.launch.py config:=$PWD/config/voss_config.yaml \
    scenario:=normal log_dir:=/tmp/voss_sim/manual
인자: config(필수, 레포 voss_config.yaml) · scenario(normal|invalid_after_s|lost_after_s|two_boxes)
      · object_mm(gateway dry_run_object_mm, 0 = 빈손) · kp(control.kp_per_s 덮어쓰기)
      · log_dir · invalid_after_s · lost_after_s
- gateway 는 **항상 dry_run:=true** (인자로 받지 않는다 — 시뮬에서 실기로 새지 않게).
- fake_box 의 벨트 속도·방향은 voss_config 에서 읽어 넘긴다 (숫자를 복사하지 않는다).
"""

import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from voss_servo.launch_params import config_values, expand, file_sha, load_yaml


def _write_overrides(folder: str, kp: str) -> str:
    """kp 를 덮어쓰는 작은 YAML 을 만들고 경로를 돌려준다."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "sim_overrides.yaml")
    body = {"belt_servo": {"ros__parameters": {"control": {"kp_per_s": float(kp)}}}}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(body, f)
    return path


def _setup(context):
    """인자 → [로그, fake_box, gateway include, belt_servo include]."""

    def arg(name: str) -> str:
        return LaunchConfiguration(name).perform(context).strip()  # launch 인자 문자열

    config = arg("config")
    if not config:
        raise RuntimeError("sim.launch 는 config:=<레포>/config/voss_config.yaml 필수")
    config = expand(config)
    cfg = config_values(load_yaml(config), file_sha(config))  # belt 값 (launch_params 재사용)
    servo_share = get_package_share_directory("voss_servo")
    robot_share = get_package_share_directory("voss_robot")
    log_dir = arg("log_dir")
    overrides = ""
    if arg("kp"):  # kp 만 바꾸는 덮어쓰기 파일
        folder = expand(log_dir) if log_dir else tempfile.mkdtemp(prefix="voss_sim_")
        overrides = _write_overrides(folder, arg("kp"))
    fake = Node(
        package="voss_servo",
        executable="fake_box",
        name="fake_box",
        output="screen",
        parameters=[
            {
                "scenario": arg("scenario"),
                "speed_cmps": float(cfg["belt.speed_cmps"]),
                "direction_base": [float(x) for x in cfg["belt.direction_base"]],
                "invalid_after_s": float(arg("invalid_after_s")),
                "lost_after_s": float(arg("lost_after_s")),
            }
        ],
    )
    # Jazzy: launch_arguments 는 (이름, 값) 쌍 목록 → dict 면 .items() (dict 그대로면 키만 남아 깨진다)
    gateway = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(robot_share, "launch", "robot_gateway.launch.py")
        ),
        launch_arguments={
            "dry_run": "true",  # 항상 고정
            "dry_run_object_mm": arg("object_mm"),
            "config": config,
        }.items(),
    )
    servo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(servo_share, "launch", "belt_servo.launch.py")),
        launch_arguments={
            "params": os.path.join(servo_share, "config", "belt_servo_sim.yaml"),
            "config": config,
            "overrides": overrides,
            "log_dir": log_dir,
        }.items(),
    )
    note = (
        f"sim.launch: scenario={arg('scenario')} object_mm={arg('object_mm')} "
        f"kp={arg('kp') or '(sim yaml)'} log_dir={log_dir or '(sim yaml)'} — gateway dry_run 고정"
    )
    return [LogInfo(msg=note), fake, gateway, servo]


def generate_launch_description() -> LaunchDescription:
    args = [
        ("config", "", "레포 config/voss_config.yaml 절대 경로 (필수)"),
        ("scenario", "normal", "normal | invalid_after_s | lost_after_s | two_boxes"),
        ("object_mm", "40.5", "가짜 RG2 물체 폭 (0 = 빈손)"),
        ("kp", "", "control.kp_per_s 덮어쓰기 (비우면 sim yaml 값)"),
        ("log_dir", "", "belt_servo 로그 폴더 (비우면 sim yaml 의 /tmp/voss_sim/servo)"),
        ("invalid_after_s", "8.0", "fake_box: 이 시각부터 position_valid=false"),
        ("lost_after_s", "8.0", "fake_box: 이 시각부터 발행 안 함"),
    ]
    decls = [DeclareLaunchArgument(n, default_value=d, description=t) for n, d, t in args]
    return LaunchDescription([*decls, OpaqueFunction(function=_setup)])
