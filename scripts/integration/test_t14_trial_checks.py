"""T14 manager/TTS 로그 판정의 오탐을 막는다."""

from t14_trial_checks import (
    expected_history_say,
    first_pcm_latency_ms,
    manager_accepted_priority,
    tts_finished,
)


def test_manager_priority_requires_real_acceptance_log() -> None:
    """Intent 발행만 했거나 관리자가 거부한 경우에는 통과시키지 않는다."""
    assert not manager_accepted_priority("publish priority 역삼동")
    assert not manager_accepted_priority("intent priority → priority '역삼동': False")
    assert manager_accepted_priority("intent priority → priority '역삼동': True 우선 역삼동")


def test_first_pcm_latency_requires_speech_out_evidence() -> None:
    """실제 PCM 쓰기 로그만 지연 수치로 인정한다."""
    assert first_pcm_latency_ms("TTS_DISPATCH queue_ms=10") is None
    assert (
        first_pcm_latency_ms(
            "TTS_FIRST_PCM_WRITTEN receive_to_write_ms=712 dispatch_to_write_ms=700"
        )
        == 712
    )


def test_tts_only_passes_after_playback_finishes() -> None:
    """첫 PCM만 전달됐거나 재생 실패한 경우에는 통과시키지 않는다."""
    assert not tts_finished("TTS_FIRST_PCM_WRITTEN receive_to_write_ms=1500")
    assert not tts_finished("TTS_FAILED: TTSClientError")
    assert tts_finished("TTS_FINISHED bytes=68000 elapsed_ms=2700")


def test_history_without_session_only_accepts_no_session_response() -> None:
    """NO_SESSION은 폴백 안내만 통과로 인정한다."""
    assert expected_history_say("", ["기록을 조회할 수 없습니다."]) == "기록을 조회할 수 없습니다."
    assert expected_history_say("", ["보류는 0개입니다."]) is None


def test_history_with_session_requires_count_sentence() -> None:
    """세션이 있으면 집계 실패 안내로 통과시키지 않는다."""
    assert expected_history_say("20261011T121525-1ab9", ["기록을 조회할 수 없습니다."]) is None
    assert expected_history_say("20261011T121525-1ab9", ["보류는 3개입니다."]) == "보류는 3개입니다."


def test_history_without_session_information_cannot_pass() -> None:
    """세션 REST가 실패하면 응답이 있어도 성공으로 판정하지 않는다."""
    assert expected_history_say(None, ["보류는 3개입니다."]) is None
