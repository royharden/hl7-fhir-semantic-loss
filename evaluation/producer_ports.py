"""Normalize accepted producer serialization only; never dispatch or infer truth.

Legacy serialization and Round2-017 declared workflow-provider claims are supported.
Final producer/adapter source bytes must be explicitly pinned by the caller.
Caller supplies pinned source bytes/config and an externally frozen binding hash.
No producer imports, ledger creation, callbacks, path discovery or model calls.
"""
import json
from .common import Refusal, digest, require_hash, sha256

PRODUCERS = {"B0": {"mapped", "partial", "refused", "error"},
             "B2": {"produced", "refused", "error"}, "DSL": {"ok", "error"},
             "SITE": {"produced", "refused", "error"}}
AVAILABLE = {"B0": {"mapped", "partial"}, "B2": {"produced"}, "DSL": {"ok"}, "SITE": {"produced"}}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise Refusal("explicit " + name + " required")
    return value


def _copy(value):
    # Exact producer JSON value is retained without rewriting identities/text.
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _binding(binding, expected_binding_sha256, source_files, config, producer):
    if not isinstance(binding, dict) or binding.get("producer") != producer:
        raise Refusal("explicit producer binding required")
    if digest(binding) != require_hash(expected_binding_sha256):
        raise Refusal("normalization binding drift")
    if not isinstance(source_files, dict) or not source_files:
        raise Refusal("explicit producer/adapter source bytes required")
    if any(not isinstance(k, str) or not k or not isinstance(v, bytes) for k, v in source_files.items()):
        raise Refusal("source inventory requires logical names and bytes")
    hashes = {name: sha256(value) for name, value in sorted(source_files.items())}
    if binding.get("source_hashes") != hashes or binding.get("config_sha256") != digest(config):
        raise Refusal("configured source/config bytes mismatch")
    _text(binding.get("config_id"), "config_id")
    _text(binding.get("site_id"), "site_id")
    require_hash(binding.get("dictionary_sha256"))
    if producer != "SITE":
        _text(binding.get("case_id"), "schedule case_id")
        require_hash(binding.get("raw_sha256"))
    if producer in {"B2", "SITE"}:
        if not isinstance(config, dict):
            raise Refusal("model config object required")
        _text(config.get("model"), "model")
    return hashes


EVIDENCE_MODES = {"authored_mock": True, "authored_fake_wire": True, "unverified_live_wire": False}
STATES = {"reserved", "settled", "unknown", "liability_breach"}


def _money(value, name):
    if value is not None and (type(value) is not int or value < 0):
        raise Refusal(name + " must be nonnegative integer microUSD or unknown")
    return value


def _history_provenance(value):
    """Historical identity may differ on refused replay; never rewrite it."""
    if not isinstance(value, dict):
        raise Refusal("persisted provenance object required")
    if "authored_fixture" in value and type(value["authored_fixture"]) is not bool:
        raise Refusal("persisted authored_fixture must be bool")
    wire = value.get("provider_wire")
    if wire is not None:
        if not isinstance(wire, dict) or wire.get("mode") not in {"authored_fake", "live"}:
            raise Refusal("persisted wire mode malformed")
        if value.get("authored_fixture") is not (wire["mode"] == "authored_fake"):
            raise Refusal("persisted wire/fixture claims disagree")
        if "model" in wire and wire["model"] != value.get("model"):
            raise Refusal("wire/native model claims disagree")
    return _copy(value)


