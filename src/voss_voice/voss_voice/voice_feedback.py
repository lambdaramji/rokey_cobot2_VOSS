"""기존 전사 처리에 표시 이벤트만 추가한다. 초록은 전사 수락이며 로봇 완료가 아니다."""

import re
import threading
import uuid

from voss_voice.listen_logic import split_wake

SPOKEN_ACKS = frozenset(
    {
        "분류를시작하겠습니다",
        "요청을처리하겠습니다",
        "분류를재개하겠습니다",
        "보류로처리하겠습니다",
        "재확인을시작하겠습니다",
        "말씀하신순서로적재하겠습니다",
    }
)

# 안내문에 호출어를 넣지 않는다 — 스피커 소리가 마이크로 돌아와 호출어로 잡히는 것을 막는다 (10/15 로그).
TIMEOUT_SAY = "시간이 지났어요. 호출어를 다시 말해 주세요."
# 로봇이 움직이는 동안에는 안내를 말하지 않는다 — TTS 가 작업자의 "정지"와 겹치거나
# manager 안내를 speech_out FIFO 뒤로 미는 것을 막는다(박병후 #40 리뷰). 표시 이벤트는 그대로 보낸다.
ROBOT_BUSY_STATES = frozenset({"PICKING", "RECHECK", "PALLETIZING"})
TIMEOUT_SAY_MIN_INTERVAL_S = 30.0
OPERATING_DOMAIN_ID = "30"


def should_say_timeout(sort_state, now, last_said, min_interval_s=TIMEOUT_SAY_MIN_INTERVAL_S):
    """TIMED_OUT 안내를 스피커로 낼지. 로봇 동작 중이면 생략, 그 밖에도 min_interval_s 에 한 번."""
    if sort_state in ROBOT_BUSY_STATES:
        return False
    return last_said is None or now - last_said >= min_interval_s


def transcript_off_refused(publish_transcript, domain_id):
    """publish_transcript=false 는 표시등 격리 시험 전용. 운용 도메인에서는 음성 정지가 무효가 되므로 거부."""
    return not publish_transcript and (domain_id or "0").strip() == OPERATING_DOMAIN_ID


def is_timeout_prompt_echo(text):
    """TTS 안내가 마이크 STT에 돌아온 경우 다시 호출어로 받지 않는다."""
    return re.sub(r"[\W_]+", "", text).casefold() == re.sub(r"[\W_]+", "", TIMEOUT_SAY).casefold()


def is_ack_echo(text):
    """고정 안내 문장이 마이크에 다시 들어온 경우 명령으로 취급하지 않는다."""
    normalized = re.sub(r"[\W_]+", "", text).casefold()
    return normalized in SPOKEN_ACKS or (
        normalized.endswith(("을우선분류하겠습니다", "으로분류하겠습니다"))
        and not normalized.startswith(("헬로", "hello"))
    )


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
            if is_timeout_prompt_echo(text) or is_ack_echo(text):
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
