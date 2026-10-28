"""Authored in-memory wire regressions, never live API or credential acceptance."""

import hashlib
import json

import pytest

from h7loss.ledger import Ledger
from h7loss.arms.b2 import map_message
from h7loss.proposal import propose_site
from h7loss.providers import future as future_module
from h7loss.providers import (
    ActivationConfig, AnthropicProvider, AuthoredWireTransport, OpenAICompatibleProvider,
    PriceBound, ProviderError, WireResponse,
)

MODEL = "<PLACEHOLDER_MODEL_PIN>"
KEY = "<PLACEHOLDER_API_KEY>"
ENDPOINT = "<PLACEHOLDER_PROVIDER_BASE_URL>"
MESSAGES = [{"role": "user", "content": "Original authored transport-only input"}]
SCHEMA = {"type": "object", "additionalProperties": False}


def price(**changes):
    values = {"model": MODEL, "config_sha256": "a" * 64, "price_sha256": "b" * 64,
              "max_input_tokens": 100, "max_output_tokens": 50,
              "input_micro_usd_per_million": 1_000_000,
              "output_micro_usd_per_million": 2_000_000,
              "max_additional_micro_usd": 5, "minimum_micro_usd": 0,
              "usage_categories_complete": True}
    values.update(changes)
    return PriceBound(**values)


def activation(**changes):
    values = {"mode": "authored_fake", "model": MODEL, "api_key": KEY,
              "endpoint": ENDPOINT, "operator_id": "builder-unit-test",
              "config_sha256": "a" * 64, "price": price()}
    values.update(changes)
    return ActivationConfig(**values)


def wire_response(*, text='{"authored":"wire-only"}', status=200, usage=True):
    payload = {"text": text}
    if usage:
        payload["usage"] = {"input_tokens": 10, "output_tokens": 4,
                            "additional_micro_usd": 1, "complete": True}
    return WireResponse(status, json.dumps(payload).encode())


@pytest.fixture
def store(tmp_path):
    ledger = Ledger(tmp_path / "authored-wire-only.sqlite")
    yield ledger
    ledger.close()


def complete(provider, *, attempt="builder-wire-1", **budget):
    return provider.complete(MESSAGES, SCHEMA, MODEL,
                             {"attempt_id": attempt, "max_output_chars": 32768, **budget})


@pytest.mark.parametrize("family", [AnthropicProvider, OpenAICompatibleProvider])
def test_authored_wire_serialization_accounts_without_authentication(store, family):
    wire = AuthoredWireTransport([wire_response()])
    result = complete(family(config=activation(), transport=wire, ledger=store))
    assert result["outcome"] == "success"
    assert result["authored_fixture"] is True
    assert result["api_compatibility_verified"] is False
    assert result["stop_required"] is False
    assert result["usage_micro_usd"] == 19
    assert (store.report()["spent"], store.report()["held"]) == (19, 0)
    assert len(wire.captured_requests) == 1
    request = wire.captured_requests[0]
    assert request["endpoint"] == ENDPOINT
    assert request["headers"] == {}
    payload = json.loads(request["body"])
    assert payload["model"] == MODEL
    assert payload["messages"] == MESSAGES
    assert payload["response_schema"] == SCHEMA
    assert KEY not in json.dumps(payload)
    assert KEY not in json.dumps(result)
    assert KEY not in repr(activation())


@pytest.mark.parametrize("family", [AnthropicProvider, OpenAICompatibleProvider])
def test_default_port_still_refuses_before_dispatch(family):
    with pytest.raises(ProviderError, match="LIVE_DISPATCH_REFUSED"):
        complete(family())


@pytest.mark.parametrize("changes", [
    {"mode": "live", "live_enabled": False},
    {"mode": "live", "live_enabled": True},  # All access remains placeholders.
    {"price": None}, {"operator_id": ""}, {"config_sha256": ""},
    {"price": price(usage_categories_complete=False)},
    {"price": price(model="authored-mismatched-model")},
    {"mode": []}, {"price": price(max_input_tokens=True)},
])
def test_missing_or_placeholder_activation_refuses_without_reservation(store, changes):
    wire = AuthoredWireTransport([wire_response()])
    provider = OpenAICompatibleProvider(config=activation(**changes), transport=wire, ledger=store)
    with pytest.raises(ProviderError):
        complete(provider)
    assert store.report()["attempts"] == []
    assert wire.captured_requests == []


