"""belt_servo 로그 레코드 양식 (레코드 만들기·직렬화는 순수, 파일 쓰기는 JsonlWriter 하나).

- 틱 로그: 30 Hz 한 틱 = 한 줄(JSON Lines), <log.dir>/ticks/ — git 미추적.
- 시도 로그: 시도 끝(ATTEMPT_END)·goal 끝(GOAL_END) 한 줄, <log.dir>/attempts/ — 게이트 집계(ADR-0002)용,
  커밋 대상(게이트 분모 = GOAL_END 행 수).
- 시도 키는 틱 키의 부분집합. 모르는 값은 null(NaN 금지).
- 설계: src/voss_servo/design/U1-dd.md 3절.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

# 틱 레코드 키 (순서 = 파일에 쓰이는 순서). 단위는 키 끝에 붙인다
TICK_FIELDS: tuple[str, ...] = (
    "kind",  # "tick" | "attempt"
    "event",  # 틱 = null, 시도 = "ATTEMPT_END" | "GOAL_END"
    "goal_id",
    "track_id",
    "attempt",
    "phase",
    "stopping",
    "terminal",
    "box_stamp_s",  # BoxTrack.stamp (촬영 시각)
    "box_rx_s",  # 그 BoxTrack 을 받은 시각
    "box_u_px",  # 그 BoxTrack 의 픽셀 u (U9-c — 시야 어느 쪽으로 빠졌나)
    "box_v_px",  # 그 BoxTrack 의 픽셀 v
    "pose_stamp_s",
    "pose_rx_s",
    "t_calc_s",  # 이 틱 계산 시각
    "t_pub_s",  # servo_cmd 발행 시각
    "position_base_m",  # 관측 박스 윗면 중심 [x, y, z]
    "position_valid",
    "position_source",
    "calib_version",
    "yaw_base_deg",  # BoxTrack yaw_base(도) — yaw_valid 이고 유한할 때만 (S2-T18 0단계, 관측 기록만)
    "yaw_valid",  # BoxTrack yaw_valid — 필드 없는 빌드·박스 없음이면 null
    "tcp_pose_m",  # 받은 TCP pose [x, y, z] (원본)
    "tcp_now_m",  # 보정 TCP (지금으로 외삽, U2)
    "tcp_extrap_s",  # 외삽 지평 (자르기 전)
    "tcp_extrap_capped",  # 외삽 지평이 상한에서 잘렸나
    "predicted_m",  # 예측 박스 위치 (U2)
    "predict_horizon_s",  # 예측 지평
    "predict_dt_clipped",  # 박스 stamp 가 미래였나
    "obs_age_s",  # now − 마지막 유효 관측의 촬영 stamp(BoxTrack.stamp). 이름은 10/10 로그 호환으로 유지
    "obs_rx_age_s",  # now − 마지막 유효 관측을 받은 시각 (수신 기준, U9-c)
    "other_box_rx_age_s",  # now − 이 goal 중 다른 트랙을 마지막으로 받은 시각 (U9-c, LOST 원인 판정 근거)
    "box_pub_count",  # /voss/vision/box 발행자 수 — LOST 틱에서만 조회, 그 밖 null (U9-c)
    "visible",  # 사각 아님 + 최신 메시지 valid
    "tcp_target_m",  # TCP 목표 (U2)
    "error_m",  # 목표 − TCP (U2)
    "err_along_m",  # 접근 높이 기준 오차의 벨트 방향 성분
    "err_cross_m",  # 같은 오차의 가로 성분 크기
    "belt_vel_mps",  # 벨트 속도 벡터
    "belt_speed_mps",
    "cmd_vel_mps",  # 발행한 속도
    "tcp_vel_meas_mps",  # pose 값 차분으로 잰 TCP 속도 [x, y, z] (U9-c, z = 측정 z 속도)
    "stall_ticks",  # 명령 ≠ 0 인데 측정 ≈ 0 인 연속 틱 수 (U9-c)
    "belt_speed_est_mps",  # 관측열 직선 맞춤 벨트 속도 — 로그 전용, 제어에 안 씀 (U9-c)
    "belt_speed_est_span_s",  # 그 맞춤에 쓴 관측의 시간 폭
    "clamped",  # 한계로 잘랐나 (U2)
    "cmd_rule",  # FF_P | FF | ZERO | ZERO_NO_POSE | ZERO_NO_OBS | ZERO_STOP
    "z_v_cmd_mps",  # clamp 전 z 속도 요구값 (목표 z 없으면 null). 발행값은 cmd_vel_mps[2] (S2-T14)
    "dt_s",  # 가속 제한에 쓴 틱 간격
    "aligned",  # 전환 플래그 (TRACK → DESCEND)
    "at_grasp_height",  # 전환 플래그 (DESCEND → GRASP)
    "at_lift_height",  # 전환 플래그 (LIFT → VERIFY)
    "reach",  # null | X_MIN | X_MAX | Z_MIN
    "vision_blind",
    "box_lost",
    "box_stale",
    "pose_stale",
    "cancel_requested",
    "stop_result",  # null | "OK" | "FAILED:<message>" | "TIMEOUT" | "UNAVAILABLE"
    "reason",
    "cause",
    "cause_fsm",  # fsm.step 이 낸 원래 cause (진단으로 덮어쓰기 전, U9-c). 스냅샷 행은 null
    "grasped",
    "retreat",  # null | "OPENING"(개방 기다림) | "RISING" — 실패 뒤 안전 후퇴 중 (U9b, phase 는 LIFT)
    "retreat_reason",  # null | 후퇴 끝에 보낼 reason (GRASP_FAILED | DEVICE_ERROR)
    "retreat_done",  # null(후퇴 없음) | true(들기 높이 도달로 끝) | false(후퇴 중 다른 이유로 끝)
    "retry_room_ok",  # null | 마지막 GRASP 실패 때 재시도 x 여유 (true 재시도 / false 후퇴)
    "phase_t_prepare_s",  # 이 시도에서 PREPARE 에 처음 들어간 시각 (U9-c, 아직이면 null)
    "phase_t_track_s",
    "phase_t_descend_s",
    "phase_t_grasp_s",
    "phase_t_lift_s",
    "phase_t_verify_s",
    "gripper",  # null | 그리퍼 호출 기록 dict (키 목록은 grip.call_record, design/U5-dd.md 4절)
    "z_profile",  # "p" | "trapezoid" — 이 시도의 z 속도 프로파일 (S2-T14)
    # --- S2-T18 J6 회전 파지 (rotate.ROT_LOG_KEYS 와 같은 순서, 회전 off 면 null) ---
    "rot_state",  # 회전 하위 상태 (COLLECT·ROTATING·SETTLING·DONE·SKIP·STOPPING·FALLBACK·RETURNING·RETURNED)
    "rot_cause",  # 회전 원인 (SMALL·STALL·TIMEOUT·RETURN_INCOMPLETE 등)
    "yaw_target_deg",  # 결정한 박스 yaw (베이스)
    "rot_delta_deg",  # 벨트 기준 상대각 Δ = 돌릴 양
    "tool_yaw_deg",  # pose 의 공구 yaw (외삽 전)
    "tool_yaw_est_deg",  # 지금으로 외삽한 공구 yaw
    "rot_err_deg",  # 지금 목표(회전 = target, 되돌리기 = home) − 공구 yaw
    "wz_cmd_dps",  # 발행한 베이스 Z 각속도
    "wz_meas_dps",  # pose 로 잰 각속도
    "rot_n",  # 결정에 쓴 yaw 프레임 수
    "rot_rbar",  # 결정 때 흩어짐 (2θ 평균 벡터 길이)
    "rot_time_s",  # 회전 시작 → DONE·FALLBACK
    "rot_end_left_deg",  # goal 끝 틱만: 공구 yaw − 기준 각 (손목이 돌아간 채 끝난 양, 다음 MoveToZone 이 맞춤)
    "config_version",
    "config_sha256",
    "params_sha256",
)

# 회전 키 (스냅샷 경로가 같은 목록을 쓴다, S2-T18 r1-1)
ROT_KEYS: tuple[str, ...] = (
    "rot_state",
    "rot_cause",
    "yaw_target_deg",
    "rot_delta_deg",
    "tool_yaw_deg",
    "tool_yaw_est_deg",
    "rot_err_deg",
    "wz_cmd_dps",
    "wz_meas_dps",
    "rot_n",
    "rot_rbar",
    "rot_time_s",
    "rot_end_left_deg",
)

# 시도 레코드 키 (틱 키의 부분집합)
ATTEMPT_FIELDS: tuple[str, ...] = (
    "kind",
    "event",
    "goal_id",
    "track_id",
    "attempt",
    "phase",
    "terminal",
    "t_calc_s",
    "reason",
    "cause",
    "cause_fsm",
    "grasped",
    "retreat",
    "retreat_reason",
    "retreat_done",
    "retry_room_ok",
    "phase_t_prepare_s",
    "phase_t_track_s",
    "phase_t_descend_s",
    "phase_t_grasp_s",
    "phase_t_lift_s",
    "phase_t_verify_s",
    "belt_speed_mps",
    "belt_speed_est_mps",
    "belt_speed_est_span_s",
    "other_box_rx_age_s",
    "box_pub_count",
    "stall_ticks",
    "gripper",
    "position_source",
    "calib_version",
    "z_profile",
    "rot_state",  # S2-T18
    "rot_cause",
    "rot_delta_deg",
    "rot_time_s",
    "rot_end_left_deg",
    "config_version",
    "config_sha256",
    "params_sha256",
)

# 모듈을 불러올 때 부분집합 규칙을 확인한다 (표를 잘못 고치면 바로 실패)
assert set(ATTEMPT_FIELDS) <= set(TICK_FIELDS), "ATTEMPT_FIELDS 는 TICK_FIELDS 의 부분집합"

# 단계 진입 시각 키 (phase 이름 → 키, U9-c)
PHASE_T_KEYS: dict[str, str] = {
    "PREPARE": "phase_t_prepare_s",
    "TRACK": "phase_t_track_s",
    "DESCEND": "phase_t_descend_s",
    "GRASP": "phase_t_grasp_s",
    "LIFT": "phase_t_lift_s",
    "VERIFY": "phase_t_verify_s",
}
assert set(PHASE_T_KEYS.values()) <= set(ATTEMPT_FIELDS), "단계 시각은 시도 행에도 남긴다"

ATTEMPT_END = "ATTEMPT_END"
GOAL_END = "GOAL_END"


def _clean(value: Any) -> Any:
    """NaN·무한대를 None 으로 바꾼다 (목록·사전 안쪽까지)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def make_tick(**values: Any) -> dict[str, Any]:
    """틱 레코드를 만든다. 키가 하나라도 빠지거나 남으면 ValueError."""
    expected = set(TICK_FIELDS) - {"kind"}  # kind 는 여기서 채운다
    given = set(values)
    if given != expected:
        missing = sorted(expected - given)
        extra = sorted(given - expected)
        raise ValueError(f"틱 키 불일치: 빠짐={missing} 남음={extra}")
    record = {"kind": "tick", **values}
    return {k: _clean(record[k]) for k in TICK_FIELDS}  # 정해진 순서로


