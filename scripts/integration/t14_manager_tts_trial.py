"""T14: 실제 sort_manager 접수와 speech_out 오디오를 하나의 격리 ROS 시험으로 확인한다.
입력: 시험용 transcript '역삼동부터 분류해', 안내 문장.
출력: 실제 manager의 명령 접수 로그 및 speech_out PCM 재생 로그.
근거: docs/interfaces/topics.md, intent_json.md, issue #23.
실제 로봇 서비스/액션과 연결하지 않으며 ROS_DOMAIN_ID=179에서만 실행한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Thread
from typing import Callable

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from voss_msgs.msg import Intent, SortState, ZoneMap

from t14_trial_checks import first_pcm_latency_ms, manager_accepted_priority, tts_finished

SAFE_DOMAIN_ID = "179"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voss_config.yaml"
LOG_DIR = Path.home() / ".local/state/voss-t14/manager-tts"
STARTUP_TIMEOUT_S = 15.0
INTENT_TIMEOUT_S = 12.0
MANAGER_TIMEOUT_S = 6.0
TTS_TIMEOUT_S = 35.0
MAX_FIRST_PCM_MS = 3000
PRIORITY_SENTENCE = "역삼동부터 분류해"
SPOKEN_SENTENCE = "T14 시험입니다. 역삼동 우선 분류 지시가 작업 관리자에 접수되었습니다."

QOS_EVENTS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
QOS_ZONE = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)


class TrialProbe(Node):
    """실제 관리자 상태·zone_map·Intent를 관측하고 시험 입력만 발행한다."""

    def __init__(self) -> None:
        super().__init__("t14_manager_tts_probe")
        self.zone_received = False
        self.idle_received = False
        self.priority_received = False
        self.transcript_pub = self.create_publisher(
            String, "/voss/voice/transcript", QOS_EVENTS
        )
        self.say_pub = self.create_publisher(String, "/voss/voice/say", QOS_EVENTS)
        self.create_subscription(
            ZoneMap, "/voss/sort/zone_map", self._on_zones, QOS_ZONE
        )
        self.create_subscription(
            SortState, "/voss/sort/state", self._on_state, QOS_EVENTS
        )
        self.create_subscription(
            Intent, "/voss/voice/intent", self._on_intent, QOS_EVENTS
        )

    def _on_zones(self, message: ZoneMap) -> None:
        """실제 관리자가 설정한 역삼동 구역이 발행됐는지 확인한다."""
        self.zone_received = any(entry.dong == "역삼동" for entry in message.entries)

    def _on_state(self, message: SortState) -> None:
        """실제 관리자가 운전하지 않는 IDLE 상태를 확인한다."""
        if message.state == "IDLE":
            self.idle_received = True

    def _on_intent(self, message: Intent) -> None:
        """허용 목록으로 검증된 priority Intent를 관측한다."""
        if (
            message.type == "priority"
            and message.dong == "역삼동"
            and message.box_id == ""
        ):
            self.priority_received = True


def require_isolation(node: Node) -> None:
    """실제 로봇 도메인이나 남아 있는 시험 노드가 있으면 시작하지 않는다."""
    if os.environ.get("ROS_DOMAIN_ID") != SAFE_DOMAIN_ID:
        raise RuntimeError("ROS_DOMAIN_ID=179 필수: 실제 로봇 도메인에서는 금지")
    if os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise RuntimeError("ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 필수")
    time.sleep(1.0)
    existing = [name for name in node.get_node_names() if name != node.get_name()]
    if existing:
        raise RuntimeError(f"기존 격리 시험 노드가 남아 있습니다: {existing}")


def start_process(name: str, command: list[str]) -> subprocess.Popen:
    """이번 시험이 소유하는 ROS 프로세스를 로그 파일과 함께 실행한다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logfile = LOG_DIR / f"{name}.log"
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    with logfile.open("w", encoding="utf-8") as output:
        return subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )


def read_log(name: str) -> str:
    """지금까지 기록된 노드 로그를 읽는다."""
    logfile = LOG_DIR / f"{name}.log"
    if not logfile.exists():
        return ""
    return logfile.read_text(encoding="utf-8", errors="replace")


