# Integration002: as-built parser/dictionary reconciliation
Construction only. Round2 developer source-path tests now pass on the allowed
below-target Python3.11.3 fallback and later the app-local Python3.12.13 source-path
target (ROUND2-CHECKS.md). Separate O/H/Q, rights,
Python3.12 installed-artifact execution, actual FHIR validation and semantic
acceptance remain pending.

The original ten transforms remain closed. Existing dictionary_lookup and
unit_from_dictionary now consume the accepted producer top-level maps. No source
producer or shared interface file was edited. Optional dictionary.tables is an
explicit compatibility path. Original dictionary bytes/hash are not rewritten.
Producer site_id is checked if present; absent site_id produces an explicitly
unverified site label, with exact proposal.site_id and dictionary hash retained.
See OUTER DL2-DICTIONARY-INTEGRATION002.md for the producer-owned site_id request.
UPDATE005 resolves that request in accepted producer d77daaa: new releases include
site_id, derived scalar table views and report_code as a nonempty display STRING.
The executor uses that fallback exactly as DiagnosticReport.code.text; it does not
invent a coding namespace. Explicit report.code/report.system mappings still require
a dictionary-bound coding. Scalar code views are checked against canonical entries;
overlapping mapped sources merge emitted target pointers, while mapped-versus-drop/
abstain conflicts and duplicate target assignments refuse.
The canonical flags map carries released local Coding entries; those are emitted
as interpretation.coding, while an explicit scalar flag view remains text. Flag
pointers resolve to the emitted interpretation element in either representation.

The selector component="all" may bind existing decimal_with_comparator,
dictionary_lookup, repeated_value and unit_from_dictionary to one complete
lexical field/repetition. OBX-5 value operations use parser OBX-2 datatype and
all leaves of exactly one repetition. They do not flatten unknown components.
NM -> exact quantity; ST -> decoded valueString; SN -> comparator quantity,
bounded colon ratio or hyphen range; CWE -> dictionary-bound valueCodeableConcept.
CWE and code/unit fields require source authority component3 to authorize the
emitted system. Display source is mapped only when it agrees with emitted display.
Nonempty extra components/subcomponents, conflicting namespaces, unsupported
SN combinations, null/empty values and numeric precision loss refuse. Ratio units
refuse because a single source unit does not establish numerator/denominator roles.
Range units apply to both bounds only through the explicit known unit mapping.
This is original construction behavior, not admitted standard conformance.

Closed targets add patient.system, report.code and report.system to existing
identity/code/status slots. Patient/order/observation resource identities and
relations remain executor-owned. Multiple value repetitions emit separate
observations with common code/status; notes retain separate source segment slots.
Every mapped disposition is computed only after resource emission and resolves
against the actual Bundle as a JSON pointer. All source rows remain present:
unselected empty/null/unknown slots abstain with distinct reasons; on refusal all
parsed refs are retained as execution_refused abstentions with no output Bundle.
A datatype source row can point at multiple emitted repeated-value structures;
it never becomes an invented scalar value.

Exact provider/accounting/ruling signatures and response shapes for DL4 are in
AS-BUILT-PORTS.md. Both model paths take the same injected lifetime Ledger. No
runner is introduced here. No live dispatch or independent role is authorized.

Deferred: integrated parser/DSL public developer execution, all selector/null/
repeat/group/SN/CWE/namespace adversarial cases and pointer traversal, malformed
input refusal and attempt identity drift tests, accounting/crash/concurrency,
journal replay and all actual validation/independent review gates.
