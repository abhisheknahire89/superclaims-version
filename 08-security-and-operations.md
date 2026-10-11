# 08 — Security, privacy and operations

Status: **PROPOSED** controls. Each regulatory statement cites evidence and is labelled *documented obligation*, *customer requirement* or *our control*. Interpretations marked ⚖ need qualified legal review before they are relied on. Competitor evidence on security is limited to an ISO/IEC 27001:2022 certificate with a software-development-and-support scope, plus a statement that security specifics are shared per deployment (E004, E005). We do not know the competitor's product controls.

## 1. Data, roles and obligations

| Item | Position | Basis |
|---|---|---|
| Data handled | Health information, identity data (name, date of birth, gender, IDs), financial data (bank details, amounts), hospital commercial data (tariffs) | Claim documents |
| Our legal role | **Data processor** for the insurer or TPA (the data fiduciary under the DPDP Act). We process only on documented instructions | ⚖ Our proposed position. The DPDP Act puts obligations on fiduciaries, who must bind processors by contract (E-REG-10, secondary) |
| DPDP timeline | Rules notified 13 Nov 2025. Most obligations (notice, security safeguards, breach intimation, retention, rights) apply from 13 May 2027 | Documented obligation (E-REG-10, secondary source; verify against the Gazette, OQ-45) |
| IRDAI cyber guidelines 2026 | Apply to insurers and intermediaries, *including TPAs*, from the current financial year. Include MeitY-empanelled cloud with STQC audit, control of sub-outsourcing, segregation of group companies' infrastructure, 6-monthly external penetration tests, DPDP compliance | Documented obligation on our customers (E-REG-05). They will pass it to us contractually (customer requirement). Full Annexure B not yet reviewed (OQ-46) |
| TPA data restriction | A TPA "shall not share the data and personal information received by it … except as provided" | Documented obligation on TPAs (E-REG-04 Reg 19(7)). ⚖ Whether a SaaS processor operating within the TPA's control is "sharing" needs review (OQ-24) |
| TPA outsourcing restriction | TPA must not outsource servicing of policies | Documented obligation on TPAs (E-REG-04). Our control: AW is a tool operated by the customer's staff. We do not adjudicate on their behalf. Any managed-review service is a separate legal question (OQ-24) |
| Express consent for sharing medical records | Insurers must obtain it "in every instance" | Documented obligation on insurers (E-REG-01 Ch.III). Our control: consent status is a claim attribute supplied by the customer; no secondary use |

## 2. Access control

- **Identity.** Federated to the customer's IdP (OIDC) with MFA enforced by the IdP. No local passwords. Session idle timeout 15 min. Re-authentication (step-up) for decisions above the approval limit, configuration publishing and audit export.
- **Authorisation.** Role-based (03 §4) plus attributes (tenant, assigned claims, approval limits). Server-side checks on every call. RLS as defence in depth (validated: another tenant sees 0 rows).
- **Least privilege for us.** No standing production access for engineers. Break-glass access is time-boxed (≤ 4 h), ticket-linked, approved by the customer's admin, fully audited, and automatically revoked. Support works from de-identified reproductions by default.
- **Service identities.** Each worker has its own IAM role, scoped to its bucket prefixes and VPC endpoints. API clients use per-integration OAuth credentials; mTLS for TMS links; quarterly credential rotation.

## 3. Customer separation and residency

- **Separation.** One AWS account per tenant: separate VPC, database, buckets, KMS customer-managed key, IdP realm, model-gateway quota and logs. No shared caches. No cross-tenant analytics without explicit, contracted aggregation of de-identified statistics. This matches the 2026 IRDAI emphasis on segregating group companies and vendor personnel with cross-entity access (E-REG-05).
- **Residency.** Primary in ap-south-1 (Mumbai), disaster recovery in ap-south-2 (Hyderabad). LLM inference via the Bedrock India geographic profile, which routes only between those two regions according to AWS (E-PRC-05, COMPANY-REPORTED). OCR via in-region endpoints (availability to confirm, OQ-41). Confirm MeitY empanelment and STQC status of the chosen cloud services (OQ-40).

## 4. Encryption and keys

TLS 1.2+ everywhere, with TLS 1.3 preferred. KMS customer-managed keys per tenant for RDS, S3 and backups. Column-level envelope encryption for member names, IDs and bank details, so DB snapshots alone do not expose PHI to operators. Key rotation is annual. Crypto-shredding of the tenant key is part of exit (§5).

## 5. Retention, deletion and exit

- Defaults are in 05 §1.5. The actual retention periods for claim records are a customer and legal decision (OQ-27).
- Deletion at the end of retention is crypto-shredding for whole tenants, or object deletion plus row purge jobs for claim-level retention.
- On contract termination: export (originals, structured data, audit chain), then destruction with a certificate. The cyber guidelines require cloud providers to "completely eliminate any trace of data" at termination (E-REG-05). We pass the same commitment through.

## 6. Audit and monitoring

