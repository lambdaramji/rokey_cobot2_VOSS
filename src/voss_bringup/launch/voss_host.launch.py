"""호스트 전체 기동 (T22 #31) — g0-runbook 2절 T2~T8 의 호스트 노드 + 음성 3노드 + hmi_bridge 를 launch 하나로.
실행은 사람이 한다. dry_run:=false 는 로봇이 움직인다 — 비상정지 옆에서(CLAUDE.md 규칙 6).

  ros2 launch voss_bringup voss_host.launch.py                   # dry_run(가짜 로봇·가짜 RG2) — 기본. 도메인 30 이면 거부
  ros2 launch voss_bringup voss_host.launch.py dry_run:=false    # 실기: T1·T2(학민)를 먼저 따로, 비전은 docker/vision

넣지 않는 것: T1 두산 브링업(외부 패키지·컨트롤러 IP — 공개 레포에 적지 않는다), 비전(기본은 컨테이너 docker/vision,
호스트에서 띄우려면 with_vision:=true). camera·logger·voice·hmi 는 auto = 실기(dry_run:=false)일 때만 켠다.
config_dir(기본 VOSS_CONFIG_DIR, 없으면 ~/voss_ws/config)의 voss_config.yaml·belt_servo_real.yaml 을 쓴다.
실값 파일이 없는 개인 PC 의 dry_run 은 servo_params:=<voss_servo share>/config/belt_servo_sim.yaml 또는 with_servo:=false.

dry_run 은 운용 도메인(ROS_DOMAIN_ID 30)에서 거부한다 — 가짜 gateway(가짜 /voss/robot/pose·READY·늘 성공하는
move_to_zone)와 belt_servo·sort_manager 가 진짜 노드 옆에 하나 더 뜬다. 시험은 다른 도메인(예 77)에서.
robot_gateway(T2)는 with_gateway:=auto = dry_run 일 때만 이 launch 에 넣는다. 실기는 학민이 런북 T1·T2 를 따로 띄워
No-Go 줄(pose_source joint_states 확인·컨트롤러 TCP 등록 #121·이동 높이 계산)을 본 뒤 이 launch 를 띄운다 — FAULT 때
gateway 만 다시 띄우고(런북 6절), Ctrl+C 로 이 launch 를 내려도 gateway 는 남아 watchdog 이 정지시킨다(7절 순서).
실기 Ctrl+C 전에: /voss/sort/command stop → PAUSED·로봇 OBSERVE 정지 확인 → 벨트 12 V 끄기(런북 7절).
sort_logger 는 VOSS_DB_LOGGER_PASSWORD 를 셸 환경에서 받는다(런북 T4). 기동 순서는 런북과 같게 actions 를 놓지만
운전 시작은 sort_manager 의 준비 판단(ROBOT·SERVO·VISION·OCR·LOG 모두 READY)이 막는다 — start 는 사람이 따로 보낸다.
"""

import os
from typing import NamedTuple

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

DEFAULT_CONFIG_DIR = os.environ.get("VOSS_CONFIG_DIR", os.path.expanduser("~/voss_ws/config"))
DEFAULT_SERVO_LOG = os.path.expanduser("~/voss_ws/src/rokey_cobot2_VOSS/data/servo")

# 런북 T3 의 10/08 확인 명령(학민) 그대로: 1920×1080×30, 노출 60(6 ms)·자동 꺼짐, WB 4600 고정, 깊이 끔(규칙 4)
CAMERA_PARAMS = {
    "enable_color": True,
    "enable_depth": False,
    "enable_infra1": False,
    "enable_infra2": False,
    "enable_accel": False,
    "enable_gyro": False,
    "rgb_camera.color_profile": "1920x1080x30",
    "rgb_camera.enable_auto_exposure": False,
    "rgb_camera.exposure": 60,
    "rgb_camera.enable_auto_white_balance": False,
    "rgb_camera.white_balance": 4600.0,
    "initial_reset": True,
}

