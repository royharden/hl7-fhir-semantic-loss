"""Builder-authored fake-wire regressions, never independent gold or live evidence."""

import hashlib
import json

import pytest

from h7loss.arms.b2 import map_message
from h7loss.ledger import Ledger
from h7loss.proposal import propose_site
from h7loss.providers import (
    ActivationConfig, AnthropicProvider, AuthoredWireTransport,
    OpenAICompatibleProvider, PriceBound, WireResponse,
)

MODEL = "<PLACEHOLDER_MODEL_PIN>"
KEY = "<PLACEHOLDER_API_KEY>"
ENDPOINT = "<PLACEHOLDER_PROVIDER_BASE_URL>"
BUNDLE = {"bundle": {"resourceType": "Bundle", "type": "collection", "entry": []},
          "dispositions": []}


def activation(**changes):
    price = PriceBound(model=MODEL, config_sha256="a" * 64, price_sha256="b" * 64,
        max_input_tokens=100, max_output_tokens=50,
        input_micro_usd_per_million=1_000_000, output_micro_usd_per_million=2_000_000,
        max_additional_micro_usd=5, usage_categories_complete=True)
    values = dict(mode="authored_fake", model=MODEL, api_key=KEY, endpoint=ENDPOINT,
                  operator_id="builder-unit-test", config_sha256="a" * 64, price=price)
    values.update(changes)
    return ActivationConfig(**values)


def response(text, *, usage=True, status=200):
    payload = {"text": text}
    if usage:
        payload["usage"] = {"input_tokens": 10, "output_tokens": 4,
                            "additional_micro_usd": 1, "complete": True}
    return WireResponse(status, json.dumps(payload).encode())


@pytest.fixture
def ledger(tmp_path):
    store = Ledger(tmp_path / "builder-authored-workflow-wire.sqlite")
    yield store
    store.close()


