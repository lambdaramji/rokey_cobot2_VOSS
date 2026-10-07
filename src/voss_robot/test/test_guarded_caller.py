"""doosan.GuardedCaller 시험: 타임아웃 난 요청의 응답 전에는 다음 요청을 보내지 않는다(#91 리뷰)."""

import threading
import time
from types import SimpleNamespace

import pytest
from voss_robot.doosan import DoosanError, GuardedCaller


class FakeFuture:
    def __init__(self) -> None:
        self._cbs, self._res = [], None

    def add_done_callback(self, cb) -> None:
        self._cbs.append(cb)

    def result(self):
        return self._res

    def finish(self, res) -> None:
        self._res = res
        for cb in self._cbs:
            cb(self)


class FakeClient:
    """응답 지연(delay_s)을 흉내 내고, 컨트롤러 쪽 동시 진행 요청 수를 센다."""

    srv_name = "/dsr01/fake"

    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.in_flight = 0
        self.max_in_flight = 0
        self.sent = 0
        self._lock = threading.Lock()

    def service_is_ready(self) -> bool:
        return True

    def call_async(self, _req):
        fut = FakeFuture()
        with self._lock:
            self.sent += 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)

        def respond():
            time.sleep(self.delay_s)
            with self._lock:
                self.in_flight -= 1
            fut.finish(SimpleNamespace(success=True))

        threading.Thread(target=respond, daemon=True).start()
        return fut


def test_ok_call_returns_response():
    caller = GuardedCaller(timeout_s=0.2)
    assert caller.call(FakeClient(0.01), None).success
    assert caller.misses == 0


def test_no_overlap_after_timeout():
    # 리뷰 재현 조건: 첫 응답 200 ms, 타임아웃 50 ms → 예전 코드는 컨트롤러 쪽 요청이 2개 겹쳤다
    client, caller = FakeClient(0.2), GuardedCaller(timeout_s=0.05, max_misses=10)
    for _ in range(6):
        try:
            caller.call(client, None)
        except DoosanError:
            pass
    assert client.max_in_flight == 1


def test_late_response_unblocks_next_call():
    client, caller = FakeClient(0.08), GuardedCaller(timeout_s=0.05)
    with pytest.raises(DoosanError, match="TIMEOUT"):
        caller.call(client, None)
    client.delay_s = 0.0
    assert caller.call(client, None).success  # 늦은 응답(80 ms)이 대기 50 ms 안에 와서 보낸다
    assert caller.misses == 0


def test_busy_does_not_send():
    client, caller = FakeClient(0.5), GuardedCaller(timeout_s=0.05, max_misses=10)
    with pytest.raises(DoosanError, match="TIMEOUT"):
        caller.call(client, None)
    with pytest.raises(DoosanError, match="BUSY"):
        caller.call(client, None)
    assert client.sent == 1


def test_fault_after_consecutive_misses():
    client, caller = FakeClient(1.0), GuardedCaller(timeout_s=0.03, max_misses=3)
    for _ in range(3):
        with pytest.raises(DoosanError):
            caller.call(client, None)
    assert caller.faulted
    with pytest.raises(DoosanError, match="FAULT"):
        caller.call(client, None)
    assert client.sent == 1


def test_success_false_raises():
    client = FakeClient(0.0)
    client.call_async = lambda _r: _done(SimpleNamespace(success=False))
    with pytest.raises(DoosanError, match="success=false"):
        GuardedCaller(timeout_s=0.1).call(client, None)


def _done(res):
    fut = FakeFuture()
    fut._res = res
    fut.add_done_callback = lambda cb: cb(fut)
    return fut
