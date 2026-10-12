-- Sprint 2 (S2-T01, BRD v1.5 pallet_log): 이미 만들어진 DB(데이터 폴더가 있는 공용 PC)에 init/ 과 같은 결과를 적용한다. 데이터를 지우지 않고,
-- 여러 번 실행해도 된다. init/ 은 데이터 폴더가 비어 있을 때만 돌기 때문에 따로 둔다(README).
-- 실행(공용 PC, 사람이, sort_logger 를 끈 뒤): docker/db 에서
--   docker compose exec -T db psql -U voss_admin -d voss -v ON_ERROR_STOP=1 < migrations/20261012_sprint2_pallet.sql
BEGIN;

ALTER TABLE sort_log ADD COLUMN IF NOT EXISTS slot smallint CHECK (slot >= 0);   -- ← SortResult.slot, -1 → NULL

CREATE TABLE IF NOT EXISTS pallet_log (
  run_id        varchar(24)  NOT NULL,               -- palletize 실행 ID (session_id 와 같은 형식)
  box_id        varchar(32)  NOT NULL,               -- sort_log.box_id
  session_id    varchar(24)  NOT NULL,
  dong          varchar(16)  NOT NULL DEFAULT '',
  route_index   smallint     NOT NULL CHECK (route_index BETWEEN -1 AND 2),  -- 0 = 첫 배송지, -1 = 경로 밖(EXCLUDED)
  zone          varchar(8)   NOT NULL CHECK (zone IN ('A', 'B', 'C')),       -- 집은 곳
  slot          smallint     NOT NULL CHECK (slot >= 0),
  pallet_slot   smallint     CHECK (pallet_slot BETWEEN 0 AND 15),           -- (열−1)×4+(층−1)×2+(줄−1), NULL = 싣지 않음(-1)
  pallet_col    smallint     CHECK (pallet_col BETWEEN 1 AND 4),             -- 1 = 트럭 머리(−X), NULL = 싣지 않음(0)
  pallet_lane   smallint     CHECK (pallet_lane BETWEEN 1 AND 2),
  pallet_layer  smallint     CHECK (pallet_layer BETWEEN 1 AND 2),           -- 2 = +27 mm
  result        varchar(8)   NOT NULL CHECK (result IN ('DONE', 'FAILED', 'OVERFLOW', 'EXCLUDED')),  -- ← outcome
  reason        varchar(24)  NOT NULL DEFAULT '',
  attempts      smallint     NOT NULL DEFAULT 0,
  finished_at   timestamptz  NOT NULL,               -- ← PalletResult.stamp
  inserted_at   timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, box_id)
);
CREATE INDEX IF NOT EXISTS pallet_log_session_idx ON pallet_log (session_id, box_id);

GRANT SELECT, INSERT ON pallet_log TO voss_logger;
GRANT SELECT ON pallet_log TO voss_web;

COMMIT;
