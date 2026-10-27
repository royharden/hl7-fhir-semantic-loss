"""Schedule-first denominator registry; failures never silently disappear.

No inference of outcome truth. The supplied assessment flags must come from
separately admitted semantic scoring, and never from model or validator success.
"""
from .common import Refusal, digest, require_hash

JAVA = {"pass", "fail", "error", "not_run"}
ROUNDTRIP = {"pass", "fail", "error", "not_run", "unsupported"}
OUTCOMES = {"completed", "error", "timeout", "no_output", "unsupported", "skipped"}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise Refusal(f"nonempty {name} required")
    return value


def validate_schedule(schedule):
    """One row per scheduled scored case and arm, onboarding excluded explicitly."""
    if not isinstance(schedule, list) or not schedule:
        raise Refusal("nonempty explicit schedule required")
    seen = set()
    for row in schedule:
        if not isinstance(row, dict):
            raise Refusal("schedule rows must be objects")
        for name in ("case_id", "site_id", "arm_id", "config_id"):
            _text(row.get(name), name)
        require_hash(row.get("raw_sha256"))
        if row.get("namespace") not in {"authored_fixture", "offline_dev", "heldout"}:
            raise Refusal("explicit evidence namespace required")
        if row.get("purpose") not in {"scored", "onboarding"}:
            raise Refusal("explicit scored/onboarding purpose required")
        key = (row["case_id"], row["arm_id"])
        if key in seen:
            raise Refusal("duplicate scheduled case/arm")
        seen.add(key)
    # One raw identity/site/purpose per case across all arms.
    identities = {}
    arms = {}
    for row in schedule:
        identity = tuple(row[k] for k in ("site_id", "raw_sha256", "namespace", "purpose"))
        case = row["case_id"]
        if case in identities and identities[case] != identity:
            raise Refusal("case identity differs across scheduled arms")
        identities[case] = identity
        arms.setdefault(case, set()).add(row["arm_id"])
    if len({frozenset(value) for value in arms.values()}) != 1:
        raise Refusal("every scheduled case must include all scheduled arms")
    return {"schedule_sha256": digest(schedule), "rows": len(schedule)}


