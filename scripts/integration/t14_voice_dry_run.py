"""T14 비구동 선행시험: voice_listener(text) → intent_parser → 가짜 manager.
입력: 운전·우선·답변·이력 대표 발화 4개.
출력: 실제 ROS Intent와 /voss/voice/say, Web PC REST 조회 경로.
계약: docs/interfaces/intent_json.md, topics.md, issue #23.
실제 manager·로봇을 구동하지 않으며 격리된 ROS_DOMAIN_ID에서만 실행한다.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Thread

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from voss_msgs.msg import Intent, SortState, ZoneMap, ZoneMapEntry

SAFE_TEST_DOMAIN_ID = "179"
VOICE_STARTUP_TIMEOUT_S = 12.0
CASE_TIMEOUT_S = 9.0
SAMPLE_BOX_ID = "20261011T121525-1ab9-001"
LOG_DIR = Path.home() / ".local/state/voss-t14"


@dataclass(frozen=True)
class Trial:
    """시험할 음성 문장과 기대되는 모의 manager 출력이다."""
    title: str
    transcript: str
    state: str
    intent_type: str
    dong: str = ""
    answer_box_id: str = ""


TRIALS = (
    Trial("운전", "작업 시작해", "IDLE", "start"),
    Trial("우선", "역삼동부터 분류해", "RUNNING", "priority", dong="역삼동"),
    Trial("답변", "대치동", "ASKING", "answer", dong="대치동",
          answer_box_id=SAMPLE_BOX_ID),
    Trial("이력", "보류 몇 개야", "IDLE", "query_history"),
)


class MockManager(Node):
    """실제 sort_manager 대신 수신 Intent를 기록하고 안내만 발행한다."""

    def __init__(self) -> None:
        super().__init__("t14_mock_manager")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        zone_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.received_intents: list[Intent] = []
        self.received_says: list[str] = []
        self.zone_pub = self.create_publisher(ZoneMap, "/voss/sort/zone_map", zone_qos)
        self.state_pub = self.create_publisher(SortState, "/voss/sort/state", qos)
        self.create_subscription(Intent, "/voss/voice/intent", self._on_intent, qos)
        self.create_subscription(String, "/voss/voice/say", self._on_say, qos)
        self.say_pub = self.create_publisher(String, "/voss/voice/say", qos)

    def _on_intent(self, message: Intent) -> None:
        """가짜 manager에 도착한 Intent를 기록하고 수신 안내만 한다."""
        self.received_intents.append(message)
        self.say_pub.publish(String(data=f"T14 모의 manager 수신: {message.type}"))

    def _on_say(self, message: String) -> None:
        """manager 또는 이력 조회에서 생성된 안내 문구를 보관한다."""
        self.received_says.append(message.data)

    def publish_zones(self) -> None:
        """실제 zone_map을 바꾸지 않고 격리 도메인에만 허용 목록을 발행한다."""
        entries = []
        for dong, zone, alias in (
            ("역삼동", "A", "역삼"),
            ("대치동", "B", "대치"),
            ("청담동", "C", "청담"),
        ):
            entry = ZoneMapEntry()
            entry.dong = dong
            entry.zone = zone
            entry.code = ""
            entry.aliases = [alias]
            entries.append(entry)
        message = ZoneMap()
        message.version = "t14-dry-run"
        message.entries = entries
        self.zone_pub.publish(message)

    def publish_state(self, state: str, box_id: str) -> None:
        """답변 시험 시 ASKING과 해당 box_id를 모의로 제공한다."""
        message = SortState()
        message.state = state
        message.box_id = box_id
        message.pending_question = "T14 시험 질문" if state == "ASKING" else ""
        message.track_id = -1
        message.ready = False
        message.not_ready = ["ROBOT"]
        message.session_id = ""
        self.state_pub.publish(message)


def ensure_isolated(node: Node) -> None:
    """실제 로봇 도메인이나 다른 노드가 보이면 시험을 거부한다."""
    if os.getenv("ROS_DOMAIN_ID") != SAFE_TEST_DOMAIN_ID:
        raise RuntimeError(f"ROS_DOMAIN_ID={SAFE_TEST_DOMAIN_ID}에서만 실행할 수 있습니다.")
    if os.getenv("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise RuntimeError("ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST가 필요합니다.")
    time.sleep(1.0)
    existing = [name for name in node.get_node_names() if name != node.get_name()]
    if existing:
        raise RuntimeError(f"격리 도메인에 기존 노드가 있습니다: {existing}")


def start_child(name: str, args: list[str]) -> subprocess.Popen:
    """자식 ROS 노드의 실행 로그를 파일에 보존하며 시작한다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    with log_path.open("w", encoding="utf-8") as output:
        return subprocess.Popen(
            args,
            stdin=subprocess.PIPE if name == "voice_listener" else subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )


