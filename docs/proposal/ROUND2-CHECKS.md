# Round2 keyless developer regression receipt

These are builder-authored unit/integration cases, never independent gold,
held-out cases, calibration or clinical evidence. Real spend remains USD0.00.
Mock usage/ledger charges are authored fault inputs, never real billing.

At the initial below-target run, the app-local environment was NOT READY because
INT's pre-install RAM
guard was below3GiB. ENVIRONMENT-ROUND2.md explicitly authorized a limited existing-
tool fallback for DL2. No installs, package/global configuration changes, Docker,
network/model/API calls, accounts or credential reads were performed by this lane.

Executed interpreter: C:\Program Files\Python311\python.exe
Version: CPython3.11.3, MSC v.1934 64bit AMD64; pytest9.0.3.
Working tree: C:\Worktrees\PortfolioBuilder\hl7-fhir-semantic-loss\DL2-proposal-ledger
Base:9c796c853314c076086a97089039e888c4db3880.

Environment: PYTHONPATH=own-worktree/src;own-worktree and
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Command exactly:

```text
C:\Program Files\Python311\python.exe -m pytest tests/proposal -q --tb=short -p no:cacheprovider --basetemp C:\Users\Roy Harden\OneDrive\PJ-OD\PortfolioBuilder\hl7-fhir-semantic-loss\.agent-work\runtime\DL2\round2-009-20261027T215451344 --junitxml C:\Users\Roy Harden\OneDrive\PJ-OD\PortfolioBuilder\hl7-fhir-semantic-loss\.agent-work\runtime\DL2\receipts\round2-009-20261027T215451344.xml
```

Result:100 passed in17.71seconds, exit0. No skipped or failed tests in this run.
Raw stdout and JUnit XML are preserved privately in OUTER
.agent-work/runtime/DL2/receipts/round2-009-20261027T215451344.log and .xml.
Never reuse that basetemp path: a later invocation must choose a fresh unique
DL2-owned temporary directory so pytest cannot remove an existing artifact tree.
All databases and journals were created inside that isolated developer test base;
no real app ledger was reset or used. Existing files were not deleted by the lane.

Coverage: all ten closed transforms; SN comparator/ratio/range, CWE namespace and
display handling; parser-issued refs, real emitted JSON pointers, escapes/repeats;
per-consumed Z bindings and selector/empty/subcomponent joins; malformed/hash/site/
conflicting/refusal paths; bounded B2 syntax and site schema repairs, request drift,
retained refusal attempts, capped output digests, disabled live ports; mock accounting
cap/unknown/settlement/extreme totals/two-connection concurrency; journal CAS/stale/
supplement/hash/tamper/crash-tail/projection/concurrent append.

One production defect was corrected: generic decimal_with_comparator returned
value/comparator without the quantity kind required by the renderer. The explicit
bound non-OBX numeric regression exercises the corrected consumer contract. No
additional live access or semantic meaning is granted by the fix.

Existing model placeholder <PLACEHOLDER_MODEL_PIN> appears only as MockProvider
metadata in test_mock_workflows.py. No real model pin or key was used. INT must add
that test path to the existing HANDOFF-PLACEHOLDERS.md used-in column; no new access
placeholder is introduced.

At that initial receipt, deferred items included the declared Python3.12 target
(now source-path tested in Runtime014 below), installed-wheel replay, broader
cross-lane/application journeys, rights/admission and actual Java/FHIR/roundtrip
validation, live providers/model quality/budget pricing/operator access, separately
appointed outside-builder O/H/Q/R and independent semantic acceptance. Source tests
passing does not make complete_semantic_score true or ratify independent meaning.


## Runtime012 granted joined-source check

