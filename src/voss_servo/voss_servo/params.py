"""belt_servo 파라미터 표와 기동 검사 (순수 모듈 — ROS 를 import 하지 않는다).

- 값 규칙: docs/interfaces/voss_config.md. 미측정 = null → launch 가 넘기지 않음 → 여기서 None → READY 거부.
- belt.* · gripper.* · timing.* 원본은 config/voss_config.yaml. CLAUDE.md 규칙 5 로 belt_servo 는 그 파일을
  직접 읽지 않고 bringup 이 넘겨주는 파라미터로 받는다.
- 설계: src/voss_servo/design/U1-dd.md 1절.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 사각 구간에서 나오는 높이 = 들어가는 높이 + 이 값 (fsm.py 와 같은 값, 순환 import 를 피하려고 여기 둔다)
BLIND_EXIT_MARGIN_MM = 5.0
# 재시도 상한 (계약: TrackAndGrasp.action attempts 최대 3)
MAX_ATTEMPTS = 3
# belt.direction_base 길이 허용 오차 (voss_config.md 값 규칙: 1 ± 0.01)
DIRECTION_NORM_TOL = 0.01

# YAML 의 null 이 --params-file 로 들어오면 문자열 "null" 이 된다 → 미측정으로 본다
NULL_STRINGS = ("null", "~")
# 지문에서 뺄 키: 실행 위치(log.dir)·voss_config 자체 지문은 제어 설정이 아니다
DIGEST_EXCLUDE = ("log.dir", "config_version", "config_sha256")

# 검사 함수: 값을 받아 문제가 있으면 이유 문자열, 없으면 None 을 돌려준다
Check = Callable[[Any], "str | None"]


def _positive(v: Any) -> str | None:
    """0 보다 커야 하는 값."""
    return None if v > 0 else "0 보다 커야 함"  # 0·음수는 거부


def _non_negative(v: Any) -> str | None:
    """0 이상이어야 하는 값 (0 이 의미 있는 값일 때)."""
    return None if v >= 0 else "음수 불가"  # 음수만 거부


def _retry_range(v: Any) -> str | None:
    """재시도 상한은 1 ~ 3."""
    return None if 1 <= v <= MAX_ATTEMPTS else f"1~{MAX_ATTEMPTS} 이어야 함"


def _not_empty(v: Any) -> str | None:
    """빈 문자열 거부."""
    return None if str(v).strip() else "비어 있음"


@dataclass(frozen=True)
class ParamSpec:
    """파라미터 표의 한 줄."""

    name: str  # ROS 파라미터 이름 (점으로 묶음)
    kind: str  # float | int | float3 | str | int_or_str
    unit: str  # 사람이 읽는 단위
    required: bool  # True 면 값이 없을 때 READY 거부
    check: Check | None = None  # 자기 값 하나만 보는 검사


# DD 1절 표 그대로. 순서 = 로그·문서 순서
PARAM_SPECS: tuple[ParamSpec, ...] = (
    # --- bringup 이 voss_config.yaml 에서 넘기는 팀 공용 값 ---
    ParamSpec("belt.speed_cmps", "float", "cm/s", True, _positive),
    ParamSpec("belt.direction_base", "float3", "단위벡터", True),
    ParamSpec("gripper.pre_open_mm", "float", "mm", True, _positive),
    ParamSpec("gripper.grasp_width_mm", "float", "mm", True, _positive),
    ParamSpec("gripper.force_n", "float", "N", True, _positive),
    ParamSpec("timing.latency_offset_ms", "float", "ms", True),  # 0 = 보정 없음(유효값)
    ParamSpec("config_version", "int_or_str", "-", False),  # 없으면 경고만
    ParamSpec("config_sha256", "str", "-", False),  # 없으면 경고만
    # --- belt_servo 전용 값 (config/belt_servo.yaml) ---
    ParamSpec("grasp.tcp_z_below_top_mm", "float", "mm", True, _positive),
    ParamSpec("grasp.hold_width_min_mm", "float", "mm", True, _positive),
    ParamSpec("grasp.hold_width_max_mm", "float", "mm", True, _positive),
    ParamSpec("reach.x_min_mm", "float", "mm", True),
    ParamSpec("reach.x_max_mm", "float", "mm", True),
    ParamSpec("control.kp_per_s", "float", "1/s", True, _non_negative),  # 0 = FF 만
    ParamSpec("limits.max_speed_mps", "float", "m/s", True, _positive),
    ParamSpec("limits.max_acc_mps2", "float", "m/s²", True, _positive),
    ParamSpec("z.approach_above_top_mm", "float", "mm", True, _positive),
    ParamSpec("z.lift_above_top_mm", "float", "mm", True, _positive),
    ParamSpec("z.vision_cutoff_above_top_mm", "float", "mm", True, _non_negative),
    ParamSpec("input.stale_timeout_s", "float", "s", True, _positive),
    ParamSpec("input.lost_timeout_s", "float", "s", True, _positive),
    ParamSpec("retry.max_attempts", "int", "회", True, _retry_range),
    ParamSpec("stop_timeout_s", "float", "s", True, _positive),
    ParamSpec("rate_hz", "float", "Hz", True, _positive),
    ParamSpec("zero_hold_s", "float", "s", True, _non_negative),
    ParamSpec("log.dir", "str", "-", True, _not_empty),
)

# 이름으로 찾기 쉽게 사전도 만든다
SPEC_BY_NAME: dict[str, ParamSpec] = {s.name: s for s in PARAM_SPECS}


@dataclass
class ReadyReport:
    """기동 검사 결과."""

    ready: bool  # True 면 goal 을 받을 수 있다
    missing: list[str] = field(default_factory=list)  # 값이 안 온 필수 키
    invalid: list[tuple[str, str]] = field(default_factory=list)  # (키, 이유)


def _is_number(v: Any) -> bool:
    """bool 은 빼고 int·float 만 숫자로 본다. NaN·무한대도 거부."""
    if isinstance(v, bool) or not isinstance(v, int | float):  # True 가 1 로 섞이지 않게
        return False
    return math.isfinite(v)  # NaN·inf 거부


def _kind_error(kind: str, v: Any) -> str | None:
    """값의 모양이 kind 와 맞는지 본다. 맞으면 None."""
    if kind == "float":
        return None if _is_number(v) else "숫자 아님"
    if kind == "int":
        ok = isinstance(v, int) and not isinstance(v, bool)  # 정수만 (3.0 도 거부)
        return None if ok else "정수 아님"
    if kind == "float3":
        # ROS 는 double 배열을 array.array 로 줄 수 있어 list·tuple 로 한정하지 않는다
        if isinstance(v, str | bytes) or not hasattr(v, "__len__"):
            return "길이 3 숫자 목록 아님"
        ok = len(v) == 3 and all(_is_number(x) for x in v)
        return None if ok else "길이 3 숫자 목록 아님"
    if kind == "str":
        return None if isinstance(v, str) else "문자열 아님"
    if kind == "int_or_str":
        ok = isinstance(v, str) or (isinstance(v, int) and not isinstance(v, bool))
        return None if ok else "정수·문자열 아님"
    return f"알 수 없는 종류 {kind}"  # 표를 잘못 쓴 경우


def vector_norm(v: Any) -> float:
    """3차원 벡터 길이 √(x² + y² + z²)."""
    return math.sqrt(sum(float(x) * float(x) for x in v))


def _cross_checks(values: dict[str, Any], bad: set[str]) -> list[tuple[str, str]]:
    """두 값 이상을 함께 보는 검사. 둘 다 있고 개별 검사를 통과한 값만 본다."""

    def have(*names: str) -> bool:
        # 모두 값이 있고 앞 단계에서 invalid 가 아니어야 비교한다
        return all(values.get(n) is not None and n not in bad for n in names)

    out: list[tuple[str, str]] = []
    if have("belt.direction_base"):
        norm = vector_norm(values["belt.direction_base"])  # 방향 화살표 길이
        if abs(norm - 1.0) > DIRECTION_NORM_TOL:
            out.append(("belt.direction_base", f"norm {norm:.3f}"))
    if have("gripper.grasp_width_mm", "gripper.pre_open_mm"):
        if values["gripper.grasp_width_mm"] >= values["gripper.pre_open_mm"]:
            out.append(("gripper.grasp_width_mm", "pre_open_mm 보다 작아야 함"))
    if have("grasp.hold_width_min_mm", "grasp.hold_width_max_mm"):
        if values["grasp.hold_width_min_mm"] >= values["grasp.hold_width_max_mm"]:
            out.append(("grasp.hold_width_min_mm", "hold_width_max_mm 보다 작아야 함"))
    if have("reach.x_min_mm", "reach.x_max_mm"):
        if values["reach.x_min_mm"] >= values["reach.x_max_mm"]:
            out.append(("reach.x_min_mm", "x_max_mm 보다 작아야 함"))
    if have("z.approach_above_top_mm", "z.vision_cutoff_above_top_mm"):
        exit_mm = (
            values["z.vision_cutoff_above_top_mm"] + BLIND_EXIT_MARGIN_MM
        )  # 사각에서 나오는 높이
        if values["z.approach_above_top_mm"] <= exit_mm:
            out.append(("z.approach_above_top_mm", f"사각 이탈 높이 {exit_mm:g} mm 보다 커야 함"))
    return out


def check_params(values: dict[str, Any]) -> ReadyReport:
    """파라미터 값 묶음을 검사해 READY 여부와 문제 키를 돌려준다.

    values: {이름: 값 또는 None}. None 또는 키 없음 = 미측정·미전달.
    """
    missing: list[str] = []
    invalid: list[tuple[str, str]] = []
    for spec in PARAM_SPECS:
        v = values.get(spec.name)  # 없으면 None
        if isinstance(v, str) and v.strip() in NULL_STRINGS:
            v = None  # 문자열 "null" 도 미측정
        if v is None:
            if spec.required:
                missing.append(spec.name)  # 필수인데 안 왔다
            continue
        why = _kind_error(spec.kind, v)  # 모양 검사
        if why is None and spec.check is not None:
            why = spec.check(v)  # 값 범위 검사
        if why is not None:
            invalid.append((spec.name, why))
    bad = {name for name, _ in invalid}  # 개별 검사에서 이미 틀린 키
    invalid.extend(_cross_checks(values, bad))
    return ReadyReport(ready=not missing and not invalid, missing=missing, invalid=invalid)


def params_digest(values: dict[str, Any]) -> str:
    """제어·판정 값(None 아님, DIGEST_EXCLUDE 제외)을 이름순 JSON 으로 만들어 sha256 지문(64자)."""
    present = {
        k: values[k] for k in sorted(values) if values[k] is not None and k not in DIGEST_EXCLUDE
    }  # 값 있는 제어 설정만
    text = json.dumps(
        present,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=list,  # array.array 같은 배열은 list 로 바꿔 직렬화
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ready_log_line(report: ReadyReport) -> str:
    """기동 로그 한 줄. 어떤 키가 문제인지 이름으로 남긴다."""
    if report.ready:
        return "READY"
    bad = ", ".join(f"{k}: {why}" for k, why in report.invalid)  # "키: 이유" 목록
    return f"READY 거부: missing=[{', '.join(report.missing)}] invalid=[{bad}]"
