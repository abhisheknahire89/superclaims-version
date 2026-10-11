"""Seed the synthetic demo tenant: users and limits, hospitals, configuration (published four-eyes), members, policies,
opening sum-insured utilisation, and one prior claim whose bill number recurs on demo claim 3 (for the anomaly rule).

All data is SYNTHETIC and mirrors the research pack's fixtures. Usage:
  python -m aw.seed            (uses AW_OWNER_DSN for the tenant row and AW_DATABASE_URL for everything else)
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from . import configs
from .db import Database, Json
from .matching import normalise_name
from .money import to_paise

PACK = Path(__file__).resolve().parents[3]
TENANT = "TENANT-DEMO"

USERS = [  # user_id, display name, roles, approval limit (₹) — limits mirror config/workflow-TENANT-DEMO (illustrative)
    ("PROC-07", "Processor 07 (synthetic)", ["PROCESSOR"], "150000.00"),
    ("PROC-11", "Processor 11 (synthetic)", ["PROCESSOR"], "100000.00"),
    ("PROC-04", "Processor 04 (synthetic)", ["PROCESSOR"], "100000.00"),
    ("SUP-02", "Supervisor 02 (synthetic)", ["SUPERVISOR"], "500000.00"),
    ("MO-01", "Medical officer 01 (synthetic)", ["MEDICAL_OFFICER"], "100000.00"),
    ("FWA-01", "FWA analyst 01 (synthetic)", ["FWA_ANALYST"], None),
    ("AUD-01", "Auditor 01 (synthetic)", ["AUDITOR"], None),
    ("CFG-01", "Config admin 01 (synthetic)", ["CONFIG_ADMIN"], None),
    ("ADM-01", "Tenant admin 01 (synthetic)", ["TENANT_ADMIN"], None),
    ("RO-01", "Insurer liaison (read-only, synthetic)", ["READ_ONLY"], None),
]
HOSPITALS = [("HOSP-ILL-NN-07", "Illustrative Hospital NN-07 (synthetic)", False),
             ("HOSP-ILL-NW-01", "Illustrative Network Hospital 01 (synthetic)", True),
             ("HOSP-ILL-NN-12", "Illustrative Hospital NN-12 (synthetic)", False)]
DEMO = [("CLM-DEMO-0001", "trace-1-straightforward", "TMS-2026-0001"),
        ("CLM-DEMO-0002", "trace-2-interacting-adjustments", "TMS-2026-0002"),
        ("CLM-DEMO-0003", "trace-3a-insufficient-conflicting", "TMS-2026-0003")]


def _fixture(name: str) -> dict:
    return json.loads((PACK / "fixtures" / "claims" / f"{name}.input.json").read_text(encoding="utf-8"))


def seed(owner: Database, app: Database, tenant: str = TENANT) -> dict:
    with owner.connection() as c:
        c.execute("INSERT INTO tenant (tenant_id, legal_name, tenant_kind) VALUES ($1, 'Demo TPA (synthetic)', 'TPA') ON CONFLICT DO NOTHING", tenant)
    with app.tenant_tx(tenant) as c:
        for uid, name, roles, limit in USERS:
            c.execute("INSERT INTO app_user (user_id, tenant_id, idp_subject, display_name) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                      uid, tenant, f"dev|{uid}", name)
            for r in roles:
                if not c.fetch_one("SELECT 1 FROM role_assignment WHERE tenant_id=$1 AND user_id=$2 AND role=$3", tenant, uid, r):
                    c.execute("INSERT INTO role_assignment (tenant_id, user_id, role, approval_limit_paise, valid_from) VALUES ($1,$2,$3,$4,'2026-01-01')",
                              tenant, uid, r, to_paise(limit) if limit else None)
        for hid, name, net in HOSPITALS:
            c.execute("INSERT INTO hospital (tenant_id, hospital_id, name, is_network) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING", tenant, hid, name, net)
        loaded = configs.load_directory(c, PACK / "schemas", tenant, PACK / "config", author="CFG-01", approver="ADM-01")
        for _claim, fx_name, _ext in DEMO:
            fx = _fixture(fx_name)
            m, p = fx["member"], fx["policy"]
            c.execute("INSERT INTO member (tenant_id, member_id, full_name, name_normalised, gender, dob) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING",
                      tenant, m["member_id"], m["name_normalised"].title(), normalise_name(m["name_normalised"]), m["gender"], date.fromisoformat(m["dob"]))
            cfg_id, cfg_ver = p["config_ref"].split("@")
            c.execute("INSERT INTO policy (tenant_id, policy_no, product_name, period_start, period_end, config_artifact_id, config_version)"
                      " VALUES ($1,$2,'Illustrative Indemnity Plan A',$3,$4,$5,$6) ON CONFLICT DO NOTHING",
                      tenant, p["policy_no"], date.fromisoformat(p["period_start"]), date.fromisoformat(p["period_end"]), cfg_id, cfg_ver)
            c.execute("INSERT INTO policy_member (tenant_id, policy_no, member_id, continuous_cover_since, base_sum_insured_paise, cumulative_bonus_paise)"
                      " VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING", tenant, p["policy_no"], m["member_id"],
                      date.fromisoformat(p["continuous_cover_since"]), to_paise(p["base_sum_insured"]), to_paise(p["cumulative_bonus"]))
            if to_paise(p["paid_in_current_year"]) and not c.fetch_one(
                    "SELECT 1 FROM si_ledger_entry WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3 AND entry_kind='OPENING_PAID_EXTERNAL'",
                    tenant, p["policy_no"], m["member_id"]):
                c.execute("INSERT INTO si_ledger_entry (tenant_id, policy_no, member_id, policy_year_start, entry_kind, amount_paise)"
                          " VALUES ($1,$2,$3,$4,'OPENING_PAID_EXTERNAL',$5)", tenant, p["policy_no"], m["member_id"],
                          date.fromisoformat(p["period_start"]), to_paise(p["paid_in_current_year"]))
        # prior claim at hospital NN-12 for another member with the same bill number as demo claim 3 (pattern for review)
        c.execute("INSERT INTO member (tenant_id, member_id, full_name, name_normalised, gender, dob) VALUES ($1,'MEM-DEMO-8808','Ravi Kumar','RAVI KUMAR','M','1980-05-05') ON CONFLICT DO NOTHING", tenant)
        c.execute("INSERT INTO policy (tenant_id, policy_no, product_name, period_start, period_end, config_artifact_id, config_version)"
                  " VALUES ($1,'ILL-POL-000888','Illustrative Indemnity Plan A','2026-01-01','2026-12-31','POLCFG-ILL-INDEMNITY-A','2026.1.0') ON CONFLICT DO NOTHING", tenant)
        c.execute("INSERT INTO policy_member (tenant_id, policy_no, member_id, continuous_cover_since, base_sum_insured_paise) VALUES ($1,'ILL-POL-000888','MEM-DEMO-8808','2024-01-01',30000000) ON CONFLICT DO NOTHING", tenant)
        if not c.fetch_one("SELECT 1 FROM claim WHERE tenant_id=$1 AND claim_id='CLM-DEMO-0088'", tenant):
            c.execute("INSERT INTO claim (tenant_id, claim_id, external_ref, workflow, status, policy_no, member_id, hospital_id, submitted_at)"
                      " VALUES ($1,'CLM-DEMO-0088','TMS-2026-0088','IPD_REIMBURSEMENT','FINALISED','ILL-POL-000888','MEM-DEMO-8808','HOSP-ILL-NN-12','2026-09-20')", tenant)
            c.execute("INSERT INTO resolved_fact (tenant_id, resolved_fact_id, claim_id, field_path, value, basis) VALUES ($1,'RSF-DEMO-0088-BILLNO','CLM-DEMO-0088','bill.number',$2::jsonb,'REVIEWER_ENTERED')",
                      tenant, Json("SH/26/0915"))
    return {"tenant": tenant, "configs": loaded}


if __name__ == "__main__":
    o, a = Database(os.environ["AW_OWNER_DSN"]), Database(os.environ["AW_DATABASE_URL"])
    print(json.dumps(seed(o, a), indent=1, default=str))