ARGS = [
    ("config_dir", DEFAULT_CONFIG_DIR, "voss_config.yaml·belt_servo_real.yaml 이 있는 폴더"),
    ("dry_run", "true", "true = 가짜 로봇·RG2 (기본). false = 실기"),
    (
        "with_gateway",
        "auto",
        "auto | true | false — robot_gateway(T2). auto 는 dry_run 일 때만(실기는 런북 T2 를 따로)",
    ),
    ("pose_source", "joint_states", "gateway pose 소스 (런북 T2, #140)"),
    ("dry_run_object_mm", "", "dry_run 가짜 RG2 물체 폭 (비우면 gateway 기본)"),
    (
        "with_servo",
        "true",
        "belt_servo 띄우기 (voss_dry_run servo:=mock 이면 false — g0_mock 이 대역)",
    ),
    ("servo_params", "", "belt_servo 파라미터 YAML (비우면 config_dir/belt_servo_real.yaml)"),
    ("servo_overrides", "", "belt_servo 덮어쓸 YAML (예: belt_servo_kp0.yaml)"),
    ("servo_log_dir", DEFAULT_SERVO_LOG, "belt_servo 틱·시도 로그 폴더 (런북 T7)"),
    ("home_first", "true", "sort_manager start 때 OBSERVE 로 먼저 간다"),
    ("with_camera", "auto", "auto | true | false — auto 는 실기일 때만"),
    ("with_logger", "auto", "sort_logger (런북 T4, sort_manager 보다 먼저)"),
    ("with_voice", "auto", "voice_listener·intent_parser·speech_out"),
    ("voice_mode", "mic", "mic | text — text 는 stdin 이 필요해 voice_listener 를 따로 띄운다"),
    ("with_hmi", "auto", "hmi_bridge (Mosquitto 1883)"),
    ("with_vision", "false", "비전을 호스트에서 (기본은 컨테이너 docker/vision)"),
    ("vision_playback", "", "with_vision 때 box_tracker 녹화 재생 (도메인 30 이면 노드가 거부)"),
    (
        "vision_playback_restamp",
        "false",
        "재생 시각을 지금 시계로 (재생으로 sort_manager 를 돌릴 때)",
    ),
    ("ocr_python", os.environ.get("VOSS_OCR_PYTHON", ""), "with_vision 때 PaddleOCR venv python"),
    ("ocr_device", "cpu", "with_vision 때 cpu | gpu:0"),
]


class Step(NamedTuple):
    """launch 동작 하나. include = 다른 패키지 launch 파일, node = 노드 하나.
    (dataclass 는 쓰지 않는다 — ros2 launch 는 launch 파일을 sys.modules 에 올리지 않고 불러와 dataclass 가 깨진다)"""

    kind: str  # include | node
    pkg: str
    target: str  # launch 파일 이름 또는 실행 파일 이름
    args: dict | None = None  # include 인자 또는 노드 파라미터
    name: str = ""


def on(value: str, dry_run: bool) -> bool:
    """auto | true | false → 켤지. auto 는 실기일 때만."""
    v = value.strip().lower()
    if v == "auto":
        return not dry_run
    if v in ("true", "false"):
        return v == "true"
    raise ValueError(f"auto | true | false 만 받는다: {value!r}")


def gateway_on(value: str, dry_run: bool) -> bool:
    """robot_gateway 를 이 launch 에 넣을지. auto 는 dry_run 일 때만 — 실기는 런북 T2 로 따로 띄운다."""
    return on(value, not dry_run)


def refuse_dry_run_on_operating_domain(dry_run: bool, env: dict) -> None:
    """dry_run 은 도메인 30 에서 띄우지 않는다 (ROS 없음, pytest 대상). voss_dry_run 의 refuse_operating_domain 과 같은 규칙."""
    if dry_run and env.get("ROS_DOMAIN_ID", "0").strip() == "30":
        raise RuntimeError(
            "voss_host 거부: dry_run(가짜 로봇)을 ROS_DOMAIN_ID 30(운용 도메인)에서 — 가짜 pose·move_to_zone 과 "
            "belt_servo·sort_manager 가 진짜 노드와 섞인다. 실기는 dry_run:=false, "
            "시험은 export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 뒤 다시"
        )


