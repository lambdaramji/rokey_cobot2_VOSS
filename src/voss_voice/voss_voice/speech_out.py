"""speech_out: ROS say 이벤트를 FIFO 순서로 로컬 TTS로 재생한다.
입력은 /voss/voice/say (std_msgs/String), 출력은 로컬 스피커다.
관련 문서: docs/interfaces/topics.md, SYS-FR-022.
"""

from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Callable

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

SAY_TOPIC = "/voss/voice/say"
DEFAULT_TTS_COMMAND = "espeak-ng"
QUEUE_CAPACITY = 32
TTS_TIMEOUT_S = 30.0
QOS_SAY = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


def speak_with_espeak(text: str, executable: str) -> None:
    """로컬 한국어 TTS를 재생하고 오류가 나면 호출자에게 전달한다."""
    subprocess.run(
        [executable, "-v", "ko", "--", text],
        check=True,
        timeout=TTS_TIMEOUT_S,
    )


class SpeechQueue:
    """ROS와 독립적으로 메시지를 FIFO로 재생하는 작업 큐."""

    def __init__(
        self,
        play: Callable[[str], None],
        report: Callable[[str], None],
        capacity: int = QUEUE_CAPACITY,
    ) -> None:
        self._play = play
        self._report = report
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=capacity)
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, text: str) -> bool:
        """문장을 추가하며 빈 메시지나 큐 포화는 거부한다."""
        cleaned = text.strip()
        if not cleaned:
            return False
        try:
            self._queue.put_nowait(cleaned)
        except queue.Full:
            self._report("TTS_QUEUE_FULL")
            return False
        return True

    def _run(self) -> None:
        """재생 실패를 보고하되 다음 메시지 처리를 계속한다."""
        while True:
            text = self._queue.get()
            try:
                if text is None:
                    return
                self._play(text)
                self._report("TTS_PLAYED")
            except (OSError, subprocess.SubprocessError) as error:
                self._report(f"TTS_FAILED: {error}")
            finally:
                self._queue.task_done()

    def close(self) -> None:
        """큐의 기존 항목을 모두 처리하고 작업 스레드를 종료한다."""
        self._queue.put(None)
        self._worker.join()


class SpeechOutNode(Node):
    """say 토픽을 구독하고 TTS 재생 큐에 전달하는 ROS 노드."""

    def __init__(self) -> None:
        super().__init__("speech_out")
        self.declare_parameter("tts_command", DEFAULT_TTS_COMMAND)
        executable = str(self.get_parameter("tts_command").value)
        self._speech_queue = SpeechQueue(
            play=lambda text: speak_with_espeak(text, executable),
            report=self._report_playback,
        )
        self.create_subscription(String, SAY_TOPIC, self._on_say, QOS_SAY)
        self.get_logger().info("speech_out ready (espeak-ng, FIFO)")

    def _on_say(self, message: String) -> None:
        """say 메시지를 큐에 넣고 실패하면 경고한다."""
        if not self._speech_queue.enqueue(message.data):
            self.get_logger().warning("TTS message skipped")

    def _report_playback(self, status: str) -> None:
        """재생 결과 또는 명시적 오류를 기록한다."""
        if status.startswith("TTS_FAILED") or status == "TTS_QUEUE_FULL":
            self.get_logger().error(status)
            return
        self.get_logger().info(status)

    def destroy_node(self) -> bool:
        """종료 전에 남은 문장의 FIFO 재생을 마친다."""
        self._speech_queue.close()
        return super().destroy_node()


def main(args=None) -> None:
    """speech_out 노드를 실행한다."""
    rclpy.init(args=args)
    node = SpeechOutNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
