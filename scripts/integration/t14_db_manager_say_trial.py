"""T14 #23: 실제 DB 집계 안내와 실제 manager 자체 Say→speech_out 통합 비구동 시험.
입력: Spring Boot 읽기 전용 /api/stats, 격리 ROS 가짜 준비/OBSERVE 실패 응답.
출력: DB 집계와 한국어 발화, 실제 manager가 발행한 오류 안내 재생 확인.
계약: docs/interfaces/web_api.md, topics.md, intent_json.md.
로봇 구동/DB 쓰기/MQTT 발행을 하지 않으며 ROS_DOMAIN_ID=179 전용이다.
"""

from __future__ import annotations

import json
import os
import signal
import time
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from voss_msgs.action import TrackAndGrasp
from voss_msgs.msg import BoxTrack, LabelRead, SortState, ZoneMap
from voss_msgs.srv import Command, MoveToZone

from t14_manager_tts_trial import (
    CONFIG_PATH,
    LOG_DIR,
    require_isolation,
    read_log,
    start_process,
    wait_until,
)
from t14_trial_checks import (
    count_finished_playbacks,
    history_scope,
    last_pcm_latency_ms,
)
from voss_voice.intent_logic import stats_sentence

API_BASE = "http://127.0.0.1:8080"
MANAGER_SAY = "관측 자세로 가지 못해 일시정지했습니다."
FAKE_MOVE_FAILURE = "T14_SIMULATED_OBSERVE_FAILURE"
HISTORY_QUERY = {"query_kind": "held_count", "dong": ""}
STARTUP_TIMEOUT_S = 20.0
SERVICE_TIMEOUT_S = 10.0
TTS_TIMEOUT_S = 45.0
HISTORY_TIMEOUT_S = 15.0
MAX_FIRST_PCM_MS = 3000

QOS_EVENTS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


def get_json(path: str, params: dict[str, str] | None = None) -> dict:
    """Spring Boot 읽기 전용 GET을 수행하고 HTTP 오류를 그대로 실패 처리한다."""
    url = API_BASE + path
    if params:
        url += "?" + urlencode(params)
    try:
        with urlopen(url, timeout=5.0) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise RuntimeError(f"Spring Boot GET {path} 실패: {type(error).__name__}") from error
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Spring Boot GET {path}: ok=true 아님")
    return result


def read_real_db_count() -> tuple[str, int]:
    """현재 세션이 없으면 전체 이력을 명시적으로 조회해 실제 DB 값을 받는다."""
    current = get_json("/api/sessions/current")
    session_id = current.get("session_id")
    if not isinstance(session_id, str):
        raise RuntimeError("현재 세션 응답 형식 오류")

    scope = history_scope(session_id)
    params = {"query_kind": HISTORY_QUERY["query_kind"]}
    if scope == "all":
        params["session_id"] = "all"

    stats = get_json("/api/stats", params)
    count = stats.get("count")
    if type(count) is not int or count < 0:
        raise RuntimeError("집계 응답 count는 0 이상의 정수여야 함")
    print(f"PASS: 실제 DB held_count={count}, 조회 범위={scope}", flush=True)
    return scope, count


