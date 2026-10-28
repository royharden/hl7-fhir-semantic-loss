# Construction claim audit

| Claim | Source boundary | Current disposition |
| --- | --- | --- |
| Authored keyless demonstration | Actual original developer generator, hash, explicit fixture namespace | Exercised by target developer tests |
| Escaped report | `report/render.py` serializes then HTML-escapes supplied data | Malicious-tag regression passed; no browser/CSP execution claim |
| Exact supplied-record provenance | CLI decodes and hashes the same bounded byte snapshot | Target export/hash and malformed-input regressions passed |
| Failure export | Supplied failures retained with source hash, including empty-list receipt | Target regressions passed |
| Parser/B0/DSL wiring | Actual producer interfaces at tested source6d338e0 | Target joined developer paths passed; full semantics not established |
| Rights, Java passes, round-trip, independent truth, scored quality | Explicit refusal paths and pending roles | Not admitted / not run / not measured |
| Budget and public readiness | No transport or credential lookup in CLI | No spend, no public release authorization |
| Mock ledger and simulated rulings | Actual Ledger/MockProvider/RulingStore interfaces | Isolated developer accounting/journal paths passed; no real billing or custody |

Imported reports can contain unsupported claims. They remain visible as supplied,
unverified content and cannot establish admission or acceptance. No numeric claim audit
against sealed evaluation results exists yet; that belongs to the later authorized
campaign and Q review. No report-generation path creates a pass receipt or role signature.

Runtime evidence: tests/cli, 37 passed/0 failed/0 skipped in4.36s, exact target environment
and command in ROUND2-TESTING.md. This is builder regression evidence, never independent gold.
