"""Render trace outputs into markdown tables and hash-chained audit-event fixtures.

Usage: python3 verification/render_traces.py   (after run_traces.py)
Writes: verification/trace-tables.md, fixtures/claims/<trace>.audit.json
All timestamps are synthetic. Actor IDs are role placeholders, not people.
The chain check below is a self-consistency check (each hash recomputes and links to its predecessor);
it does not prove that the events reflect what happened.
"""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Audit event types used across the pack (05 §2.2 lists the full vocabulary).
# Each trace spec is an ordered script of steps; "DOCS" expands to receive/classify/extract per document,
# "RULES" expands to RULE_RUN_STARTED, one RULE_EXECUTED per execution (milliseconds apart) and RECOMMENDATION_CREATED.
TRACES = {
    "trace-1-straightforward": {
        "start": "2026-08-14T10:02:00+05:30",
        "script": [("DOCS", "all"), ("RULES", None),
                   ("USER:PROC-07", "REVIEWER_VIEWED_RECOMMENDATION", {}),
                   ("USER:PROC-07", "DECISION_RECORDED", {"decision": "APPROVED_PARTIAL", "approved_payable": "107591.00",
                                                          "second_approval": "not required (payable ≤ PROC-07 illustrative limit 1,50,000; deductions 1.6% of billed)",
                                                          "comment": "NME deductions verified against bill page 2."}),
                   ("SYSTEM", "SETTLEMENT_WORKSHEET_EXPORTED", {"format": "JSON+PDF", "target": "TMS_STUB"})],
    },
    "trace-2-interacting-adjustments": {
        "start": "2026-07-09T11:20:00+05:30",
        "script": [("DOCS", "all"), ("RULES", None),
                   ("USER:PROC-11", "REVIEWER_VIEWED_RECOMMENDATION", {}),
                   ("USER:PROC-11", "REVIEWER_CONFIRMED_FINDING", {"adjustment_rule": "R-LINE-DUPLICATE", "line_id": "L11", "comment": "DOC-0002-PH1-COPY is a photocopy of PH-2291."}),
                   ("USER:PROC-11", "APPROVAL_REQUESTED", {"proposed_disposition": "APPROVED_PARTIAL", "approved_payable": "85000.00",
                                                           "reason": "Second approval required by WFCFG-TENANT-DEMO: total deductions 50.7% of billed > 30%."}),
                   ("USER:SUP-02", "APPROVAL_GRANTED", {}),
                   ("SYSTEM", "DECISION_RECORDED", {"decision": "APPROVED_PARTIAL", "approved_payable": "85000.00", "decided_by": "PROC-11", "second_approver": "SUP-02"}),
                   ("SYSTEM", "SETTLEMENT_WORKSHEET_EXPORTED", {"format": "JSON+PDF", "target": "TMS_STUB"})],
    },
    "trace-2b-reviewer-override": {
        "start": "2026-07-09T11:31:00+05:30",
        "branch_from": ("trace-2-interacting-adjustments", "RECOMMENDATION_CREATED"),
        "note": "What-if branch of trace 2 (not loaded into the DB): right after the first recommendation, PROC-11 overrides the CT tariff deduction instead of approving. The audit chain forks from trace 2's RECOMMENDATION_CREATED event.",
        "script": [("USER:PROC-11", "REVIEWER_ACTION_RECORDED", {"action": "OVERRIDE_ADJUSTMENT", "override_id": "RA-0207", "line_id": "L14", "rule_id": "R-LINE-TARIFF",
                                                                 "after_amount": "0.00", "reason_code": "TARIFF_ITEM_NOT_APPLICABLE"}),
                   ("SYSTEM", "RECOMMENDATION_MARKED_STALE", {"evaluation_id": "EVAL-0002-v1", "reason": "REVIEWER_CORRECTION"}),
                   ("RULES", None)],
    },
    "trace-3a-insufficient-conflicting": {
        "start": "2026-09-10T09:45:00+05:30",
        "script": [("DOCS", "all"), ("RULES", None),
                   ("USER:PROC-04", "REVIEWER_VIEWED_RECOMMENDATION", {}),
                   ("USER:PROC-04", "QUERY_APPROVED", {"query_items": 5, "channel": "TMS_STUB", "addressees": ["HOSPITAL", "INSURER"]}),
                   ("USER:MO-01", "MEDICAL_REVIEW_OPENED", {"finding_kind": "POSSIBLE_PED_WITHIN_WAITING_PERIOD"}),
                   ("USER:FWA-01", "ANOMALY_TRIAGED", {"finding_kind": "ANOMALY_BILL_NUMBER_REUSE", "disposition": "ACCEPTED_FOR_REVIEW"})],
    },
    "trace-3b-after-new-evidence": {
        "start": "2026-09-14T15:10:00+05:30",
        "continue_from": "trace-3a-insufficient-conflicting",
        "script": [("DOC_RECEIVED_ONLY", "DOC-0003-FB2"), ("DOC_RECEIVED_ONLY", "DOC-0003-AR"),
                   ("SYSTEM", "RECOMMENDATION_MARKED_STALE", {"evaluation_id": "EVAL-0003-v1", "reason": "NEW_EVIDENCE"}),
                   ("DOC_PROCESS_ONLY", "DOC-0003-FB2"), ("DOC_PROCESS_ONLY", "DOC-0003-AR"),
                   ("USER:PROC-04", "REVIEWER_ACTION_RECORDED", {"action": "RESOLVE_CONFLICT", "finding_kind": "DATE_CONFLICT", "resolution": "2026-09-02", "evidence": "DOC-0003-AR p1"}),
                   ("USER:PROC-04", "REVIEWER_ACTION_RECORDED", {"action": "RESOLVE_CONFLICT", "finding_kind": "IDENTITY_CONFLICT", "resolution": "Corrected bill DOC-0003-FB2 supersedes DOC-0003-SB"}),
                   ("RULES", None),
                   ("USER:MO-01", "MEDICAL_REVIEW_PENDING", {"finding_kind": "POSSIBLE_PED_WITHIN_WAITING_PERIOD", "awaiting": ["PAST_TREATMENT_RECORDS", "PROPOSAL_FORM"]})],
    },
}


