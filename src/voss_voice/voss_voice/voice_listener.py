"""voice_listener — 마이크(또는 텍스트 입력) → /voss/voice/transcript (ADR-0007).

mode:=mic  : 내장 마이크 → 에너지 VAD 구간 → FastAPI /ai/stt(Whisper) → 호출어 확인 → 발행
mode:=text : 터미널 한 줄 = 발화 한 번 (시연장 소음 폴백, STT 없이 intent_parser 단독 시험)
mic 을 열 수 없으면(sounddevice 없음·장치 없음) text 로 자동 전환한다.
녹음 구간은 메모리에만 두고 파일로 저장하지 않는다(CLAUDE.md 규칙 8).
"""

from __future__ import annotations

import queue
import sys
import threading
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from voss_voice import http_client
from voss_voice.listen_logic import Segmenter, VadConfig, WakeGate, to_wav

QOS_EVENTS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


class VoiceListenerNode(Node):
    def __init__(self) -> None:
        super().__init__("voice_listener")
        p = self.declare_parameter
        p("mode", "mic")  # mic | text
        p("require_wake", True)  # mic 모드에서 호출어 요구 (false = 모든 구간 통과, 시험용)
        p("wake_window_s", 5.0)
        p("ai_base", http_client.AI_BASE)
        p("stt_timeout_s", 5.0)
        p("device", "")  # sounddevice 장치 이름·번호, "" = 기본
        p("vad_threshold_db", -40.0)
        p("end_silence_ms", 700)

        self._pub = self.create_publisher(String, "/voss/voice/transcript", QOS_EVENTS)
        self._stop = threading.Event()
        mode = self.get_parameter("mode").value
        require_wake = bool(self.get_parameter("require_wake").value)

        # 마이크 스레드가 시작되기 전에 게이트를 먼저 만든다
        self._gate = WakeGate(float(self.get_parameter("wake_window_s").value), require_wake)
        if mode == "mic" and self._start_mic():
            self.get_logger().info("voice_listener: mic 모드 — '헬로, 로키' 뒤에 말하세요")
        else:
            # 텍스트 폴백은 호출어 없이 받는다(사람이 직접 친 입력)
            self._gate = WakeGate(require_wake=False)
            threading.Thread(target=self._text_loop, daemon=True).start()
            self.get_logger().info("voice_listener: text 모드 — 한 줄 입력 = 발화 한 번")

    # ---------- 텍스트 폴백 ----------
    def _text_loop(self) -> None:
        for line in sys.stdin:
            if self._stop.is_set():
                break
            self._emit(line, time.monotonic(), source="text")

    # ---------- 마이크 ----------
    def _start_mic(self) -> bool:
        try:
            import sounddevice as sd  # noqa: PLC0415 — 마이크 모드에서만 필요
        except ImportError:
            self.get_logger().error("sounddevice 없음 → text 모드로 전환 (pip install sounddevice)")
            return False
        cfg = VadConfig(
            threshold_db=float(self.get_parameter("vad_threshold_db").value),
            end_silence_ms=int(self.get_parameter("end_silence_ms").value),
        )
        self._cfg = cfg
        self._seg = Segmenter(cfg)
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        dev = self.get_parameter("device").value or None
        try:
            self._stream = sd.InputStream(
                samplerate=cfg.sample_rate,
                channels=1,
                dtype="int16",
                device=dev,
                blocksize=cfg.sample_rate * cfg.frame_ms // 1000,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:  # noqa: BLE001 — 장치 오류 종류가 다양함
            self.get_logger().error(f"마이크 열기 실패({e}) → text 모드로 전환")
            return False
        threading.Thread(target=self._mic_loop, daemon=True).start()
        return True

    def _on_audio(self, indata, frames, t, status) -> None:  # sounddevice 콜백 스레드
        try:
            self._frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # 처리가 밀리면 오래된 소리는 버린다

    def _mic_loop(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self._frames.get(timeout=0.5)
            except queue.Empty:
                continue
            seg = self._seg.feed(frame)
            if seg is None:
                continue
            t0 = time.monotonic()
            resp = http_client.post_stt(
                to_wav(seg, self._cfg.sample_rate),
                base=self.get_parameter("ai_base").value,
                timeout_s=float(self.get_parameter("stt_timeout_s").value),
            )
            stt_ms = 1000 * (time.monotonic() - t0)
            if resp is None:
                self.get_logger().warn(f"STT 실패 ({stt_ms:.0f} ms)")
                continue
            self._emit(resp["text"], time.monotonic(), source=f"mic stt={stt_ms:.0f}ms")

    def _emit(self, text: str, now: float, source: str) -> None:
        out = self._gate.on_text(text, now)
        if out is None:
            if self._gate.armed:
                self.get_logger().info("호출어 감지 — 명령을 기다립니다")
            return
        self._pub.publish(String(data=out))
        self.get_logger().info(f"transcript [{source}]: {out}")

    def destroy_node(self) -> None:
        self._stop.set()
        stream = getattr(self, "_stream", None)
        if stream is not None:
            stream.stop()
            stream.close()
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceListenerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
