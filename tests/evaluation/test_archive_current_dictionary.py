"""Builder-only producer/archive seam regressions; no independent gold or data."""
import copy
import pytest
from evaluation.archive import validate_dictionary
from evaluation.common import Refusal, digest
from h7loss.gen.development import development_dictionary


@pytest.mark.parametrize("site", [f"dev-{i:02d}" for i in range(1, 9)])
def test_current_developer_dictionary_preserves_exact_release(site):
    value = development_dictionary(site)
    original_hash = digest(value)
    assert validate_dictionary(value) is value
    assert digest(value) == original_hash


def test_current_dictionary_still_refuses_undeclared_seed():
    value = development_dictionary()
    value["hidden_seed"] = 4
    with pytest.raises(Refusal):
        validate_dictionary(value)


def test_scalar_view_cannot_change_canonical_code():
    value = development_dictionary()
    key = next(iter(value["tables"]["observation_codes"]))
    value["tables"]["observation_codes"][key] = "different"
    with pytest.raises(Refusal):
        validate_dictionary(value)


def test_scalar_flag_view_cannot_change_canonical_flag():
    value = development_dictionary()
    value["tables"]["flags"]["A"] = "different"
    with pytest.raises(Refusal):
        validate_dictionary(value)


def test_unreleased_z_binding_is_not_admitted():
    value = development_dictionary()
    value["bindings"] = {"ZDV.1.1.1": "patient.id"}
    with pytest.raises(Refusal):
        validate_dictionary(value)


def test_reconstructive_time_field_stays_refused():
    value = development_dictionary()
    value["time_fields"]["hidden_profile"] = "opaque"
    with pytest.raises(Refusal):
        validate_dictionary(value)


def test_unknown_note_scope_stays_unsupported():
    value = development_dictionary()
    value["note_scopes"]["NTE.3"] = ["unreleased"]
    with pytest.raises(Refusal):
        validate_dictionary(value)


@pytest.mark.parametrize("field,value", [("time_fields", {"ZDV.1": "report_effective"}), ("note_scopes", {"ZDV.1": ["order"]})])
def test_unreleased_z_time_and_scope_conventions_refuse(field, value):
    dictionary = development_dictionary()
    dictionary[field].update(value)
    with pytest.raises(Refusal):
        validate_dictionary(dictionary)


def test_time_mapping_cannot_swap_released_roles():
    dictionary = development_dictionary()
    dictionary["time_fields"]["OBR.7"] = "observation_effective"
    with pytest.raises(Refusal):
        validate_dictionary(dictionary)
