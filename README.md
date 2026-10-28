# Semantic Loss Lab (`h7loss`)
Synthetic ORU^R01 v2.8 to FHIR R4 semantic-loss instrument. Dirty construction with keyless developer CLI checks; no measured semantic results or clinical claims. Rights/admission/independent roles pending.
Plan: OUTER ../planning/promoted/PLAN-M12-v1.md; run ../agentops/START.md; deferred checks ../DEFERRED-VALIDATION.md. Evaluation separate from product wheel.

The local CLI source offers an authored `demo --mock`, one-message developer generation,
lazy parser/B0/DSL command wiring, escaped HTML/JSON reporting and full supplied-failure
export. Reports mark supplied assertions unverified and preserve byte hashes. Admission,
Java validation, round trip, independent scoring, campaigns and live dispatch
currently refuse. Round 2 target CLI tests exercised the authored and mock commands.

See [the proposed CLI journey](docs/user/CLI.md), [limitations](LIMITATIONS.md), and
[deferred CLI/report checks](tests/README.md). No keys or hosted services are needed for
the authored demo. The app-local target environment uses requirements-test-resolved.txt.
Installed-artifact replay, actual validator/model runs and independent acceptance remain pending.

Integrated source journey: `demo --mock` calls the original developer generator, parser
and B0. Authored-response mock-map/mock-propose commands use the persistent money ledger;
simulated hash-bound ruling append and journal replay are wired. Literal producer
outcomes and failures remain visible, with nonzero exits for partial/refused work.
The developer regression run exercised these paths through Typer's CliRunner.

Round 2 adds builder-only CLI regressions under `tests/cli`; local execution requires
the INT-owned environment's READY marker. See [keyless developer validation](docs/user/ROUND2-TESTING.md)
for isolation and command guidance. Observed target run: 37 passed in 4.36s on Python
3.12.13, Typer0.12.5 and Click8.1.8, source6d338e0. This covers developer CLI behavior;
independent truth, installed-wheel entrypoint and actual validator/model results remain pending.
