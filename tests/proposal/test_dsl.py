"""Builder-authored developer regressions, never independent gold or FHIR validation."""

from copy import deepcopy

import pytest

from h7loss.proposal import compile_proposal, execute_proposal, validate_proposal
from h7loss.v2 import parse_message


def _resources(result, kind):
    return [entry["resource"] for entry in result["bundle"]["entry"]
            if entry["resource"]["resourceType"] == kind]


def _resolve(bundle, pointer):
    assert pointer.startswith("/")
    current = bundle
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _assert_complete_refs(raw, result):
    expected = parse_message(raw)["source_refs"]
    actual = [row["source_ref"] for row in result["dispositions"]]
    key = lambda ref: tuple(sorted(ref.items()))
    assert sorted(map(key, actual)) == sorted(map(key, expected))
    assert len(actual) == len({key(ref) for ref in actual})
    for ref in actual:
        assert 0 <= ref["byte_start"] <= ref["byte_end"] <= len(raw)


def test_repeated_escaped_text_has_distinct_resources_and_resolvable_targets(dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case(value=r"alpha\F\beta~gamma\S\delta")
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    observations = _resources(result, "Observation")
    assert [item["valueString"] for item in observations] == ["alpha|beta", "gamma^delta"]
    assert len({item["id"] for item in observations}) == 2
    assert all(item["subject"]["reference"] == "Patient/" + _resources(result, "Patient")[0]["id"]
               for item in observations)
    assert _resources(result, "DiagnosticReport")[0]["code"] == {"text": dictionary["report_code"]}
    _assert_complete_refs(raw, result)
    mapped = [row for row in result["dispositions"] if row["disposition"] == "mapped"]
    assert mapped
    for row in mapped:
        assert row["target_refs"]
        for pointer in row["target_refs"]:
            assert _resolve(result["bundle"], pointer) is not None


@pytest.mark.parametrize("datatype,value,unit,field,expected", [
    ("NM", "5.25", True, "valueQuantity", {"value": 5.25, "system": "urn:h7loss:dev:units", "code": "du", "unit": "Synthetic developer unit"}),
    ("SN", ">^5.00", False, "valueQuantity", {"value": 5, "comparator": ">"}),
    ("SN", "^2^:^3", False, "valueRatio", {"numerator": {"value": 2}, "denominator": {"value": 3}}),
    ("SN", "^1^-^4", True, "valueRange", {"low": {"value": 1, "system": "urn:h7loss:dev:units", "code": "du", "unit": "Synthetic developer unit"}, "high": {"value": 4, "system": "urn:h7loss:dev:units", "code": "du", "unit": "Synthetic developer unit"}}),
])
def test_numeric_value_shapes_preserve_builder_case(datatype, value, unit, field, expected, dsl_case):
    raw, dictionary, rules, _rule, proposal = dsl_case(datatype, value, unit=unit)
    if datatype == "SN":
        rules[5].update(transform="decimal_with_comparator")
        rules[5]["source"]["repetition"] = 1
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    assert _resources(result, "Observation")[0][field] == expected
    _assert_complete_refs(raw, result)


def test_cwe_coding_uses_released_namespace_and_does_not_map_disagreeing_display(dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case("CWE", "BLUE^unreleased display^LOCAL")
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    assert _resources(result, "Observation")[0]["valueCodeableConcept"] == {
        "coding": [dictionary["value_codes"]["BLUE"]]}
    display = next(row for row in result["dispositions"]
                   if row["source_ref"]["segment_index"] == 3 and row["source_ref"]["field"] == 5
                   and row["source_ref"]["component"] == 2)
    assert display["disposition"] == "abstain"
    assert display["target_refs"] == []


@pytest.mark.parametrize("datatype,value,unit", [
    ("CWE", "BLUE^Synthetic blue category^FOREIGN", False),
    ("CWE", "BLUE^Synthetic blue category^LOCAL^extra", False),
    ("SN", "^2^:^0", False),
    ("SN", "^4^-^1", False),
    ("SN", "^2^:^3", True),
    ("NM", "0.123456789012345678901", False),
    ("ST", '""', False),
    ("ST", "", False),
])
def test_unsupported_values_refuse_without_partial_mapped_claims(datatype, value, unit, dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case(datatype, value, unit=unit)
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "error"
    assert result["bundle"] is None
    assert result["error"]
    _assert_complete_refs(raw, result)
    assert all(row["disposition"] == "abstain" and row["target_refs"] == []
               for row in result["dispositions"])


@pytest.mark.parametrize("transform", ["declare_drop", "abstain"])
def test_explicit_nonmapping_disposition_stays_out_of_output(transform, dsl_case):
    raw, dictionary, rules, rule, proposal = dsl_case(tail="NTE|1||unit-note")
    disposition = rule("NTE", "observation", 3, "observation.note")
    disposition.pop("target")
    disposition.update(transform=transform, reason="builder_unit_reason")
    rules.append(disposition)
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    assert "note" not in _resources(result, "Observation")[0]
    note = next(row for row in result["dispositions"]
                if raw[row["source_ref"]["byte_start"]:row["source_ref"]["byte_end"]] == b"unit-note")
    assert note["disposition"] == ("declared_drop" if transform == "declare_drop" else "abstain")
    assert note["reason_code"] == "builder_unit_reason"
    assert note["target_refs"] == []


def test_literal_guard_and_constant_use_only_explicit_public_table(dsl_case):
    raw, dictionary, rules, rule, proposal = dsl_case(tail="NTE|1||unit-note")
    dictionary["tables"]["unit_constant"] = {"constant": "builder released note"}
    note = rule("NTE", "observation", 3, "observation.note", "constant_from_dictionary", table="unit_constant")
    note["guard"] = "different"
    rules.append(note)
    skipped = execute_proposal(raw, dictionary, proposal())
    assert skipped["outcome"] == "ok", skipped["error"]
    assert "note" not in _resources(skipped, "Observation")[0]
    note["guard"] = "unit-note"
    mapped = execute_proposal(raw, dictionary, proposal())
    assert mapped["outcome"] == "ok", mapped["error"]
    assert _resources(mapped, "Observation")[0]["note"] == [{"text": "builder released note"}]


def test_z_join_checks_each_consumed_binding_and_preserves_empty_positions(dsl_case):
    raw, dictionary, rules, rule, proposal = dsl_case(tail="ZUT|alpha^^beta")
    dictionary["tables"]["unit_join"] = {"separator": " "}
    dictionary["bindings"] = {"ZUT.1.1.1": "observation.note"}
    rules.append(rule("ZUT", "observation", 1, "observation.note", "join_components",
                      component="all", table="unit_join"))
    refused = execute_proposal(raw, dictionary, proposal())
    assert refused["outcome"] == "error"
    assert refused["error"] == "undocumented_z_meaning"
    assert refused["bundle"] is None
    dictionary["bindings"]["ZUT.1.3.1"] = "observation.note"
    mapped = execute_proposal(raw, dictionary, proposal())
    assert mapped["outcome"] == "ok", mapped["error"]
    assert _resources(mapped, "Observation")[0]["note"] == [{"text": "alpha  beta"}]
    _assert_complete_refs(raw, mapped)


def test_z_join_cannot_consume_components_outside_selector(dsl_case):
    raw, dictionary, rules, rule, proposal = dsl_case(tail="ZUT|alpha^beta")
    dictionary["tables"]["unit_join"] = {"separator": " "}
    dictionary["bindings"] = {"ZUT.1.1.1": "observation.note"}
    rules.append(rule("ZUT", "observation", 1, "observation.note", "join_components", table="unit_join"))
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    assert _resources(result, "Observation")[0]["note"] == [{"text": "alpha"}]
    beta = next(row for row in result["dispositions"]
                if raw[row["source_ref"]["byte_start"]:row["source_ref"]["byte_end"]] == b"beta")
    assert beta["disposition"] == "abstain"


def test_subcomponent_join_refuses_flattening(dsl_case):
    raw, dictionary, rules, rule, proposal = dsl_case(tail="ZUT|alpha&beta")
    dictionary["tables"]["unit_join"] = {"separator": " "}
    dictionary["bindings"] = {"ZUT.1.1.2": "observation.note"}
    note = rule("ZUT", "observation", 1, "observation.note", "join_components", table="unit_join")
    note["source"]["subcomponent"] = 2
    rules.append(note)
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "error"
    assert result["error"] == "join_unsupported_atom"
    assert result["bundle"] is None


def test_fake_pointer_and_conflicting_assignments_fail_closed(dsl_case):
    raw, dictionary, rules, _rule, proposal = dsl_case()
    ref = deepcopy(next(ref for ref in parse_message(raw)["source_refs"]
                        if ref["segment_index"] == 1 and ref["field"] == 3 and ref["component"] == 1))
    ref["byte_start"] += 1
    rules[0]["source"] = ref
    forged = execute_proposal(raw, dictionary, proposal())
    assert forged["outcome"] == "error"
    assert forged["error"] == "fake_source_pointer"
    raw, dictionary, rules, _rule, proposal = dsl_case()
    rules.append(deepcopy(rules[0]))
    duplicate = execute_proposal(raw, dictionary, proposal())
    assert duplicate["outcome"] == "error"
    assert duplicate["error"] == "conflicting_target"
    assert duplicate["bundle"] is None


def test_original_dictionary_hash_and_site_identity_are_not_silently_rewritten(dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case()
    original = proposal()
    dictionary["builder_unit_new_field"] = "changed release"
    assert execute_proposal(raw, dictionary, original)["error"] == "stale_dictionary"
    changed = proposal()
    changed["site_id"] = "other-explicit-site"
    assert execute_proposal(raw, dictionary, changed)["error"] == "site_mismatch"


@pytest.mark.parametrize("timestamp,expected", [
    ("20260102120000+0000", "2026-01-02T12:00:00+00:00"),
    ("202601", "2026-01"),
])
def test_timestamp_keeps_released_precision(timestamp, expected, dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case(timestamp=timestamp)
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    assert _resources(result, "Observation")[0]["effectiveDateTime"] == expected


def test_partial_time_without_offset_refuses_instead_of_inventing_zone(dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case(timestamp="20260102120000")
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "error"
    assert result["error"] == "fhir_timestamp_cannot_preserve_partial_time"


@pytest.mark.parametrize("mutation", [
    lambda item: item["rules"][0].update(transform="__import__('os').system"),
    lambda item: item["rules"][0].update(target="../../arbitrary/path"),
    lambda item: item["rules"][0].update(code="not a permitted property"),
    lambda item: item["rules"][0].update(guard={"expression": "loop"}),
])
def test_unknown_code_paths_expressions_and_keys_are_rejected(mutation, dsl_case):
    _raw, _dictionary, _rules, _rule, proposal = dsl_case()
    supplied = proposal()
    mutation(supplied)
    assert validate_proposal(supplied)["valid"] is False
    with pytest.raises(ValueError, match="invalid_proposal"):
        compile_proposal(supplied)


def test_recursive_json_and_malformed_dictionary_return_refusal(dsl_case):
    raw, dictionary, _rules, _rule, proposal = dsl_case()
    recursive = proposal()
    recursive["self"] = recursive
    assert validate_proposal(recursive)["valid"] is False
    dictionary["tables"] = []
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "error"
    assert result["bundle"] is None
    assert result["error"] == "dictionary_mapping_required:tables"
