"""listen_logic 단위 시험: 호출어 분리, WakeGate, 에너지 VAD, WAV (마이크·ROS 없이)."""

import io
import queue
import wave

import numpy as np
import pytest
from voss_voice.listen_logic import (
    Segmenter,
    VadConfig,
    WakeGate,
    dbfs,
    put_drop_oldest,
    split_wake,
    to_wav,
)


@pytest.mark.parametrize(
    "text,cmd",
    [
        ("헬로, 로키. 작업 시작", "작업 시작"),
        ("헬로우 로키 역삼동부터 분류해", "역삼동부터 분류해"),
        ("Hello, Rokey. 대치동 먼저", "대치동 먼저"),
        ("hello rocky 몇 개 남았어?", "몇 개 남았어"),
        ("어 헬로 로키 다시 시작", "다시 시작"),
        ("헬로 로키", ""),
        ("헬로 로키야, 작업 시작해", "작업 시작해"),
        ("헬로우 로키야 역삼동부터", "역삼동부터"),
    ],
)
def test_split_wake_found(text, cmd):
    assert split_wake(text) == (True, cmd)


@pytest.mark.parametrize(
    "text",
    [
        "로키",
        "로키야",
        "로키야 작업 시작해",
        "로키 작업 시작해",
    ],
)
def test_legacy_wake_is_rejected(text: str) -> None:
    """옛 호출어로는 일반 명령을 전달하지 않는다."""
    assert WakeGate().on_text(text, 0.0) is None


@pytest.mark.parametrize(
    "text", ["작업 시작", "역삼동부터 분류해 헬로 로키", "헬로", "블로키 작업", ""]
)
def test_split_wake_not_found(text):
    assert split_wake(text)[0] is False


def test_gate_wake_with_command():
    g = WakeGate()
    assert g.on_text("헬로 로키, 작업 시작", 0.0) == "작업 시작"


def test_gate_wake_then_next_utterance_within_window():
    g = WakeGate(window_s=5.0)
    assert g.on_text("헬로 로키", 0.0) is None and g.armed
    assert g.on_text("역삼동부터 분류해", 3.0) == "역삼동부터 분류해"
    assert not g.armed


def test_gate_window_expires():
    g = WakeGate(window_s=5.0)
    g.on_text("헬로 로키", 0.0)
    assert g.on_text("역삼동부터 분류해", 6.0) is None


def test_gate_ignores_speech_without_wake():
    g = WakeGate()
    assert g.on_text("오늘 점심 뭐 먹지", 0.0) is None
    assert g.on_text("작업 시작", 1.0) is None


@pytest.mark.parametrize("text", ["멈춰", "잠깐 정지!", "스톱"])
def test_gate_stop_without_wake(text):
    assert WakeGate().on_text(text, 0.0) == text


def test_gate_without_wake_requirement_passes_everything():
    assert WakeGate(require_wake=False).on_text("작업 시작", 0.0) == "작업 시작"


# --- VAD ---
CFG = VadConfig(
    sample_rate=16000, frame_ms=30, threshold_db=-40, min_speech_ms=300, end_silence_ms=300
)
N = 16000 * 30 // 1000  # 480 샘플/프레임


def _tone(db: float) -> np.ndarray:
    amp = 32768 * 10 ** (db / 20) * np.sqrt(2)
    t = np.arange(N) / 16000
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.int16)


SILENCE = np.zeros(N, dtype=np.int16)


def test_dbfs():
    assert dbfs(SILENCE) == float("-inf")
    assert abs(dbfs(_tone(-20)) + 20) < 0.5


def _run(frames):
    seg = Segmenter(CFG)
    out = [s for f in frames if (s := seg.feed(f)) is not None]
    return out


def test_segment_emitted_after_silence():
    out = _run([SILENCE] * 5 + [_tone(-20)] * 20 + [SILENCE] * 15)
    assert len(out) == 1
    # 말 20프레임 + 앞 여유(pre-roll) + 끝 무음 일부
    assert 20 * N <= len(out[0]) <= (20 + 7 + 10) * N


def test_short_click_is_dropped():
    assert _run([SILENCE] * 5 + [_tone(-20)] * 3 + [SILENCE] * 15) == []


def test_quiet_noise_is_not_speech():
    assert _run([_tone(-55)] * 40) == []


def test_long_speech_is_cut_at_max():
    cfg = VadConfig(frame_ms=30, threshold_db=-40, max_segment_s=1.0)
    seg = Segmenter(cfg)
    out = [s for _ in range(100) if (s := seg.feed(_tone(-20))) is not None]
    assert len(out) >= 2


def test_to_wav_roundtrip():
    pcm = _tone(-20)
    with wave.open(io.BytesIO(to_wav(pcm, 16000))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (
            1,
            2,
            16000,
            N,
        )


def test_full_queue_drops_oldest_keeps_newest():
    q = queue.Queue(maxsize=3)
    assert [put_drop_oldest(q, i) for i in range(3)] == [False, False, False]
    assert put_drop_oldest(q, "멈춰") is True
    assert [q.get_nowait() for _ in range(3)] == [1, 2, "멈춰"]
