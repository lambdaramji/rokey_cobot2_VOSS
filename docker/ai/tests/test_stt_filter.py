"""Whisper 프롬프트 메아리와 실제 짧은 명령 구분."""

from app.stt_filter import is_prompt_echo


def test_default_prompt_echo_is_removed() -> None:
    prompt = "헬로우 로키. 헬로 로키. 역삼동, 대치동, 청담동."
    assert is_prompt_echo(prompt, prompt)
    assert is_prompt_echo("헬로우 로키 헬로 로키 역삼동 대치동 청담동", prompt)


def test_short_commands_and_empty_prompt_are_preserved() -> None:
    prompt = "헬로우 로키. 헬로 로키. 역삼동, 대치동, 청담동."
    for text in ("정지", "멈춰", "헬로 로키", "역삼동"):
        assert not is_prompt_echo(text, prompt)
    assert not is_prompt_echo("정지", "")
    assert not is_prompt_echo("정지", "정지")


def test_old_long_prompt_echo_is_removed_without_short_stop_loss() -> None:
    prompt = "헬로우 로키. 역삼동 대치동 청담동. 박스 분류 보류 일시 정지 시작 재개."
    assert is_prompt_echo(prompt.replace("일시 정지", "정지"), prompt)
    assert not is_prompt_echo("정지", prompt)
