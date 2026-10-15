"""Web PC stop을 두 전송 경로에 순서대로 시도하는 순수 I/O 조합."""

from collections.abc import Callable


def attempt_stop(ros_send: Callable[[], None], web_send: Callable[[], bool]) -> tuple[bool, bool]:
    """ROS를 먼저 보내고, 어느 경로가 실패해도 다른 경로를 시도한다."""
    ros_sent = False
    web_accepted = False
    try:
        ros_send()
        ros_sent = True
    except Exception:  # noqa: BLE001 — 전송 경계: 웹 시도까지 막지 않는다.
        pass
    try:
        web_accepted = bool(web_send())
    except Exception:  # noqa: BLE001 — ROS 시도 결과는 유지한다.
        pass
    return ros_sent, web_accepted
