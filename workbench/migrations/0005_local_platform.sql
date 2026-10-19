BEGIN;
CREATE UNIQUE INDEX app_user_tenant_ref ON app_user(tenant_id,user_id);
CREATE TABLE local_credential (
 tenant_id TEXT NOT NULL,user_id TEXT NOT NULL,password_hash TEXT NOT NULL,
 failed_attempts INTEGER NOT NULL DEFAULT 0,locked_until TIMESTAMPTZ,
 PRIMARY KEY(tenant_id,user_id),FOREIGN KEY(tenant_id,user_id) REFERENCES app_user(tenant_id,user_id));
CREATE TABLE local_session (
 tenant_id TEXT NOT NULL,session_hash TEXT NOT NULL,user_id TEXT NOT NULL,
 csrf_hash TEXT NOT NULL,expires_at TIMESTAMPTZ NOT NULL,revoked BOOLEAN NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,session_hash),FOREIGN KEY(tenant_id,user_id) REFERENCES app_user(tenant_id,user_id));
CREATE TABLE audit_anchor (
 tenant_id TEXT NOT NULL,anchor_id TEXT NOT NULL,claim_id TEXT NOT NULL,seq INTEGER NOT NULL,
 head TEXT NOT NULL,object_key TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,anchor_id),FOREIGN KEY(tenant_id,claim_id) REFERENCES claim);
DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['local_credential','local_session','audit_anchor'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY tenant_scope ON %I USING (tenant_id=current_setting(''app.tenant_id'',true)) WITH CHECK (tenant_id=current_setting(''app.tenant_id'',true))',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON %I TO aw_app',t);
 END LOOP; END $$;
CREATE TRIGGER anchor_append_only BEFORE UPDATE OR DELETE ON audit_anchor FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
COMMIT;
BEGIN;
ALTER TABLE processing_job DROP CONSTRAINT processing_job_job_kind_check;
ALTER TABLE processing_job ADD CHECK(job_kind IN ('CLASSIFY','OCR','EXTRACT','RECONCILE','EVALUATE','EXPORT','WEBHOOK','AUDIT_ANCHOR','DEADLINE_SCAN'));
CREATE TABLE deadline_alert (
 tenant_id TEXT NOT NULL,claim_id TEXT NOT NULL,due_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,claim_id,due_at),
 FOREIGN KEY(tenant_id,claim_id) REFERENCES claim);
ALTER TABLE deadline_alert ENABLE ROW LEVEL SECURITY;
ALTER TABLE deadline_alert FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON deadline_alert USING(tenant_id=current_setting('app.tenant_id',true)) WITH CHECK(tenant_id=current_setting('app.tenant_id',true));
GRANT SELECT,INSERT ON deadline_alert TO aw_app;
CREATE TRIGGER deadline_alert_append_only BEFORE UPDATE OR DELETE ON deadline_alert FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
COMMIT;
