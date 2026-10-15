"""Whisper initial_prompt의 전체 재출력만 걸러내는 순수 판정."""

from difflib import SequenceMatcher


def is_prompt_echo(text: str, prompt: str) -> bool:
    """짧은 명령은 보존하고, 프롬프트 길이에 가까운 메아리만 버린다."""
    heard = "".join(ch.casefold() for ch in text if ch.isalnum())
    seed = "".join(ch.casefold() for ch in prompt if ch.isalnum())
    return (
        len(seed) >= 8
        and len(heard) >= min(20, len(seed))
        and SequenceMatcher(None, heard, seed).ratio() >= 0.82
    )
