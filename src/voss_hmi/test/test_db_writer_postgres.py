"""DbWriter + docker/db 스키마·계정 시험 — 실제 PostgreSQL 이 있을 때만 돈다.

실행 예 (docker/db 를 띄운 공용 PC):
  VOSS_TEST_DB_PORT=5432 VOSS_DB_LOGGER_PASSWORD=... VOSS_DB_WEB_PASSWORD=... \
    PYTHONPATH=. pytest -q test/test_db_writer_postgres.py
환경 변수 VOSS_TEST_DB_PORT 가 없으면 건너뛴다(CI·노트북). 시험 행은 box_id 'TEST-' 로 시작한다.
"""

import os
import uuid

import pytest

# 모듈 수준 importorskip 은 psycopg2 가 없을 때 같이 수집되는 다른 시험 파일까지 모두 수집을 멈춘다(pytest 7.4,
# colcon test 가 voss_hmi 시험 41개를 하나도 안 돌림) → import 실패만 잡고 이 파일의 시험만 건너뛴다
try:
    import psycopg2
except ImportError:  # 개발 PC (python3-psycopg2 없음)
    psycopg2 = None

from voss_hmi.db_writer import DbError, DbWriter, RowRejected  # noqa: E402
from voss_hmi.log_logic import pallet_result_to_row, result_to_row  # noqa: E402

PORT = os.getenv("VOSS_TEST_DB_PORT")
pytestmark = pytest.mark.skipif(
    psycopg2 is None or not PORT,
    reason="psycopg2 또는 VOSS_TEST_DB_PORT 없음 — 실제 DB 시험 건너뜀",
)


def connect_as(user: str, password_env: str):
    return psycopg2.connect(
        host="127.0.0.1",
        port=int(PORT),
        dbname="voss",
        user=user,
        password=os.getenv(password_env, ""),
    )


def make_writer() -> DbWriter:
    return DbWriter(
        host="127.0.0.1",
        port=int(PORT),
        dbname="voss",
        user="voss_logger",
        password=os.getenv("VOSS_DB_LOGGER_PASSWORD", ""),
    )


def make_row(**changes) -> dict:
    result = {
        "box_id": f"TEST-{uuid.uuid4().hex[:12]}",
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
        "attempts": 3,
        "stamp": (1_791_610_212, 500_000_000),
        "started_at": (0, 0),
    }
    result.update(changes)
    return result_to_row(result)


def select_row(box_id: str) -> dict:
    with connect_as("voss_web", "VOSS_DB_WEB_PASSWORD") as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM sort_log WHERE box_id = %s", (box_id,))
        names = [column.name for column in cursor.description]
        values = cursor.fetchone()
    return dict(zip(names, values, strict=True)) if values else {}


def test_insert_then_same_box_id_select_returns_the_row():
    writer = make_writer()
    row = make_row()
    assert writer.insert(row) is True
    saved = select_row(row["box_id"])  # G0 증거: 같은 box_id 를 다른 계정으로 조회
    assert saved["result"] == "PLACED" and saved["zone"] == "A"
    assert saved["retries"] == 2  # max(attempts − 1, 0), DB 가 계산
    assert saved["started_at"] is None  # 0 시각 → NULL
    writer.close()


def test_duplicate_box_id_does_nothing():
    writer = make_writer()
    row = make_row()
    assert writer.insert(row) is True
    second = dict(row, result="FAILED")
    assert writer.insert(second) is False
    assert select_row(row["box_id"])["result"] == "PLACED"
    writer.close()


def test_invalid_zone_is_rejected_and_connection_still_works():
    writer = make_writer()
    with pytest.raises(RowRejected):
        writer.insert(make_row(zone="X"))
    assert writer.insert(make_row()) is True  # 같은 연결로 계속 쓸 수 있다
    writer.close()


def test_logger_account_cannot_update_or_delete():
    row = make_row()
    make_writer().insert(row)
    with connect_as("voss_logger", "VOSS_DB_LOGGER_PASSWORD") as conn, conn.cursor() as cursor:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute("DELETE FROM sort_log WHERE box_id = %s", (row["box_id"],))


def test_web_account_cannot_insert_into_sort_log():
    with connect_as("voss_web", "VOSS_DB_WEB_PASSWORD") as conn, conn.cursor() as cursor:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute("INSERT INTO sort_log (box_id) VALUES ('TEST-web')")


def test_wrong_port_raises_db_error_quickly():
    writer = DbWriter("127.0.0.1", 1, "voss", "voss_logger", "x", timeout_s=1.0)
    with pytest.raises(DbError):
        writer.check()


# ---------- Sprint 2 (S2-T07, BRD v1.5): sort_log.slot · pallet_log · ListPlacements ----------
def make_pallet_row(box_id: str, session_id: str, outcome: str = "DONE", **changes) -> dict:
    result = {
        "run_id": f"T{uuid.uuid4().hex[:15]}",
        "session_id": session_id,
        "box_id": box_id,
        "dong": "역삼동",
        "route_index": 0,
        "zone": "A",
        "slot": 0,
        "pallet_slot": 9 if outcome in ("DONE", "FAILED") else -1,
        "pallet_col": 3 if outcome in ("DONE", "FAILED") else 0,
        "pallet_lane": 2 if outcome in ("DONE", "FAILED") else 0,
        "pallet_layer": 1 if outcome in ("DONE", "FAILED") else 0,
        "outcome": outcome,
        "reason": "",
        "attempts": 1 if outcome in ("DONE", "FAILED") else 0,
        "stamp": (1_791_610_300, 0),
    }
    result.update(changes)
    return pallet_result_to_row(result)


def test_slot_and_pallet_log_and_list_placements():
    writer = make_writer()
    session = f"TEST{uuid.uuid4().hex[:16]}"
    placed = make_row(session_id=session, slot=2)
    overflow = make_row(session_id=session, slot=3)
    held = make_row(session_id=session, zone="HOLD", outcome="HELD", slot=0)
    for row in (placed, overflow, held):
        assert writer.insert(row) is True
    assert select_row(placed["box_id"])["slot"] == 2
    assert writer.insert_pallet(make_pallet_row(placed["box_id"], session)) is True
    assert writer.insert_pallet(make_pallet_row(overflow["box_id"], session, "OVERFLOW")) is True
    rows = writer.list_placements(session)  # PLACED·A/B/C 만, palletized = DONE 행이 있나
    got = {r[0]: (r[2], r[3], r[5]) for r in rows}
    assert got == {placed["box_id"]: ("A", 2, True), overflow["box_id"]: ("A", 3, False)}
    writer.close()
