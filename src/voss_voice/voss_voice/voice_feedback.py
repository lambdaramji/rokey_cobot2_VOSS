"""기존 전사 처리에 표시 이벤트만 추가한다. 초록은 전사 수락이며 로봇 완료가 아니다."""

import re
import threading
import uuid

from voss_voice.listen_logic import split_wake

TIMEOUT_SAY = "시간이 지났어요. 다시 '헬로 로키'라고 말해 주세요."


def is_timeout_prompt_echo(text):
    """TTS 안내가 마이크 STT에 돌아온 경우 다시 호출어로 받지 않는다."""
    return re.sub(r"[\W_]+", "", text).casefold() == re.sub(r"[\W_]+", "", TIMEOUT_SAY).casefold()


class VoiceFeedback:
    def __init__(self, gate, publish):
        self.gate = gate
        self.publish = publish
        self.lock = threading.RLock()
        self.active_id = ""
        self.deadline = 0.0

    def _send(self, phase):
        self.publish(
            {"phase": phase, "event_id": str(uuid.uuid4()), "utterance_id": self.active_id}
        )

    def _begin(self, now):
        self.active_id = str(uuid.uuid4())
        self.deadline = now + self.gate.window_s
        self._send("WAKE_DETECTED")

    def expire(self, now):
        """추가 음성이 없어도 호출 대기 종료를 한 번 발행한다."""
        with self.lock:
            if self.active_id and now > self.deadline:
                self._send("TIMED_OUT")
                self.active_id = ""
                self.gate.cancel()

    def fail(self, now):
        """호출 대기 중 발생한 STT 실패만 표시하고 게이트를 닫는다."""
        with self.lock:
            self.expire(now)
            if self.active_id:
                self._send("RECOGNITION_FAILED")
                self.active_id = ""
                self.gate.cancel()

    def on_text(self, text, now):
        """기존 WakeGate 결과를 그대로 반환하고 실제 호출어에만 표시 이벤트를 붙인다."""
        with self.lock:
            self.expire(now)
            if is_timeout_prompt_echo(text):
                return None
            if not text.strip():
                # 잡음 구간의 빈 STT: 기존 WakeGate 처럼 무시하고 호출 대기를 유지한다
                # (벨트·로봇 소음 뒤에 오는 명령을 버리지 않게). 실패 표시는 STT 호출 실패(fail)만.
                return None
            woke, _ = split_wake(text)
            output = self.gate.on_text(text, now)
            if woke:
                self._begin(now)
            if output and self.active_id:
                self._send("COMMAND_ACCEPTED")
                self.active_id = ""
            return output
