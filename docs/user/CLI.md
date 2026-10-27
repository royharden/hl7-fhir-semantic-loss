# Local source journey

Construction source only. These commands have **not been run**. Dependency installation,
wheel packaging, imports, CLI invocation and end-to-end behavior await activation after
Dirty Mode. The declared entry point is `h7loss = h7loss.cli:app`.

After separately authorized setup, the proposed keyless journey is:

```text
h7loss demo --mock
h7loss gen --output dev-message.hl7
h7loss parse dev-message.hl7
h7loss map dev-message.hl7 --dictionary developer-dictionary.json
h7loss propose dev-message.hl7 --dictionary developer-dictionary.json --proposal authored-proposal.json
h7loss report supplied-record.json --output report.html
h7loss report supplied-record.json --output report.json --format json
h7loss failures supplied-record.json --output failures.jsonl
```

`gen` emits one original developer message, not the planned 8-site corpus. `demo --mock`
prints an explicitly illustrative source record and `not_run` receipts; it does not run
the mapper, Java validator, oracle or round trip. No validator pass, critical-error rate,
model-quality comparison or demo timing is measured. Mapping requires a separately
authored dictionary matching the core mapper's contract; proposal execution consumes a
local authored DSL document and never calls a model. The parser, B0 and proposal imports
are lazy and must be reconciled with their owners before runtime claims.

Report input is an explicit JSON object (at most 4 MiB). It is rendered as an escaped,
inert supplied record. A record's own assertions stay unverified, including any alleged
validator receipt or numeric claim. The report wraps the record with a SHA256 of the
exact input bytes; JSON export preserves the same provenance. No links, embedded HTML,
scripts or external resources are activated. `failures` requires an explicit `failures`
list of objects, exports every supplied item and reports its count, including zero.
It does not invent missing failures or silently select a favorable subset.

All file-writing commands use exclusive creation: choose a new output path. Parent
directories must already exist. Raw messages are capped at 1 MiB. Output hashes identify
bytes written, not independent correctness. CLI-generated envelopes have no fabricated
ledger or evaluation identities; mapper dispositions retain their supplied evidence.

`admit`, `validate`, `roundtrip`, `rule`, `score`, `eval`, and `live` refuse with exit 2
and an explicit reason. They cannot sign admission, infer Java success, appoint an
independent author, record a ruling, open held-out truth or authorize dispatch. Planned
evaluation belongs in a separate distribution; product source never imports it.
Local operational failures emit a JSON error with exit 1. Successful source-tool paths
intend exit 0, which is not validation or product acceptance. Typer usage errors may use
its own standard error output and exit 2.