def _attempts(payload, producer, binding, config, evidence):
    attempts = payload.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > 2:
        raise Refusal("all producer attempts, bounded initial+repair, required")
    seen, usage = set(), []
    arm = "B2" if producer == "B2" else "A"
    fixture = EVIDENCE_MODES[evidence]
    for number, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise Refusal("attempt object required")
        identity = require_hash(attempt.get("attempt_id"))
        if identity in seen:
            raise Refusal("duplicate producer attempt")
        seen.add(identity)
        provenance = attempt.get("provenance")
        if not isinstance(provenance, dict):
            raise Refusal("attempt provenance required")
        expected = {"arm_id": arm, "config_id": binding["config_id"],
                    "dictionary_sha256": binding["dictionary_sha256"], "model": config["model"],
                    "attempt_number": number, "authored_fixture": fixture}
        if producer == "B2":
            expected.update(case_id=binding["case_id"], raw_sha256=binding["raw_sha256"])
        else:
            expected["site_id"] = binding["site_id"]
        if "attempt_number" in attempt and (type(attempt["attempt_number"]) is not int or attempt["attempt_number"] != number):
            raise Refusal("producer repair identity mismatch")
        for claim in (provenance, attempt.get("incoming_provenance", provenance)):
            if not isinstance(claim, dict) or any(type(claim.get(k)) is not type(v) or claim.get(k) != v for k, v in expected.items()):
                raise Refusal("incoming/native identity/config/dictionary/fixture drift")
            for key in ("request_identity_sha256", "messages_sha256", "initial_messages_sha256"):
                require_hash(claim.get(key))
            _history_provenance(claim)
        incoming_reported = "incoming_provenance" in attempt
        if evidence != "authored_mock" and not incoming_reported:
            raise Refusal("wire workflow requires explicit incoming provenance")
        incoming = attempt.get("incoming_provenance", provenance)
        if any(provenance[k] != incoming[k] for k in ("request_identity_sha256", "messages_sha256", "initial_messages_sha256")):
            raise Refusal("incoming/native request hash claims disagree")
        if "incoming_provenance" in attempt and "provider_wire" in incoming:
            raise Refusal("incoming workflow provenance cannot supply provider_wire")
        if "provider_wire" in provenance:
            expected_mode = "authored_fake" if evidence == "authored_fake_wire" else "live" if evidence == "unverified_live_wire" else None
            if provenance["provider_wire"]["mode"] != expected_mode:
                raise Refusal("current wire mode and root evidence disagree")
        if "evidence_class" in attempt and attempt["evidence_class"] != evidence:
            raise Refusal("attempt/root evidence classes disagree")
        if "authored_fixture" in attempt and (type(attempt["authored_fixture"]) is not bool or attempt["authored_fixture"] is not fixture):
            raise Refusal("producer evidence/fixture claims disagree")
        if attempt.get("dispatch_state") not in {"not_dispatched", "dispatched"}:
            raise Refusal("explicit invocation dispatch state required")
        for flag in ("previously_dispatched", "dispatch_occurred_this_call", "stop_required", "output_omitted"):
            if flag in attempt and type(attempt[flag]) is not bool:
                raise Refusal("malformed attempt boolean: " + flag)
        if "dispatch_occurred_this_call" in attempt and attempt["dispatch_occurred_this_call"] != (attempt["dispatch_state"] == "dispatched"):
            raise Refusal("invocation dispatch claims disagree")
        if "ledger_dispatch_state" in attempt and attempt["ledger_dispatch_state"] not in {"not_dispatched", "dispatched"}:
            raise Refusal("malformed persisted dispatch state")
        liability = attempt.get("max_liability_micro_usd")
        if type(liability) is not int or not 0 <= liability <= 40_000_000:
            raise Refusal("integer lifetime-cap-bounded caller ceiling required")
        for field in ("usage_micro_usd", "reserved_micro_usd", "actual_micro_usd"):
            if field in attempt:
                _money(attempt[field], field)
        if "actual_micro_usd" in attempt:
            actual, reserved, state = attempt["actual_micro_usd"], attempt.get("reserved_micro_usd"), attempt.get("usage_state")
            if state in {"reserved", "unknown"} and actual is not None:
                raise Refusal("unsettled history cannot claim known actual cost")
            if state in {"settled", "liability_breach"} and actual is None:
                raise Refusal("settled history requires reported actual cost")
            if actual is not None and reserved is not None and state in {"settled", "liability_breach"}:
                if (actual > reserved) != (state == "liability_breach"):
                    raise Refusal("settlement/breach amounts disagree")
            if attempt.get("dispatch_occurred_this_call") is True and "usage_micro_usd" in attempt and attempt["usage_micro_usd"] != actual:
                raise Refusal("current response usage and persisted settlement disagree")
        if attempt.get("dispatch_occurred_this_call") is True and attempt.get("reserved_micro_usd") is not None and attempt["reserved_micro_usd"] > liability:
            raise Refusal("new reservation exceeds caller ceiling")
        if "outcome" in attempt and attempt["outcome"] not in {"success", "malformed", "timeout", "unknown_usage", "cap_exceeded", "error", "refused"}:
            raise Refusal("unknown producer attempt state")
        for field in ("usage_state", "reservation_state"):
            if field in attempt and attempt[field] not in STATES:
                raise Refusal("unknown persisted accounting state")
        if attempt.get("outcome") in {"timeout", "unknown_usage", "error"} and attempt.get("usage_micro_usd") is not None:
            raise Refusal("unknown/error invocation usage must remain unknown")
        if "api_compatibility_verified" in attempt and attempt["api_compatibility_verified"] is not False:
            raise Refusal("unverified provider cannot assert API verification")
        for field in ("raw_output_sha256", "raw_text_sha256", "wire_response_sha256"):
            if attempt.get(field) is not None:
                require_hash(attempt[field])
        if "raw_text_sha256" in attempt and attempt.get("raw_output_sha256") != attempt["raw_text_sha256"]:
            raise Refusal("workflow model-text hash names disagree")
        persisted = None
        if "ledger_provenance" in attempt:
            persisted = _history_provenance(attempt["ledger_provenance"])
        previous = attempt.get("previous_attempt")
        if previous is not None:
            if not isinstance(previous, dict) or type(previous.get("dispatched")) is not bool or previous.get("usage_state") not in STATES:
                raise Refusal("malformed previous attempt history")
            _money(previous.get("reserved"), "previous reserved")
            _money(previous.get("actual"), "previous actual")
            _history_provenance(previous.get("provenance"))
            if "previously_dispatched" in attempt and attempt["previously_dispatched"] != previous["dispatched"]:
                raise Refusal("previous dispatch claims disagree")
        if attempt.get("previously_dispatched") is True and attempt.get("ledger_dispatch_state") == "not_dispatched":
            raise Refusal("persisted ledger state cannot hide prior dispatch")
        usage.append({"attempt_id": identity, "usage_reported": "usage_micro_usd" in attempt,
                      "usage_micro_usd": attempt.get("usage_micro_usd"),
                      "usage_state": attempt.get("usage_state", "not_reported"),
                      "reservation_state": attempt.get("reservation_state", "not_reported"),
                      "dispatch_state": attempt["dispatch_state"],
                      "previously_dispatched": attempt.get("previously_dispatched"),
                      "dispatch_occurred_this_call": attempt.get("dispatch_occurred_this_call"),
                      "ledger_dispatch_state": attempt.get("ledger_dispatch_state"),
                      "max_liability_micro_usd": liability, "caller_max_liability_micro_usd": liability,
                      "reserved_reported": "reserved_micro_usd" in attempt,
                      "reserved_micro_usd": attempt.get("reserved_micro_usd"),
                      "actual_reported": "actual_micro_usd" in attempt,
                      "actual_micro_usd": attempt.get("actual_micro_usd"),
                      "accounting_scope": "persisted_attempt" if "reserved_micro_usd" in attempt or "actual_micro_usd" in attempt else "not_reported",
                      "incoming_provenance_reported": incoming_reported,
                      "incoming_provenance": _copy(incoming) if incoming_reported else None,
                      "ledger_provenance": persisted, "previous_attempt": _copy(previous),
                      "persisted_binding_matches_incoming": None if persisted is None or not incoming_reported else all(k in persisted and digest(persisted[k]) == digest(v) for k, v in incoming.items()),
                      "raw_output_sha256": attempt.get("raw_output_sha256"),
                      "raw_text_sha256": attempt.get("raw_text_sha256"),
                      "wire_response_sha256": attempt.get("wire_response_sha256"),
                      "stop_required": attempt.get("stop_required"),
                      "billing_verified": False})
    return _copy(attempts), usage


