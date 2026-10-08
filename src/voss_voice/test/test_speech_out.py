"""speech_out의 ROS 독립 FIFO·예외 처리를 검증한다.
실제 오디오 출력과 3초 지연 실측은 별도 수행한다.
관련 문서: SYS-FR-022, docs/interfaces/topics.md.
"""

import threading

from voss_voice.speech_out import SpeechQueue


def test_empty_speech_is_rejected():
    """빈 메시지를 큐에 넣지 않는다."""
    played = []
    speech_queue = SpeechQueue(played.append, lambda status: None)
    assert not speech_queue.enqueue(" ")
    speech_queue.close()
    assert played == []


def test_speech_is_played_in_fifo_order():
    """두 메시지가 입력 순서대로 재생된다."""
    played = []
    speech_queue = SpeechQueue(played.append, lambda status: None)
    assert speech_queue.enqueue("첫 문장")
    assert speech_queue.enqueue("두 번째 문장")
    speech_queue.close()
    assert played == ["첫 문장", "두 번째 문장"]


def test_playback_error_does_not_discard_following_speech():
    """첫 재생 실패 뒤 다음 메시지도 처리한다."""
    played = []
    reports = []

    def play(text: str) -> None:
        """첫 메시지만 실패시킨다."""
        if text == "실패":
            raise OSError("speaker unavailable")
        played.append(text)

    speech_queue = SpeechQueue(play, reports.append)
    assert speech_queue.enqueue("실패")
    assert speech_queue.enqueue("정상")
    speech_queue.close()
    assert played == ["정상"]
    assert any(status.startswith("TTS_FAILED") for status in reports)


def test_full_queue_rejects_new_speech():
    """재생 중 큐 포화 시 새 메시지를 거절한다."""
    started = threading.Event()
    release = threading.Event()
    played = []
    reports = []

    def play(text: str) -> None:
        """큐를 채울 수 있도록 재생을 대기시킨다."""
        started.set()
        release.wait(timeout=2.0)
        played.append(text)

    speech_queue = SpeechQueue(play, reports.append, capacity=1)
    assert speech_queue.enqueue("첫 번째")
    assert started.wait(timeout=2.0)
    assert speech_queue.enqueue("두 번째")
    assert not speech_queue.enqueue("세 번째")
    release.set()
    speech_queue.close()
    assert played == ["첫 번째", "두 번째"]
    assert "TTS_QUEUE_FULL" in reports
