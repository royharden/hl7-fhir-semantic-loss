"""Developer-authored serialized claims only: no wire, credentials or live config."""
import copy
import json
import pytest
from evaluation.common import Refusal, digest, sha256
from evaluation.producer_ports import denominator_records, normalize_producer

MODEL = "<PLACEHOLDER_MODEL_PIN>"  # Serialization fixture only, never dispatched.


def fixture(mode="authored_fake_wire", producer="B2"):
    config = {"model": MODEL}
    files = {"developer-producer": b"original developer source fixture"}
    binding = {"producer": producer, "config_id": "developer-config", "site_id": "developer-site",
               "dictionary_sha256": sha256(b"original developer dictionary"), "config_sha256": digest(config),
               "source_hashes": {name: sha256(raw) for name, raw in files.items()}}
    if producer != "SITE":
        binding.update(case_id="developer-case", raw_sha256=sha256(b"original developer message"))
    native = {"arm_id": "B2" if producer == "B2" else "A", "config_id": binding["config_id"],
              "dictionary_sha256": binding["dictionary_sha256"], "model": MODEL,
              "attempt_number": 0, "authored_fixture": mode != "unverified_live_wire",
              "request_identity_sha256": sha256(b"developer request"),
              "messages_sha256": sha256(b"developer messages"), "initial_messages_sha256": sha256(b"developer initial")}
    if producer == "B2":
        native.update(case_id=binding["case_id"], raw_sha256=binding["raw_sha256"])
        identity = digest(["B2", binding["case_id"], binding["config_id"], binding["raw_sha256"], 0])
    else:
        native["site_id"] = binding["site_id"]
        identity = sha256(json.dumps(["A", binding["site_id"], binding["dictionary_sha256"], binding["config_id"], 0]).encode())
    persisted = copy.deepcopy(native)
    if mode != "authored_mock":
        persisted["provider_wire"] = {"mode": "authored_fake" if mode == "authored_fake_wire" else "live", "model": MODEL}
    text_hash = sha256(b"original developer model text")
    attempt = {"attempt_id": identity, "provenance": persisted, "incoming_provenance": native,
               "ledger_provenance": copy.deepcopy(persisted), "evidence_class": mode,
               "authored_fixture": mode != "unverified_live_wire", "max_liability_micro_usd": 50,
               "dispatch_state": "dispatched", "previously_dispatched": False,
               "dispatch_occurred_this_call": True, "ledger_dispatch_state": "dispatched",
               "outcome": "success", "usage_micro_usd": 3, "usage_state": "settled",
               "reservation_state": "settled", "reserved_micro_usd": 50 if mode == "authored_mock" else 10,
               "actual_micro_usd": 3, "raw_output_sha256": text_hash, "raw_text_sha256": text_hash,
               "wire_response_sha256": sha256(b"original developer wire body"),
               "stop_required": False, "api_compatibility_verified": False, "output_omitted": False}
    payload = {"outcome": "produced", "attempts": [attempt], "evidence_class": mode,
               "runtime_verified": False, "error": None, "stop_required": False}
    if producer == "B2":
        bundle = {"resourceType": "Bundle", "entry": []}
        payload.update(case_id=binding["case_id"], arm_id="B2", config_id=binding["config_id"],
                       raw_sha256=binding["raw_sha256"], bundle=bundle, bundle_sha256=digest(bundle), dispositions=[])
    else:
        payload["proposal"] = {"version": 1, "site_id": binding["site_id"], "dictionary_sha256": binding["dictionary_sha256"], "rules": []}
    return payload, binding, files, config


def normalize(data):
    payload, binding, files, config = data
    return normalize_producer(payload, producer=binding["producer"], binding=binding,
        expected_binding_sha256=digest(binding), source_files=files, config=config)


