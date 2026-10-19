BEGIN;
ALTER TABLE policy_knowledge_record DROP CONSTRAINT policy_knowledge_record_kind_check;
ALTER TABLE policy_knowledge_record ADD CONSTRAINT policy_knowledge_record_kind_check CHECK(kind IN ('Insurer','InsuranceProduct','ProductRevision','PolicyDocument','DocumentVersion','SourceVerification','Clause','RuleApproval','PolicyRuleMapping','MemberDataRequirement','TariffDataRequirement','ProductHistory'));
COMMIT;
