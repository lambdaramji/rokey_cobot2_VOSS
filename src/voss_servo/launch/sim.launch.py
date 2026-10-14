"""개인 PC 시뮬 (sim 전용): fake_box + robot_gateway dry_run + belt_servo (design/U3-dd.md 5절).

보통은 sim_check 가 이 launch 를 case 마다 띄우고 끈다 (U3-run.md B). 직접 띄울 때:
  cd ~/cobot2/cobot2_voss
  voss-ros ros2 launch voss_servo sim.launch.py config:=$PWD/config/voss_config.yaml \
    scenario:=normal log_dir:=/tmp/voss_sim/manual
인자: config(필수, 레포 voss_config.yaml) · scenario(normal|invalid_after_s|lost_after_s|two_boxes)
      · object_mm(gateway dry_run_object_mm, 0 = 빈손) · kp(control.kp_per_s 덮어쓰기)
      · log_dir · invalid_after_s · lost_after_s
      · (U9b) gripper(gateway|fake) · grip_plan · grip_close_s · max_attempts(retry.max_attempts 덮어쓰기)
        · box_start_x_mm (fake_box 시작 x) — 기본값이면 지금과 똑같이 동작
      · (S2-T14) z_profile(p|trapezoid, z.profile 덮어쓰기 — 비우면 sim yaml 의 p)
      · (S2-T18) rotate(""|true — rotate.enable + input.pose_lag_ms 0 덮어쓰기), box_yaw_deg(벨트 기준 박스 각)
- gripper:=fake 면 fake_gripper 를 띄우고 belt_servo 의 /voss/robot/gripper 를 /voss/sim/gripper 로 remap
  (gateway 의 그리퍼 서비스는 떠 있지만 belt_servo 가 부르지 않는다, design/U9b-dd.md 6.2).
- gateway 는 **항상 dry_run:=true** (인자로 받지 않는다 — 시뮬에서 실기로 새지 않게).
- fake_box 의 벨트 속도·방향은 voss_config 에서 읽어 넘긴다 (숫자를 복사하지 않는다).
"""

import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetRemap
from voss_servo.fake_box import DEFAULT_START_M
from voss_servo.fake_gripper import SERVICE as FAKE_GRIPPER_SRV
from voss_servo.fake_gripper import parse_plan
from voss_servo.launch_params import config_values, expand, file_sha, load_yaml

GRIPPER_SRV = "/voss/robot/gripper"  # belt_servo 가 부르는 이름 (topics.md)


