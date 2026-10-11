"""T14 후속 비구동 통합시험: 마이크·Whisper → 실제 manager, 이력 → speech_out.
입력: Nodes PC 마이크에서 호출어와 우선순위·이력 문장 2회.
출력: 실제 sort_manager 접수, /api/stats 조회 안내와 PCM 재생 증거.
계약: docs/interfaces/topics.md, intent_json.md, web_api.md, issue #23.
로봇 구동 인터페이스에 연결하지 않는 ROS_DOMAIN_ID=179 전용 시험.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from t14_manager_tts_trial import (
    CONFIG_PATH,
    PRIORITY_SENTENCE,
    SAFE_DOMAIN_ID,
    TrialProbe,
    manager_accepted_priority,
    parser_subscriber_ready,
    read_log,
    require_isolation,
    speech_subscriber_ready,
    start_process,
    stop_processes,
    wait_until,
)
from t14_trial_checks import first_pcm_latency_ms, tts_finished

API_SESSION_URL = "http://127.0.0.1:8080/api/sessions/current"
HISTORY_SENTENCE = "보류 몇 개야"
SAY_NO_SESSION = "기록을 조회할 수 없습니다."
MIC_LOG_MARKER = "voice_listener: mic 모드"
MIC_FALLBACK_MARKER = "voice_listener: text 모드"
MIC_START_TIMEOUT_S = 15.0
MIC_COMMAND_TIMEOUT_S = 85.0
MANAGER_RECEIVE_TIMEOUT_S = 8.0
SPEECH_TIMEOUT_S = 45.0
MAX_FIRST_PCM_MS = 3000
TEST_LOG_DIR = Path.home() / ".local/state/voss-t14/mic-history"


class MicHistoryProbe(TrialProbe):
    """실제 voice_listener transcript와 이력 안내를 관측한다."""

    def __init__(self) -> None:
        super().__init__()
        self.transcripts: list[str] = []
        self.says: list[str] = []
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(
            String, "/voss/voice/transcript", self._on_transcript, qos
        )
        self.create_subscription(
            String, "/voss/voice/say", self._on_say, qos
        )

    def _on_transcript(self, message: String) -> None:
        """마이크·Whisper 결과가 ROS로 전달됐는지 기록한다."""
        self.transcripts.append(message.data)

    def _on_say(self, message: String) -> None:
        """이력 조회 결과로 음성 안내가 나왔는지 기록한다."""
        self.says.append(message.data)


def fetch_current_session() -> str | None:
    """Web PC Spring Boot 현재 세션을 읽기 전용으로 조회한다."""
    try:
        with urlopen(API_SESSION_URL, timeout=5.0) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        print(f"WARN: 현재 세션 REST 조회 실패 ({type(error).__name__})", flush=True)
        return None

    if not isinstance(payload, dict) or not payload.get("ok"):
        print("WARN: /api/sessions/current 비정상 응답", flush=True)
        return None

    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        print("WARN: 세션 ID 형식 오류", flush=True)
        return None
    return session_id


def wait_for_mic(processes: list) -> None:
    """마이크 모드만 인정하고 텍스트 폴백이면 시험을 중단한다."""
    def mic_started() -> bool:
        log_text = read_log("voice_listener")
        if MIC_FALLBACK_MARKER in log_text:
            raise RuntimeError("마이크 없음/오류: voice_listener가 text 폴백됨")
        return MIC_LOG_MARKER in log_text

    wait_until(mic_started, "마이크 준비", MIC_START_TIMEOUT_S, processes)


def wait_for_voice_connections(node: MicHistoryProbe, processes: list) -> None:
    """실제 manager·parser·speech_out·voice_listener 연결을 확인한다."""
    def all_ready() -> bool:
        publisher_info = node.get_publishers_info_by_topic("/voss/voice/transcript")
        microphone_ready = any(info.node_name == "voice_listener" for info in publisher_info)
        return (
            node.zone_received
            and node.idle_received
            and parser_subscriber_ready(node)
            and speech_subscriber_ready(node)
            and microphone_ready
        )

    wait_until(all_ready, "ROS 음성 연결", MIC_START_TIMEOUT_S, processes)


def run_priority(node: MicHistoryProbe, processes: list) -> None:
    """마이크로 우선순위를 지시하고 실제 manager 접수를 검증한다."""
    print("\n[1/2] 마이크에 한 문장으로 말씀해 주세요:", flush=True)
    print("      '헬로 로키, 역삼동부터 분류해'", flush=True)
    wait_until(
        lambda: node.priority_received,
        "마이크/Whisper priority Intent",
        MIC_COMMAND_TIMEOUT_S,
        processes,
    )
    wait_until(
        lambda: manager_accepted_priority(read_log("sort_manager")),
        "실제 sort_manager priority 접수",
        MANAGER_RECEIVE_TIMEOUT_S,
        processes,
    )
    print("PASS: 마이크→Whisper→intent_parser→실제 manager 접수", flush=True)
    print(f"Whisper 전사: {node.transcripts[-1] if node.transcripts else '(관측 없음)'}")


def expected_history_say(session_id: str | None, says: list[str]) -> str | None:
    """세션이 없으면 NO_SESSION만, 세션이 있으면 정상 집계 안내만 인정한다."""
    if session_id == "":
        for text in says:
            if text == SAY_NO_SESSION:
                return text
        return None
    if session_id:
        for text in says:
            if text.startswith("보류는 ") and text.endswith("개입니다."):
                return text
    return None


def run_history(node: MicHistoryProbe, processes: list) -> None:
    """두 번째 마이크 명령을 실제 REST 안내와 speech_out까지 연결한다."""
    session_id = fetch_current_session()
    if session_id is None:
        raise RuntimeError("REST 세션 정보를 확인할 수 없어 이력 시험 중단")
    print("\n[2/2] 마이크에 한 문장으로 말씀해 주세요:", flush=True)
    print("      '헬로 로키, 보류 몇 개야'", flush=True)

    def history_transcribed() -> bool:
        return any("보류" in text and "몇" in text for text in node.transcripts)

    wait_until(
        history_transcribed, "마이크/Whisper 이력 문장", MIC_COMMAND_TIMEOUT_S, processes
    )
    wait_until(
        lambda: expected_history_say(session_id, node.says) is not None,
        "REST 이력 안내",
        SPEECH_TIMEOUT_S,
        processes,
    )
    sentence = expected_history_say(session_id, node.says)
    print(f"이력 안내: {sentence}", flush=True)

    wait_until(
        lambda: tts_finished(read_log("speech_out"))
        or "TTS_FAILED:" in read_log("speech_out"),
        "이력 TTS 재생", SPEECH_TIMEOUT_S, processes,
    )
    speech_log = read_log("speech_out")
    if "TTS_FAILED:" in speech_log:
        raise RuntimeError("TTS 재생 실패: speech_out.log 확인")
    delay_ms = first_pcm_latency_ms(speech_log)
    if delay_ms is None:
        raise RuntimeError("TTS 첫 PCM 로그가 없음")
    print(f"PASS: 실제 이력 안내 → speech_out 완료 ({delay_ms} ms)", flush=True)
    if delay_ms > MAX_FIRST_PCM_MS:
        print(f"FAIL: 첫 PCM {delay_ms} ms > {MAX_FIRST_PCM_MS} ms")
    if session_id == "":
        print("판정: NO_SESSION 폴백 PASS (DB 정상 집계 검증 아님)")
    else:
        print(f"판정: 세션 {session_id}에 대한 집계 안내 발행 PASS")
    print("청각 확인: Nodes PC 스피커에서 이력 안내가 들리는지 직접 확인하세요.")


def run_all(node: MicHistoryProbe, processes: list) -> None:
    """마이크 전사와 관리자 접수·이력 TTS까지 연속 확인한다."""
    wait_for_mic(processes)
    wait_for_voice_connections(node, processes)
    run_priority(node, processes)
    run_history(node, processes)
    print("\n=== T14 마이크 + 실제 manager + REST 이력 + TTS 연속 시험 완료 ===")
    print("미검증: 실제 로봇 구동, manager 자체 Say 발화, HMI DOM 변경.")


def main() -> None:
    """격리 환경에서만 실제 마이크와 세 ROS 노드를 띄워 시험한다."""
    if os.environ.get("ROS_DOMAIN_ID") != SAFE_DOMAIN_ID:
        raise SystemExit("실제 로봇 보호: ROS_DOMAIN_ID=179 필요")
    if os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise SystemExit("실제 로봇 보호: ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST 필요")
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"설정 파일 없음: {CONFIG_PATH}")
    if shutil.which("aplay") is None:
        raise SystemExit("aplay 없음: Nodes PC 스피커 설정 필요")

    rclpy.init()
    node = MicHistoryProbe()
    executor = MultiThreadedExecutor(num_threads=2)
    processes: list = []
    runner: Thread | None = None
    try:
        require_isolation(node)
        executor.add_node(node)
        runner = Thread(target=executor.spin, daemon=True)
        runner.start()
        processes.append(start_process(
            "sort_manager",
            ["ros2", "run", "voss_manager", "sort_manager",
             "--ros-args", "-p", f"config_path:={CONFIG_PATH}", "-p", "home_first:=false"],
        ))
        processes.append(start_process(
            "intent_parser", ["ros2", "run", "voss_voice", "intent_parser"],
        ))
        processes.append(start_process(
            "speech_out", ["ros2", "run", "voss_voice", "speech_out"],
        ))
        processes.append(start_process(
            "voice_listener",
            ["ros2", "run", "voss_voice", "voice_listener",
             "--ros-args", "-p", "mode:=mic", "-p", "require_wake:=true"],
        ))
        run_all(node, processes)
    except (RuntimeError, OSError) as error:
        print(f"FAIL: {error}", flush=True)
        print(f"시험 로그: {TEST_LOG_DIR} 또는 기존 manager-tts 로그 경로", flush=True)
        raise SystemExit(1) from error
    finally:
        stop_processes(processes)
        executor.shutdown()
        if runner is not None:
            runner.join(timeout=2)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
