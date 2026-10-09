"""belt_servo 단독 기동 (design/U3-dd.md 2절). 계산은 전부 voss_servo/launch_params.py.

실기 (G0 runbook T7, 사람이 비상정지 옆에서 — 브링업·robot_gateway 뒤):
  ros2 launch voss_servo belt_servo.launch.py params:=~/voss_ws/config/belt_servo_real.yaml \
    log_dir:=<레포>/data/servo
인자: params(필수, belt_servo YAML) · config(voss_config.yaml, 기본 gateway launch 와 같음)
      · overrides(덮어쓸 YAML, 선택) · log_dir(log.dir 덮어쓰기, 선택)
- null(미측정) 키는 넘기지 않는다 → 노드가 "READY 거부: missing=[…]" 로 알려 준다.
- voss_config 의 belt·gripper·timing 값과 config_version·config_sha256(앞 12자리)을 함께 넘긴다.
- 파일 없음·YAML 오류·params 에 voss_config 키(규칙 5) → launch 가 오류로 멈추고 노드를 띄우지 않는다.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from voss_servo.launch_params import build_params, summary_line


def _setup(context):
    """인자 → build_params → [요약 로그, 경고 로그…, belt_servo 노드]."""

    def arg(name: str) -> str:
        return LaunchConfiguration(name).perform(context).strip()  # launch 인자 문자열

    result = build_params(
        arg("params"),
        arg("config"),
        overrides_path=arg("overrides") or None,  # 빈 문자열 = 안 씀
        log_dir=arg("log_dir") or None,
    )
    actions = [LogInfo(msg=summary_line(result))]  # 무엇을 읽어 무엇을 넘겼나
    actions += [LogInfo(msg=f"경고: {w}") for w in result.warnings]
    actions.append(
        Node(
            package="voss_servo",
            executable="belt_servo",
            name="belt_servo",
            output="screen",  # emulate_tty 는 쓰지 않는다 (로그 파일에 색 코드가 섞이지 않게)
            parameters=[result.params],
        )
    )
    return actions


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params", default_value="", description="belt_servo 파라미터 YAML (필수)"
            ),
            DeclareLaunchArgument(
                "config",
                default_value="~/voss_ws/config/voss_config.yaml",
                description="voss_config.yaml (gateway launch 와 같은 기본값)",
            ),
            DeclareLaunchArgument(
                "overrides", default_value="", description="덮어쓸 YAML (선택, 같은 모양)"
            ),
            DeclareLaunchArgument(
                "log_dir", default_value="", description="log.dir 덮어쓰기 (선택, 절대 경로로 펼침)"
            ),
            OpaqueFunction(function=_setup),
        ]
    )