def _normalize_producer(payload, *, producer, binding, expected_binding_sha256, source_files, config):
    """Return a runner-compatible message result OR a separate site-setup record.

    source_files are supplied artifact bytes; caller must obtain them from the
    actual source-pinned runtime closure, not substitute arbitrary claimed files.
    This is hash comparison, never source execution/rights/identity attestation.
    """
    if producer not in PRODUCERS or not isinstance(payload, dict):
        raise Refusal("unsupported serialized producer")
    hashes = _binding(binding, expected_binding_sha256, source_files, config, producer)
    original = _copy(payload)
    payload = original
    outcome = payload.get("outcome")
    if outcome not in PRODUCERS[producer]:
        raise Refusal("unrecognized producer outcome")
    if "error" not in payload or (payload["error"] is not None and not isinstance(payload["error"], str)):
        raise Refusal("explicit nullable producer error required")
    is_output = outcome in AVAILABLE[producer]
    if is_output and payload["error"] is not None:
        raise Refusal("output availability conflicts with producer error")
    attempts, usage = [], []
    evidence = payload.get("evidence_class") if producer in {"B2", "SITE"} else "unverified_construction"
    producer_stop = payload.get("stop_required")
    if "stop_required" in payload and type(producer_stop) is not bool:
        raise Refusal("explicit stop_required must be boolean")
    if producer in {"B2", "SITE"}:
        if evidence not in EVIDENCE_MODES or payload.get("runtime_verified") is not False:
            raise Refusal("supported claimed/unverified evidence classification required")
        if "authored_fixture" in payload and (type(payload["authored_fixture"]) is not bool or payload["authored_fixture"] is not EVIDENCE_MODES[evidence]):
            raise Refusal("root evidence/fixture claims disagree")
        if evidence != "authored_mock" and type(producer_stop) is not bool:
            raise Refusal("wire workflow requires explicit stop_required")
        if is_output and producer_stop is True:
            raise Refusal("output availability conflicts with stop_required")
        if not is_output and producer_stop is False:
            raise Refusal("failed workflow cannot claim continuation")
        attempts, usage = _attempts(payload, producer, binding, config, evidence)
        if is_output and not attempts:
            raise Refusal("produced provider output without retained attempt")
        if producer_stop is False and any(a.get("stop_required") is True for a in attempts):
            raise Refusal("workflow continuation contradicts stopped attempt")
        if is_output and producer_stop is False and any(a.get("usage_micro_usd") is None for a in attempts):
            raise Refusal("workflow output cannot claim continuation on unknown usage")
    result = {"producer": producer, "producer_outcome": outcome, "producer_result": original,
              "producer_result_sha256": digest(original), "binding_sha256": expected_binding_sha256,
              "binding_verified": True, "source_hashes": hashes, "config_sha256": binding["config_sha256"],
              "config_id": binding["config_id"], "site_id": binding["site_id"],
              "dictionary_sha256": binding["dictionary_sha256"], "attempts": attempts, "usage": usage,
              "evidence_class": evidence, "evidence_verification": "claimed_unverified",
              "producer_stop_required": producer_stop, "stop_required": producer_stop,
              "complete_semantic_score": False, "headline_eligible": False,
              "live_execution_verified": False, "billing_verified": False,
              "error": payload["error"], "runtime_verified": False,
              "java_status": "not_run", "generic_rt_status": "not_run", "paired_rt_status": "not_run",
              "unreported_critical_error": None, "any_critical_loss": None,
              "independent_semantic_acceptance": False}
    if producer == "SITE":
        if "proposal" not in payload:
            raise Refusal("explicit nullable site proposal required")
        proposal = payload["proposal"]
        if is_output:
            if not isinstance(proposal, dict) or proposal.get("site_id") != binding["site_id"] or proposal.get("dictionary_sha256") != binding["dictionary_sha256"]:
                raise Refusal("site proposal identity mismatch")
        elif proposal is not None:
            raise Refusal("failed site result cannot carry proposal")
        return {**result, "record_kind": "site_setup", "outcome": "setup_produced" if is_output else "setup_failed",
                "proposal": proposal, "proposal_sha256": digest(proposal) if proposal is not None else None,
                "eligible_for_scored_denominator": False}
    expected_arm = {"B0": "B0", "B2": "B2", "DSL": "A"}[producer]
    if payload.get("arm_id") != expected_arm:
        raise Refusal("producer arm mismatch")
    raw_hash = binding["raw_sha256"]
    expected_case = raw_hash[:16] if producer == "B0" else raw_hash if producer == "DSL" else binding["case_id"]
    if payload.get("case_id") != expected_case:
        raise Refusal("producer case identity mismatch")
    if "raw_sha256" in payload and payload["raw_sha256"] != raw_hash:
        raise Refusal("producer raw hash mismatch")
    if producer == "B2" and (payload.get("config_id") != binding["config_id"] or payload.get("raw_sha256") != raw_hash):
        raise Refusal("B2 configured identity mismatch")
    if producer in {"B0", "DSL"} and is_output and payload.get("dictionary_sha256") != binding["dictionary_sha256"]:
        raise Refusal("producer dictionary identity mismatch")
    if producer == "DSL" and "site_id" in payload and payload["site_id"] != binding["site_id"]:
        raise Refusal("DSL site identity mismatch")
    bundle, dispositions = payload.get("bundle"), payload.get("dispositions")
    if not isinstance(dispositions, list):
        raise Refusal("explicit dispositions required")
    if is_output:
        if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
            raise Refusal("output availability requires embedded Bundle")
        bundle_hash = digest(bundle)
        if producer == "B2" and payload.get("bundle_sha256") != bundle_hash:
            raise Refusal("B2 serialized bundle hash mismatch")
        if producer == "DSL":
            require_hash(payload.get("mapping_sha256"))
    elif bundle is not None:
        raise Refusal("failed result cannot carry a Bundle")
    else:
        bundle_hash = None
    # The original producer case ID is retained; schedule identity is a separate
    # explicit binding, never written back into producer attempts or ledger IDs.
    return {**result, "record_kind": "message", "outcome": "completed" if is_output else "error",
            "case_id": binding["case_id"], "producer_case_id": payload["case_id"], "arm_id": expected_arm,
            "raw_sha256": raw_hash, "bundle": bundle, "bundle_sha256": bundle_hash,
            "output_sha256": bundle_hash, "dispositions": dispositions,
            "output_availability_only": is_output, "eligible_for_scored_denominator": True}


