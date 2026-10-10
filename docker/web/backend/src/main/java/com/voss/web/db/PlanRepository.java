// 웹 고유 테이블 session_plan의 수량만 관리한다.
// 입력: session_id·planned. 출력: 예정 수량 조회 및 저장.
// 근거: docs/interfaces/web_api.md (sort_log 작성 금지).
package com.voss.web.db;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.stereotype.Repository;

@Repository
public class PlanRepository {
    private static final int DEFAULT_PLANNED = 10;
    private final DbAccess db;

    /** session_plan 접근 권한이 있는 DB 접속 도구를 받는다. */
    public PlanRepository(DbAccess db) { this.db = db; }

    /** 세션별 값을 먼저 확인하고, 없으면 next 또는 기본값을 사용한다. */
    public int planned(String session) {
        String key = session.isEmpty() ? "next" : session;
        Integer value = read(key);
        if (value != null) { return value; }
        if (!session.isEmpty()) {
            Integer nextValue = read("next");
            if (nextValue != null) {
                attachPending(session);
                return nextValue;
            }
        }
        return DEFAULT_PLANNED;
    }

    /** 세션이 없으면 next에 저장해 첫 세션에서도 쓸 수 있도록 한다. */
    public void save(String session, int planned) {
        String key = session.isEmpty() ? "next" : session;
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

    /** 첫 세션 조회 시 예정 수량 next를 실제 session_id로 옮긴다. */
    private void attachPending(String session) {
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

    /** 저장한 수량을 조회하며 미등록 값은 null로 구분한다. */
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
