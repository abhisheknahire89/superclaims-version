BEGIN;
CREATE TABLE policy_knowledge_record (
 tenant_id TEXT NOT NULL REFERENCES tenant, record_id TEXT NOT NULL, kind TEXT NOT NULL,
 body JSONB NOT NULL, created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,record_id),
 CHECK(kind IN ('Insurer','InsuranceProduct','ProductRevision','PolicyDocument','DocumentVersion','SourceVerification','Clause','RuleApproval','PolicyRuleMapping','MemberDataRequirement','TariffDataRequirement'))
);
CREATE TABLE policy_rule_candidate (
 tenant_id TEXT NOT NULL REFERENCES tenant, rule_id TEXT NOT NULL, source_id TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'DRAFT', body JSONB NOT NULL, authored_by TEXT NOT NULL,
 reviewed_by TEXT, approved_by TEXT, row_version BIGINT NOT NULL DEFAULT 1,
 PRIMARY KEY(tenant_id,rule_id), FOREIGN KEY(tenant_id,source_id) REFERENCES policy_knowledge_record(tenant_id,record_id),
 CHECK(state IN ('DRAFT','VALIDATED','HUMAN_REVIEWED','APPROVED','PUBLISHED')),
 CHECK(state NOT IN ('APPROVED','PUBLISHED') OR (approved_by IS NOT NULL AND approved_by<>authored_by AND reviewed_by IS NOT NULL))
);
CREATE TABLE policy_review_event (
 tenant_id TEXT NOT NULL REFERENCES tenant,event_id TEXT NOT NULL,subject_id TEXT NOT NULL,
 actor_user_id TEXT NOT NULL,action TEXT NOT NULL,details JSONB NOT NULL,occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,event_id)
);
CREATE FUNCTION protect_policy_rule() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.state IN ('APPROVED','PUBLISHED') AND (NEW.body<>OLD.body OR NEW.authored_by<>OLD.authored_by OR NEW.source_id<>OLD.source_id OR NEW.approved_by<>OLD.approved_by OR NEW.reviewed_by<>OLD.reviewed_by) THEN RAISE EXCEPTION 'approved policy rule is immutable'; END IF;
 IF NEW.state<>OLD.state AND NOT ((OLD.state='DRAFT' AND NEW.state='VALIDATED') OR (OLD.state='VALIDATED' AND NEW.state='HUMAN_REVIEWED') OR (OLD.state='HUMAN_REVIEWED' AND NEW.state='APPROVED') OR (OLD.state='APPROVED' AND NEW.state='PUBLISHED') OR (OLD.state IN ('VALIDATED','HUMAN_REVIEWED') AND NEW.state='DRAFT')) THEN RAISE EXCEPTION 'invalid policy rule lifecycle'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_policy_knowledge BEFORE UPDATE OR DELETE ON policy_knowledge_record FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER immutable_policy_review BEFORE UPDATE OR DELETE ON policy_review_event FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER policy_rule_lifecycle BEFORE UPDATE ON policy_rule_candidate FOR EACH ROW EXECUTE FUNCTION protect_policy_rule();
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['policy_knowledge_record','policy_rule_candidate','policy_review_event'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id=current_setting(''app.tenant_id'',true)) WITH CHECK (tenant_id=current_setting(''app.tenant_id'',true))',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT ON policy_knowledge_record,policy_review_event TO aw_app;
GRANT SELECT,INSERT,UPDATE ON policy_rule_candidate TO aw_app;
COMMIT;