def wait_until(
    condition: Callable[[], bool],
    label: str,
    timeout_s: float,
    processes: list[subprocess.Popen],
) -> None:
    """조건을 기다리되 노드 종료·시간 초과를 즉시 실패로 처리한다."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{label}: 자식 노드 종료 PID={process.pid}")
        if condition():
            return
        time.sleep(0.1)
    raise RuntimeError(f"{label}: {timeout_s:.0f}초 내 확인 실패")


def speech_subscriber_ready(node: TrialProbe) -> bool:
    """테스트 안내를 실제 speech_out만 수신할 수 있는지 확인한다."""
    infos = node.get_subscriptions_info_by_topic("/voss/voice/say")
    return any(info.node_name == "speech_out" for info in infos)


def parser_subscriber_ready(node: TrialProbe) -> bool:
    """실제 intent_parser가 transcript를 받을 준비가 됐는지 확인한다."""
    infos = node.get_subscriptions_info_by_topic("/voss/voice/transcript")
    return any(info.node_name == "intent_parser" for info in infos)


def stop_processes(processes: list[subprocess.Popen]) -> None:
    """이번 스크립트가 생성한 노드만 종료하고 기존 노드는 건드리지 않는다."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_trial(node: TrialProbe, processes: list[subprocess.Popen]) -> None:
    """실제 관리자 priority 접수, 실제 TTS 오디오 재생을 연속 시험한다."""
    wait_until(
        lambda: (
            node.zone_received
            and node.idle_received
            and parser_subscriber_ready(node)
            and speech_subscriber_ready(node)
        ),
        "노드 준비",
        STARTUP_TIMEOUT_S,
        processes,
    )

    # start/stop은 장비 호출이 가능하다. 격리 시험에서는 priority만 보낸다.
    node.transcript_pub.publish(String(data=PRIORITY_SENTENCE))
    wait_until(
        lambda: node.priority_received,
        "Intent 파싱",
        INTENT_TIMEOUT_S,
        processes,
    )
    wait_until(
        lambda: manager_accepted_priority(read_log("sort_manager")),
        "실제 sort_manager 접수",
        MANAGER_TIMEOUT_S,
        processes,
    )
    print("PASS: 실제 sort_manager priority(역삼동) 접수", flush=True)

    # manager는 IDLE에서 priority를 받아도 Say를 만들지 않는다.
    # TTS 재생은 시험기가 표준 Say 토픽을 발행해 별도로 확인한다.
    node.say_pub.publish(String(data=SPOKEN_SENTENCE))
    wait_until(
        lambda: (
            tts_finished(read_log("speech_out"))
            or "TTS_FAILED:" in read_log("speech_out")
        ),
        "실제 speech_out 오디오",
        TTS_TIMEOUT_S,
        processes,
    )

    speech_log = read_log("speech_out")
    if "TTS_FAILED:" in speech_log:
        raise RuntimeError("TTS 실패: speech_out.log 확인")
    delay_ms = first_pcm_latency_ms(speech_log)
    if delay_ms is None:
        raise RuntimeError("첫 PCM 전달 지연 로그가 없습니다.")
    print(f"PASS: speech_out PCM 재생 완료, 첫 PCM 전달 {delay_ms} ms", flush=True)
    if delay_ms > MAX_FIRST_PCM_MS:
        print(f"주의: 첫 PCM 전달 지연 {delay_ms} ms > {MAX_FIRST_PCM_MS} ms")
    print("청각 확인 필요: Nodes PC 스피커에서 T14 안내가 실제 들렸는지 확인하세요.")
    print("=== T14 실제 manager 접수 + 실제 TTS 재생 경로 확인 ===")
    print("범위: 격리 도메인 IDLE 우선순위 접수 + 시험기 Say 출력.")
    print("미검증: manager 자체 Say 생성→TTS, 실로봇·마이크·HMI 통합.")


def main() -> None:
    """PC의 ROS 격리 설정을 확인하고 세 노드 시험을 실행한다."""
    if os.environ.get("ROS_DOMAIN_ID") != SAFE_DOMAIN_ID:
        raise SystemExit("ROS_DOMAIN_ID=179일 때만 실행 가능")
    if os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise SystemExit("ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 필수")
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"설정 파일 없음: {CONFIG_PATH}")
    if shutil.which("aplay") is None:
        raise SystemExit("aplay 없음: Nodes PC 음성 출력 패키지 설치 확인 필요")

    rclpy.init()
    probe = TrialProbe()
    executor = MultiThreadedExecutor(num_threads=2)
    children: list[subprocess.Popen] = []
    runner: Thread | None = None
    try:
        require_isolation(probe)
        executor.add_node(probe)
        runner = Thread(target=executor.spin, daemon=True)
        runner.start()
        children.append(
            start_process(
                "sort_manager",
                [
                    "ros2", "run", "voss_manager", "sort_manager",
                    "--ros-args", "-p", f"config_path:={CONFIG_PATH}",
                    "-p", "home_first:=false",
                ],
            )
        )
        children.append(
            start_process("intent_parser", ["ros2", "run", "voss_voice", "intent_parser"])
        )
        children.append(
            start_process("speech_out", ["ros2", "run", "voss_voice", "speech_out"])
        )
        run_trial(probe, children)
    except (RuntimeError, OSError) as error:
        print(f"FAIL: {error}")
        print(f"노드별 진단 로그: {LOG_DIR}")
        raise SystemExit(1) from error
    finally:
        stop_processes(children)
        executor.shutdown()
        if runner is not None:
            runner.join(timeout=2)
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
