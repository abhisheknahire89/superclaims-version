"""Browser smoke test of the reviewer UI against a running development server.

    PYTHONPATH=src python3 -m aw.server --seed-demo &        # fresh database, see README
    python3 tests/ui_smoke.py http://127.0.0.1:8080 /tmp/aw-shots

It walks the main reviewer path in headless Chromium, saves a screenshot at each step and fails on any browser
console error or failed API call. Claim 3 is decided along the way, so run it against a freshly seeded database.
It is not part of `make test` because it needs Playwright, a browser and a live server.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main(base: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        # HTTP failures are judged by the response handler below (an expected 409 is not a problem), so the
        # browser's own "Failed to load resource" console lines are skipped here.
        page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}")
                if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
        page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.request.method} {r.url}")
                if r.status >= 400 and not (r.status == 409 and r.url.endswith("/decisions")) else None)

        def shot(name: str):
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)

        # sign in as a processor
        page.goto(base + "/#/login")
        page.get_by_role("button", name="PROC-11").click()
        expect(page.get_by_role("heading", name="Work queue")).to_be_visible()
        expect(page.locator("tr.qrow")).to_have_count(3)
        shot("01-queue")

        # claim 2: bill and deductions, evidence for a deduction, findings, decision needs a second approver
        page.get_by_role("link", name="CLM-DEMO-0002").click()
        expect(page.locator(".proposed")).to_contain_text("85,000.00")
        shot("02-workspace-bill")
        page.locator("button.chip.ded").first.click()
        expect(page.locator(".viewer img")).to_be_visible()
        page.wait_for_function("document.querySelector('.viewer .box') !== null")
        expect(page.locator("#evidence dl.kv")).to_contain_text("Authority")
        shot("03-evidence")
        page.get_by_role("button", name="Zoom").click()
        expect(page.locator(".viewer.zoom")).to_be_visible()
        page.locator("#evidence").screenshot(path=str(out / "04-evidence-zoom.png"))
        page.get_by_role("tab", name="Decision").click()
        page.get_by_role("button", name="Record decision").click()
        expect(page.locator(".err[role=alert]")).to_contain_text("deductions above share of billed")
        page.get_by_role("button", name="Send for approval").click()
        expect(page.locator("h3", has_text="Awaiting second approval")).to_be_visible()
        shot("05-sent-for-approval")

        # the supervisor approves
        page.get_by_role("button", name="Sign out").click()
        page.get_by_role("button", name="SUP-02").click()
        expect(page.locator("#who")).to_contain_text("Supervisor")
        page.goto(base + "/#/claim/CLM-DEMO-0002")
        page.get_by_role("tab", name="Decision").click()
        page.get_by_role("button", name="Approve", exact=True).click()
        expect(page.locator(".banner.final")).to_contain_text("85,000.00")
        page.get_by_role("tab", name="Audit").click()
        expect(page.locator("p.ok")).to_contain_text("Hash chain verified")
        shot("06-approved-audit")

        # claim 3: blocked, conflict shown in the facts pane, queries drafted
        page.goto(base + "/#/claim/CLM-DEMO-0003")
        expect(page.locator(".banner.block")).to_be_visible()
        expect(page.locator(".fact.conflict").first).to_be_visible()
        shot("07-claim3-blocked")
        page.get_by_role("tab", name="Findings").click()
        expect(page.locator("article.finding.blocking").first).to_be_visible()
        page.locator("article.finding").get_by_role("button", name="Evidence").first.click()
        shot("08-claim3-findings")
        page.get_by_role("tab", name="Queries").click()
        expect(page.locator("[role=tabpanel] form.drawer h3").first).to_contain_text("To:")
        shot("09-claim3-queries")

        browser.close()
    for p in problems:
        print("PROBLEM:", p)
    print(f"screenshots in {out}; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080", Path(sys.argv[2] if len(sys.argv) > 2 else "ui-shots")))
