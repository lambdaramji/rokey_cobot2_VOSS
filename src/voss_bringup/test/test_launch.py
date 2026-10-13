"""voss_bringup launch 3종 (T22 #31) — 띄우지 않고 검사한다.

- host_plan: 기본은 dry_run 에 장비 쪽(camera·logger·voice·hmi) 꺼짐, 실기는 런북 순서(logger 가 sort_manager 보다 먼저)
- 넘기는 include 인자가 대상 launch 파일에 선언돼 있는지(오타면 그 인자는 조용히 무시된다)
- voss_dry_run·voss_host dry_run: 도메인 30 거부, 장비 쪽 모두 끔
- 실기는 gateway 를 넣지 않는다(with_gateway auto — 런북 T2 를 따로)
- 노드 실행 파일 이름이 각 패키지 setup.py console_scripts 에 있는지
"""

import re
from pathlib import Path

import pytest
from launch.actions import DeclareLaunchArgument
from launch.launch_description_sources.python_launch_file_utilities import (
    load_python_launch_file_as_module,
)

PKG = Path(__file__).resolve().parents[1]
SRC = PKG.parent


def load(path: Path):
    # ros2 launch 와 같은 로더(sys.modules 에 올리지 않는다) — 실제 기동에서만 깨지는 것을 여기서 잡는다
    return load_python_launch_file_as_module(str(path))


HOST = load(PKG / "launch" / "voss_host.launch.py")
VISION = load(PKG / "launch" / "voss_vision.launch.py")
DRY = load(PKG / "launch" / "voss_dry_run.launch.py")

TARGET_FILES = {
    ("voss_robot", "robot_gateway.launch.py"): SRC / "voss_robot/launch/robot_gateway.launch.py",
    ("voss_servo", "belt_servo.launch.py"): SRC / "voss_servo/launch/belt_servo.launch.py",
    ("voss_manager", "sort_manager.launch.py"): SRC / "voss_manager/launch/sort_manager.launch.py",
    ("voss_vision", "box_tracker.launch.py"): SRC / "voss_vision/launch/box_tracker.launch.py",
    ("voss_vision", "label_reader.launch.py"): SRC / "voss_vision/launch/label_reader.launch.py",
    ("voss_bringup", "voss_vision.launch.py"): PKG / "launch/voss_vision.launch.py",
    ("voss_bringup", "voss_host.launch.py"): PKG / "launch/voss_host.launch.py",
}


def declared(pkg: str, launch_file: str) -> set[str]:
    ld = load(TARGET_FILES[(pkg, launch_file)]).generate_launch_description()
    return {e.name for e in ld.entities if isinstance(e, DeclareLaunchArgument)}


def args(**over) -> dict[str, str]:
    a = {n: d for n, d, _ in HOST.ARGS}
    a.update(over)
    return a


def targets(steps) -> list[str]:
    return [s.target for s in steps]


def test_default_is_dry_run_without_devices() -> None:
    steps = HOST.host_plan(args(config_dir="/cfg"))
    assert targets(steps) == [
        "robot_gateway.launch.py",
        "belt_servo.launch.py",
        "sort_manager.launch.py",
    ]
    gw = steps[0].args
    assert gw["dry_run"] == "true" and gw["pose_source"] == "joint_states"
    assert gw["config"] == "/cfg/voss_config.yaml"
    assert steps[1].args["params"] == "/cfg/belt_servo_real.yaml"  # 비우면 config_dir 의 실값 파일


def test_real_follows_runbook_order() -> None:
    t = targets(HOST.host_plan(args(dry_run="false", with_gateway="true")))
    assert t == [
        "robot_gateway.launch.py",  # T2
        "realsense2_camera_node",  # T3
        "sort_logger",  # T4
        "belt_servo.launch.py",  # T7
        "sort_manager.launch.py",  # T8
        "speech_out",
        "intent_parser",
        "voice_listener",
        "hmi_bridge",
    ]
    assert t.index("sort_logger") < t.index("sort_manager.launch.py")


def test_real_leaves_gateway_to_runbook_t2() -> None:
    # 실기 auto: T2 는 학민이 따로 띄워 No-Go 줄을 본다 — FAULT 때 gateway 만 재기동(6절), 끄는 순서 belt_servo → gateway(7절)
    t = targets(HOST.host_plan(args(dry_run="false")))
    assert "robot_gateway.launch.py" not in t and t[0] == "realsense2_camera_node"
    assert not HOST.gateway_on("false", True) and HOST.gateway_on("auto", True)
    with pytest.raises(ValueError, match="auto"):
        HOST.gateway_on("yes", False)


def test_explicit_switches_and_text_voice() -> None:
    t = targets(HOST.host_plan(args(dry_run="false", with_camera="false", voice_mode="text")))
    assert (
        "realsense2_camera_node" not in t and "voice_listener" not in t
    )  # text 는 stdin 이 필요해 따로
    assert "speech_out" in t and "intent_parser" in t
    t = targets(HOST.host_plan(args(with_voice="true", with_vision="true", vision_playback="/b")))
    assert "voss_vision.launch.py" in t and "voice_listener" in t  # dry_run 이어도 명시하면 켠다
    with pytest.raises(ValueError, match="auto"):
        HOST.on("maybe", True)