def normalize_producer(payload, *, producer, binding, expected_binding_sha256, source_files, config):
    """Retain finite serialized producer bytes even when normalization refuses.

    Unsupported records remain in runner evidence but are not attributed to a
    scored denominator until source/config/identity binding can be established.
    No new producer call or rewritten attempt identity is authorized by refusal.
    """
    original = _copy(payload)
    try:
        return _normalize_producer(original, producer=producer, binding=binding,
            expected_binding_sha256=expected_binding_sha256, source_files=source_files, config=config)
    except (Refusal, KeyError, TypeError, ValueError, RecursionError) as error:
        return {"record_kind": "unsupported_producer", "producer": producer,
                "outcome": "unsupported", "error": str(error),
                "producer_result": original, "producer_result_sha256": digest(original),
                "attempts": original.get("attempts") if isinstance(original, dict) else None,
                "binding_verified": False, "eligible_for_scored_denominator": False,
                "evidence_class": original.get("evidence_class") if isinstance(original, dict) else None,
                "evidence_verification": "claimed_unverified", "stop_required": True,
                "producer_stop_required": original.get("stop_required") if isinstance(original, dict) else None,
                "complete_semantic_score": False, "headline_eligible": False,
                "live_execution_verified": False, "billing_verified": False,
                "runtime_verified": False, "independent_semantic_acceptance": False}