class FakeHardwareProbe(Node):
    """로봇 대신 동작하지 않는 가짜 준비 서비스와 실제 Say 관측을 제공한다."""

    def __init__(self) -> None:
        super().__init__("t14_db_manager_say_probe")
        self.idle_ready = False
        self.state = ""
        self.manager_says: list[str] = []
        self.last_move_zone = ""
        self._pose_pub = self.create_publisher(
            PoseStamped, "/voss/robot/pose",
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
        )
        self._log_pub = self.create_publisher(String, "/voss/log/status", QOS_EVENTS)
        # 판독 데이터를 보내지 않는다. ready용으로 publisher 존재만 제공한다.
        self._box_pub = self.create_publisher(
            BoxTrack, "/voss/vision/box",
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
        )
        self._label_pub = self.create_publisher(LabelRead, "/voss/vision/label", QOS_EVENTS)
        self.create_service(MoveToZone, "/voss/robot/move_to_zone", self._fail_move)
        self._servo_server = ActionServer(
            self, TrackAndGrasp, "/voss/servo/track_and_grasp",
            execute_callback=self._reject_grasp_execution,
            goal_callback=self._deny_grasp_goal,
        )
        self.start_client = self.create_client(Command, "/voss/sort/command")
        self.transcript_pub = self.create_publisher(String, "/voss/voice/transcript", QOS_EVENTS)
        self.say_pub = self.create_publisher(String, "/voss/voice/say", QOS_EVENTS)
        self.create_subscription(SortState, "/voss/sort/state", self._on_state, QOS_EVENTS)
        self.create_subscription(String, "/voss/voice/say", self._on_say, QOS_EVENTS)
        self.create_subscription(ZoneMap, "/voss/sort/zone_map", self._on_zone, QOS_EVENTS)
        self.zone_received = False
        self.create_timer(0.1, self._publish_readiness)

    def _publish_readiness(self) -> None:
        """실제 이동 없이 manager의 초기 ready 조건만 충족한다."""
        self._pose_pub.publish(PoseStamped())
        self._log_pub.publish(String(data="OK"))

    def _fail_move(self, request, response):
        """실제 이동 서비스 대신 실패만 반환해 manager 자체 안내를 유발한다."""
        self.last_move_zone = request.zone
        response.ok = False
        response.message = FAKE_MOVE_FAILURE
        return response

    def _deny_grasp_goal(self, _request):
        """추종 동작은 이 비구동 시험에서 절대 수락하지 않는다."""
        return GoalResponse.REJECT

    def _reject_grasp_execution(self, _goal_handle):
        """거부된 액션은 실행되지 않는다. 잘못 호출돼도 무동작 결과만 반환한다."""
        return TrackAndGrasp.Result()

    def _on_state(self, message: SortState) -> None:
        """실제 manager가 IDLE·ready가 됐는지 확인한다."""
        self.state = message.state
        if message.state == "IDLE" and message.ready:
            self.idle_ready = True

    def _on_say(self, message: String) -> None:
        """실제 manager가 보낸 Say와 테스트 음성 안내를 관측한다."""
        self.manager_says.append(message.data)

    def _on_zone(self, _message: ZoneMap) -> None:
        """실제 manager ZoneMap 수신 여부만 확인한다."""
        self.zone_received = True


def voice_connections_ready(node: FakeHardwareProbe) -> bool:
    """관리자·스피커·파서 구독 연결을 ROS 그래프에서 확인한다."""
    info = node.get_subscriptions_info_by_topic("/voss/voice/say")
    return any(entry.node_name == "speech_out" for entry in info)


def run_start_in_simulation(node: FakeHardwareProbe, processes: list) -> None:
    """가짜 준비 조건에서만 실제 manager를 시작해 실패 안내를 발생시킨다."""
    wait_until(
        lambda: node.idle_ready
        and node.zone_received
        and node.start_client.service_is_ready()
        and voice_connections_ready(node),
        "가짜 준비·실제 manager/speech_out 연결",
        STARTUP_TIMEOUT_S,
        processes,
    )
    result = node.start_client.call_async(Command.Request(command="start", arg=""))
    wait_until(lambda: result.done(), "격리 manager start 응답", SERVICE_TIMEOUT_S, processes)
    response = result.result()
    if response is None or not response.ok:
        raise RuntimeError(f"격리 manager start 거부: {response}")
    print("PASS: 격리 manager start (실제 로봇 연결 없음)", flush=True)


def wait_playback(processes: list, expected_finishes: int, label: str) -> None:
    """실제 speech_out의 새 PCM 재생 완료 및 3초 안의 첫 PCM을 확인한다."""
    wait_until(
        lambda: count_finished_playbacks(read_log("speech_out")) >= expected_finishes
        or "TTS_FAILED:" in read_log("speech_out"),
        label,
        TTS_TIMEOUT_S,
        processes,
    )
    log_text = read_log("speech_out")
    if "TTS_FAILED:" in log_text:
        raise RuntimeError("speech_out TTS_FAILED 로그 발견")
    first_pcm_ms = last_pcm_latency_ms(log_text)
    if first_pcm_ms is None:
        raise RuntimeError("첫 PCM 지연 로그 없음")
    if first_pcm_ms > MAX_FIRST_PCM_MS:
        raise RuntimeError(f"첫 PCM 전달 {first_pcm_ms}ms > {MAX_FIRST_PCM_MS}ms")
    print(f"PASS: {label}, 첫 PCM {first_pcm_ms} ms", flush=True)


def verify_real_manager_say(node: FakeHardwareProbe, processes: list) -> None:
    """실제 manager가 직접 발행한 OBSERVE 실패 안내가 재생되는지 확인한다."""
    run_start_in_simulation(node, processes)
    wait_until(
        lambda: MANAGER_SAY in node.manager_says,
        "실제 manager 자체 Say 발행",
        SERVICE_TIMEOUT_S,
        processes,
    )
    if node.last_move_zone != "OBSERVE":
        raise RuntimeError("가짜 OBSERVE 이동 실패 이벤트가 발생하지 않음")
    if FAKE_MOVE_FAILURE not in read_log("sort_manager"):
        raise RuntimeError("실제 manager의 OBSERVE 실패 처리 로그 없음")
    wait_playback(processes, 1, "manager 자체 Say→실제 speech_out 재생")
    print(f"manager 안내: {MANAGER_SAY}", flush=True)


