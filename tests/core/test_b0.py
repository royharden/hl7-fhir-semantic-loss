"""Builder-authored original developer regressions, never independent gold."""

import copy
import hashlib
import json
from decimal import Decimal

import pytest

from h7loss.arms.b0 import map_message, paired_inverse
from h7loss.gen import generate_case
from h7loss.v2 import parse_message
from h7loss.v2.time import timestamp_to_fhir


def replace_field(raw, tag, number, text, occurrence=0):
    lines = raw.split(b"\r")
    indices = [i for i, line in enumerate(lines) if line.startswith(tag.encode() + b"|")]
    index = indices[occurrence]
    fields = lines[index].decode().split("|")
    fields += [""] * max(0, number + 1 - len(fields))
    fields[number] = text
    lines[index] = "|".join(fields).encode()
    return b"\r".join(lines)


def case(kind="NM", value="5.00"):
    authored = generate_case("dev-01", 0)
    raw = authored["raw"]
    for number, text in ((2, kind), (3, f"D01{kind}^Developer test^LOCAL"), (5, value),
                         (6, "du^Developer unit^LOCAL" if kind in {"NM", "SN"} else "")):
        raw = replace_field(raw, "OBX", number, text)
    return raw, authored["dictionary"]


def resources(result, resource_type):
    return [entry["resource"] for entry in (result.get("bundle") or {}).get("entry", [])
            if entry["resource"]["resourceType"] == resource_type]


def source_rows(result, field, *, tag="OBX", raw=None):
    indices = None if raw is None else {s["index"] for s in parse_message(raw)["segments"] if s["tag"] == tag}
    return [row for row in result["dispositions"] if row["source_ref"]["field"] == field
            and (indices is None or row["source_ref"]["segment_index"] in indices)]


