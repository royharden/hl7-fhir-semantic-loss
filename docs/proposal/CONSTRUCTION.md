# Proposal, accounting and rulings construction

This source is built for Dirty construction and has not run. Authored mock responses
are not model-quality results, FHIR validation, mapping-IG admission, or independent
semantic evidence. Live ports always refuse and never inspect credentials.

`h7loss.proposal.validate_proposal(dict)` returns `valid/errors`;
`compile_proposal(dict)` freezes JSON and its SHA256; `execute_proposal(raw,
dictionary, proposal)` returns a serialized ArmResult with a Bundle or explicit
error. There is no eval, model-written template, plugin, FHIRPath, arbitrary target
path, filesystem lookup or external validator call.

Version 1 proposal keys are exactly `version`, `site_id`, `dictionary_sha256`,
`rules`. The dictionary hash is SHA256 over UTF-8 Python JSON with sorted keys,
compact separators, ASCII escaping and nonfinite values refused. Maximum proposal
32 KiB, 64 rules; maximum raw message 1 MiB. Rules contain `source`, `transform`,
and a fixed `target`, with optional literal `guard`, dictionary table name and
disposition reason. Source is either an exact complete SourceRef or the selector
`segment/scope/field/repetition/component/subcomponent`. Indices are one based;
scopes are message, patient, order, observation. A reusable site proposal uses
selectors. `repetition: "all"` is exclusive to repeated_value; `component: "all"`
is supported by join_components and the existing decimal/dictionary/repeated/unit
transforms for bounded composite inputs. Parser-produced lexical refs bind every match.

The ten fixed transforms are copy_text, decimal_with_comparator,
timestamp_preserve_precision, dictionary_lookup, unit_from_dictionary,
repeated_value, join_components, constant_from_dictionary, declare_drop and
abstain. Dictionary operations prefer explicit top-level `dictionary[name]` tables,
matching the accepted developer producer, with `dictionary.tables[name]` retained
for explicit custom tables. Lookups index exact decoded text, constants index
`constant`, and joins use a released `separator`. Coding entries preserve
system/code/display and require a source coding authority permitted by the dictionary. Z segments require every mapped component's explicit
`dictionary.bindings["Zxx.field.component.subcomponent"] == target`. Nothing
promotes hidden/undocumented meaning. When dictionary.site_id is present it must match. Without that producer field,
proposal.site_id is an explicit unverified site label bound to the unchanged exact
dictionary hash; the result records site_label_verified=false. No dictionary_id
string is parsed to infer a site.

Targets are the closed patient id/system, observation code/system/value/comparator/
unit/status/flag/time/precision/note, and report code/system/status slots. Executor-owned IDs follow
DL1's `patient:0/order:N/observation:N` lexical groups; model output cannot set
relations. Patient identity is required before other output. Observation code and
FHIR status are required before emitting an Observation. DiagnosticReport requires
dictionary-bound mapped report.code (or dictionary.report_code display STRING,
preserved as code.text without an invented namespace)
plus mapped status. Identifier system is mapped only through explicit released
identifier_systems. Report and observation namespaces remain dictionary-bound. References are executor-owned.
FHIR timestamps preserve original precision/offset; partial time without seconds
or zone refuses. Numeric conversion refuses precision loss. The standalone
precision target refuses pending an admitted extension contract. ServiceRequest
and cross-scope source selectors remain unsupported. Bounded SN/CWE conversion
is described in INTEGRATION002.md.
No IG conformance is claimed. Empty/null/unsupported atoms and unmatched rules
produce explicit abstentions; mapping conflicts fail the whole output.

`propose_site(dictionary, onboarding, *, provider, ledger, config_id, model, site_id=None, ...)`
is mock-only, at most five explicit onboarding strings, one initial proposal and
one local schema-only repair. No scores, truth, user-supplied feedback callbacks,
Java or roundtrip feedback enter this path. Reusing dispatched site/config/hash
identity refuses. A fresh config is not approval for a further study attempt;
campaign freeze enforcement belongs to the future authorized runner.

`h7loss.arms.b2.map_message` uses the same Ledger and accepts exactly MockProvider.
It permits one JSON syntax repair and returns raw authored attempts/hashes. Shape
errors are not repaired. Produced output is unvalidated model-authored content.

`Ledger(path, cap_micro_usd=40_000_000)` is the sole app-lifetime money authority:
reserve worst-case liability, atomically claim dispatch, settle known usage or
retain unknown liability, report. All amounts are integer microUSD. Never replace
the database to reset capacity. Caller-provided maximum liability is not a price
proof or dispatch approval. Live dispatch is unavailable under this construction.

`RulingStore(journal, index=None)` writes authoritative canonical hash-chained
JSONL with serialized append, actor/evidence, source/dictionary/mapping keys,
expected revision and after-study freeze hash. SQLite is a rebuildable projection.
Stale keys, conflicting revisions, invalid chain and partial records refuse.
Mapping unknowns requires a separately hashed fictional dictionary supplement,
custodian-authorization and expanded-obligation hashes; original obligation stays
recorded. Hash fields record evidence, not role authentication or admission.
Simulation is explicit. Rulings do not alter original primary-study expectations.

Deferred activation checks: parser/DSL joined execution and source-pointer
coverage; all transforms, guards, repetitions, conflicts, malicious JSON and
resource target refs; proposal/B2 syntax repair and attempt-cap persistence;
accounting cap/concurrency/crash/unknown settlement; journal append/crash/CAS/stale/
supplement/SQLite replay; actual Java/structural checks; separate O/H/Q admission
and semantic acceptance. Do not infer a pass from static inspection.
