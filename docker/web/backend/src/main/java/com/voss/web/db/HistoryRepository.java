// 공식 집계와 이력은 PostgreSQL sort_log만 조회한다.
// 입력: 확정된 세션 및 조회 필터. 출력: 집계·결과·CSV에 쓸 행.
// 근거: docs/interfaces/web_api.md (#52 MC-021·022).
package com.voss.web.db;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class HistoryRepository {
    private final DbAccess db;
    /** 읽기 전용 DB 연결 도구를 전달받는다. */
    public HistoryRepository(DbAccess db) { this.db = db; }

    /** 분류된 동별 건수를 공식 DB에서 계산한다. */
    public long placedByDong(String session, String dong) {
        return count("result = 'PLACED' AND dong = ?", session, dong);
    }

    /** 보류된 건수를 공식 DB에서 계산한다. */
    public long held(String session) { return count("result = 'HELD'", session, null); }

    /** 계획 수량 계산을 위한 종료된 처리 건수를 센다. PASSED는 제외한다. */
    public long completed(String session) {
        return count("result IN ('PLACED','HELD','FAILED')", session, null);
    }

    /** 현재 세션에서 특정 분류 결과가 몇 개인지 계산한다. */
    public long outcome(String session, String result) {
        return count("result = ?", session, result);
    }

    /** 분류 구역별 PLACED/HELD 건수를 계산한다. */
    public Map<String, Long> zones(String session) {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (String zone : List.of("A", "B", "C", "RECHECK", "HOLD")) {
            counts.put(zone, count("zone = ? AND result IN ('PLACED','HELD')", session, zone));
        }
        return counts;
    }

    /** 이력 필터를 바인드 변수로 적용하고 최근 기록부터 조회한다. */
    public List<Map<String,Object>> results(String session, List<String> outcomes, int limit) {
        StringBuilder sql = new StringBuilder("SELECT * FROM sort_log WHERE 1=1");
        List<Object> parameters = new ArrayList<>();
        appendSession(sql, parameters, session);
        if (!outcomes.isEmpty()) {
            sql.append(" AND result IN (");
            for (int index = 0; index < outcomes.size(); index++) {
                if (index > 0) { sql.append(','); }
                sql.append('?');
                parameters.add(outcomes.get(index));
            }
            sql.append(')');
        }
        sql.append(" ORDER BY finished_at DESC NULLS LAST LIMIT ?");
        parameters.add(limit);
        return queryRows(sql.toString(), parameters);
    }

    /** 전체 sort_log 컬럼과 초 단위 cycle_s를 CSV용으로 조회한다. */
    public List<Map<String,Object>> exportRows(String session) {
        StringBuilder sql = new StringBuilder("SELECT *, EXTRACT(EPOCH FROM (finished_at - started_at)) AS cycle_s FROM sort_log WHERE 1=1");
        List<Object> parameters = new ArrayList<>();
        appendSession(sql, parameters, session);
        sql.append(" ORDER BY finished_at DESC NULLS LAST");
        return queryRows(sql.toString(), parameters);
    }

    /** 집계 SQL의 조건은 코드 내부의 고정 문자열로만 사용한다. */
    private long count(String condition, String session, String argument) {
        StringBuilder sql = new StringBuilder("SELECT COUNT(*) FROM sort_log WHERE ");
        sql.append(condition);
        List<Object> parameters = new ArrayList<>();
        if (argument != null) { parameters.add(argument); }
        appendSession(sql, parameters, session);
        try (Connection connection = db.openRead();
             PreparedStatement statement = connection.prepareStatement(sql.toString())) {
            bind(statement, parameters);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                return result.getLong(1);
            }
        } catch (SQLException exception) {
            throw db.dbError("sort_log 집계 조회에 실패했습니다.");
        }
    }

    /** 전체 조회에는 세션 조건을 적용하지 않는다. */
    private void appendSession(StringBuilder sql, List<Object> parameters, String session) {
        if (!"all".equals(session)) {
            sql.append(" AND session_id = ?");
            parameters.add(session);
        }
    }

    /** 파라미터 바인딩을 한 곳에서 처리한다. */
    private void bind(PreparedStatement statement, List<Object> parameters) throws SQLException {
        for (int index = 0; index < parameters.size(); index++) {
            statement.setObject(index + 1, parameters.get(index));
        }
    }

    /** DB 컬럼 이름 그대로 JSON 맵에 기록한다. */
    private List<Map<String,Object>> queryRows(String sql, List<Object> parameters) {
        List<Map<String,Object>> rows = new ArrayList<>();
        try (Connection connection = db.openRead();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            bind(statement, parameters);
            try (ResultSet result = statement.executeQuery()) {
                ResultSetMetaData metadata = result.getMetaData();
                while (result.next()) {
                    Map<String,Object> row = new LinkedHashMap<>();
                    for (int column = 1; column <= metadata.getColumnCount(); column++) {
                        Object value = result.getObject(column);
                        if (value instanceof Timestamp stamp) { value = stamp.toInstant().toString(); }
                        row.put(metadata.getColumnLabel(column), value);
                    }
                    rows.add(row);
                }
            }
        } catch (SQLException exception) {
            throw db.dbError("sort_log 이력 조회에 실패했습니다.");
        }
        return rows;
    }
}
