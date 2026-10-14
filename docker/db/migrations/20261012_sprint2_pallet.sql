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
-- 검증(정의석 #47 리뷰): CREATE TABLE IF NOT EXISTS 는 구버전 pallet_log(예: BRD v1.4 의 pallet_row)가 이미 있으면
-- 구조가 달라도 건너뛴다. 아래가 기대 구조와 다르면 RAISE 로 이 트랜잭션 전체를 되돌린다 — 데이터는 지우지 않는다.
-- 이때는 README "마이그레이션 검증 실패" 절대로 사람이 판단한다(기존 행을 보관한 뒤 이름 바꾸기 등).
DO $$
DECLARE
  expected text[][] := ARRAY[
    ['run_id','character varying','NO'], ['box_id','character varying','NO'], ['session_id','character varying','NO'],
    ['dong','character varying','NO'], ['route_index','smallint','NO'], ['zone','character varying','NO'],
    ['slot','smallint','NO'], ['pallet_slot','smallint','YES'], ['pallet_col','smallint','YES'],
    ['pallet_lane','smallint','YES'], ['pallet_layer','smallint','YES'], ['result','character varying','NO'],
    ['reason','character varying','NO'], ['attempts','smallint','NO'], ['finished_at','timestamp with time zone','NO'],
    ['inserted_at','timestamp with time zone','NO']];
  problems text[] := '{}';
  col record;
  i int;
  pk text;
  result_check text;
BEGIN
  FOR i IN 1 .. array_length(expected, 1) LOOP
    SELECT data_type, is_nullable INTO col FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'pallet_log' AND column_name = expected[i][1];
    IF NOT FOUND THEN
      problems := problems || format('컬럼 없음 %s', expected[i][1]);
    ELSIF col.data_type <> expected[i][2] OR col.is_nullable <> expected[i][3] THEN
      problems := problems || format('%s = %s null=%s (기대 %s null=%s)', expected[i][1], col.data_type,
                                     col.is_nullable, expected[i][2], expected[i][3]);
    END IF;
  END LOOP;
  SELECT string_agg(a.attname, ',' ORDER BY array_position(c.conkey, a.attnum)) INTO pk
    FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
    WHERE c.conrelid = 'public.pallet_log'::regclass AND c.contype = 'p';
  IF pk IS DISTINCT FROM 'run_id,box_id' THEN
    problems := problems || format('PK = %s (기대 run_id,box_id)', coalesce(pk, '없음'));
  END IF;
  SELECT string_agg(pg_get_constraintdef(c.oid), ' ') INTO result_check
    FROM pg_constraint c WHERE c.conrelid = 'public.pallet_log'::regclass AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%result%';
  IF result_check IS NULL OR result_check NOT LIKE '%OVERFLOW%' OR result_check NOT LIKE '%EXCLUDED%' THEN
    problems := problems || format('result CHECK 에 OVERFLOW·EXCLUDED 없음: %s', coalesce(result_check, '없음'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                 AND table_name = 'sort_log' AND column_name = 'slot' AND data_type = 'smallint') THEN
    problems := problems || 'sort_log.slot(smallint) 없음'::text;
  END IF;
  IF array_length(problems, 1) > 0 THEN
    RAISE EXCEPTION 'pallet_log 구조가 Sprint 2(BRD v1.5) 와 다름 — 변경 없이 롤백: %', array_to_string(problems, '; ')
      USING HINT = 'docker/db/README.md "마이그레이션 검증 실패" 절. 기존 행을 보관한 뒤 사람이 판단한다(DROP 금지).';
  END IF;
  RAISE NOTICE 'pallet_log 구조 확인: 컬럼 16개·PK(run_id, box_id)·result CHECK·sort_log.slot OK';
END $$;

CREATE INDEX IF NOT EXISTS pallet_log_session_idx ON pallet_log (session_id, box_id);

GRANT SELECT, INSERT ON pallet_log TO voss_logger;
GRANT SELECT ON pallet_log TO voss_web;

COMMIT;