def _fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def summarize(schedule, attempts, assessments):
    """Bind final attempts explicitly; retain every attempt including repairs.

    attempt: attempt_id, case_id, arm_id, config_id, raw_sha256, outcome,
    output_sha256 (completed only). assessment: same case/arm/config/raw,
    final_attempt_id, Java/generic/paired status, optional semantic flags.
    Missing assessment or score is unmeasured, never clean. No final attempt
    is selected by recency. No-output/failure rows still occupy scheduled N.
    """
    seal = validate_schedule(schedule)
    if not isinstance(attempts, list) or not isinstance(assessments, list):
        raise Refusal("attempts and assessments must be explicit lists")
    index = {(s["case_id"], s["arm_id"]): s for s in schedule}
    attempt_index = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise Refusal("attempt must be an object")
        attempt_id = _text(attempt.get("attempt_id"), "attempt_id")
        if attempt_id in attempt_index:
            raise Refusal("duplicate attempt id")
        case = _text(attempt.get("case_id"), "case_id")
        arm = _text(attempt.get("arm_id"), "arm_id")
        bound = index.get((case, arm))
        if bound is None or any(attempt.get(k) != bound[k] for k in ("config_id", "raw_sha256")):
            raise Refusal("attempt outside schedule or identity drift")
        if attempt.get("outcome") not in OUTCOMES:
            raise Refusal("unsupported attempt outcome")
        if attempt["outcome"] == "completed":
            require_hash(attempt.get("output_sha256"))
        elif attempt.get("output_sha256") is not None:
            require_hash(attempt["output_sha256"])
        attempt_index[attempt_id] = attempt
    observed = {}
    for assessment in assessments:
        if not isinstance(assessment, dict):
            raise Refusal("assessment must be an object")
        case = _text(assessment.get("case_id"), "case_id")
        arm = _text(assessment.get("arm_id"), "arm_id")
        key = (case, arm)
        scheduled = index.get(key)
        if key in observed or scheduled is None:
            raise Refusal("duplicate or unscheduled assessment")
        if any(assessment.get(k) != scheduled[k] for k in ("config_id", "raw_sha256")):
            raise Refusal("assessment identity drift")
        attempt = attempt_index.get(assessment.get("final_attempt_id"))
        if attempt is None or (attempt["case_id"], attempt["arm_id"]) != key:
            raise Refusal("explicit bound final attempt required")
        if assessment.get("java_status") not in JAVA:
            raise Refusal("explicit Java status required")
        for status in ("generic_rt_status", "paired_rt_status"):
            if assessment.get(status) not in ROUNDTRIP:
                raise Refusal("explicit roundtrip status required")
        if attempt["outcome"] != "completed" and any(assessment[k] == "pass" for k in ("java_status", "generic_rt_status", "paired_rt_status")):
            raise Refusal("non-completed attempt cannot pass output checks")
        if assessment.get("output_sha256") != attempt.get("output_sha256"):
            raise Refusal("assessment/output hash mismatch")
        for flag in ("unreported_critical_error", "any_critical_loss"):
            if assessment.get(flag) is not None and type(assessment[flag]) is not bool:
                raise Refusal("semantic flags must be bool or explicit unknown")
        wrong, loss = (assessment.get(k) for k in ("unreported_critical_error", "any_critical_loss"))
        if (wrong is None) != (loss is None):
            raise Refusal("semantic flags must be known or unknown together")
        if wrong is True and loss is not True:
            raise Refusal("critical error must also count as any critical loss")
        if wrong is not None:
            if attempt["outcome"] != "completed":
                raise Refusal("semantic output score requires completed output")
            require_hash(assessment.get("semantic_receipt_sha256"))
        observed[key] = assessment
    groups = {}
    for key, scheduled in index.items():
        if scheduled["purpose"] != "scored":
            continue
        group = (scheduled["namespace"], scheduled["site_id"], scheduled["arm_id"])
        groups.setdefault(group, []).append((key, observed.get(key)))
    summaries = []
    for (namespace, site, arm), rows in sorted(groups.items()):
        selected = [a for _, a in rows if a is not None]
        java = [a for a in selected if a["java_status"] == "pass"]
        rt = [a for a in java if a["generic_rt_status"] == "pass"]
        all_scored = [a for a in selected if a.get("unreported_critical_error") is not None]
        def metric(population, flag):
            measured = [a for a in population if a.get(flag) is not None]
            count = sum(a[flag] for a in measured)
            # Incomplete semantic coverage cannot produce a deceptively clean rate.
            return {**_fraction(count, len(population)), "value": count / len(population) if population and len(measured) == len(population) else None,
                    "measured": len(measured), "unmeasured": len(population) - len(measured)}
        outcomes = {outcome: 0 for outcome in sorted(OUTCOMES)}
        for a in selected:
            outcomes[attempt_index[a["final_attempt_id"]]["outcome"]] += 1
        wrong_count = sum(a["unreported_critical_error"] for a in all_scored)
        loss_count = sum(a["any_critical_loss"] for a in all_scored)
        total = len(rows)
        summaries.append({"namespace": namespace, "site_id": site, "arm_id": arm,
            "scheduled": total, "assessment_missing": total - len(selected), "outcomes": outcomes,
            "java_status_counts": {s: sum(a["java_status"] == s for a in selected) for s in sorted(JAVA)},
            "wrong_but_java_valid": metric(java, "unreported_critical_error"),
            "wrong_but_java_rt_valid": metric(rt, "unreported_critical_error"),
            "lossy_but_java_rt_valid": metric(rt, "any_critical_loss"),
            "wrong_all_scheduled": {**_fraction(wrong_count, total), "value": wrong_count / total if len(all_scored) == total else None, "unmeasured": total-len(all_scored)},
            "lossy_all_scheduled": {**_fraction(loss_count, total), "value": loss_count / total if len(all_scored) == total else None, "unmeasured": total-len(all_scored)}})
    return {**seal, "groups": summaries, "attempts_retained": len(attempts),
            "attempts_sha256": digest(attempts), "assessments_sha256": digest(assessments),
            "onboarding_rows": sum(s["purpose"] == "onboarding" for s in schedule),
            "runtime_verified": False, "independent_semantic_acceptance": False}