def test_authored_mode_rejects_socket_capable_or_arbitrary_transport(store):
    class ForbiddenTransport:
        def send(self, **kwargs):
            pytest.fail("an authored fixture must never call an injected arbitrary sender")

    provider = OpenAICompatibleProvider(config=activation(), transport=ForbiddenTransport(), ledger=store)
    with pytest.raises(ProviderError):
        complete(provider)
    assert store.report()["attempts"] == []


def test_authored_mode_never_evaluates_an_arbitrary_transport_property(store):
    class ForbiddenProperty:
        @property
        def send(self):
            pytest.fail("arbitrary sender properties must not execute in authored mode")

    provider = OpenAICompatibleProvider(config=activation(), transport=ForbiddenProperty(), ledger=store)
    with pytest.raises(ProviderError):
        complete(provider)
    assert store.report()["attempts"] == []


def test_reserve_precedes_the_only_send_and_capacity_failure_never_sends(tmp_path):
    store = Ledger(tmp_path / "wire-cap.sqlite", cap_micro_usd=204)
    wire = AuthoredWireTransport([wire_response()])
    try:
        provider = OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store)
        try:
            result = complete(provider)
        except ProviderError:
            pass
        else:
            assert result["outcome"] == "error"
        assert wire.captured_requests == []
        assert store.report()["attempts"] == []
    finally:
        store.close()


def test_replay_and_request_drift_do_not_create_another_send(store):
    wire = AuthoredWireTransport([wire_response(), wire_response()])
    first = OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store)
    assert complete(first)["outcome"] == "success"
    changed = OpenAICompatibleProvider(config=activation(operator_id="other-builder-unit-label"),
                                       transport=wire, ledger=store)
    for provider in (first, changed):
        try:
            result = complete(provider)
        except ProviderError:
            pass
        else:
            assert result["outcome"] == "error"
    assert len(wire.captured_requests) == 1
    assert len(store.report()["attempts"]) == 1


@pytest.mark.parametrize("response", [
    WireResponse(503, b'{"text":"authored failure"}'),
    WireResponse(200, b"not-json"),
    wire_response(usage=False),
])
def test_wire_failure_or_unknown_usage_retains_full_reservation(store, response):
    wire = AuthoredWireTransport([response])
    result = complete(OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store))
    assert result["outcome"] == "error"
    assert result["usage_micro_usd"] is None
    assert result["stop_required"] is True
    assert len(wire.captured_requests) == 1
    assert (store.report()["spent"], store.report()["held"]) == (0, 205)


def test_output_cap_keeps_raw_digest_and_unknown_billing_hold(store):
    text = "Original authored over-cap text"
    wire = AuthoredWireTransport([wire_response(text=text)])
    result = complete(OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store),
                      max_output_chars=4)
    assert result["outcome"] == "error" and result["stop_required"] is True
    assert result["usage_micro_usd"] is None
    assert store.report()["held"] == 205
    # This neutral wire API hashes raw response-envelope bytes, not MockProvider text.
    assert result["raw_output_sha256"] == hashlib.sha256(wire_response(text=text).body).hexdigest()


def test_placeholder_key_is_not_embedded_in_public_output_or_provenance(store):
    wire = AuthoredWireTransport([wire_response(text="authored echo " + KEY)])
    result = complete(OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store))
    assert KEY not in json.dumps(result)
    assert KEY not in json.dumps(store.report())
    assert KEY not in repr(activation())


def test_malformed_recursive_request_refuses_before_ledger_or_wire(store):
    schema = {}
    schema["self"] = schema
    wire = AuthoredWireTransport([wire_response()])
    provider = OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store)
    with pytest.raises(ProviderError):
        provider.complete(MESSAGES, schema, MODEL, {"attempt_id": "recursive", "max_output_chars": 32768})
    assert store.report()["attempts"] == []
    assert wire.captured_requests == []


