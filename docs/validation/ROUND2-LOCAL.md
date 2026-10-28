# Round 2 local construction validation

2026-10-27. This is builder-authored developer validation, not independent semantic,
clinical, standards-conformance, live-provider, held-out-study or release acceptance.

## Executed checks

| Scope | Exact source | Actual result |
|---|---|---|
| Final combined developer suite | `27c655375064fcda29625fbfb95dd95540661a39` | Python 3.12.13 / pytest 9.0.3: **488 passed**, 0 failures/errors/skips; pytest 15.91 s, driver 17.022 s |
| Installed application console | wheel built from `7aab52e`, packaged module/config bytes equal checked tree `1aa1c79` | Clean runtime-only venv, no source path injection; help, authored demo, exports, parse/map, HTML/JSON/failure reports and explicit validator refusal passed |
| Package boundary | same wheel | All packaged Python bytes matched pinned source; evaluation/tests/private coordination absent; evaluation, pytest and hatchling not importable in runtime-only venv |

The combined run covered core, proposal/provider/accounting/rulings, provisional
vocabulary/evaluation/runner/archive/normalizer, and CLI regressions together. Source,
tracked configuration/schema assets and HEAD were unchanged during the run; working
tree was clean before and after. Plugins, pytest cache and bytecode writes were disabled;
all ledgers/journals were fresh isolated developer fixtures. No real app ledger reset.

The wheel SHA256 is
`a90b77a8e4b8e171ef15e1b6b2988bb22075eb3c77e5bc17f0aba0a16f8ba136`.
The clean install used the pinned runtime dependency subset from the private local cache.
Installed `h7loss` imported from its own venv, without the development/test environment.
The single installed `demo --mock` command took 1.502594 s on Kaiser-Pro/Windows x64;
setup/download/build excluded. This is only an authored keyless demonstration, not timing
of a Java/roundtrip/model study. Expected partial mapping and validator refusal returned
exit 2, preserving their unverified records; they were not fabricated as successful
validation. No application model/network/credential access occurred. Actual testing spend
was USD 0.00, against a USD 40.00 hard ceiling.

## Failures retained and repaired

- Python 3.11 compatibility passes did not substitute for target checks. The first
  Python 3.12 core run failed a deep-dictionary case; explicit depth/node bounds replaced
  reliance on encoder recursion. The repaired core scope passed 149 target tests.
- The first 009C bridge run failed oversized-onboarding classification; both wrappers
  were corrected without weakening dispatch refusal. The repaired proposal scope passed
  179 target tests.
- The first combined run stopped at 33 passes/1 failure: an older CLI unit expected
  unknown billing to produce usable output. The authoritative stop-required behavior was
  preserved. The revised test verifies one attempt, unknown actual usage, held liability,
  no repair and nonzero exit; 38 CLI tests then passed and the final combined run passed.
- Three package-driver setup attempts failed before application execution (two Windows
  constraint-path parsing failures, then an offline cache/version mismatch). Their
  receipts/drivers remain private. Workspace-relative paths and the setup's matching uv
  0.11.19 enabled the offline install; the already-built wheel was reused unchanged.

Exact execution commands, pre/post source manifests, logs, JUnit, wheel members and
failed-attempt receipts are retained in the private OUTER coordination shell. This
portable summary intentionally contains no private chat export or access value.

## Remaining phase boundaries

`complete_semantic_score`, `headline_eligible` and independent/live/billing verification
remain false. Builder-v0 policy is provisional, not independent gold. Normalized
provider labels are claims, not proof of real calls or charges. Java/stock Microsoft
baseline/generic independent roundtrip, standards assets and actual-use rights are not
admitted or measured. No held-out corpus or independent O/H/Q/R was authored/appointed
by the builder lineage. A separate fresh nonbuilder role process and later human
ratification are required by the current instructions.

Future live activation additionally needs Roy-supplied access, the exact model/endpoint,
current vendor translation/adapter/authentication/tokenizer/complete-price verification,
explicit operator/campaign/input bounds and one lifetime money ledger. Filling a key
alone does not verify vendor support. Default commands remain keyless/refused; no live
adapter/SDK/HTTP client or activation CLI is bundled. No public license, remote, push,
publish/deploy or account/credit purchase was authorized or performed. Dirty Mode remains
open under its scoped Round 2 policy; this checkpoint does not close it or appoint a
successor integrator.
