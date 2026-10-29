"""Site-cluster summaries; no expectation creation or population inference."""
from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any


def ratio(numerator: int, denominator: int) -> float | None:
    """An empty denominator is undefined, including 0/0."""
    if (type(numerator) is not int or type(denominator) is not int
            or numerator < 0 or denominator < 0 or numerator > denominator):
        raise ValueError("counts require integers with 0 <= numerator <= denominator")
    return None if denominator == 0 else numerator / denominator


def percentile(values: Sequence[float], probability: float) -> float:
    """Linear interpolation at (n-1)*p; frozen quantile convention."""
    if not values or not 0 <= probability <= 1:
        raise ValueError("nonempty values and probability in [0,1] required")
    ordered = sorted(values)
    if any(not math.isfinite(v) for v in ordered):
        raise ValueError("nonfinite statistic")
    index = (len(ordered) - 1) * probability
    lo = math.floor(index)
    hi = math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def _summary(rows: Sequence[Mapping[str, int]]) -> dict[str, Any]:
    values = [ratio(row["numerator"], row["denominator"]) for row in rows]
    numerator = sum(row["numerator"] for row in rows)
    denominator = sum(row["denominator"] for row in rows)
    macro = None if any(v is None for v in values) else sum(values) / len(values)
    return {"numerator": numerator, "denominator": denominator,
            "pooled": ratio(numerator, denominator), "macro": macro}


def paired_site_bootstrap(
    sites: Mapping[str, Mapping[str, Mapping[str, int]]],
    *, seed: int, resamples: int = 10_000,
    contrast: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Resample sites together for all arms. Contrast is first minus second.

    Each arm row has numerator and denominator for one frozen metric. Never
    pass message rows as sites. Undefined replicates are retained as counts;
    an interval is undefined if any replicate statistic is undefined.
    """
    if not sites or type(seed) is not int or type(resamples) is not int or resamples < 1:
        raise ValueError("sites, integer seed and positive resample count required")
    site_ids = sorted(sites)
    if any(not isinstance(site, str) or not site for site in site_ids):
        raise ValueError("nonempty site identifiers required")
    arms = sorted(sites[site_ids[0]])
    if not arms or any(set(sites[s]) != set(arms) for s in site_ids):
        raise ValueError("all scheduled arms must have a row at every site")
    for site in site_ids:
        for arm in arms:
            row = sites[site][arm]
            if set(row) != {"numerator", "denominator"}:
                raise ValueError("metric row must contain only numerator and denominator")
            ratio(row["numerator"], row["denominator"])
    if contrast is not None and (len(contrast) != 2 or any(a not in arms for a in contrast)):
        raise ValueError("contrast arms must exist")
    point = {a: _summary([sites[s][a] for s in site_ids]) for a in arms}
    draws: dict[str, dict[str, list[float | None]]] = {
        a: {"macro": [], "pooled": []} for a in arms}
    differences: dict[str, list[float | None]] = {"macro": [], "pooled": []}
    rng = random.Random(seed)
    for _ in range(resamples):
        selected = [site_ids[rng.randrange(len(site_ids))] for _ in site_ids]
        sample = {a: _summary([sites[s][a] for s in selected]) for a in arms}
        for a in arms:
            for metric in ("macro", "pooled"):
                draws[a][metric].append(sample[a][metric])
        if contrast is not None:
            for metric in differences:
                left, right = (sample[a][metric] for a in contrast)
                differences[metric].append(None if left is None or right is None else left - right)

    def interval(values: Sequence[float | None]) -> dict[str, Any]:
        defined = [v for v in values if v is not None]
        bounds = None if len(defined) != len(values) else [percentile(defined, .025), percentile(defined, .975)]
        return {"interval_95": bounds, "defined_resamples": len(defined),
                "undefined_resamples": len(values) - len(defined)}

    result: dict[str, Any] = {
        "resampling_unit": "site", "seed": seed, "resamples": resamples,
        "quantile": "linear-(n-1)*p", "point": point,
        "sites": {s: {a: dict(sites[s][a]) for a in arms} for s in site_ids},
        "intervals": {a: {m: interval(v) for m, v in draws[a].items()} for a in arms},
        "population_inference": False,
    }
    if contrast is not None:
        result["contrast"] = {"first_minus_second": list(contrast),
            "point": {m: None if any(point[a][m] is None for a in contrast)
                      else point[contrast[0]][m] - point[contrast[1]][m]
                      for m in differences},
            "intervals": {m: interval(v) for m, v in differences.items()}}
    return result


def design_disposition(sensitivity: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify supplied pre-seal sensitivity estimates; does not estimate power.

    Rows require icc, half_width, power, discordance, basis and evidence_sha256.
    basis is observed_dev or assumed_range. Fractions use 0..1 units.
    """
    required_iccs = {0.0, .05, .10, .20}
    seen: set[float] = set()
    reasons: list[str] = []
    for row in sensitivity:
        for key in ("icc", "half_width", "power", "discordance"):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"invalid sensitivity fraction: {key}")
        if row.get("basis") not in {"observed_dev", "assumed_range"}:
            raise ValueError("sensitivity basis must be explicit")
        digest = row.get("evidence_sha256", "")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("sensitivity evidence hash required")
        seen.add(float(row["icc"]))
        if row["icc"] == .10 and row["half_width"] > .10:
            reasons.append("half_width_at_icc_0.10_exceeds_0.10")
        if row["power"] < .8:
            reasons.append("power_below_0.80")
    if not required_iccs.issubset(seen):
        reasons.append("missing_required_icc_sensitivity")
    return {"descriptive_only": bool(reasons), "reasons": sorted(set(reasons)),
            "meaningful_paired_difference": .10, "population_inference": False,
            "model_quality_from_mock": False,
            "note": "Passing this design screen does not authorize superiority language or dispatch."}
