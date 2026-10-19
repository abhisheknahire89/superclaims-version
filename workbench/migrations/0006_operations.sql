BEGIN;
-- Tenant administration history is separate from PHI-bearing claim audits.
CREATE TABLE admin_event (
 tenant_id TEXT NOT NULL REFERENCES tenant, event_id TEXT NOT NULL,
 actor_user_id TEXT NOT NULL, subject_user_id TEXT NOT NULL,
 action TEXT NOT NULL, details JSONB NOT NULL, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,event_id)
);
ALTER TABLE admin_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_event FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON admin_event USING (tenant_id=current_setting('app.tenant_id',true)) WITH CHECK (tenant_id=current_setting('app.tenant_id',true));
CREATE TRIGGER immutable_admin_event BEFORE UPDATE OR DELETE ON admin_event FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
GRANT SELECT,INSERT ON admin_event TO aw_app;
COMMIT;
