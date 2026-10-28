"""Future, vendor-neutral dispatch port. Vendor API compatibility is NOT_VERIFIED.

No SDK, socket, HTTP client, environment lookup, or credential discovery lives here.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

from h7loss.ledger import Ledger, LedgerError
from .ports import ProviderError

MODEL = "<PLACEHOLDER_MODEL_PIN>"
KEY = "<PLACEHOLDER_API_KEY>"
ENDPOINT = "<PLACEHOLDER_PROVIDER_BASE_URL>"
_MAX_BYTES = 1_048_576


@dataclass(frozen=True)
class PriceBound:
    model: str
    config_sha256: str
    price_sha256: str
    max_input_tokens: int
    max_output_tokens: int
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    max_additional_micro_usd: int = 0
    minimum_micro_usd: int = 0
    usage_categories_complete: bool = False


@dataclass(frozen=True)
class ActivationConfig:
    mode: str = "disabled"
    model: str = MODEL
    api_key: str = field(default=KEY, repr=False)
    endpoint: str = ENDPOINT
    operator_id: str = ""
    config_sha256: str = ""
    operator_authorization_sha256: str = ""
    vendor_contract_sha256: str = ""
    input_bound_sha256: str = ""
    live_enabled: bool = False
    price: PriceBound | None = None


@dataclass(frozen=True)
class WireResponse:
    status_code: int
    body: bytes = field(repr=False)


class AuthoredWireTransport:
    """Concrete canned transport; exact type required in authored_fake mode."""

    def __init__(self, responses: Sequence[WireResponse]):
        self._responses = list(responses)
        if any(type(response) is not WireResponse for response in self._responses):
            raise ProviderError("authored WireResponse fixtures required")
        self.captured_requests: list[dict[str, Any]] = []

    def send(self, *, endpoint: str, body: bytes, headers: dict[str, str],
             max_attempts: int, hidden_retries: int) -> WireResponse:
        if headers or max_attempts != 1 or hidden_retries != 0:
            raise ProviderError("authored transport requires no authentication and one attempt")
        self.captured_requests.append({"endpoint": endpoint, "body": body, "headers": {}})
        if not self._responses:
            raise ProviderError("authored wire fixtures exhausted")
        return self._responses.pop(0)


def _json(value: Any) -> bytes:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 10000:
            raise ProviderError("JSON complexity bound exceeded")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ProviderError("JSON string keys required")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ProviderError("finite JSON required")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProviderError("finite bounded JSON required") from None
    if len(encoded) > _MAX_BYTES:
        raise ProviderError("JSON byte bound exceeded")
    return encoded


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_text(value: Any, needle: str) -> bool:
    """Search logical JSON keys/values, independent of reversible wire escaping."""
    pending = [value]
    visited = set()
    count = 0
    while pending:
        item = pending.pop()
        count += 1
        if count > 10000:
            raise ProviderError("JSON complexity bound exceeded")
        if type(item) is str:
            if needle in item:
                return True
        elif type(item) in (dict, list):
            identity = id(item)
            if identity in visited:
                continue
            visited.add(identity)
            if type(item) is dict:
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
    return False


def _integer(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 1_000_000_000_000_000


def _cost(price: PriceBound, input_tokens: int, output_tokens: int, additional: int) -> int:
    # Ceiling each independently billable token category; never use binary floats.
    return max(price.minimum_micro_usd,
               (input_tokens * price.input_micro_usd_per_million + 999999) // 1000000
               + (output_tokens * price.output_micro_usd_per_million + 999999) // 1000000
               + additional)


def _digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def _validate(config: ActivationConfig, transport: Any, ledger: Any, model: str) -> PriceBound:
    if type(config) is not ActivationConfig or type(config.mode) is not str or config.mode not in {"authored_fake", "live"}:
        raise ProviderError("LIVE_DISPATCH_REFUSED: explicit activation required")
    if type(ledger) is not Ledger or transport is None:
        raise ProviderError("explicit transport and same lifetime Ledger required")
    # Inspect no attribute or callback on an arbitrary sender in authored mode.
    if config.mode == "authored_fake" and type(transport) is not AuthoredWireTransport:
        raise ProviderError("authored fake requires exact canned transport")
    if type(model) is not str or any(type(value) is not str for value in (
            config.model, config.api_key, config.endpoint, config.operator_id)):
        raise ProviderError("explicit string activation fields required")
    if (not isinstance(config.operator_id, str) or not config.operator_id.strip()
            or len(config.operator_id) > 256):
        raise ProviderError("explicit bounded operator identity required")
    price = config.price
    if (type(price) is not PriceBound or price.model != model or config.model != model
            or not isinstance(model, str) or not model.strip()
            or price.config_sha256 != config.config_sha256
            or price.usage_categories_complete is not True):
        raise ProviderError("exact model/config complete price bound required")
    for name in ("max_input_tokens", "max_output_tokens", "input_micro_usd_per_million",
                 "output_micro_usd_per_million", "max_additional_micro_usd", "minimum_micro_usd"):
        if not _integer(getattr(price, name)):
            raise ProviderError("bounded nonnegative integer price fields required")
    if price.max_input_tokens == 0 or price.max_output_tokens == 0:
        raise ProviderError("positive token bounds required")
    if not all(_digest(value) for value in (config.config_sha256, price.price_sha256)):
        raise ProviderError("config and price hashes required")
    if config.mode == "authored_fake":
        if (type(transport) is not AuthoredWireTransport or config.model != MODEL
                or config.api_key != KEY or config.endpoint != ENDPOINT):
            raise ProviderError("authored fake requires exact canned transport and named placeholders")
    else:
        if (config.live_enabled is not True or not isinstance(config.operator_id, str)
                or not config.operator_id.strip() or len(config.operator_id) > 256
                or not all(_digest(value) for value in (config.operator_authorization_sha256,
                            config.vendor_contract_sha256, config.input_bound_sha256))):
            raise ProviderError("LIVE_DISPATCH_REFUSED: authorized operator and receipt gates required")
        if any(not isinstance(value, str) or not value.strip() or "<PLACEHOLDER" in value
               for value in (model, config.api_key, config.endpoint)):
            raise ProviderError("LIVE_DISPATCH_REFUSED: explicit nonplaceholder model/key/endpoint required")
        try:
            endpoint = urlsplit(config.endpoint)
            valid = (endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
                     and not endpoint.password and not endpoint.query and not endpoint.fragment)
            endpoint.port
        except ValueError:
            valid = False
        if not valid:
            raise ProviderError("LIVE_DISPATCH_REFUSED: plain HTTPS endpoint required")
        # Credential bytes cannot enter persistent request/provenance metadata.
        if any(config.api_key in value for value in (model, config.operator_id, config.endpoint)):
            raise ProviderError("credential overlaps public metadata")
        if not callable(getattr(transport, "send", None)):
            raise ProviderError("explicit live adapter send method required")
    return price


class FutureProvider:
    kind = "live"
    family = "vendor-neutral"

    def __init__(self, config: ActivationConfig | None = None, transport: Any = None,
                 ledger: Ledger | None = None):
        self._config = config
        self._transport = transport
        self._ledger = ledger

    def complete(self, messages: list[dict[str, str]], schema: dict[str, Any],
                 model: str, budget: dict[str, Any]) -> dict[str, Any]:
        config = self._config
        if config is None:
            raise ProviderError("LIVE_DISPATCH_REFUSED: explicit activation required")
        price = _validate(config, self._transport, self._ledger, model)
        if (type(budget) is not dict or type(budget.get("attempt_id")) is not str
                or not budget["attempt_id"].strip() or len(budget["attempt_id"]) > 256
                or type(budget.get("max_output_chars")) is not int
                or not 0 < budget["max_output_chars"] <= _MAX_BYTES):
            raise ProviderError("explicit bounded attempt_id and max_output_chars required")
        if (type(messages) is not list or not messages or type(schema) is not dict
                or any(type(item) is not dict or set(item) != {"role", "content"}
                       or any(type(value) is not str for value in item.values()) for item in messages)):
            raise ProviderError("explicit messages and response schema required")
        attempt_id = budget["attempt_id"]
        envelope = {"messages": messages, "response_schema": schema, "model": model,
                    "limits": {"max_input_tokens": price.max_input_tokens,
                               "max_output_tokens": price.max_output_tokens,
                               "max_output_chars": budget["max_output_chars"]},
                    "config_sha256": config.config_sha256, "family": self.family}
        body = _json(envelope)
        if _contains_text(envelope, config.api_key) or config.api_key in attempt_id:
            raise ProviderError("credential overlaps request metadata")
        provenance = {"family": self.family, "model": model, "mode": config.mode,
                      "operator_id": config.operator_id, "config_sha256": config.config_sha256,
                      "operator_authorization_sha256": config.operator_authorization_sha256,
                      "vendor_contract_sha256": config.vendor_contract_sha256,
                      "input_bound_sha256": config.input_bound_sha256,
                      "endpoint_sha256": _hash(config.endpoint.encode()),
                      "request_sha256": _hash(body), "price_bound_sha256": _hash(_json(asdict(price)))}
        _json(provenance)  # Validate before the logical-string scan, without logging it.
        if _contains_text(provenance, config.api_key):
            raise ProviderError("credential overlaps provenance")
        liability = _cost(price, price.max_input_tokens, price.max_output_tokens, price.max_additional_micro_usd)
        ledger = self._ledger
        try:
            ledger.reserve(attempt_id, liability, provenance)
            ledger.mark_dispatch(attempt_id)
        except LedgerError:
            raise ProviderError("ledger refused reservation or dispatch") from None
        result = {"outcome": "error", "text": "", "usage_micro_usd": None,
                  "attempt_id": attempt_id, "provenance": provenance, "stop_required": True,
                  "authored_fixture": config.mode == "authored_fake",
                  "evidence_class": "authored_fake_wire" if config.mode == "authored_fake" else "unverified_live_wire",
                  "api_compatibility_verified": False, "hidden_retries": 0,
                  "max_liability_micro_usd": liability, "raw_output_sha256": None}
        receipt: dict[str, Any] = {"api_compatibility_verified": False}
        try:
            headers = {} if config.mode == "authored_fake" else {"Authorization": "Bearer " + config.api_key}
            # Bypass instance-level send replacement in the authored-only path.
            if config.mode == "authored_fake":
                response = AuthoredWireTransport.send(
                    self._transport, endpoint=config.endpoint, body=body, headers=headers,
                    max_attempts=1, hidden_retries=0)
            else:
                response = self._transport.send(
                    endpoint=config.endpoint, body=body, headers=headers,
                    max_attempts=1, hidden_retries=0)
            if type(response) is not WireResponse or type(response.body) is not bytes:
                raise ProviderError("malformed wire response")
            result["raw_output_sha256"] = _hash(response.body)
            receipt["raw_output_sha256"] = result["raw_output_sha256"]
            if type(response.status_code) is not int or not 200 <= response.status_code < 300:
                raise ProviderError("non-2xx wire response")
            if len(response.body) > _MAX_BYTES:
                raise ProviderError("wire output byte cap exceeded")
            value = json.loads(response.body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            _json(value)
            if type(value) is not dict or type(value.get("text")) is not str:
                raise ProviderError("malformed output text")
            text = value["text"]
            if len(text) > budget["max_output_chars"]:
                raise ProviderError("output character cap exceeded")
            usage = value.get("usage")
            known = (type(usage) is dict and set(usage) == {"input_tokens", "output_tokens", "additional_micro_usd", "complete"}
                     and usage["complete"] is True
                     and all(_integer(usage[name]) for name in ("input_tokens", "output_tokens", "additional_micro_usd")))
            if known and (usage["input_tokens"] > price.max_input_tokens
                          or usage["output_tokens"] > price.max_output_tokens
                          or usage["additional_micro_usd"] > price.max_additional_micro_usd):
                raise ProviderError("usage exceeds authorized category bounds")
            if known:
                result["usage_micro_usd"] = _cost(price, usage["input_tokens"], usage["output_tokens"], usage["additional_micro_usd"])
                result.update(outcome="success", stop_required=False)
            else:
                result["error"] = "unknown_or_incomplete_usage"
            result["text"] = text.replace(config.api_key, "[REDACTED]") if config.api_key else text
        except Exception:
            # Do not retain exception text: external adapters can put secrets in it.
            result.update(outcome="error", text="", usage_micro_usd=None, stop_required=True,
                          error="wire_or_output_failure")
        settlement = ledger.settle(attempt_id, result["usage_micro_usd"], receipt)
        result["usage_state"] = settlement["usage_state"]
        return result
