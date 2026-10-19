BEGIN;
CREATE FUNCTION guard_policy_candidate_entry() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state <> 'DRAFT' OR NEW.reviewed_by IS NOT NULL OR NEW.approved_by IS NOT NULL THEN RAISE EXCEPTION 'new candidate must enter as unapproved draft'; END IF;
 IF NOT EXISTS (SELECT 1 FROM policy_knowledge_record WHERE tenant_id=NEW.tenant_id AND record_id=NEW.source_id AND kind='DocumentVersion') THEN RAISE EXCEPTION 'candidate must link original document version'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER policy_candidate_entry BEFORE INSERT ON policy_rule_candidate FOR EACH ROW EXECUTE FUNCTION guard_policy_candidate_entry();
COMMIT;
