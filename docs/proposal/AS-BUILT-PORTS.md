# Provider, ledger and ruling ports

Source construction with Round2 developer compatibility checks: the allowed
Python3.11.3 fallback passed100 proposal/provider/accounting/journal tests. See
ROUND2-CHECKS.md for exact command/counts and limits. Python3.12 installed-artifact
execution and actual live/FHIR/semantic acceptance remain unverified. Mock usage/latency/output is authored evidence; it is not measured model
quality, clinical evidence, billing, role authentication or admission. The CLI/runner
must preserve this distinction. Live providers are permanently disabled in this source.

## Shared lifetime accounting

Import `Ledger, LedgerError` from `h7loss.ledger`. Construct exactly one app-lifetime
database with `Ledger(path, cap_micro_usd=40_000_000)`, inject that ledger into both B2
and site proposal calls, and close it explicitly with `close()`. Neither arm discovers
or constructs a database. A second database is not new spend permission; external
runner/operator custody must enforce the one-database rule. An existing database's cap
must equal the constructor cap; no implicit change/reset is allowed. Amounts are integer
microUSD, never floats or Decimal inputs; the app ceiling is USD40 total.

Methods and return shapes:

- `reserve(attempt_id, max_liability, provenance)` requires a nonempty identifier up
  to 256 characters, integer liability in `[0,40_000_000]`, and nonempty finite JSON
  object provenance. Returns the SQL attempt row: `attempt_id`, `reserved`, `actual`
  (integer or null), `dispatched` (0/1), `usage_state`, `provenance` (canonical JSON
  string), and `created_at`. Matching existing identity/liability/provenance is
  idempotent. Conflicting identity or insufficient/frozen capacity raises LedgerError.
- `mark_dispatch(attempt_id)` requires a fresh, reserved, undispatched row and
  unfrozen ledger, then atomically records dispatch. Replaying an already dispatched
  ID refuses; it never authorizes another provider attempt.
- `settle(attempt_id, usage, receipt)` requires a dispatched row and nonempty finite
  JSON receipt. `usage=None` means unknown and leaves worst-case liability held.
  Known usage is a nonnegative integer within SQLite's signed-integer range. Known
  usage above the reservation is recorded, marks `liability_breach`, and permanently
  freezes dispatch. Matching known settlements are idempotent; changing a settled
  amount refuses. A later evidenced known settlement can resolve an unknown amount.
  It returns the updated attempt row. Retried matching settlements retain the original
  receipt rather than appending new evidence. Unknown settlement calls append events.
- `report()` returns `currency: "microUSD"`, `cap`, `spent`, `held`, `remaining`,
  `frozen`, SQL `attempts`, ordered `events`, and `snapshot_sha256`. Event `detail`
  and attempt `provenance` are canonical JSON strings. Unknown actual is never zero.
  Python integer aggregation preserves multiple extreme breach receipts without
  SQLite SUM overflow. `close()` closes the connection.

Reserve/dispatch/settle/report use SQLite `BEGIN IMMEDIATE`; DB and OS exceptions
remain operational errors. A single Ledger connection uses SQLite's default thread
restriction; use separate explicitly authorized connections to the same database for
separate threads/processes, not one connection across threads. Concurrency/crash,
cap/idempotency/unknown reconciliation and filesystem durability remain unverified.

## Mock and default-disabled future providers

`MockProvider(responses)` accepts an explicit sequence of authored mappings. Each
`complete(messages, schema, model, budget)` consumes exactly one fixture; no retry,
fallback success, SDK, network, environment or credential discovery exists. Budget
requires positive integer `max_output_chars`. Fixtures contain `outcome` in
`success|malformed|timeout|unknown_usage`, optional `text` string (default empty),
and `usage_micro_usd` nonnegative integer or null (default zero). Timeout/unknown
force unknown usage. Exhaustion or malformed fixtures raise `ProviderError`.

Responses contain `outcome`, `text`, `usage_micro_usd`, `authored_fixture: true`,
`fixture_index`, `raw_output_sha256`, `raw_output_chars`, `output_omitted`,
`latency_ms: null`, and `hidden_retries: 0`. Over-character-cap output returns
`outcome: "cap_exceeded"`, empty `text`, `output_omitted: true` and an error; its
digest and character count refer to the original fixture output, not the empty
replacement. Full capped text stays with the caller's authored fixture. Hashes use
UTF-8 bytes; character caps count Python string characters, not tokens or bytes.

`AnthropicProvider.complete(...)` and `OpenAICompatibleProvider.complete(...)`
raise `ProviderError("LIVE_DISPATCH_REFUSED: ...")` with their default no-argument
constructors. ROUND2-009B adds explicit guarded future config/transport/Ledger
injection; see FUTURE-PROVIDER.md. That vendor-neutral extension is NOT_VERIFIED
for any live API, and its new fake-wire tests require a separately granted runtime
slot. Earlier100-pass receipts cover the prior d5/f453 source, not the later extension.
B2 and site APIs still require
`type(provider) is MockProvider`, so subclasses or arbitrary provider objects refuse.

## B2 and site proposal consumers

