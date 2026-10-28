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
Initial RAM-blocked attempts remain historical NOT_RUN. Runtime014 later authorized
the READY app-local Python3.12.13 environment with pytest9.0.3, Typer0.12.5, Click8.1.8
and Pydantic2.12.5. The run on source6d338e02685a7f7b77799b31fe4082e46d9396fb,
treeb068241d2ea3964547d93b11c8afba76dd3c803e returned exit0: **37 passed in4.36s**,
zero failures/skips. The app was exercised through CliRunner, without installing the
product wheel or invoking an installed console script.

Executed command (own worktree cwd, environment variables as above):

```text
<OUTER>\.venv\Scripts\python.exe -m pytest -q tests/cli -p no:cacheprovider --maxfail=1 --basetemp <OUTER>\.agent-work\runtime\DL4\target312-e64812ba012e41e79b775d5faa75a097\temp --junitxml <OUTER>\.agent-work\runtime\DL4\target312-e64812ba012e41e79b775d5faa75a097\results.xml
```

The same run directory retains command.json, pytest.log and results.xml with hashes in
the private run READY receipt. It used authored temporary DBs/journals only, no actual
ledger reset, API key, network/model call, worker install or spending. The slot was
released after return; no unchanged-suite rerun was needed. Local checks prove only
the exercised developer behavior. Java, generic/paired roundtrip acceptance, independent scoring and
custody/rights/model/clinical gates remain separate and pending.
