# Keyless developer validation — Round 2

Roy's Round 2 policy permits local keyless runtime checks on the INT-owned app-local
environment. This does not authorize model calls, credentials, public standards assets,
independent truth, spending, servers, Docker or publication. Developer test fixtures are
builder-authored unit cases, never held-out gold, independent calibration or clinical
validation. All mocked costs remain simulated; actual spend is USD0.

INT publishes `ENVIRONMENT-ROUND2.md` with READY and the exact OUTER interpreter. Workers
must not install or repair dependencies themselves. Use that interpreter read-only,
pointing PYTHONPATH at the worker's own source and repository. Disable external pytest
plugins and bytecode writes; isolate all DBs/journals under a fresh unique OUTER
`.agent-work/runtime/DL4/<run-id>/` directory. Preserve failed-run logs and choose a new
run-id when rerunning; never reset the real lifetime ledger.

Example PowerShell template (substitute verified READY paths; not an execution receipt):

```powershell
$env:PYTHONPATH = '<WORKTREE>\src;<WORKTREE>'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
& '<READY_INTERPRETER>' -m pytest '<WORKTREE>\tests\cli' -p no:cacheprovider -ra `
  --basetemp '<OUTER>\.agent-work\runtime\DL4\<unique-run>\pytest-temp' `
  --junitxml '<OUTER>\.agent-work\runtime\DL4\<unique-run>\results.xml'
```

`tests/cli` exercises help/demo, original developer exports and hashes, parse refusal,
B0 partial results, DSL binding, authored mock repair/unknown usage/persistence/capped
metadata, simulated journal/replay/new-path restrictions, report escaping and complete
JSON preservation, malformed/deep/oversize inputs, and ledger/input/sidecar aliases.
Symlink capability may be unavailable on Windows; report the exact skipped case rather
than claim that path passed. Hardlink alias checks remain separate.

Execution state and exact commands/counts belong in the current run's READY receipt.
At initial test authoring the environment marker was absent; the published marker now
says NOT READY because setup RAM was below 3 GiB. No app-local interpreter exists yet.
Global Python3.11/Typer0.7 is explicitly not an authorized DL4 CLI fallback; do not run
this suite there or alter the product to accommodate it. No runtime claim is implied.
A later keyless test pass proves only the exercised local
developer behavior. Java, generic/paired roundtrip acceptance, independent scoring and
custody/rights/model/clinical gates remain separate and pending.
