import json
from types import SimpleNamespace

from voss_voice.listen_logic import WakeGate
from voss_voice.voice_feedback import (
    TIMEOUT_SAY,
    VoiceFeedback,
    is_timeout_prompt_echo,
    should_say_timeout,
    transcript_off_refused,
)


def feedback():
    events = []
    return VoiceFeedback(WakeGate(), events.append), events


def test_wake_then_transcript_share_id():
    flow, events = feedback()
    assert flow.on_text("헬로 로키", 0) is None
    assert events[-1]["phase"] == "WAKE_DETECTED"
    assert flow.on_text("테스트입니다", 2) == "테스트입니다"
    assert events[-1]["phase"] == "COMMAND_ACCEPTED"
    assert events[0]["utterance_id"] == events[1]["utterance_id"]
    assert events[0]["event_id"] != events[1]["event_id"]


def test_combined_wake_and_command_emit_ordered_pair():
    flow, events = feedback()
    assert flow.on_text("헬로 로키 테스트입니다", 0) == "테스트입니다"
    assert [e["phase"] for e in events] == ["WAKE_DETECTED", "COMMAND_ACCEPTED"]


def test_timeout_without_more_audio_and_late_text_ignored():
    flow, events = feedback()
    flow.on_text("헬로 로키", 0)
    flow.expire(5.1)
    flow.expire(6)
    assert flow.on_text("테스트", 7) is None
    assert [e["phase"] for e in events] == ["WAKE_DETECTED", "TIMED_OUT"]
    assert not flow.gate.armed


def test_timeout_prompt_echo_does_not_rearm_wake():
    flow, events = feedback()
    flow.on_text("헬로 로키", 0)
    flow.expire(5.1)
    assert is_timeout_prompt_echo(TIMEOUT_SAY.replace("'", "“").replace("로키“", "로키”"))
    assert flow.on_text(TIMEOUT_SAY, 6) is None
    assert [e["phase"] for e in events] == ["WAKE_DETECTED", "TIMED_OUT"]
    assert not flow.gate.armed


def listener_node(sort_state=""):
    statuses, spoken = [], []
    node = SimpleNamespace(
        _status_pub=SimpleNamespace(publish=statuses.append),
        _say_pub=SimpleNamespace(publish=spoken.append),
        _sort_state=sort_state,
        _last_timeout_say=None,
        get_parameter=lambda name: SimpleNamespace(value=30.0),
    )
    return node, statuses, spoken


def test_listener_says_once_for_timeout_event():
    from voss_voice.voice_listener import VoiceListenerNode

    node, statuses, spoken = listener_node()
    flow = VoiceFeedback(
        WakeGate(), lambda payload: VoiceListenerNode._publish_status(node, payload)
    )
    flow.on_text("헬로 로키", 0)
    flow.expire(5.1)
    flow.expire(6)
    assert len(statuses) == 2
    assert [message.data for message in spoken] == [TIMEOUT_SAY]


def test_listener_skips_timeout_speech_while_robot_moves():
    from voss_voice.voice_listener import VoiceListenerNode

    node, statuses, spoken = listener_node("PICKING")
    flow = VoiceFeedback(
        WakeGate(), lambda payload: VoiceListenerNode._publish_status(node, payload)
    )
    flow.on_text("헬로 로키", 0)
    flow.expire(5.1)
    assert [json.loads(m.data)["phase"] for m in statuses] == ["WAKE_DETECTED", "TIMED_OUT"]
    assert spoken == []


def test_timeout_speech_gate():
    assert should_say_timeout("RUNNING", 100.0, None)
    assert not should_say_timeout("RECHECK", 100.0, None)
    assert not should_say_timeout("PALLETIZING", 100.0, None)
    assert not should_say_timeout("IDLE", 100.0, 80.0)
    assert should_say_timeout("IDLE", 110.0, 80.0)


def test_transcript_off_refused_only_on_operating_domain():
    assert transcript_off_refused(False, "30")
    assert transcript_off_refused(False, " 30 ")
    assert not transcript_off_refused(False, "179")
    assert not transcript_off_refused(False, None)
    assert not transcript_off_refused(True, "30")


def test_empty_stt_keeps_waiting_like_wake_gate():
    flow, events = feedback()
    flow.on_text("헬로 로키", 0)
    assert flow.on_text("", 1) is None
    assert flow.gate.armed
    assert flow.on_text("테스트", 2) == "테스트"
    assert [e["phase"] for e in events] == ["WAKE_DETECTED", "COMMAND_ACCEPTED"]


def test_stt_call_failure_after_wake_fails_and_disarms():
    flow, events = feedback()
    flow.on_text("헬로 로키", 0)
    flow.fail(1)
    assert events[-1]["phase"] == "RECOGNITION_FAILED"
    assert flow.on_text("테스트", 2) is None


def test_stt_error_without_wake_is_not_a_command_failure():
    flow, events = feedback()
    flow.fail(0)
    flow.on_text("주변 대화", 1)
    assert events == []


def test_repeated_wake_starts_new_attempt():
    flow, events = feedback()
    flow.on_text("헬로 로키", 0)
    flow.on_text("헬로 로키", 4)
    assert events[0]["utterance_id"] != events[1]["utterance_id"]
    flow.expire(6)
    assert len(events) == 2


def test_stop_still_bypasses_wake():
    flow, events = feedback()
    assert flow.on_text("멈춰", 0) == "멈춰"
    assert events == []