@pytest.mark.parametrize("mode", ["authored_mock", "authored_fake_wire", "unverified_live_wire"])
def test_claimed_modes_preserved_without_execution_or_semantic_upgrade(mode):
    data = fixture(mode)
    original = copy.deepcopy(data[0])
    result = normalize(data)
    assert result["outcome"] == "completed"
    assert result["evidence_class"] == mode
    assert result["evidence_verification"] == "claimed_unverified"
    assert result["runtime_verified"] is False
    assert result["live_execution_verified"] is False
    assert result["billing_verified"] is False
    assert result["complete_semantic_score"] is False
    assert result["headline_eligible"] is False
    assert result["java_status"] == result["generic_rt_status"] == result["paired_rt_status"] == "not_run"
    assert result["unreported_critical_error"] is result["any_critical_loss"] is None
    assert result["producer_result"] == original == data[0]
    assert result["attempts"] == original["attempts"]
    usage = result["usage"][0]
    assert usage["max_liability_micro_usd"] == usage["caller_max_liability_micro_usd"] == 50
    assert usage["reserved_micro_usd"] == (50 if mode == "authored_mock" else 10)
    assert usage["actual_micro_usd"] == 3
    assert usage["wire_response_sha256"] != usage["raw_output_sha256"] == usage["raw_text_sha256"]
    assert usage["persisted_binding_matches_incoming"] is True


def test_unknown_usage_stops_and_keeps_exposure_unknown():
    data = fixture()
    data[0].update(outcome="error", bundle=None, error="unknown usage", stop_required=True)
    data[0].pop("bundle_sha256")
    data[0]["attempts"][0].update(outcome="error", usage_micro_usd=None, actual_micro_usd=None,
                                  usage_state="unknown", reservation_state="unknown", stop_required=True)
    result = normalize(data)
    assert result["outcome"] == "error" and result["stop_required"] is True
    assert result["usage"][0]["reserved_micro_usd"] == 10
    assert result["usage"][0]["actual_micro_usd"] is None
    assert result["usage"][0]["usage_micro_usd"] is None
    assert len(result["attempts"]) == 1


def test_refused_replay_preserves_old_charge_and_distinct_incoming_history():
    data = fixture()
    payload = data[0]
    attempt = payload["attempts"][0]
    old = copy.deepcopy(attempt["ledger_provenance"])
    old["config_id"] = "prior-config"
    payload.update(outcome="refused", bundle=None, error="ledger refused", stop_required=True)
    payload.pop("bundle_sha256")
    attempt.update(provenance=copy.deepcopy(attempt["incoming_provenance"]), ledger_provenance=old,
        max_liability_micro_usd=5, outcome="refused", usage_micro_usd=None, dispatch_state="not_dispatched",
        previously_dispatched=True, dispatch_occurred_this_call=False, stop_required=True,
        previous_attempt={"dispatched": True, "usage_state": "settled", "reserved": 10, "actual": 3, "provenance": copy.deepcopy(old)})
    original_id = attempt["attempt_id"]
    result = normalize(data)
    assert result["outcome"] == "error"
    history = result["usage"][0]
    assert history["dispatch_state"] == "not_dispatched"
    assert history["ledger_dispatch_state"] == "dispatched" and history["previously_dispatched"] is True
    assert history["dispatch_occurred_this_call"] is False
    assert history["usage_micro_usd"] is None and history["actual_micro_usd"] == 3
    assert history["reserved_micro_usd"] == 10 > history["caller_max_liability_micro_usd"]
    assert history["persisted_binding_matches_incoming"] is False
    assert history["incoming_provenance"]["config_id"] == "developer-config"
    assert history["ledger_provenance"]["config_id"] == "prior-config"
    assert result["attempts"][0]["attempt_id"] == original_id


def test_absent_actual_history_never_defaults_to_cap_or_zero():
    data = fixture("authored_mock")
    attempt = data[0]["attempts"][0]
    for field in ["reserved_micro_usd", "actual_micro_usd", "ledger_provenance", "ledger_dispatch_state", "incoming_provenance", "dispatch_occurred_this_call"]:
        attempt.pop(field)
    data[0].pop("stop_required")  # Accepted older Mock envelope.
    result = normalize(data)
    assert result["outcome"] == "completed"
    assert result["stop_required"] is None
    assert result["usage"][0]["actual_micro_usd"] is None
    assert result["usage"][0]["reserved_micro_usd"] is None
    assert result["usage"][0]["actual_reported"] is result["usage"][0]["reserved_reported"] is False


