"""label_reader 기동 (호스트 G0 또는 비전 컨테이너). 실행은 사람이 한다. 로봇을 움직이지 않는다.

  ros2 launch voss_vision label_reader.launch.py python:=$HOME/.venvs/voss_ocr/bin/python   # 호스트 venv
  ros2 launch voss_vision label_reader.launch.py ocr_device:=gpu:0                         # GPU (T22)

python: PaddleOCR 가 시스템 python 에 없으면 그 venv 의 python 으로 노드를 띄운다(기본: 환경 변수 VOSS_OCR_PYTHON,
없으면 시스템 python). venv 는 --system-site-packages 로 만들어 rclpy 를 같이 쓴다.
voss_config.yaml 은 config_dir(기본: VOSS_CONFIG_DIR, 없으면 레포 config/)에서 읽는다.
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
            DeclareLaunchArgument("ocr_device", default_value="cpu"),
            DeclareLaunchArgument("python", default_value=os.environ.get("VOSS_OCR_PYTHON", "")),
            Node(
                package="voss_vision",
                executable="label_reader",
                name="label_reader",
                output="screen",
                prefix=LaunchConfiguration("python"),
                parameters=[
                    PathJoinSubstitution(
                        [FindPackageShare("voss_vision"), "config", "label_reader.yaml"]
                    ),
                    {
                        "config_path": PathJoinSubstitution(
                            [LaunchConfiguration("config_dir"), "voss_config.yaml"]
                        ),
                        "ocr_device": LaunchConfiguration("ocr_device"),
                    },
                ],
            ),
        ]
    )
