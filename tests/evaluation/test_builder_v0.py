"""Builder-authored developer regressions, never independent truth/calibration."""
import copy
import pytest
from evaluation.builder_v0 import compare, extract
from evaluation.common import Refusal

LABEL = "builder-authored, provisional, not independent gold"


def bundle(*resources):
    return {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": r} for r in resources]}


def expected(*rows, cardinalities=()):
    return {"policy_id": "builder-v0", "authorship": LABEL, "assertions": list(rows),
            "relation_cardinalities": list(cardinalities), "unmatched_critical": True}


def assertion(role, values, *, subject="Observation/o", kind="scalar", critical=True):
    return {"subject": subject, "role": role, "kind": kind, "allowed_values": values, "critical": critical}


def observation(**fields):
    return {"resourceType": "Observation", "id": "o", **fields}


def test_metadata_exclusion_preserves_nonmetadata_and_provisional_flags():
    actual = bundle(observation(valueString="original"))
    actual["entry"][0]["fullUrl"] = "urn:local:o"
    result = compare(actual, expected(assertion("valueString", ["original"])))
    assert result["findings"] == []
    assert result["complete_semantic_score"] is False
    assert result["headline_eligible"] is False
    assert result["independent_ratification"] == "PENDING - Roy"
    assert result["authorship"] == LABEL
    assert result["runtime_validation"] == "not_run"


def test_unexpected_leaf_is_not_silently_metadata():
    result = compare(bundle(observation(unlisted="extra")), expected())
    assert result["counts"] == {"invention": 1}
    assert result["findings"][0]["actual_pointer"] == "/entry/0/resource/unlisted"


def test_distortion_and_missing_are_distinct():
    result = compare(bundle(observation(valueString="changed")), expected(assertion("valueString", ["original"]), assertion("status", ["final"])))
    assert result["counts"] == {"missing_assertion": 1, "distortion": 1}


def test_repeated_occurrences_are_not_deduplicated():
    actual = bundle(observation(note=[{"text": "same"}, {"text": "same"}]))
    row = assertion("note[].text", ["same"])
    assert compare(actual, expected(row, copy.deepcopy(row)))["findings"] == []
    result = compare(actual, expected(row))
    assert result["counts"] == {"duplicate": 1}
    assert len(result["matched"]) == 1


def test_alternatives_consume_one_occurrence_not_all_options():
    actual = bundle(observation(note=[{"text": "x"}, {"text": "y"}]))
    result = compare(actual, expected(assertion("note[].text", ["x", "y"])))
    assert result["counts"] == {"alternative_stuffing": 1}


def test_overlapping_alternatives_use_maximum_matching():
    actual = bundle(observation(note=[{"text": "x"}, {"text": "y"}]))
    result = compare(actual, expected(assertion("note[].text", ["x", "y"]), assertion("note[].text", ["x"])))
    assert len(result["matched"]) == 2
    assert result["findings"] == []


def test_wrong_relation_not_scalar_distortion():
    actual = bundle({"resourceType": "Patient", "id": "p1"}, {"resourceType": "Patient", "id": "p2"}, observation(subject={"reference": "Patient/p2"}))
    result = compare(actual, expected(assertion("subject.reference", ["Patient/p1"], kind="relation")))
    assert result["counts"] == {"wrong_relation": 1}


def test_missing_relation_and_explicit_minimum():
    actual = bundle(observation())
    rule = {"subject": "Observation/o", "role": "subject.reference", "min": 1, "max": 1, "critical": True}
    result = compare(actual, expected(assertion("subject.reference", ["Patient/p1"], kind="relation"), cardinalities=[rule]))
    assert result["counts"] == {"missing_relation": 1, "relation_cardinality": 1}


def test_dangling_relation_cannot_match_same_literal():
    result = compare(bundle(observation(subject={"reference": "Patient/missing"})), expected(assertion("subject.reference", ["Patient/missing"], kind="relation")))
    assert result["matched"] == []
    assert result["counts"] == {"wrong_relation": 1}
    assert result["projection_issues"][0]["class"] == "unresolved_relation"


def test_duplicate_resource_identity_does_not_resolve_relation():
    actual = bundle({"resourceType": "Patient", "id": "p"}, {"resourceType": "Patient", "id": "p"}, observation(subject={"reference": "Patient/p"}))
    result = compare(actual, expected(assertion("subject.reference", ["Patient/p"], kind="relation")))
    assert {i["class"] for i in result["projection_issues"]} == {"duplicate_resource_identity", "unresolved_relation"}
    assert result["matched"] == []


def test_fullurl_alias_can_resolve_to_same_local_resource():
    actual = bundle({"resourceType": "Patient", "id": "p"}, observation(subject={"reference": "urn:local:p"}))
    actual["entry"][0]["fullUrl"] = "urn:local:p"
    result = compare(actual, expected(assertion("subject.reference", ["Patient/p"], kind="relation")))
    assert result["findings"] == []


@pytest.mark.parametrize("actual,wanted", [(True, 1), (1, "1"), (None, ""), ({}, [])])
def test_no_implicit_scalar_or_empty_container_equivalence(actual, wanted):
    result = compare(bundle(observation(valueString=actual)), expected(assertion("valueString", [wanted])))
    assert result["counts"] == {"distortion": 1}


def test_no_implicit_unit_equivalence():
    actual = bundle(observation(valueQuantity={"value": 1, "unit": "unit-a"}))
    result = compare(actual, expected(assertion("valueQuantity.value", [1]), assertion("valueQuantity.unit", ["unit-b"])))
    assert result["counts"] == {"distortion": 1}


def test_finite_json_and_bounds_refuse():
    with pytest.raises(Refusal):
        extract(bundle(observation(valueString=float("nan"))))
    with pytest.raises(Refusal):
        extract(bundle(*[observation() for _ in range(1025)]))


def test_independent_label_and_malformed_policy_refuse():
    value = expected()
    value["authorship"] = "independent gold"
    with pytest.raises(Refusal):
        compare(bundle(observation()), value)
    with pytest.raises(Refusal):
        compare(bundle(observation()), {"assertions": []})


def test_unsupported_resources_remain_explicit():
    result = extract(bundle({"resourceType": "Other", "id": "x", "value": "kept"}))
    assert result["issues"][0]["class"] == "unsupported_resource"
    assert result["assertions"][0]["value"] == "kept"
    assert result["complete_semantic_score"] is False


def test_extractor_is_explicitly_headline_ineligible():
    result = extract(bundle(observation(valueString="developer-only")))
    assert result["headline_eligible"] is False
    assert result["complete_semantic_score"] is False
    assert result["authorship"] == LABEL
    assert result["independent_ratification"] == "PENDING - Roy"


def test_role_limit_precedes_cartesian_graph(monkeypatch):
    import evaluation.builder_v0 as module
    calls = 0
    original = module.digest
    def bounded_digest(value):
        nonlocal calls
        calls += 1
        assert calls <= 10, "oversized role reached candidate hashing"
        return original(value)
    monkeypatch.setattr(module, "digest", bounded_digest)
    actual = bundle(observation(note=[{"text": "same"} for _ in range(513)]))
    wants = [assertion("note[].text", ["same"]) for _ in range(513)]
    with pytest.raises(Refusal, match="per-role matching limit"):
        compare(actual, expected(*wants))
    assert calls <= 10


@pytest.mark.parametrize("kind", [[], {}, None, True])
def test_malformed_assertion_kind_refuses(kind):
    row = assertion("valueString", ["x"])
    row["kind"] = kind
    with pytest.raises(Refusal):
        compare(bundle(observation(valueString="x")), expected(row))