def h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


CHAIN_TAIL = {}
EVENTS = {}


def audit_for(name, spec, out, inp):
    t = datetime.fromisoformat(spec["start"])
    events, prev, base_seq = [], "GENESIS", 0
    if spec.get("continue_from"):
        prev, base_seq = CHAIN_TAIL[spec["continue_from"]]
    if spec.get("branch_from"):
        src, upto = spec["branch_from"]
        fork = next(e for e in EVENTS[src] if e["event_type"] == upto)
        prev, base_seq = fork["event_hash"], fork["seq"]
    types = {d["document_id"]: d["type"] for d in inp.get("documents_present", [])}

    def emit(actor, etype, payload, step=timedelta(seconds=20)):
        nonlocal t, prev
        t += step
        ev = {"seq": base_seq + len(events) + 1, "claim_id": out["claim_id"], "occurred_at": t.isoformat(timespec="milliseconds"), "actor": actor,
              "event_type": etype, "payload": payload, "prev_hash": prev}
        ev["event_hash"] = h(ev)
        prev = ev["event_hash"]
        events.append(ev)

    def receive(doc):
        emit("INTEGRATION:TMS", "DOCUMENT_RECEIVED", {"document_id": doc, "declared_type": types.get(doc), "sha256": h(doc)[:16] + "…(synthetic)"}, timedelta(seconds=5))

    def process(doc):
        emit("SYSTEM", "DOCUMENT_CLASSIFIED", {"document_id": doc, "type": types.get(doc), "classifier": "doc-classifier@0.4 (proposed)"}, timedelta(seconds=6))
        emit("SYSTEM", "EXTRACTION_COMPLETED", {"document_id": doc, "extractor": "extract-pipeline@0.7 (proposed)"}, timedelta(seconds=25))

    for step in spec["script"]:
        kind = step[0]
        if kind == "DOCS":
            for d in inp.get("documents_present", []):
                receive(d["document_id"])
            for d in inp.get("documents_present", []):
                process(d["document_id"])
        elif kind == "DOC_RECEIVED_ONLY":
            receive(step[1])
        elif kind == "DOC_PROCESS_ONLY":
            process(step[1])
        elif kind == "RULES":
            emit("SYSTEM", "RULE_RUN_STARTED", {"evaluation_id": out["evaluation_id"], "config_versions": out["config_versions"]["policy_config"], "input_hash": out["input_hash"]}, timedelta(seconds=2))
            for ex in out["rule_executions"]:
                emit("SYSTEM", "RULE_EXECUTED", {"rule_id": ex["rule_id"], "rule_version": ex["rule_version"], "status": ex["status"]}, timedelta(milliseconds=12))
            emit("SYSTEM", "RECOMMENDATION_CREATED", {"evaluation_id": out["evaluation_id"], "type": out["recommendation"]["type"],
                                                      "recommended_payable": out["recommendation"]["recommended_payable"], "output_hash": out["output_hash"]}, timedelta(milliseconds=40))
        else:
            actor, etype, payload = step
            emit(actor, etype, payload, timedelta(seconds=45))
    CHAIN_TAIL[name] = (prev, events[-1]["seq"])
    EVENTS[name] = events
    return events


def fmt(x):
    if x is None:
        return "—"
    return f"{float(x):,.2f}"


