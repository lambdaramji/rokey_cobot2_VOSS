"""실제 스피커 없이 PCM 전달과 재생 오류를 검증한다."""

import pytest

from voss_voice import audio_player


class FakeInput:
    """aplay 표준입력의 테스트 대역이다."""

    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, chunk: bytes) -> int:
        self.data.extend(chunk)
        return len(chunk)

    def close(self) -> None:
        pass


class FakeProcess:
    """aplay 프로세스의 테스트 대역이다."""

    def __init__(self, returncode: int = 0) -> None:
        self.stdin = FakeInput()
        self.returncode = returncode

    def communicate(self, timeout=None):
        return b"", b"audio failure"

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_pcm_chunks_are_sent_to_audio_player(monkeypatch) -> None:
    """PCM 조각이 순서대로 스피커 프로세스에 전달된다."""
    player = FakeProcess()

    # 재생이 끝나면 player.stdin은 None이 되므로
    # 테스트에서는 입력 스트림을 미리 보관한다.
    audio_input = player.stdin

    def fake_popen(command, **kwargs):
        assert command == audio_player.APLAY_COMMAND
        return player

    monkeypatch.setattr(
        audio_player.subprocess,
        "Popen",
        fake_popen,
    )

    sent_bytes = audio_player.play_pcm([b"\x01\x00", b"\x02\x00"])

    assert sent_bytes == 4
    assert bytes(audio_input.data) == b"\x01\x00\x02\x00"


def test_audio_player_reports_failed_process(monkeypatch) -> None:
    """재생기가 실패하면 오류를 보고한다."""
    player = FakeProcess(returncode=1)

    monkeypatch.setattr(
        audio_player.subprocess,
        "Popen",
        lambda command, **kwargs: player,
    )

    with pytest.raises(RuntimeError, match="aplay failed"):
        audio_player.play_pcm([b"\x01\x00"])


def test_first_pcm_callback_runs_once_after_first_write(monkeypatch) -> None:
    """첫 PCM 전달 이후 콜백이 한 번만 실행되는지 확인한다."""
    player = FakeProcess()
    audio_input = player.stdin
    observed_data: list[bytes] = []

    def record_first_write() -> None:
        """콜백 호출 시점에 전달된 PCM을 보관한다."""
        observed_data.append(bytes(audio_input.data))

    def fake_popen(command, **kwargs):
        return player

    monkeypatch.setattr(
        audio_player.subprocess,
        "Popen",
        fake_popen,
    )

    audio_player.play_pcm(
        [b"\x01\x00", b"\x02\x00"],
        on_first_pcm_written=record_first_write,
    )

    assert observed_data == [b"\x01\x00"]
