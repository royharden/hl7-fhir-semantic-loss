# Future provider port — API compatibility NOT_VERIFIED

This source is a future activation boundary, not verified support for either vendor.
No HTTP client, SDK, bundled live transport, environment lookup, credential-file lookup,
retry loop, or database constructor is included. Actual spend remains zero. B2 and site
proposal defaults remain exact-type MockProvider-only. Existing no-argument
AnthropicProvider/OpenAICompatibleProvider.complete calls raise LIVE_DISPATCH_REFUSED.

## Public API

Exports from h7loss.providers:

- Frozen ActivationConfig(mode='disabled', model='<PLACEHOLDER_MODEL_PIN>',
  api_key='<PLACEHOLDER_API_KEY>', endpoint='<PLACEHOLDER_PROVIDER_BASE_URL>',
  operator_id='', config_sha256='', operator_authorization_sha256='',
  vendor_contract_sha256='', input_bound_sha256='', live_enabled=False, price=None).
  Mode is disabled, authored_fake, or live. The key is excluded from dataclass repr.
- Frozen PriceBound(model, config_sha256, price_sha256, max_input_tokens,
  max_output_tokens, input_micro_usd_per_million, output_micro_usd_per_million,
  max_additional_micro_usd=0, minimum_micro_usd=0, usage_categories_complete=False).
- Frozen WireResponse(status_code: int, body: bytes), with body excluded from repr.
- AuthoredWireTransport(responses: Sequence[WireResponse]); captured_requests contains
  dictionaries with endpoint, body (serialized bytes), and headers (empty).
- AnthropicProvider(config=None, transport=None, ledger=None), and the same constructor
  for OpenAICompatibleProvider. complete(messages, schema, model, budget) requires
  budget={'attempt_id': <caller-stable bounded string>, 'max_output_chars': <positive int>}.

The caller injects the same lifetime Ledger used elsewhere. The port never creates,
replaces, resets, or chooses a database. Configuration validation raises ProviderError
before dispatch. Ledger refusal raises a generic ProviderError without exception text.

## Accounting and dispatch

The price model/config must match the activation model/config exactly. Config and price
hashes are 64 hexadecimal characters. Prices and token counts are nonnegative integers;
token caps must be positive and all usage categories explicitly bounded. Liability is:

    max(minimum_micro_usd,
        ceil(max_input_tokens * input_rate / 1000000)
        + ceil(max_output_tokens * output_rate / 1000000)
        + max_additional_micro_usd)

Integer arithmetic implements each ceiling independently. The existing Ledger enforces
its lifetime ceiling. Canonical request, complete price bound, endpoint, mode, model,
operator and receipt hashes bind attempt provenance. Changing them under the same
attempt ID conflicts; a previously dispatched attempt cannot send again. The key is
excluded from request and provenance. No automatic repair/retry exists here.

One reserve and mark_dispatch precede exactly one send. Every supplied transport must
honor send(endpoint=..., body=..., headers=..., max_attempts=1, hidden_retries=0).
This contract is a requirement on a trusted future adapter; injected external code is
not sandboxed or certified by this port. No such live adapter is bundled.

The response body is an authored vendor-neutral envelope:

    {"text":"...","usage":{"input_tokens":0,"output_tokens":0,
       "additional_micro_usd":0,"complete":true}}

Complete usage within every category cap settles using the same integer calculation.
Absent, malformed, or incomplete usage retains the entire reservation and requires stop.
Transport exceptions, non-2xx, malformed JSON/text, output caps, or category-cap excess
return error with stop_required=true and unknown usage, retaining the reservation.
Raw-body SHA256 and caller attempt remain available when a byte response was received;
raw response bytes and exception strings never enter the result or ledger. Errors do
not release liability. Configured key occurrences in output text are redacted, including
in authored placeholder fixtures. Headers never enter the result. Successful results
include usage_micro_usd, usage_state, attempt_id, provenance, raw_output_sha256,
stop_required=false, and api_compatibility_verified=false.

