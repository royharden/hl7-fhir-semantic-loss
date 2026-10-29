"""Builder-authored provisional projection/scoring, never independent gold.

This compares developer-supplied occurrences, not source truth. It is not a FHIR
validator, oracle/compiler/renderer, clinical judgment or completeness proof.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
from .common import Refusal, digest

POLICY_FILE = Path(__file__).resolve().parents[1] / "schemas" / "builder-v0-output-policy.json"


def _json(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode()) > 2_000_000:
            raise Refusal("builder-v0 serialized input limit")
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as error:
        raise Refusal("finite bounded JSON required") from error


def policy():
    value = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    if value.get("policy_id") != "builder-v0" or value.get("complete_semantic_score") is not False:
        raise Refusal("unsupported provisional contract")
    return value


def _ptr(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def extract(bundle):
    contract = policy()
    bundle = _json(bundle)
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle" or not isinstance(bundle.get("entry"), list):
        raise Refusal("builder-v0 requires Bundle entry list")
    limits = contract["limits"]
    if len(bundle["entry"]) > limits["resources"]:
        raise Refusal("resource count limit")
    aliases, resources, issues = defaultdict(list), [], []
    for index, entry in enumerate(bundle["entry"]):
        if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
            raise Refusal("resource entry object required")
        resource = entry["resource"]
        resource_type, resource_id = resource.get("resourceType"), resource.get("id")
        path = ("entry", index, "resource")
        if not isinstance(resource_type, str) or not resource_type:
            raise Refusal("resourceType required")
        identity = resource_type + "/" + resource_id if isinstance(resource_id, str) and resource_id else "@" + _ptr(path)
        if resource_type not in contract["supported_resources"]:
            issues.append({"class": "unsupported_resource", "pointer": _ptr(path), "resource_type": resource_type})
        resources.append({"identity": identity, "path": path, "resource": resource, "entry": entry})
        aliases[identity].append(index)
        if "fullUrl" in entry:
            if not isinstance(entry["fullUrl"], str) or not entry["fullUrl"]:
                raise Refusal("fullUrl must be a nonempty string")
            aliases[entry["fullUrl"]].append(index)
    # A resource alias may name itself twice (id and fullUrl); that is one target.
    aliases = {key: sorted(set(ids)) for key, ids in aliases.items()}
    for key, ids in aliases.items():
        if len(ids) > 1:
            issues.append({"class": "duplicate_resource_identity", "identity": key, "indices": ids})
    assertions, nodes = [], 0
    def walk(value, parts, role, subject, key=None, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > limits["nodes"] or depth > limits["depth"]:
            raise Refusal("projection traversal limit")
        if isinstance(value, dict) and value:
            for name, item in value.items():
                walk(item, parts + (name,), role + ("." if role else "") + name, subject, name, depth+1)
            return
        if isinstance(value, list) and value:
            for index, item in enumerate(value):
                walk(item, parts + (index,), role + "[]", subject, key, depth+1)
            return
        kind, unresolved, observed = "scalar", False, value
        if key == "reference":
            kind = "relation"
            target = aliases.get(value, []) if isinstance(value, str) else []
            unresolved = len(target) != 1
            if unresolved:
                issues.append({"class": "unresolved_relation", "pointer": _ptr(parts), "observed": value})
            else:
                observed = resources[target[0]]["identity"]
        assertions.append({"subject": subject, "role": role, "kind": kind, "value": observed,
                           "pointer": _ptr(parts), "unresolved": unresolved})
    for index, item in enumerate(resources):
        identity = item["identity"]
        if len(aliases[identity]) > 1:
            identity += "@" + _ptr(item["path"])
        for name, value in item["resource"].items():
            if name not in {"resourceType", "id"}:
                walk(value, item["path"] + (name,), name, identity, name)
        # Unexpected entry/Bundle properties are assertions, never silently metadata.
        for name, value in item["entry"].items():
            if name not in {"resource", "fullUrl"}:
                walk(value, ("entry", index, name), "entry."+name, identity, name)
    for name, value in bundle.items():
        if name not in {"resourceType", "type", "entry"}:
            walk(value, (name,), name, "@Bundle", name)
    return {"policy_id": "builder-v0", "policy_sha256": digest(contract), "assertions": assertions,
            "issues": issues, "bundle_sha256": digest(bundle), "complete_semantic_score": False,
            "authorship": contract["authorship"], "independent_ratification": "PENDING - Roy",
            "headline_eligible": False}


def compare(bundle, expectations):
    """Compare an explicit builder-v0 developer expectation document.

    Each expected occurrence has subject/role/kind/allowed_values/critical. At
    most one actual occurrence satisfies it; alternatives are not extra truths.
    No source expectation is inferred or compiled from Bundle content.
    """
    extracted = extract(bundle)
    expected = _json(expectations)
    if not isinstance(expected, dict) or set(expected) != {"policy_id", "authorship", "assertions", "relation_cardinalities", "unmatched_critical"}:
        raise Refusal("explicit builder-v0 expectation document required")
    if expected["policy_id"] != "builder-v0" or expected["authorship"] != "builder-authored, provisional, not independent gold" or type(expected["unmatched_critical"]) is not bool:
        raise Refusal("provisional authorship/critical policy required")
    if not isinstance(expected["assertions"], list) or len(expected["assertions"]) > 10_000:
        raise Refusal("bounded expected occurrence list required")
    groups, actual_groups = defaultdict(list), defaultdict(list)
    for index, row in enumerate(expected["assertions"]):
        if not isinstance(row, dict) or set(row) != {"subject", "role", "kind", "allowed_values", "critical"}:
            raise Refusal("unsupported expected assertion")
        if any(not isinstance(row[k], str) or not row[k] for k in ("subject", "role")) or not isinstance(row["kind"], str) or row["kind"] not in {"scalar", "relation"} or type(row["critical"]) is not bool:
            raise Refusal("invalid expected occurrence identity")
        if not isinstance(row["allowed_values"], list) or not row["allowed_values"] or len(row["allowed_values"]) > 32:
            raise Refusal("explicit bounded alternatives required")
        if row["kind"] == "relation" and any(not isinstance(v, str) or not v for v in row["allowed_values"]):
            raise Refusal("explicit relation targets required")
        groups[(row["subject"], row["role"], row["kind"])].append((index, row))
    for index, row in enumerate(extracted["assertions"]):
        actual_groups[(row["subject"], row["role"], row["kind"])].append((index, row))
    findings, matched = [], []
    for key in sorted(set(groups) | set(actual_groups)):
        wants, observed = groups[key], actual_groups[key]
        # Enforce bounds before allocating/hashing a Cartesian candidate graph.
        if len(wants) > 512 or len(observed) > 512:
            raise Refusal("per-role matching limit")
        # Maximum bipartite matching avoids greedy false errors with overlapping alternatives.
        edges = {i: [j for j, (_, a) in enumerate(observed) if not a["unresolved"] and any(digest(a["value"]) == digest(v) for v in row["allowed_values"])] for i, (_, row) in enumerate(wants)}
        owners = {}
        def augment(i, seen):
            for j in edges[i]:
                if j in seen:
                    continue
                seen.add(j)
                if j not in owners or augment(owners[j], seen):
                    owners[j] = i
                    return True
            return False
        for i in range(len(wants)):
            augment(i, set())
        matched_wants = set(owners.values())
        for j, i in owners.items():
            matched.append({"expected_index": wants[i][0], "actual_pointer": observed[j][1]["pointer"]})
        missing = [i for i in range(len(wants)) if i not in matched_wants]
        extra = [j for j in range(len(observed)) if j not in owners]
        # Unmatched same-role occurrences are distortions, with relations explicit.
        while missing and extra:
            i, j = missing.pop(0), extra.pop(0)
            row, actual = wants[i][1], observed[j][1]
            findings.append({"class": "wrong_relation" if key[2] == "relation" else "distortion",
                "expected_index": wants[i][0], "actual_pointer": actual["pointer"],
                "observed": actual["value"], "critical": row["critical"]})
        for i in missing:
            findings.append({"class": "missing_relation" if key[2] == "relation" else "missing_assertion",
                             "expected_index": wants[i][0], "critical": wants[i][1]["critical"]})
        matched_values = {digest(observed[j][1]["value"]) for j in owners}
        alternative_values = {digest(v) for i in matched_wants for v in wants[i][1]["allowed_values"]}
        for j in extra:
            actual = observed[j][1]
            value_hash = digest(actual["value"])
            category = "duplicate" if value_hash in matched_values else "alternative_stuffing" if value_hash in alternative_values else "invention"
            findings.append({"class": category, "actual_pointer": actual["pointer"], "observed": actual["value"],
                             "critical": expected["unmatched_critical"]})
    cardinalities = expected["relation_cardinalities"]
    if not isinstance(cardinalities, list) or len(cardinalities) > 10_000:
        raise Refusal("bounded cardinality list required")
    for rule in cardinalities:
        if not isinstance(rule, dict) or set(rule) != {"subject", "role", "min", "max", "critical"}:
            raise Refusal("explicit relation cardinality required")
        if any(not isinstance(rule[k], str) or not rule[k] for k in ("subject", "role")) or type(rule["critical"]) is not bool or type(rule["min"]) is not int or type(rule["max"]) is not int or not 0 <= rule["min"] <= rule["max"]:
            raise Refusal("invalid cardinality")
        count = sum(a["subject"] == rule["subject"] and a["role"] == rule["role"] and a["kind"] == "relation" and not a["unresolved"] for a in extracted["assertions"])
        if not rule["min"] <= count <= rule["max"]:
            findings.append({"class": "relation_cardinality", "subject": rule["subject"], "role": rule["role"], "observed_count": count, "critical": rule["critical"]})
    return {"policy_id": "builder-v0", "policy_sha256": extracted["policy_sha256"],
            "bundle_sha256": extracted["bundle_sha256"], "expectations_sha256": digest(expected),
            "matched": matched, "findings": findings, "counts": dict(Counter(f["class"] for f in findings)),
            "projection_issues": extracted["issues"], "complete_semantic_score": False,
            "authorship": "builder-authored, provisional, not independent gold", "independent_ratification": "PENDING - Roy",
            "runtime_validation": "not_run", "headline_eligible": False}