def test_baseline_ledger_and_links_are_explicit():
    raw, dictionary = case()
    result = map_message(raw, dictionary)
    assert result["outcome"] == "partial"  # Unknown Z and other source leaves remain unsupported.
    assert result["provenance"]["validation"] == "not_run"
    assert len(result["dispositions"]) == len(parse_message(raw)["atoms"])
    patient, = resources(result, "Patient")
    report, = resources(result, "DiagnosticReport")
    observation, = resources(result, "Observation")
    assert report["subject"]["reference"] == "Patient/" + patient["id"]
    assert observation["subject"] == report["subject"]
    assert report["result"] == [{"reference": "Observation/" + observation["id"]}]
    assert result["dictionary_sha256"] == hashlib.sha256(json.dumps(dictionary, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


@pytest.mark.parametrize("table,value", [("codes", []), ("identifier_systems", None),
                                        ("report_statuses", {"F": []}), ("coding_authorities", {"LOCAL": None})])
def test_malformed_dictionary_refuses_with_leaf_ledger(table, value):
    raw, dictionary = case()
    dictionary[table] = value
    result = map_message(raw, dictionary)
    assert result["outcome"] == "refused"
    assert result["bundle"] is None
    assert result["error"].startswith("invalid_dictionary:")
    assert len(result["dispositions"]) == len(parse_message(raw)["atoms"])
    assert not any(row["disposition"] == "mapped" for row in result["dispositions"])


@pytest.mark.parametrize("shape", ["cycle", "deep"])
def test_recursive_dictionary_metadata_refuses_instead_of_crashing(shape):
    raw, dictionary = case()
    if shape == "cycle":
        dictionary["recursive_metadata"] = dictionary
    else:
        nested = []
        for _ in range(1500):
            nested = [nested]
        dictionary["recursive_metadata"] = nested
    result = map_message(raw, dictionary)
    assert result["outcome"] == "refused"
    assert result["error"].startswith("invalid_dictionary:")


@pytest.mark.parametrize("field,replacement", [(3, "D01NM^Test^CONFLICT"), (6, "du^Unit^CONFLICT")])
def test_coding_namespace_conflict_never_asserts_observation(field, replacement):
    raw, dictionary = case()
    result = map_message(replace_field(raw, "OBX", field, replacement), dictionary)
    assert resources(result, "Observation") == []


@pytest.mark.parametrize("lexeme", ["5.00", "-0.20", "100.125", "+5", ".50", "9007199254740993"])
def test_supported_numeric_value_and_lexical_scale(lexeme):
    raw, dictionary = case(value=lexeme)
    result = map_message(raw, dictionary)
    observation, = resources(result, "Observation")
    assert Decimal(str(observation["valueQuantity"]["value"])) == Decimal(lexeme)
    inverse = paired_inverse(result, dictionary)
    assert any(p["text"] == lexeme and p["source_ref"]["field"] == 5 for p in inverse["projection"])
    assert inverse["status"] == "partial"


@pytest.mark.parametrize("lexeme", ["NaN", "Infinity", "1e3", "9007199254740993.1", '""'])
def test_numeric_unsupported_or_lossy_input_is_not_asserted(lexeme):
    raw, dictionary = case(value=lexeme)
    assert resources(map_message(raw, dictionary), "Observation") == []


def test_sn_comparator_and_cwe_are_dictionary_bound():
    raw, dictionary = case("SN", ">^5.00")
    result = map_message(raw, dictionary)
    observation, = resources(result, "Observation")
    assert observation["valueQuantity"]["comparator"] == ">"
    assert {p["text"] for p in paired_inverse(result, dictionary)["projection"]} >= {"SN", ">", "5.00"}
    raw, dictionary = case("CWE", "BLUE^Original blue^LOCAL")
    observation, = resources(map_message(raw, dictionary), "Observation")
    assert observation["valueCodeableConcept"]["coding"][0] == dictionary["value_codes"]["BLUE"]
    raw = replace_field(raw, "OBX", 5, "BLUE^Original blue^CONFLICT")
    assert not resources(map_message(raw, dictionary), "Observation")


def test_sn_range_and_unknown_categorical_meaning_abstain():
    for kind, value in (("SN", "^1^-^4"), ("SN", ">^1^:^2"), ("CWE", "UNRELEASED^Unknown^LOCAL")):
        raw, dictionary = case(kind, value)
        assert not resources(map_message(raw, dictionary), "Observation")


def test_repeated_text_notes_flags_and_projection_keep_distinct_targets():
    raw, dictionary = case("ST", "alpha~beta\\F\\gamma")
    raw = replace_field(raw, "OBX", 8, "A~H")
    result = map_message(raw, dictionary)
    observations = resources(result, "Observation")
    assert [o["valueString"] for o in observations] == ["alpha", "beta|gamma"]
    assert all([flag["coding"][0]["code"] for flag in o["interpretation"]] == ["A", "H"] for o in observations)
    assert all(o["note"] == [{"text": "Original synthetic observation note 1"}] for o in observations)
    report, = resources(result, "DiagnosticReport")
    assert any(e.get("valueString") == "Original synthetic order note" for e in report["extension"])
    inverse = paired_inverse(result, dictionary)
    assert inverse["error"] is None
    assert {p["text"] for p in inverse["projection"]} >= {"alpha", "beta|gamma", "A", "H"}
    notes = [p for p in inverse["projection"] if p["text"] == "Original synthetic observation note 1"]
    assert len(notes) == 1 and len(notes[0]["target_refs"]) == 2


def test_absent_dictionary_meaning_does_not_map_time_notes_or_flags():
    raw, dictionary = case()
    raw = replace_field(raw, "OBX", 8, "A")
    dictionary.update(time_fields={}, note_scopes={}, flags={})
    result = map_message(raw, dictionary)
    observation, = resources(result, "Observation")
    assert not {"effectiveDateTime", "interpretation", "note"} & observation.keys()
    assert all(row["disposition"] != "mapped" for row in source_rows(result, 14, raw=raw))


@pytest.mark.parametrize("compact,iso,precision", [
    ("2026", "2026", 4), ("202602", "2026-02", 6), ("20260228", "2026-02-28", 8),
    ("20260102120000.120-0530", "2026-01-02T12:00:00.120-05:30", 17),
    ("20260102120000+1400", "2026-01-02T12:00:00+14:00", 14),
])
def test_timestamp_precision_source_projection(compact, iso, precision):
    assert timestamp_to_fhir(compact) == (iso, precision)
    raw, dictionary = case()
    result = map_message(replace_field(raw, "OBX", 14, compact), dictionary)
    observation, = resources(result, "Observation")
    assert observation["effectiveDateTime"] == iso
    assert any(p["text"] == compact for p in paired_inverse(result, dictionary)["projection"])


@pytest.mark.parametrize("compact", ["20260102120000", "2026010212+0000", "20260230", "20260102120000+1401", "20260102120000+0060", "0000"])
def test_bad_or_incompletely_zoned_time_abstains(compact):
    with pytest.raises(ValueError):
        timestamp_to_fhir(compact)
    raw, dictionary = case()
    result = map_message(replace_field(raw, "OBX", 14, compact), dictionary)
    observation, = resources(result, "Observation")
    assert "effectiveDateTime" not in observation


def test_inverse_rejects_hash_pointer_and_numeric_tamper():
    raw, dictionary = case()
    original = map_message(raw, dictionary)
    changed_dictionary = copy.deepcopy(dictionary)
    changed_dictionary["dictionary_id"] += "-changed"
    assert paired_inverse(original, changed_dictionary)["error"] == "dictionary_hash_mismatch"
    changed = copy.deepcopy(original)
    resources(changed, "Observation")[0]["valueQuantity"]["value"] = 99
    inverse = paired_inverse(changed, dictionary)
    assert any(p["reason_code"] == "numeric_target_changed" for p in inverse["unsupported"])
    changed = copy.deepcopy(original)
    changed["paired_projection"][0]["target_ref"] = "../../secret"
    inverse = paired_inverse(changed, dictionary)
    assert any(p["reason_code"] == "projection_not_bound_to_mapped_disposition" for p in inverse["unsupported"])


def test_inverse_observes_changed_links_without_claiming_pass():
    raw, dictionary = case()
    result = map_message(raw, dictionary)
    resources(result, "Observation")[0]["subject"]["reference"] = "Patient/changed"
    inverse = paired_inverse(result, dictionary)
    assert any(row["reference"] == "Patient/changed" for row in inverse["relations"])
    assert inverse["status"] == "partial" and inverse["runtime_verified"] is False
    assert "raw" not in inverse and "pass" not in inverse.values()


def test_inverse_ambiguous_dictionary_is_explicitly_unsupported():
    raw, dictionary = case()
    dictionary["identifier_systems"]["ALIAS"] = dictionary["identifier_systems"]["H7LOSSDEV"]
    inverse = paired_inverse(map_message(raw, dictionary), dictionary)
    assert any(p["reason_code"] == "inverse_dictionary_missing_or_ambiguous" for p in inverse["unsupported"])


def test_developer_dictionary_views_and_partition_are_not_independent_truth():
    authored = generate_case("dev-02", 49)
    dictionary = authored["dictionary"]
    assert authored["usage"] == "onboarding"
    assert authored["provenance"]["admission"] == "NOT_ADMITTED"
    assert dictionary["site_id"] == "dev-02" and isinstance(dictionary["report_code"], str)
    assert dictionary["bindings"] == {} and dictionary["z_segments"] == {}
    for token, coding in dictionary["codes"].items():
        if token in dictionary["tables"]["observation_codes"]:
            assert dictionary["tables"]["observation_codes"][token] == coding["code"]


def test_order_shape_limits_refuse_instead_of_relinking_source():
    raw, dictionary = case()
    lines = raw.split(b"\r")
    pid = next(line for line in lines if line.startswith(b"PID|"))
    obr = next(line for line in lines if line.startswith(b"OBR|"))
    obx = next(line for line in lines if line.startswith(b"OBX|"))
    # Wrong patient/order ordering must not become a guessed patient relation.
    swapped = [line for line in lines if not line.startswith((b"PID|", b"OBR|"))]
    swapped[1:1] = [obr, pid]
    assert map_message(b"\r".join(swapped), dictionary)["error"] == "order_before_patient"
    # Four observations in one order exceed the declared per-order support.
    crowded = raw + obx + b"\r" + obx + b"\r" + obx + b"\r"
    assert map_message(crowded, dictionary)["error"] == "unsupported_order_observation_count"
    # Duplicated patients and source observations lacking an order stay refused.
    assert map_message(raw + pid + b"\r", dictionary)["outcome"] == "refused"
    without_order = b"\r".join(line for line in lines if not line.startswith(b"OBR|"))
    assert map_message(without_order, dictionary)["outcome"] == "refused"


@pytest.mark.parametrize("mutation", ["source_hash", "missing_rules", "duplicate_disposition", "invalid_relation", "datatype_conflict", "numeric_extension"])
def test_inverse_malformed_or_unsupported_projection_never_reports_success(mutation):
    raw, dictionary = case()
    result = map_message(raw, dictionary)
    if mutation == "source_hash":
        result["raw_sha256"] = "0" * 64
    elif mutation == "missing_rules":
        result["paired_projection"] = []
    elif mutation == "duplicate_disposition":
        result["dispositions"].append(copy.deepcopy(result["dispositions"][0]))
    elif mutation == "invalid_relation":
        result["paired_relations"][0]["target_ref"] = "file:///private"
    elif mutation == "datatype_conflict":
        resources(result, "Observation")[0]["valueString"] = "alternative stuffing"
    else:
        resources(result, "Observation")[0]["extension"][0]["valueString"] = "not-a-number"
    inverse = paired_inverse(result, dictionary)
    assert inverse["status"] in {"partial", "unsupported"}
    assert inverse["unsupported"] or inverse["error"]
    assert inverse["runtime_verified"] is False


def test_original_development_design_is_deterministic_and_bounded():
    from h7loss.gen import generate_development_cases

    counts = {}
    hashes = set()
    mapped = 0
    for authored in generate_development_cases():
        key = (authored["site_id"], authored["usage"])
        counts[key] = counts.get(key, 0) + 1
        hashes.add(authored["raw_sha256"])
        repeated = generate_case(authored["site_id"], authored["index"])
        assert repeated["raw"] == authored["raw"]
        assert repeated["dictionary_sha256"] == authored["dictionary_sha256"]
        result = map_message(authored["raw"], authored["dictionary"])
        assert result["error"] is None  # Unsupported values abstain inside the bounded message.
        mapped += len(resources(result, "Observation"))
    assert len(hashes) == 400 and len(counts) == 16
    assert sorted(counts.values()) == [5] * 8 + [45] * 8
    assert mapped > 0
