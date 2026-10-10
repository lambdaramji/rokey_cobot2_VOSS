// MQTT 수신 시점의 session_plan 연결을 JDBC 모의 객체로 검증한다.
// 입력: 모의 DB Connection, PreparedStatement, ResultSet.
// 출력: 조회 시 부작용 없음, 트랜잭션·롤백·sort_log 쓰기 금지 증거.
// 근거: docs/interfaces/web_api.md (#68), ADR-0006.
package com.voss.web.db;

import com.voss.web.api.ApiException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class PlanRepositoryTest {
    private static final String SESSION = "20261010T143012-a3f9";
    private final DbAccess db = mock(DbAccess.class);
    private final PlanRepository plans = new PlanRepository(db);

    /** 세션이 없으면 DB에 접근하지 않고 next 연결을 건너뛴다. */
    @Test
    void testEmptySessionCannotConsumeNextPlan() {
        plans.attachPending("");
        verifyNoInteractions(db);
    }

    /** GET 조회는 기존 세션 행만 읽고 next를 이동하지 않는다. */
    @Test
    void testReadingSessionDoesNotAttachPendingPlan() throws Exception {
        Connection connection = mock(Connection.class);
        PreparedStatement select = mock(PreparedStatement.class);
        ResultSet result = mock(ResultSet.class);
        when(db.openPlan()).thenReturn(connection);
        when(connection.prepareStatement(startsWith("SELECT planned"))).thenReturn(select);
        when(select.executeQuery()).thenReturn(result);
        when(result.next()).thenReturn(false);

        assertEquals(10, plans.planned(SESSION));
        verify(connection, times(1)).prepareStatement(anyString());
        verify(connection, never()).commit();
    }

    /** 새 세션 연결은 session_plan에만 트랜잭션으로 쓰고 commit한다. */
    @Test
    void testAttachingNextPlanUsesTransactionWithoutWritingSortLog() throws Exception {
        Connection connection = mock(Connection.class);
        PreparedStatement insert = mock(PreparedStatement.class);
        PreparedStatement delete = mock(PreparedStatement.class);
        when(db.openPlan()).thenReturn(connection);
        when(connection.prepareStatement(startsWith("INSERT INTO session_plan"))).thenReturn(insert);
        when(connection.prepareStatement(startsWith("DELETE FROM session_plan"))).thenReturn(delete);

        plans.attachPending(SESSION);

        ArgumentCaptor<String> sql = ArgumentCaptor.forClass(String.class);
        verify(connection, times(2)).prepareStatement(sql.capture());
        List<String> statements = sql.getAllValues();
        assertTrue(statements.stream().allMatch(query -> query.contains("session_plan")));
        assertTrue(statements.get(0).contains("ON CONFLICT (session_id) DO NOTHING"));
        verify(insert).setString(1, SESSION);
        verify(connection).setAutoCommit(false);
        verify(connection).commit();
        verify(connection, never()).rollback();
    }

    /** SQL 오류가 발생하면 이전 next를 삭제하지 않고 롤백한다. */
    @Test
    void testFailedAttachRollsBackTransaction() throws Exception {
        Connection connection = mock(Connection.class);
        PreparedStatement insert = mock(PreparedStatement.class);
        PreparedStatement delete = mock(PreparedStatement.class);
        when(db.openPlan()).thenReturn(connection);
        when(connection.prepareStatement(startsWith("INSERT INTO session_plan"))).thenReturn(insert);
        when(connection.prepareStatement(startsWith("DELETE FROM session_plan"))).thenReturn(delete);
        when(insert.executeUpdate()).thenThrow(new SQLException("test-only"));
        when(db.dbError(anyString())).thenReturn(new ApiException(
                HttpStatus.SERVICE_UNAVAILABLE, "DB_ERROR", "테스트 오류"));

        ApiException failure = assertThrows(ApiException.class, () -> plans.attachPending(SESSION));
        assertEquals("DB_ERROR", failure.code());
        verify(connection).rollback();
        verify(connection, never()).commit();
    }
}