def verify_real_db_speech(node: FakeHardwareProbe, processes: list) -> None:
    """실제 DB 집계값과 한국어 TTS 음성을 비교한다."""
    scope, count = read_real_db_count()
    expected = stats_sentence(HISTORY_QUERY, {"ok": True, "count": count})

    if scope != "all":
        # 실제 현재 세션이 있으면 intent_parser의 정규 REST 조회 경로를 탄다.
        processes.append(start_process(
            "intent_parser", ["ros2", "run", "voss_voice", "intent_parser"]
        ))
        wait_until(
            lambda: any(
                info.node_name == "intent_parser"
                for info in node.get_subscriptions_info_by_topic("/voss/voice/transcript")
            ),
            "실제 intent_parser 연결",
            STARTUP_TIMEOUT_S,
            processes,
        )
        # ZoneMap 콜백이 준비될 시간을 준다 (transient_local).
        time.sleep(0.6)
        node.transcript_pub.publish(String(data="보류 몇 개야"))
        wait_until(
            lambda: expected in node.manager_says,
            "intent_parser DB 조회→Say",
            HISTORY_TIMEOUT_S,
            processes,
        )
        print("PASS: 실제 현재 세션의 음성 이력 조회→Say", flush=True)
    else:
        # 현재 세션을 위조할 수 없으므로 전체 이력 조회만 수행한다.
        # 정규 intent_parser의 현재 세션 경로 성공이라고 주장하지 않는다.
        node.say_pub.publish(String(data=expected))
        wait_until(
            lambda: expected in node.manager_says,
            "시험기 DB 집계값 Say",
            SERVICE_TIMEOUT_S,
            processes,
        )
        print("부분검증: 전체 이력 DB 값→시험기 Say (현재 세션 없음)", flush=True)

    wait_playback(processes, 2, "실제 DB 집계값→TTS 음성 재생")
    print(f"DB 집계 안내: {expected}", flush=True)
    print(f"집계 범위: {'전체 이력(session_id=all)' if scope == 'all' else '현재 세션'}")


def stop_owned_process_groups(processes: list) -> None:
    """이번 스크립트가 시작한 프로세스 그룹만 종료해 자식 노드까지 정리한다."""
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    for process in processes:
        try:
            process.wait(timeout=4.0)
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    time.sleep(1.0)


def main() -> None:
    """실물 장비를 건드리지 않는 로컬 격리 시험 두 건을 연속 수행한다."""
    if os.environ.get("ROS_DOMAIN_ID") != "179":
        raise SystemExit("실물 로봇 보호: ROS_DOMAIN_ID=179에서만 허용")
    if os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE") != "LOCALHOST":
        raise SystemExit("실물 로봇 보호: LOCALHOST 탐색만 허용")
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"설정 파일 없음: {CONFIG_PATH}")
    # 데이터 유무/REST 접근을 먼저 확인하되 실제 DB 쓰기와 세션 생성은 하지 않는다.
    get_json("/api/sessions/current")

    rclpy.init()
    probe = FakeHardwareProbe()
    executor = MultiThreadedExecutor(num_threads=3)
    processes: list = []
    thread: Thread | None = None
    try:
        require_isolation(probe)
        executor.add_node(probe)
        thread = Thread(target=executor.spin, daemon=True)
        thread.start()
        processes.append(start_process(
            "speech_out", ["ros2", "run", "voss_voice", "speech_out"],
        ))
        processes.append(start_process(
            "sort_manager", [
                "ros2", "run", "voss_manager", "sort_manager",
                "--ros-args", "-p", f"config_path:={CONFIG_PATH}",
                "-p", "home_first:=true",
            ],
        ))
        verify_real_manager_say(probe, processes)
        verify_real_db_speech(probe, processes)
        print("=== T14 DB 이력 음성 + manager 자체 안내 비구동 연속시험 종료 ===")
        print("청각 확인: 두 안내 모두 Nodes PC에서 들렸는지 직접 확인 필요")
    except (RuntimeError, OSError) as error:
        print(f"FAIL: {error}", flush=True)
        print(f"로그: {LOG_DIR}", flush=True)
        raise SystemExit(1) from error
    finally:
        stop_owned_process_groups(processes)
        executor.shutdown()
        if thread is not None:
            thread.join(timeout=2.0)
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
