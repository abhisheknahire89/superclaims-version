BEGIN;
-- Immutable human evidence explicitly distinguishes visual transcription from OCR.
CREATE UNIQUE INDEX document_claim_ref ON document (tenant_id, document_id, claim_id);
CREATE TABLE human_page_transcription (
 tenant_id TEXT NOT NULL,
 transcription_id TEXT NOT NULL,
 claim_id TEXT NOT NULL,
 document_id TEXT NOT NULL,
 page_no INTEGER NOT NULL,
 image_sha256 TEXT NOT NULL CHECK (length(image_sha256)=64),
 quote TEXT NOT NULL CHECK (length(quote) BETWEEN 1 AND 400),
 bbox JSONB NOT NULL CHECK (jsonb_typeof(bbox)='array' AND jsonb_array_length(bbox)=4),
 confirmed_by TEXT NOT NULL REFERENCES app_user(user_id),
 reviewed_complete BOOLEAN NOT NULL DEFAULT false,
 confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id, transcription_id),
 FOREIGN KEY (tenant_id, document_id, claim_id) REFERENCES document(tenant_id, document_id, claim_id),
 FOREIGN KEY (tenant_id, document_id, page_no) REFERENCES document_page
);
ALTER TABLE human_page_transcription ENABLE ROW LEVEL SECURITY;
ALTER TABLE human_page_transcription FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON human_page_transcription USING (tenant_id=current_setting('app.tenant_id',true)) WITH CHECK (tenant_id=current_setting('app.tenant_id',true));
CREATE TRIGGER human_transcription_append_only BEFORE UPDATE OR DELETE ON human_page_transcription FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
GRANT SELECT, INSERT ON human_page_transcription TO aw_app;
COMMIT;
