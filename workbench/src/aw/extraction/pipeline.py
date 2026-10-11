"""EXTRACT job: classify a document, run the extraction provider, validate the output against the schema,
run the grounding check on every value and line, persist append-only extracted facts, and queue RECONCILE."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .. import audit, configs, jobs
from ..db import Conn, Json
from ..ids import new_id
from . import grounding
from .pages import PageText
from .providers import PIPELINE_VERSION, FixtureProvider, classify

REQUIRED_BY_TYPE = {
    "FINAL_BILL_ITEMISED": {"patient.name", "bill.total"},
    "FINAL_BILL_SUMMARY": {"patient.name", "bill.total"},
    "DISCHARGE_SUMMARY": {"patient.name", "admission.date", "diagnosis.primary_text"},
    "CLAIM_FORM": {"patient.name"},
}
LOW_CONFIDENCE = 0.85


@lru_cache(maxsize=4)
def _schema_validator(schema_dir: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((Path(schema_dir) / "extraction-output.schema.json").read_text(encoding="utf-8")))


def load_pages(conn: Conn, store, tenant_id: str, document_id: str) -> list[PageText]:
    rows = conn.fetch_all("SELECT page_no, text_layer, text_key FROM document_page WHERE tenant_id=$1 AND document_id=$2 ORDER BY page_no",
                          tenant_id, document_id)
    pages = []
    for r in rows:
        if r["text_key"]:
            pages.append(PageText.from_json(json.loads(store.get(r["text_key"]))))
        else:
            pages.append(PageText(r["page_no"], 0, 0, "", [], [], "NONE"))
    return pages


def run_extraction(conn: Conn, ctx, tenant_id: str, document_id: str) -> dict:
    doc = conn.fetch_one("SELECT * FROM document WHERE tenant_id=$1 AND document_id=$2", tenant_id, document_id)
    if doc is None or doc["status"] in ("QUARANTINED",):
        return {"skipped": True}
    claim_id = doc["claim_id"]
    pages = load_pages(conn, ctx.store, tenant_id, document_id)
    cmap = configs.effective(conn, tenant_id, "CLASSIFIER_MAP", date.today())
    if cmap is None:
        raise RuntimeError("CLASSIFIER_MAP_NOT_CONFIGURED")
    # A reviewer's reclassification wins over the classifier.
    reclass = conn.fetch_one("SELECT after_value FROM reviewer_action WHERE tenant_id=$1 AND action='RECLASSIFY_DOCUMENT'"
                             " AND target_ref->>'id' = $2 ORDER BY created_at DESC LIMIT 1", tenant_id, document_id)
    if reclass:
        dtype, conf, kw = reclass["after_value"]["document_type"], 1.0, "reviewer"
    else:
        dtype, conf, kw = classify(pages, cmap)
    conn.execute("UPDATE document SET classified_type=$3, status='EXTRACTING' WHERE tenant_id=$1 AND document_id=$2",
                 tenant_id, document_id, dtype)
    audit.append(conn, tenant_id, claim_id, "SYSTEM", "DOCUMENT_CLASSIFIED",
                 {"document_id": document_id, "type": dtype, "confidence": conf, "basis": kw})
    run_id = new_id("XRN")
    if all(p.text_layer == "NONE" for p in pages):
        conn.execute("INSERT INTO extraction_run (tenant_id, extraction_run_id, document_id, pipeline_version, model_ref, outcome, finished_at)"
                     " VALUES ($1,$2,$3,$4,$5,'FAILED',now())", tenant_id, run_id, document_id, PIPELINE_VERSION, "none")
        conn.execute("UPDATE document SET status='FAILED_TECHNICAL' WHERE tenant_id=$1 AND document_id=$2", tenant_id, document_id)
        audit.append(conn, tenant_id, claim_id, "SYSTEM", "EXTRACTION_FAILED", {"document_id": document_id, "code": "NO_TEXT_LAYER_OCR_NOT_CONFIGURED"})
        jobs.enqueue(conn, tenant_id, "RECONCILE", claim_id, f"reconcile:{claim_id}:{run_id}", {})
        return {"run_id": run_id, "outcome": "FAILED"}

    provider = ctx.provider
    if isinstance(provider, FixtureProvider):
        provider.current_sha = doc["sha256"]
    raw = provider.extract(dtype, pages)
    raw["document_id"] = document_id
    errors = [f"{list(e.path)}: {e.message}" for e in _schema_validator(str(ctx.schema_dir)).iter_errors(raw)]
    if errors:
        conn.execute("INSERT INTO extraction_run (tenant_id, extraction_run_id, document_id, pipeline_version, model_ref, outcome, finished_at)"
                     " VALUES ($1,$2,$3,$4,$5,'FAILED',now())", tenant_id, run_id, document_id, PIPELINE_VERSION, provider.name)
        conn.execute("UPDATE document SET status='FAILED_TECHNICAL' WHERE tenant_id=$1 AND document_id=$2", tenant_id, document_id)
        audit.append(conn, tenant_id, claim_id, "SYSTEM", "EXTRACTION_FAILED",
                     {"document_id": document_id, "code": "SCHEMA_VALIDATION_FAILED", "errors": len(errors)})
        return {"run_id": run_id, "outcome": "FAILED", "errors": errors[:5]}

    page_text = {p.page_no: p.text for p in pages}
    conn.execute("INSERT INTO extraction_run (tenant_id, extraction_run_id, document_id, pipeline_version, model_ref, prompt_version, outcome)"
                 " VALUES ($1,$2,$3,$4,$5,$6,'OK')", tenant_id, run_id, document_id, PIPELINE_VERSION, provider.name, None)
    verified_paths, not_found, low_conf = set(), 0, 0
    for f in raw["fields"]:
        span = f["evidence"][0]
        g = grounding.check(span["quote"], page_text.get(span["page"], ""))
        verified_paths.add(f["path"]) if g == "VERIFIED" else None
        not_found += g != "VERIFIED"
        low_conf += f["confidence"] < LOW_CONFIDENCE
        conn.execute(
            "INSERT INTO extracted_fact (tenant_id, fact_id, claim_id, extraction_run_id, field_path, raw_value, normalised_value, confidence, evidence, grounding_check)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::jsonb,$10)",
            tenant_id, new_id("FCT"), claim_id, run_id, f["path"], None if f["value"] is None else str(f["value"]),
            Json(f.get("normalised", f["value"])), round(float(f["confidence"]), 3),
            Json({"document_id": document_id, "page": span["page"], "bbox": span.get("bbox"), "quote": span["quote"]}), g)
    for item in raw.get("line_items", []):
        span = item["evidence"][0]
        g = grounding.check(span["quote"], page_text.get(span["page"], ""))
        not_found += g != "VERIFIED"
        conn.execute(
            "INSERT INTO extracted_fact (tenant_id, fact_id, claim_id, extraction_run_id, field_path, raw_value, normalised_value, confidence, evidence, grounding_check)"
            " VALUES ($1,$2,$3,$4,'bill.line_item',$5,$6::jsonb,$7,$8::jsonb,$9)",
            tenant_id, new_id("FCT"), claim_id, run_id, item["description"], Json({k: v for k, v in item.items() if k != "evidence"}),
            round(float(item["confidence"]), 3),
            Json({"document_id": document_id, "page": span["page"], "bbox": span.get("bbox"), "quote": span["quote"]}), g)
    required = REQUIRED_BY_TYPE.get(dtype, set())
    complete = required <= verified_paths and (dtype != "FINAL_BILL_ITEMISED" or raw.get("line_items"))
    status = "EXTRACTED" if complete and not low_conf else "NEEDS_REVIEW"
    if "EMBEDDED_INSTRUCTIONS_IGNORED" in raw.get("warnings", []):
        status = "NEEDS_REVIEW"
    conn.execute("UPDATE document SET status=$3::doc_status WHERE tenant_id=$1 AND document_id=$2", tenant_id, document_id, status)
    conn.execute("UPDATE extraction_run SET finished_at=now(), outcome=$3 WHERE tenant_id=$1 AND extraction_run_id=$2",
                 tenant_id, run_id, "OK" if not not_found else "PARTIAL")
    audit.append(conn, tenant_id, claim_id, "SYSTEM", "EXTRACTION_COMPLETED",
                 {"document_id": document_id, "extraction_run_id": run_id, "provider": provider.name, "pipeline_version": PIPELINE_VERSION,
                  "fields": len(raw["fields"]), "line_items": len(raw.get("line_items", [])), "not_grounded": not_found,
                  "warnings": raw.get("warnings", []), "status": status})
    jobs.enqueue(conn, tenant_id, "RECONCILE", claim_id, f"reconcile:{claim_id}:{run_id}", {})
    return {"run_id": run_id, "outcome": "OK", "document_type": dtype, "status": status, "not_grounded": not_found}
