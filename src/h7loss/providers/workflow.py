"""One accounting owner per workflow attempt; no implicit provider activation."""
from __future__ import annotations

import json
from typing import Any

from h7loss.ledger import Ledger, LedgerError
from .ports import AnthropicProvider, MockProvider, OpenAICompatibleProvider, ProviderError
from .future import (ActivationConfig, FutureProvider, _contains_text, _validate,
                     bounded_json)


def describe_provider(provider: Any, ledger: Ledger) -> str:
    """Validate explicit provider identity and configuration without dispatching."""
    if type(ledger) is not Ledger:
        raise ProviderError("same explicit lifetime Ledger required")
    if type(provider) is MockProvider:
        return "authored_mock"
    if type(provider) not in (AnthropicProvider, OpenAICompatibleProvider):
        raise ProviderError("LIVE_DISPATCH_REFUSED: unsupported workflow provider")
    if provider._ledger is not ledger:
        raise ProviderError("same explicit lifetime Ledger required")
    config = provider._config
    if type(config) is not ActivationConfig:
        raise ProviderError("LIVE_DISPATCH_REFUSED: explicit activation required")
    _validate(config, provider._transport, ledger, config.model)
    return "authored_fake_wire" if config.mode == "authored_fake" else "unverified_live_wire"


def _history(ledger: Ledger, attempt_id: str) -> dict | None:
    return next((row for row in ledger.report()["attempts"]
                 if row["attempt_id"] == attempt_id), None)


def _record_history(attempt: dict, row: dict | None, *, previous: bool) -> None:
    if row is None:
        return
    attempt["ledger_dispatch_state"] = "dispatched" if row["dispatched"] else "not_dispatched"
    attempt["reservation_state"] = row["usage_state"]
    attempt["usage_state"] = row["usage_state"]
    attempt["reserved_micro_usd"] = row["reserved"]
    attempt["actual_micro_usd"] = row["actual"]
    attempt["ledger_provenance"] = json.loads(row["provenance"])
    if previous:
        attempt["previously_dispatched"] = bool(row["dispatched"])
        attempt["previous_attempt"] = {
            "dispatched": bool(row["dispatched"]), "usage_state": row["usage_state"],
            "reserved": row["reserved"], "actual": row["actual"],
            "provenance": json.loads(row["provenance"])}


