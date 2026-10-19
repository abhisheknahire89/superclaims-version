Independent targeted review by /root/research_audit, 13 October 2026.

Reviewed acquisition, provenance, date handling, approval, shadow adapter, API roles,
published immutability, tenant isolation. Readonly main repository; isolated tests.
Initially reproduced: empty evidence/stale coverage/inconsistent reservations/unknown
rule dependency still computed; unquoted source/rule expiry dates accepted; changed URL
missed across different manifest imports. Also truthy context flag/nonblank interpretation
and inconsistent terminal state. Lead repaired all of these.

Independent retest: 3 adversarial database tests passed in2.789s; corrected-import changed
URL retained both originals and flagged change. Standard subsystem16tests passed in5.064s.
No tested runtime config modification, automatic disposition, API four-eyes bypass,
cross-tenant candidate/event access or approved-body update. Definitive payable null.
This was targeted review, not an exhaustive security audit. Rename/alias resolution and
interactive quarantine remediation remain scope limitations. Test scripts preserved in
/tmp/aw-policy-independent-review.py and /tmp/aw-policy-independent-retest-plus.py.

Follow-up product-history/remediation review found shared SQLite cross-tenant writes,
non-atomic rollback, unbound name words and supplied fake evidence hashes. All repaired:
PG tenant overlays, atomic audit, existing identity+verified title binding, canonical
original hashes and retrieval-bound resolution. Independent repaired retest5tests2.221s
passed, including realAPI role/reauth guards, pending identity extraction gate, other
Tenant rejection isolation, rollback, source rejection protection and false names/hash.
Script /tmp/aw-policy-history-retest-api.py; no real public source/rule auto-approved.
