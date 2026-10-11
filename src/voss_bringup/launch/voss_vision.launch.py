"""비전 두 노드(box_tracker·label_reader)를 한 번에 (T22 #31). 실행은 사람이 한다. 로봇을 움직이지 않는다.

기본 운용은 컨테이너(docker/vision, 노드마다 서비스)다. 이 launch 는 컨테이너를 못 쓸 때 호스트에서 띄우는 대체 경로이자
voss_dry_run·voss_host(with_vision:=true)가 부르는 묶음이다.

  ros2 launch voss_bringup voss_vision.launch.py python:=$HOME/.venvs/voss_ocr/bin/python
  ros2 launch voss_bringup voss_vision.launch.py playback:=<bag> python:=...   # 녹화 재생(도메인 30 이면 box_tracker 가 거부)
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.substitutions import FindPackageShare

DEFAULT_CONFIG_DIR = os.environ.get(
    "VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/config")
)
ARGS = [
    ("config_dir", DEFAULT_CONFIG_DIR, "belt_homography·hand_eye·voss_config.yaml 폴더"),
    ("detector", "seg", "box_tracker 검출 방식 (ADR-0011, 게이트·통합 중 바꾸지 않는다)"),
    ("playback", "", "box_tracker 녹화 재생 bag 폴더 (비우면 카메라 실시간)"),
    ("playback_rate", "1.0", "재생 배속"),
    (
        "playback_restamp",
        "false",
        "재생 시각을 지금 시계로 (sort_manager·belt_servo 를 재생으로 돌릴 때)",
    ),
    ("ocr_device", "cpu", "label_reader cpu | gpu:0"),
    ("python", os.environ.get("VOSS_OCR_PYTHON", ""), "label_reader 를 띄울 PaddleOCR venv python"),
    ("with_box_tracker", "true", "box_tracker 띄우기"),
    ("with_label_reader", "true", "label_reader 띄우기"),
]
BOX_TRACKER_ARGS = ("detector", "playback", "playback_rate", "playback_restamp", "config_dir")
LABEL_READER_ARGS = ("config_dir", "ocr_device", "python")


def _include(launch_file: str, keys: tuple[str, ...], when: str) -> IncludeLaunchDescription:
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource([FindPackageShare("voss_vision"), "/launch/", launch_file]),
        launch_arguments=[(k, LaunchConfiguration(k)) for k in keys],
        condition=IfCondition(LaunchConfiguration(when)),
    )


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=t) for n, d, t in ARGS]
        + [
            _include("box_tracker.launch.py", BOX_TRACKER_ARGS, "with_box_tracker"),
            _include("label_reader.launch.py", LABEL_READER_ARGS, "with_label_reader"),
        ]
    )