INT then granted the sole serialized compatibility slot in RUNTIME-012.md. The
accepted parser dependency changed, so masterf3d969d was merged preserving reviewed
d5e4074 own bytes at joined sourcef4533e2bd98a5aff0e612cd8acdb3cade351a489.
Command: exact same Python3.11.3 interpreter, -m pytest -q tests/proposal
-p no:cacheprovider --maxfail=1, with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
PYTHONDONTWRITEBYTECODE=1 and the same explicit own-worktree PYTHONPATH.
Fresh basetemp: OUTER .agent-work/runtime/DL2/runtime-012-20261027T220114408.
JUnit/stdout: OUTER .agent-work/runtime/DL2/receipts/runtime-012-20261027T220114408.xml
and .log. Result100 passed9.36seconds, exit0. Slot RELEASED; RUNTIME-013.md grants
DL3 the next slot. No unchanged test repetition is requested.

These two100-pass receipts do NOT cover the later ROUND2-009B future-provider
extension or its new test_future_provider.py. That source was separately reviewed
and subsequently received its own authorized Runtime014 check below. No real HTTP/key/provider
compatibility follows from a canned wire pass.


## Runtime014 declared-target source check

INT marked ENVIRONMENT-ROUND2 READY and granted DL2 slotB. Exact interpreter:
C:\Users\Roy Harden\OneDrive\PJ-OD\PortfolioBuilder\hl7-fhir-semantic-loss\.venv\Scripts\python.exe,
CPython3.12.13 / pytest9.0.3. Shared environment used read-only, no worker installs.

Tested source commit40f79162891890f680ce35840e98b2c9089a6f97 has exact frozen
tree5edcfa283bae5a8b76dd38544426eb9faffac7b2. At run time it was an immutable staged
candidate on HEADf4533e2; the tree was rechecked identical after process exit and
committed unchanged. Later receipt-only documentation edits do not change src/tests.

Environment: PYTHONPATH=own-worktree/src;own-worktree,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and PYTHONDONTWRITEBYTECODE=1.
Working directory remains the assigned DL2 worktree. Exact arguments:

```text
-m pytest -q tests/proposal -p no:cacheprovider --maxfail=1 --basetemp OUTER/.agent-work/runtime/DL2/target312-c45a8a6114374905ac0e1981dc86ea7a/temp --junitxml OUTER/.agent-work/runtime/DL2/target312-c45a8a6114374905ac0e1981dc86ea7a/junit.xml
```

OUTER is the absolute app root named in the interpreter path. Full expanded argv,
interpreter/source/environment pin is in that run directory's source-pin.json.
Result133 passed9.80seconds, exit0; zero failures/errors/skips. All developer DBs,
journals and reports were in the fresh unique lane folder. Runtime process returned;
slotB released with final READY. No real HTTP, socket-capable transport, model,
credential access, account creation, dependency change, install or spend occurred.

Private artifacts in the same run folder:

- pytest.log SHA2561b5ea6b6af8dd0c05c117b7d4b30d4fd65b4271421b976c31e21244ad08547a0
- junit.xml SHA2567a5b6926b1e960e2a6860e7239903f613f586e8301f35b97d3ce4ab71156e2e2
- source-pin.json records the immutable test source and exact argv.

New coverage includes future activation/default refusal, placeholder-only canned
serialization, no-auth/no-callback fake transport, sole-ledger price ceiling and
per-category rounding, request drift/replay, malformed/unknown/capped wire response,
redaction and escaping-independent request/provenance exclusion before reservation.
Only the three named placeholders are used in positive fake-wire configurations.
Pure quoted/backslash/Unicode substring fixtures are ordinary search text, never
credentials or values in activation access fields.

Fresh Medium review found the escaped-JSON overlap bug; logical string-key/value
scanning repairs it. Fresh High construction re-review passed the tested tree.
Both review lineages are builders; no outside-builder O/H/Q or human independence
is implied. The133 tests are developer regressions, not clinical validation or
independent semantic truth. Installed wheel, actual vendor documentation/API/header/
pricing/tokenizer/adapter compatibility, live calls, Java/FHIR/roundtrip and separate
rights/truth/campaign acceptance remain pending. Actual spend stays USD0.00.


