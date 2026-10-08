"""준비 판단 ROBOT/SERVO/VISION/OCR/LOG (ROS 없음, pytest 대상). SRD v1.0 §5.7, voss_msgs.md SortState.

노드가 나이(초)·존재 여부를 모아 넘기고, 여기서 not_ready 목록을 만든다.
- ROBOT: RobotState 를 한 번이라도 받았으면 RobotState 기준(나이 ≤ 1.5 s + connected + READY/STOPPED + 오류 없음),
  아직이면 과도 규칙(`/voss/robot/pose` 0.5 s 이내 + `/voss/robot/move_to_zone` 서비스 있음).
- SERVO: `/voss/servo/track_and_grasp` 액션 서버 있음.
- VISION·OCR: `/voss/vision/box`·`/voss/vision/label` 발행자가 있음. BoxTrack 은 박스가 없으면 나오지 않으므로
  메시지 나이로는 "박스 없음" 과 "비전 장애" 를 가를 수 없다 → 지금은 발행자 존재만 본다(한계, 아래 상태 신호 필요).
- LOG: `/voss/log/status` 가 3 s 안에 왔고 STARTING 이 아님. DB_ERROR·SPOOL_FULL 은 경고만(운전 비차단, MC-027).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ITEMS = ("ROBOT", "SERVO", "VISION", "OCR", "LOG")


@dataclass(frozen=True)
class ReadyInputs:
    pose_age_s: float = math.inf  # 마지막 /voss/robot/pose 수신 후 지난 시간
    move_srv: bool = False  # /voss/robot/move_to_zone 서비스 있음
    robot_state_age_s: float = math.inf  # 마지막 RobotState 수신 후, 한 번도 없으면 inf
    robot_connected: bool = False
    robot_state: str = ""
    robot_error: str = ""
    servo_server: bool = False
    vision_pubs: int = 0
    ocr_pubs: int = 0
    log_age_s: float = math.inf
    log_status: str = ""


@dataclass(frozen=True)
class ReadyLimits:
    pose_max_age_s: float = 0.5
    robot_state_max_age_s: float = 1.5  # 2 Hz 주기의 3배 (남현지 F-05 제안)
    log_max_age_s: float = 3.0


DEFAULT_LIMITS = ReadyLimits()


def not_ready(inp: ReadyInputs, lim: ReadyLimits = DEFAULT_LIMITS) -> list[str]:
    out = []
    if math.isfinite(inp.robot_state_age_s):
        ok = (
            inp.robot_state_age_s <= lim.robot_state_max_age_s
            and inp.robot_connected
            and inp.robot_state in ("READY", "STOPPED")
            and not inp.robot_error
        )
    else:
        ok = inp.pose_age_s <= lim.pose_max_age_s and inp.move_srv
    if not ok:
        out.append("ROBOT")
    if not inp.servo_server:
        out.append("SERVO")
    if inp.vision_pubs < 1:
        out.append("VISION")
    if inp.ocr_pubs < 1:
        out.append("OCR")
    if inp.log_age_s > lim.log_max_age_s or inp.log_status in ("", "STARTING"):
        out.append("LOG")
    return out


def log_warning(status: str) -> str:
    """운전 중 경고만 하는 로그 상태. 정상이면 ""."""
    return status if status in ("DB_ERROR", "SPOOL_FULL") else ""
