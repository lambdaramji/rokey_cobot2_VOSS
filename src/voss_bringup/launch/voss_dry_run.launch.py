"""로봇 없이 소프트웨어 전체 루프 (T22 #31, 개발·리허설용). 아무 장비도 움직이지 않는다 — 실행은 사람이 한다.

녹화(box_tracker playback, restamp) → label_reader(stage 1) → sort_manager → TrackAndGrasp → robot_gateway dry_run
(가짜 로봇·가짜 RG2) → MoveToZone(가짜) 까지 한 번에 띄운다. sort_logger 대신 g0_mock --log(LOG 준비만), 음성·HMI·카메라 없음.
TrackAndGrasp 는 기본 g0_mock --servo(servo:=mock). 고정 카메라 녹화로는 진짜 추종을 흉내 낼 수 없어 진짜 belt_servo 는
박스가 화면을 벗어나 LOST 로 끝난다(10/11). servo:=sim 이면 진짜 belt_servo(sim 파라미터)로 PREPARE·TRACK 까지 본다.
**ROS_DOMAIN_ID 30(공용 PC 운용 도메인)에서는 기동을 거부한다** — 가짜 pose·응답이 진짜 로봇 옆에 섞이지 않게(box_tracker
playback·g0_mock 도 각자 거부한다). 공용 PC 에서도 다른 도메인(예 77)에서만.

  export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  ros2 launch voss_bringup voss_dry_run.launch.py playback:=$HOME/voss_data/1006_raw/voss_data/1006/t17/A_MIX_01
  # 다른 터미널(같은 도메인): ros2 service call /voss/sort/command voss_msgs/srv/Command "{command: start}"
녹화 박스 좌표는 녹화 때 관측 자세 기준(box_tracker 재생은 실시간 pose 를 받지 않는다)이라, 가짜 로봇이 움직여도 섞이지 않는다.
"""

from __future__ import annotations

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare

REPO = os.environ.get("VOSS_REPO", os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS"))
ARGS = [
    ("playback", "", "box_tracker 녹화 bag 폴더 (필수)"),
    ("config_dir", os.environ.get("VOSS_CONFIG_DIR", os.path.join(REPO, "config")), "레포 config/"),
    ("repo", REPO, "레포 루트 (tools/mock/g0_mock.py)"),
    (
        "servo",
        "mock",
        "mock = g0_mock --servo(가짜 TrackAndGrasp OK → PLACE 까지) | sim = 진짜 belt_servo(sim 파라미터)",
    ),
    ("object_mm", "40.5", "가짜 RG2 물체 폭 (0 = 빈손 → 파지 실패 경로)"),
    (
        "ocr_python",
        os.environ.get("VOSS_OCR_PYTHON", os.path.expanduser("~/.venvs/voss_ocr/bin/python")),
        "label_reader PaddleOCR venv python",
    ),  # fmt: skip
    (
        "with_vision",
        "true",
        "false 면 비전은 컨테이너(docker/vision, BOX_TRACKER_ARGS=playback:=…)로 따로",
    ),
    ("mock_log", "true", "g0_mock --log 로 /voss/log/status OK (sort_logger·DB 없이 LOG 준비)"),
    (
        "servo_log_dir",
        "/tmp/voss_dry_run/servo",
        "belt_servo 로그 (게이트 증거 폴더 data/servo 를 섞지 않게)",
    ),
]


def refuse_operating_domain(env: dict) -> None:
    """도메인 30 에서는 띄우지 않는다 (ROS 없음, pytest 대상)."""
    if env.get("ROS_DOMAIN_ID", "0").strip() == "30":
        raise RuntimeError(
            "voss_dry_run 거부: ROS_DOMAIN_ID 30(운용 도메인) — 가짜 로봇·녹화 박스가 진짜 로봇과 섞인다. "
            "export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 뒤 다시"
        )


def servo_mode(a: dict[str, str]) -> str:
    """mock | sim. 고정 카메라 녹화에서는 진짜 belt_servo 가 박스를 화면에 붙잡지 못해 LOST 로 끝난다(10/11)
    → 기본 mock 으로 sort_manager 의 PLACE·적재까지 본다. sim 은 서보 기동·PREPARE·TRACK 확인용."""
    m = a["servo"].strip().lower()
    if m not in ("mock", "sim"):
        raise RuntimeError(f"voss_dry_run: servo:=mock | sim (받은 값 {a['servo']!r})")
    return m


def mock_args(a: dict[str, str]) -> list[str]:
    """g0_mock 인자 (pytest 대상). 비면 g0_mock 을 띄우지 않는다."""
    out = []
    if a["mock_log"].strip().lower() == "true":
        out.append("--log")
    if servo_mode(a) == "mock":
        out.append("--servo")
    return out


def dry_run_host_args(a: dict[str, str], servo_sim_yaml: str) -> dict[str, str]:
    """voss_host.launch.py 에 넘길 인자 (pytest 대상). 장비 쪽은 모두 끈다."""
    if not a["playback"]:
        raise RuntimeError("voss_dry_run: playback:=<bag 폴더> 가 필요하다")
    return {
        "with_servo": "true" if servo_mode(a) == "sim" else "false",
        "config_dir": a["config_dir"],
        "dry_run": "true",
        "dry_run_object_mm": a["object_mm"],
        "servo_params": servo_sim_yaml,
        "servo_log_dir": a["servo_log_dir"],
        "with_camera": "false",
        "with_logger": "false",
        "with_voice": "false",
        "with_hmi": "false",
        "with_vision": a["with_vision"],
        "vision_playback": os.path.expanduser(a["playback"]),
        "vision_playback_restamp": "true",  # 녹화 시각(예 10/06)이면 sort_manager 가 "관측 시작 전 촬영"으로 버린다
        "ocr_python": a["ocr_python"],
        "ocr_device": "cpu",
    }


def _setup(context):
    refuse_operating_domain(dict(os.environ))
    a = {n: context.launch_configurations[n] for n, _, _ in ARGS}
    sim_yaml = os.path.join(
        FindPackageShare("voss_servo").perform(context), "config", "belt_servo_sim.yaml"
    )
    host = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare("voss_bringup"), "/launch/voss_host.launch.py"]
        ),
        launch_arguments=list(dry_run_host_args(a, sim_yaml).items()),
    )
    acts = [host]
    margs = mock_args(a)
    if margs:
        mock = os.path.join(os.path.expanduser(a["repo"]), "tools", "mock", "g0_mock.py")
        acts.append(ExecuteProcess(cmd=["python3", mock, *margs], output="screen", name="g0_mock"))
    return acts


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=t) for n, d, t in ARGS]
        + [OpaqueFunction(function=_setup)]
    )
