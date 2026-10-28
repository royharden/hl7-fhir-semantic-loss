"""Builder unit expectations for original helpers; not independent semantic truth."""

from copy import deepcopy

import pytest

from h7loss.proposal.values import coding_entry, decode_value, render_value
from h7loss.v2 import parse_message


def _value_atoms(raw):
    return [atom for atom in parse_message(raw)["atoms"]
            if atom["source_ref"]["segment_index"] == 3 and atom["source_ref"]["field"] == 5]


def test_sn_consumes_nonempty_separator_but_not_empty_placeholders(dsl_case):
    raw, dictionary, *_ = dsl_case("SN", "^2^:^3")
    decoded = decode_value("SN", _value_atoms(raw), dictionary, "decimal_with_comparator")
    assert decoded["value"] == {"kind": "ratio", "numerator": "2", "denominator": "3"}
    assert {ref["component"] for ref in decoded["consumed"]} == {2, 3, 4}
    assert all(raw[ref["byte_start"]:ref["byte_end"]] for ref in decoded["consumed"])


def test_cwe_display_ref_only_when_its_meaning_is_emitted(dsl_case):
    raw, dictionary, *_ = dsl_case("CWE", "BLUE^Synthetic blue category^LOCAL")
    matched = decode_value("CWE", _value_atoms(raw), dictionary, "dictionary_lookup")
    assert {ref["component"] for ref in matched["consumed"]} == {1, 2, 3}
    raw, dictionary, *_ = dsl_case("CWE", "BLUE^different source display^LOCAL")
    different = decode_value("CWE", _value_atoms(raw), dictionary, "dictionary_lookup")
    assert {ref["component"] for ref in different["consumed"]} == {1, 3}


def test_mixed_raw_or_repetition_refs_cannot_be_combined(dsl_case):
    raw, dictionary, *_ = dsl_case("SN", ">^5")
    atoms = _value_atoms(raw)
    changed = deepcopy(atoms)
    changed[1]["source_ref"]["repetition"] = 2
    with pytest.raises(ValueError, match="mixed_value_repetitions"):
        decode_value("SN", changed, dictionary, "decimal_with_comparator")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e3", "0.123456789012345678901", " 1"])
def test_numeric_lexemes_cannot_silently_change_value(value, dsl_case):
    raw, dictionary, *_ = dsl_case("NM", value)
    with pytest.raises(ValueError):
        decode_value("NM", _value_atoms(raw), dictionary, "decimal_with_comparator")


def test_namespace_cannot_be_relabelled_by_dictionary_entry(dsl_case):
    _raw, dictionary, *_ = dsl_case()
    entry = {"code": "BLUE", "system": "urn:builder-test:unreleased"}
    with pytest.raises(ValueError, match="coding_authority_conflict"):
        coding_entry(entry, "LOCAL", dictionary)


def test_coding_result_is_detached_from_mutable_dictionary(dsl_case):
    _raw, dictionary, *_ = dsl_case()
    entry = dictionary["value_codes"]["BLUE"]
    result = coding_entry(entry, "LOCAL", dictionary)
    result["code"] = "changed output"
    assert entry["code"] == "BLUE"


def test_ratio_unit_requires_released_side_policy():
    with pytest.raises(ValueError, match="ratio_unit_roles_not_released"):
        render_value({"kind": "ratio", "numerator": "2", "denominator": "3"}, "unit")


@pytest.mark.parametrize("value", [
    {"kind": "quantity", "value": "5", "comparator": None, "extra": "invention"},
    {"kind": "quantity", "value": "5", "comparator": "about"},
    {"kind": "range", "low": "4", "high": "1"},
    {"kind": "ratio", "numerator": "1", "denominator": "0"},
])
def test_render_refuses_extra_or_conflicting_value_semantics(value):
    with pytest.raises(ValueError):
        render_value(value)