@pytest.mark.parametrize("mode", ["authored_fake_wire", "unverified_live_wire"])
def test_site_modes_never_enter_message_denominator(mode):
    result = normalize(fixture(mode, "SITE"))
    assert result["record_kind"] == "site_setup" and result["outcome"] == "setup_produced"
    assert result["evidence_class"] == mode
    assert result["eligible_for_scored_denominator"] is False
    with pytest.raises(Refusal):
        denominator_records(result, final_attempt_id="setup-is-not-message")


def test_denominator_retains_claimed_evidence_and_accounting():
    result = normalize(fixture())
    records = denominator_records(result, final_attempt_id="campaign-explicit-slot")
    assert records["attempt"]["evidence_class"] == "authored_fake_wire"
    assert records["attempt"]["usage"][0]["actual_micro_usd"] == 3
    assert records["assessment"]["java_status"] == "not_run"
    assert records["assessment"]["any_critical_loss"] is None


@pytest.mark.parametrize("location,field,value", [
    ("root", "runtime_verified", True), ("root", "evidence_class", "invented_verified"),
    ("root", "stop_required", "false"), ("attempt", "evidence_class", "authored_mock"),
    ("attempt", "authored_fixture", False), ("attempt", "authored_fixture", 1),
    ("attempt", "dispatch_occurred_this_call", False), ("attempt", "reserved_micro_usd", -1),
    ("attempt", "actual_micro_usd", 1.5), ("attempt", "actual_micro_usd", None),
    ("attempt", "max_liability_micro_usd", True), ("attempt", "reserved_micro_usd", 51),
    ("attempt", "raw_text_sha256", sha256(b"different model text")),
    ("attempt", "api_compatibility_verified", True),
    ("provenance", "authored_fixture", False), ("incoming_provenance", "model", "changed"),
    ("ledger_provenance", "authored_fixture", 1),
])
def test_inconsistent_claims_are_unsupported_with_original_retained(location, field, value):
    data = fixture()
    payload = data[0]
    target = payload if location == "root" else payload["attempts"][0] if location == "attempt" else payload["attempts"][0][location]
    target[field] = value
    original = copy.deepcopy(payload)
    result = normalize(data)
    assert result["outcome"] == "unsupported"
    assert result["stop_required"] is True
    assert result["producer_result"] == original
    assert result["runtime_verified"] is False and result["complete_semantic_score"] is False


def test_claimed_live_requires_false_native_fixture_flag():
    data = fixture("unverified_live_wire")
    data[0]["attempts"][0]["incoming_provenance"]["authored_fixture"] = True
    assert normalize(data)["outcome"] == "unsupported"


def test_root_cannot_continue_when_attempt_stopped():
    data = fixture()
    data[0]["attempts"][0]["stop_required"] = True
    assert normalize(data)["outcome"] == "unsupported"


def test_wire_failure_can_retain_only_wire_hash():
    data = fixture()
    data[0].update(outcome="error", bundle=None, error="wire malformed", stop_required=True)
    data[0].pop("bundle_sha256")
    attempt = data[0]["attempts"][0]
    attempt.update(outcome="error", usage_micro_usd=None, actual_micro_usd=None, usage_state="unknown",
                   reservation_state="unknown", raw_output_sha256=None, raw_text_sha256=None,
                   output_omitted=True, stop_required=True)
    result = normalize(data)
    assert result["outcome"] == "error"
    assert result["usage"][0]["wire_response_sha256"] == attempt["wire_response_sha256"]
    assert result["usage"][0]["raw_output_sha256"] is None