@pytest.fixture(params=["B2", "site"])
def workflow(request, dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case()
    kind = request.param

    def invoke(provider, ledger, **changes):
        options = dict(provider=provider, ledger=ledger, config_id="builder-bridge-config",
                       model=MODEL, max_liability_micro_usd=205)
        if kind == "B2":
            options.update(case_id="builder-bridge-case", repair_liability_micro_usd=205)
        options.update(changes)
        source = options.pop("dictionary", dictionary)
        onboarding = options.pop("onboarding", [])
        if kind == "B2":
            return map_message(raw, source, onboarding=onboarding, **options)
        return propose_site(source, onboarding, **options)

    return {"kind": kind, "invoke": invoke, "raw": raw, "dictionary": dictionary,
            "text": json.dumps(BUNDLE if kind == "B2" else proposal())}


def configured(family, ledger, responses, **changes):
    wire = AuthoredWireTransport(responses)
    return family(config=activation(**changes), transport=wire, ledger=ledger), wire


def assert_authored(result):
    assert result["evidence_class"] == "authored_fake_wire"
    assert result["runtime_verified"] is False


@pytest.mark.parametrize("family", [AnthropicProvider, OpenAICompatibleProvider])
def test_native_workflow_identity_and_single_accounting_owner(ledger, workflow, family):
    provider, wire = configured(family, ledger, [response(workflow["text"])])
    result = workflow["invoke"](provider, ledger)
    assert result["outcome"] == "produced"
    assert result["stop_required"] is False
    assert_authored(result)
    report = ledger.report()
    assert (report["spent"], report["held"]) == (19, 0)
    assert [event["kind"] for event in report["events"]] == ["reserve", "dispatch", "settled"]
    assert len(report["attempts"]) == len(result["attempts"]) == len(wire.captured_requests) == 1
    row, attempt = report["attempts"][0], result["attempts"][0]
    assert attempt["evidence_class"] == "authored_fake_wire"
    assert attempt["raw_output_sha256"] == hashlib.sha256(workflow["text"].encode()).hexdigest()
    assert attempt["wire_response_sha256"] == hashlib.sha256(response(workflow["text"]).body).hexdigest()
    dictionary_hash = hashlib.sha256(json.dumps(workflow["dictionary"], sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if workflow["kind"] == "B2":
        native = json.dumps(["B2", "builder-bridge-case", "builder-bridge-config",
            hashlib.sha256(workflow["raw"]).hexdigest(), 0], separators=(",", ":"), sort_keys=True)
    else:
        native = json.dumps(["A", "dev-01", dictionary_hash, "builder-bridge-config", 0])
    assert row["attempt_id"] == attempt["attempt_id"] == hashlib.sha256(native.encode()).hexdigest()
    assert row["reserved"] == 205 and row["actual"] == 19
    provenance = json.loads(row["provenance"])
    assert provenance["arm_id"] == ("B2" if workflow["kind"] == "B2" else "A")
    assert provenance["config_id"] == "builder-bridge-config"
    assert provenance["dictionary_sha256"] == dictionary_hash
    assert isinstance(provenance["provider_wire"], dict)
    if workflow["kind"] == "B2":
        assert provenance["case_id"] == "builder-bridge-case"
        assert provenance["raw_sha256"] == hashlib.sha256(workflow["raw"]).hexdigest()
    else:
        assert provenance["site_id"] == "dev-01"
    captured = wire.captured_requests[0]
    assert captured["endpoint"] == ENDPOINT and captured["headers"] == {}
    assert json.loads(captured["body"])["model"] == MODEL
    assert KEY not in json.dumps(result) + json.dumps(report)


def test_replay_preserves_prior_dispatch_but_never_sends_again(ledger, workflow):
    provider, wire = configured(OpenAICompatibleProvider, ledger,
                                [response(workflow["text"]), response(workflow["text"])])
    first = workflow["invoke"](provider, ledger)
    events = ledger.report()["events"]
    replay = workflow["invoke"](provider, ledger)
    assert replay["outcome"] == "refused"
    assert replay["stop_required"] is True
    attempt = replay["attempts"][0]
    assert attempt["attempt_id"] == first["attempts"][0]["attempt_id"]
    assert attempt["dispatch_state"] == "not_dispatched"
    assert attempt["previously_dispatched"] is True
    assert attempt["ledger_dispatch_state"] == "dispatched"
    assert attempt["dispatch_occurred_this_call"] is False
    assert len(wire.captured_requests) == 1
    assert ledger.report()["events"] == events


def test_caller_ceiling_and_computed_reservation_remain_distinct(ledger, workflow):
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response(workflow["text"])])
    result = workflow["invoke"](provider, ledger, max_liability_micro_usd=300)
    assert result["outcome"] == "produced"
    attempt = result["attempts"][0]
    assert attempt["max_liability_micro_usd"] == 300
    assert attempt["reserved_micro_usd"] == 205
    assert attempt["actual_micro_usd"] == 19
    assert len(wire.captured_requests) == 1


def test_one_public_syntax_or_schema_repair_has_two_settlements(ledger, workflow):
    invalid = "{" if workflow["kind"] == "B2" else "{}"
    provider, wire = configured(OpenAICompatibleProvider, ledger,
                                [response(invalid), response(workflow["text"])])
    result = workflow["invoke"](provider, ledger)
    assert result["outcome"] == "produced"
    assert_authored(result)
    assert len(result["attempts"]) == len(wire.captured_requests) == 2
    assert len({attempt["attempt_id"] for attempt in result["attempts"]}) == 2
    report = ledger.report()
    assert (report["spent"], report["held"]) == (38, 0)
    assert [event["kind"] for event in report["events"]] == ["reserve", "dispatch", "settled"] * 2
    if workflow["kind"] == "site":
        repair = json.loads(wire.captured_requests[1]["body"])["messages"][-1]["content"]
        public = json.loads(repair)
        assert set(public) == {"schema_errors"}
        assert public["schema_errors"] == result["attempts"][0]["public_schema_errors"]


@pytest.mark.parametrize("text", ["{", "{}"])
def test_site_raw_and_schema_repairs_use_only_public_errors(ledger, dsl_case, text):
    _raw, dictionary, _rules, _rule, proposal = dsl_case()
    provider, wire = configured(AnthropicProvider, ledger, [response(text), response(json.dumps(proposal()))])
    result = propose_site(dictionary, [], provider=provider, ledger=ledger,
        config_id="builder-site-public-repair", model=MODEL, max_liability_micro_usd=205)
    assert result["outcome"] == "produced"
    repair = json.loads(json.loads(wire.captured_requests[1]["body"])["messages"][-1]["content"])
    assert set(repair) == {"schema_errors"}
    assert repair["schema_errors"] and all(isinstance(code, str) for code in repair["schema_errors"])


@pytest.mark.parametrize("failure", ["unknown_valid", "unknown_malformed", "cap", "refusal"])
def test_unknown_cap_and_refusal_stop_before_repair(ledger, workflow, failure):
    first = response(workflow["text"] if failure == "unknown_valid" else "{", usage=False)
    if failure == "cap":
        first = response("x" * 40_000)
    elif failure == "refusal":
        first = response("{", status=503)
    provider, wire = configured(OpenAICompatibleProvider, ledger, [first, response(workflow["text"])])
    result = workflow["invoke"](provider, ledger)
    assert result["outcome"] != "produced"
    assert result["stop_required"] is True
    assert len(wire.captured_requests) == len(result["attempts"]) == 1
    assert result["attempts"][0]["usage_micro_usd"] is None
    assert (ledger.report()["spent"], ledger.report()["held"]) == (0, 205)


@pytest.mark.parametrize("cap", [0, 204])
def test_caller_cap_cannot_be_replaced_by_provider_price(ledger, workflow, cap):
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response(workflow["text"])])
    result = workflow["invoke"](provider, ledger, max_liability_micro_usd=cap)
    assert result["outcome"] == "refused"
    assert result["stop_required"] is True
    assert wire.captured_requests == []
    assert ledger.report()["attempts"] == []


