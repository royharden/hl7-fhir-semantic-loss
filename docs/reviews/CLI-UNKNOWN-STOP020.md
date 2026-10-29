# CLI unknown-billing contract correction — Round2-020

Base1aa1c79decc03bb1567172281b9079ad162e6878. Root combined failure preserved at
OUTER .agent-work/runtime/INT/combined312-dfdeedcfadf04baea0f1eb7022330c7d:1 failed,
33 passed, remaining cases unexecuted. Failure was a stale test expectation, not a CLI
serialization or producer safety defect. WORKFLOW-PROVIDERS requires unknown billing
to stop with held liability. Product source remains unchanged.

Repair515250d9848842798417f17aa6584e339d6b8eac splits known-billing syntax repair and
unknown-usage stop regressions. Unknown malformed text plus an available valid second
fixture asserts exit2, exact error/stop, no Bundle, one retained attempt, actualNone,
held7, and reserve→dispatch→unknown event sequence. This catches premature repair,
extra dispatch and treating unknown usage as zero. No skip/suppression/guard weakening.

Fresh Medium0037_Codex_gpt-61-sol_Sub_DL4UnknownReview PASS on changed tests/actual source
contract. Focused target run on immutable tree d2f664483da029420b0b5317ae832fa6d3873280:
38 passed in4.87s, exit0. No code fixes/reruns; slotD released. Exact interpreter/argv/
artifact hashes in private READY. Subsequent docs only record observed scope. Earlier
37pass6d338e0 and installed-smoke evidence are not claimed to cover the new combined
failure. No duplicate installed-artifact check, broad combined test or live/model call.
Builder regressions remain separate from independent/clinical/Java/held-out acceptance.
