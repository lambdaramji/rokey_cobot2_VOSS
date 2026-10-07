"""PostgreSQL `sort_log` 에 한 행씩 쓰는 얇은 계층 (psycopg2).

- 한 행마다 INSERT → COMMIT. commit 이 성공적으로 돌아온 뒤에만 "저장됨" 으로 본다(#54: inserted_at 은 commit 시각이 아님).
- 같은 box_id 가 다시 오면 `ON CONFLICT DO NOTHING` 으로 넘기고 "중복" 으로 알려 준다(voss_msgs.md).
- 연결·쓰기 실패는 DbError 로 올린다. 무엇을 할지(스풀에 쌓기)는 노드가 정한다.
- 행 자체가 스키마에 안 맞으면(허용 외 zone 등) RowRejected 로 올린다. 다시 보내도 계속 실패하므로
  스풀에 넣으면 뒤의 행까지 모두 막힌다 — 노드가 따로 보관하고 넘어간다.

관련 문서: docker/db/init/01_schema.sql, docs/interfaces/voss_msgs.md (DB sort_log 대응)
"""

from __future__ import annotations

from voss_hmi.log_logic import SORT_LOG_COLUMNS

INSERT_SQL = (
    "INSERT INTO sort_log ("
    + ", ".join(SORT_LOG_COLUMNS)
    + ") VALUES ("
    + ", ".join(f"%({name})s" for name in SORT_LOG_COLUMNS)
    + ") ON CONFLICT (box_id) DO NOTHING RETURNING box_id"
)


class DbError(Exception):
    """DB 에 연결하지 못했거나 쓰지 못했다. 나중에 다시 보내면 될 수 있다."""


class RowRejected(Exception):
    """DB 가 이 행 자체를 거부했다(CHECK·형식 위반). 다시 보내도 같은 결과다."""


class DbWriter:
    """sort_log 쓰기 전용 연결 하나를 관리한다. 끊기면 다음 호출 때 다시 연결한다."""

    def __init__(
        self,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: str,
        timeout_s: float = 2.0,
    ) -> None:
        self._settings = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password,
            "connect_timeout": max(int(timeout_s), 1),
            # 쿼리 하나가 오래 걸려 ROS 콜백이 멈추지 않게 한다
            "options": f"-c statement_timeout={int(timeout_s * 1000)}",
        }
        self._conn = None

    def _connection(self):
        """열린 연결을 돌려준다. 없거나 닫혔으면 새로 연다."""
        import psycopg2  # ROS 없이 log_logic 만 시험할 때는 필요 없어서 여기서 올린다

        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(**self._settings)
            except psycopg2.Error as error:
                raise DbError(f"connect: {type(error).__name__}: {error}".strip()) from error
        return self._conn

    def check(self) -> None:
        """연결이 살아 있는지 `SELECT 1` 로 확인한다. 실패하면 DbError."""
        import psycopg2

        conn = self._connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            conn.rollback()  # 읽기만 했으니 트랜잭션을 닫는다
        except psycopg2.Error as error:
            self.close()
            raise DbError(f"check: {type(error).__name__}") from error

    def insert(self, row: dict) -> bool:
        """한 행을 쓰고 commit 한다. 새로 들어갔으면 True, 같은 box_id 가 이미 있으면 False."""
        import psycopg2

        conn = self._connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(INSERT_SQL, row)
                inserted = cursor.fetchone() is not None  # DO NOTHING 이면 RETURNING 결과가 없다
            conn.commit()
            return inserted
        except (psycopg2.DataError, psycopg2.IntegrityError) as error:
            # box_id 중복은 위의 DO NOTHING 이 처리하므로, 여기 오는 것은 CHECK·형식 위반이다
            conn.rollback()
            raise RowRejected(f"{type(error).__name__}: {error}".strip()) from error
        except psycopg2.Error as error:
            # 연결이 끊긴 경우가 많아 연결을 버리고 다음에 새로 연다
            self.close()
            raise DbError(f"insert: {type(error).__name__}") from error

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 — 닫는 중 오류는 무시한다
                pass
        self._conn = None
