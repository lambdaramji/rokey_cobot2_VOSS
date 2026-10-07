"""두산 dsr_controller2 서비스 어댑터. 이 패키지 밖에서 /dsr01 을 부르지 않는다(절대 규칙 3).

모든 메서드는 SerialCallQueue 작업 스레드 안에서만 부른다(동시 호출 금지).
- DryRunDoosan: 두산 없이 개인 PC 개발용. dsr_msgs2 를 import 하지 않는다.
- RosDoosan: 실제 서비스 호출. dsr_msgs2 는 생성할 때만 import 해서 드라이버가 없는 CI 에서도
  이 모듈을 import 할 수 있다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence

DEFAULT_PREFIX = "/dsr01/dsr_controller2/"  # doosan-robot2 31750d6, 10/07 실기 브링업에서 확인(#55)


class DoosanError(RuntimeError):
    """두산 서비스 실패(응답 없음·success=false·서비스 없음)."""


class DryRunDoosan:
    """가짜 로봇: 주어진 플랜지 자세에 멈춰 있다."""

    def __init__(self, flange_pose: Sequence[float]) -> None:
        self._pose = [float(v) for v in flange_pose]

    def get_flange_posx(self) -> list[float]:
        """현재 플랜지 posx (mm·deg). 실제처럼 아주 짧게 기다린다."""
        time.sleep(0.002)
        return list(self._pose)


class RosDoosan:
    """dsr_controller2 서비스 클라이언트. node 는 MultiThreadedExecutor 로 돌아야 응답을 받는다."""

    def __init__(self, node, prefix: str = DEFAULT_PREFIX, timeout_s: float = 0.5) -> None:
        from dsr_msgs2.srv import GetCurrentToolFlangePosx  # 실기·에뮬레이터에서만 필요
        from rclpy.callback_groups import ReentrantCallbackGroup

        self._timeout = timeout_s
        self._group = ReentrantCallbackGroup()  # 응답 콜백이 다른 실행 스레드에서 돌게
        self._flange_srv = GetCurrentToolFlangePosx
        self._flange = node.create_client(
            GetCurrentToolFlangePosx,
            prefix + "aux_control/get_current_tool_flange_posx",
            callback_group=self._group,
        )

    def wait_ready(self, timeout_s: float) -> bool:
        """서비스가 보일 때까지 기다린다(브링업 확인)."""
        return self._flange.wait_for_service(timeout_sec=timeout_s)

    def _call(self, client, req):
        """call_async 를 보내고 응답을 timeout 까지 기다린다. 큐 작업 스레드에서만 부른다."""
        if not client.service_is_ready():
            raise DoosanError(f"서비스 없음: {client.srv_name}")
        done = threading.Event()
        fut = client.call_async(req)
        fut.add_done_callback(lambda _f: done.set())
        if not done.wait(self._timeout):
            fut.cancel()
            raise DoosanError(f"TIMEOUT {self._timeout:.2f}s: {client.srv_name}")
        res = fut.result()
        if res is None or not getattr(res, "success", False):
            raise DoosanError(f"success=false: {client.srv_name}")
        return res

    def get_flange_posx(self) -> list[float]:
        """현재 플랜지 posx (Base, mm·deg). TCP 등록 여부와 상관없다."""
        req = self._flange_srv.Request()
        req.ref = 0  # DR_BASE
        return [float(v) for v in self._call(self._flange, req).pos]
