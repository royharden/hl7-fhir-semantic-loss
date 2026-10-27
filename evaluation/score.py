"""Truth-consuming exact comparator; external O assertions are required.
No compiler, calibration, renderer or expected outcomes live here. Unsupported
semantics refuse rather than treating an unexamined FHIR output as correct.
"""
from .common import Refusal, digest, pointer, require_hash

def extract(bundle, targets):
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise Refusal("unsupported output: FHIR Bundle object required")
    out = []
    seen = set()
    for target in targets:
        path = target.get("pointer")
        if not isinstance(path, str) or not path or path in seen:
            raise Refusal("missing/duplicate assertion pointer")
        seen.add(path)
        try:
            value = pointer(bundle, path)
        except (KeyError, IndexError):
            value = None
            present = False
        else:
            present = True
        out.append({"pointer": path, "present": present, "value": value})
    return out

def compare_assertions(bundle, oracle, dispositions, *, case_id, raw_sha256):
    require_hash(raw_sha256)
    if oracle.get("case_id") != case_id or oracle.get("raw_sha256") != raw_sha256:
        raise Refusal("oracle/source identity mismatch")
    require_hash(oracle.get("release_sha256"))
    assertions = oracle.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise Refusal("external assertions missing")
    rows, ids, refs = [], set(), set()
    for item in dispositions:
        source_ref = item.get("source_ref")
        if not isinstance(source_ref, dict) or source_ref.get("raw_sha256") != raw_sha256:
            raise Refusal("disposition source hash missing/mismatched")
        ref = digest(source_ref)
        if ref in refs or item.get("disposition") not in {"mapped", "declared_drop", "abstain"}:
            raise Refusal("duplicate/invalid disposition")
        refs.add(ref)
    for atom in assertions:
        atom_id = atom.get("atom_id")
        if not atom_id or atom_id in ids or type(atom.get("critical")) is not bool:
            raise Refusal("invalid/duplicate atom")
        ids.add(atom_id)
        if atom.get("comparison") != "exact" or atom.get("knowability") not in {"known", "unknown"}:
            raise Refusal("unsupported comparison or knowability")
        source_ref = atom.get("source_ref")
        if not isinstance(source_ref, dict) or source_ref.get("raw_sha256") != raw_sha256:
            raise Refusal("oracle source ref hash missing/mismatched")
        targets = atom.get("targets")
        if not isinstance(targets, list) or not targets:
            raise Refusal("complete O-supplied target projection required")
        actual = extract(bundle, targets)
        matches = [d for d in dispositions if d.get("source_ref") == atom.get("source_ref")]
        disposition = matches[0]["disposition"] if matches else "missing"
        present = any(a["present"] for a in actual)
        if atom["knowability"] == "unknown":
            classification = "invention" if present else ("correct_abstention" if disposition == "abstain" else "safe_nonassertion")
        else:
            exact = all(a["present"] and digest(a["value"]) == digest(t["expected"]) for a, t in zip(actual, targets))
            if exact:
                classification = "preserved"
            elif present:
                classification = "distortion"
            elif disposition == "declared_drop":
                classification = "declared_drop"
            elif disposition == "abstain":
                classification = "unnecessary_abstention"
            else:
                classification = "silent_drop"
        dishonest = disposition in {"declared_drop", "abstain"} and present
        rows.append({"atom_id": atom_id, "critical": atom["critical"], "classification": classification,
                     "disposition": disposition, "false_declaration": dishonest, "observed": actual})
    return {"case_id": case_id, "raw_sha256": raw_sha256, "oracle_release_sha256": oracle["release_sha256"],
            "rows": rows, "scope": "external exact target projection only", "complete_semantic_score": False,
            "pending": ["independent mutation validation", "complete output invention enumeration", "relationship equivalences"]}

def ratio(numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int or not 0 <= numerator <= denominator:
        raise Refusal("invalid denominator counts")
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}

def metrics(cases):
    """Require every scheduled case, including failures, to be supplied explicitly."""
    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise Refusal("duplicate scheduled case")
    allowed_classes = {"preserved", "correct_abstention", "safe_nonassertion", "invention", "distortion", "silent_drop", "declared_drop", "unnecessary_abstention"}
    for case in cases:
        rows = case.get("rows", [])
        if not isinstance(rows, list):
            raise Refusal("score rows must be a list")
        seen_atoms = set()
        for row in rows:
            if not isinstance(row, dict) or type(row.get("critical")) is not bool or row.get("classification") not in allowed_classes:
                raise Refusal("invalid metric score row")
            atom = row.get("atom_id")
            if not isinstance(atom, str) or not atom or atom in seen_atoms:
                raise Refusal("missing/duplicate metric atom id")
            seen_atoms.add(atom)
        if case.get("java_status") not in {"pass", "fail", "error", "not_run"}:
            raise Refusal("explicit Java status required for every scheduled case")
        if case.get("generic_rt_status") not in {"pass", "fail", "error", "not_run", "unsupported"}:
            raise Refusal("explicit generic roundtrip status required for every scheduled case")
        if case.get("java_status") == "pass" and not case.get("rows"):
            raise Refusal("cannot classify Java-valid output without external score rows")
    java = [c for c in cases if c.get("java_status") == "pass"]
    rt = [c for c in java if c.get("generic_rt_status") == "pass"]
    wrong = lambda c: any(r["critical"] and r["classification"] in {"invention", "distortion", "silent_drop"} for r in c.get("rows", []))
    lossy = lambda c: any(r["critical"] and r["classification"] in {"invention", "distortion", "silent_drop", "declared_drop", "unnecessary_abstention"} for r in c.get("rows", []))
    return {"scheduled": len(cases), "wrong_but_java_valid": ratio(sum(map(wrong, java)), len(java)),
            "wrong_but_java_rt_valid": ratio(sum(map(wrong, rt)), len(rt)),
            "wrong_all_scheduled": ratio(sum(map(wrong, cases)), len(cases)),
            "lossy_java_rt_valid": ratio(sum(map(lossy, rt)), len(rt)),
            "lossy_all_scheduled": ratio(sum(map(lossy, cases)), len(cases)),
            "complete_semantic_score": False, "runtime_verified": False}