def test_historical_live_claim_does_not_relabel_current_fake_or_hide_history():
    data = fixture()
    payload, attempt = data[0], data[0]["attempts"][0]
    prior = copy.deepcopy(attempt["ledger_provenance"])
    prior["authored_fixture"] = False
    prior["provider_wire"]["mode"] = "live"
    attempt.update(provenance=copy.deepcopy(attempt["incoming_provenance"]), ledger_provenance=prior,
                   previous_attempt={"dispatched": True, "usage_state": "settled", "reserved": 10, "actual": 3, "provenance": copy.deepcopy(prior)},
                   previously_dispatched=True, dispatch_occurred_this_call=False, dispatch_state="not_dispatched",
                   outcome="refused", usage_micro_usd=None, stop_required=True)
    payload.update(outcome="refused", bundle=None, error="mode drift refused", stop_required=True)
    payload.pop("bundle_sha256")
    result = normalize(data)
    assert result["outcome"] == "error"
    assert result["evidence_class"] == "authored_fake_wire"
    assert result["usage"][0]["ledger_provenance"]["authored_fixture"] is False
    assert result["usage"][0]["ledger_provenance"]["provider_wire"]["mode"] == "live"
    assert result["usage"][0]["persisted_binding_matches_incoming"] is False
    assert result["live_execution_verified"] is False


def test_explicit_unknown_model_text_hash_cannot_claim_known_text_digest():
    data = fixture()
    data[0]["attempts"][0]["raw_text_sha256"] = None
    assert normalize(data)["outcome"] == "unsupported"


def test_optional_root_fixture_claim_must_agree_with_evidence():
    data = fixture("unverified_live_wire")
    data[0]["authored_fixture"] = True
    assert normalize(data)["outcome"] == "unsupported"


def test_current_request_hashes_cannot_disagree_with_incoming():
    data = fixture()
    data[0]["attempts"][0]["incoming_provenance"]["messages_sha256"] = sha256(b"different message request")
    assert normalize(data)["outcome"] == "unsupported"


def test_mock_label_cannot_claim_current_fake_wire_provenance():
    data = fixture("authored_mock")
    data[0]["attempts"][0]["provenance"]["provider_wire"] = {"mode": "authored_fake", "model": MODEL}
    assert normalize(data)["outcome"] == "unsupported"


def test_persisted_dispatch_cannot_hide_previous_dispatch():
    data = fixture()
    data[0]["attempts"][0].update(previously_dispatched=True, ledger_dispatch_state="not_dispatched")
    assert normalize(data)["outcome"] == "unsupported"


def test_same_identity_replay_detects_changed_request_fingerprint():
    data = fixture()
    payload, attempt = data[0], data[0]["attempts"][0]
    old = copy.deepcopy(attempt["ledger_provenance"])
    incoming = copy.deepcopy(attempt["incoming_provenance"])
    incoming["request_identity_sha256"] = sha256(b"new onboarding or request limits")
    incoming["messages_sha256"] = sha256(b"new onboarding messages")
    attempt.update(provenance=copy.deepcopy(incoming), incoming_provenance=incoming,
                   ledger_provenance=old, previous_attempt={"dispatched": True, "usage_state": "settled", "reserved": 10, "actual": 3, "provenance": copy.deepcopy(old)},
                   previously_dispatched=True, dispatch_occurred_this_call=False, dispatch_state="not_dispatched",
                   outcome="refused", usage_micro_usd=None, stop_required=True)
    payload.update(outcome="refused", bundle=None, error="request drift refused", stop_required=True)
    payload.pop("bundle_sha256")
    result = normalize(data)
    assert result["outcome"] == "error"
    history = result["usage"][0]
    assert history["incoming_provenance"]["config_id"] == history["ledger_provenance"]["config_id"]
    assert history["persisted_binding_matches_incoming"] is False
    assert history["incoming_provenance"]["request_identity_sha256"] != history["ledger_provenance"]["request_identity_sha256"]
    assert result["attempts"][0]["attempt_id"] == attempt["attempt_id"]


