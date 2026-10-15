"""실제 로봇 없이 중복 stop 서비스 호출과 실패 뒤 재시도를 확인한다."""

from types import SimpleNamespace

from voss_manager.sort_manager import SortManagerNode


def test_overlapping_stop_uses_one_service_call_then_allows_retry() -> None:
    calls = []
    future = SimpleNamespace(add_done_callback=lambda callback: None)
    stop_cli = SimpleNamespace(
        service_is_ready=lambda: True,
        call_async=lambda request: calls.append(request) or future,
    )
    node = SimpleNamespace(
        stop_op=None,
        stop_cli=stop_cli,
        stop_timeout_s=3.0,
        _new_op=lambda kind, timeout: {"kind": kind, "token": len(calls) + 1},
        _on_stop_response=lambda *_: None,
    )

    SortManagerNode._call_stop(node)
    SortManagerNode._call_stop(node)
    assert len(calls) == 1

    node.stop_op = None  # 완료·실패·timeout 처리는 기존 콜백에서 이 값을 비운다.
    SortManagerNode._call_stop(node)
    assert len(calls) == 2
