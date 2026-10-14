"""PostgreSQL `sort_log`·`pallet_log` 에 한 행씩 쓰고 ListPlacements 를 조회하는 얇은 계층 (psycopg2).

- 한 행마다 INSERT → COMMIT. commit 이 성공적으로 돌아온 뒤에만 "저장됨" 으로 본다(#54: inserted_at 은 commit 시각이 아님).
- 같은 box_id 가 다시 오면 `ON CONFLICT DO NOTHING` 으로 넘기고 "중복" 으로 알려 준다(voss_msgs.md).
- 연결·쓰기 실패는 DbError 로 올린다. 무엇을 할지(스풀에 쌓기)는 노드가 정한다.
- 행 자체가 스키마에 안 맞으면(허용 외 zone 등) RowRejected 로 올린다. 다시 보내도 계속 실패하므로
  스풀에 넣으면 뒤의 행까지 모두 막힌다 — 노드가 따로 보관하고 넘어간다.

- 연결할 때 스키마를 본다(Sprint 2): `sort_log.slot` 이 없으면(마이그레이션 전 DB) slot 없이 쓰고 `schema_warning` 에
  남긴다 — 열이 없어 모든 INSERT 가 실패해 결과가 스풀에만 쌓이는 일을 막는다. `pallet_log` 가 없으면 그 쓰기·조회만 실패.

관련 문서: docker/db/init/01_schema.sql, docs/interfaces/voss_msgs.md (DB sort_log 대응, PalletResult, ListPlacements)
"""

from __future__ import annotations

from voss_hmi.log_logic import PALLET_LOG_COLUMNS, SORT_LOG_COLUMNS


def insert_sql(table: str, columns: list[str], key: str) -> str:
    """INSERT … ON CONFLICT (key) DO NOTHING RETURNING box_id — 새로 들어갔는지 RETURNING 으로 안다."""
    return (
        f"INSERT INTO {table} ("
        + ", ".join(columns)
        + ") VALUES ("
        + ", ".join(f"%({name})s" for name in columns)
        + f") ON CONFLICT ({key}) DO NOTHING RETURNING box_id"
    )


def sort_log_columns(has_slot: bool) -> list[str]:
    """마이그레이션 전 DB(slot 열 없음)면 slot 을 빼고 쓴다."""
    return [c for c in SORT_LOG_COLUMNS if has_slot or c != "slot"]


INSERT_SQL = insert_sql("sort_log", SORT_LOG_COLUMNS, "box_id")
PALLET_INSERT_SQL = insert_sql("pallet_log", PALLET_LOG_COLUMNS, "run_id, box_id")
# ListPlacements: 그 세션의 PLACED·A/B/C 행 + 팔레트로 옮겼나(DONE 행이 있나) — voss_msgs.md Placement
PLACEMENTS_SQL = (
    "SELECT s.box_id, s.dong, s.zone, s.slot, s.finished_at, "
    "EXISTS (SELECT 1 FROM pallet_log p WHERE p.box_id = s.box_id AND p.result = 'DONE') "
    "FROM sort_log s WHERE s.session_id = %(session_id)s AND s.result = 'PLACED' "
    "AND s.zone IN ('A', 'B', 'C') ORDER BY s.finished_at, s.box_id"
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
        self._sort_sql = INSERT_SQL
        self._sort_columns = list(SORT_LOG_COLUMNS)
        self.has_pallet_log = True
        self.schema_warning = ""  # 노드가 한 번 로그로 남긴다

    def _connection(self):
        """열린 연결을 돌려준다. 없거나 닫혔으면 새로 연다."""
        import psycopg2  # ROS 없이 log_logic 만 시험할 때는 필요 없어서 여기서 올린다

        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(**self._settings)
                self._detect_schema(self._conn)
            except psycopg2.Error as error:
                self.close()
                raise DbError(f"connect: {type(error).__name__}: {error}".strip()) from error
        return self._conn

    def _detect_schema(self, conn) -> None:
        """sort_log.slot·pallet_log 이 있나 (마이그레이션 20261012_sprint2_pallet.sql 적용 여부)."""
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name IN ('sort_log', 'pallet_log')"
            )
            found: dict[str, set] = {}
            for table, column in cursor.fetchall():
                found.setdefault(table, set()).add(column)
        conn.rollback()
        has_slot = "slot" in found.get("sort_log", set())
        self.has_pallet_log = "pallet_log" in found
        self._sort_columns = sort_log_columns(has_slot)
        self._sort_sql = insert_sql("sort_log", self._sort_columns, "box_id")
        missing = [
            n
            for n, ok in (("sort_log.slot", has_slot), ("pallet_log", self.has_pallet_log))
            if not ok
        ]
        self.schema_warning = (
            f"DB 에 {', '.join(missing)} 없음 — docker/db/migrations/20261012_sprint2_pallet.sql 적용 필요"
            if missing
            else ""
        )

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
        """sort_log 한 행을 쓰고 commit 한다. 새로 들어갔으면 True, 같은 box_id 가 이미 있으면 False."""
        conn = self._connection()  # 연결하며 스키마를 본다 → _sort_sql·_sort_columns
        return self._insert(conn, self._sort_sql, self._sort_columns, row)

    def insert_pallet(self, row: dict) -> bool:
        """pallet_log 한 행 (유일키 run_id + box_id). 테이블이 없으면 DbError(스풀에 남는다)."""
        conn = self._connection()
        if not self.has_pallet_log:
            raise DbError("pallet_log 테이블 없음 — 마이그레이션 필요")
        return self._insert(conn, PALLET_INSERT_SQL, PALLET_LOG_COLUMNS, row)

    def list_placements(self, session_id: str) -> list[tuple]:
        """ListPlacements 조회 행. 실패하면 DbError."""
        import psycopg2

        conn = self._connection()
        if not self.has_pallet_log or "slot" not in self._sort_columns:
            raise DbError(self.schema_warning or "스키마 확인 실패")
        try:
            with conn.cursor() as cursor:
                cursor.execute(PLACEMENTS_SQL, {"session_id": session_id})
                rows = cursor.fetchall()
            conn.rollback()  # 읽기만 했으니 트랜잭션을 닫는다
            return rows
        except psycopg2.Error as error:
            self.close()
            raise DbError(f"list_placements: {type(error).__name__}") from error

    def _insert(self, conn, sql: str, columns: list[str], row: dict) -> bool:
        import psycopg2

        params = {
            name: row.get(name) for name in columns
        }  # 예전 스풀 행처럼 열이 빠져 있어도 NULL 로
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
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
