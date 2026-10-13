"""Sprint 2 S2-T07 (BRD v1.5) — sort_log.slot, pallet_log 행, ListPlacements 응답, 두 저장 흐름의 상태 (DB 없이)."""

from datetime import UTC, datetime

from voss_hmi.db_writer import PLACEMENTS_SQL, insert_sql, sort_log_columns
from voss_hmi.log_logic import (
    PALLET_LOG_COLUMNS,
    SORT_LOG_COLUMNS,
    Spool,
    list_placements_reply,
    pallet_result_to_row,
    placements_from_rows,
    result_to_row,
    worst_status,
)
from voss_hmi.result_store import ResultStore


def sort_result(**kw) -> dict:
    r = {"box_id": "S-001", "session_id": "S", "track_id": 1, "code": "S07-01", "dong": "역삼동",
         "confidence": 0.9, "decided_by": "OCR", "zone": "A", "outcome": "PLACED", "reason": "",
         "raw_text": "", "dong_alt": "", "rule_version": "1", "attempts": 1, "stamp": (10, 0),
         "started_at": (0, 0)}  # fmt: skip
    r.update(kw)
    return r


def pallet_result(outcome: str = "DONE", **kw) -> dict:
    loaded = outcome in ("DONE", "FAILED")
    r = {"run_id": "R", "session_id": "S", "box_id": "S-001", "dong": "대치동", "route_index": 1,
         "zone": "B", "slot": 4, "pallet_slot": 6 if loaded else -1, "pallet_col": 2 if loaded else 0,
         "pallet_lane": 1 if loaded else 0, "pallet_layer": 2 if loaded else 0, "outcome": outcome,
         "reason": "", "attempts": 1 if loaded else 0, "stamp": (20, 500_000_000)}  # fmt: skip
    r.update(kw)
    return r


def test_sort_log_slot_minus_one_is_null() -> None:
    assert SORT_LOG_COLUMNS[-1] == "slot"  # 스키마와 같은 순서(맨 끝)
    assert result_to_row(sort_result(slot=2))["slot"] == 2
    assert result_to_row(sort_result(slot=-1))["slot"] is None
    assert result_to_row(sort_result())["slot"] is None  # 예전 결과(slot 없음)


def test_pallet_row_keeps_unloaded_with_nulls() -> None:
    done = pallet_result_to_row(pallet_result())
    assert list(done) == PALLET_LOG_COLUMNS
    assert (done["result"], done["pallet_slot"], done["pallet_col"], done["pallet_layer"]) == ("DONE", 6, 2, 2)
    over = pallet_result_to_row(pallet_result("OVERFLOW"))
    assert (over["result"], over["pallet_slot"], over["pallet_col"], over["pallet_lane"]) == ("OVERFLOW", None, None, None)
    excl = pallet_result_to_row(pallet_result("EXCLUDED", route_index=-1))
    assert excl["route_index"] == -1 and excl["finished_at"].startswith("1970-01-01T00:00:20.5")


def test_placements_reply() -> None:
    t = datetime(2026, 10, 13, 9, 0, 0, 250000, tzinfo=UTC)
    rows = [("S-001", "역삼동", "A", 0, t, False), ("S-002", "역삼동", "A", None, t, True)]
    ok, msg, items = list_placements_reply("S", 0, lambda sid: rows)
    assert ok and msg == "" and items[0]["slot"] == 0 and items[1]["slot"] == -1 and items[1]["palletized"]
    assert items[0]["stamp"] == divmod(round(t.timestamp() * 1e9), 1_000_000_000)
    assert placements_from_rows([]) == []
    assert list_placements_reply("", 0, lambda sid: rows)[1].startswith("INVALID")
    assert list_placements_reply("S", 3, lambda sid: rows)[1].startswith("SPOOL_PENDING")

    def broken(sid):
        raise RuntimeError("connect: OperationalError")

    ok, msg, items = list_placements_reply("S", 0, broken)
    assert not ok and msg.startswith("DB_ERROR") and items == []


def test_sql_shapes() -> None:
    assert "slot" not in sort_log_columns(False) and sort_log_columns(True)[-1] == "slot"  # 마이그레이션 전 DB
    sql = insert_sql("pallet_log", PALLET_LOG_COLUMNS, "run_id, box_id")
    assert "ON CONFLICT (run_id, box_id) DO NOTHING RETURNING box_id" in sql
    assert "s.result = 'PLACED'" in PLACEMENTS_SQL and "p.result = 'DONE'" in PLACEMENTS_SQL


def test_status_is_worst_of_both_stores() -> None:
    assert worst_status("OK", "OK") == "OK"
    assert worst_status("OK", "DB_ERROR") == "DB_ERROR"
    assert worst_status("SPOOL_FULL", "DB_ERROR") == "SPOOL_FULL"
    assert worst_status("OK", "STARTING") == "STARTING"


class FakeTable:
    def __init__(self) -> None:
        self.rows = []

    def insert(self, row):
        self.rows.append(row)
        return True

    def check(self):
        pass


def test_pallet_store_logs_with_prefix(tmp_path) -> None:
    info = []
    table = FakeTable()
    store = ResultStore(table, Spool(str(tmp_path / "p.jsonl")), Spool(str(tmp_path / "p.rej")),
                        info.append, info.append, info.append, log_prefix="pallet_log ")  # fmt: skip
    store.tick()  # 연결 확인
    store.save(pallet_result_to_row(pallet_result()))
    assert table.rows and any(x.startswith("pallet_log db_committed box_id=S-001") for x in info)
