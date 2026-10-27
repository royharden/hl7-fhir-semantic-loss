# Construction claim audit

| Claim | Source boundary | Current disposition |
| --- | --- | --- |
| Authored keyless demonstration | `cli.py` literal original developer message, hash, explicit fixture namespace | Source built; execution deferred |
| Escaped report | `report/render.py` serializes then HTML-escapes all supplied data, CSP forbids resources | Source inspected; malicious-input runtime checks deferred |
| Exact supplied-record provenance | CLI decodes and hashes the same bounded byte snapshot | Source inspected; file/encoding checks deferred |
| Failure export | Every supplied failure object retained with source hash; missing list refuses | Source built; execution deferred |
| Parser/B0/DSL wiring | Actual producer interfaces at accepted 3f6df71 / DL1 d77daaa | Source reconciled; joined execution deferred |
| Rights, Java passes, round-trip, independent truth, scored quality | Explicit refusal paths and pending roles | Not admitted / not run / not measured |
| Budget and public readiness | No transport or credential lookup in CLI | No spend, no public release authorization |
| Mock ledger and simulated rulings | Actual Ledger/MockProvider/RulingStore interfaces | Source wired; no calls or durable writes exercised |

Imported reports can contain unsupported claims. They remain visible as supplied,
unverified content and cannot establish admission or acceptance. No numeric claim audit
against sealed evaluation results exists yet; that belongs to the later authorized
campaign and Q review. No report-generation path creates a pass receipt or role signature.
