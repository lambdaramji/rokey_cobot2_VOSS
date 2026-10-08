"""voice_listener 의 순수 로직 (ROS·마이크·HTTP 의존 없음, pytest 대상). ADR-0007.

- VAD: 에너지(dBFS) 기준으로 말소리 구간만 잘라 STT 로 보낸다. 구간은 메모리에만 두고 저장하지 않는다.
- 호출어: STT 문자열 앞부분에서 "헬로 로키" 계열을 찾는다. 뒤에 명령이 붙어 있으면 그 명령을,
  호출어만 있으면 다음 구간(window_s 안)을 명령으로 본다.
- 정지 키워드("멈춰" 등)는 호출어 없이도 통과시킨다(안전, intent_json.md stop 예외).
"""

from __future__ import annotations

import io
import math
import queue
import re
import wave
from dataclasses import dataclass

import numpy as np

from voss_voice.intent_logic import is_stop

# 공백·문장부호를 뺀 소문자 기준. Whisper 가 한글·영문 어느 쪽으로 적어도 잡는다.
_WAKE_RE = re.compile(
    r"(?:헬로우?|헤로|할로|핼로|hello|helo)(?:로키|록키|로끼|rokey|rocky|roky)"
)
_PUNCT = re.compile(r"[\s\.,!?~·\-]+")


def split_wake(text: str) -> tuple[bool, str]:
    """(호출어 있음, 뒤에 붙은 명령). 호출어는 문장 맨 앞(앞쪽 군더더기 "어", "음" 허용)만 인정."""
    # 문장부호·공백을 뺀 글자와 원문 위치를 함께 들고 다닌다
    kept = [(ch, i) for i, ch in enumerate(text.lower()) if not _PUNCT.fullmatch(ch)]
    squashed = "".join(ch for ch, _ in kept)
    filler = re.match(r"(?:어+|음+|저기)?", squashed).end()
    m = _WAKE_RE.match(squashed, filler)
    if not m or m.end() == filler:
        return False, ""
    end_in_text = kept[m.end() - 1][1] + 1
    return True, _PUNCT.sub(" ", text[end_in_text:]).strip()


class WakeGate:
    """STT 결과 → 발행할 transcript (없으면 None)."""

    def __init__(self, window_s: float = 5.0, require_wake: bool = True) -> None:
        self.window_s = window_s
        self.require_wake = require_wake
        self._armed_until = -math.inf

    @property
    def armed(self) -> bool:
        return self._armed_until > -math.inf

    def on_text(self, text: str, now: float) -> str | None:
        text = text.strip()
        if not text:
            return None
        if is_stop(text):  # 안전: 호출어 없이도
            self._armed_until = -math.inf
            return text
        if not self.require_wake:
            return text
        woke, cmd = split_wake(text)
        if woke:
            if cmd:
                self._armed_until = -math.inf
                return cmd
            self._armed_until = now + self.window_s  # "헬로 로키" 만 → 다음 말을 기다림
            return None
        if now <= self._armed_until:
            self._armed_until = -math.inf
            return text
        self._armed_until = -math.inf
        return None


def dbfs(frame: np.ndarray) -> float:
    """int16 프레임의 RMS(dBFS). 무음이면 -inf."""
    if frame.size == 0:
        return -math.inf
    rms = math.sqrt(float(np.mean(frame.astype(np.float64) ** 2)))
    return -math.inf if rms == 0 else 20 * math.log10(rms / 32768.0)


@dataclass
class VadConfig:
    sample_rate: int = 16000
    frame_ms: int = 30
    threshold_db: float = -40.0  # 1 m 내장 마이크 실측(measurements #10)으로 조정
    min_speech_ms: int = 300  # 이보다 짧은 소리는 버림 (클릭·기침)
    end_silence_ms: int = 700  # 이만큼 조용하면 구간 끝
    max_segment_s: float = 8.0  # 이보다 길면 강제로 끊음
    pre_roll_ms: int = 200  # 말 시작 직전 소리 포함


class Segmenter:
    """프레임(int16)을 넣으면 말소리 구간(int16 배열)을 돌려준다."""

    def __init__(self, cfg: VadConfig | None = None) -> None:
        self.cfg = cfg or VadConfig()
        self._pre: list[np.ndarray] = []
        self._buf: list[np.ndarray] = []
        self._speech_ms = 0
        self._silence_ms = 0

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        c = self.cfg
        loud = dbfs(frame) >= c.threshold_db
        if not self._buf:
            if loud:
                self._buf = [*self._pre, frame]
                self._speech_ms, self._silence_ms = c.frame_ms, 0
                self._pre = []
            else:
                self._pre.append(frame)
                keep = max(1, c.pre_roll_ms // c.frame_ms)
                self._pre = self._pre[-keep:]
            return None
        self._buf.append(frame)
        if loud:
            self._speech_ms += c.frame_ms
            self._silence_ms = 0
        else:
            self._silence_ms += c.frame_ms
        total_s = len(self._buf) * c.frame_ms / 1000
        if self._silence_ms >= c.end_silence_ms or total_s >= c.max_segment_s:
            seg, speech = np.concatenate(self._buf), self._speech_ms
            self._buf, self._speech_ms, self._silence_ms = [], 0, 0
            return seg if speech >= c.min_speech_ms else None
        return None


def to_wav(pcm: np.ndarray, sample_rate: int = 16000) -> bytes:
    """int16 mono → WAV bytes (메모리, 파일로 저장하지 않음)."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.astype("<i2").tobytes())
    return out.getvalue()


def put_drop_oldest(q: queue.Queue, item) -> bool:
    """큐가 차 있으면 **가장 오래된** 항목을 버리고 새 항목을 넣는다. 버렸으면 True.

    STT 를 기다리는 동안 큐가 차도 그 뒤에 한 말("멈춰")은 남긴다(#72 리뷰).
    """
    try:
        q.put_nowait(item)
        return False
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:  # 다른 스레드가 그사이 채운 경우 — 이번 것은 버린다
            pass
        return True
