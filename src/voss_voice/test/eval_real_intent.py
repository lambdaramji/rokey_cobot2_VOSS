"""T09 실제 Intent 평가 스크립트.
입력: intent_cases.json의 20개 발화 (--cases palletize 면 palletize_cases.json 8개, S2-T06)
출력: Intent 정답 여부와 처리 시간
계약: docs/interfaces/intent_json.md
"""

import argparse
import json
from pathlib import Path

from voss_voice.http_client import post_intent
from voss_voice.intent_logic import ZoneMapView
from voss_voice.transcript_flow import TranscriptFlow

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "intent_cases.json"
PALLETIZE_PATH = Path(__file__).parent / "fixtures" / "palletize_cases.json"


def load_cases(path: Path = FIXTURE_PATH) -> list[dict]:
    """정답 JSON에서 테스트 케이스 목록을 읽어 반환한다."""
    fixture_text = path.read_text()
    return json.loads(fixture_text)["cases"]


def create_test_flow() -> tuple[TranscriptFlow, list[dict], list[dict], list[str]]:
    """실제 LLM과 가짜 ROS·DB 출력을 연결한 평가 객체를 만든다."""
    published_intents = []
    stats_queries = []
    spoken_texts = []

    zone_map = ZoneMapView.from_entries(
        [
            ("역삼동", "A", ["역삼"]),
            ("대치동", "B", ["대치"]),
            ("청담동", "C", ["청담"]),
        ]
    )

    def fake_get_stats(query: dict) -> dict:
        """조회 조건을 기록하고 가짜 DB 결과를 반환한다."""
        stats_queries.append(query.copy())
        return {"ok": True, "count": 0}

    flow = TranscriptFlow(
        post_intent=post_intent,
        get_stats=fake_get_stats,
        publish=published_intents.append,
        say=spoken_texts.append,
    )

    flow.view = zone_map

    return flow, published_intents, stats_queries, spoken_texts


def evaluate_case(test_case: dict) -> tuple[bool, str, float]:
    """한 문장을 실행하고 정답 여부, 상세 결과, 처리 시간을 반환한다."""
    flow, published_intents, stats_queries, spoken_texts = create_test_flow()

    # 발화 당시 로봇 상태를 시험 데이터로 설정한다.
    flow.state = test_case.get("state", "")
    flow.box_id = test_case.get("box_id", "")

    expected = test_case["expect"]

    # 실제 GPT-4o를 호출한다. stop은 로컬에서 즉시 처리한다.
    result_kind, elapsed_ms = flow.handle(test_case["text"])

    # stop은 handle()이 "stop"을 반환하지만
    # 정답 파일에서는 발행 동작인 "publish"로 표기한다.
    if result_kind == "stop":
        result_kind = "publish"

    if result_kind != expected["kind"]:
        return False, f"kind 불일치: {result_kind}", elapsed_ms

    # 거부 정답(palletize 중복·미등록·4개 이상): 되묻기만 하고 아무것도 발행하지 않아야 한다
    if result_kind == "say":
        if published_intents:
            return False, "거부해야 하는데 Intent 를 발행함", elapsed_ms
        return True, f"거부: {spoken_texts[-1] if spoken_texts else ''}", elapsed_ms

    if result_kind == "publish":
        if len(published_intents) != 1:
            return False, "Intent 발행 건수 불일치", elapsed_ms

        actual = published_intents[0]
        fields_to_check = ("type", "dong", "zone", "box_id", "route")

    elif result_kind == "query":
        if len(stats_queries) != 1:
            return False, "DB 조회 요청 건수 불일치", elapsed_ms

        actual = stats_queries[0]
        fields_to_check = ("query_kind", "dong")

    else:
        return False, f"예상하지 못한 결과: {result_kind}", elapsed_ms

    # 정답 파일에 정의된 필드만 비교한다.
    for field_name in fields_to_check:
        if field_name not in expected:
            continue

        actual_value = actual.get(field_name)
        expected_value = expected[field_name]

        if actual_value != expected_value:
            return (
                False,
                f"{field_name} 불일치: 실제={actual_value}, 기대={expected_value}",
                elapsed_ms,
            )

    return True, "일치", elapsed_ms


EXPECTED_CASE_COUNT = 20
MIN_CORRECT_CASES = 19


def main() -> None:
    """전체 20문장을 평가하고 정확도와 최종 판정을 출력한다. --cases palletize 는 8문장 전부 맞아야 PASS."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", choices=("intent", "palletize"), default="intent")
    palletize = ap.parse_args().cases == "palletize"
    test_cases = load_cases(PALLETIZE_PATH if palletize else FIXTURE_PATH)

    total_count = len(test_cases)
    passed_count = 0

    expected_count = 8 if palletize else EXPECTED_CASE_COUNT
    if total_count != expected_count:
        raise ValueError(f"테스트 문장 수 오류: {total_count}개")

    for test_case in test_cases:
        passed, detail, elapsed_ms = evaluate_case(test_case)

        if passed:
            passed_count += 1

        status = "PASS" if passed else "FAIL"

        print(
            f"{test_case['id']}: {status} | {detail} | {elapsed_ms:.0f}ms",
            flush=True,
        )

    failed_count = total_count - passed_count
    accuracy = passed_count / total_count * 100

    print("\n========== T09 평가 결과 ==========")
    print(f"전체: {total_count}건")
    print(f"성공: {passed_count}건")
    print(f"실패: {failed_count}건")
    print(f"정확도: {accuracy:.1f}%")

    if passed_count >= (
        total_count if palletize else MIN_CORRECT_CASES
    ):  # palletize: 받기 5/5·거부 100%
        print("판정: PASS")
    else:
        print("판정: FAIL")


if __name__ == "__main__":
    main()
