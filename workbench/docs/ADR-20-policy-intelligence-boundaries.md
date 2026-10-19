# ADR-20 — Isolated public-policy intelligence and shadow rules

Accepted 13 October 2026. The newer user assignment authorizes bounded public insurer PDF retrieval and a local research import; it overrides the older blanket no-network/no-public-policy-data restriction only for this isolated public research subsystem. No patient data, hosted AI, insurer/TPA live integration or operational rule publication is authorized.

Public acquisition is an isolated content-addressed research directory with a SQLite transport journal, not a claim database or customer configuration. Imports never promote research VERIFIED labels. Product identities require canonical insurer plus exact UIN; revision identity is original PDF hash until a human establishes contractual revision/effective dates. Downloaded content proves bytes, not member entitlement. Original bytes and old revisions are retained.

New migration0007 adds tenant-RLS review records and append-only review events to the existing PostgreSQL platform. Public source intake, candidate interpretation and four-eyes approval reuse existing config.author/config.publish roles, local sessions/CSRF and password confirmation. Published policy-intelligence rules are shadow records only; no config_artifact or published synthetic configuration is changed. Their source evidence is rechecked against immutable original bytes at every validation/approval/preview.

Four layers remain distinct: public wording; issued member contract; dynamic benefits; hospital tariff. Unknown dates, options, current coverage and tariff values remain unknown. Applicability selection uses explicit issued revision and policy-period/wording/endorsement/treatment/tariff dates separately, never the newest URL. Ambiguity blocks affected financial preview. Controlled supported-rule translation calls the existing Decimal engine; unsupported types remain review tasks. No second financial engine is introduced.

Named audit workbook and corrected exports are absent from currently located files. Their inspection is NOT RUN until supplied; existing registry/product CSVs are quarantined with row-level reasons and raw-input hashes. Original research verification/download claims are not accepted as proof.

Preview scope: only explicitly illustrative interface bundles may run. Complete fields are not independent private-evidence verification. Definitive payable always remains null. Current IST snapshot, paise balances net of reservations, explicit claim/utilisation history and supported dependencies are required. The transient legacy ledger offset encodes provided remaining cover, never actual paid claims or a persisted entry. Only unconditional copay/per-claim deductible translations are supported. Supplied start/end dates require exact quotations; candidate dates also require source pages.

0008 prevents direct insertion of already-published candidates. Illustrative derivatives use a separate fixed .policy-illustrative directory, public originals .policy-research. Long native policy PDFs charge OCR raster budget only to pages needing local OCR; existing claim-reader limits remain unchanged.

0009–0010 add immutable ProductHistory and ResearchRemediation records. Reviewed
rename/status evidence binds existing identity, verified document title, exact original
hash/page/quote and distinct author/approver. Name-conflict evidence-only download
remains quarantined until explicit review; invalid metadata is not repairable that way.
Tenant review uses PostgreSQL overlays and an atomic audit transaction, never mutates
the shared acquisition journal. Resolution expires against changed retrieval hashes.
Withdrawal history requires issued-contract continuation review, not automatic denial.