def host_plan(a: dict[str, str]) -> list[Step]:
    """인자 → 런북 순서의 동작 목록 (ROS 없음, pytest 대상)."""
    dry = a["dry_run"].strip().lower() != "false"
    cfg = os.path.expanduser(a["config_dir"])
    steps = []
    gw = {"dry_run": "true" if dry else "false", "pose_source": a["pose_source"],
          "config": os.path.join(cfg, "voss_config.yaml")}  # fmt: skip
    if a["dry_run_object_mm"]:
        gw["dry_run_object_mm"] = a["dry_run_object_mm"]
    if gateway_on(a["with_gateway"], dry):  # T2
        steps.append(Step("include", "voss_robot", "robot_gateway.launch.py", gw))
    if on(a["with_camera"], dry):  # T3
        steps.append(
            Step(
                "node", "realsense2_camera", "realsense2_camera_node", dict(CAMERA_PARAMS), "camera"
            )
        )
    if on(a["with_logger"], dry):  # T4 — sort_manager 보다 먼저
        steps.append(Step("node", "voss_hmi", "sort_logger", name="sort_logger"))
    if a["with_vision"].strip().lower() == "true":  # T5·T6 (기본은 컨테이너)
        vis = {"config_dir": cfg, "playback": a["vision_playback"],
            "playback_restamp": a["vision_playback_restamp"], "ocr_device": a["ocr_device"],
               "python": a["ocr_python"]}  # fmt: skip
        steps.append(Step("include", "voss_bringup", "voss_vision.launch.py", vis))
    servo = {"params": a["servo_params"] or os.path.join(cfg, "belt_servo_real.yaml"),
             "config": os.path.join(cfg, "voss_config.yaml"), "overrides": a["servo_overrides"],
             "log_dir": a["servo_log_dir"]}  # fmt: skip
    if a["with_servo"].strip().lower() != "false":
        steps.append(Step("include", "voss_servo", "belt_servo.launch.py", servo))  # T7
    mgr = {"config_dir": cfg, "home_first": a["home_first"]}
    steps.append(Step("include", "voss_manager", "sort_manager.launch.py", mgr))  # T8
    if on(a["with_voice"], dry):
        steps.append(Step("node", "voss_voice", "speech_out", name="speech_out"))
        steps.append(Step("node", "voss_voice", "intent_parser", name="intent_parser"))
        if a["voice_mode"] == "mic":
            steps.append(
                Step("node", "voss_voice", "voice_listener", {"mode": "mic"}, "voice_listener")
            )
    if on(a["with_hmi"], dry):
        steps.append(Step("node", "voss_hmi", "hmi_bridge", name="hmi_bridge"))
    return steps


def to_action(s: Step):
    if s.kind == "include":
        src = PythonLaunchDescriptionSource([FindPackageShare(s.pkg), "/launch/", s.target])
        return IncludeLaunchDescription(src, launch_arguments=list((s.args or {}).items()))
    return Node(package=s.pkg, executable=s.target, name=s.name or None, output="screen",
                parameters=[s.args] if s.args else [])  # fmt: skip


def _setup(context):
    a = {n: context.launch_configurations[n] for n, _, _ in ARGS}
    dry = a["dry_run"].strip().lower() != "false"
    refuse_dry_run_on_operating_domain(dry, dict(os.environ))
    steps = host_plan(a)
    names = ", ".join(s.name or s.target.replace(".launch.py", "") for s in steps)
    notes = [LogInfo(msg=f"voss_host: {'dry_run(가짜 로봇)' if dry else '실기'} — {names}")]
    if not dry:
        notes.append(
            LogInfo(
                msg="voss_host: 실기 — 로봇이 움직일 수 있다. 비상정지 옆에서, T1 두산 브링업이 먼저 떠 있어야 한다"
            )
        )
    if not dry and not gateway_on(a["with_gateway"], dry):
        notes.append(
            LogInfo(
                msg="voss_host: robot_gateway 는 넣지 않았다 — 런북 T2 로 따로 띄워 No-Go 줄을 확인한 뒤여야 한다. "
                "끄기 전 /voss/sort/command stop → PAUSED·OBSERVE 정지 확인 → 벨트 끄기"
            )
        )
    if on(a["with_logger"], dry) and not os.environ.get("VOSS_DB_LOGGER_PASSWORD"):
        notes.append(
            LogInfo(
                msg="voss_host: VOSS_DB_LOGGER_PASSWORD 가 셸에 없다 — sort_logger DB 연결이 실패한다(런북 T4)"
            )
        )
    if on(a["with_voice"], dry) and a["voice_mode"] != "mic":
        notes.append(LogInfo(msg="voss_host: voice_mode text — voice_listener 는 따로: "
                                 "ros2 run voss_voice voice_listener --ros-args -p mode:=text"))  # fmt: skip
    return notes + [to_action(s) for s in steps]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=t) for n, d, t in ARGS]
        + [OpaqueFunction(function=_setup)]
    )
