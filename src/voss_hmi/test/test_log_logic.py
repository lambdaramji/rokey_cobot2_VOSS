"""log_logic 시험: SortResult → sort_log 행, 재시도 간격, 상태 판정, 스풀 파일 (ROS·DB 없음)."""

from voss_hmi.log_logic import (
    SORT_LOG_COLUMNS,
    SPOOL_WARN_ROWS,
    Spool,
    decide_status,
    result_to_row,
    retry_delay_s,
    ros_time_to_iso,
)


def make_result(**changes) -> dict:
    """SortResult 필드 그대로의 dict (시각은 (sec, nanosec))."""
    result = {
        "box_id": "20261010T143012-a3f9-004",
        "session_id": "20261010T143012-a3f9",
        "track_id": 7,
        "code": "S07-01",
        "dong": "역삼동",
        "confidence": 0.93,
        "decided_by": "OCR",
        "zone": "A",
        "outcome": "PLACED",
        "reason": "",
        "raw_text": "S07-01 역삼동",
        "dong_alt": "",
        "rule_version": "v1",
        "attempts": 2,
        "stamp": (1_791_610_212, 500_000_000),  # 2026-10-10 14:30:12.5 KST
        "started_at": (1_791_610_190, 0),
    }
    result.update(changes)
    return result


def test_row_has_exactly_the_sort_log_columns():
    assert list(result_to_row(make_result())) == SORT_LOG_COLUMNS


def test_renamed_fields_follow_the_db_mapping():
    row = result_to_row(make_result(outcome="HELD", dong_alt="대치동"))
    assert row["result"] == "HELD"  # outcome → result
    assert row["second_region"] == "대치동"  # dong_alt → second_region
    assert row["finished_at"] == "2026-10-10T05:30:12.500000+00:00"  # stamp → finished_at


def test_zero_started_at_becomes_none_not_a_guess():
    row = result_to_row(make_result(started_at=(0, 0)))
    assert row["started_at"] is None


def test_ros_time_to_iso_keeps_utc_offset():
    assert ros_time_to_iso(0, 1000) == "1970-01-01T00:00:00.000001+00:00"


def test_retry_delays_are_1_2_5_10_then_30():
    delays = [retry_delay_s(n) for n in range(1, 8)]
    assert delays == [1, 2, 5, 10, 30, 30, 30]


def test_status_starting_until_first_connection():
    assert decide_status(False, False, 0, True) == "STARTING"


def test_status_ok_only_when_db_ok_and_spool_empty():
    assert decide_status(True, True, 0, True) == "OK"
    assert decide_status(True, True, 3, True) == "DB_ERROR"  # 보낼 행이 남아 있음
    assert decide_status(True, False, 0, True) == "DB_ERROR"


def test_status_spool_full_when_spool_cannot_grow():
    assert decide_status(True, False, SPOOL_WARN_ROWS, True) == "SPOOL_FULL"
    assert decide_status(True, False, 0, False) == "SPOOL_FULL"


def test_spool_keeps_order_and_survives_reopen(tmp_path):
    path = str(tmp_path / "spool" / "sort_log.jsonl")
    spool = Spool(path)
    assert spool.read_all() == []
    assert spool.append({"box_id": "a"}) and spool.append({"box_id": "b"})

    reopened = Spool(path)  # 재기동한 것처럼 새 객체로 연다
    assert [row["box_id"] for row in reopened.read_all()] == ["a", "b"]


def test_spool_rewrite_keeps_only_remaining_rows(tmp_path):
    spool = Spool(str(tmp_path / "s.jsonl"))
    for box_id in ["a", "b", "c"]:
        spool.append({"box_id": box_id})
    spool.rewrite([{"box_id": "c"}])
    assert spool.read_all() == [{"box_id": "c"}]
    spool.rewrite([])
    assert spool.count() == 0


def test_spool_skips_a_half_written_line(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"box_id": "a"}\n{"box_id": "b', encoding="utf-8")
    assert Spool(str(path)).read_all() == [{"box_id": "a"}]


def test_spool_append_reports_failure_instead_of_raising(tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    spool = Spool(str(blocker / "s.jsonl"))  # 폴더 자리에 파일이 있어 만들 수 없다
    assert spool.append({"box_id": "a"}) is False
