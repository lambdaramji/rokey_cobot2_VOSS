# VOSS 작업 로그 DB (PostgreSQL 16)

ADR-0006 · 계약: `docs/interfaces/voss_msgs.md` "DB sort_log 대응", `web_api.md`.
쓰기는 **sort_logger(ROS) 하나**(`voss_logger`), Spring Boot 는 `voss_web` 으로 `sort_log` 를 읽기만 한다.

| 항목 | 값 |
|---|---|
| 포트 | `127.0.0.1:5432` 만 (Wi-Fi 쪽으로 열지 않음, web_api.md 포트 표) |
| 데이터 | 호스트 `/var/lib/voss/pgdata` — 10/16 발표까지 지우지 않는다(SRD) |
| 스키마 | `init/01_schema.sql` — `sort_log`(PK box_id, Sprint 2 `slot`), `pallet_log`(PK run_id + box_id, Sprint 2), `session_plan`(Spring Boot) |
| 계정 | `init/02_roles.sh` — `voss_logger`(sort_log·pallet_log INSERT·SELECT), `voss_web`(sort_log·pallet_log SELECT, session_plan 읽기·쓰기). 비밀번호는 `.env` |
| 마이그레이션 | `migrations/` — 이미 있는 DB 에 스키마 변경을 적용(아래). `20261012_sprint2_pallet.sql` = Sprint 2 `sort_log.slot`·`pallet_log` |

`init/` 은 **데이터 폴더가 비어 있을 때 처음 한 번만** 실행된다. 스키마를 바꾸면 마이그레이션 SQL 을 따로 만든다(데이터를 지우지 않는다).

## 실행 (공용 PC, 사람이 실행)
```bash
sudo mkdir -p /var/lib/voss/pgdata /var/lib/voss/spool && sudo chown $USER /var/lib/voss/spool
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/db
cp .env.example .env              # 비밀번호 3개 채우기 (.env 는 커밋 금지)
docker compose up -d
docker compose ps                 # STATUS 가 healthy 인지
```

`docker/db/.env`는 PostgreSQL 초기화 전용이다. 관리자 비밀번호와
`voss_logger`, `voss_web` 역할 생성용 비밀번호를 둔다. Spring Boot 접속 변수는
`docker/web/.env`에 별도로 두며, 거기의 `VOSS_DB_READ_PASSWORD`·`VOSS_DB_PLAN_PASSWORD`(둘 다
`voss_web` 계정)는 여기의 `VOSS_DB_WEB_PASSWORD`와 같은 값이어야 한다.

## 마이그레이션 (공용 PC, 사람이 실행)
데이터 폴더가 이미 있으면 `init/` 이 다시 돌지 않는다. sort_logger 를 끈 뒤 한 번 실행한다(여러 번 실행해도 결과가 같다).
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/docker/db
docker compose exec -T db psql -U voss_admin -d voss -v ON_ERROR_STOP=1 < migrations/20261012_sprint2_pallet.sql
docker compose exec db psql -U voss_admin -d voss -c '\d pallet_log'   # 표가 보이면 끝
```

## sort_logger 연결 (호스트)
```bash
sudo apt install python3-psycopg2
export VOSS_DB_LOGGER_PASSWORD=<.env 와 같은 값>
ros2 run voss_hmi sort_logger
ros2 topic echo /voss/log/status   # STARTING → OK
```

## G0 증거: 같은 box_id 조회
sort_logger 로그에서 `db_committed box_id=<ID>` 를 확인한 뒤:
```bash
docker compose exec db psql -U voss_admin -d voss -c \
  "SELECT box_id, session_id, result, zone, finished_at, inserted_at FROM sort_log WHERE box_id = '<ID>';"
```

## 시험 (실제 DB)
```bash
cd ~/voss_ws/src/rokey_cobot2_VOSS/src/voss_hmi
set -a; . ../../docker/db/.env; set +a
VOSS_TEST_DB_PORT=5432 PYTHONPATH=. pytest -q test/test_db_writer_postgres.py
# 시험 행은 box_id 가 'TEST-' 로 시작한다. 시연 전 지우려면 (관리자 계정):
docker compose exec db psql -U voss_admin -d voss -c "DELETE FROM sort_log WHERE box_id LIKE 'TEST-%';"
```
