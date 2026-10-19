BEGIN;
ALTER TABLE claim ADD COLUMN parent_claim_id TEXT;
ALTER TABLE claim ADD COLUMN cashless_root_id TEXT;
ALTER TABLE claim ADD CONSTRAINT claim_parent_tenant_fk FOREIGN KEY (tenant_id,parent_claim_id) REFERENCES claim(tenant_id,claim_id);
ALTER TABLE claim ADD CONSTRAINT claim_cashless_root_fk FOREIGN KEY (tenant_id,cashless_root_id) REFERENCES claim(tenant_id,claim_id);
ALTER TABLE claim ADD CONSTRAINT claim_not_own_parent CHECK (parent_claim_id IS NULL OR parent_claim_id<>claim_id);
CREATE UNIQUE INDEX claim_parent_one_child ON claim(tenant_id,parent_claim_id) WHERE parent_claim_id IS NOT NULL AND status<>'WITHDRAWN';
CREATE UNIQUE INDEX cashless_one_discharge ON claim(tenant_id,cashless_root_id) WHERE workflow='CASHLESS_DISCHARGE' AND cashless_root_id IS NOT NULL AND status<>'WITHDRAWN';
COMMIT;
