"""Verify corpus artifacts and labels without consulting extractor code."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import pdfplumber
from PIL import Image

root = Path(__file__).resolve().parent / "out"
manifest = json.loads((root / "manifest.json").read_text())
assert manifest["held_back"] and manifest["synthetic"]
assert len(manifest["claims"]) == 10
assert sorted(Counter(c["layout_id"] for c in manifest["claims"]).values()) == [5, 5]
formats = Counter()
for item in manifest["documents"]:
    file = root / item["path"]
    assert file.is_file()
    formats[item["format"]] += 1
    if item["format"] in {"png", "jpg"}:
        with Image.open(file) as image:
            image.verify()
    else:
        assert hashlib.sha256(file.read_bytes()).hexdigest() == item["sha256"]
        with pdfplumber.open(file) as pdf:
            assert len(pdf.pages) == item["pages"]
            if item["format"] == "scanned_pdf":
                assert not any(page.extract_text() for page in pdf.pages)
            else:
                all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                assert "SYNTHETIC" in all_text
                if item["document_type"] == "FINAL_BILL_ITEMISED":
                    expected = item["expected_fields"]["bill.total"]
                    assert sum(Decimal(line["amount"]) for line in item["expected_lines"]) == Decimal(expected)
                    assert expected in all_text
                    assert len(item["expected_lines"]) == 10
                    for row in item["expected_lines"]:
                        assert Decimal(row["quantity"]) * Decimal(row["unit_rate"]) == Decimal(row["amount"])
                        assert row["description"] in all_text
assert formats == {"native_pdf": 30, "scanned_pdf": 30, "png": 32, "jpg": 32}
report = {"result": "PASS", "claims": 10, "layouts": 2, "formats": dict(formats), "checks": ["synthetic labels", "artifact hashes", "page counts", "image integrity", "scan has no native text", "exact decimal row arithmetic", "bill total reconciliation"]}
(root / "generation-verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"result": "PASS", "claims": 10, "layouts": 2, "files_verified": 124}))
