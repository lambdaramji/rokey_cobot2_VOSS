"""그리퍼 호출 한 건의 생애와 x 여유 계산 (순수 모듈 — ROS 를 import 하지 않는다).

- 호출은 기다리지 않는다: 노드가 call_async 로 보내고 틱마다 poll() 로 들여다본다(진동벨).
- 응답 message 는 콜론 앞 코드로 읽는다: "INVALID: width" → INVALID (gateway rg2.py 형식).
- FSM(judge_grip) 에는 원문이 아니라 코드를 넘긴다 → cause 가 GRIPPER_<코드> 로 깔끔하다.
- 계약: src/voss_msgs/srv/Gripper.srv, docs/interfaces/voss_msgs.md Gripper 행.
- 설계: src/voss_servo/design/U5-dd.md 1절, U5-pseudo.md 1·2절.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from voss_servo import fsm

# --- 호출 종류 (FSM 행동과 1:1) ---
OPEN = "OPEN"  # 사전 개방 (PREPARE)
CLOSE = "CLOSE"  # 닫기 (GRASP)
VERIFY = "VERIFY"  # 확인 = 닫기 한 번 더 (VERIFY, HLD D1)
ACTION_KIND = {fsm.GRIPPER_OPEN: OPEN, fsm.GRIPPER_CLOSE: CLOSE, fsm.GRIPPER_VERIFY: VERIFY}

# --- 응답 코드 ---
CODES = ("OK", "TIMEOUT", "INVALID", "BUSY", "COMM_ERROR")  # Gripper.srv message 계약
UNKNOWN = "UNKNOWN"  # 계약 밖 message
UNAVAILABLE = "UNAVAILABLE"  # 요청 순간 서비스가 없음 (belt_servo 가 만든다)

# --- BUSY 재요청 (HLD D3, DD E1) ---
BUSY_RETRY_MAX = 1  # 재요청 횟수
BUSY_RETRY_DELAY_S = 0.5  # BUSY 뒤 재요청까지 기다림 (판단값 — 33 ms 뒤면 RG2 가 아직 바쁘다)

# --- poll 결과 / 로그 state ---
PENDING = "PENDING"  # 아직 응답 없음
REPLY = "REPLY"  # 응답 받음 (판정은 FSM)
BUSY_WAIT = "BUSY_WAIT"  # BUSY 받음 → 재요청 기다리는 중
RETRY = "RETRY"  # 지금 재요청할 때
TIMED_OUT = "TIMED_OUT"  # 기다림 한계 넘음


@dataclass(frozen=True)
class GripCall:
    """그리퍼 호출 한 건 = 이름표(goal·시도·종류·순번) + 보낸 값."""

    goal_id: str  # goal UUID 16진수
    attempt: int  # 보낼 때의 파지 시도 번호 (OPEN 은 0)
    kind: str  # OPEN | CLOSE | VERIFY
    seq: int  # 이 goal 안의 그리퍼 요청 순번 (1부터, BUSY 재요청도 +1)
    width_mm: float  # 보낸 폭
    force_n: float  # 보낸 힘
    sent_s: float  # 보낸 시각 (노드 시계)
    busy_retries: int = 0  # BUSY 로 다시 보낸 횟수
    busy_at: float | None = None  # BUSY 받은 시각 (재요청 기다리는 중이면 값이 있다)


@dataclass(frozen=True)
class RawReply:
    """Gripper 응답을 ROS 없이 옮긴 것."""

    ok: bool
    width_mm: float  # RG2 보고 폭
    grip_detected: bool  # RG2 물체 감지 비트
    message: str  # 원문 ("INVALID: …" 처럼 이유가 붙을 수 있다)


@dataclass(frozen=True)
class PollResult:
    """poll() 의 결과."""

    status: str  # PENDING | REPLY | BUSY_WAIT | RETRY | TIMED_OUT
    reply: fsm.GripperReply | None = None  # REPLY·TIMED_OUT 때만 (message = 코드)
    code: str = ""  # 응답 코드
    raw_message: str = ""  # 원문 (로그용)


def request_for(action: str, pre_open_mm: float, grasp_width_mm: float) -> tuple[str, float]:
    """FSM 행동 → (종류, 보낼 폭). VERIFY 도 닫기 폭으로 보낸다 (HLD D1)."""
    kind = ACTION_KIND.get(action)  # 모르는 행동이면 None
    if kind is None:
        raise ValueError(f"모르는 그리퍼 행동: {action}")
    width = pre_open_mm if kind == OPEN else grasp_width_mm  # 개방만 넓게
    return kind, width


def message_code(message: str) -> str:
    """응답 message → 코드. 콜론 앞만 보고, 계약에 없으면 UNKNOWN."""
    head = message.split(":", 1)[0].strip().upper()  # "INVALID: width" → "INVALID"
    return head if head in CODES else UNKNOWN  # "" 도 UNKNOWN


def new_call(
    goal_id: str, attempt: int, kind: str, width_mm: float, force_n: float, seq: int, now: float
) -> GripCall:
    """새 호출 기록."""
    return GripCall(goal_id, attempt, kind, seq, width_mm, force_n, sent_s=now)


def busy_marked(call: GripCall, now: float) -> GripCall:
    """BUSY 를 받았다 → 재요청 기다리기 시작."""
    return replace(call, busy_at=now)


def retried(call: GripCall, now: float) -> GripCall:
    """BUSY 재요청 = 새 요청: 순번·재요청 횟수 +1, 보낸 시각 새로 (기다림 한계도 새로, DD E1)."""
    return replace(
        call, seq=call.seq + 1, busy_retries=call.busy_retries + 1, sent_s=now, busy_at=None
    )


def poll(
    call: GripCall,
    done: bool,
    raw: RawReply | None,
    failed: bool,
    now: float,
    timeout_s: float,
) -> PollResult:
    """호출 한 건을 들여다본다. 노드가 future 상태(done·raw·failed)를 ROS 없이 넘긴다."""
    if call.busy_at is not None:  # ⓪ BUSY 뒤 재요청 기다리는 중 (응답은 이미 소비했다)
        if now - call.busy_at >= BUSY_RETRY_DELAY_S:
            return PollResult(RETRY)
        return PollResult(PENDING)
    if done:
        if failed or raw is None:  # ① future 가 예외로 끝남 → 통신 실패로 본다 (DD E3)
            reply = fsm.GripperReply(False, 0.0, False, "COMM_ERROR")
            return PollResult(REPLY, reply, "COMM_ERROR")
        code = message_code(raw.message)  # ② 응답 코드
        if code == "BUSY" and call.busy_retries < BUSY_RETRY_MAX:
            return PollResult(BUSY_WAIT, None, code, raw.message)  # 조금 뒤 한 번 더
        reply = fsm.GripperReply(raw.ok, float(raw.width_mm), raw.grip_detected, code)
        return PollResult(REPLY, reply, code, raw.message)
    if now - call.sent_s > timeout_s:  # ③ 기다림 한계 (같으면 아직 기다린다)
        reply = fsm.GripperReply(False, 0.0, False, "TIMEOUT")
        return PollResult(TIMED_OUT, reply, "TIMEOUT")
    return PollResult(PENDING)  # ④ 아직


def unavailable_reply() -> fsm.GripperReply:
    """서비스가 없을 때 FSM 에 넘길 응답 → judge_grip 이 DEVICE_ERROR(GRIPPER_UNAVAILABLE)."""
    return fsm.GripperReply(False, 0.0, False, UNAVAILABLE)


def descend_time_s(dist_m: float, v: float, a: float, k: float, tol: float) -> float:
    """접근 높이 → 파지 높이 하강 예상 시간 (U2 z 제어: kp_z × 오차 를 v 로 포화, DD E5).

    dist_m 하강 거리, v 하강 속도 상한, a 가속 상한, k = kp_z, tol = 도달 허용치.
    예: (0.059, 0.05, 0.1, 2, 0.002) → 0.25 + 0.68 + 1.26 ≈ 2.19 s (U2 시뮬레이션 2.17 s).
    """
    if min(v, a, k, tol) <= 0:  # 기동 검사가 먼저 막는다 (방어)
        raise ValueError("v·a·k·tol 은 0 보다 커야 함")
    d_p = v / k  # 이 거리 안부터 P 가 속도를 줄인다 (포화가 끝나는 곳)
    if dist_m <= d_p:  # 처음부터 감속 구간: 지수 접근으로 tol 까지
        return max(math.log(dist_m / tol) / k, 0.0) if dist_m > 0 else 0.0
    accel = v / (2.0 * a)  # 0 → v 로 가속하며 늦어지는 시간
    cruise = (dist_m - d_p) / v  # 상한 속도로 가는 구간
    tail = math.log(d_p / tol) / k if d_p > tol else 0.0  # 감속 꼬리 (d_p → tol)
    return accel + cruise + tail


def grasp_room_ok(
    tcp_x: float, x_max: float, belt_speed: float, need_s: float, margin_m: float
) -> bool:
    """정렬된 지금 하강·닫힘을 끝낼 x 여유가 있나 (HLD D6). 같으면 여유 있음."""
    room = x_max - tcp_x  # 추종 구간 끝까지 남은 길
    need = belt_speed * need_s + margin_m  # 하강·닫힘 동안 벨트를 따라 더 갈 길 + 여유
    return room >= need


def call_record(
    call: GripCall,
    state: str,
    now: float,
    reply: fsm.GripperReply | None = None,
    code: str | None = None,
    raw: str | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    """로그 gripper 칸. 키는 항상 전부, 모르는 값은 None (DD 4절, E14)."""
    finished = state in (REPLY, TIMED_OUT, UNAVAILABLE)  # 응답(또는 결론)이 났다
    return {
        "kind": call.kind,
        "attempt": call.attempt,
        "seq": call.seq,
        "state": state,
        "sent_s": call.sent_s,
        "rx_s": now if finished else None,
        "latency_s": now - call.sent_s if finished else None,  # 보낸 뒤 결론까지
        "width_cmd_mm": call.width_mm,
        "force_n": call.force_n,
        "busy_retries": call.busy_retries,
        "ok": reply.ok if reply else None,
        "width_actual_mm": reply.width_mm if reply else None,
        "grip_detected": reply.grip_detected if reply else None,
        "message": raw,  # 원문
        "code": code,
        "verdict": verdict,  # HELD | NOT_HELD | DEVICE_ERROR (CLOSE·VERIFY 만)
    }
