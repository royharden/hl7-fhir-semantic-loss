"""No SDK imports, retries, network, environment or credential discovery."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
from typing import Any


class ProviderError(ValueError):
    """An explicit provider refusal or authored fixture failure."""


class MockProvider:
    """Consume explicit authored response fixtures, one fixture per call.

    Fixtures: outcome success|malformed|timeout|unknown_usage; text is raw output.
    ``usage_micro_usd`` is simulated accounting data, never measured live cost.
    No fallback success and no implicit retry occur when fixtures are exhausted.
    """

    kind = "mock"

    def __init__(self, responses: Sequence[Mapping[str, Any]]):
        self._responses = [deepcopy(dict(response)) for response in responses]
        self._next = 0

    def complete(self, messages: list[dict[str, str]], schema: dict[str, Any],
                 model: str, budget: dict[str, int]) -> dict[str, Any]:
        if not model or not messages or not isinstance(schema, dict):
            raise ProviderError("explicit model/messages/schema required")
        if type(budget.get("max_output_chars")) is not int or budget["max_output_chars"] <= 0:
            raise ProviderError("positive output character bound required")
        if self._next >= len(self._responses):
            raise ProviderError("authored mock fixtures exhausted")
        fixture_index = self._next
        self._next += 1
        response = deepcopy(self._responses[fixture_index])
        outcome = response.get("outcome")
        if outcome not in {"success", "malformed", "timeout", "unknown_usage"}:
            raise ProviderError("unsupported authored mock outcome")
        text = response.get("text", "")
        if not isinstance(text, str):
            raise ProviderError("mock response text must be a string")
        usage = response.get("usage_micro_usd", 0)
        if usage is not None and (type(usage) is not int or usage < 0):
            raise ProviderError("mock usage must be nonnegative integer microUSD or unknown")
        if outcome in {"timeout", "unknown_usage"}:
            usage = None
        raw_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if len(text) > budget["max_output_chars"]:
            return {"outcome": "cap_exceeded", "text": "", "usage_micro_usd": usage,
                    "authored_fixture": True, "fixture_index": fixture_index,
                    "raw_output_sha256": raw_hash, "raw_output_chars": len(text),
                    "output_omitted": True, "hidden_retries": 0, "latency_ms": None,
                    "error": "mock output exceeds bound"}
        return {"outcome": outcome, "text": text, "usage_micro_usd": usage,
                "authored_fixture": True, "fixture_index": fixture_index,
                "raw_output_sha256": raw_hash, "raw_output_chars": len(text),
                "output_omitted": False,
                "latency_ms": None, "hidden_retries": 0}


# Imported after ProviderError to keep the port's public exception stable.
from .future import FutureProvider


class AnthropicProvider(FutureProvider):
    """Explicit future activation only; vendor API compatibility unverified."""

    family = "anthropic"


class OpenAICompatibleProvider(FutureProvider):
    """Explicit future activation only; vendor API compatibility unverified."""

    family = "openai_compatible"