def wait_for_subscribers(node: MockManager) -> None:
    """voice_listener·intent_parser의 ROS 구독자가 준비될 때까지 기다린다."""
    deadline = time.monotonic() + VOICE_STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        transcript_publishers = node.get_publishers_info_by_topic("/voss/voice/transcript")
        transcript_ready = any(info.node_name == "voice_listener" for info in transcript_publishers)
        zones_ready = node.zone_pub.get_subscription_count() > 0
        states_ready = node.state_pub.get_subscription_count() > 0
        if transcript_ready and zones_ready and states_ready:
            return
        time.sleep(0.2)
    raise RuntimeError("voice_listener 또는 intent_parser가 준비되지 않았습니다.")


def wait_for_result(node: MockManager, trial: Trial) -> bool:
    """출력 조건을 확인한다. 이력은 manager Intent가 아니라 음성 안내다."""
    deadline = time.monotonic() + CASE_TIMEOUT_S
    while time.monotonic() < deadline:
        if trial.intent_type == "query_history":
            for sentence in node.received_says:
                if sentence.startswith("보류는 ") or sentence == "기록을 조회할 수 없습니다.":
                    print(f"이력 안내: {sentence}")
                    return True
        else:
            for intent in node.received_intents:
                if intent.type != trial.intent_type:
                    continue
                if intent.dong != trial.dong:
                    continue
                if intent.box_id != trial.answer_box_id:
                    continue
                return True
        time.sleep(0.1)
    return False


def run_trials(node: MockManager, listener: subprocess.Popen) -> int:
    """실제 텍스트 폴백·Intent 노드를 거쳐 4유형을 한 번씩 시험한다."""
    if listener.stdin is None:
        raise RuntimeError("voice_listener 표준 입력이 없습니다.")

    node.publish_zones()
    time.sleep(0.5)
    passed = 0
    for trial in TRIALS:
        node.received_intents.clear()
        node.received_says.clear()
        node.publish_state(trial.state, trial.answer_box_id)
        time.sleep(0.5)
        listener.stdin.write(trial.transcript + "\n")
        listener.stdin.flush()

        ok = wait_for_result(node, trial)
        print(f"{'PASS' if ok else 'FAIL'}: {trial.title} — {trial.transcript}", flush=True)
        if ok:
            passed += 1
    return passed


def stop_children(processes: list[subprocess.Popen]) -> None:
    """본 시험이 시작한 음성 노드만 종료한다."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> None:
    """ROS 격리 도메인에서 4유형을 검증하고 총합을 출력한다."""
    if os.getenv("ROS_DOMAIN_ID") != SAFE_TEST_DOMAIN_ID:
        raise SystemExit("실제 도메인 보호: ROS_DOMAIN_ID=179 설정이 필요합니다.")
    if os.getenv("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise SystemExit("ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 설정이 필요합니다.")
    rclpy.init()
    node = MockManager()
    executor = MultiThreadedExecutor(num_threads=2)
    processes: list[subprocess.Popen] = []
    executor_thread = None
    try:
        ensure_isolated(node)
        executor.add_node(node)
        executor_thread = Thread(target=executor.spin, daemon=True)
        executor_thread.start()

        parser = start_child("intent_parser", ["ros2", "run", "voss_voice", "intent_parser"])
        processes.append(parser)
        listener = start_child(
            "voice_listener",
            ["ros2", "run", "voss_voice", "voice_listener",
             "--ros-args", "-p", "mode:=text"],
        )
        processes.append(listener)

        wait_for_subscribers(node)
        passed = run_trials(node, listener)
        print(f"=== T14 비구동 선행시험: {passed}/{len(TRIALS)} ===")
        print("주의: TTS 스피커·실제 sort_manager·HMI 연결·실로봇은 이 시험 대상이 아닙니다.")
        if passed != len(TRIALS):
            raise SystemExit("FAIL: 일부 유형 실패. ~/.local/state/voss-t14/ 로그를 확인하세요.")
    finally:
        stop_children(processes)
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