##Runtime016009C workflow/accounting bridge

Accepted baseecfcfee97c34023c8817e1b624dfa0a5a366fde3 was merged before the new
workflow seam. Same exact app-local CPython3.12.13/pytest9.0.3, own PYTHONPATH,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1/PYTHONDONTWRITEBYTECODE=1, cache disabled. Both
runs used arguments -m pytest -q tests/proposal -p no:cacheprovider --maxfail=1,
fresh distinct OUTER .agent-work/runtime/DL2/target312-UUID/temp and per-run
junit.xml/pytest.log/source-pin.json. Exact expanded argv is in each source pin.
No overlapping test processes or source mutation during either execution.

First run: tree09f2ffc51adcd72b1e7b3ebb728c2e6e25ef70f6, folder
target312-f65cfd9da9a843f181e68767a05165b7. Result174passed/1failed13.40s,
exit1; JUnit175executed/1failure/0errors/0skips, suite12.898s. Maxfail1 left
remaining cases unexecuted. Oversized B2 onboarding returned error instead of
input-refused before dispatch. It sent nothing and made no money reservation.
The failure artifacts remain intact:

- pytest.log SHA256183416852af952e78dd19488faebc856e5889a496e96bd9616a9e131525cc34a
- junit.xml SHA256b45064960418ab3e130a5c14ce9589923550e1000c860e24408d1f658d0b032e
- source-pin.json SHA2568cd7d4147ea78ad4e04de3f9eefb39c437cf67c564ebbca1117c06c20ccba050

Repair moves complete request construction/hashing inside pre-attempt refusal guards
in B2 and site. Valid-input hashes/IDs/spacing are unchanged; no test was weakened.
The complete rerun was justified by that source correction and the incomplete first
suite. Repaired core commitd652e449e6c341812022f144ce4cd5e3b4e389ec has exact
tested treed5f081ba3074f16a9e8590ae148965e09f9af4b6; immutable before/after run.

Final run folder target312-3c40988c4cb84eafa1f2fe32a17c0648:
179passed35.27s, exit0; JUnit179tests/0failures/0errors/0skips, suite34.591s.

- pytest.log SHA2560be743311d4906530bbd4350440c315d70a94aa05392a994ba1c0f2d8c13c07b
- junit.xml SHA25626886afa6b74d88784c76723baeae5668198845e14660ffe34f417f57db0b770
- source-pin.json SHA256f3f414478e16bbd30633ad00dfc249ccc38369f92b5181c689ed71a75d84eca9

Fresh Medium0A98 reviewed the original full bridge; fresh Medium0B01 reviewed the
concrete refusal-guard repair and original failure receipt. They authored neither
production code nor tests and performed no duplicate runtime. All are builder lineage,
not independent O/H/Q or human stand-ins. Later documentation-only receipt commits do
not change source/tests or require duplicate execution.

The new cases exercise one financial owner, same Ledger instance, native B2/A IDs and
provenance, caller ceilings vs actual reservation/settlement, no duplicate dispatch on
replay, known cap fee preservation, unknown/cap/failure stop before repair, one bounded
syntax/schema repair with public-only feedback, exact modes, model-text vs wire hashes,
placeholder/default-live guards, depth/node/byte input refusal and JSON secret filtering.
All future positive fixtures use the concrete canned transport and the same three named
placeholders; no HTTP/socket-capable fake, invented/actual key or model call is used.
Mock/test monetary entries are simulated; actual app spend remains USD0.00.

SlotB process returned/released. Earlier133-pass evidence is009B only, not a substitute
for these009C bytes. Installed-wheel/combined consumer journeys are INT-owned next work.
Official current vendor adapter/headers/tokenizer/prices/access, live calls, Java/FHIR/
roundtrip, rights, and outside-builder O/H/Q/R/semantic acceptance remain pending.
