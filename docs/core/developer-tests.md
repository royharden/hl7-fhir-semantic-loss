# Builder regression checks

`tests/core` contains original builder-authored unit inputs/assertions, not oracle
calibration, held-out evaluation data, independent fidelity review or clinical
validation. Developer generator determinism/counts and mapper behavior are checked
against the original public developer dictionary. A successful run does not admit
standards/terminology rights or imply Java conformance or complete semantic scoring.

The parser regressions cover original-byte identity on fifty developer inputs,
MSH fields, byte/hash/coordinate refs, known and unsupported escapes, repeats,
components/subcomponents, empty/null, group scopes, custom delimiters, framing,
byte/segment/atom caps, hostile text and forged-coordinate aliases. Source fixes
allow exactly the declared atom cap before rejecting the next leaf, and reject
bool/float values where an exact integer coordinate is required.

Mapper/projection regressions cover malformed dictionary refusal, namespace
conflicts, numeric precision and lexical scale, NM/SN/ST/CWE, unsupported ranges,
repeated notes/flags/values, dictionary-gated time precision/timezone handling,
patient/order links, dictionary hash drift, numeric/metadata/link tampering,
ambiguous reverse dictionary keys and the authored eight-by-fifty source design.

Round2 execution is gated by the OUTER `ENVIRONMENT-ROUND2.md` READY record. INT
owns the shared OUTER `.venv`; workers install nothing. When explicitly READY,
use its exact interpreter in the assigned worktree with `PYTHONPATH` containing
`<worktree>/src;<worktree>` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Run only
`-m pytest tests/core -q -p no:cacheprovider`, with a unique task artifact root
under OUTER `.agent-work/runtime/DL1/` for any base temp/log/JUnit output. Record
the actual interpreter, base commit, full command, exit code and collected/passed/
failed counts. Do not substitute a globally registered or another app's Python.

At authorship checkpoint the target environment was NOT READY (INT RAM guard
blocked setup before installation). INT subsequently authorized an existing-tool
fallback: Python 3.11.3 with pytest 9.0.3, explicit worktree PYTHONPATH and disabled
plugin autoload. This source-level compatibility run completed 146 developer tests
with 146 passed, zero failures, exit 0, in 5.17 seconds. It ran the same core command
above with isolated OUTER artifacts. The private READY receipt records exact paths
and command. No installs or live calls occurred. This is below the declared Python
3.12 target and is not installed-artifact, Java or independent evaluation acceptance.

The first target-3.12 run exposed JSON-encoder-dependent recursion behavior: deeply
nested metadata serialized successfully there while 3.11 rejected it. B0 now
explicitly limits dictionary traversal to depth 64 (root depth zero) and 65536
visited nodes before hashing. Malformed/over-limit metadata returns refusal with
the parsed leaf ledger; it does not depend on the interpreter recursion threshold.
