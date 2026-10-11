"""Cross-reference check: every ID cited anywhere in the pack must be defined in its home file.

Usage: python3 verification/check_refs.py
Home files: TC-/EC-/M-XXX-nn metrics -> 10; OQ- -> 12; BL- -> 11; CAP- -> 02; ADR- -> 04; S-nn -> 03; FI- -> 06;
            M-nn materials -> 09; evidence IDs -> source-ledger.csv.
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
docs = {p.name: p.read_text() for p in sorted(ROOT.glob("[01][0-9]-*.md"))}
docs["00-README.md"] = (ROOT / "00-README.md").read_text()
alltext = "\n".join(docs.values())
ledger_ids = {r["evidence_id"] for r in csv.DictReader(open(ROOT / "source-ledger.csv", encoding="utf-8"))}


def expand(text, pattern):
    """Find IDs, expanding ranges like TC-CAL-01..05 or FI-01..FI-11 or E-REG-01..08."""
    found = set()
    for m in re.finditer(pattern, text):
        found.add(m.group(0))
    rng = re.compile(r"\b([A-Z]+(?:-[A-Z]+)*-)(\d{2})\.\.(?:[A-Z]+(?:-[A-Z]+)*-)?(\d{2})\b")
    for m in rng.finditer(text):
        prefix, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        for i in range(a, b + 1):
            cand = f"{prefix}{i:02d}"
            if re.fullmatch(pattern.replace("\\b", ""), cand):
                found.add(cand)
    return found


def defined_in(fname, pattern):
    text = docs[fname]
    # definitions = IDs appearing at the start of a table row or a heading
    defs = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") or s.startswith("#"):
            first = s.strip("|# ").split("|")[0]
            defs |= set(re.findall(pattern, first))
            defs |= expand(first, pattern)
    return defs


checks = [
    ("TC", r"\bTC-[A-Z]+-\d{2}\b", "10-validation-plan.md"),
    ("EC", r"\bEC-\d{2}\b", "10-validation-plan.md"),
    ("Metric", r"\bM-(?:EXT|BIL|RUL|FIN|EVD|ABS|ANO|CLN|OPS)-\d{2}\b", "10-validation-plan.md"),
    ("OQ", r"\bOQ-\d{2}\b", "12-open-questions.md"),
    ("BL", r"\bBL-\d{2}\b", "11-build-backlog.md"),
    ("CAP", r"\bCAP-\d{2}\b", "02-PRD.md"),
    ("ADR", r"\bADR-\d{2}\b", "04-architecture.md"),
    ("Screen", r"\bS-\d{2}\b", "03-workflows-and-UX.md"),
    ("Material", r"\bM-\d{2}\b", "09-materials-and-costs.md"),
]
problems = {}
for label, pat, home in checks:
    cited = expand(alltext, pat)
    defined = defined_in(home, pat)
    if label == "FI":
        pass
    missing = sorted(cited - defined)
    if missing:
        problems[label] = missing

# FI invariants are defined as list items in 06
fi_cited = expand(alltext, r"\bFI-\d{2}\b")
fi_defined = set(re.findall(r"- (FI-\d{2}) ", docs["06-rule-catalog.md"]))
if fi_cited - fi_defined:
    problems["FI"] = sorted(fi_cited - fi_defined)

# CAP headings are '### CAP-nn'
cap_def = set(re.findall(r"### (CAP-\d{2})", docs["02-PRD.md"]))
cap_cited = expand(alltext, r"\bCAP-\d{2}\b")
problems.pop("CAP", None)
if cap_cited - cap_def:
    problems["CAP"] = sorted(cap_cited - cap_def)

# evidence IDs
ev_cited = set(re.findall(r"\bE-(?:LI|REG|PRC|CMP|SK|FX)-\d{2}\b|\bE0\d{2}\b", alltext))
ev_cited |= {x for x in expand(alltext, r"\bE-(?:LI|REG|PRC|CMP|SK|FX)-\d{2}\b")}
ev_ranges = re.findall(r"\bE0(\d{2})–E0(\d{2})\b", alltext)
for a, b in ev_ranges:
    for i in range(int(a), int(b) + 1):
        ev_cited.add(f"E0{i:02d}")
missing_ev = sorted(ev_cited - ledger_ids)
if missing_ev:
    problems["Evidence (not in ledger)"] = missing_ev

# fixture IDs used in docs and API examples (adjustments, evaluations, reviewer actions, decisions) must exist in the fixtures
import json as _json
fx_text = "\n".join(f.read_text(encoding="utf-8") for f in (ROOT / "fixtures").rglob("*.json"))
fx_text += (ROOT / "verification/db_load_sql.py").read_text(encoding="utf-8")
api_text = (ROOT / "api/openapi.yaml").read_text(encoding="utf-8")
id_cited = set(re.findall(r"\b(?:ADJ|EVAL|RA|DEC|FND)-\d{4}(?:-v\d)?\b", alltext + api_text))
id_missing = sorted(i for i in id_cited if i not in fx_text)
if id_missing:
    problems["Fixture IDs (not in fixtures)"] = id_missing

print("OK — all cross-references resolve" if not problems else "\n".join(f"{k}: {v}" for k, v in problems.items()))
sys.exit(1 if problems else 0)