def to_attempt(tick: dict[str, Any], event: str) -> dict[str, Any]:
    """틱 레코드에서 시도 레코드를 뽑는다."""
    record = {k: tick[k] for k in ATTEMPT_FIELDS}  # 부분집합만 복사
    record["kind"] = "attempt"
    record["event"] = event
    return record


def to_json_line(record: dict[str, Any]) -> str:
    """레코드 → JSON 한 줄 (줄바꿈 없음). NaN 이 섞이면 예외."""
    return json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def log_paths(log_dir: str, started: datetime) -> tuple[Path, Path]:
    """노드 기동 1회 = 파일 1쌍. 절대 경로로 돌려준다."""
    base = Path(log_dir).expanduser().resolve()  # 상대 경로는 실행 위치 기준 → 절대 경로로
    stamp = started.strftime("%Y%m%d_%H%M%S")
    ticks = base / "ticks" / f"servo_ticks_{stamp}.jsonl"
    attempts = base / "attempts" / f"servo_attempts_{stamp}.jsonl"
    return ticks, attempts


class JsonlWriter:
    """JSON Lines 파일에 한 줄씩 쓰고 바로 flush 한다 (노드가 죽어도 쓴 줄은 남게)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: TextIO | None = None  # 처음 쓸 때 연다 (빈 파일을 만들지 않으려고)

    def write(self, record: dict[str, Any]) -> None:
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)  # 폴더가 없으면 만든다
            self._file = self.path.open("a", encoding="utf-8")
        self._file.write(to_json_line(record) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


assert set(ROT_KEYS) <= set(TICK_FIELDS), "ROT_KEYS 는 TICK_FIELDS 의 부분집합"
