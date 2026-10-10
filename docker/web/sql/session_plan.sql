-- T13 #22 웹에서 수량을 기록하는 별도 테이블 (sort_log는 sort_logger만 쓴다).
-- 공용 PC PostgreSQL 관리자가 실행하고 별도 웹 계획 계정에 이 테이블만 쓰기 권한을 준다.
CREATE TABLE IF NOT EXISTS session_plan (
    session_id varchar(24) PRIMARY KEY,
    planned integer NOT NULL CHECK (planned BETWEEN 1 AND 100),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);
