# Core construction boundary

Original source, unadmitted and runtime-unverified. No copied standard prose,
terminology, gold, held-out data or evaluation implementation is included.

`parse_message(bytes)` returns original raw hex/hash, zero-based segment indices,
one-based field/repetition/component/subcomponent positions and half-open byte
spans. Empty and explicit null leaves remain distinct. CR and CRLF are retained;
LF framing is unsupported. MSH delimiter fields are opaque. Escapes F/S/T/R/E,
X hexadecimal and .br are lexical conveniences, not clinical interpretation.
Unknown escapes and non-ASCII decoded bytes retain raw refs and refuse text use.
One MiB, 4096 segment and 65536 atom caps bound parsing. Serialization reopens the
original bytes and verifies SHA256; edits to parsed field metadata do not rewrite
the source. This is archival lexical serialization, not an editable builder.

B0 implements a narrow original dictionary-bound construction mapping. Dictionary
keys: `identifier_systems` maps source authority to system URI, `codes`/`units`
map local tokens to system/code/display, `observation_statuses` and
`report_statuses` explicitly map source status tokens. Local coding metadata
requires `coding_authorities` to bind nonempty source authority tokens to a list
of allowed target system URIs; conflicting/unknown namespaces refuse mapping.
Malformed dictionary maps return explicit refusal with leaf abstentions.
Metadata without a specific rule is abstained, never validated terminology.
Every parsed leaf receives a disposition. Mapping unknown/null/unsupported
values is refused. Repeated OBX-5 leaves produce separate Observations under the
same order, with Patient and DiagnosticReport links. Explicit `time_fields`
meaning enables OBR-7/OBX-14 conversion to effectiveDateTime, preserving date-only
precision or full seconds/fractions with the supplied numeric offset. Partial
time or missing timezone refuses conversion. Explicit original `flags` maps
enable distinct OBX-8 repetitions in Observation.interpretation. `note_scopes`
permits scoped NTE-3: observation notes become distinct Annotation text entries;
order notes become distinct original order-note extension values. No meaning is
inferred for absent dictionary entries. Reports require code/status;
Observations require report, code/status/value and numeric unit when applicable.
NM/SN numerical conversion rejects nonfinite/changed decimal values and retains
the original number lexeme. SN ranges beyond comparator/number are unsupported.

No IG file/hash lock is available: the rules remain original/unadmitted, with
`ig_rule_lock=PENDING`. No Java pass is asserted. `paired_inverse(result,dictionary)`
reconstructs only declared mapped source leaf text from actual resource values,
safe bundle pointers and the hash-bound public dictionary. It reports unsupported
source leaves and observed links explicitly; see paired.md. It never replays raw
bytes and never reports a roundtrip pass. This paired builder control is not an
independent renderer, oracle or Q truth.

Deferred: installed-wheel integration, byte/ref/escape/cap regression tests,
dictionary input validation, NM/SN/ST/CWE fidelity, every-atom ledger checks,
actual FHIR validation, mapping IG/rights admission and pinned rule citations,
paired-projection runtime checks and independently owned truth/fidelity/calibration gates.
