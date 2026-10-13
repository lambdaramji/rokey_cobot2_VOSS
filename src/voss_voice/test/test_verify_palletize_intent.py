"""팔레타이징 검증 (verify/palletizing) 4단계 — 음성 경로 입력 TR-PAL-01. LLM 을 부르지 않는다.

자연어 → route 는 LLM(FastAPI /ai/intent) 몫이라 여기서는 "LLM 이 들은 그대로 route 를 냈다"고 두고
intent_parser 의 허용 목록 검증(check_route)만 본다. 실제 LLM 정확도는 eval_real_intent.py --cases palletize (비용 — 사람이 실행).
"""

import json
import pathlib

import pytest
from voss_voice.intent_logic import SAY_ROUTE_DUP, SAY_ROUTE_UNKNOWN, ZoneMapView, decide

VIEW = ZoneMapView.from_entries(
    [("역삼동", "A", ["역삼"]), ("대치동", "B", ["대치"]), ("청담동", "C", ["청담"])]
)
FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "text,heard,want",
    [
        (
            "헬로 로키, 역삼 들렀다가 대치 거쳐서 청담으로 가",
            ["역삼", "대치", "청담"],
            ["역삼동", "대치동", "청담동"],
        ),
        (
            "대치, 역삼, 청담 순서로 실어줘",
            ["대치", "역삼", "청담"],
            ["대치동", "역삼동", "청담동"],
        ),
        ("역삼동이랑 청담동만 갈 거야", ["역삼동", "청담동"], ["역삼동", "청담동"]),
        ("삼성동 들렀다가 역삼으로 가", ["삼성동", "역삼"], SAY_ROUTE_UNKNOWN),
        ("역삼, 대치, 역삼", ["역삼", "대치", "역삼"], SAY_ROUTE_DUP),
    ],
)
def test_route_from_heard_names(text, heard, want) -> None:
    d = decide(
        {"type": "palletize", "dong": None, "zone": None, "route": heard}, text, VIEW, "RUNNING"
    )
    if isinstance(want, list):
        assert d.kind == "publish" and d.intent["type"] == "palletize" and d.intent["route"] == want
    else:
        assert d.kind == "say" and d.say == want


def test_palletize_cases_live_outside_nfr03_set() -> None:
    """정답 세트 위치 기록: NFR-03 20건(intent_cases.json)에는 palletize 가 없고 palletize_cases.json 에 따로 있다."""
    base = json.loads((FIX / "intent_cases.json").read_text(encoding="utf-8"))["cases"]
    assert not [c for c in base if c["expect"].get("type") == "palletize"]
    pal = json.loads((FIX / "palletize_cases.json").read_text(encoding="utf-8"))["cases"]
    assert len(pal) == 8
