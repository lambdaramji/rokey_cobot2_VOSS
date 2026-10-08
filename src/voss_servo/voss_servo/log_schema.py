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
    "pose_stamp_s",
    "pose_rx_s",
    "t_calc_s",  # 이 틱 계산 시각
    "t_pub_s",  # servo_cmd 발행 시각
    "position_base_m",  # 관측 박스 윗면 중심 [x, y, z]
    "position_valid",
    "position_source",
    "calib_version",
    "tcp_pose_m",  # 받은 TCP pose [x, y, z] (원본)
    "tcp_now_m",  # 보정 TCP (지금으로 외삽, U2)
    "tcp_extrap_s",  # 외삽 지평 (자르기 전)
    "tcp_extrap_capped",  # 외삽 지평이 상한에서 잘렸나
    "predicted_m",  # 예측 박스 위치 (U2)
    "predict_horizon_s",  # 예측 지평
    "predict_dt_clipped",  # 박스 stamp 가 미래였나
    "obs_age_s",  # 마지막 유효 관측 나이 (촬영 시각 기준)
    "visible",  # 사각 아님 + 최신 메시지 valid
    "tcp_target_m",  # TCP 목표 (U2)
    "error_m",  # 목표 − TCP (U2)
    "err_along_m",  # 접근 높이 기준 오차의 벨트 방향 성분
    "err_cross_m",  # 같은 오차의 가로 성분 크기
    "belt_vel_mps",  # 벨트 속도 벡터
    "belt_speed_mps",
    "cmd_vel_mps",  # 발행한 속도
    "clamped",  # 한계로 잘랐나 (U2)
    "cmd_rule",  # FF_P | FF | ZERO | ZERO_NO_POSE | ZERO_NO_OBS | ZERO_STOP
    "dt_s",  # 가속 제한에 쓴 틱 간격
    "aligned",  # 전환 플래그 (TRACK → DESCEND)
    "at_grasp_height",  # 전환 플래그 (DESCEND → GRASP)
    "at_lift_height",  # 전환 플래그 (LIFT → VERIFY)
    "reach",  # null | X_MIN | X_MAX
    "vision_blind",
    "box_lost",
    "box_stale",
    "pose_stale",
    "cancel_requested",
    "stop_result",  # null | "OK" | "FAILED:<message>" | "TIMEOUT" | "UNAVAILABLE"
    "reason",
    "cause",
    "grasped",
    "gripper",  # null | {ok, width_actual_mm, grip_detected, message}
    "config_version",
    "config_sha256",
    "params_sha256",
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
    "grasped",
    "belt_speed_mps",
    "gripper",
    "position_source",
    "calib_version",
    "config_version",
    "config_sha256",
    "params_sha256",
)

# 모듈을 불러올 때 부분집합 규칙을 확인한다 (표를 잘못 고치면 바로 실패)
assert set(ATTEMPT_FIELDS) <= set(TICK_FIELDS), "ATTEMPT_FIELDS 는 TICK_FIELDS 의 부분집합"

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
