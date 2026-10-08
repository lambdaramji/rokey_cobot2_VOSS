"""MQTT 명령 JSON의 검증·변환을 담당한다.

입력: docs/interfaces/mqtt.md의 voss/command JSON.
출력: ROS Command.srv의 command/arg 또는 bridge 거부 코드.
ROS·MQTT 라이브러리 없이 pytest로 검증할 수 있게 순수 함수만 둔다.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

COMMAND_MAX_AGE_S = 30.0
ALLOWED_TYPES = {"start", "stop", "resume", "priority", "answer", "reset_zone"}
RESETTABLE_ZONES = {"A", "B", "C", "RECHECK", "HOLD"}


@dataclass(frozen=True)
class ParsedCommand:
    """검증된 MQTT 명령을 ROS Command.srv 입력으로 바꾼 결과다."""

    command_id: str
    command: str
    arg: str
    raw_text: str
    sent_at: datetime


class CommandError(ValueError):
    """MQTT 명령이 계약을 어겼을 때 bridge 거부 코드를 함께 보관한다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_command_json(payload: str, now: datetime) -> ParsedCommand:
    """MQTT JSON을 검증하고 ROS Command.srv 입력으로 변환한다.

    JSON/필드/시각/args가 계약과 다르면 CommandError를 발생시킨다.
    """

    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CommandError("INVALID_JSON") from exc

    if not isinstance(data, dict):
        raise CommandError("INVALID_JSON")

    command_id = data.get("command_id")
    command_type = data.get("type")
    args = data.get("args")
    raw_text = data.get("raw_text")
    sent_at_text = data.get("sent_at")

    if not _is_uuid(command_id):
        raise CommandError("INVALID_COMMAND")
    if command_type not in ALLOWED_TYPES:
        raise CommandError("INVALID_COMMAND")
    if not isinstance(args, dict):
        raise CommandError("INVALID_ARGS")
    if not isinstance(raw_text, str):
        raise CommandError("INVALID_COMMAND")

    sent_at = _parse_sent_at(sent_at_text)
    if command_type != "stop" and _is_expired(sent_at, now):
        raise CommandError("EXPIRED")

    arg = _command_arg(command_type, args)
    return ParsedCommand(
        command_id=command_id,
        command=command_type,
        arg=arg,
        raw_text=raw_text,
        sent_at=sent_at,
    )


def _is_uuid(value: object) -> bool:
    """문자열이 UUID 형식인지 확인한다."""

    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _parse_sent_at(value: object) -> datetime:
    """timezone이 포함된 ISO-8601 시각만 허용한다."""

    if not isinstance(value, str):
        raise CommandError("INVALID_SENT_AT")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommandError("INVALID_SENT_AT") from exc

    if parsed.tzinfo is None:
        raise CommandError("INVALID_SENT_AT")
    return parsed


def _is_expired(sent_at: datetime, now: datetime) -> bool:
    """stop을 제외한 명령이 30초보다 오래됐는지 확인한다."""

    age_s = (now - sent_at).total_seconds()
    return age_s > COMMAND_MAX_AGE_S


def _command_arg(command_type: str, args: dict[str, object]) -> str:
    """명령별 args 객체를 Command.arg 문자열로 변환한다."""

    if command_type == "start":
        _require_exact_keys(args, set())
        return "ALL"

    if command_type in {"stop", "resume"}:
        _require_exact_keys(args, set())
        return ""

    if command_type == "priority":
        _require_exact_keys(args, {"dong"})
        return _required_text(args["dong"])

    if command_type == "reset_zone":
        _require_exact_keys(args, {"zone"})
        zone = _required_text(args["zone"])
        if zone not in RESETTABLE_ZONES:
            raise CommandError("INVALID_ARGS")
        return zone

    if command_type == "answer":
        return _answer_arg(args)

    raise CommandError("INVALID_COMMAND")


def _answer_arg(args: dict[str, object]) -> str:
    """answer의 box_id와 동/HOLD 중 하나를 합쳐 Command.arg를 만든다."""

    keys = set(args)
    allowed_key_sets = ({"box_id", "dong"}, {"box_id", "zone"})
    if keys not in allowed_key_sets:
        raise CommandError("INVALID_ARGS")

    box_id = _required_text(args["box_id"])
    if "dong" in args:
        target = _required_text(args["dong"])
    else:
        target = _required_text(args["zone"])
        if target != "HOLD":
            raise CommandError("INVALID_ARGS")

    if "|" in box_id or "|" in target:
        raise CommandError("INVALID_ARGS")
    return f"{box_id}|{target}"


def _required_text(value: object) -> str:
    """빈 문자열이 아닌 문자열만 반환한다."""

    if not isinstance(value, str):
        raise CommandError("INVALID_ARGS")
    stripped = value.strip()
    if not stripped:
        raise CommandError("INVALID_ARGS")
    return stripped


def _require_exact_keys(args: dict[str, object], expected: set[str]) -> None:
    """정의되지 않은 args 키가 조용히 무시되지 않게 정확히 비교한다."""

    if set(args) != expected:
        raise CommandError("INVALID_ARGS")