def test_default_zero_caller_cap_refuses_even_explicit_fake_activation(ledger, workflow):
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response(workflow["text"])])
    options = dict(provider=provider, ledger=ledger, config_id="builder-default-cap", model=MODEL)
    if workflow["kind"] == "B2":
        result = map_message(workflow["raw"], workflow["dictionary"],
                             case_id="builder-default-case", **options)
    else:
        result = propose_site(workflow["dictionary"], [], **options)
    assert result["outcome"] == "refused"
    assert result["stop_required"] is True
    assert wire.captured_requests == ledger.report()["attempts"] == []


def test_b2_repair_uses_its_own_caller_cap(ledger):
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response("{"), response(json.dumps(BUNDLE))])
    result = map_message(b"builder-only input", {"site_id": "builder-site"},
        provider=provider, ledger=ledger, case_id="builder-repair-cap", config_id="builder-config",
        model=MODEL, max_liability_micro_usd=205, repair_liability_micro_usd=204)
    assert result["outcome"] != "produced"
    assert result["stop_required"] is True
    assert len(wire.captured_requests) == 1
    assert len(ledger.report()["attempts"]) == 1
    assert ledger.report()["spent"] == 19


@pytest.mark.parametrize("mode", ["disabled", "live"])
def test_unactivated_or_placeholder_live_workflow_never_sends(ledger, workflow, mode):
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response(workflow["text"])],
                                mode=mode, live_enabled=True)
    result = workflow["invoke"](provider, ledger)
    assert result["outcome"] == "refused"
    assert wire.captured_requests == ledger.report()["attempts"] == []


@pytest.mark.parametrize("family", [AnthropicProvider, OpenAICompatibleProvider])
def test_default_provider_guard_never_reserves(ledger, workflow, family):
    result = workflow["invoke"](family(), ledger)
    assert result["outcome"] == "refused"
    assert ledger.report()["attempts"] == []


def test_equal_database_path_is_not_the_same_ledger_object(ledger, workflow, tmp_path):
    other = Ledger(tmp_path / "builder-authored-workflow-wire.sqlite")
    try:
        provider, wire = configured(OpenAICompatibleProvider, other, [response(workflow["text"])])
        result = workflow["invoke"](provider, ledger)
        assert result["outcome"] == "refused"
        assert wire.captured_requests == ledger.report()["attempts"] == other.report()["attempts"] == []
    finally:
        other.close()


@pytest.mark.parametrize("malformation", ["cycle", "depth", "dictionary_bytes", "onboarding_bytes"])
def test_bounded_context_refuses_before_any_dispatch(ledger, workflow, malformation):
    dictionary = {"site_id": "dev-01"}
    onboarding = []
    if malformation == "cycle":
        dictionary["recursive"] = dictionary
    elif malformation == "depth":
        nested = dictionary
        for _ in range(34):
            nested["child"] = {}
            nested = nested["child"]
    elif malformation == "dictionary_bytes":
        dictionary["oversized"] = "x" * 1_048_577
    else:
        onboarding = ["x" * 1_048_577]
    provider, wire = configured(OpenAICompatibleProvider, ledger, [response(workflow["text"])])
    result = workflow["invoke"](provider, ledger, dictionary=dictionary, onboarding=onboarding)
    assert result["outcome"] == "refused"
    assert wire.captured_requests == ledger.report()["attempts"] == []
