"""Explicit preregistration freezing; no truth discovery or role signatures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

REQUIRED_HASHES = (
    "metrics", "arms", "thresholds", "prompts", "dsl", "model", "prices",
    "controls", "review_sample", "equivalences", "protocol", "input_manifest",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def prereg_hash(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def validate_prereg(document: Mapping[str, Any]) -> list[str]:
    """Return blocking reasons. Hash shape is not rights or identity approval."""
    problems: list[str] = []
    if document.get("schema_version") != 1:
        problems.append("unsupported_schema_version")
    for key in ("run_id", "frozen_at", "actor"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            problems.append(f"missing_{key}")
    if document.get("heldout_started") is not False:
        problems.append("heldout_already_started_or_unknown")
    hashes = document.get("hashes")
    if not isinstance(hashes, dict):
        problems.append("missing_hashes")
        hashes = {}
    for name in REQUIRED_HASHES:
        value = hashes.get(name)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            problems.append(f"missing_or_invalid_hash:{name}")
    stats = document.get("statistics", {})
    if not isinstance(stats, dict):
        stats = {}
    for key, expected in (("resampling_unit", "site"), ("resamples", 10_000),
                          ("quantile", "linear-(n-1)*p"), ("interval", .95)):
        if stats.get(key) != expected:
            problems.append(f"unfrozen_statistics:{key}")
    if type(stats.get("seed")) is not int:
        problems.append("missing_integer_seed")
    design = document.get("design_disposition")
    if not isinstance(design, dict) or type(design.get("descriptive_only")) is not bool:
        problems.append("missing_design_disposition")
    if document.get("evidence_kind") not in {"authored_fixture", "offline_dev"}:
        problems.append("invalid_preseal_evidence_kind")
    try:
        canonical_bytes(document)
    except (TypeError, ValueError):
        problems.append("noncanonical_json_value")
    return problems


def freeze_prereg(document: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    """Create once at caller-selected path; an existing freeze is never replaced.

    This records the supplied actor without attesting that actor's identity.
    A later design change requires a new path/version before held-out starts.
    """
    problems = validate_prereg(document)
    if problems:
        raise ValueError("preregistration refused: " + ", ".join(problems))
    data = canonical_bytes(document)
    with destination.open("xb") as stream:
        stream.write(data + b"\n")
    return {"status": "frozen", "sha256": hashlib.sha256(data).hexdigest(),
            "file_sha256": hashlib.sha256(data + b"\n").hexdigest(),
            "destination": str(destination), "dispatch_authorized": False,
            "independent_review": "pending"}
