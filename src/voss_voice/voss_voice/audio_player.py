
"""audio_player: PCM 음성을 Linux 스피커로 출력한다.
입력: 24kHz 16-bit PCM 바이트 조각.
출력: 스피커 재생 및 전송 바이트 수.
근거: docs/interfaces/web_api.md, SYS-FR-022.
"""

import subprocess
from collections.abc import Callable, Iterable

PLAY_TIMEOUT_S = 30.0

APLAY_COMMAND = [
    "aplay",
    "-q",
    "-t", "raw",
    "-f", "S16_LE",
    "-r", "24000",
    "-c", "1",
]


def play_pcm(
    chunks: Iterable[bytes],
    on_first_pcm_written: Callable[[], None] | None = None,
) -> int:
    """PCM을 순차 재생하고 전달한 바이트 수를 반환한다."""
    player = subprocess.Popen(
        APLAY_COMMAND,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    received_bytes = 0

    try:
        if player.stdin is None:
            raise RuntimeError("Audio stdin unavailable")

        first_write_reported = False

        for chunk in chunks:
            if not chunk:
                continue

            player.stdin.write(chunk)
            received_bytes += len(chunk)

            if not first_write_reported:
                first_write_reported = True

                if on_first_pcm_written is not None:
                    on_first_pcm_written()

        player.stdin.close()
        player.stdin = None

        _, error_output = player.communicate(
            timeout=PLAY_TIMEOUT_S
        )

        if player.returncode != 0:
            message = error_output.decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(f"aplay failed: {message}")

        if received_bytes == 0:
            raise RuntimeError("TTS returned empty PCM")

        return received_bytes

    except Exception:
        # 오류가 나면 오디오 프로세스를 남기지 않는다.
        if player.poll() is None:
            player.kill()

        player.communicate()
        raise
