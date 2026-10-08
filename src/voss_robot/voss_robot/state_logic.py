"""/voss/robot/state (voss_msgs/RobotState) 판정 — ROS import 없음. voss_msgs.md RobotState, #55 MC-019.

- connected = 두산 컨트롤러·RG2 Modbus 모두 연결 (pose 가 최근에 나오고 FAULT 가 아니며, RG2 상태를 읽음).
- error_code 우선순위: ESTOP > SAFETY_STOP > TIMEOUT(두산 응답 없음·FAULT·pose 끊김·연결 끊김) > GRIPPER_ERROR.
  비상정지 = state ERROR + error_code ESTOP. 컨트롤러 알람(예 1206 NOT REACHABLE)은 한 번 나는 이벤트라
  error_code 로 붙잡지 않고 detail 에 마지막 알람만 남긴다.
- state: error_code 가 있으면 ERROR, 동작 중(action ≠ "")이면 BUSY, stop 뒤 새 모션 전이면 STOPPED, 아니면 READY.
  sort_manager 는 READY·STOPPED + connected + error_code 없음을 준비로 본다(#96, 10/08 합의).
"""

from __future__ import annotations

from dataclasses import dataclass

# 두산 ROBOT_STATE (dsr_common2/include/DRFC.h)
CTRL_NAMES = {
    0: "INITIALIZING",
    1: "STANDBY",
    2: "MOVING",
    3: "SAFE_OFF",
    4: "TEACHING",
    5: "SAFE_STOP",
    6: "EMERGENCY_STOP",
    7: "HOMMING",
    8: "RECOVERY",
    9: "SAFE_STOP2",
    10: "SAFE_OFF2",
    15: "NOT_READY",
}
CTRL_ESTOP = {6}
CTRL_SAFETY = {3, 5, 9, 10}
CTRL_OK = {1, 2}  # STANDBY·MOVING 만 운전 가능으로 본다


@dataclass
class Inputs:
    dsr_ok: bool  # 두산 서비스 응답 정상(FAULT 아님) + pose 가 최근
    ctrl_state: int | None  # 최근 get_robot_state 값 (None = 아직 모름·오래됨)
    disconnected: bool  # /dsr01/robot_disconnection 을 받은 뒤 아직 회복 안 됨
    rg2_ok: bool  # RG2 상태를 최근에 읽음
    rg2_safety: bool  # RG2 safety_err
    servo_active: bool
    gripper_busy: bool
    zone_action: str = ""  # move_to_zone 중이면 "MOVE_TO_ZONE:B" 등 (다음 단계)
    stopped: bool = False  # /voss/robot/stop 뒤 아직 새 모션 명령 전
    last_alarm: str = ""  # 마지막 컨트롤러 알람 (detail 용)
    tcp_note: str = (
        ""  # 컨트롤러 TCP 등록이 voss_config 와 다를 때 (예 "TCP 등록 없음(플랜지 모드)")
    )


@dataclass(frozen=True)
class State:
    connected: bool
    state: str
    action: str
    error_code: str
    detail: str

    def key(self) -> tuple:
        """바뀌면 바로 발행할 항목 (detail 은 제외)."""
        return self.connected, self.state, self.action, self.error_code


def decide(i: Inputs) -> State:
    connected = i.dsr_ok and not i.disconnected and i.rg2_ok
    if i.ctrl_state in CTRL_ESTOP:
        err = "ESTOP"
    elif i.ctrl_state in CTRL_SAFETY:
        err = "SAFETY_STOP"
    elif (
        not i.dsr_ok or i.disconnected or (i.ctrl_state is not None and i.ctrl_state not in CTRL_OK)
    ):
        err = "TIMEOUT"  # 두산 쪽 응답·연결 문제 또는 운전 불가 상태
    elif not i.rg2_ok or i.rg2_safety:
        err = "GRIPPER_ERROR"
    else:
        err = ""
    action = (
        i.zone_action
        or ("SERVO" if i.servo_active else "")
        or ("GRIPPER" if i.gripper_busy else "")
    )
    if err:
        state = "ERROR"
    elif action:
        state = "BUSY"
    elif i.stopped:
        state = "STOPPED"
    else:
        state = "READY"
    parts = [
        f"controller {CTRL_NAMES.get(i.ctrl_state, i.ctrl_state) if i.ctrl_state is not None else '?'}"
    ]
    if not i.dsr_ok:
        parts.append("두산 응답 없음/pose 끊김")
    if i.disconnected:
        parts.append("robot_disconnection")
    if not i.rg2_ok:
        parts.append("RG2 읽기 실패")
    if i.rg2_safety:
        parts.append("RG2 safety_err")
    if i.tcp_note:
        parts.append(
            i.tcp_note
        )  # 펜던트 공간 제한이 핑거 끝을 못 막는 상태 — HMI·절차서에서 보이게(#121)
    if i.last_alarm:
        parts.append(f"마지막 알람 {i.last_alarm}")
    return State(connected, state, action, err, ", ".join(parts))