## Serialized request and bounds

Requests are canonical UTF-8 JSON (sorted keys, compact separators, no nonfinite values):

    {"messages":[{"role":"user","content":"..."}],"response_schema":{},
     "model":"<PLACEHOLDER_MODEL_PIN>","limits":{"max_input_tokens":1,
     "max_output_tokens":1,"max_output_chars":100},"config_sha256":"...",
     "family":"anthropic"}

The other family label is openai_compatible. This is an internal envelope, **not** a
claimed Anthropic/OpenAI API payload. JSON depth is capped at 32, visited values at
10000, serialized request and response at 1048576 bytes, output characters at the
explicit cap (at most 1048576). The future adapter must verify official current vendor
documentation, translate this envelope, enforce actual token limits, normalize usage
including every billable category/minimum, and demonstrate the no-retry contract before
compatibility can be admitted. A generic live call carries Authorization: Bearer in
memory to that adapter; this is not a verified vendor authentication layout.

## Activation and placeholder inventory

Authored_fake requires exact type AuthoredWireTransport, not subclasses or user callbacks.
Its class send method is selected directly, so replacing instance.send cannot inject a
callback. It consumes canned WireResponse objects in memory, has no socket implementation,
omits authentication headers entirely, and requires all three exact placeholder values.
Labels are authored_fixture=true, evidence_class=authored_fake_wire, and
api_compatibility_verified=false. Authored fixtures are developer-only evidence.

Live requires explicit live_enabled=true, a nonempty operator_id, valid 64-hex
operator_authorization_sha256/vendor_contract_sha256/input_bound_sha256 receipts, and
nonmissing nonplaceholder model/key/HTTPS endpoint without userinfo, query, or fragment.
It also requires the exact bounded PriceBound and explicit injected transport/Ledger.
No receipt hash authenticates an operator by itself: external authorization remains a
future INT/operator obligation. This source does not authorize any actual live call.

Exact placeholder source locations for INT's handoff inventory:

- src/h7loss/providers/future.py: MODEL and ActivationConfig.model default use
  <PLACEHOLDER_MODEL_PIN>.
- src/h7loss/providers/future.py: KEY and ActivationConfig.api_key default use
  <PLACEHOLDER_API_KEY> (repr excluded).
- src/h7loss/providers/future.py: ENDPOINT and ActivationConfig.endpoint default use
  <PLACEHOLDER_PROVIDER_BASE_URL>.
- This document's API/request/inventory examples repeat only those named placeholders.
- Parent-owned tests/proposal/test_future_provider.py should use only these same three
  placeholders; the parent records its exact test locations in READY.

No vendor docs were retrieved, credentials supplied, live call performed, or compatibility
verified in this source-only task. Runtime014 executed the authored fake-wire and existing proposal suite on the
app-local Python3.12.13 target:133 passed9.80s at source commit40f7916 /
tree5edcfa283bae5a8b76dd38544426eb9faffac7b2. See ROUND2-CHECKS.md for exact
command/artifact hashes. This does not verify actual vendor adapters, authentication,
current pricing/tokenizers, live calls, installed-wheel replay or independent meaning;
all of those admission gates remain pending.


##009C workflow adapter

The later WORKFLOW-PROVIDERS.md seam permits explicit configured ports in B2/site
without duplicate reservation. Caller initial/repair liability caps bound the computed
price before any send; native workflow IDs/top-level provenance remain. Default CLI
behavior stays keyless MockProvider; no future live activation command is granted.
Standalone future raw_output_sha256 remains raw-envelope SHA256, while workflow
raw_output_sha256 is raw model text and wire_response_sha256 keeps the envelope hash.
Actual reserved/settled fields are separate from caller ceilings. Unknown/error stops
before any workflow repair and retains exposure. Runtime016179-pass builder evidence
covers this source bridge; vendor translation/access/admission remains unverified.
