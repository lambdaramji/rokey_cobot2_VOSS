"""결과 저장 흐름: DB 에 바로 쓰고, 못 쓰면 스풀에 쌓았다가 다시 보낸다 (ROS 없이 pytest 로 시험).

sort_logger 노드는 결과를 받으면 `save()`, 1초마다 `tick()` 을 부르고, `status()` 를 발행하기만 한다.

지키는 규칙 (SRD v1.0 §5 DB, #52 MC-027, voss_msgs.md)
- 결과 1건 = 행 1개. 같은 box_id 는 DB 가 DO NOTHING 으로 넘기고 "duplicate" 로그만 남긴다.
- DB 에 못 쓰면 스풀 파일에 쌓는다. 운전은 막지 않고 상태만 DB_ERROR 로 알린다.
- 스풀에 행이 남아 있는 동안 새 결과도 스풀 뒤에 쌓는다 → 저장 순서가 도착 순서와 같다.
- 스풀은 1 → 2 → 5 → 10 → 30초 간격으로 앞에서부터 다시 보낸다. 중간에 실패하면 남은 행만 남긴다.
- DB 가 행 자체를 거부하면(허용 외 값) 따로 보관하고 넘어간다. 스풀에 넣으면 뒤의 행까지 계속 막힌다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from voss_hmi.db_writer import DbError, RowRejected
from voss_hmi.log_logic import Spool, decide_status, retry_delay_s


class ResultStore:
    def __init__(
        self,
        writer,
        spool: Spool,
        rejected: Spool,
        log_info: Callable[[str], None],
        log_warn: Callable[[str], None],
        log_error: Callable[[str], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """writer 는 insert(row) -> bool, check() 를 가진 객체(DbWriter 또는 시험용 가짜)."""
        self._writer = writer
        self._spool = spool
        self._rejected = rejected
        self._info = log_info
        self._warn = log_warn
        self._error = log_error
        self._clock = clock

        self.ever_connected = False  # 한 번이라도 DB 연결에 성공했나 (아니면 STARTING)
        self.db_ok = False  # 마지막 DB 시도가 성공했나
        self.spool_writable = True  # 마지막 스풀 쓰기가 성공했나
        self.failures_in_a_row = 0
        self.next_retry_at = 0.0  # clock() 기준. 이 시각 전에는 다시 시도하지 않는다

    # ---------- 노드가 부르는 세 가지 ----------
    def save(self, row: dict) -> None:
        """결과 한 행을 저장한다(바로 DB, 안 되면 스풀)."""
        if self._spool.count() > 0 or not self.db_ok:
            self._save_to_spool(row, reason="DB 미연결 또는 스풀 대기 중")
            return
        try:
            self._insert_and_log(row)
        except RowRejected as error:
            self._save_rejected(row, str(error))
        except DbError as error:
            self._mark_db_failure(str(error))
            self._save_to_spool(row, reason=str(error))

    def tick(self) -> None:
        """1초마다 부른다. DB 가 끊겼거나 스풀이 남아 있으면, 기다릴 시간이 지났을 때 다시 시도한다."""
        needs_work = not self.db_ok or self._spool.count() > 0
        if needs_work and self._clock() >= self.next_retry_at:
            self._recover()

    def status(self) -> str:
        """/voss/log/status 에 낼 값."""
        return decide_status(
            ever_connected=self.ever_connected,
            db_ok=self.db_ok,
            spool_rows=self._spool.count(),
            spool_writable=self.spool_writable,
        )

    # ---------- 안쪽 단계 ----------
    def _insert_and_log(self, row: dict) -> None:
        """한 행을 쓰고 결과를 로그로 남긴다. 실패하면 DbError / RowRejected 를 그대로 올린다."""
        inserted = self._writer.insert(row)
        if inserted:
            committed_at = datetime.now(UTC).astimezone().isoformat(timespec="milliseconds")
            # G0 증거: commit 이 돌아온 뒤에 남기는 로그 (inserted_at 은 commit 시각이 아니다)
            self._info(
                f"db_committed box_id={row['box_id']} result={row['result']} zone={row['zone']} "
                f"session={row['session_id']} at={committed_at}"
            )
        else:
            self._warn(f"duplicate box_id={row['box_id']} — 이미 있는 행, 다시 쓰지 않음")

    def _recover(self) -> None:
        """DB 연결을 확인하고, 스풀에 쌓인 행을 앞에서부터 다시 보낸다."""
        rows = self._spool.read_all()
        try:
            if not rows:
                self._writer.check()
            for index, row in enumerate(rows):
                try:
                    self._insert_and_log(row)
                except RowRejected as error:
                    self._save_rejected(row, str(error))  # 이 행만 빼고 다음 행으로
                except DbError:
                    self._spool.rewrite(rows[index:])  # 못 보낸 행(이 행 포함)만 남긴다
                    raise
        except DbError as error:
            self._mark_db_failure(str(error))
            return

        if rows:
            self._spool.rewrite([])
            self._info(f"스풀 {len(rows)}행 재전송 완료")
        self._mark_db_success()

    def _save_to_spool(self, row: dict, reason: str) -> None:
        if self._spool.append(row):
            self.spool_writable = True
            self._warn(f"spooled box_id={row['box_id']} ({reason})")
        else:
            # 스풀에도 못 썼다 = 이 결과는 유실될 수 있다. 숨기지 않고 크게 남긴다
            self.spool_writable = False
            self._error(
                f"LOST box_id={row['box_id']} result={row['result']} — 스풀 파일에도 쓰지 못했다"
            )

    def _save_rejected(self, row: dict, detail: str) -> None:
        self._rejected.append(row)
        self._error(
            f"REJECTED box_id={row['box_id']} ({detail}) — {self._rejected.path} 에 보관, 확인 필요"
        )

    def _mark_db_success(self) -> None:
        if not self.ever_connected:
            self._info("DB 연결 성공")
        self.ever_connected = True
        self.db_ok = True
        self.failures_in_a_row = 0
        self.next_retry_at = 0.0

    def _mark_db_failure(self, detail: str) -> None:
        self.db_ok = False
        self.failures_in_a_row += 1
        wait_s = retry_delay_s(self.failures_in_a_row)
        self.next_retry_at = self._clock() + wait_s
        self._warn(f"DB 실패 ({detail}) — {wait_s}초 뒤 다시 시도")
