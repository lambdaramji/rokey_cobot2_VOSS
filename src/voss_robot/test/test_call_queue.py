"""call_queue.py 시험: 직렬 실행·우선 작업·예외 전달·정지 때 대기 작업 버리기."""

import threading
import time

import pytest
from voss_robot.call_queue import QueueClosed, SerialCallQueue


@pytest.fixture
def q():
    queue = SerialCallQueue()
    yield queue
    queue.close()


def test_runs_one_at_a_time_in_order(q):
    running, overlap, order = [0], [False], []
    lock = threading.Lock()

    def job(i):
        def fn():
            with lock:
                running[0] += 1
                overlap[0] |= running[0] > 1  # 두 작업이 겹치면 실패
            time.sleep(0.01)
            order.append(i)
            with lock:
                running[0] -= 1
            return i

        return fn

    futs = [q.submit(job(i)) for i in range(5)]
    assert [f.result(timeout=2) for f in futs] == list(range(5))
    assert order == list(range(5))
    assert not overlap[0]


def test_priority_runs_before_waiting_jobs(q):
    gate, started, order = threading.Event(), threading.Event(), []
    first = q.submit(lambda: (started.set(), gate.wait(2)))  # 작업 스레드를 잡아 둔다
    assert started.wait(2)
    normal = q.submit(lambda: order.append("normal"))
    stop = q.submit(lambda: order.append("stop"), priority=True)
    gate.set()
    for f in (first, normal, stop):
        f.result(timeout=2)
    assert order == ["stop", "normal"]


def test_exception_goes_to_caller(q):
    def boom():
        raise RuntimeError("dsr timeout")

    with pytest.raises(RuntimeError, match="dsr timeout"):
        q.submit(boom).result(timeout=2)
    assert q.submit(lambda: 1).result(timeout=2) == 1  # 예외 뒤에도 큐는 계속 돈다


def test_drop_pending_keeps_priority(q):
    gate, started = threading.Event(), threading.Event()
    q.submit(lambda: (started.set(), gate.wait(2)))
    assert started.wait(2)  # 첫 작업이 실행 중이어야 나머지 3개만 대기열에 있다
    waiting = [q.submit(lambda: "move") for _ in range(3)]
    stop = q.submit(lambda: "stop", priority=True)
    assert q.drop_pending("stopped") == 3
    gate.set()
    assert stop.result(timeout=2) == "stop"
    for f in waiting:
        with pytest.raises(QueueClosed):
            f.result(timeout=2)


def test_submit_after_close():
    queue = SerialCallQueue()
    queue.close()
    with pytest.raises(QueueClosed):
        queue.submit(lambda: 1)