def denominator_records(normalized, *, final_attempt_id):
    """Wrap one message result; no semantic or validator outcome is inferred."""
    if normalized.get("binding_verified") is not True:
        raise Refusal("denominator attribution requires verified serialized binding")
    if digest(normalized.get("producer_result")) != normalized.get("producer_result_sha256"):
        raise Refusal("retained producer result drift")
    if normalized.get("record_kind") != "message" or normalized.get("eligible_for_scored_denominator") is not True:
        raise Refusal("site setup is never a scored message")
    _text(final_attempt_id, "explicit campaign attempt identity")
    common = {k: normalized[k] for k in ("case_id", "arm_id", "config_id", "raw_sha256", "output_sha256")}
    attempt = {**common, "attempt_id": final_attempt_id, "outcome": normalized["outcome"],
               "producer_result_sha256": normalized["producer_result_sha256"],
               "producer_attempts": normalized["attempts"], "usage": normalized["usage"],
               "binding_sha256": normalized["binding_sha256"], "evidence_class": normalized["evidence_class"],
               "stop_required": normalized.get("stop_required"), "evidence_verification": "claimed_unverified"}
    assessment = {**common, "final_attempt_id": final_attempt_id, "java_status": "not_run",
                  "generic_rt_status": "not_run", "paired_rt_status": "not_run",
                  "unreported_critical_error": None, "any_critical_loss": None}
    return {"attempt": attempt, "assessment": assessment}
