"""Worksheet rendering and the export job.

Phase 1 has no TMS adapter (BL-20, needs the customer's TMS specification). The development exporter writes the
worksheet JSON into the object store and marks the export ACKNOWLEDGED with that key, so the end-to-end path and
its audit events can be exercised. A TMS adapter replaces `LocalFileExporter` without changing callers.
"""
from __future__ import annotations

import io
import json

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import audit
from .db import Conn
from .money import inr, to_paise


def render_worksheet_pdf(ws: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    w, h = A4
    y = h - 40

    def line(text, size=9, bold=False, x=40, gap=13):
        nonlocal y
        if y < 60:
            c.showPage()
            y = h - 40
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, text[:120])
        y -= gap

    line("SETTLEMENT WORKSHEET", 14, True, gap=20)
    line(f"Worksheet {ws['worksheet_id']}  ·  Claim {ws['claim_id']}  ·  Decision {ws['decision']['decision_id']} ({ws['decision']['disposition']})")
    line(f"Decided by {ws['decision']['decided_by']}" + (f", second approver {ws['decision']['second_approver']}" if ws['decision'].get('second_approver') else ""))
    a = ws["amounts"]
    line(f"Billed Rs. {inr(to_paise(a['billed']))}   Approved Rs. {inr(to_paise(a['approved']))}   Disallowed Rs. {inr(to_paise(a['disallowed_total']))}", 10, True, gap=18)
    line("Amounts disallowed, with reasons and policy references", 10, True)
    for d in ws["disallowances"]:
        line(f"{d['line_id']:>5}  Rs. {inr(to_paise(d['amount'])):>12}  {d['clause']}")
        line(f"        {d['reason']}", 8, gap=11)
    y -= 6
    line("Line table", 10, True)
    for l in ws["line_table"]:
        payable = "—" if l["payable"] is None else inr(to_paise(l["payable"]))
        line(f"{l['line_id']:>5}  {l['description'][:60]:<60}  {inr(to_paise(l['billed'])):>12}  {payable:>12}", 8, gap=11)
    y -= 6
    line("Grievance route (to be completed with customer-supplied text before go-live)", 10, True)
    for k, v in ws["grievance_route"].items():
        line(f"{k.replace('_', ' ')}: {v}", 8, gap=11)
    y -= 6
    p = ws["provenance"]
    line(f"Engine {p['engine_version']} · output {p['output_hash'][:23]}…", 7)
    c.showPage()
    c.save()
    return buf.getvalue()


class LocalFileExporter:
    target = "TMS"

    def __init__(self, store):
        self.store = store

    def __call__(self, conn: Conn, job: dict):
        decision_id = job["subject_id"]
        d = conn.fetch_one("SELECT d.*, e.export_id FROM decision d JOIN export_record e ON e.tenant_id=d.tenant_id AND e.decision_id=d.decision_id"
                           " AND e.target='TMS' WHERE d.tenant_id=$1 AND d.decision_id=$2", job["tenant_id"], decision_id)
        if not d or not d["worksheet"]:
            return
        key = f"{job['tenant_id']}/{d['claim_id']}/exports/{decision_id}.json"
        self.store.put_once(key, json.dumps(d["worksheet"], sort_keys=True, indent=1).encode())
        conn.execute("UPDATE export_record SET state='ACKNOWLEDGED', target_reference=$3 WHERE tenant_id=$1 AND export_id=$2",
                     job["tenant_id"], d["export_id"], key)
        conn.execute("UPDATE claim SET status='EXPORTED', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2 AND status='FINALISED'",
                     job["tenant_id"], d["claim_id"])
        audit.append(conn, job["tenant_id"], d["claim_id"], "INTEGRATION:LOCAL_EXPORTER", "EXPORT_ACKNOWLEDGED",
                     {"decision_id": decision_id, "target": "TMS", "reference": key})
