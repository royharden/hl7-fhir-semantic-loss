"""Builder-authored transform seam cases, not independent semantic expectations."""

import pytest

from h7loss.proposal import execute_proposal


def test_bound_non_obx_decimal_uses_the_renderer_quantity_contract(dsl_case):
    """Catches the missing kind discriminator in the generic decimal transform."""
    raw, dictionary, rules, rule, proposal = dsl_case(tail="ZNU|>5.25")
    rules[:] = [r for r in rules if r.get("target") != "observation.value"]
    dictionary["bindings"]["ZNU.1.1.1"] = "observation.value"
    rules.append(rule("ZNU", "observation", 1, "observation.value", "decimal_with_comparator"))
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "ok", result["error"]
    observations = [e["resource"] for e in result["bundle"]["entry"]
                    if e["resource"]["resourceType"] == "Observation"]
    assert observations[0]["valueQuantity"] == {"value": 5.25, "comparator": ">"}
    for row in result["dispositions"]:
        source = row["source_ref"]
        if raw[source["byte_start"]:source["byte_end"]] == b"alpha":
            assert row["disposition"] == "abstain"
        for pointer in row["target_refs"]:
            target = result["bundle"]
            for token in pointer.split("/")[1:]:
                target = target[int(token)] if isinstance(target, list) else target[token]


@pytest.mark.parametrize("key", ["tables", "codes", "flags", "bindings"])
def test_malformed_dictionary_maps_return_a_structured_refusal(dsl_case, key):
    raw, dictionary, _rules, _rule, proposal = dsl_case()
    dictionary[key] = []
    result = execute_proposal(raw, dictionary, proposal())
    assert result["outcome"] == "error"
    assert result["bundle"] is None
    assert result["error"].startswith("dictionary_mapping_required:")
