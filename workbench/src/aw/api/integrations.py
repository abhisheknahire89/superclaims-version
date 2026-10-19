"""Imports and the TMS event receiver. Third-party integration is out of scope for this build: these endpoints are kept
exactly as the Phase 1 build left them (status "not built" for TMS adapters, bulk import UI, webhooks and API keys)."""
from __future__ import annotations

from .. import audit
from ..matching import normalise_name
from ..money import to_paise
from .core import Api, Problem


def register(api: Api):
    @api.op("importPolicies", "/v1/imports/policies", "POST")
    def h_import_policies(conn, p, req, body):
        p.require("admin.users")
        n = 0
        for r in body["records"]:
            conn.execute("INSERT INTO member (tenant_id, member_id, full_name, name_normalised, gender, dob) VALUES ($1,$2,$3,$4,$5,$6::date)"
                         " ON CONFLICT (tenant_id, member_id) DO UPDATE SET full_name=EXCLUDED.full_name, name_normalised=EXCLUDED.name_normalised",
                         p.tenant_id, r["member_id"], r["full_name"], normalise_name(r["full_name"]), r.get("gender"), r.get("dob"))
            conn.execute("INSERT INTO policy (tenant_id, policy_no, product_name, period_start, period_end, config_artifact_id, config_version)"
                         " VALUES ($1,$2,$3,$4::date,$5::date,$6,$7) ON CONFLICT DO NOTHING", p.tenant_id, r["policy_no"], r.get("product_name", ""),
                         r["period_start"], r["period_end"], r["config_artifact_id"], r["config_version"])
            conn.execute("INSERT INTO policy_member (tenant_id, policy_no, member_id, continuous_cover_since, base_sum_insured_paise, cumulative_bonus_paise)"
                         " VALUES ($1,$2,$3,$4::date,$5,$6) ON CONFLICT DO NOTHING", p.tenant_id, r["policy_no"], r["member_id"], r["continuous_cover_since"],
                         to_paise(r["base_sum_insured"]), to_paise(r.get("cumulative_bonus", "0.00")))
            n += 1
        return 202, {"accepted": n}, None

    @api.op("importSiLedger", "/v1/imports/si-ledger", "POST")
    def h_import_si(conn, p, req, body):
        p.require("admin.users")
        for e in body["entries"]:
            conn.execute("INSERT INTO si_ledger_entry (tenant_id, policy_no, member_id, policy_year_start, entry_kind, amount_paise) VALUES ($1,$2,$3,$4::date,'OPENING_PAID_EXTERNAL',$5)",
                         p.tenant_id, e["policy_no"], e["member_id"], e["policy_year_start"], to_paise(e["amount"]))
        return 202, {"accepted": len(body["entries"])}, None

    @api.op("receiveTmsEvent", "/v1/integrations/tms/events", "POST")
    def h_tms_event(conn, p, req, body):
        claim = conn.fetch_one("SELECT claim_id FROM claim WHERE tenant_id=$1 AND external_ref=$2", p.tenant_id, body["external_ref"])
        if not claim:
            raise Problem(404, "claim-not-found", "no claim with that external_ref")
        if body["event_type"] == "CLAIM_WITHDRAWN":
            conn.execute("UPDATE claim SET status='WITHDRAWN', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2 AND status NOT IN ('FINALISED','EXPORTED')",
                         p.tenant_id, claim["claim_id"])
            audit.append(conn, p.tenant_id, claim["claim_id"], "INTEGRATION:TMS", "CLAIM_WITHDRAWN", {"event_id": body["event_id"]})
        return 202, {"accepted": True, "claim_id": claim["claim_id"]}, None