def dispatch_attempt(provider: Any, ledger: Ledger, *, attempt_id: str, liability: int,
                     provenance: dict, messages: list[dict[str, str]], schema: dict,
                     model: str, max_output_chars: int) -> dict:
    """Return one local attempt, including refusals; never retry or change its ID.

    Mock accounting belongs here. FutureProvider owns its own accounting, called
    unbound exactly once. A malformed model text with known billing remains an
    ordinary response for the workflow's existing bounded repair policy.
    """
    attempt: dict[str, Any] = {
        "attempt_id": attempt_id if type(attempt_id) is str else None, "provenance": None,
        "incoming_provenance": None, "max_liability_micro_usd": liability if type(liability) is int else None,
        "dispatch_state": "not_dispatched", "previously_dispatched": False,
        "dispatch_occurred_this_call": False, "usage_micro_usd": None}
    result = {"outcome": "refused", "attempt": attempt, "response": None,
              "error": None, "stop_required": True}
    prior = None
    is_future = type(provider) in (AnthropicProvider, OpenAICompatibleProvider)
    try:
        # Snapshot history even when this invocation is refused by input/config gates.
        if type(ledger) is Ledger and type(attempt_id) is str:
            prior = _history(ledger, attempt_id)
            _record_history(attempt, prior, previous=True)
        if (type(attempt_id) is not str or not attempt_id.strip() or len(attempt_id) > 256
                or type(liability) is not int or not 0 <= liability <= 40_000_000
                or type(max_output_chars) is not int or not 0 < max_output_chars <= 1_048_576
                or type(provenance) is not dict or not provenance):
            raise ProviderError("explicit bounded attempt identity, liability and provenance required")
        # Isolate incoming provenance from provider/caller mutation and bound all inputs.
        incoming = json.loads(bounded_json(provenance))
        bounded_json({"messages": messages, "schema": schema, "model": model})
        attempt.update(provenance=incoming, incoming_provenance=incoming)
        if type(ledger) is not Ledger:
            raise ProviderError("same explicit lifetime Ledger required")
        if is_future and type(provider._config) is ActivationConfig:
            # Check before activation gates so even refused diagnostics cannot echo keys.
            key = provider._config.api_key
            if type(key) is str and key and (_contains_text(incoming, key) or key in attempt_id):
                attempt.update(provenance={"redacted": True}, incoming_provenance={"redacted": True},
                               attempt_id=None if key in attempt_id else attempt_id)
                raise ProviderError("credential overlaps workflow metadata")
        evidence = describe_provider(provider, ledger)
        attempt["evidence_class"] = evidence
        if is_future:
            response = FutureProvider.complete(
                provider, messages, schema, model,
                {"attempt_id": attempt_id, "max_output_chars": max_output_chars,
                 "max_liability_micro_usd": liability, "workflow_provenance": incoming})
            # Standalone future API preserves its original wire-body hash. Workflows
            # have always named the model-text hash raw_output_sha256.
            response = dict(response)
            response["wire_response_sha256"] = response.get("wire_response_sha256", response.get("raw_output_sha256"))
            response["raw_output_sha256"] = response.get("raw_text_sha256")
        else:
            reservation = ledger.reserve(attempt_id, liability, incoming)
            attempt["reservation_state"] = reservation["usage_state"]
            ledger.mark_dispatch(attempt_id)
            attempt.update(dispatch_state="dispatched", dispatch_occurred_this_call=True)
            try:
                # Preserve MockProvider capture-method compatibility for local tests.
                response = provider.complete(messages, schema, model,
                                             {"max_output_chars": max_output_chars})
                if type(response) is not dict:
                    raise ProviderError("malformed mock response")
            except Exception:
                ledger.settle(attempt_id, None, {"provider_exception": "mock_provider_failure"})
                raise ProviderError("mock provider failure; reservation retained") from None
            response = dict(response)
            failed = response.get("outcome") in {"timeout", "unknown_usage", "cap_exceeded", "error"}
            unknown = response.get("usage_micro_usd") is None
            if failed or unknown:
                # An explicit known mock fee remains a known fee even on a cap;
                # unknown usage remains None and retains the reservation.
                response["stop_required"] = True
            settlement = ledger.settle(attempt_id, response.get("usage_micro_usd"),
                                       {"raw_output_sha256": response.get("raw_output_sha256"),
                                        "mock_fixture_index": response.get("fixture_index"),
                                        "outcome": response.get("outcome")})
            response["usage_state"] = settlement["usage_state"]
            response["evidence_class"] = evidence
            response["stop_required"] = bool(response.get("stop_required") or settlement["usage_state"] == "liability_breach")
        attempt.update(response)
        _record_history(attempt, _history(ledger, attempt_id), previous=False)
        attempt["dispatch_occurred_this_call"] = True
        attempt["dispatch_state"] = "dispatched"
        attempt["max_liability_micro_usd"] = liability
        result["response"] = response
        stopped = bool(response.get("stop_required") or response.get("usage_micro_usd") is None)
        result.update(outcome="error" if stopped else "ok", stop_required=stopped,
                      error=response.get("error") if stopped else None)
        if stopped and result["error"] is None:
            result["error"] = "unknown_usage_or_provider_failure"
    except (ProviderError, LedgerError, ValueError, TypeError, UnicodeError, RecursionError):
        # No raw exception text: external adapters may include sensitive content.
        row = _history(ledger, attempt_id) if type(ledger) is Ledger and type(attempt_id) is str else None
        _record_history(attempt, row, previous=False)
        newly_dispatched = bool(row and row["dispatched"] and not (prior and prior["dispatched"]))
        attempt["dispatch_occurred_this_call"] = newly_dispatched
        attempt["dispatch_state"] = "dispatched" if newly_dispatched else "not_dispatched"
        result.update(outcome="error" if newly_dispatched else "refused",
                      error="provider_or_ledger_refused", stop_required=True)
        attempt.update(outcome=result["outcome"], error=result["error"])
    if is_future and type(provider._config) is ActivationConfig:
        key = provider._config.api_key
        if type(key) is str and key:
            # Includes diagnostic paths refused before activation/input validation.
            if type(attempt["attempt_id"]) is str and key in attempt["attempt_id"]:
                attempt["attempt_id"] = None
            for name in ("provenance", "incoming_provenance", "ledger_provenance"):
                if name in attempt and _contains_text(attempt[name], key):
                    attempt[name] = {"redacted": True}
            previous = attempt.get("previous_attempt")
            if previous and _contains_text(previous["provenance"], key):
                previous["provenance"] = {"redacted": True}
    return result
