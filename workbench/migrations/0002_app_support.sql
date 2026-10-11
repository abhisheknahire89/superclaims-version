-- 0002: additions the Phase 1 application needs on top of the pack schema (0001).
-- Kept separate so 0001 stays byte-identical to the research pack's db/schema.sql (checked in tests).
BEGIN;

-- Job payload (e.g. the trigger for an EVALUATE job) and failure detail without document content.
ALTER TABLE processing_job ADD COLUMN payload JSONB NOT NULL DEFAULT '{}';
ALTER TABLE processing_job ADD COLUMN finished_at TIMESTAMPTZ;

-- Finding continuity across evaluations: same subject => same finding row (03 §2.5 step 4).
ALTER TABLE finding ADD COLUMN subject_key TEXT;
CREATE UNIQUE INDEX finding_subject_uq ON finding (tenant_id, claim_id, subject_key) WHERE subject_key IS NOT NULL;

-- Why an evaluation FAILED (engine or configuration error code), never document text.
ALTER TABLE evaluation ADD COLUMN error_code TEXT;
ALTER TABLE evaluation ADD COLUMN error_detail TEXT;
ALTER TABLE evaluation ADD COLUMN result JSONB;          -- full engine output (recommendation, lines, query items) for display and replay

-- Query items keep their own addressee until grouped into a letter.
ALTER TABLE query_item ADD COLUMN addressed_to TEXT;

-- Worksheet artefacts produced at decision time.
ALTER TABLE decision ADD COLUMN worksheet JSONB;

-- Page geometry for the evidence viewer.
ALTER TABLE document_page ADD COLUMN width_pt NUMERIC(8,2);
ALTER TABLE document_page ADD COLUMN height_pt NUMERIC(8,2);

-- Worker role sees all queued jobs (it then does the work in a tenant-scoped transaction as the app role).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aw_worker') THEN
    EXECUTE 'CREATE POLICY worker_poll ON processing_job TO aw_worker USING (true) WITH CHECK (true)';
  END IF;
END $$;

-- Grants for the RLS-restricted application role (created outside migrations by IaC or scripts/dev_db.sh).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aw_app') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO aw_app';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO aw_app';
    EXECUTE 'GRANT DELETE ON idempotency_key TO aw_app';
    EXECUTE 'REVOKE ALL ON schema_migration FROM aw_app';
    EXECUTE 'REVOKE INSERT, UPDATE ON tenant FROM aw_app';             -- tenants are provisioned by operators, not the app
    EXECUTE 'REVOKE UPDATE ON config_artifact FROM aw_app';
    EXECUTE 'GRANT UPDATE (status, approved_by, published_at, effective_to) ON config_artifact TO aw_app';  -- body is immutable
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aw_worker') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO aw_worker';
    EXECUTE 'GRANT SELECT, UPDATE ON processing_job TO aw_worker';
  END IF;
END $$;

COMMIT;
