"""speech_out의 FIFO와 큐 오류를 ROS 없이 검증한다."""

import pytest
from voss_voice.speech_queue import SpeechQueue


def test_messages_are_taken_in_arrival_order() -> None:
    """안내 문장이 도착 순서대로 나온다."""
    queue = SpeechQueue(limit=2)

    assert queue.add("첫 번째", 1.0)
    assert queue.add("두 번째", 2.0)

    assert queue.take(0.0).text == "첫 번째"
    assert queue.take(0.0).text == "두 번째"


def test_empty_message_is_ignored() -> None:
    """빈 문장은 재생 큐에 넣지 않는다."""
    queue = SpeechQueue()

    assert not queue.add("  ", 1.0)
    assert queue.take(0.0) is None


def test_full_queue_preserves_existing_message() -> None:
    """큐가 가득 차면 기존 순서를 유지한다."""
    queue = SpeechQueue(limit=1)

    assert queue.add("기존 안내", 1.0)
    assert not queue.add("새 안내", 2.0)
    assert queue.take(0.0).text == "기존 안내"


def test_invalid_queue_limit_is_rejected() -> None:
    """잘못된 큐 크기는 초기화 단계에서 거부한다."""
    with pytest.raises(ValueError):
        SpeechQueue(limit=0)