def test_new_wire_class_requires_explicit_incoming_record():
    data = fixture()
    data[0]["attempts"][0].pop("incoming_provenance")
    assert normalize(data)["outcome"] == "unsupported"


@pytest.mark.parametrize("change", ["source_bytes", "model_config", "price_config"])
def test_frozen_source_and_config_price_drift_refuse(change):
    data = fixture()
    if change == "source_bytes":
        data[2]["developer-producer"] = b"changed developer producer source"
    elif change == "model_config":
        data[3]["model"] = "changed-negative-model-claim"
    else:
        data[3]["price_bound_sha256"] = sha256(b"changed developer price declaration")
    original = copy.deepcopy(data[0])
    result = normalize(data)
    assert result["outcome"] == "unsupported"
    assert result["producer_result"] == original
    assert result["billing_verified"] is False and result["runtime_verified"] is False


def test_prior_price_and_config_proof_is_not_rewritten_to_new_request():
    data = fixture()
    payload, binding, _, config = data
    config["price_bound_sha256"] = sha256(b"new developer price declaration")
    binding["config_sha256"] = digest(config)
    attempt = payload["attempts"][0]
    old = copy.deepcopy(attempt["ledger_provenance"])
    old["provider_wire"].update(price_bound_sha256=sha256(b"old developer price declaration"), config_sha256=sha256(b"old developer activation config"))
    attempt.update(provenance=copy.deepcopy(attempt["incoming_provenance"]), ledger_provenance=old,
                   previously_dispatched=True, dispatch_occurred_this_call=False, dispatch_state="not_dispatched",
                   outcome="refused", usage_micro_usd=None, stop_required=True,
                   previous_attempt={"dispatched": True, "usage_state": "settled", "reserved": 10, "actual": 3, "provenance": copy.deepcopy(old)})
    payload.update(outcome="refused", bundle=None, error="price/config drift refused", stop_required=True)
    payload.pop("bundle_sha256")
    result = normalize(data)
    assert result["outcome"] == "error"
    assert result["usage"][0]["ledger_provenance"]["provider_wire"] == old["provider_wire"]
    assert result["usage"][0]["ledger_provenance"]["provider_wire"]["price_bound_sha256"] != config["price_bound_sha256"]
    assert result["usage"][0]["usage_micro_usd"] is None
    assert result["usage"][0]["actual_micro_usd"] == 3
    assert result["billing_verified"] is False


def test_unsupported_provider_refusal_never_becomes_success():
    data = fixture()
    data[0].update(evidence_class="unsupported_provider", outcome="refused", bundle=None,
                   attempts=[], error="activation refused", stop_required=True)
    data[0].pop("bundle_sha256")
    result = normalize(data)
    assert result["outcome"] == "unsupported"
    assert result["evidence_class"] == "unsupported_provider"
    assert result["producer_result"]["outcome"] == "refused"
    assert result["attempts"] == [] and result["stop_required"] is True


@pytest.mark.parametrize("breach", [False, True])
def test_known_cap_or_breach_charge_is_preserved_separately_from_ceiling(breach):
    data = fixture("authored_mock")
    payload, attempt = data[0], data[0]["attempts"][0]
    fee = 53 if breach else 3
    state = "liability_breach" if breach else "settled"
    payload.update(outcome="error", bundle=None, error="developer cap/breach", stop_required=True)
    payload.pop("bundle_sha256")
    attempt.update(outcome="success" if breach else "cap_exceeded", usage_micro_usd=fee,
                   actual_micro_usd=fee, reserved_micro_usd=50, usage_state=state,
                   reservation_state=state, stop_required=True, output_omitted=True)
    result = normalize(data)
    assert result["outcome"] == "error" and result["stop_required"] is True
    assert result["usage"][0]["actual_micro_usd"] == fee
    assert result["usage"][0]["caller_max_liability_micro_usd"] == 50
    assert result["billing_verified"] is False
