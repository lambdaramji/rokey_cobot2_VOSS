"""두산 서비스 단일 호출 큐 (ROS·두산 import 없음).

두산 서비스를 여러 스레드가 동시에 부르면 dsr_controller2 가 응답을 멈추고 브링업 재시작 말고는
복구가 안 된다(전 프로젝트 실측, BRD 6.1). 그래서 모든 호출을 작업 스레드 하나가 차례로 실행한다.
- 일반 작업: 들어온 순서(FIFO)
- 정지 작업(priority=True): 대기 중인 일반 작업보다 먼저. 실행 중인 작업을 끊지는 못한다 —
  두산 move_stop 은 별도 callback group 이라 큐 밖에서 바로 부르는 경로를 gateway 가 따로 둔다.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any


class QueueClosed(RuntimeError):
    """닫힌 큐에 작업을 넣었거나, 대기 중이던 작업이 버려졌다."""


class SerialCallQueue:
    """작업 스레드 하나로 함수 호출을 직렬화한다. submit() 은 Future 를 돌려준다."""

    def __init__(self, name: str = "dsr_call_queue") -> None:
        self._cv = threading.Condition()  # 대기열 보호 + 작업 도착 알림
        self._normal: deque[tuple[Callable[[], Any], Future, float]] = deque()
        self._priority: deque[tuple[Callable[[], Any], Future, float]] = deque()
        self._closed = False
        self.last_wait_s = 0.0  # 마지막 작업의 큐 대기 시간 (로그용, MC-004)
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def submit(self, fn: Callable[[], Any], priority: bool = False) -> Future:
        """fn 을 큐에 넣는다. priority=True 면 대기 중인 일반 작업보다 먼저 실행."""
        fut: Future = Future()
        with self._cv:
            if self._closed:
                raise QueueClosed("큐가 닫혀 있다")
            (self._priority if priority else self._normal).append((fn, fut, time.monotonic()))
            self._cv.notify()
        return fut

    def pending(self) -> int:
        """아직 시작하지 않은 작업 수."""
        with self._cv:
            return len(self._normal) + len(self._priority)

    def drop_pending(self, reason: str = "dropped") -> int:
        """대기 중인 일반 작업을 모두 버린다(정지 때). 버린 Future 에는 QueueClosed 를 넣는다."""
        with self._cv:
            dropped = list(self._normal)
            self._normal.clear()
        for _fn, fut, _t in dropped:
            fut.set_exception(QueueClosed(reason))
        return len(dropped)

    def close(self, timeout: float = 2.0) -> None:
        """새 작업을 막고 대기 작업을 버린 뒤 작업 스레드를 끝낸다."""
        with self._cv:
            self._closed = True
            dropped = list(self._priority) + list(self._normal)
            self._priority.clear()
            self._normal.clear()
            self._cv.notify_all()
        for _fn, fut, _t in dropped:
            fut.set_exception(QueueClosed("closed"))
        self._thread.join(timeout)

    def _run(self) -> None:
        """작업 스레드: 우선 대기열 → 일반 대기열 순서로 하나씩 꺼내 실행."""
        while True:
            with self._cv:
                while not self._closed and not self._priority and not self._normal:
                    self._cv.wait()
                if self._closed:
                    return
                q = self._priority if self._priority else self._normal
                fn, fut, t_in = q.popleft()
            if not fut.set_running_or_notify_cancel():
                continue  # 호출자가 이미 취소했다
            self.last_wait_s = time.monotonic() - t_in
            try:
                fut.set_result(fn())
            except Exception as e:  # 예외는 호출자(Future)에게 그대로 넘긴다
                fut.set_exception(e)
