# Round2 keyless developer regression receipt

These are builder-authored unit/integration cases, never independent gold,
held-out cases, calibration or clinical evidence. Real spend remains USD0.00.
Mock usage/ledger charges are authored fault inputs, never real billing.

The app-local target environment remains NOT READY because INT's pre-install RAM
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

Still deferred: declared Python3.12 target and installed-wheel replay, broader
cross-lane/application journeys, rights/admission and actual Java/FHIR/roundtrip
validation, live providers/model quality/budget pricing/operator access, separately
appointed outside-builder O/H/Q/R and independent semantic acceptance. Source tests
passing does not make complete_semantic_score true or ratify independent meaning.
