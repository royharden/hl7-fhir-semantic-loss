# Developer generator construction

`h7loss.gen.generate_case(site_id="dev-01", index=0)` returns a fresh mapping with
`case_id`, `site_id`, `index`, `partition`, `usage`, `provenance`, `raw` bytes,
`raw_sha256`, `dictionary`, and `dictionary_sha256`. The dictionary hash uses
ASCII JSON with sorted keys and separators `,` and `:`. Raw bytes make this an
in-process construction interface; a future CLI must explicitly encode/write them.

`generate_development_cases()` lazily yields eight sites with fifty messages each.
Indices 0–44 are developer scored inputs and 45–49 are separate onboarding inputs.
No corpus files are produced on import. This source capability has not been run.

All identifiers, displays, local units and values are original synthetic developer
material, marked `NOT_ADMITTED`; rights and independent semantic review remain
pending. The dictionary contains no copied standard terminology or external
dictionary. `codes` describes observation codes; `units` describes the original
`du` unit; `value_codes` describes the original categorical values. These maps are
explicit released developer metadata, not an oracle. `site_id`, scalar `tables`,
empty `bindings`, and string `report_code` are views derived from the same original
maps for the current DSL API. Canonical hashing matches the DSL's sorted compact
ASCII-escaped JSON and rejects nonfinite numbers. `time_fields`, `note_scopes`,
and original `flags` explicitly release local meanings for B0. `z_segments` is empty: the
opaque ZDV field contents have no released semantic meaning.

The source varies NM/SN/ST/CWE, CR/CRLF, one/two orders, one/two/three observations,
scoped notes, missing timestamp offset, source flags/status, numeric lexical scale,
SN comparators/ranges/ratios, escaped delimiters, hex and line-break escapes,
explicit null text and repeated text. These are authored source variations, with
no expected semantic outcomes, gold annotations, atom assertions or FHIR output.
The generator imports neither parser, mapper nor evaluation code. Independent
O/H/Q authors must supply and review truth and held-out material separately.

Deferred: execute generation and determinism checks; resolve every raw pointer;
measure intended coverage/floors and exact counts; independently assess semantics;
admit the original artifacts; exercise parser/mapper and confirm dictionary seams.
No runtime, conformance, clinical validity or evaluation acceptance is claimed.
