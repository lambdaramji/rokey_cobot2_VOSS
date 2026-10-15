"""Web PC 음성/채팅에서 기존 명령 API로 보내는 형식과 실패 안내."""

import http.client
import threading
from types import SimpleNamespace

import pytest
from voss_voice.command_delivery import attempt_stop
from voss_voice.http_client import command_request
from voss_voice.intent_logic import ZoneMapView
from voss_voice.intent_parser import IntentParserNode
from voss_voice.transcript_flow import (
    SAY_COMMAND_UNCONFIRMED,
    CommandDeliveryError,
    TranscriptFlow,
)


def test_priority_and_recheck_use_existing_command_contract() -> None:
    priority = command_request(
        {"type": "priority", "dong": "역삼동", "raw_text": "역삼동 먼저 분류해"}
    )
    recheck = command_request({"type": "recheck", "raw_text": "재확인 시작"})
    assert priority == {
        "type": "priority",
        "args": {"dong": "역삼동"},
        "raw_text": "역삼동 먼저 분류해",
    }
    assert recheck["args"] == {}


def test_stop_attempts_ros_before_web_even_if_web_fails() -> None:
    calls = []
    assert attempt_stop(lambda: calls.append("ros"), lambda: calls.append("web") or False) == (
        True,
        False,
    )
    assert calls == ["ros", "web"]


def test_stop_attempts_web_after_ros_exception() -> None:
    calls = []

    def fail_ros():
        calls.append("ros")
        raise RuntimeError("DDS unavailable")

    assert attempt_stop(fail_ros, lambda: calls.append("web") or True) == (False, True)
    assert calls == ["ros", "web"]


def test_web_timeout_after_ros_stop_does_not_claim_acceptance(monkeypatch) -> None:
    sent = []
    node = SimpleNamespace(
        _command_transport="web_api",
        _api_base="http://127.0.0.1:8080",
        _publish_ros=lambda fields: sent.append(fields["type"]),
        get_logger=lambda: SimpleNamespace(error=lambda *_: None),
    )

    def timeout(*_args, **_kwargs):
        raise TimeoutError("web unavailable")

    monkeypatch.setattr("voss_voice.intent_parser.http_client.post_command", timeout)
    with pytest.raises(CommandDeliveryError):
        IntentParserNode._publish(node, {"type": "stop"})
    assert sent == ["stop"]


def test_non_stop_web_transport_does_not_publish_ros(monkeypatch) -> None:
    sent = []
    node = SimpleNamespace(
        _command_transport="web_api",
        _api_base="http://127.0.0.1:8080",
        _publish_ros=lambda fields: sent.append(("ros", fields["type"])),
    )
    monkeypatch.setattr(
        "voss_voice.intent_parser.http_client.post_command",
        lambda fields, **_: sent.append(("web", fields["type"])) or True,
    )
    IntentParserNode._publish(node, {"type": "start"})
    assert sent == [("web", "start")]


def test_delivery_failure_does_not_claim_command_was_accepted() -> None:
    spoken = []

    def fail(_intent):
        raise CommandDeliveryError("API unavailable")

    flow = TranscriptFlow(
        lambda *_: {"type": "priority", "dong": "역삼동"}, lambda _: None, fail, spoken.append
    )
    flow.view = ZoneMapView.from_entries([("역삼동", "A", [])])
    assert flow.handle("역삼동 먼저 분류해")[0] == "delivery_error"
    assert spoken == [SAY_COMMAND_UNCONFIRMED]


def test_web_sse_context_restores_zone_map_and_expires_question() -> None:
    flow = SimpleNamespace(view=None, state="", box_id="")
    node = SimpleNamespace(_flow=flow, _last_state_at=0.0, _last_spoken_question=None)
    IntentParserNode._on_web_context_event(
        node,
        "zone_map",
        ('{"version":"1","entries":[{"dong":"역삼동","zone":"A","aliases":["역삼"]}]}'),
    )
    IntentParserNode._on_web_context_event(node, "state", ('{"state":"ASKING","box_id":"box-009"}'))
    assert flow.view.canonical_dong("역삼") == "역삼동"
    assert (flow.state, flow.box_id) == ("ASKING", "box-009")
    node._last_state_at -= 4.0
    IntentParserNode._expire_state(node)
    assert (flow.state, flow.box_id) == ("", "")


