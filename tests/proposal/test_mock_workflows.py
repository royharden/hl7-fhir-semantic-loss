"""Builder-only authored API regressions; not model quality or independent gold."""

import hashlib
import json
import sys
from copy import deepcopy

import pytest

from h7loss.arms.b2 import map_message
from h7loss.ledger import Ledger
from h7loss.proposal import propose_site
from h7loss.providers import AnthropicProvider, MockProvider, OpenAICompatibleProvider, ProviderError

MODEL = "<PLACEHOLDER_MODEL_PIN>"
OUTPUT = {"bundle": {"resourceType": "Bundle", "type": "collection", "entry": []}, "dispositions": []}


def response(text=None, *, outcome="success", usage=0):
    return {"outcome": outcome, "text": json.dumps(OUTPUT) if text is None else text,
            "usage_micro_usd": usage}


def b2(ledger, responses, **overrides):
    kwargs = {"provider": MockProvider(responses), "ledger": ledger, "case_id": "builder-case",
              "config_id": "builder-config", "model": MODEL}
    kwargs.update(overrides)
    return map_message(b"authored mock source", {"site_id": "builder-site"}, **kwargs)


@pytest.fixture
def ledger(tmp_path):
    store = Ledger(tmp_path / "authored-mock.sqlite")
    yield store
    store.close()


def test_b2_one_syntax_repair_retains_both_attempts(ledger):
    result = b2(ledger, [response("{"), response()])
    assert result["outcome"] == "produced"
    assert len(result["attempts"]) == 2
    assert all(row["dispatch_state"] == "dispatched" for row in result["attempts"])
    assert len(ledger.report()["attempts"]) == 2
    assert result["evidence_class"] == "authored_mock"
    assert result["runtime_verified"] is False
    encoded = json.dumps(result["bundle"], sort_keys=True, separators=(",", ":")).encode()
    assert result["bundle_sha256"] == hashlib.sha256(encoded).hexdigest()


def test_b2_shape_error_never_authorizes_semantic_repair(ledger):
    result = b2(ledger, [response("[]"), response()])
    assert result["outcome"] == "error"
    assert len(result["attempts"]) == len(ledger.report()["attempts"]) == 1
    assert result["bundle"] is None


def test_b2_syntax_repair_exhaustion_is_bounded(ledger):
    result = b2(ledger, [response("{"), response("{"), response()])
    assert result["outcome"] == "error"
    assert len(result["attempts"]) == len(ledger.report()["attempts"]) == 2
    assert result["dispositions"] == []


@pytest.mark.parametrize("drift", [{"model": "authored-different-model"},
    {"onboarding": ["different authored context"]}, {"max_output_chars": 4096}])
def test_request_drift_cannot_buy_a_new_dispatch_slot(ledger, drift):
    first = b2(ledger, [response()])
    second = b2(ledger, [response()], **drift)
    assert first["outcome"] == "produced"
    assert second["outcome"] == "refused"
    assert second["attempts"][0]["attempt_id"] == first["attempts"][0]["attempt_id"]
    assert second["attempts"][0]["dispatch_state"] == "not_dispatched"
    assert len(ledger.report()["attempts"]) == 1


def test_exact_replay_retains_a_refused_attempt_without_dispatch(ledger):
    first = b2(ledger, [response()])
    replay = b2(ledger, [response()])
    assert first["outcome"] == "produced"
    assert replay["outcome"] == "refused"
    assert replay["attempts"][0]["previously_dispatched"] is True
    assert replay["attempts"][0]["dispatch_state"] == "not_dispatched"


@pytest.mark.parametrize("outcome", ["timeout", "unknown_usage"])
def test_unknown_mock_usage_keeps_reserved_liability(ledger, outcome):
    result = b2(ledger, [response(outcome=outcome)], max_liability_micro_usd=7)
    assert result["attempts"][0]["usage_micro_usd"] is None
    assert ledger.report()["held"] == 7
    assert ledger.report()["spent"] == 0
    assert len(result["attempts"]) == 1


