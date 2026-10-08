"""두산 dsr_controller2 서비스 어댑터. 이 패키지 밖에서 /dsr01 을 부르지 않는다(절대 규칙 3).

서비스 메서드는 SerialCallQueue 작업 스레드 안에서만 부른다(동시 호출 금지). 예외 둘:
speedl(토픽 발행이라 큐와 무관)과 move_stop_async(정지는 큐를 기다리지 않는다 — 큐 밖 별도 경로).
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


# move_stop stop_mode: DR_QSTOP (Quick stop, Stop Category 2) — ADR-0010 "Quick stop"
STOP_QSTOP = 1


class DryRunDoosan:
    """가짜 로봇: 주어진 플랜지 자세에서 시작해, speedl 선속도를 적분해 움직인다(자세는 그대로).

    실로봇처럼 스트림이 끊겨도 마지막 속도로 계속 간다(ADR-0010 실측) — gateway watchdog 시험용.
    """

    def __init__(self, flange_pose: Sequence[float]) -> None:
        self._pose = [float(v) for v in flange_pose]
        self._vel = [0.0, 0.0, 0.0]  # mm/s
        self._t = time.monotonic()
        self._lock = threading.Lock()
        self.stops = 0  # move_stop 호출 수 (시험용)

    def _advance(self) -> None:
        now = time.monotonic()
        dt, self._t = now - self._t, now
        for i in range(3):
            self._pose[i] += self._vel[i] * dt

    def get_flange_posx(self) -> list[float]:
        """현재 플랜지 posx (mm·deg). 실제처럼 아주 짧게 기다린다."""
        time.sleep(0.002)
        with self._lock:
            self._advance()
            return list(self._pose)

    def speedl(self, vel_mm_s: Sequence[float], acc: Sequence[float]) -> None:
        """speedl_stream 발행 대신: 선속도를 바로 바꾼다(가속 무시)."""
        with self._lock:
            self._advance()
            self._vel = [float(v) for v in vel_mm_s[:3]]

    def move_stop_async(self, done) -> None:
        """move_stop 대신: 바로 멈추고 done(ok, message) 를 부른다."""
        with self._lock:
            self._advance()
            self._vel = [0.0, 0.0, 0.0]
            self.stops += 1
        done(True, "OK")


class GuardedCaller:
    """서비스 호출 하나씩: 타임아웃 난 요청의 응답이 올 때까지 다음 요청을 보내지 않는다(ROS import 없음).

    rclpy 의 future.cancel() 은 클라이언트 쪽만 취소하고 컨트롤러에 간 요청은 그대로라, 타임아웃 뒤
    바로 다음 요청을 보내면 dsr_controller2 에 요청이 겹친다(#91 리뷰 박병후). 그래서 cancel 하지 않고
    늦은 응답을 기다린다. 응답 없음(TIMEOUT·BUSY)이 max_misses 번 이어지면 FAULT 로 두고 더 보내지
    않는다 — gateway 재시작으로만 푼다(RobotState ERROR 는 ⑤ 에서).
    """

    def __init__(self, timeout_s: float, max_misses: int = 3) -> None:
        self._timeout = timeout_s
        self._max_misses = max_misses
        self._late: threading.Event | None = None  # 타임아웃 난 요청의 응답 도착
        self._late_name = ""
        self.misses = 0  # 연속 응답 없음
        self.faulted = False

    def call(self, client, req):
        """client.call_async(req) 를 보내고 응답을 기다린다. 큐 작업 스레드에서만 부른다."""
        if self.faulted:
            raise DoosanError(f"FAULT: 응답 없음 {self.misses}회 연속 — gateway 재시작 필요")
        if self._late is not None:
            if not self._late.wait(self._timeout):
                self._miss()
                raise DoosanError(f"BUSY: 앞 요청 응답 대기 중({self._late_name}), 보내지 않음")
            self._late = None
        if not client.service_is_ready():
            raise DoosanError(f"서비스 없음: {client.srv_name}")
        done = threading.Event()
        fut = client.call_async(req)
        fut.add_done_callback(lambda _f: done.set())
        if not done.wait(self._timeout):
            self._late, self._late_name = done, client.srv_name  # cancel 하지 않는다
            self._miss()
            raise DoosanError(f"TIMEOUT {self._timeout:.2f}s: {client.srv_name}")
        self.misses = 0
        res = fut.result()
        if res is None or not getattr(res, "success", False):
            raise DoosanError(f"success=false: {client.srv_name}")
        return res

    def _miss(self) -> None:
        self.misses += 1
        if self.misses >= self._max_misses:
            self.faulted = True


class RosDoosan:
    """dsr_controller2 서비스 클라이언트. node 는 MultiThreadedExecutor 로 돌아야 응답을 받는다."""

    def __init__(
        self, node, prefix: str = DEFAULT_PREFIX, timeout_s: float = 0.5, max_misses: int = 3
    ) -> None:
        from dsr_msgs2.srv import GetCurrentToolFlangePosx  # 실기·에뮬레이터에서만 필요
        from rclpy.callback_groups import ReentrantCallbackGroup

        self.caller = GuardedCaller(timeout_s, max_misses)
        self._group = ReentrantCallbackGroup()  # 응답 콜백이 다른 실행 스레드에서 돌게
        self._flange_srv = GetCurrentToolFlangePosx
        self._flange = node.create_client(
            GetCurrentToolFlangePosx,
            prefix + "aux_control/get_current_tool_flange_posx",
            callback_group=self._group,
        )

        # speedl_stream: 토픽이라 서비스 큐를 쓰지 않는다. 컨트롤러 구독이 reliable depth 10 이라
        # best_effort 퍼블리셔는 연결되지 않는다(ADR-0010 조건 1)
        from dsr_msgs2.msg import SpeedlStream
        from dsr_msgs2.srv import MoveStop
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
        from rclpy.qos import QoSProfile, ReliabilityPolicy

        self._speedl_msg = SpeedlStream
        self._speedl_pub = node.create_publisher(
            SpeedlStream,
            prefix + "speedl_stream",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
        )
        # move_stop: 큐 밖 별도 경로(컨트롤러도 별도 callback group, dsr_controller2.cpp move_stop).
        # 큐에 걸린 pose 조회가 끝나길 기다리지 않고 바로 보낸다(CLAUDE.md voss_robot)
        self._stop_srv = MoveStop
        self._stop = node.create_client(
            MoveStop, prefix + "motion/move_stop", callback_group=MutuallyExclusiveCallbackGroup()
        )
        self._stop_timeout = timeout_s

    def wait_ready(self, timeout_s: float) -> bool:
        """서비스가 보일 때까지 기다린다(브링업 확인)."""
        ok = self._flange.wait_for_service(timeout_sec=timeout_s)
        return self._stop.wait_for_service(timeout_sec=timeout_s) and ok

    def speedl(self, vel_mm_s: Sequence[float], acc: Sequence[float]) -> None:
        """선속도(mm/s)만 있는 speedl. 각속도 0, time 0(acc 가 우선 — ADR-0010 조건 4)."""
        m = self._speedl_msg()
        m.vel = [float(v) for v in vel_mm_s[:3]] + [0.0, 0.0, 0.0]
        m.acc = [float(a) for a in acc]
        m.time = 0.0
        self._speedl_pub.publish(m)

    def move_stop_async(self, done) -> None:
        """Quick stop 을 큐 밖에서 보낸다. 결과는 done(ok, message) — OK / TIMEOUT / DEVICE_ERROR."""
        if not self._stop.service_is_ready():
            done(False, "DEVICE_ERROR")
            return
        req = self._stop_srv.Request()
        req.stop_mode = STOP_QSTOP
        state = {"done": False}
        lock = threading.Lock()

        def finish(ok: bool, msg: str) -> None:
            with lock:
                if state["done"]:
                    return
                state["done"] = True
            done(ok, msg)

        def on_done(f) -> None:
            r = f.result()
            ok = bool(r is not None and r.success)
            finish(ok, "OK" if ok else "DEVICE_ERROR")

        self._stop.call_async(req).add_done_callback(on_done)
        timer = threading.Timer(self._stop_timeout, lambda: finish(False, "TIMEOUT"))
        timer.daemon = True
        timer.start()

    def get_flange_posx(self) -> list[float]:
        """현재 플랜지 posx (Base, mm·deg). TCP 등록 여부와 상관없다."""
        req = self._flange_srv.Request()
        req.ref = 0  # DR_BASE
        return [float(v) for v in self.caller.call(self._flange, req).pos]