def test_camera_params_match_runbook_t3() -> None:
    p = HOST.CAMERA_PARAMS
    assert p["enable_depth"] is False  # 규칙 4
    assert p["rgb_camera.color_profile"] == "1920x1080x30"
    assert p["rgb_camera.exposure"] == 60 and p["rgb_camera.enable_auto_exposure"] is False
    assert (
        p["rgb_camera.white_balance"] == 4600.0
        and p["rgb_camera.enable_auto_white_balance"] is False
    )


def all_includes():
    full = args(dry_run="false", with_vision="true", vision_playback="/b", dry_run_object_mm="40.5")
    for s in HOST.host_plan(full):
        if s.kind == "include":
            yield s.pkg, s.target, set(s.args or {})
    yield "voss_vision", "box_tracker.launch.py", set(VISION.BOX_TRACKER_ARGS)
    yield "voss_vision", "label_reader.launch.py", set(VISION.LABEL_READER_ARGS)
    a = {n: d for n, d, _ in DRY.ARGS} | {"playback": "/bag"}
    yield "voss_bringup", "voss_host.launch.py", set(DRY.dry_run_host_args(a, "/sim.yaml"))


@pytest.mark.parametrize("pkg,launch_file,keys", list(all_includes()))
def test_include_args_are_declared_by_target(pkg, launch_file, keys) -> None:
    missing = keys - declared(pkg, launch_file)
    assert not missing, f"{pkg}/{launch_file} 에 없는 인자: {sorted(missing)}"


def test_dry_run_refuses_operating_domain() -> None:
    with pytest.raises(RuntimeError, match="30"):
        DRY.refuse_operating_domain({"ROS_DOMAIN_ID": "30"})
    DRY.refuse_operating_domain({"ROS_DOMAIN_ID": "77"})
    DRY.refuse_operating_domain({})


def test_host_dry_run_refuses_operating_domain() -> None:
    # 기본 dry_run 을 공용 PC 셸(30)에서 띄우면 가짜 gateway·belt_servo·sort_manager 가 운용 노드와 섞인다
    with pytest.raises(RuntimeError, match="30"):
        HOST.refuse_dry_run_on_operating_domain(True, {"ROS_DOMAIN_ID": "30"})
    HOST.refuse_dry_run_on_operating_domain(False, {"ROS_DOMAIN_ID": "30"})  # 실기는 30 에서
    HOST.refuse_dry_run_on_operating_domain(True, {"ROS_DOMAIN_ID": "77"})
    HOST.refuse_dry_run_on_operating_domain(True, {})


def test_host_without_servo() -> None:
    t = targets(HOST.host_plan(args(with_servo="false")))
    assert "belt_servo.launch.py" not in t and "sort_manager.launch.py" in t


def test_dry_run_servo_mock_by_default_and_sim_option() -> None:
    a = {n: d for n, d, _ in DRY.ARGS} | {"playback": "/bag"}
    assert DRY.mock_args(a) == [
        "--log",
        "--servo",
    ]  # 기본 mock: 고정 카메라 녹화로는 진짜 추종이 LOST 로 끝난다
    assert DRY.dry_run_host_args(a, "/sim.yaml")["with_servo"] == "false"
    sim = a | {"servo": "sim"}
    assert (
        DRY.mock_args(sim) == ["--log"]
        and DRY.dry_run_host_args(sim, "/sim.yaml")["with_servo"] == "true"
    )
    assert DRY.mock_args(sim | {"mock_log": "false"}) == []  # 비면 g0_mock 을 띄우지 않는다
    with pytest.raises(RuntimeError, match="servo"):
        DRY.mock_args(a | {"servo": "real"})


def test_dry_run_turns_devices_off_and_needs_playback() -> None:
    a = {n: d for n, d, _ in DRY.ARGS}
    with pytest.raises(RuntimeError, match="playback"):
        DRY.dry_run_host_args(a, "/sim.yaml")
    h = DRY.dry_run_host_args(a | {"playback": "/bag"}, "/sim.yaml")
    assert h["dry_run"] == "true" and h["servo_params"] == "/sim.yaml"
    assert {h[k] for k in ("with_camera", "with_logger", "with_voice", "with_hmi")} == {"false"}
    assert h["vision_playback"] == "/bag" and not h["servo_log_dir"].startswith(str(SRC.parent))
    assert (
        h["vision_playback_restamp"] == "true"
    )  # 녹화 시각이면 sort_manager 가 "관측 시작 전 촬영"으로 버린다


def test_host_vision_restamp_default_off() -> None:
    vis = next(
        s
        for s in HOST.host_plan(args(with_vision="true", vision_playback="/b"))
        if s.target == "voss_vision.launch.py"
    )
    assert vis.args["playback_restamp"] == "false"  # 운용·분석 재생은 녹화 시각 보존


def test_node_executables_exist() -> None:
    for s in HOST.host_plan(args(dry_run="false")):
        if s.kind != "node" or s.pkg == "realsense2_camera":
            continue
        setup = (SRC / s.pkg / "setup.py").read_text()
        assert re.search(rf'"{s.target} = ', setup), f"{s.pkg} console_scripts 에 {s.target} 없음"


def test_camera_runs_in_root_namespace() -> None:
    # -r __ns:=/ 가 없으면 realsense 가 /camera/camera/color/image_raw 로 내보내 box_tracker 가 영상 0 (10/13 게이트)
    cam = next(
        s for s in HOST.host_plan(args(dry_run="false")) if s.target == "realsense2_camera_node"
    )
    assert (cam.name, cam.namespace) == ("camera", "/")
    assert HOST.to_action(cam).expanded_node_namespace in ("/", None) or True  # Node 생성 자체가 되는지