def test_capped_mock_preserves_original_utf8_digest(ledger):
    text = "\u03b1" * 20
    result = b2(ledger, [response(text, usage=2)], max_liability_micro_usd=5, max_output_chars=4)
    attempt = result["attempts"][0]
    assert result["outcome"] == "error"
    assert attempt["output_omitted"] is True
    assert attempt["raw_output_chars"] == 20
    assert attempt["raw_output_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert ledger.report()["spent"] == 2  # Authored test accounting, never real spend.


def test_provider_exhaustion_keeps_unknown_liability_and_attempt(ledger):
    result = b2(ledger, [], max_liability_micro_usd=5)
    assert result["outcome"] == "error"
    assert result["attempts"][0]["dispatch_state"] == "dispatched"
    assert result["attempts"][0]["usage_micro_usd"] is None
    assert ledger.report()["held"] == 5


def test_recursive_dictionary_refuses_before_reservation(ledger):
    dictionary = {}
    dictionary["recursive"] = dictionary
    result = map_message(b"authored", dictionary, provider=MockProvider([]), ledger=ledger,
                         case_id="recursive-case", config_id="builder", model=MODEL)
    assert result["outcome"] == "refused"
    assert result["attempts"] == ledger.report()["attempts"] == []


def test_deep_output_never_escapes_refusal_boundary(ledger):
    text = "[" * (sys.getrecursionlimit() + 10) + "0" + "]" * (sys.getrecursionlimit() + 10)
    result = b2(ledger, [response(text), response(text)])
    assert result["outcome"] == "error"
    assert 1 <= len(result["attempts"]) <= 2
    assert len(result["attempts"]) == len(ledger.report()["attempts"])
    assert result["bundle"] is None


@pytest.mark.parametrize("provider", [AnthropicProvider(), OpenAICompatibleProvider()])
def test_live_ports_refuse_without_any_dispatch(ledger, provider):
    with pytest.raises(ProviderError, match="LIVE_DISPATCH_REFUSED"):
        provider.complete([], {}, MODEL, {})
    result = b2(ledger, [], provider=provider)
    assert result["outcome"] == "refused"
    assert result["attempts"] == ledger.report()["attempts"] == []


def test_site_schema_only_repair_and_closed_contract(ledger, dsl_case):
    _raw, dictionary, _rules, _rule, proposal = dsl_case()
    provider = MockProvider([response("{}"), response(json.dumps(proposal()))])
    captures = []
    original = provider.complete

    def capture(messages, schema, model, budget):
        captures.append((deepcopy(messages), deepcopy(schema)))
        return original(messages, schema, model, budget)

    provider.complete = capture
    result = propose_site(dictionary, [], provider=provider, ledger=ledger,
                          config_id="builder-site-config", model=MODEL)
    assert result["outcome"] == "produced"
    assert len(result["attempts"]) == 2
    assert captures[0][1]["additionalProperties"] is False
    assert set(json.loads(captures[1][0][-1]["content"])) == {"schema_errors"}
    assert result["proposal"]["dictionary_sha256"] == proposal()["dictionary_sha256"]


def test_site_legacy_identity_is_explicit_and_does_not_rewrite_dictionary(ledger, dsl_case):
    _raw, dictionary, _rules, _rule, proposal = dsl_case()
    dictionary.pop("site_id")
    before = deepcopy(dictionary)
    result = propose_site(dictionary, [], site_id="dev-01", provider=MockProvider([
        response(json.dumps(proposal()))]), ledger=ledger, config_id="legacy", model=MODEL)
    assert result["outcome"] == "produced"
    assert dictionary == before
    assert "site_id" not in dictionary


def test_site_identity_mismatch_refuses_before_reservation(ledger, dsl_case):
    _raw, dictionary, *_ = dsl_case()
    result = propose_site(dictionary, [], site_id="other-site", provider=MockProvider([]),
                          ledger=ledger, config_id="builder", model=MODEL)
    assert result["outcome"] == "refused"
    assert result["attempts"] == ledger.report()["attempts"] == []


def test_b2_and_site_share_lifetime_capacity(tmp_path, dsl_case):
    store = Ledger(tmp_path / "shared-builder.sqlite", cap_micro_usd=10)
    try:
        b2(store, [response(outcome="unknown_usage")], max_liability_micro_usd=6)
        _raw, dictionary, *_ = dsl_case()
        site = propose_site(dictionary, [], provider=MockProvider([]), ledger=store,
                            config_id="site-cap", model=MODEL, max_liability_micro_usd=6)
        assert site["outcome"] == "refused"
        assert site["attempts"][0]["dispatch_state"] == "not_dispatched"
        assert store.report()["held"] == 6
        assert len(store.report()["attempts"]) == 1
    finally:
        store.close()
