"""Synthetic claim documents for the three demo claims in the research pack (traces 1, 2 and 3a→3b).

Every page carries a 'SYNTHETIC — FOR SOFTWARE TESTING ONLY' banner. Names, hospitals, numbers and amounts are
invented (they mirror the pack's fixtures). The PDFs have a native text layer, so the heuristic extractor can read
them without OCR. Run `python -m aw.synthetic <out_dir>` to write them.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .money import inr, to_paise

PACK = Path(__file__).resolve().parents[3]
BANNER = "SYNTHETIC - FOR SOFTWARE TESTING ONLY - NOT A REAL PATIENT, HOSPITAL OR POLICY"
HOSPITALS = {
    "HOSP-ILL-NN-07": "Illustrative Hospital NN-07 (synthetic)",
    "HOSP-ILL-NW-01": "Illustrative Network Hospital 01 (synthetic)",
    "HOSP-ILL-NN-12": "Illustrative Hospital NN-12 (synthetic)",
}
TITLES = {"M": "Mr.", "F": "Mrs."}


def _dmy(iso: str, sep: str = "/") -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year}"


def _name(norm: str) -> str:
    return " ".join(t.capitalize() for t in norm.split())


def _amt(x: str) -> str:
    return inr(to_paise(x))


class Doc:
    def __init__(self, title: str):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4, invariant=1)
        self.c.setTitle(title)
        self.c.setAuthor("AW synthetic generator")
        self.y = 0.0
        self.title = title
        self._page_start()

    def _page_start(self):
        w, h = A4
        self.c.setFont("Helvetica", 7)
        self.c.drawString(40, h - 24, BANNER)
        self.c.setFont("Helvetica-Bold", 13)
        self.c.drawString(40, h - 52, self.title)
        self.y = h - 80

    def line(self, text: str, x: float = 40, size: float = 10, bold: bool = False, gap: float = 16):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(x, self.y, text)
        self.y -= gap

    def new_page(self, title: str | None = None):
        self.c.showPage()
        if title:
            self.title = title
        self._page_start()

    def table(self, rows: list[dict], per_page: int = 12):
        cols = [("No", 40, "l"), ("Date", 68, "l"), ("Description", 128, "l"), ("Inv No", 352, "l"), ("Ward", 410, "l"),
                ("Qty", 448, "l"), ("Rate", 520, "r"), ("Amount", 575, "r")]

        def header():
            self.c.setFont("Helvetica-Bold", 9)
            for name, x, al in cols:
                (self.c.drawRightString if al == "r" else self.c.drawString)(x, self.y, name)
            self.y -= 15

        for i, r in enumerate(rows):
            if i % per_page == 0:
                if i:
                    self.new_page(self.title.split(" (")[0] + " (continued)")
                header()
            self.c.setFont("Helvetica", 9)
            vals = [r["line_id"], _dmy(r["service_date"]) if r.get("service_date") else "", r["description"], r.get("invoice_no") or "-",
                    r.get("ward_context") or "WARD", r.get("quantity") or "1", _amt(r["unit_rate"]) if r.get("unit_rate") else "",
                    _amt(r["billed"])]
            for (name, x, al), v in zip(cols, vals):
                if v:
                    (self.c.drawRightString if al == "r" else self.c.drawString)(x, self.y, v)
            self.y -= 14

    def bytes(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def _fixture(name: str) -> dict:
    return json.loads((PACK / "fixtures" / "claims" / f"{name}.input.json").read_text(encoding="utf-8"))


def patient_block(d: Doc, name: str, gender: str):
    d.line(f"Patient Name: {TITLES.get(gender, '')} {name}".replace("  ", " "))
    d.line(f"Gender: {gender}")


def claim_form(fx: dict, claimed: str) -> bytes:
    d = Doc("CLAIM FORM - PART A (Reimbursement)")
    d.line(f"Policy Number: {fx['policy']['policy_no']}")
    patient_block(d, _name(fx["member"]["name_normalised"]), fx["member"]["gender"])
    d.line(f"Date of Birth: {_dmy(fx['member']['dob'])}")
    d.line(f"Hospital: {HOSPITALS[fx['hospital_id']]}")
    d.line(f"Claimed Amount: Rs. {claimed}")
    d.line("Declaration: I declare that the information given is true (synthetic).", size=8)
    return d.bytes()


def discharge_summary(fx: dict, doa: str, dod: str, procedure: str, history: str) -> bytes:
    d = Doc("DISCHARGE SUMMARY")
    d.line(f"Hospital: {HOSPITALS[fx['hospital_id']]}")
    patient_block(d, _name(fx["member"]["name_normalised"]), fx["member"]["gender"])
    d.line(f"DOA: {doa}")
    d.line(f"DOD: {dod}")
    d.line(f"Diagnosis: {fx['diagnosis']['text']}")
    d.line(f"Procedure: {procedure}")
    d.line(f"History: {history}")
    d.line("Course in hospital: Uneventful post-operative recovery (synthetic narrative).")
    d.line("Advice on discharge: Review in OPD after 7 days.")
    return d.bytes()


def final_bill(fx: dict, lines: list[dict], name: str, gender: str, doa: str, dod: str, total: str, title: str = "FINAL BILL - DETAILED BILL") -> bytes:
    d = Doc(title)
    d.line(f"Hospital: {HOSPITALS[fx['hospital_id']]}")
    d.line(f"Bill No: {fx['bill_no']}")
    patient_block(d, name, gender)
    d.line(f"DOA: {doa}")
    d.line(f"DOD: {dod}")
    d.new_page(title + " (itemised)")
    d.table(lines)
    d.y -= 10
    d.line(f"GRAND TOTAL {_amt(total)}", bold=True)
    return d.bytes()


def summary_bill(fx: dict, name: str, gender: str, admission: str, total: str) -> bytes:
    d = Doc("SUMMARY BILL")
    d.line(f"Hospital: {HOSPITALS[fx['hospital_id']]}")
    d.line(f"Bill No: {fx['bill_no']}")
    d.line(f"Patient: {TITLES[gender]} {name}")
    d.line(f"Gender: {gender}")
    d.line(f"Admission: {admission}")
    d.line("Category-wise summary only; no item break-up", size=9)
    for cat, amt in (("Room and nursing", "18500.00"), ("Professional fees", "21500.00"), ("Operation theatre", "9500.00"),
                     ("Pharmacy and consumables", "28120.25"), ("Investigations", "7950.00"), ("Other charges", "280.00")):
        d.line(f"{cat}: {_amt(amt)}", size=9, gap=13)
    d.line(f"Net Amount {_amt(total)}", bold=True)
    return d.bytes()


def simple(title: str, rows: list[str], extra_banner: str | None = None) -> bytes:
    d = Doc(title)
    if extra_banner:
        d.line(extra_banner, bold=True, size=9)
    for r in rows:
        d.line(r)
    return d.bytes()


def claim_documents() -> dict[str, list[tuple[str, str, bytes]]]:
    """{claim_id: [(name, declared_type, pdf_bytes), ...]} in upload order; claim 3 has a second batch."""
    out: dict[str, list[tuple[str, str, bytes]]] = {}
    # ---- claim 1 (trace 1)
    f1 = _fixture("trace-1-straightforward")
    n1, g1 = _name(f1["member"]["name_normalised"]), f1["member"]["gender"]
    ph1 = [l for l in f1["bill_lines"] if l["category"] == "PHARMACY"]
    out["CLM-DEMO-0001"] = [
        ("claim-form", "CLAIM_FORM", claim_form(f1, _amt(f1["bill_stated_total"]))),
        ("discharge-summary", "DISCHARGE_SUMMARY", discharge_summary(f1, _dmy(f1["admission_date"]), _dmy(f1["discharge_date"]),
                                                                     "Laparoscopic appendicectomy", "No significant past history")),
        ("final-bill", "FINAL_BILL_ITEMISED", final_bill(f1, f1["bill_lines"], n1, g1, _dmy(f1["admission_date"]), _dmy(f1["discharge_date"]),
                                                       f1["bill_stated_total"])),
        ("pharmacy-invoice", "PHARMACY_BILL", simple("PHARMACY INVOICE", [f"Invoice No: {ph1[0]['invoice_no']}", f"Patient Name: {TITLES[g1]} {n1}",
                                                                         f"Total: {_amt(ph1[0]['billed'])}"])),
        ("investigation-report", "INVESTIGATION_REPORT", simple("LABORATORY REPORT", [f"Patient Name: {TITLES[g1]} {n1}", "CBC, LFT within reference ranges (synthetic)."])),
        ("payment-receipt", "PAYMENT_RECEIPT", simple("PAYMENT RECEIPT", [f"Received from: {n1}", f"Amount: Rs. {_amt(f1['bill_stated_total'])}"])),
        ("id-proof", "ID_PROOF", simple("IDENTITY PROOF (synthetic specimen)", [f"Name: {n1}", f"Gender: {g1}"])),
        ("bank-details", "BANK_DETAILS", simple("BANK ACCOUNT DETAILS (synthetic)", [f"Account holder: {n1}", "IFSC: SYNT0000001"])),
    ]
    # ---- claim 2 (trace 2)
    f2 = _fixture("trace-2-interacting-adjustments")
    n2, g2 = _name(f2["member"]["name_normalised"]), f2["member"]["gender"]
    out["CLM-DEMO-0002"] = [
        ("claim-form", "CLAIM_FORM", claim_form(f2, _amt(f2["bill_stated_total"]))),
        ("discharge-summary", "DISCHARGE_SUMMARY", discharge_summary(f2, _dmy(f2["admission_date"]), _dmy(f2["discharge_date"]),
                                                                     "Laparoscopic cholecystectomy", "No significant past history")),
        ("final-bill", "FINAL_BILL_ITEMISED", final_bill(f2, f2["bill_lines"], n2, g2, _dmy(f2["admission_date"]), _dmy(f2["discharge_date"]),
                                                       f2["bill_stated_total"])),
        ("pharmacy-invoice-ph-2291", "PHARMACY_BILL", simple("PHARMACY INVOICE", [f"Invoice No: PH-2291", f"Patient Name: {TITLES[g2]} {n2}", "Total: 3,420.00"])),
        ("pharmacy-invoice-ph-2291-copy", "PHARMACY_BILL", simple("PHARMACY INVOICE", [f"Invoice No: PH-2291", f"Patient Name: {TITLES[g2]} {n2}", "Total: 3,420.00"],
                                                                  extra_banner="PHOTOCOPY")),
        ("pharmacy-invoice-ph-2307", "PHARMACY_BILL", simple("PHARMACY INVOICE", [f"Invoice No: PH-2307", f"Patient Name: {TITLES[g2]} {n2}", "Total: 11,865.75"])),
        ("investigation-report", "INVESTIGATION_REPORT", simple("RADIOLOGY REPORT", [f"Patient Name: {TITLES[g2]} {n2}", "CT abdomen: calculi in gall bladder (synthetic)."])),
        ("payment-receipt", "PAYMENT_RECEIPT", simple("PAYMENT RECEIPT", [f"Received from: {n2}", f"Amount: Rs. {_amt(f2['bill_stated_total'])}"])),
        ("id-proof", "ID_PROOF", simple("IDENTITY PROOF (synthetic specimen)", [f"Name: {n2}", f"Gender: {g2}"])),
        ("bank-details", "BANK_DETAILS", simple("BANK ACCOUNT DETAILS (synthetic)", [f"Account holder: {n2}", "IFSC: SYNT0000002"])),
    ]
    # ---- claim 3 (trace 3a, then 3b documents)
    f3a, f3b = _fixture("trace-3a-insufficient-conflicting"), _fixture("trace-3b-after-new-evidence")
    n3, g3 = _name(f3a["member"]["name_normalised"]), f3a["member"]["gender"]
    hist = f3a["ped_signals"][0]["text"]
    out["CLM-DEMO-0003"] = [
        ("claim-form", "CLAIM_FORM", claim_form(f3a, _amt(f3a["bill_stated_total"]))),
        ("discharge-summary", "DISCHARGE_SUMMARY", discharge_summary(f3a, "03/09/2026", "07/09/2026", "Surgical debridement, left foot", hist)),
        ("summary-bill", "FINAL_BILL_SUMMARY", summary_bill(f3a, "Sunil Sharma", "M", "02-09-2026", f3a["bill_stated_total"])),
        ("investigation-report", "INVESTIGATION_REPORT", simple("LABORATORY REPORT", [f"Patient Name: {TITLES[g3]} {n3}", "HbA1c 8.9% (synthetic)."])),
        ("payment-receipt", "PAYMENT_RECEIPT", simple("PAYMENT RECEIPT", [f"Received from: {n3}", f"Amount: Rs. {_amt(f3a['bill_stated_total'])}"])),
        ("id-proof", "ID_PROOF", simple("IDENTITY PROOF (synthetic specimen)", [f"Name: {n3}", f"Gender: {g3}"])),
        ("bank-details", "BANK_DETAILS", simple("BANK ACCOUNT DETAILS (synthetic)", [f"Account holder: {n3}", "IFSC: SYNT0000003"])),
    ]
    out["CLM-DEMO-0003:after-query"] = [
        ("final-bill-corrected", "FINAL_BILL_ITEMISED", final_bill(f3b, f3b["bill_lines"], n3, g3, "02/09/2026", "07/09/2026", f3b["bill_stated_total"],
                                                                 title="FINAL BILL - DETAILED BILL (corrected)")),
        ("admission-record", "ADMISSION_RECORD", simple("ADMISSION RECORD", [f"Patient Name: {TITLES[g3]} {n3}", "Gender: F",
                                                                          "Admitted 02/09/2026 23:40 via emergency"])),
    ]
    return out


def main(out_dir: str):
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    for claim, docs in claim_documents().items():
        for name, _t, data in docs:
            (p / f"{claim.replace(':', '_')}__{name}.pdf").write_bytes(data)
    print(f"wrote synthetic documents to {p}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "synthetic-docs")