`h7loss.arms.b2.map_message(raw, dictionary, *, provider, ledger, case_id, model,
config_id, max_liability_micro_usd=0, repair_liability_micro_usd=0,
onboarding=None, max_output_chars=32768)` requires bytes, a JSON dictionary object,
explicit nonempty string identities, at most five onboarding strings in a list,
raw length at most 1 MiB, and output character cap 1..1 MiB. Inject the shared Ledger.
It makes at most one initial attempt and one JSON-syntax-only repair. Shape errors
do not permit semantic repair. No Java, roundtrip, truth or oracle feedback enters.
Produced output requires exactly `bundle` object with resourceType Bundle and
`dispositions` list; it is not FHIR/semantic validation.

ArmResult contains case/arm/config/raw identities, `outcome` in
`refused|error|produced`, nullable `bundle`, `dispositions`, nullable `error`,
`attempts`, `evidence_class: "authored_mock"`, `runtime_verified: false`, and a
bundle hash only after successful serialization. Serialization refusals clear bundle
and dispositions but preserve recorded attempts.

`h7loss.proposal.propose_site(dictionary, onboarding, *, provider, ledger, config_id,
model, max_liability_micro_usd=0, site_id=None)` similarly injects the shared Ledger.
`site_id` may be supplied explicitly if the producer dictionary lacks it; no identifier
is inferred by parsing dictionary_id. If both explicit and dictionary site IDs exist,
they must match. Site ID appears separately in the prompt; canonical dictionary hash
is computed over the unchanged supplied dictionary. Payload is limited to 1 MiB and
output to 32,768 characters. The provided closed DSL schema and public schema-error
codes permit at most one repair. Return shape is `outcome`, nullable `proposal`,
`attempts`, `evidence_class`, `runtime_verified`, and nullable `error`.

Attempt IDs preserve first-wave slot identity: B2 arm/case/config/raw/attempt number;
site arm/site/dictionary hash/config/attempt number. A versioned request fingerprint
in provenance additionally binds model, dictionary/input, initial prompt (including
onboarding/schema), limits and liabilities. It is deterministic for identical inputs.
Drift under the same slot ID conflicts in Ledger.reserve rather than obtaining a new
call. Sites retain dictionary_id in provenance when supplied. Adding the fingerprint
does not migrate or reset existing rows: older provenance mismatches conservatively
refuse. Changing config/raw/site/dictionary identity can create a different slot; it
does not authorize a new campaign or extra repairs. The future runner must freeze the
full protocol and enforce study-wide attempt caps.

Every attempted reservation is in `attempts`, even when capacity/replay refuses.
Records contain attempt ID, provenance, liability, `dispatch_state` for this invocation,
reservation state/previous dispatch when available, response/outcome/error and usage
state when available. `dispatch_state: "not_dispatched"` does not deny an earlier
dispatch of the same ID; inspect `previously_dispatched` and ledger provenance.
Provider exceptions are recorded with unknown usage; their reservations remain held.
Outer input/serialization refusal does not erase earlier attempt records.

## Ruling journal

Import `RulingStore, RulingError, RulingConflict` from `h7loss.rulings`.
`RulingStore(journal, index=None)` requires explicit paths. Journal canonical JSONL is
authoritative; SQLite is an optional disposable projection. Index may not alias the
journal or its sibling `.lock` file, including inode aliases checked during rebuild.
Operations create the journal parent and persistent lock file when needed.

`append(key, decision, actor, basis, *, current_key, expected_revision,
original_obligation, simulated, study_freeze_sha256, supplement=None,
supplement_bytes=None)` requires:

- Exact key fields `site_id`, `dictionary_hash`, `mapping_hash`, `source_hash`,
  `item_id`. Hashes are lowercase 64-character SHA256 strings. Current key must match.
- Decision exactly `{action, reason}`; action is `abstain|declare_drop|
  map_with_supplement|reject`; text is nonblank, at most 4,096 characters.
- Nonblank bounded actor and 1..32 basis objects, each exactly `{sha256, description}`.
- Integer expected revision >=0; original obligation `preserve|declare_drop|abstain`;
  explicit simulated boolean; study-freeze hash. Unknown abstain cannot be relabeled
  as a known declared drop.
- Mapping requires supplement metadata exactly `sha256`, `fictional: true`,
  `custodian_authorization_sha256`, `expanded_obligations_sha256`, plus matching
  supplied bytes. These hashes record evidence; the store authenticates no role.

Return is `{record, durable_journal: true, projection: "rebuild_required"}`.
Record includes schema1, monotonic sequence, item-wide revision, previous/record
hashes, original inputs and obligation, after-study phase and UTC created_at. Hashing
does not overwrite or admit mappings, original data or independent expectations.

`replay()` verifies canonical bytes, schema/fields, payload, sequence, revisions and
hash chain, returning records. `current(key)` returns latest exact-bound record or
None; a newer record with different input hashes raises stale-key error.
`conflicts(key, expected_revision)` returns conflict/stale booleans and current revision.
`rebuild_index()` verifies journal then transactionally replaces projection rows and
metadata, returning projection state, count and journal head. No index path refuses.
Projection failure is separate from committed append; do not retry an append merely
because rebuilding fails.

Records are limited to 64 KiB including newline. Partial/oversized/noncanonical lines
refuse and require operator recovery preserving the original. Total journal size is
not bounded by this implementation; replay reads it into memory. Locking and fsync
are local-filesystem mechanisms, unverified on OneDrive/distributed filesystems.
Concurrency, crash tail recovery, stale/CAS, supplement and projection behavior remain
deferred. Optional ruling HTML/CLI integration belongs to DL4; independent truth roles
and acceptance remain pending.
