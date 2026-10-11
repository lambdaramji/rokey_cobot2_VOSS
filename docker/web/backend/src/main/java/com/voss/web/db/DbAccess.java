// PostgreSQL 접속을 읽기 계정과 session_plan 쓰기 계정으로 분리한다.
// 입력: 런타임 DB 환경 변수. 출력: JDBC Connection.
// 근거: docs/interfaces/web_api.md, ADR-0006 (sort_log 쓰기 금지).
package com.voss.web.db;

import com.voss.web.api.ApiException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class DbAccess {
    private static final Logger LOGGER = LoggerFactory.getLogger(DbAccess.class);
    /** 통계·이력에서는 SELECT 전용 자격 증명으로 접속한다. */
    public Connection openRead() {
        return connect("VOSS_DB_READ_URL", "VOSS_DB_READ_USER", "VOSS_DB_READ_PASSWORD", true);
    }

    /** 오직 session_plan 관리에만 사용하는 별도 계정으로 접속한다. */
    public Connection openPlan() {
        return connect("VOSS_DB_PLAN_URL", "VOSS_DB_PLAN_USER", "VOSS_DB_PLAN_PASSWORD", false);
    }

    /** 자격 증명을 로그에 노출하지 않고 연결 실패를 DB_ERROR로 바꾼다. */
    private Connection connect(String urlKey, String userKey, String passwordKey, boolean readOnly) {
        String url = System.getenv(urlKey);
        String user = System.getenv(userKey);
        String password = System.getenv(passwordKey);
        if (isMissing(url) || isMissing(user) || isMissing(password)) {
            throw dbError("DB 접속 환경 변수가 설정되지 않았습니다.");
        }
        try {
            Connection connection = DriverManager.getConnection(url, user, password);
            connection.setReadOnly(readOnly);
            return connection;
        } catch (SQLException exception) {
            LOGGER.warn("PostgreSQL 접속 실패: SQLState={}", exception.getSQLState());
            throw dbError("PostgreSQL 연결에 실패했습니다.");
        }
    }

    /** 입력 설정이 빠졌는지 확인한다. */
    private boolean isMissing(String value) { return value == null || value.isBlank(); }

    /** 외부에 SQL·비밀번호를 공개하지 않는 오류를 만든다. */
    public ApiException dbError(String detail) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DB_ERROR", detail);
    }
}
