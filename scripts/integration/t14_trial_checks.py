"""T14 실제 manager 및 TTS 선행시험 로그 판정 (ROS 없는 순수 함수)."""

import re

PRIORITY_LOG = "intent priority → priority '역삼동': True"
FIRST_PCM_PATTERN = re.compile(r"TTS_FIRST_PCM_WRITTEN receive_to_write_ms=(\d+)")
FINISHED_MARKER = "TTS_FINISHED bytes="


def manager_accepted_priority(log_text: str) -> bool:
    """관리자가 역삼동 우선순위 지시를 실제로 접수했는지 검사한다."""
    return PRIORITY_LOG in log_text


def first_pcm_latency_ms(log_text: str) -> int | None:
    """실제 speech_out 로그에서 첫 PCM 전달 지연(ms)을 반환한다."""
    match = FIRST_PCM_PATTERN.search(log_text)
    if match is None:
        return None
    return int(match.group(1))


def tts_finished(log_text: str) -> bool:
    """PCM 플레이어가 오류 없이 끝났는지 로그를 검사한다."""
    return FINISHED_MARKER in log_text


def expected_history_say(session_id: str | None, says: list[str]) -> str | None:
    """세션이 없으면 NO_SESSION만, 세션이 있으면 집계 안내만 인정한다."""
    if session_id == "":
        for sentence in says:
            if sentence == "기록을 조회할 수 없습니다.":
                return sentence
        return None
    if session_id:
        for sentence in says:
            if sentence.startswith("보류는 ") and sentence.endswith("개입니다."):
                return sentence
    return None

def history_scope(session_id: str) -> str:
    """현재 세션이 없으면 읽기 전용 전체 이력 조회 범위로 바꾼다."""
    if session_id == "":
        return "all"
    return session_id


def count_finished_playbacks(log_text: str) -> int:
    """이번 시험 speech_out 로그의 PCM 재생 완료 횟수를 반환한다."""
    return log_text.count(FINISHED_MARKER)


def last_pcm_latency_ms(log_text: str) -> int | None:
    """마지막 음성 재생의 첫 PCM 전달 지연을 반환한다."""
    matches = FIRST_PCM_PATTERN.findall(log_text)
    if not matches:
        return None
    return int(matches[-1])
