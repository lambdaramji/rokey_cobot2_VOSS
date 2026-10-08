"""sort_logger 의 판단 로직 (ROS·DB 없이 pytest 로 시험한다).

하는 일
- SortResult 필드 → DB `sort_log` 한 행으로 바꾼다 (voss_msgs.md "DB sort_log 대응").
- DB 에 못 쓴 행을 jsonl 파일(스풀)에 쌓고, 나중에 순서대로 다시 보낸다 (SRD v1.0 §5, #52 MC-027).
- `/voss/log/status` 에 낼 상태를 정한다: STARTING / OK / DB_ERROR / SPOOL_FULL (topics.md).

관련 문서: docs/interfaces/voss_msgs.md (SortResult), topics.md (sort_logger 행)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

# /voss/log/status 값 (topics.md)
STATUS_STARTING = "STARTING"  # 아직 DB 에 한 번도 연결하지 못함 → sort_manager 가 start 를 거부한다
STATUS_OK = "OK"
STATUS_DB_ERROR = "DB_ERROR"  # DB 쓰기 실패, 스풀에 쌓는 중 (운전은 막지 않는다, MC-027)
STATUS_SPOOL_FULL = "SPOOL_FULL"  # 스풀도 더 쌓을 수 없음 → 결과가 유실될 수 있다

# 스풀 재전송 간격(초): 1 → 2 → 5 → 10, 그 뒤로는 30 초마다 (SRD v1.0 §5 DB)
RETRY_DELAYS_S = [1, 2, 5, 10, 30]

# 스풀 경고 기준(SRD 제안값). 이 줄 수를 넘으면 SPOOL_FULL 로 알린다.
SPOOL_WARN_ROWS = 1000

# sort_log 컬럼 (docker/db/init/01_schema.sql 과 같은 순서)
SORT_LOG_COLUMNS = [
    "box_id",
    "session_id",
    "track_id",
    "code",
    "dong",
    "confidence",
    "decided_by",
    "zone",
    "result",
    "reason",
    "raw_text",
    "second_region",
    "rule_version",
    "attempts",
    "started_at",
    "finished_at",
]


def ros_time_to_iso(sec: int, nanosec: int) -> str | None:
    """ROS Time(sec, nanosec) → ISO-8601 UTC 문자열. 0 시각이면 None (추정해서 채우지 않는다)."""
    if sec == 0 and nanosec == 0:
        return None
    moment = datetime.fromtimestamp(sec + nanosec / 1e9, tz=UTC)
    return moment.isoformat(timespec="microseconds")  # 항상 같은 자리수


def result_to_row(result: dict) -> dict:
    """SortResult 필드(dict) → sort_log 한 행(dict).

    result 에는 SortResult 필드 이름 그대로 들어 있고, stamp·started_at 은 (sec, nanosec) 튜플이다.
    이름이 바뀌는 곳: outcome → result, dong_alt → second_region, stamp → finished_at.
    retries 는 DB 가 attempts 로 계산한다(GENERATED 컬럼).
    """
    stamp_sec, stamp_nanosec = result["stamp"]
    started_sec, started_nanosec = result["started_at"]
    return {
        "box_id": result["box_id"],
        "session_id": result["session_id"],
        "track_id": result["track_id"],
        "code": result["code"],
        "dong": result["dong"],
        "confidence": result["confidence"],
        "decided_by": result["decided_by"],
        "zone": result["zone"],
        "result": result["outcome"],
        "reason": result["reason"],
        "raw_text": result["raw_text"],
        "second_region": result["dong_alt"],
        "rule_version": result["rule_version"],
        "attempts": result["attempts"],
        "started_at": ros_time_to_iso(started_sec, started_nanosec),
        "finished_at": ros_time_to_iso(stamp_sec, stamp_nanosec),
    }


def retry_delay_s(failures_in_a_row: int) -> int:
    """연속 실패 횟수(1부터) → 다음 재시도까지 기다릴 초."""
    index = min(failures_in_a_row, len(RETRY_DELAYS_S)) - 1
    return RETRY_DELAYS_S[max(index, 0)]


def decide_status(ever_connected: bool, db_ok: bool, spool_rows: int, spool_writable: bool) -> str:
    """지금 상태를 /voss/log/status 값 하나로 정한다.

    - 한 번도 DB 에 연결하지 못했으면 STARTING (sort_manager 는 start 를 거부한다)
    - 스풀이 경고 기준을 넘었거나 파일에 쓸 수 없으면 SPOOL_FULL
    - DB 가 끊겼거나 스풀에 아직 보낼 행이 남아 있으면 DB_ERROR
    - 그 밖에는 OK
    """
    if not ever_connected:
        return STATUS_STARTING
    if not spool_writable or spool_rows >= SPOOL_WARN_ROWS:
        return STATUS_SPOOL_FULL
    if not db_ok or spool_rows > 0:
        return STATUS_DB_ERROR
    return STATUS_OK


class Spool:
    """DB 에 못 쓴 행을 한 줄에 하나씩(jsonl) 쌓아 두는 파일.

    재기동해도 남아야 하므로 메모리가 아니라 파일에 둔다(SRD: durable 볼륨).
    보낼 때는 맨 앞 줄부터 순서대로 보낸다.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def append(self, row: dict) -> bool:
        """한 행을 맨 뒤에 쌓는다. 디스크 오류 등으로 못 쓰면 False."""
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as spool_file:
                spool_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                spool_file.flush()
                os.fsync(spool_file.fileno())  # 전원이 나가도 남도록 디스크에 바로 쓴다
            return True
        except OSError:
            return False

    def read_all(self) -> list[dict]:
        """쌓인 행을 순서대로 모두 읽는다. 파일이 없으면 빈 목록. 깨진 줄은 건너뛴다."""
        if not os.path.exists(self.path):
            return []
        rows = []
        with open(self.path, encoding="utf-8") as spool_file:
            for line in spool_file:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue  # 쓰다 끊긴 마지막 줄 등. 원본 파일은 지우지 않고 rewrite 때만 빠진다
        return rows

    def count(self) -> int:
        return len(self.read_all())

    def rewrite(self, rows: list[dict]) -> None:
        """남은 행만으로 파일을 다시 쓴다. 임시 파일에 쓴 뒤 바꿔치기해 중간에 끊겨도 안전하다."""
        if not rows:
            if os.path.exists(self.path):
                os.remove(self.path)
            return
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as temp_file:
            for row in rows:
                temp_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, self.path)
