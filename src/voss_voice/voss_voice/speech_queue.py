"""speech_queue: 안내 문장을 도착 순서대로 보관한다.
입력: ROS에서 받은 문장과 수신 시각.
출력: FIFO 순서의 SpeechRequest.
근거: docs/interfaces/topics.md, MC-025.
"""

from dataclasses import dataclass
from queue import Empty, Full, Queue

QUEUE_LIMIT = 20


@dataclass(frozen=True)
class SpeechRequest:
    """재생할 문장과 수신 시각을 보관한다."""

    text: str
    received_at_s: float


class SpeechQueue:
    """ROS에 의존하지 않는 FIFO 음성 대기열이다."""

    def __init__(self, limit: int = QUEUE_LIMIT) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")

        self._queue: Queue[SpeechRequest] = Queue(maxsize=limit)

    def add(self, text: str, received_at_s: float) -> bool:
        """유효한 문장을 큐에 넣고 성공 여부를 반환한다."""
        cleaned_text = text.strip()
        if not cleaned_text:
            return False

        try:
            self._queue.put_nowait(SpeechRequest(cleaned_text, received_at_s))
        except Full:
            return False

        return True

    def take(self, timeout_s: float) -> SpeechRequest | None:
        """가장 먼저 들어온 문장을 꺼내고 없으면 None을 반환한다."""
        try:
            return self._queue.get(timeout=timeout_s)
        except Empty:
            return None
