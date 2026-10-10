// Spring Boot의 session_plan만 조회·변경한다. sort_log에는 쓰지 않는다.
// 입력: session_id와 planned, 새 SortState.session_id.
// 출력: 예정 수량 또는 next → 실제 세션에 연결된 DB 기록.
// 근거: docs/interfaces/web_api.md (#68), ADR-0006.
package com.voss.web.db;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.stereotype.Repository;

@Repository
public class PlanRepository {
    private static final int DEFAULT_PLANNED = 10;
    private static final String NEXT_SESSION = "next";
    private final DbAccess db;

    /** session_plan 접근 도구를 받는다. */
    public PlanRepository(DbAccess db) { this.db = db; }

    /** 읽기 전용으로 예정 수량을 조회한다. 새 세션 연결은 MQTT 수신 때만 한다. */
    public int planned(String session) {
        String key = session.isEmpty() ? NEXT_SESSION : session;
        Integer value = read(key);
        if (value != null) { return value; }
        return DEFAULT_PLANNED;
    }

    /** 첫 start 전에는 next에, 시작 후에는 실제 session_id에 저장한다. */
    public void save(String session, int planned) {
        String key = session.isEmpty() ? NEXT_SESSION : session;
        String sql = "INSERT INTO session_plan(session_id, planned, updated_at) VALUES (?, ?, NOW()) "
                + "ON CONFLICT (session_id) DO UPDATE SET planned=EXCLUDED.planned, updated_at=NOW()";
        try (Connection connection = db.openPlan();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, key);
            statement.setInt(2, planned);
            statement.executeUpdate();
            if (!session.isEmpty()) {
                try (PreparedStatement removeNext = connection.prepareStatement(
                        "DELETE FROM session_plan WHERE session_id = 'next'")) {
                    removeNext.executeUpdate();
                }
            }
        } catch (SQLException exception) {
            throw db.dbError("session_plan 저장에 실패했습니다.");
        }
    }

    /** 새 MQTT 세션 수신 시 next를 붙인다. 기존 세션값은 덮어쓰지 않는다. */
    public void attachPending(String session) {
        if (session == null || session.isEmpty()) { return; }
        String insert = "INSERT INTO session_plan (session_id, planned, updated_at) "
                + "SELECT ?, planned, NOW() FROM session_plan WHERE session_id='next' "
                + "ON CONFLICT (session_id) DO NOTHING";
        try (Connection connection = db.openPlan()) {
            connection.setAutoCommit(false);
            try (PreparedStatement insertStatement = connection.prepareStatement(insert);
                 PreparedStatement deleteStatement = connection.prepareStatement(
                         "DELETE FROM session_plan WHERE session_id='next'")) {
                insertStatement.setString(1, session);
                insertStatement.executeUpdate();
                deleteStatement.executeUpdate();
                connection.commit();
            } catch (SQLException exception) {
                connection.rollback();
                throw exception;
            }
        } catch (SQLException exception) {
            throw db.dbError("다음 세션 투입 수량 연결에 실패했습니다.");
        }
    }

    /** 지정된 세션 행을 조회하고 없으면 null을 반환한다. */
    private Integer read(String key) {
        try (Connection connection = db.openPlan();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT planned FROM session_plan WHERE session_id = ?")) {
            statement.setString(1, key);
            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) { return result.getInt(1); }
                return null;
            }
        } catch (SQLException exception) {
            throw db.dbError("session_plan 조회에 실패했습니다.");
        }
    }
}
