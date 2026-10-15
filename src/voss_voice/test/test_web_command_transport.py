"""Web PC 음성/채팅에서 기존 명령 API로 보내는 형식과 실패 안내."""

from types import SimpleNamespace

from voss_voice.http_client import command_request
from voss_voice.intent_logic import ZoneMapView
from voss_voice.intent_parser import IntentParserNode
from voss_voice.transcript_flow import (
    SAY_COMMAND_UNCONFIRMED,
    CommandDeliveryError,
    TranscriptFlow,
)


def test_priority_and_recheck_use_existing_command_contract() -> None:
    priority = command_request({"type": "priority", "dong": "역삼동", "raw_text": "역삼동 먼저 분류해"})
    recheck = command_request({"type": "recheck", "raw_text": "재확인 시작"})
    assert priority == {"type": "priority", "args": {"dong": "역삼동"}, "raw_text": "역삼동 먼저 분류해"}
    assert recheck["args"] == {}


def test_delivery_failure_does_not_claim_command_was_accepted() -> None:
    spoken = []

    def fail(_intent):
        raise CommandDeliveryError("API unavailable")

    flow = TranscriptFlow(lambda *_: {"type": "priority", "dong": "역삼동"},
                          lambda _: None, fail, spoken.append)
    flow.view = ZoneMapView.from_entries([("역삼동", "A", [])])
    assert flow.handle("역삼동 먼저 분류해")[0] == "delivery_error"
    assert spoken == [SAY_COMMAND_UNCONFIRMED]


def test_web_sse_context_restores_zone_map_and_expires_question() -> None:
    flow = SimpleNamespace(view=None, state="", box_id="")
    node = SimpleNamespace(_flow=flow, _last_state_at=0.0, _last_spoken_question=None)
    IntentParserNode._on_web_context_event(node, "zone_map", (
        '{"version":"1","entries":[{"dong":"역삼동","zone":"A","aliases":["역삼"]}]}'
    ))
    IntentParserNode._on_web_context_event(node, "state", (
        '{"state":"ASKING","box_id":"box-009"}'
    ))
    assert flow.view.canonical_dong("역삼") == "역삼동"
    assert (flow.state, flow.box_id) == ("ASKING", "box-009")
    node._last_state_at -= 4.0
    IntentParserNode._expire_state(node)
    assert (flow.state, flow.box_id) == ("", "")


def test_web_sse_question_is_spoken_once_per_asking_entry() -> None:
    spoken = []
    flow = SimpleNamespace(view=None, state="", box_id="")
    node = SimpleNamespace(
        _flow=flow, _last_state_at=0.0, _last_spoken_question=None,
        _pub_say=SimpleNamespace(publish=lambda message: spoken.append(message.data)),
    )
    asking = ('{"state":"ASKING","session_id":"session-1","box_id":"box-016",'
              '"pending_question":"016번 박스 송장을 확인하지 못했습니다. 보류하려면 보류라고 말해 주세요."}')
    IntentParserNode._on_web_context_event(node, "state", asking)
    IntentParserNode._on_web_context_event(node, "state", asking)
    assert spoken == ["016번 박스 송장을 확인하지 못했습니다. 보류하려면 보류라고 말해 주세요."]

    IntentParserNode._on_web_context_event(node, "state", '{"state":"RUNNING","box_id":""}')
    IntentParserNode._on_web_context_event(node, "state", asking)
    assert len(spoken) == 2  # 정지·재개 뒤 같은 박스를 다시 물으면 다시 읽는다.
