#!/bin/bash
# 계정 2개를 만든다. 비밀번호는 .env(gitignore) 에서만 온다 — 이 파일에 적지 않는다.
#   voss_logger : sort_logger(ROS) 전용. sort_log 에 INSERT·SELECT 만 (UPDATE·DELETE 없음)
#   voss_web    : Spring Boot 전용. sort_log 는 SELECT 만, session_plan 은 읽기·쓰기
set -euo pipefail
: "${VOSS_DB_LOGGER_PASSWORD:?.env 에 VOSS_DB_LOGGER_PASSWORD 를 넣어야 한다}"
: "${VOSS_DB_WEB_PASSWORD:?.env 에 VOSS_DB_WEB_PASSWORD 를 넣어야 한다}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v logger_pw="$VOSS_DB_LOGGER_PASSWORD" -v web_pw="$VOSS_DB_WEB_PASSWORD" <<'SQL'
CREATE ROLE voss_logger LOGIN PASSWORD :'logger_pw';
CREATE ROLE voss_web    LOGIN PASSWORD :'web_pw';

GRANT CONNECT ON DATABASE voss TO voss_logger, voss_web;
GRANT USAGE ON SCHEMA public TO voss_logger, voss_web;

GRANT SELECT, INSERT ON sort_log TO voss_logger;
GRANT SELECT ON sort_log TO voss_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON session_plan TO voss_web;
SQL
