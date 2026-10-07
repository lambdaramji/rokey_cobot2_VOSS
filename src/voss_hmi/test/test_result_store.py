"""ResultStore 시험: 바로 저장 / 스풀 / 재전송 순서 / 거부 행 / 상태 (가짜 DB, ROS 없음)."""

import pytest
from voss_hmi.db_writer import DbError, RowRejected
from voss_hmi.log_logic import Spool
from voss_hmi.result_store import ResultStore


class FakeWriter:
    """DbWriter 자리에 끼우는 가짜. down=True 면 연결 실패를 흉내 낸다."""

    def __init__(self):
        self.down = False
        self.rows = {}  # box_id → row (DB 안의 행)
        self.reject_box_ids = set()

    def check(self):
        if self.down:
            raise DbError("connect: OperationalError")

    def insert(self, row):
        if self.down:
            raise DbError("insert: OperationalError")
        if row["box_id"] in self.reject_box_ids:
            raise RowRejected("CheckViolation")
        if row["box_id"] in self.rows:
            return False  # ON CONFLICT DO NOTHING
        self.rows[row["box_id"]] = row
        return True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    writer = FakeWriter()
    clock = FakeClock()
    logs = []
    store = ResultStore(
        writer=writer,
        spool=Spool(str(tmp_path / "sort_log.jsonl")),
        rejected=Spool(str(tmp_path / "sort_log.jsonl.rejected")),
        log_info=lambda text: logs.append(("info", text)),
        log_warn=lambda text: logs.append(("warn", text)),
        log_error=lambda text: logs.append(("error", text)),
        clock=clock,
    )
    return store, writer, clock, logs


def row(box_id, result="PLACED"):
    return {"box_id": box_id, "result": result, "zone": "A", "session_id": "s1"}


def test_starting_until_first_tick_connects(setup):
    store, writer, clock, logs = setup
    assert store.status() == "STARTING"
    store.tick()
    assert store.status() == "OK"


def test_result_is_committed_and_logged_as_g0_evidence(setup):
    store, writer, clock, logs = setup
    store.tick()
    store.save(row("b1"))
    assert "b1" in writer.rows
    assert any(
        level == "info" and text.startswith("db_committed box_id=b1") for level, text in logs
    )


def test_duplicate_box_id_is_not_written_twice(setup):
    store, writer, clock, logs = setup
    store.tick()
    store.save(row("b1"))
    store.save(row("b1", result="FAILED"))
    assert writer.rows["b1"]["result"] == "PLACED"  # 처음 행이 그대로
    assert any(text.startswith("duplicate box_id=b1") for _, text in logs)


def test_db_down_spools_and_reports_db_error_without_blocking(setup):
    store, writer, clock, logs = setup
    store.tick()
    writer.down = True
    store.save(row("b1"))
    assert writer.rows == {}
    assert store.status() == "DB_ERROR"


def test_spool_is_resent_in_order_after_db_comes_back(setup):
    store, writer, clock, logs = setup
    store.tick()
    writer.down = True
    for box_id in ["b1", "b2", "b3"]:
        store.save(row(box_id))

    writer.down = False
    clock.now = 1.0  # 첫 재시도는 1초 뒤
    store.tick()

    assert list(writer.rows) == ["b1", "b2", "b3"]
    assert store.status() == "OK"


def test_new_result_waits_behind_spool_to_keep_order(setup):
    store, writer, clock, logs = setup
    store.tick()
    writer.down = True
    store.save(row("b1"))
    writer.down = False
    store.save(row("b2"))  # DB 는 살아났지만 b1 이 아직 스풀에 있다
    assert writer.rows == {}

    clock.now = 1.0
    store.tick()
    assert list(writer.rows) == ["b1", "b2"]


def test_retry_waits_1_2_5_10_then_30_seconds(setup):
    store, writer, clock, logs = setup
    writer.down = True
    waits = []
    for _ in range(6):
        store.tick()  # 실패 → 다음 시각 계산
        waits.append(store.next_retry_at - clock.now)
        clock.now = store.next_retry_at
    assert waits == [1, 2, 5, 10, 30, 30]


def test_tick_does_not_retry_before_the_wait_is_over(setup):
    store, writer, clock, logs = setup
    writer.down = True
    store.tick()  # 실패, 1초 뒤 재시도
    writer.down = False
    clock.now = 0.5
    store.tick()
    assert store.status() == "STARTING"  # 아직 시도하지 않았다
    clock.now = 1.0
    store.tick()
    assert store.status() == "OK"


def test_partial_resend_keeps_only_unsent_rows(setup, tmp_path):
    store, writer, clock, logs = setup
    store.tick()
    writer.down = True
    for box_id in ["b1", "b2", "b3"]:
        store.save(row(box_id))

    # b2 를 보내는 순간 다시 끊기는 경우
    original_insert = writer.insert

    def insert_then_drop(r):
        if r["box_id"] == "b2":
            writer.down = True
        return original_insert(r)

    writer.down = False
    writer.insert = insert_then_drop
    clock.now = 1.0
    store.tick()

    assert list(writer.rows) == ["b1"]
    remaining = Spool(str(tmp_path / "sort_log.jsonl")).read_all()
    assert [r["box_id"] for r in remaining] == ["b2", "b3"]


def test_rejected_row_is_kept_aside_and_does_not_block_others(setup, tmp_path):
    store, writer, clock, logs = setup
    store.tick()
    writer.reject_box_ids.add("bad")
    store.save(row("bad"))
    store.save(row("b2"))

    assert list(writer.rows) == ["b2"]
    assert store.status() == "OK"
    kept = Spool(str(tmp_path / "sort_log.jsonl.rejected")).read_all()
    assert [r["box_id"] for r in kept] == ["bad"]
    assert any(level == "error" and "REJECTED box_id=bad" in text for level, text in logs)


def test_lost_result_is_logged_loudly_when_spool_cannot_be_written(setup):
    store, writer, clock, logs = setup
    store.tick()
    writer.down = True
    store._spool = Spool("/proc/voss-cannot-write/sort_log.jsonl")
    store.save(row("b1"))
    assert store.status() == "SPOOL_FULL"
    assert any(level == "error" and "LOST box_id=b1" in text for level, text in logs)
