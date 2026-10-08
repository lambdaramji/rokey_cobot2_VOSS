-- VOSS 작업 로그 DB 스키마 (docker/db). 컨테이너를 처음 만들 때 한 번만 실행된다.
-- 계약: docs/interfaces/voss_msgs.md "DB sort_log 대응" (#52 MC-003·020, #54), web_api.md (session_plan)
-- 쓰기는 sort_logger(voss_logger) 하나, Spring Boot(voss_web) 는 sort_log 를 읽기만 한다 (ADR-0006).

-- SortResult 1건 = 1행. 같은 box_id 가 다시 오면 sort_logger 가 ON CONFLICT DO NOTHING 으로 넘긴다.
CREATE TABLE sort_log (
  box_id        varchar(32)  PRIMARY KEY,            -- 예 20261010T143012-a3f9-004 (24자)
  session_id    varchar(24)  NOT NULL,               -- 예 20261010T143012-a3f9 (20자)
  track_id      integer,                             -- 참고용 (BoxTrack.track_id)
  code          varchar(16)  NOT NULL DEFAULT '',    -- 분류코드 예 S07-01
  dong          varchar(16)  NOT NULL DEFAULT '',
  confidence    real,                                -- 0~1
  decided_by    varchar(8)   NOT NULL CHECK (decided_by IN ('OCR', 'RECHECK', 'OPERATOR', 'NONE')),
  zone          varchar(8)   NOT NULL DEFAULT '' CHECK (zone IN ('A', 'B', 'C', 'RECHECK', 'HOLD', '')),
  result        varchar(8)   NOT NULL CHECK (result IN ('PLACED', 'HELD', 'FAILED', 'PASSED')),  -- ← outcome
  reason        varchar(24)  NOT NULL DEFAULT '',
  raw_text      text         NOT NULL DEFAULT '',
  second_region varchar(16)  NOT NULL DEFAULT '',    -- ← dong_alt
  rule_version  varchar(16)  NOT NULL DEFAULT '',
  attempts      smallint     NOT NULL DEFAULT 0,
  retries       smallint     GENERATED ALWAYS AS (GREATEST(attempts - 1, 0)) STORED,
  started_at    timestamptz,                         -- ROS Time 0 이면 NULL (추정하지 않음)
  finished_at   timestamptz  NOT NULL,               -- ← SortResult.stamp
  inserted_at   timestamptz  NOT NULL DEFAULT now()  -- 트랜잭션 시작 시각. commit 시각이 아니다(#54)
);
CREATE INDEX sort_log_session_result_idx ON sort_log (session_id, result);
CREATE INDEX sort_log_finished_at_idx ON sort_log (finished_at);

-- 투입 예정 수량 (web_api.md PUT /api/sessions/current/plan). Spring Boot 자체 테이블.
-- 세션이 아직 없으면 session_id = 'next' 로 두었다가 start 때 새 session_id 에 붙인다.
CREATE TABLE session_plan (
  session_id varchar(24) PRIMARY KEY,
  planned    integer     NOT NULL CHECK (planned BETWEEN 1 AND 100),
  updated_at timestamptz NOT NULL DEFAULT now()
);