def _write_overrides(
    folder: str, kp: str, max_attempts: str = "", z_profile: str = "", rotate: str = ""
) -> str:
    """kp·max_attempts·z_profile·rotate 중 값이 있는 것만 덮어쓰는 작은 YAML 을 만들고 경로를 돌려준다."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "sim_overrides.yaml")
    params: dict = {}
    if kp:
        params["control"] = {"kp_per_s": float(kp)}  # P 게인
    if max_attempts:
        params["retry"] = {"max_attempts": int(max_attempts)}  # 재시도 상한 (U9b)
    if z_profile:
        params["z"] = {"profile": z_profile}  # z 속도 프로파일 p | trapezoid (S2-T14)
    if rotate == "true":
        params["rotate"] = {"enable": True}  # J6 회전 파지 켜기 (S2-T18)
        # rotate 는 joint_states 짝(pose_lag 0)이 전제(교차 검사) — 이 케이스만 sim yaml 의 60 과 다르다
        params["input"] = {"pose_lag_ms": 0.0}
    body = {"belt_servo": {"ros__parameters": params}}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(body, f)
    return path


def _wants_overrides(kp: str, max_attempts: str, z_profile: str, rotate: str = "") -> bool:
    """덮어쓸 값이 하나라도 있나. 새 인자를 _write_overrides 에 넣으면 여기에도 넣는다 (S2-T14 재검 m5)."""
    return bool(kp or max_attempts or z_profile or rotate == "true")


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
    want = (arg("kp"), arg("max_attempts"), arg("z_profile"), arg("rotate"))
    if _wants_overrides(*want):  # 덮어쓰기 파일
        folder = expand(log_dir) if log_dir else tempfile.mkdtemp(prefix="voss_sim_")
        overrides = _write_overrides(folder, *want)
    gripper = arg("gripper")
    if gripper not in ("gateway", "fake"):
        raise RuntimeError(f"sim.launch gripper:={gripper} — gateway 또는 fake")
    start = [float(arg("box_start_x_mm")) / 1000.0, *DEFAULT_START_M[1:]]  # 시작 x 만 바꾼다
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
                "start_xyz_m": start,
                "yaw_deg": float(arg("box_yaw_deg")),  # 벨트 기준 박스 각 (S2-T18, 기본 0)
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
    actions = [fake, gateway]
    if gripper == "fake":
        # 모르는 계획이면 여기서 ValueError — belt_servo 를 띄우기 전에 launch 가 멈춘다
        parse_plan(arg("grip_plan"))
        actions.append(
            Node(
                package="voss_servo",
                executable="fake_gripper",
                name="fake_gripper",
                output="screen",
                parameters=[{"plan": arg("grip_plan"), "close_s": float(arg("grip_close_s"))}],
            )
        )
        # 이 그룹 안에서 뜨는 노드(belt_servo)만 그리퍼 서비스를 가짜로 잇는다
        servo = GroupAction([SetRemap(src=GRIPPER_SRV, dst=FAKE_GRIPPER_SRV), servo])
    note = (
        f"sim.launch: scenario={arg('scenario')} object_mm={arg('object_mm')} "
        f"kp={arg('kp') or '(sim yaml)'} max_attempts={arg('max_attempts') or '(sim yaml)'} "
        f"z_profile={arg('z_profile') or '(sim yaml)'} "
        f"rotate={arg('rotate') or '(sim yaml off)'} box_yaw={arg('box_yaw_deg')} "
        f"gripper={gripper} plan={arg('grip_plan')} close={arg('grip_close_s')} "
        f"start_x={arg('box_start_x_mm')} log_dir={log_dir or '(sim yaml)'} — gateway dry_run 고정"
    )
    return [LogInfo(msg=note), *actions, servo]


def generate_launch_description() -> LaunchDescription:
    args = [
        ("config", "", "레포 config/voss_config.yaml 절대 경로 (필수)"),
        ("scenario", "normal", "normal | invalid_after_s | lost_after_s | two_boxes"),
        ("object_mm", "40.5", "가짜 RG2 물체 폭 (0 = 빈손)"),
        ("kp", "", "control.kp_per_s 덮어쓰기 (비우면 sim yaml 값)"),
        ("log_dir", "", "belt_servo 로그 폴더 (비우면 sim yaml 의 /tmp/voss_sim/servo)"),
        ("invalid_after_s", "8.0", "fake_box: 이 시각부터 position_valid=false"),
        ("lost_after_s", "8.0", "fake_box: 이 시각부터 발행 안 함"),
        ("gripper", "gateway", "gateway(dry_run 가짜 RG2) | fake(fake_gripper 계획표, U9b)"),
        ("grip_plan", "held", "fake 계획: 닫기마다 empty|held|wide (쉼표 구분)"),
        ("grip_close_s", "1.7", "fake 닫힘 지연 s"),
        ("max_attempts", "", "retry.max_attempts 덮어쓰기 (비우면 sim yaml)"),
        ("box_start_x_mm", str(DEFAULT_START_M[0] * 1000.0), "fake_box 시작 x mm"),
        ("z_profile", "", "z.profile 덮어쓰기 p | trapezoid (비우면 sim yaml, S2-T14)"),
        ("rotate", "", "true = rotate.enable + pose_lag 0 덮어쓰기 (비우면 sim yaml off, S2-T18)"),
        ("box_yaw_deg", "0", "fake_box 박스 각 — 벨트 방향 기준 deg (S2-T18)"),
    ]
    decls = [DeclareLaunchArgument(n, default_value=d, description=t) for n, d, t in args]
    return LaunchDescription([*decls, OpaqueFunction(function=_setup)])
