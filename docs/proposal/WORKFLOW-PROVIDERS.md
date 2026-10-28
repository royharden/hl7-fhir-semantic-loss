# Workflow provider bridge — source contract, compatibility NOT_VERIFIED

The bridge preserves existing keyless MockProvider defaults. Configured future providers
can enter B2/site through an explicit internal seam; neither a CLI activation route nor
a live HTTP adapter is added. No SDK, network call, environment/credential discovery,
installation or spend is part of this task. Runtime016 subsequently passed179
builder source-path tests on Python3.12.13; exact source/failure/repair receipts
are in ROUND2-CHECKS.md. That does not verify live/vendor or independent meaning.

## Exact API

Import from h7loss.providers.workflow:

    describe_provider(provider, ledger) -> str
    dispatch_attempt(provider, ledger, *, attempt_id, liability, provenance,
                     messages, schema, model, max_output_chars) -> dict
    bounded_json(value, compact=True) -> str

The descriptor accepts exact MockProvider as authored_mock. It accepts only the exact
public AnthropicProvider/OpenAICompatibleProvider classes after their existing future
activation gates, and requires provider._ledger is ledger. Evidence is authored_fake_wire
or unverified_live_wire. Default/unconfigured/disabled objects refuse with ProviderError;
subclasses and arbitrary provider objects are not admitted. Descriptor validation neither
reserves nor sends. Runtime current scope remains exact canned authored fake with the
three named placeholders; future live gates remain intact and compatibility unverified.

The dispatch result has outcome ('ok', 'refused', or 'error'), attempt, response (dict or
None), error (string or None), and stop_required. 'ok' means provider/accounting completed
with known billing; output syntax/shape/source/semantic validity remains a workflow task.
Thus malformed model JSON with known billing can consume only an already permitted
syntax/schema repair. Unknown usage or any provider failure/cap stops the workflow.

Attempt includes attempt_id, incoming_provenance, provenance, caller
max_liability_micro_usd, dispatch_state, previously_dispatched,
dispatch_occurred_this_call, and provider response/accounting fields when available.
Persisted history adds previous_attempt (dispatched, usage_state, reserved, actual,
provenance), reservation_state, usage_state, ledger_dispatch_state, reserved_micro_usd,
actual_micro_usd and ledger_provenance. Actual reserved/settled amounts are distinct
from the caller maximum liability ceiling.
A replay/refusal retains incoming provenance alongside actual persisted history.
Legacy dispatch_state describes this invocation only; replay stays not_dispatched with
previously_dispatched=true, ledger_dispatch_state=dispatched and
 dispatch_occurred_this_call=false. The wrapper must append each returned attempt, including
refusals. Invalid unbounded provenance is omitted; credential-bearing metadata is
redacted before returning diagnostic fields; a credential-bearing attempt identity is withheld, never replaced. No raw exception text is returned.

## One owner for each attempt

For exact MockProvider the helper alone reserves, marks dispatch, calls the normal
instance complete method once (preserving capture-method tests), and settles. Existing
native workflow attempt IDs/provenance are unchanged. Known authored mock cap fees
remain known fees and settle; the cap still stops. Unknown mock usage/timeout/exception
retains its reservation and stops. A liability breach preserves Ledger's frozen state.

For exact configured future providers the helper calls UNBOUND FutureProvider.complete
once. It does not reserve, mark, or settle a future attempt. The future budget adds:

    {'attempt_id': ..., 'max_output_chars': ...,
     'max_liability_micro_usd': liability, 'workflow_provenance': provenance}

Future computes its exact price liability and refuses before reserve/send if it exceeds
the explicit nonnegative integer caller cap. Native workflow provenance fields stay at
the TOP LEVEL of the actual ledger record, plus reserved field provider_wire containing
canonical provider request/config/price/operator proof and caller liability cap. Caller
provenance cannot overwrite provider_wire. Drift conflicts under the same stable ID.
The computed price reservation can be lower than the caller ceiling; no extra ceiling
is reserved by the workflow. Both paths use the exact same injected lifetime Ledger;
no second database, reset, alternative ID, hidden retry, or extra feedback is introduced.

## Output evidence and secrets

Future's standalone raw_output_sha256 remains the original wire-body hash for backwards
compatibility. New wire_response_sha256 explicitly names that digest. raw_text_sha256
and raw_output_chars describe the model text BEFORE the character cap; output_omitted
remains true for failures/caps. Workflow response.raw_output_sha256 is normalized to
raw_text_sha256, matching the existing model-text digest vocabulary. The original wire
hash remains in wire_response_sha256 and the settlement receipt. A malformed wire body
can have a wire hash without any text hash.

Plain-text configured key occurrences retain the existing redaction behavior. For model
text that parses as JSON, logical key/value overlap with the configured key refuses the
output and retains billing exposure. Escaped Unicode spelling and duplicate-key values
are checked too. Output/exception/headers never expose the configured key. A raw hash
is evidence of original bytes, not proof that the returned redacted text is identical.

## Bounded serialization and handoff

bounded_json uses the future primitive: explicit depth32, node10000, finite JSON values,
string dictionary keys, and UTF-8 serialized byte cap1048576. compact=True uses sorted
keys and compact separators. compact=False uses sorted keys with ordinary json.dumps
spacing, preserving existing site fingerprints. The helper bounds messages/schema and
provenance before dispatch; workflows use it when constructing/hashing their native
requests. The future wire remains an internal vendor-neutral envelope described in
FUTURE-PROVIDER.md. Official current vendor translation, token enforcement, admitted
transport, authorized operator/access, and no-retry verification remain future work.

No new placeholder is added here. Future authored mode still requires exactly:
<PLACEHOLDER_MODEL_PIN>, <PLACEHOLDER_API_KEY>, <PLACEHOLDER_PROVIDER_BASE_URL>.
Source locations remain future.py MODEL/KEY/ENDPOINT and ActivationConfig defaults.
Parent-owned integration/test files must record their own exact placeholder locations.
Developer fixture evidence does not establish independent/clinical/held-out acceptance.
