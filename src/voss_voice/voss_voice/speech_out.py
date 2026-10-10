"""speech_out: ROS 안내 메시지를 스피커로 출력한다.
입력: /voss/voice/say (std_msgs/String).
출력: FIFO 음성 재생 및 진단 로그.
근거: topics.md, SYS-FR-022, IC-VOICE-01.
"""

import time
from threading import Event, Thread

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String

from voss_voice.audio_player import play_pcm
from voss_voice.speech_queue import SpeechQueue
from voss_voice.tts_client import stream_tts_audio

SAY_TOPIC = "/voss/voice/say"
QUEUE_POLL_S = 0.2

SAY_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)


class SpeechOutNode(Node):
    """ROS 메시지는 큐에 넣고 워커에서 음성을 재생한다."""

    def __init__(self) -> None:
        super().__init__("speech_out")

        self._queue = SpeechQueue()
        self._stop_requested = Event()

        self._subscription = self.create_subscription(
            String,
            SAY_TOPIC,
            self._on_say,
            SAY_QOS,
        )

        self._worker = Thread(
            target=self._play_loop,
            name="tts_playback",
        )
        self._worker.start()

        self.get_logger().info("speech_out ready: OpenAI TTS")

    def _on_say(self, message: String) -> None:
        """받은 문장을 FIFO에 넣고 즉시 반환한다."""
        if not message.data.strip():
            return

        received_at_s = time.monotonic()

        if not self._queue.add(message.data, received_at_s):
            self.get_logger().warning("TTS_QUEUE_FULL")

    def _play_loop(self) -> None:
        """첫 문장을 재생 완료한 다음 문장을 처리한다."""
        while not self._stop_requested.is_set():
            request = self._queue.take(QUEUE_POLL_S)
            if request is None:
                continue

            self._play_one(
                request.text,
                request.received_at_s,
            )

    def _play_one(
        self,
        text: str,
        received_at_s: float,
    ) -> None:
        """TTS 요청과 완료·실패 시간을 기록한다."""
        started_at_s = time.monotonic()
        queue_ms = (started_at_s - received_at_s) * 1000

        self.get_logger().info(f"TTS_DISPATCH queue_ms={queue_ms:.0f}")

        def log_first_pcm_written() -> None:
            """첫 PCM 전달까지의 시간을 기록한다."""
            written_at_s = time.monotonic()

            receive_to_write_ms = (written_at_s - received_at_s) * 1000

            dispatch_to_write_ms = (written_at_s - started_at_s) * 1000

            self.get_logger().info(
                "TTS_FIRST_PCM_WRITTEN "
                f"receive_to_write_ms={receive_to_write_ms:.0f} "
                f"dispatch_to_write_ms={dispatch_to_write_ms:.0f}"
            )

        chunks = stream_tts_audio(text)

        try:
            byte_count = play_pcm(
                chunks,
                on_first_pcm_written=log_first_pcm_written,
            )
        except Exception as error:
            # 실패해도 다음 안내는 처리한다.
            self.get_logger().error(f"TTS_FAILED: {type(error).__name__}: {error}")
            return
        finally:
            chunks.close()

        elapsed_ms = (time.monotonic() - started_at_s) * 1000

        self.get_logger().info(f"TTS_FINISHED bytes={byte_count} elapsed_ms={elapsed_ms:.0f}")

    def close(self) -> None:
        """현재 재생 종료 후 워커를 정리한다."""
        self._stop_requested.set()
        self._worker.join()


def main(args=None) -> None:
    """ROS 노드를 시작하고 종료 시 자원을 정리한다."""
    rclpy.init(args=args)
    node = None

    try:
        node = SpeechOutNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()

        rclpy.shutdown()


if __name__ == "__main__":
    main()
