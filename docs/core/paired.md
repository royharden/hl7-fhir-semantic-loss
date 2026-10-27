# B0 paired source projection

`h7loss.v2.paired.paired_inverse(result, dictionary)` reconstructs supported
source leaf text from the mapped Bundle and public, hash-bound dictionary. It
never reads raw bytes, raw hex, a generator, an oracle or an independent renderer.
It is original B0 paired control tooling, not Q truth or a round-trip verdict.

The producer supplies `paired_projection`: records containing `source_ref`,
`target_ref` (a Bundle-rooted `/entry/N/resource/...` pointer), and one fixed
`transform`. Each record must match a mapped disposition and one of that row's
target refs. Coordinate metadata is B0-attributed; it is not independently
verified against raw input here.

- `copy`: the target must be text.
- `dictionary_key`: `table` selects identifier_systems, codes, value_codes, units,
  observation_statuses, report_statuses or flags. A unique public dictionary key
  must match the target string, or target system/code pair for coded objects.
- `timestamp`: `precision` counts compact date/time digits plus fractional digits.
  Supported counts are 4, 6, 8, 14, or 15–23. Date-only targets retain precision;
  full time requires seconds and an explicit numeric offset. Fraction length
  must match metadata exactly. No implicit zone or Z normalization is performed.
- `datatype`: an Observation's actual single value choice determines ST, CWE,
  NM or SN; SN requires a supported Quantity comparator.
- `numeric_lexeme`: the Observation must retain exactly one
  `urn:h7loss:original-numeric-lexeme` string extension. Its decimal value must
  equal the actual finite Quantity value. The extension alone cannot mask a
  changed numerical target.

Consistent duplicate source refs coalesce with all target refs retained;
conflicting repeated target values become unsupported. Every disposition without
a successful inverse remains explicit in `unsupported`, including declared drops,
abstentions and mapped leaves without an inverse rule. Ambiguous dictionary
reversal, missing targets and malformed metadata refuse projection as appropriate.

Optional `paired_relations` records contain only `source_group` and `target_ref`.
Pointers must select actual subject.reference or report.result/N/reference text.
Returned relations carry those observed values, never expected links or truth.

The return includes `status` (`projected`, `partial` or `unsupported`),
`projection`, `unsupported`, `relations`, `error`, and an explicit construction
evidence/runtime-unverified label. A projection is not a full v2 message or byte
serializer. No pass/fail source comparison, clinical fidelity, IG admission or
independent evaluation claim is supplied.

Deferred after Dirty Mode: exercise target mutation, duplicate/conflict,
dictionary ambiguity/hash mismatch, timestamp precision/offset, numeric drift,
malformed metadata, source-ref completeness and patient/order link scenarios.