- **Domain audit.** Hash-chained `audit_event`, append-only by trigger (validated). Daily anchoring of chain heads to Object Lock storage. Monthly automated chain verification report per tenant.
- **Access audit.** Every read of a claim workspace is logged (who, when, which claim), because health data access must be reviewable. Unusual access patterns (bulk views, out-of-hours) raise alerts to the customer's admin.
- **Security monitoring.** CloudTrail, GuardDuty-equivalent threat detection, WAF logs and VPC flow logs, all centralised per tenant. Alerts go to the on-call engineer and the customer contact as contracted.

## 7. Incident response, backup and recovery

- **Incident severity matrix and runbooks** (BL-34). Customer notification without undue delay, and within the contractual window (proposed ≤ 6 h for confirmed incidents involving their data), so the customer can meet its own obligations.
  - Customer obligations to plan for: CERT-In incident reporting (commonly cited as 6 hours, verify, OQ-43); DPDP breach intimation to the Board "without delay" plus a detailed report within 72 hours (E-REG-10, secondary); IRDAI reporting under the cyber guidelines (OQ-46).
- **Backups.** RDS PITR (RPO ≤ 15 min) with cross-region copies; S3 versioning and replication; Object Lock on originals. Immutable backup copies, as the 2026 guidelines expect (E-REG-05).
- **Restore drills.** Quarterly. Success criteria: the DB is restored, the audit chains verify, and a sample of evaluation output hashes recomputes identically.
- **Business continuity.** If AW is unavailable, customers continue in their TMS (the system of record). AW never holds a claim hostage. The cashless discharge workflow (P1) must have a documented manual fallback that keeps the 3-hour clock.

## 8. Secure development and testing

- Threat model reviewed per release (table below). SAST, dependency and container scanning in CI. Secrets only in Secrets Manager. Infrastructure as code with policy checks (no public buckets, encryption required, no wide security groups).
- External black-box penetration test of internet-facing assets every 6 months, plus grey/white-box before go-live (E-REG-05 lists 6-monthly external testing for regulated entities).
- AI-specific tests: prompt-injection fixtures (TC-SEC-03), PHI-in-logs CI test (TC-SEC-04), and a cross-tenant isolation test (TC-SEC-01).

| Threat | Example | Control | Test |
|---|---|---|---|
| Spoofing | Stolen reviewer session | IdP MFA, short sessions, step-up for consequential actions | TC-SEC-02 |
| Tampering | Edit a deduction after approval | Append-only tables, decision pinned to evaluation and output hash, hash chain | TC-AUD-01 |
| Repudiation | "I didn't approve that" | Signed-in actor on every action; audit export | TC-AUD-01 |
| Information disclosure | PHI in logs; cross-tenant leak; LLM provider retention | Log filters; per-tenant accounts and RLS; zero-retention configuration | TC-SEC-01, TC-SEC-04 |
| Denial of service | Upload floods | WAF rate limits; size limits; queue isolation per tenant | Load test BL-31 |
| Elevation of privilege | Processor publishes config | RBAC; four-eyes checks in the DB | TC-CFG-01 |
| Malicious documents | Malware PDF; prompt injection | Sandboxed parsing; malware scan; schema-only model outputs | TC-SEC-03, TC-SEC-05 |
| Insider misuse | Bulk browsing of claims | Access logging and anomaly alerts; masking in lists | TC-SEC-06 |

## 9. Operations and support

- **Support tiers.** L1 (customer super-users) → L2 (our support, de-identified by default) → L3 (engineering, break-glass only).
- **Pilot SLAs (proposed).** Severity-1 incident response 30 min in business hours; severity-2 4 h. Availability 99.5% in business hours.
- **Change management.** Release notes per tenant. Configuration changes are customer-approved (four-eyes). Model and prompt changes gated by the golden set (10 §5) with canary rollout. A visible "what changed" log for auditors.
- **Customer configuration support.** Onboarding one product (wording, tariff and NME list) is estimated at 6–9 person-days with a claims SME, plus 5–8 days of golden-claim annotation: about 2–3.5 weeks elapsed (09 §4). Configuration is replayed on golden claims before go-live.

## 10. Certification and assurance roadmap (no claims are made today)

| Item | When | Note |
|---|---|---|
| ISMS aligned to ISO/IEC 27001:2022 | Build from Phase 1; certify after 6+ months of operating evidence | The competitor holds this certification (E004). Buyers will ask |
| Annual cyber audit support for customers (CERT-In-empanelled auditor) | Before production | Our reading of the 2026 guidelines' summary annexure is that intermediaries submit an annual, audited compliance report to the insurers they serve (E-REG-05 Annexure A; UNVERIFIED paraphrase, confirm in the full text, OQ-46). Plan for it either way: TPA customers will pass the requirement on to their vendors |
| DPDP readiness (processor obligations via contract) | Before 13 May 2027 | E-REG-10 |
| SOC 2 Type II | Optional, if needed for multinational insurers | — |

## 11. Items for qualified review ⚖

OQ-24 (TPA outsourcing and data-sharing provisions vs SaaS), OQ-27 (record retention period), OQ-40 (MeitY empanelment of the chosen services), OQ-43 (CERT-In log and incident rules), OQ-45 (DPDP Rules primary text), OQ-46 (full IRDAI 2026 cyber guidelines Annexure B).