def tables(name, out, events, spec):
    rec = out["recommendation"]
    md = [f"### Output: {name}", ""]
    if spec.get("note"):
        md += [f"_{spec['note']}_", ""]
    md.append(f"Recommendation **{rec['type']}** · computed: {rec['computed']} · recommended payable: {fmt(rec['recommended_payable'])} · "
              f"billed (lines): {fmt(rec['billed_total'])} · stated bill total: {fmt(rec['bill_stated_total'])}")
    md.append("")
    if out["lines"]:
        md += ["| Line | Description | Category | Context | Billed (₹) | Payable (₹) |", "|---|---|---|---|---:|---:|"]
        for l in out["lines"]:
            md.append(f"| {l['line_id']} | {l['description']} | {l['category']} | {l['ward_context']} | {fmt(l['billed'])} | {fmt(l['payable'])} |")
        md.append("")
    if out["adjustments"]:
        md += ["| # | Rule (version) | Level / line | Reason | Origin | Base before (₹) | Deduction (₹) | Remaining (₹) | Authority (clause) | Formula |", "|---|---|---|---|---|---:|---:|---:|---|---|"]
        for i, a in enumerate(out["adjustments"], 1):
            md.append(f"| {i} | {a['rule_id']} ({a['rule_version']}) | {a['level']} {a['line_id'] or ''} | {a['reason_code']} | {a['origin']} | {fmt(a['base_before'])} | {fmt(a['amount'])} | {fmt(a['remaining_after'])} | {a['authority']['clause']} | `{a['formula']}` |")
        md.append("")
    md += ["Rule execution order:", "", "| Step | Rule | Status | Key detail |", "|---|---|---|---|"]
    for i, e in enumerate(out["rule_executions"], 1):
        d = json.dumps(e["detail"], ensure_ascii=False)
        d = d if len(d) < 140 else d[:137] + "…"
        md.append(f"| {i} | {e['rule_id']} | {e['status']} | `{d}` |")
    md.append("")
    if out["findings"]:
        md += ["| Finding | Category | Kind | Severity | Blocking | Routed to | Summary |", "|---|---|---|---|---|---|---|"]
        for f in out["findings"]:
            md.append(f"| {f['finding_id']} | {f['category']} | {f['kind']} | {f['severity']} | {f['blocking']} | {f['route_to']} | {f['summary']} |")
        md.append("")
    if out["query_items"]:
        md += ["| Query item | To | Document requested | Text |", "|---|---|---|---|"]
        for q in out["query_items"]:
            md.append(f"| {q['query_item_id']} | {q['addressed_to']} | {q['requested_document_type']} | {q['text']} |")
        md.append("")
    md += ["Audit events (hash-chained; full list in the `.audit.json` fixture):", "", "| Seq | Time (IST) | Actor | Event | Payload (abridged) |", "|---|---|---|---|---|"]
    keep = [e for e in events if e["event_type"] not in ("RULE_EXECUTED", "DOCUMENT_CLASSIFIED", "EXTRACTION_COMPLETED", "DOCUMENT_RECEIVED")]
    for e in keep:
        p = json.dumps(e["payload"], ensure_ascii=False)
        p = p if len(p) < 120 else p[:117] + "…"
        md.append(f"| {e['seq']} | {e['occurred_at'][11:23]} | {e['actor']} | {e['event_type']} | `{p}` |")
    n_doc = sum(1 for e in events if e["event_type"] == "DOCUMENT_RECEIVED")
    md.append(f"\n({len(events)} events in total, including {n_doc} DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)\n")
    return md


all_md = ["<!-- Generated by verification/render_traces.py from fixtures/claims/*.output.json. Do not hand-edit. -->", ""]
for name, spec in TRACES.items():
    out = json.loads((ROOT / f"fixtures/claims/{name}.output.json").read_text())
    inp = json.loads((ROOT / f"fixtures/claims/{name}.input.json").read_text())
    start_prev = CHAIN_TAIL[spec["continue_from"]][0] if spec.get("continue_from") else "GENESIS"
    if spec.get("branch_from"):
        start_prev = next(e for e in EVENTS[spec["branch_from"][0]] if e["event_type"] == spec["branch_from"][1])["event_hash"]
    events = audit_for(name, spec, out, inp)
    prev = start_prev
    for e in events:  # self-consistency check
        body = {k: v for k, v in e.items() if k != "event_hash"}
        assert e["prev_hash"] == prev and h(body) == e["event_hash"], f"broken chain in {name}"
        prev = e["event_hash"]
    times = [e["occurred_at"] for e in events]
    assert times == sorted(times), f"events out of time order in {name}"
    (ROOT / f"fixtures/claims/{name}.audit.json").write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n")
    all_md += tables(name, out, events, spec)
(ROOT / "verification/trace-tables.md").write_text("\n".join(all_md))
print("rendered", len(TRACES), "traces; audit chains self-consistent and time-ordered")
