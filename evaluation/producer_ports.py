"""Normalize accepted producer serialization only; never dispatch or infer truth.

Source traced at accepted master 0edf825 (DL1 d77daaa / DL2 4e6d300).
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


def _attempts(payload, producer, binding, config):
    attempts = payload.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > 2:
        raise Refusal("all producer attempts, bounded initial+repair, required")
    seen, usage = set(), []
    arm = "B2" if producer == "B2" else "A"
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
                    "attempt_number": number, "authored_fixture": True}
        if producer == "B2":
            expected.update(case_id=binding["case_id"], raw_sha256=binding["raw_sha256"])
            if type(attempt.get("attempt_number")) is not int or attempt["attempt_number"] != number:
                raise Refusal("producer repair identity mismatch")
        else:
            expected["site_id"] = binding["site_id"]
        if any(type(provenance.get(k)) is not type(v) or provenance.get(k) != v for k, v in expected.items()):
            raise Refusal("attempt identity/config/dictionary drift")
        for key in ("request_identity_sha256", "messages_sha256", "initial_messages_sha256"):
            require_hash(provenance.get(key))
        if attempt.get("dispatch_state") not in {"not_dispatched", "dispatched"}:
            raise Refusal("explicit dispatch state required")
        if "previously_dispatched" in attempt and type(attempt["previously_dispatched"]) is not bool:
            raise Refusal("invalid previous dispatch state")
        liability = attempt.get("max_liability_micro_usd")
        if type(liability) is not int or not 0 <= liability <= 40_000_000:
            raise Refusal("integer lifetime-cap-bounded liability required")
        if "usage_micro_usd" in attempt and attempt["usage_micro_usd"] is not None and (type(attempt["usage_micro_usd"]) is not int or attempt["usage_micro_usd"] < 0):
            raise Refusal("usage must be nonnegative integer microUSD or unknown")
        if "outcome" in attempt and attempt["outcome"] not in {"success", "malformed", "timeout", "unknown_usage", "cap_exceeded", "error", "refused"}:
            raise Refusal("unknown producer attempt state")
        if "usage_state" in attempt and attempt["usage_state"] not in {"settled", "unknown", "liability_breach"}:
            raise Refusal("unknown settlement state")
        if "reservation_state" in attempt and attempt["reservation_state"] not in {"reserved", "settled", "unknown", "liability_breach"}:
            raise Refusal("unknown reservation state")
        if attempt.get("authored_fixture", True) is not True:
            raise Refusal("producer evidence classification mismatch")
        if attempt.get("outcome") in {"timeout", "unknown_usage", "error"} and attempt.get("usage_micro_usd") is not None:
            raise Refusal("failure/unknown usage must not become known zero")
        usage.append({"attempt_id": identity, "usage_reported": "usage_micro_usd" in attempt,
                      "usage_micro_usd": attempt.get("usage_micro_usd"),
                      "usage_state": attempt.get("usage_state", "not_reported"),
                      "reservation_state": attempt.get("reservation_state", "not_reported"),
                      "dispatch_state": attempt["dispatch_state"],
                      "previously_dispatched": attempt.get("previously_dispatched"),
                      "max_liability_micro_usd": liability})
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
    if producer in {"B2", "SITE"}:
        if payload.get("evidence_class") != "authored_mock" or payload.get("runtime_verified") is not False:
            raise Refusal("authored mock/unverified classification required")
        attempts, usage = _attempts(payload, producer, binding, config)
        if is_output and not attempts:
            raise Refusal("produced model fixture without retained attempt")
    result = {"producer": producer, "producer_outcome": outcome, "producer_result": original,
              "producer_result_sha256": digest(original), "binding_sha256": expected_binding_sha256,
              "binding_verified": True, "source_hashes": hashes, "config_sha256": binding["config_sha256"],
              "config_id": binding["config_id"], "site_id": binding["site_id"],
              "dictionary_sha256": binding["dictionary_sha256"], "attempts": attempts, "usage": usage,
              "evidence_class": "authored_mock" if producer in {"B2", "SITE"} else "unverified_construction",
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
               "binding_sha256": normalized["binding_sha256"], "evidence_class": normalized["evidence_class"]}
    assessment = {**common, "final_attempt_id": final_attempt_id, "java_status": "not_run",
                  "generic_rt_status": "not_run", "paired_rt_status": "not_run",
                  "unreported_critical_error": None, "any_critical_loss": None}
    return {"attempt": attempt, "assessment": assessment}
