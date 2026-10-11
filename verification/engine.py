"""
Reference calculation harness for the Adjudication Workbench rule catalog.

STATUS: verification harness for the research pack, not production code.
It exists to (1) prove that the worked traces in 06-rule-catalog.md are
reproducible, (2) exercise the financial invariants in 10-validation-plan.md,
and (3) give engineers an executable reading of the rule semantics.

Design rules it demonstrates:
  * Money is Decimal, never float. Line-step results are quantised to paise
    (ROUND_HALF_UP); the final payable is rounded per configuration and the
    rounding difference is recorded as its own adjustment.
  * Every rule operates on a line's *remaining* amount, so a rupee can be
    deducted at most once (no double deduction).
  * Every adjustment carries its authority (config artifact@version + document + clause);
    a rule with no configured authority fails the evaluation instead of deducting.
  * Gates run first; a blocking gate stops every rule whose inputs it taints.
    Scope ALL_FINANCIAL stops all money computation; eligibility review rules still
    run, using only identity-matched documents.
  * Reviewer overrides are re-applied on re-evaluation only if the line is unchanged
    (fingerprint match); otherwise they become a reconfirmation finding.
  * The engine never emits a final "REJECT". Its strongest negative output is
    REFER_CRC (refer to the insurer's Claims Review Committee).
  * Output is deterministic and order-independent: same inputs + same config
    versions -> same hash; bill-line order does not change the payable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

PAISE = Decimal("0.01")
RUPEE = Decimal("1")
ENGINE_VERSION = "ref-harness-0.4.0"

RULE_VERSIONS = {
    "R-GATE-IDENTITY": "1.0.0",
    "R-GATE-DATES": "1.0.0",
    "R-GATE-ITEMISATION": "1.0.0",
    "R-DOC-COMPLETENESS": "1.0.0",
    "R-ELIG-POLICY-ACTIVE": "1.0.0",
    "R-ELIG-WAITING": "1.1.0",
    "R-LINE-DUPLICATE": "1.0.0",
    "R-LINE-NONPAYABLE": "1.0.0",
    "R-LINE-TARIFF": "1.0.0",
    "R-LINE-ROOM-CAP": "1.1.0",
    "R-LINE-PROPORTIONATE": "1.1.0",
    "R-CLAIM-SUBLIMIT": "1.0.0",
    "R-CLAIM-DEDUCTIBLE": "1.0.0",
    "R-CLAIM-COPAY": "1.0.0",
    "R-CLAIM-SI-CAP": "1.0.0",
    "R-CLAIM-ROUNDING": "1.0.0",
    "R-ANOM-BILLNO-REUSE": "0.9.0",
}

FINDING_META = {  # kind -> (category, uncertainty note or None)
    "IDENTITY_CONFLICT": ("IDENTITY", None),
    "DATE_CONFLICT": ("DOCUMENT", None),
    "DOCUMENT_INCOMPLETE": ("DOCUMENT", None),
    "BILL_TOTAL_MISMATCH": ("FINANCIAL", None),
    "ROOM_DAYS_EXCEED_STAY": ("FINANCIAL", None),
    "OVERRIDE_NEEDS_RECONFIRMATION": ("FINANCIAL", None),
    "POLICY_NOT_IN_FORCE": ("ELIGIBILITY", None),
    "INITIAL_WAITING_PERIOD": ("ELIGIBILITY", None),
    "SPECIFIC_WAITING_PERIOD": ("ELIGIBILITY", None),
    "POSSIBLE_PED_WITHIN_WAITING_PERIOD": ("CLINICAL", "Whether the condition meets the policy's PED definition and relates to this admission requires medical-officer judgement; the engine applies no deduction."),
    "ANOMALY_BILL_NUMBER_REUSE": ("ANOMALY", "Pattern only; common innocent causes include hospital numbering resets and data-entry errors. Not a fraud determination."),
}


class ConfigurationError(Exception):
    """Raised when configuration cannot authorise an action (e.g. missing clause reference)."""


def D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def q2(x: Decimal) -> Decimal:
    return x.quantize(PAISE, rounding=ROUND_HALF_UP)


def money(x: Decimal) -> str:
    return f"{q2(x):.2f}"


def months_between(start: date, end: date) -> int:
    """Completed calendar months from start to end."""
    m = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        m -= 1
    return m


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def sha256(obj) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def line_fingerprint(l: dict) -> str:
    keys = ("description", "category", "billed", "quantity", "unit_rate", "ward_context", "invoice_no", "service_date")
    return sha256({k: l.get(k) for k in keys})


@dataclass
class Line:
    line_id: str
    description: str
    category: str
    billed: Decimal
    ward_context: str = "WARD"
    room_category: str | None = None
    quantity: Decimal = Decimal("1")
    unit_rate: Decimal | None = None
    invoice_no: str | None = None
    service_date: str | None = None
    evidence: list[dict] = field(default_factory=list)
    fingerprint: str = ""
    remaining: Decimal = Decimal("0")

    def __post_init__(self):
        self.billed = q2(D(self.billed))
        self.quantity = D(self.quantity)
        self.unit_rate = None if self.unit_rate is None else q2(D(self.unit_rate))
        self.remaining = self.billed


class Run:
    def __init__(self, claim: dict, policy: dict, nme: dict, tariff: dict | None, checklist: dict | None = None):
        self.claim = claim
        self.policy = policy
        self.nme = nme
        self.tariff = tariff
        self.checklist = checklist
        self.lines = []
        for l in claim.get("bill_lines", []):
            ln = Line(**{k: v for k, v in l.items() if k in Line.__dataclass_fields__ and k not in ("remaining", "fingerprint")})
            ln.fingerprint = line_fingerprint(l)
            self.lines.append(ln)
        self.overrides = {(o["line_id"], o["rule_id"]): o for o in claim.get("reviewer_overrides", [])}
        self.adjustments: list[dict] = []
        self.findings: list[dict] = []
        self.queries: list[dict] = []
        self.executions: list[dict] = []
        self.blocked_scopes: set[str] = set()
        self.claim_level: dict[str, Any] = {}
        self.seq = 0

    # ---------- bookkeeping ----------
    def _next(self, prefix: str) -> str:
        self.seq += 1
        return f"{prefix}-{self.seq:04d}"

    def config_versions(self) -> dict:
        return {
            "policy_config": f"{self.policy['config_id']}@{self.policy['config_version']}",
            "nme_list": f"{self.nme['list_id']}@{self.nme['list_version']}",
            "tariff": None if not self.tariff else f"{self.tariff['tariff_id']}@{self.tariff['tariff_version']}",
            "checklist": None if not self.checklist else f"{self.checklist['checklist_id']}@{self.checklist['checklist_version']}",
            "engine": ENGINE_VERSION,
            "rules": RULE_VERSIONS,
        }

    def authority(self, rule_id: str) -> dict:
        if rule_id == "R-LINE-TARIFF":
            if not self.tariff or not self.tariff.get("agreement_clause"):
                raise ConfigurationError("tariff has no agreement_clause")
            return {"artifact": f"{self.tariff['tariff_id']}@{self.tariff['tariff_version']}", "doc_id": self.tariff["agreement_doc_id"], "clause": self.tariff["agreement_clause"]}
        ref = self.policy.get("clause_refs", {}).get(rule_id)
        if not ref:
            raise ConfigurationError(f"no clause reference configured for {rule_id}")
        return {"artifact": f"{self.policy['config_id']}@{self.policy['config_version']}", "doc_id": ref["doc_id"], "clause": ref["clause"]}

    def execute(self, rule_id: str, status: str, detail: dict):
        self.executions.append({
            "execution_id": self._next("EXE"),
            "rule_id": rule_id,
            "rule_version": RULE_VERSIONS[rule_id],
            "status": status,
            "detail": detail,
        })

    def adjust_line(self, line: Line, rule_id: str, amount: Decimal, formula: str, reason_code: str, explanation: str, evidence: list[dict] | None = None):
        engine_amount = q2(amount)
        if engine_amount <= 0 and (line.line_id, rule_id) not in self.overrides:
            return None
        origin, override_ref, applied = "ENGINE", None, engine_amount
        ov = self.overrides.get((line.line_id, rule_id))
        if ov:
            if ov["line_fingerprint"] == line.fingerprint:
                applied = min(q2(D(ov["amount"])), line.remaining)
                origin, override_ref = "REVIEWER_OVERRIDE", ov["override_id"]
                formula = f"reviewer override {ov['override_id']} ({ov['reason_code']}); engine computed {money(engine_amount)}"
                explanation = f"{explanation} Reviewer override: {ov['comment']}"
            else:
                self.finding(rule_id, "OVERRIDE_NEEDS_RECONFIRMATION", "MEDIUM", False,
                             f"Override {ov['override_id']} on {line.line_id} was made against a different version of this line; engine amount used until the reviewer reconfirms.",
                             line.evidence, route_to="PROCESSOR")
        if applied > line.remaining:
            raise AssertionError(f"{rule_id}: deduction {applied} exceeds remaining {line.remaining} on {line.line_id}")
        before = line.remaining
        line.remaining = q2(line.remaining - applied)
        adj = {
            "adjustment_id": self._next("ADJ"),
            "level": "LINE",
            "line_id": line.line_id,
            "rule_id": rule_id,
            "rule_version": RULE_VERSIONS[rule_id],
            "reason_code": reason_code,
            "amount": money(applied),
            "engine_amount": money(engine_amount),
            "origin": origin,
            "override_ref": override_ref,
            "base_before": money(before),
            "remaining_after": money(line.remaining),
            "formula": formula,
            "explanation": explanation,
            "authority": self.authority(rule_id),
            "evidence_refs": (evidence or []) + line.evidence,
        }
        self.adjustments.append(adj)
        return adj

    def adjust_claim(self, rule_id: str, amount: Decimal, base: Decimal, formula: str, reason_code: str, explanation: str, evidence: list[dict]):
        adj = {
            "adjustment_id": self._next("ADJ"),
            "level": "CLAIM",
            "line_id": None,
            "rule_id": rule_id,
            "rule_version": RULE_VERSIONS[rule_id],
            "reason_code": reason_code,
            "amount": money(amount),
            "engine_amount": money(amount),
            "origin": "ENGINE",
            "override_ref": None,
            "base_before": money(base),
            "remaining_after": money(base - amount),
            "formula": formula,
            "explanation": explanation,
            "authority": self.authority(rule_id),
            "evidence_refs": evidence,
        }
        self.adjustments.append(adj)
        return adj

    def finding(self, rule_id: str, kind: str, severity: str, blocking: bool, summary: str, evidence: list[dict], route_to: str | None = None, scopes: list[str] | None = None):
        category, note = FINDING_META[kind]
        f = {
            "finding_id": self._next("FND"),
            "rule_id": rule_id,
            "category": category,
            "kind": kind,
            "severity": severity,
            "blocking": blocking,
            "blocked_scopes": scopes or [],
            "summary": summary,
            "uncertainty_note": note,
            "evidence_refs": evidence,
            "route_to": route_to,
            "status": "OPEN",
        }
        self.findings.append(f)
        if blocking:
            self.blocked_scopes.update(scopes or ["ALL_FINANCIAL"])
        return f

    def query(self, addressed_to: str, text: str, finding_ids: list[str], doc_type: str | None = None):
        self.queries.append({
            "query_item_id": self._next("QRY"),
            "addressed_to": addressed_to,
            "requested_document_type": doc_type,
            "text": text,
            "linked_findings": finding_ids,
        })

    # ---------- gates ----------
    def gate_identity(self):
        """Harness implements exact match on normalised name + gender only.
        Production scoring (transliteration-aware similarity, initials) is catalogued, not implemented here."""
        rid = "R-GATE-IDENTITY"
        member = self.claim["member"]
        mismatches = []
        for src in self.claim.get("identity_observations", []):
            name_ok = src["name_normalised"] == member["name_normalised"]
            gender_ok = src.get("gender") in (None, member["gender"])
            if not (name_ok and gender_ok):
                mismatches.append(src)
        self.claim_level["identity_mismatched_sources"] = {m["source"] for m in mismatches}
        if mismatches:
            f = self.finding(rid, "IDENTITY_CONFLICT", "HIGH", True,
                             "Patient identity on one or more documents does not match the policy member record.",
                             [m["evidence"] for m in mismatches], route_to="PROCESSOR", scopes=["ALL_FINANCIAL"])
            self.query("HOSPITAL", "Please provide a corrected final bill showing the patient's name and gender exactly as on the admission record, or confirm the identity of the patient billed.", [f["finding_id"]], "FINAL_BILL_CORRECTED")
            self.execute(rid, "BLOCKED", {"mismatch_count": len(mismatches), "method": "exact normalised match (harness)"})
        else:
            self.execute(rid, "PASSED", {"sources_checked": len(self.claim.get("identity_observations", [])), "method": "exact normalised match (harness)"})

    def gate_dates(self):
        rid = "R-GATE-DATES"
        doas = {o["value"] for o in self.claim.get("admission_date_observations", [])}
        if len(doas) > 1:
            f = self.finding(rid, "DATE_CONFLICT", "HIGH", True,
                             f"Date of admission differs across documents: {sorted(doas)}.",
                             [o["evidence"] for o in self.claim["admission_date_observations"]], route_to="PROCESSOR",
                             scopes=["ROOM_DAYS", "WAITING_PERIOD", "PRE_POST_WINDOW"])
            self.query("HOSPITAL", "Please confirm the date and time of admission with a copy of the admission record / indoor case papers.", [f["finding_id"]], "ADMISSION_RECORD")
            self.execute(rid, "BLOCKED", {"distinct_admission_dates": sorted(doas)})
        else:
            self.execute(rid, "PASSED", {"admission_date": next(iter(doas)) if doas else None})

    def gate_itemisation(self):
        rid = "R-GATE-ITEMISATION"
        if not self.claim.get("itemised_bill_available", True):
            f = self.finding(rid, "DOCUMENT_INCOMPLETE", "HIGH", True,
                             "Only a summary bill is available; line-level rules cannot run without an itemised break-up.",
                             self.claim.get("summary_bill_evidence", []), route_to="PROCESSOR", scopes=["LINE_RULES"])
            self.query("HOSPITAL", "Please provide the itemised final bill with date-wise break-up of room, pharmacy, consumables, investigations and professional fees.", [f["finding_id"]], "FINAL_BILL_ITEMISED")
            self.execute(rid, "BLOCKED", {"itemised": False})
        else:
            stated = D(self.claim.get("bill_stated_total", "0"))
            computed = q2(sum((l.billed for l in self.lines), Decimal("0")))
            if stated and stated != computed:
                self.finding(rid, "BILL_TOTAL_MISMATCH", "MEDIUM", True,
                             f"Sum of line items {money(computed)} differs from stated bill total {money(stated)}.",
                             self.claim.get("summary_bill_evidence", []), route_to="PROCESSOR", scopes=["LINE_RULES"])
                self.execute(rid, "BLOCKED", {"stated": money(stated), "computed": money(computed)})
            else:
                self.execute(rid, "PASSED", {"stated_total": money(stated), "sum_of_lines": money(computed)})

    def doc_completeness(self):
        """Checklist items not covered by a gate; missing items raise non-blocking findings and queries."""
        rid = "R-DOC-COMPLETENESS"
        if not self.checklist:
            self.execute(rid, "NOT_APPLICABLE", {"reason": "no checklist configured"})
            return
        present = {d["type"] for d in self.claim.get("documents_present", [])}
        billed_categories = {l.category for l in self.lines}
        billed_invoices = any(l.invoice_no for l in self.lines if l.category == "PHARMACY")
        missing, required = [], []
        for item in self.checklist["items"]:
            if item.get("covered_by_gate"):
                continue
            cond = item.get("required_if")
            if cond == "PHARMACY_INVOICES_BILLED" and not billed_invoices:
                continue
            if cond and cond.startswith("CATEGORY_BILLED:") and cond.split(":", 1)[1] not in billed_categories:
                continue
            required.append(item["type"])
            if item["type"] not in present:
                missing.append(item)
        for item in missing:
            f = self.finding(rid, "DOCUMENT_INCOMPLETE", "MEDIUM", False, f"Required document missing: {item['label']}.", [], route_to="PROCESSOR")
            self.query(item.get("default_addressee", "HOSPITAL"), f"Please provide: {item['label']}.", [f["finding_id"]], item["type"])
        self.execute(rid, "REVIEW" if missing else "PASSED", {"required": required, "missing": [m["type"] for m in missing]})

    # ---------- eligibility ----------
    def _candidate_admission_dates(self) -> list[date]:
        """Established date if the date gate passed; otherwise every observed candidate.
        Eligibility rules may still run under a date conflict when the outcome is the
        same for every candidate (decision invariance); otherwise they are blocked."""
        if self.claim.get("admission_date") and "WAITING_PERIOD" not in self.blocked_scopes:
            return [date.fromisoformat(self.claim["admission_date"])]
        return sorted({date.fromisoformat(o["value"]) for o in self.claim.get("admission_date_observations", [])
                       if o["source"] not in self.claim_level.get("identity_mismatched_sources", set())})

    def elig_policy_active(self):
        rid = "R-ELIG-POLICY-ACTIVE"
        pol = self.claim["policy"]
        cands = self._candidate_admission_dates()
        if not cands:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "no admission date observed on identity-matched documents"})
            return
        start, end = date.fromisoformat(pol["period_start"]), date.fromisoformat(pol["period_end"])
        outcomes = {start <= d <= end for d in cands}
        if len(outcomes) > 1:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "outcome differs across candidate admission dates", "candidates": [str(d) for d in cands]})
            return
        if outcomes == {False}:
            self.finding(rid, "POLICY_NOT_IN_FORCE", "HIGH", True, "Admission date falls outside the policy period.", [], route_to="CRC_REFERRAL_CANDIDATE", scopes=["ALL_FINANCIAL"])
            self.execute(rid, "FAILED", {"candidates": [str(d) for d in cands]})
        else:
            self.execute(rid, "PASSED", {"evaluated_dates": [str(d) for d in cands], "invariant_under_date_conflict": len(cands) > 1,
                                         "period": [pol["period_start"], pol["period_end"]]})

    def elig_waiting(self):
        rid = "R-ELIG-WAITING"
        cands = self._candidate_admission_dates()
        if not cands:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "no admission date observed on identity-matched documents"})
            return
        pol = self.claim["policy"]
        wp = self.policy["waiting_periods"]
        inception = date.fromisoformat(pol["continuous_cover_since"])
        months_set = {months_between(inception, d) for d in cands}
        ped_outcome = {m < wp["pre_existing_disease_months"] for m in months_set}
        if len(ped_outcome) > 1:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "PED outcome differs across candidate admission dates", "candidates": [str(d) for d in cands]})
            return
        doa = cands[0]
        cover_months = min(months_set)
        cover_days = (doa - inception).days
        detail = {"continuous_cover_months": cover_months, "evaluated_dates": [str(d) for d in cands],
                  "invariant_under_date_conflict": len(cands) > 1}
        status = "PASSED"
        if cover_days < wp["initial_days"] and not self.claim.get("is_accident", False):
            self.finding(rid, "INITIAL_WAITING_PERIOD", "HIGH", False, f"Admission {cover_days} days after cover start (< {wp['initial_days']}).", [], route_to="MEDICAL_OFFICER")
            status = "REVIEW"
        for spec in wp["specific_conditions"]:
            if set(spec["procedure_codes"]) & set(self.claim.get("procedure_codes", [])):
                detail[spec["code"]] = {"required_months": spec["months"], "cover_months": cover_months}
                if cover_months < spec["months"]:
                    self.finding(rid, "SPECIFIC_WAITING_PERIOD", "HIGH", False,
                                 f"{spec['label']}: {cover_months} months of cover vs {spec['months']} required.",
                                 [], route_to="MEDICAL_OFFICER")
                    status = "REVIEW"
        for sig in self.claim.get("ped_signals", []):
            detail["ped_signal"] = sig["text"]
            if cover_months < wp["pre_existing_disease_months"]:
                f = self.finding(rid, "POSSIBLE_PED_WITHIN_WAITING_PERIOD", "HIGH", False,
                                 f"Clinical history mentions '{sig['text']}'. Continuous cover is {cover_months} months, below the "
                                 f"{wp['pre_existing_disease_months']}-month PED waiting period. Whether the condition is a PED as defined, "
                                 "and whether it is related to this admission, needs medical-officer review. No deduction or denial is applied by the engine.",
                                 [sig["evidence"]], route_to="MEDICAL_OFFICER")
                self.query("HOSPITAL", "Please provide the first consultation / past treatment records for the condition noted in the history, if available with the hospital.", [f["finding_id"]], "PAST_TREATMENT_RECORDS")
                self.query("INSURER", "Please share the proposal form and underwriting disclosures for the policy, for PED assessment.", [f["finding_id"]], "PROPOSAL_FORM")
                status = "REVIEW"
        self.execute(rid, status, detail)

    # ---------- line rules ----------
    def _line_rules_allowed(self) -> bool:
        return not ({"ALL_FINANCIAL", "LINE_RULES"} & self.blocked_scopes)

    def line_duplicate(self):
        rid = "R-LINE-DUPLICATE"
        hits = []
        groups: dict[tuple, list[Line]] = {}
        for l in self.lines:
            if l.invoice_no:
                groups.setdefault((l.invoice_no, l.service_date, l.billed, l.category), []).append(l)
        for key, ls in groups.items():
            ls = sorted(ls, key=lambda x: x.line_id)  # deterministic: keep the lowest line_id, regardless of bill order
            for dup in ls[1:]:
                self.adjust_line(dup, rid, dup.remaining, "remaining (full)", "DUPLICATE_LINE",
                                 f"Same invoice {dup.invoice_no}, date and amount already billed on {ls[0].line_id}.")
                hits.append(dup.line_id)
        self.execute(rid, "APPLIED" if hits else "NOT_APPLICABLE", {"duplicate_lines": sorted(hits)})

    def _nme_match(self, desc: str):
        d = desc.lower()
        for item in self.nme["items"]:
            for syn in item["synonyms"]:
                if syn in d:
                    return item
        return None

    def line_nonpayable(self):
        rid = "R-LINE-NONPAYABLE"
        hits = []
        for l in sorted(self.lines, key=lambda x: x.line_id):
            if l.remaining == 0:
                continue
            item = self._nme_match(l.description)
            if item:
                treatment = self.policy["non_payable"]["treatment"][item["category"]]
                self.adjust_line(l, rid, l.remaining, "remaining (full)", f"NME_{item['category']}",
                                 f"'{l.description}' matched {item['item_code']} ({item['canonical']}); treatment {treatment} under list {self.nme['list_id']} v{self.nme['list_version']}.")
                hits.append({"line_id": l.line_id, "item_code": item["item_code"]})
        self.execute(rid, "APPLIED" if hits else "NOT_APPLICABLE", {"matches": hits})

    def line_tariff(self):
        rid = "R-LINE-TARIFF"
        if not self.tariff or not (self.claim.get("hospital_is_network") and self.policy["tariff"]["apply_network_tariff_on_reimbursement"]):
            self.execute(rid, "NOT_APPLICABLE", {"reason": "no applicable network tariff"})
            return
        hits = []
        for l in sorted(self.lines, key=lambda x: x.line_id):
            if l.remaining == 0:
                continue
            for cap in self.tariff["item_caps"]:
                if any(k in l.description.lower() for k in cap["match_keys"]):
                    allowed = D(cap["max_rate"]) * l.quantity
                    excess = l.remaining - allowed
                    if excess > 0 or (l.line_id, rid) in self.overrides:
                        self.adjust_line(l, rid, max(excess, Decimal("0")), f"remaining {money(l.remaining)} - tariff {cap['max_rate']} x qty {l.quantity}",
                                         "TARIFF_EXCESS", f"Billed above agreed tariff item {cap['tariff_item_code']} ({self.tariff['tariff_id']} v{self.tariff['tariff_version']}).")
                        hits.append(l.line_id)
        self.execute(rid, "APPLIED" if hits else "NOT_APPLICABLE", {"capped_lines": hits})

    def _room_limits(self):
        base_si = D(self.claim["policy"]["base_sum_insured"])
        rr = self.policy["room_rent"]
        normal = q2(base_si * D(rr["normal_room_limit"]["percent"]) / 100)
        icu = q2(base_si * D(rr["icu_limit"]["percent"]) / 100)
        return normal, icu

    def _allowed_room_days(self):
        doa, dod = self.claim.get("admission_date"), self.claim.get("discharge_date")
        if not doa or not dod:
            return None
        nights = (date.fromisoformat(dod) - date.fromisoformat(doa)).days
        conv = self.policy["room_rent"].get("room_day_count", "MIDNIGHTS")
        return max(1, nights) if conv == "MIDNIGHTS" else nights + 1

    def line_room_cap(self):
        rid = "R-LINE-ROOM-CAP"
        if "ROOM_DAYS" in self.blocked_scopes:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "room days depend on a disputed admission date"})
            return
        normal, icu = self._room_limits()
        self.claim_level["eligible_normal_rate"] = normal
        hits = []
        room_lines = sorted([l for l in self.lines if l.category in ("ROOM", "ICU_ROOM")], key=lambda x: x.line_id)
        billed_days = sum((l.quantity for l in room_lines), Decimal("0"))
        allowed_days = self._allowed_room_days()
        if allowed_days is not None and billed_days > allowed_days:
            self.finding(rid, "ROOM_DAYS_EXCEED_STAY", "MEDIUM", False,
                         f"Room/ICU days billed ({billed_days}) exceed the stay ({allowed_days} days under the {self.policy['room_rent'].get('room_day_count', 'MIDNIGHTS')} convention). No automatic deduction; reviewer to confirm.",
                         [e for l in room_lines for e in l.evidence], route_to="PROCESSOR")
        for l in room_lines:
            if l.remaining == 0:
                continue
            limit = icu if l.category == "ICU_ROOM" else normal
            allowed = limit * l.quantity
            excess = l.remaining - allowed
            if excess > 0:
                self.adjust_line(l, rid, excess, f"remaining {money(l.remaining)} - limit {money(limit)}/day x {l.quantity} days",
                                 "ROOM_RENT_EXCESS" if l.category == "ROOM" else "ICU_RENT_EXCESS",
                                 f"Eligible {'ICU' if l.category == 'ICU_ROOM' else 'room'} rent is {money(limit)}/day.")
                hits.append(l.line_id)
        # actual normal-room rate for the proportionate rule: order-independent basis from config
        normal_lines = [l for l in room_lines if l.category == "ROOM" and l.unit_rate is not None]
        basis = self.policy["room_rent"]["proportionate_deduction"].get("actual_rate_basis", "DAY_WEIGHTED")
        actual = None
        if normal_lines:
            if basis == "HIGHEST":
                actual = max(l.unit_rate for l in normal_lines)
            else:  # DAY_WEIGHTED
                days = sum((l.quantity for l in normal_lines), Decimal("0"))
                actual = sum((l.unit_rate * l.quantity for l in normal_lines), Decimal("0")) / days
        self.claim_level["actual_normal_rate"] = actual
        self.execute(rid, "APPLIED" if hits else "NOT_APPLICABLE",
                     {"eligible_normal_per_day": money(normal), "eligible_icu_per_day": money(icu),
                      "actual_normal_per_day": None if actual is None else money(actual), "actual_rate_basis": basis,
                      "billed_room_days": str(billed_days), "allowed_room_days": allowed_days, "lines": hits})

    def line_proportionate(self):
        rid = "R-LINE-PROPORTIONATE"
        cfg = self.policy["room_rent"]["proportionate_deduction"]
        if "ROOM_DAYS" in self.blocked_scopes:
            self.execute(rid, "SKIPPED_BLOCKED", {"reason": "room category/days not established"})
            return
        if not cfg["enabled"]:
            self.execute(rid, "NOT_APPLICABLE", {"reason": "disabled in policy config"})
            return
        if self.tariff and cfg["skip_if_hospital_has_uniform_pricing"] and self.tariff.get("uniform_pricing_across_room_categories") and self.claim.get("hospital_is_network"):
            self.execute(rid, "NOT_APPLICABLE", {"reason": "hospital tariff does not vary by room category"})
            return
        eligible = self.claim_level.get("eligible_normal_rate")
        actual = self.claim_level.get("actual_normal_rate")
        if not actual or actual <= eligible:
            self.execute(rid, "NOT_APPLICABLE", {"reason": "actual room rate within eligibility", "eligible": None if eligible is None else money(eligible), "actual": None if actual is None else money(actual)})
            return
        ratio = eligible / actual  # exact Decimal ratio; applied per line then quantised
        hits = []
        for l in sorted(self.lines, key=lambda x: x.line_id):
            if l.remaining == 0 or l.category not in cfg["applies_to_categories"] or l.ward_context in cfg["exempt_ward_contexts"]:
                continue
            payable_part = q2(l.remaining * ratio)
            deduction = l.remaining - payable_part
            self.adjust_line(l, rid, deduction, f"remaining {money(l.remaining)} x (1 - {money(eligible)}/{money(actual)})",
                             "PROPORTIONATE_DEDUCTION",
                             f"Room occupied at {money(actual)}/day ({cfg.get('actual_rate_basis', 'DAY_WEIGHTED').lower().replace('_', '-')}) vs eligible {money(eligible)}/day; associated charges paid in proportion.")
            hits.append(l.line_id)
        self.execute(rid, "APPLIED" if hits else "NOT_APPLICABLE", {"ratio": f"{money(eligible)}/{money(actual)}", "lines": hits})

    # ---------- claim-level ----------
    def claim_rules(self):
        admissible = q2(sum((l.remaining for l in self.lines), Decimal("0")))
        self.claim_level["admissible_after_line_rules"] = admissible
        running = admissible
        member, pol = self.claim["member"], self.claim["policy"]

        rid = "R-CLAIM-SUBLIMIT"
        applied = []
        for sl in self.policy["sub_limits"]:
            if set(sl["procedure_codes"]) & set(self.claim.get("procedure_codes", [])):
                cap = D(sl["amount"])
                if running > cap:
                    self.adjust_claim(rid, running - cap, running, f"{money(running)} - sub-limit {sl['amount']}", "SUBLIMIT_EXCESS", f"{sl['code']} applies.",
                                      [{"record_type": "CLAIM_RECORD", "record_id": self.claim["claim_id"], "field": "procedure_codes"}])
                    running = cap
                    applied.append(sl["code"])
        self.execute(rid, "APPLIED" if applied else "NOT_APPLICABLE", {"sub_limits": applied})

        rid = "R-CLAIM-DEDUCTIBLE"
        ded = D(self.policy["deductible"]["amount"])
        if ded > 0:
            take = min(ded, running)
            self.adjust_claim(rid, take, running, f"min(deductible {money(ded)}, {money(running)})", "DEDUCTIBLE", "Policy deductible.",
                              [{"record_type": "POLICY_RECORD", "record_id": pol["policy_no"], "field": "deductible"}])
            running -= take
            self.execute(rid, "APPLIED", {"deductible": money(ded)})
        else:
            self.execute(rid, "NOT_APPLICABLE", {"deductible": "0.00"})

        rid = "R-CLAIM-COPAY"
        doa = date.fromisoformat(self.claim["admission_date"])
        age = age_on(date.fromisoformat(member["dob"]), doa)
        pct, rule_code = Decimal("0"), None
        for r in self.policy["co_payment"]["rules"]:
            if age >= r["condition"]["age_at_admission_gte"]:
                pct, rule_code = D(r["percent"]), r["rule_code"]
        if pct > 0:
            copay = q2(running * pct / 100)
            self.adjust_claim(rid, copay, running, f"{money(running)} x {pct}%", "CO_PAYMENT", f"{rule_code}: age {age} at admission.",
                              [{"record_type": "MEMBER_RECORD", "record_id": member["member_id"], "field": "dob"},
                               {"record_type": "CLAIM_RECORD", "record_id": self.claim["claim_id"], "field": "admission_date"}])
            running -= copay
            self.execute(rid, "APPLIED", {"age_at_admission": age, "percent": str(pct), "base": money(running + copay)})
        else:
            self.execute(rid, "NOT_APPLICABLE", {"age_at_admission": age})

        rid = "R-CLAIM-SI-CAP"
        available = D(pol["base_sum_insured"]) + (D(pol.get("cumulative_bonus", "0")) if self.policy["sum_insured"]["cumulative_bonus_counts_toward_available_si"] else 0) - D(pol.get("paid_in_current_year", "0"))
        available = max(available, Decimal("0"))
        if running > available:
            self.adjust_claim(rid, running - available, running, f"{money(running)} - available SI {money(available)}", "SUM_INSURED_EXHAUSTED",
                              "Amount exceeds available sum insured for the policy year.",
                              [{"record_type": "SI_LEDGER", "record_id": f"{pol['policy_no']}/{member['member_id']}", "field": "available_at_evaluation"}])
            running = available
            self.execute(rid, "APPLIED", {"available_si": money(available)})
        else:
            self.execute(rid, "NOT_APPLICABLE", {"available_si": money(available)})

        rid = "R-CLAIM-ROUNDING"
        final = running.quantize(RUPEE, rounding=ROUND_HALF_UP) if self.policy["rounding"]["final_payable"] == "RUPEE_HALF_UP" else q2(running)
        diff = running - final
        if diff != 0:
            self.adjust_claim(rid, diff, running, f"{money(running)} -> {final} ({self.policy['rounding']['final_payable']})", "ROUNDING",
                              "Final payable rounded per configuration; a negative amount increases the payable.",
                              [{"record_type": "CONFIG", "record_id": f"{self.policy['config_id']}@{self.policy['config_version']}", "field": "rounding.final_payable"}])
        self.execute(rid, "APPLIED" if diff != 0 else "NOT_APPLICABLE", {"before": money(running), "after": money(final)})
        return q2(final)

    # ---------- anomaly ----------
    def anomaly_billno(self):
        rid = "R-ANOM-BILLNO-REUSE"
        hits = []
        for other in self.claim.get("portfolio_bill_number_index", []):
            if other["bill_no"] == self.claim.get("bill_no") and other["hospital_id"] == self.claim.get("hospital_id") and other["member_id"] != self.claim["member"]["member_id"]:
                hits.append(other["claim_id"])
        if hits:
            self.finding(rid, "ANOMALY_BILL_NUMBER_REUSE", "MEDIUM", False,
                         f"Bill number {self.claim['bill_no']} from the same hospital also appears on claim(s) {hits} for a different member. "
                         "This is a pattern for review, not a fraud determination.",
                         [self.claim.get("bill_no_evidence", {})], route_to="FWA_REVIEW")
        self.execute(rid, "FLAGGED" if hits else "NOT_APPLICABLE", {"other_claims": hits})

    # ---------- orchestration ----------
    def run(self) -> dict:
        self.gate_identity()
        self.gate_dates()
        self.gate_itemisation()
        self.doc_completeness()
        self.elig_policy_active()
        self.elig_waiting()
        payable = None
        if self._line_rules_allowed():
            self.line_duplicate()
            self.line_nonpayable()
            self.line_tariff()
            self.line_room_cap()
            self.line_proportionate()
            if not ({"ALL_FINANCIAL", "LINE_RULES", "ROOM_DAYS"} & self.blocked_scopes):
                payable = self.claim_rules()
            else:
                for rid in ["R-CLAIM-SUBLIMIT", "R-CLAIM-DEDUCTIBLE", "R-CLAIM-COPAY", "R-CLAIM-SI-CAP", "R-CLAIM-ROUNDING"]:
                    self.execute(rid, "SKIPPED_BLOCKED", {"reason": f"blocked scopes {sorted(self.blocked_scopes)}"})
        else:
            for rid in ["R-LINE-DUPLICATE", "R-LINE-NONPAYABLE", "R-LINE-TARIFF", "R-LINE-ROOM-CAP", "R-LINE-PROPORTIONATE",
                        "R-CLAIM-SUBLIMIT", "R-CLAIM-DEDUCTIBLE", "R-CLAIM-COPAY", "R-CLAIM-SI-CAP", "R-CLAIM-ROUNDING"]:
                self.execute(rid, "SKIPPED_BLOCKED", {"reason": f"blocked scopes {sorted(self.blocked_scopes)}"})
        self.anomaly_billno()
        return self._result(payable)

    def _recommendation_type(self, payable):
        open_review = [f for f in self.findings if not f["blocking"] and f["route_to"] == "MEDICAL_OFFICER"]
        if any(f["route_to"] == "CRC_REFERRAL_CANDIDATE" for f in self.findings):
            return "REFER_CRC"
        if self.blocked_scopes:
            return "QUERY_AND_REFER_MEDICAL" if open_review else "QUERY"
        if open_review:
            return "REFER_MEDICAL"
        billed = sum((l.billed for l in self.lines), Decimal("0"))
        return "PAY_FULL" if payable is not None and q2(billed) == payable else "PAY_PARTIAL"

    def _result(self, payable):
        billed = q2(sum((l.billed for l in self.lines), Decimal("0")))
        line_ded = q2(sum((D(a["amount"]) for a in self.adjustments if a["level"] == "LINE"), Decimal("0")))
        claim_ded = q2(sum((D(a["amount"]) for a in self.adjustments if a["level"] == "CLAIM"), Decimal("0")))
        cv = self.config_versions()
        out = {
            "engine_version": ENGINE_VERSION,
            "claim_id": self.claim["claim_id"],
            "evaluation_id": self.claim.get("evaluation_id"),
            "config_versions": cv,
            "input_hash": sha256({"claim": self.claim, "config_versions": cv}),
            "recommendation": {
                "type": self._recommendation_type(payable),
                "computed": payable is not None,
                "recommended_payable": None if payable is None else money(payable),
                "billed_total": money(billed),
                "bill_stated_total": self.claim.get("bill_stated_total"),
                "itemised_lines_available": bool(self.lines),
                "line_level_deductions": money(line_ded),
                "claim_level_deductions": money(claim_ded),
                "admissible_after_line_rules": None if "admissible_after_line_rules" not in self.claim_level else money(self.claim_level["admissible_after_line_rules"]),
                "blocked_scopes": sorted(self.blocked_scopes),
                "human_decision_required": True,
            },
            "lines": [{"line_id": l.line_id, "description": l.description, "category": l.category, "ward_context": l.ward_context,
                       "billed": money(l.billed), "payable": money(l.remaining) if self._line_rules_allowed() else None,
                       "fingerprint": l.fingerprint} for l in self.lines],
            "adjustments": self.adjustments,
            "findings": self.findings,
            "query_items": self.queries,
            "rule_executions": self.executions,
        }
        out["output_hash"] = sha256({k: v for k, v in out.items() if k != "output_hash"})
        return out


def evaluate(claim: dict, policy: dict, nme: dict, tariff: dict | None, checklist: dict | None = None) -> dict:
    return Run(claim, policy, nme, tariff, checklist).run()