def test_same_injected_lifetime_ledger_is_used_across_future_calls(store):
    config = activation()
    wire = AuthoredWireTransport([wire_response(), wire_response()])
    provider = OpenAICompatibleProvider(config=config, transport=wire, ledger=store)
    complete(provider, attempt="builder-wire-one")
    complete(provider, attempt="builder-wire-two")
    assert len(store.report()["attempts"]) == 2
    assert store.report()["spent"] == 38
    assert len(wire.captured_requests) == 2


def test_each_fractional_billing_category_is_rounded_up_independently(store):
    config = activation(price=price(max_input_tokens=1, max_output_tokens=1,
        input_micro_usd_per_million=1, output_micro_usd_per_million=1,
        max_additional_micro_usd=0))
    body = json.dumps({"text": "authored fractional-price fixture", "usage": {
        "input_tokens": 1, "output_tokens": 1, "additional_micro_usd": 0, "complete": True}}).encode()
    wire = AuthoredWireTransport([WireResponse(200, body)])
    result = complete(OpenAICompatibleProvider(config=config, transport=wire, ledger=store))
    assert result["outcome"] == "success"
    assert result["max_liability_micro_usd"] == result["usage_micro_usd"] == 2
    assert store.report()["spent"] == 2


def test_instance_callback_cannot_replace_the_canned_fake_wire(store):
    wire = AuthoredWireTransport([wire_response()])
    wire.send = lambda **kwargs: pytest.fail("instance callback must never be selected")
    result = complete(OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store))
    assert result["outcome"] == "success"
    assert len(wire.captured_requests) == 1


def test_future_fake_port_does_not_bypass_current_mock_only_arm_gate(store):
    wire = AuthoredWireTransport([wire_response()])
    provider = OpenAICompatibleProvider(config=activation(), transport=wire, ledger=store)
    b2_result = map_message(b"authored", {}, provider=provider, ledger=store,
                           case_id="builder-case", config_id="builder-config", model=MODEL)
    site_result = propose_site({"site_id": "builder-site"}, [], provider=provider, ledger=store,
                               config_id="builder-config", model=MODEL)
    assert b2_result["outcome"] == site_result["outcome"] == "refused"
    assert b2_result["attempts"] == site_result["attempts"] == store.report()["attempts"] == []
    assert wire.captured_requests == []


@pytest.mark.parametrize("location", ["schema_value", "schema_key", "operator_id"])
def test_reversible_json_escaping_cannot_bypass_placeholder_exclusion(store, monkeypatch, location):
    """Only the allowed placeholder is used; no invented credential fixture."""
    original = future_module._json

    def equivalent_escaped_json(value):
        return original(value).replace(b"<", b"\\u003c")

    monkeypatch.setattr(future_module, "_json", equivalent_escaped_json)
    config = activation(operator_id="builder-unit-test " + KEY) if location == "operator_id" else activation()
    schema = {KEY: "authored"} if location == "schema_key" else {"description": KEY} if location == "schema_value" else SCHEMA
    wire = AuthoredWireTransport([wire_response()])
    provider = OpenAICompatibleProvider(config=config, transport=wire, ledger=store)
    with pytest.raises(ProviderError, match="credential overlaps"):
        provider.complete(MESSAGES, schema, MODEL, {"attempt_id": "escaping-regression", "max_output_chars": 32768})
    assert store.report()["attempts"] == []
    assert wire.captured_requests == []


@pytest.mark.parametrize("text", ['unit"value', "unit\\path", "unit-caf\u00e9"])
def test_logical_string_search_covers_json_escaped_noncredential_unit_text(text):
    # Ordinary substring-search fixtures: these values are never API keys/config.
    document = {"nested": ["prefix " + text + " suffix"], text: "authored"}
    assert future_module._contains_text(document, text) is True
    assert future_module._contains_text(document, "absent unit pattern") is False