def test_web_sse_question_is_spoken_once_per_asking_entry() -> None:
    spoken = []
    flow = SimpleNamespace(view=None, state="", box_id="")
    node = SimpleNamespace(
        _flow=flow,
        _last_state_at=0.0,
        _last_spoken_question=None,
        _pub_say=SimpleNamespace(publish=lambda message: spoken.append(message.data)),
    )
    asking = (
        '{"state":"ASKING","session_id":"session-1","box_id":"box-016",'
        '"pending_question":"016번 박스 송장을 확인하지 못했습니다. 보류하려면 보류라고 말해 주세요."}'
    )
    IntentParserNode._on_web_context_event(node, "state", asking)
    IntentParserNode._on_web_context_event(node, "state", asking)
    assert spoken == ["016번 박스 송장을 확인하지 못했습니다. 보류하려면 보류라고 말해 주세요."]

    IntentParserNode._on_web_context_event(node, "state", '{"state":"RUNNING","box_id":""}')
    IntentParserNode._on_web_context_event(node, "state", asking)
    assert len(spoken) == 2  # 정지·재개 뒤 같은 박스를 다시 물으면 다시 읽는다.


def test_web_sse_reconnects_after_incomplete_read(monkeypatch) -> None:
    flow = SimpleNamespace(view=None, state="", box_id="")
    stopped = threading.Event()
    warnings, seen, opens = [], [], []
    node = SimpleNamespace(
        _flow=flow,
        _api_base="http://127.0.0.1:8080",
        _context_stop=stopped,
        _last_state_at=0.0,
        _last_spoken_question=None,
        _pub_say=SimpleNamespace(publish=lambda _: None),
        get_logger=lambda: SimpleNamespace(warn=warnings.append),
    )
    node._invalidate_web_context = lambda: IntentParserNode._invalidate_web_context(node)

    def on_event(event, data):
        IntentParserNode._on_web_context_event(node, event, data)
        if event == "state" and flow.state == "ASKING":
            seen.append(flow.box_id)
            if len(seen) == 2:
                stopped.set()

    node._on_web_context_event = on_event

    class Stream:
        def __init__(self, first):
            self.first = first

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            if self.first:
                yield b"event: state\n"
                yield b'data: {"state":"ASKING","box_id":"box-1"}\n\n'
                yield b"\n"
                raise http.client.IncompleteRead(b"partial")
            yield b"event: zone_map\n"
            yield b"data: malformed\n"
            yield b"\n"
            yield b"event: state\n"
            yield b'data: {"state":"ASKING","box_id":"box-2"}\n'
            yield b"\n"

    def open_stream(*_args, **_kwargs):
        opens.append(flow.state)
        return Stream(len(opens) == 1)

    monkeypatch.setattr(
        "voss_voice.intent_parser.urllib.request.build_opener",
        lambda *_: SimpleNamespace(open=open_stream),
    )
    IntentParserNode._stream_web_context(node)
    assert seen == ["box-1", "box-2"]
    assert opens == ["", ""]  # 단절된 첫 질문은 재접속 전에 무효화
    assert flow.state == ""
    assert any("IncompleteRead" in warning for warning in warnings)


def test_web_disconnect_preserves_ros_context() -> None:
    flow = SimpleNamespace(view=object(), state="ASKING", box_id="box-ros")
    node = SimpleNamespace(_flow=flow, _state_source="ros", _zone_map_source="ros")
    IntentParserNode._invalidate_web_context(node)
    assert flow.state == "ASKING" and flow.box_id == "box-ros"
    assert flow.view is not None


def test_web_disconnect_restores_last_ros_zone_map() -> None:
    ros_view = object()
    flow = SimpleNamespace(view=object(), state="", box_id="")
    node = SimpleNamespace(_flow=flow, _zone_map_source="web", _ros_view=ros_view)
    IntentParserNode._invalidate_web_context(node)
    assert flow.view is ros_view
