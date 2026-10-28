# Local source journey

These commands have **not been run** by DL4. Round 2 permits keyless local developer
checks only on the INT-owned READY interpreter. At this checkpoint ENVIRONMENT-ROUND2.md
is NOT READY: RAM blocked setup, and global Typer0.7 is unsupported. Do not use that
fallback to drive product changes. See [Round 2 testing](ROUND2-TESTING.md). Wheel and
independent/runtime acceptance remain separate. Entry point: `h7loss = h7loss.cli:app`.

After separately authorized setup, the proposed keyless journey is:

```text
h7loss demo --mock
h7loss gen --output dev-message.hl7
h7loss dev-dictionary developer-dictionary.json
h7loss dev-case developer-case.json
h7loss parse dev-message.hl7
h7loss map dev-message.hl7 --dictionary developer-dictionary.json
h7loss propose dev-message.hl7 --dictionary developer-dictionary.json --proposal authored-proposal.json
h7loss report supplied-record.json --output report.html
h7loss report supplied-record.json --output report.json --format json
h7loss failures supplied-record.json --output failures.jsonl
h7loss mock-map dev-message.hl7 --dictionary developer-dictionary.json --fixtures authored-responses.json --ledger mock-accounting.sqlite
h7loss mock-propose developer-dictionary.json --fixtures authored-site-responses.json --ledger mock-accounting.sqlite
h7loss ledger-report mock-accounting.sqlite
h7loss rule authored-ruling.json --source dev-message.hl7 --dictionary developer-dictionary.json --mapping authored-proposal.json --journal simulated-rulings.jsonl --simulate
h7loss rule-replay simulated-rulings.jsonl
```

`gen` emits one original DL1 developer message (default dev-01, index 1); `--site` and
`--index` select bounded developer inputs, never held-out data. `dev-dictionary` exports
the matching site metadata; `dev-case` exports metadata, dictionary and ASCII raw_message
in one JSON artifact. `demo --mock` wires the original developer generator, parser and
B0 mapper in process. Literal producer output and `not_run` Java/roundtrip receipts are
retained. No oracle, Java or round trip is invoked. No validator pass, critical-error
rate, model-quality comparison or demo timing is measured. Lazy public interfaces are
source-reconciled with accepted baseline 3f6df71 (DL1 d77daaa plus INT's contract
correction); runtime behavior is unverified.

Outcomes remain literal. B0 `mapped`, DSL `ok` and mock `produced` intend exit 0. B0
`partial`, producer errors/refusals, invalid proposals and parse errors/unsupported
framing intend exit 2 while retaining actual result/dispositions. Exit 0 says only that
the source tool completed, never that source semantics were preserved.

Mock fixture files require explicit `config_id`, `model`, and `responses` (one or two
authored provider objects). Optional integer `max_liability_micro_usd` and
`repair_liability_micro_usd` default to zero. B2 also requires `case_id`. Each response
has `outcome` (`success`, `malformed`, `timeout`, `unknown_usage`), string `text`, and
optional integer-or-null `usage_micro_usd`. These are simulated amounts, not measured
provider costs. All attempts and accounting state are retained, including unknown
liability and exhausted repair. Use the same persistent app ledger; do not reset its
budget or change config IDs to imply campaign retry permission. `mock-propose` accepts
at most five `onboarding` strings. The accepted developer dictionary now includes
`site_id`, derived scalar tables, `bindings`, and a nonempty STRING `report_code`.
The same exact released dictionary object is hashed and passed to B0 and DSL; the CLI
never rewrites or augments it. A legacy dictionary missing these fields is not silently
upgraded. Derived tables remain views inside the same release, not separate truth.

Rule requests contain exactly `key`, `decision`, `actor`, `basis`, `expected_revision`,
`original_obligation`, `study_freeze_sha256`, and optional `supplement`, using the
`RulingStore.append` contract. Current source/dictionary/mapping hashes come from the
exact three file byte snapshots, including whitespace, and must match the request key.
This differs from DSL's canonical dictionary hash. Optional `--supplement` supplies
explicit fictional supplement bytes. Only `--simulate` can append. Supplied actor,
freeze and evidence hashes confer no independent identity, custody authority or study
admission. Original obligation/revision/chain stay intact. No CLI command applies a
ruling to primary data/truth. Journals and locks cannot alias input files. Per PORTS005,
the CLI initializes one record in a new simulation journal/lock path only; existing
journals are preserved and can be inspected with rule-replay. General multi-record
append remains a RulingStore source API, not an admitted CLI action. Path guards do not
claim atomic race-proof filesystem containment.

JSON inputs are bounded to 4 MiB and 64 container levels. Report input is an explicit
JSON object. It is rendered as an escaped,
inert supplied record. A record's own assertions stay unverified, including any alleged
validator receipt or numeric claim. The report wraps the record with a SHA256 of the
exact input bytes; JSON export preserves the same provenance. No links, embedded HTML,
scripts or external resources are activated. `failures` requires an explicit `failures`
list of objects, exports every supplied item and reports its count, including zero.
It does not invent missing failures or silently select a favorable subset.

Artifact exports use exclusive creation: choose a new output path. Parent directories
must already exist. Ledger/journal commands persist or append explicit paths and can
create SQLite or lock sidecars. Raw messages are capped at 1 MiB. Output hashes identify
bytes written, not independent correctness. CLI-generated envelopes have no fabricated
ledger or evaluation identities; mapper dispositions retain their supplied evidence.

`admit`, `validate`, `roundtrip`, `score`, `eval`, and `live` refuse with exit 2
and an explicit reason. They cannot sign admission, infer Java success, appoint an
independent author, open held-out truth or authorize dispatch. Planned
evaluation belongs in a separate distribution; product source never imports it or
starts a subprocess to bypass that boundary. Supplied validation, roundtrip, ledger,
attempt and disposition sections are rendered as unverified views, never admitted
execution evidence. The complete input remains present in the report.
Local operational failures emit a JSON error with exit 1. Successful source-tool paths
are not validation or product acceptance. Typer usage errors may use
its own standard error output and exit 2.
