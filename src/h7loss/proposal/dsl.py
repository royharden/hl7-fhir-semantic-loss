"""Original constrained DSL. Unknown semantics produce refusal, never guessed mappings.

Selectors address one exact lexical SourceRef. Repeated values require separate rules;
the executor allocates resources from parser group identities rather than model paths.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

TRANSFORMS = frozenset({
    "copy_text", "decimal_with_comparator", "timestamp_preserve_precision",
    "dictionary_lookup", "unit_from_dictionary", "repeated_value", "join_components",
    "constant_from_dictionary", "declare_drop", "abstain",
})
TARGETS = frozenset({
    "patient.id", "observation.code", "observation.system", "observation.value",
    "observation.comparator", "observation.unit", "observation.status", "observation.flag",
    "observation.time", "observation.precision", "observation.note", "report.status",
})
REF_KEYS = frozenset({"raw_sha256", "segment_index", "group_id", "field", "repetition",
                      "component", "subcomponent", "byte_start", "byte_end"})
RULE_KEYS = frozenset({"source", "target", "transform", "guard", "dictionary", "reason"})
SELECTOR_KEYS = frozenset({"segment", "scope", "field", "repetition", "component", "subcomponent"})
PROPOSAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["version", "site_id", "dictionary_sha256", "rules"],
    "properties": {
        "version": {"const": 1}, "site_id": {"type": "string", "minLength": 1},
        "dictionary_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "rules": {"type": "array", "minItems": 1, "maxItems": 64, "items": {
            "type": "object", "additionalProperties": False, "required": ["source", "transform"],
            "properties": {
                "source": {"type": "object", "additionalProperties": False,
                           "required": sorted(SELECTOR_KEYS), "properties": {
                               "segment": {"type": "string", "pattern": "^[A-Z0-9]{3}$"},
                               "scope": {"enum": ["message", "patient", "order", "observation"]},
                               "field": {"type": "integer", "minimum": 1},
                               "repetition": {"oneOf": [{"type": "integer", "minimum": 1}, {"const": "all"}]},
                               "component": {"oneOf": [{"type": "integer", "minimum": 1}, {"const": "all"}]},
                               "subcomponent": {"type": "integer", "minimum": 1}}},
                "transform": {"enum": sorted(TRANSFORMS)}, "target": {"enum": sorted(TARGETS)},
                "guard": {"type": "string"}, "dictionary": {"type": "string", "minLength": 1},
                "reason": {"type": "string", "minLength": 1}},
            "allOf": [
                {"if": {"properties": {"transform": {"enum": ["declare_drop", "abstain"]}}},
                 "then": {"required": ["reason"], "not": {"required": ["target"]}},
                 "else": {"required": ["target"]}},
                {"if": {"properties": {"source": {"properties": {"repetition": {"const": "all"}}}}},
                 "then": {"properties": {"transform": {"const": "repeated_value"}}}},
                {"if": {"properties": {"source": {"properties": {"component": {"const": "all"}}}}},
                 "then": {"properties": {"transform": {"const": "join_components"}}}}
            ]}}
    }
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_proposal(proposal: dict) -> dict:
    """Return schema errors without executing expressions or accepting extension keys."""
    errors: list[str] = []
    try:
        if len(_canonical(proposal)) > 32768:
            errors.append("proposal_too_large")
    except (ValueError, TypeError, RecursionError):
        return {"valid": False, "errors": ["not_finite_json"]}
    if not isinstance(proposal, dict) or set(proposal) != {"version", "site_id", "dictionary_sha256", "rules"}:
        return {"valid": False, "errors": ["proposal_keys"]}
    if type(proposal["version"]) is not int or proposal["version"] != 1:
        errors.append("version")
    if not isinstance(proposal["site_id"], str) or not proposal["site_id"]:
        errors.append("site_id")
    digest = proposal["dictionary_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        errors.append("dictionary_sha256")
    rules = proposal["rules"]
    if not isinstance(rules, list) or not 1 <= len(rules) <= 64:
        return {"valid": False, "errors": errors + ["rules_count"]}
    for index, rule in enumerate(rules):
        prefix = f"rule:{index}:"
        if not isinstance(rule, dict) or set(rule) - RULE_KEYS or not {"source", "transform"} <= set(rule):
            errors.append(prefix + "keys")
            continue
        transform = rule["transform"]
        if not isinstance(transform, str) or transform not in TRANSFORMS:
            errors.append(prefix + "transform")
            continue
        target = rule.get("target")
        if transform not in {"declare_drop", "abstain"} and (not isinstance(target, str) or target not in TARGETS):
            errors.append(prefix + "target")
        if transform in {"declare_drop", "abstain"} and ("target" in rule or not isinstance(rule.get("reason"), str) or not rule["reason"]):
            errors.append(prefix + "disposition")
        source = rule["source"]
        if not isinstance(source, dict) or set(source) not in (REF_KEYS, SELECTOR_KEYS):
            errors.append(prefix + "source_keys")
        elif set(source) == REF_KEYS:
            for key in REF_KEYS - {"group_id", "raw_sha256"}:
                if type(source[key]) is not int or source[key] < 0:
                    errors.append(prefix + key)
            if not isinstance(source["group_id"], str) or not source["group_id"]:
                errors.append(prefix + "unbound_group")
            if not isinstance(source["raw_sha256"], str) or len(source["raw_sha256"]) != 64:
                errors.append(prefix + "source_hash")
        else:
            if not isinstance(source["segment"], str) or not re.fullmatch(r"[A-Z0-9]{3}", source["segment"]):
                errors.append(prefix + "segment")
            if source["scope"] not in ("message", "patient", "order", "observation"):
                errors.append(prefix + "scope")
            for key in ("field", "repetition", "component", "subcomponent"):
                if key == "repetition" and source[key] == "all" and transform == "repeated_value":
                    continue
                if key == "component" and source[key] == "all" and transform == "join_components":
                    continue
                if type(source[key]) is not int or source[key] < 1:
                    errors.append(prefix + key)
        if "guard" in rule and not isinstance(rule["guard"], str):
            errors.append(prefix + "guard_literal_only")
        if "dictionary" in rule and (not isinstance(rule["dictionary"], str) or not rule["dictionary"]):
            errors.append(prefix + "dictionary_key")
    return {"valid": not errors, "errors": errors}


def compile_proposal(proposal: dict) -> dict:
    checked = validate_proposal(proposal)
    if not checked["valid"]:
        raise ValueError("invalid_proposal:" + ",".join(checked["errors"]))
    # JSON roundtrip breaks caller aliases; compiled bytes carry no callables/paths.
    frozen = json.loads(_canonical(proposal))
    return {"proposal": frozen, "sha256": hashlib.sha256(_canonical(frozen)).hexdigest()}


def _transform(rule: dict, text: str, dictionary: dict, components: list[str] | None = None) -> Any:
    name = rule["transform"]
    if name in {"copy_text", "repeated_value"}:
        return text
    if name in {"dictionary_lookup", "unit_from_dictionary", "constant_from_dictionary"}:
        tables = dictionary.get("tables", {})
        table = tables.get(rule.get("dictionary"))
        if not isinstance(table, dict):
            raise ValueError("missing_dictionary_table")
        key = "constant" if name == "constant_from_dictionary" else text
        if key not in table or not isinstance(table[key], str) or not table[key]:
            raise ValueError("unknown_dictionary_meaning")
        return table[key]
    if name == "join_components":
        # Join is deliberately bounded by an explicit released table; no model
        # expression or arbitrary separator language is interpreted.
        table = dictionary.get("tables", {}).get(rule.get("dictionary"))
        if not isinstance(table, dict) or not isinstance(table.get("separator"), str) or len(table["separator"]) > 32 or components is None:
            raise ValueError("join_separator_not_released")
        return table["separator"].join(components)
    if name == "timestamp_preserve_precision":
        matched = re.fullmatch(r"(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\.\d{1,6})?([+-]\d{4})?", text)
        if not matched:
            raise ValueError("unsupported_timestamp")
        year, month, day, hour, minute, second, fraction, offset = matched.groups()
        if (fraction and second is None) or (offset and hour is None):
            raise ValueError("timestamp_precision")
        # Validate actual calendar/range while preserving absent components.
        datetime(int(year), int(month or 1), int(day or 1), int(hour or 0), int(minute or 0), int(second or 0))
        output = year + ("-" + month if month else "") + ("-" + day if day else "")
        if hour:
            # FHIR datetime time requires seconds and zone; partial time must abstain.
            if not minute or not second or not offset:
                raise ValueError("fhir_timestamp_cannot_preserve_partial_time")
            if int(offset[1:3]) > 14 or int(offset[3:]) > 59 or (int(offset[1:3]) == 14 and offset[3:] != "00"):
                raise ValueError("timestamp_offset")
            output += "T" + hour + ":" + minute + ":" + second + (fraction or "") + offset[:3] + ":" + offset[3:]
        return output
    if name == "decimal_with_comparator":
        comparator = next((c for c in ("<=", ">=", "<", ">") if text.startswith(c)), None)
        number = text[len(comparator):] if comparator else text
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", number) or len(number) > 128:
            raise ValueError("unsupported_decimal")
        try:
            value = Decimal(number)
        except InvalidOperation as exc:
            raise ValueError("unsupported_decimal") from exc
        if not value.is_finite():
            raise ValueError("unsupported_decimal")
        return {"value": str(value), "comparator": comparator}
    raise ValueError("unsupported_transform")


def _scope(group: str) -> str:
    return "observation" if "/observation:" in group else "order" if "/order:" in group else "patient" if group.startswith("patient:") else "message"


def _matches(selector: dict, ref: dict, tags: dict) -> bool:
    if set(selector) == REF_KEYS:
        return selector == ref
    return (tags.get(ref["segment_index"]) == selector["segment"]
            and _scope(ref["group_id"]) == selector["scope"]
            and all(selector[k] == ref[k] for k in ("field", "subcomponent"))
            and (selector["component"] == "all" or selector["component"] == ref["component"])
            and (selector["repetition"] == "all" or selector["repetition"] == ref["repetition"]))


def _resource_id(group: str, kind: str, repetition: int = 0) -> str:
    return kind.lower() + "-" + hashlib.sha256(f"{group}:{repetition}".encode()).hexdigest()[:24]


def _number(text: str) -> int | float:
    value = Decimal(text)
    number = int(value) if value == value.to_integral_value() else float(value)
    if Decimal(str(number)) != value:
        raise ValueError("numeric_precision_loss")
    return number


def _resources(slots: dict, dictionary: dict) -> list[dict]:
    """Construct resources/relations from parser groups, never model-written paths."""
    groups = sorted({group for group, _target, _rep in slots})
    resources: list[dict] = []
    patient_id = _resource_id("patient:0", "Patient")
    has_patient = ("patient:0", "patient.id", 0) in slots
    if slots and not has_patient:
        raise ValueError("missing_patient_identifier")
    if has_patient:
        identifier = slots[("patient:0", "patient.id", 0)]
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("invalid_patient_identifier")
        resources.append({"resourceType": "Patient", "id": patient_id, "identifier": [{"value": identifier}]})
    reports: dict[str, dict] = {}
    for group in groups:
        if _scope(group) == "order":
            status = slots.get((group, "report.status", 0))
            code = dictionary.get("report_code")
            if status not in {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended", "cancelled", "entered-in-error", "unknown"} or not isinstance(code, str) or not code:
                raise ValueError("report_required_fields_missing_or_invalid")
            report = {"resourceType": "DiagnosticReport", "id": _resource_id(group, "DiagnosticReport"),
                      "status": status, "code": {"text": code}, "subject": {"reference": "Patient/" + patient_id}, "result": []}
            reports[group] = report
            resources.append(report)
    for group in groups:
        if _scope(group) != "observation":
            continue
        common = {target: value for (g, target, rep), value in slots.items() if g == group and rep == 0}
        repeated = {rep: value for (g, target, rep), value in slots.items() if g == group and target == "observation.value" and rep > 0}
        if repeated and "observation.value" in common:
            raise ValueError("conflicting_scalar_and_repeated_value")
        variants = repeated or {0: common.get("observation.value")}
        for repetition, value in sorted(variants.items()):
            if common.get("observation.status") not in {"registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error", "unknown"} or not isinstance(common.get("observation.code"), str):
                raise ValueError("observation_required_fields_missing_or_invalid")
            observation = {"resourceType": "Observation", "id": _resource_id(group, "Observation", repetition),
                           "status": common["observation.status"], "code": {"coding": [{"code": common["observation.code"]}]},
                           "subject": {"reference": "Patient/" + patient_id}}
            if "observation.system" in common:
                observation["code"]["coding"][0]["system"] = common["observation.system"]
            if isinstance(value, dict):
                quantity = {"value": _number(value["value"])}
                comparator = value.get("comparator") or common.get("observation.comparator")
                if value.get("comparator") and common.get("observation.comparator") and value["comparator"] != common["observation.comparator"]:
                    raise ValueError("conflicting_comparator")
                if comparator:
                    if comparator not in {"<", "<=", ">=", ">"}:
                        raise ValueError("invalid_comparator")
                    quantity["comparator"] = comparator
                if "observation.unit" in common:
                    quantity["unit"] = common["observation.unit"]
                observation["valueQuantity"] = quantity
            elif isinstance(value, str):
                if "observation.unit" in common or "observation.comparator" in common:
                    raise ValueError("unit_or_comparator_requires_quantity")
                observation["valueString"] = value
            elif value is not None:
                raise ValueError("unsupported_value")
            elif "observation.unit" in common or "observation.comparator" in common:
                raise ValueError("orphan_quantity_metadata")
            if "observation.time" in common:
                observation["effectiveDateTime"] = common["observation.time"]
            if "observation.precision" in common:
                raise ValueError("precision_target_requires_released_extension")
            if "observation.flag" in common:
                observation["interpretation"] = [{"text": common["observation.flag"]}]
            notes = [value for (g, target, _rep), value in slots.items() if g == group and target == "observation.note"]
            if notes:
                observation["note"] = [{"text": text} for text in notes]
            resources.append(observation)
            order_group = group.split("/observation:", 1)[0]
            if order_group in reports:
                reports[order_group]["result"].append({"reference": "Observation/" + observation["id"]})
    return resources


def execute_proposal(raw: bytes, dictionary: dict, proposal: dict) -> dict:
    """Execute exact bound rules; fail the entire output on any conflicting mapping.

    Parser refs are authoritative lexical coordinates. Callers cannot make a valid
    pointer simply by supplying a matching byte range from another segment/group.
    """
    result: dict = {"case_id": hashlib.sha256(raw).hexdigest(), "arm_id": "A",
                    "outcome": "error", "bundle": None, "dispositions": [], "error": None}
    try:
        compiled = compile_proposal(proposal)
        if len(raw) > 1048576:
            raise ValueError("message_too_large")
        if hashlib.sha256(_canonical(dictionary)).hexdigest() != proposal["dictionary_sha256"]:
            raise ValueError("stale_dictionary")
        if not isinstance(dictionary, dict) or not isinstance(dictionary.get("tables", {}), dict) or not isinstance(dictionary.get("bindings", {}), dict):
            raise ValueError("dictionary_mapping_required")
        if dictionary.get("site_id") != proposal["site_id"]:
            raise ValueError("site_mismatch")
        from h7loss.v2 import parse_message

        parsed = parse_message(raw)
        if parsed.get("unsupported") or parsed.get("errors"):
            raise ValueError("unsupported_parser_input")
        refs = parsed.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError("parser_source_refs_unavailable")
        available = {_canonical(ref): ref for ref in refs if isinstance(ref, dict)}
        assigned: dict[tuple[str, str, int], Any] = {}
        used: set[bytes] = set()
        tags = {segment["index"]: segment["tag"] for segment in parsed["segments"]}
        atoms = {_canonical(atom["source_ref"]): atom for atom in parsed.get("atoms", [])}
        for rule in compiled["proposal"]["rules"]:
            matching = [ref for ref in refs if _matches(rule["source"], ref, tags)]
            if set(rule["source"]) == REF_KEYS and not matching:
                raise ValueError("fake_source_pointer")
            for ref in matching:
                key = _canonical(ref)
                siblings = [ref]
                if rule["transform"] == "join_components":
                    siblings = [r for r in matching if all(r[k] == ref[k] for k in ("segment_index", "field", "repetition"))]
                    if ref != siblings[0]:
                        continue
                if ref["raw_sha256"] != result["case_id"]:
                    raise ValueError("source_hash_mismatch")
                start, end = ref["byte_start"], ref["byte_end"]
                if not 0 <= start <= end <= len(raw):
                    raise ValueError("source_bounds")
                atom = atoms.get(key)
                if not atom or atom.get("unsupported") or atom.get("null") or atom.get("empty"):
                    continue  # Explicit no_bound_rule abstention below, including null.
                text = atom.get("text")
                if not isinstance(text, str):
                    raise ValueError("undecodable_source")
                if rule["transform"] == "join_components":
                    sibling_atoms = [atoms[_canonical(r)] for r in siblings]
                    if any(a.get("unsupported") or a.get("null") or not isinstance(a.get("text"), str) for a in sibling_atoms):
                        raise ValueError("join_unsupported_atom")
                    text = parsed["delimiters"]["component"].join(a["text"] for a in sibling_atoms)
                if "guard" in rule and text != rule["guard"]:
                    continue
                if any(_canonical(r) in used for r in siblings):
                    raise ValueError("conflicting_source_dispositions")
                used.update(_canonical(r) for r in siblings)
                transform = rule["transform"]
                disposition = {"source_ref": ref, "disposition": "abstain", "reason_code": "unknown",
                               "target_refs": [], "evidence_refs": [proposal["dictionary_sha256"]]}
                if transform in {"declare_drop", "abstain"}:
                    disposition.update(disposition="declared_drop" if transform == "declare_drop" else "abstain",
                                       reason_code=rule["reason"])
                else:
                    target = rule["target"]
                    # Unknown Z meanings require an explicit dictionary target binding.
                    if tags[ref["segment_index"]].startswith("Z"):
                        for bound in siblings:
                            binding = f"{tags[bound['segment_index']]}.{bound['field']}.{bound['component']}.{bound['subcomponent']}"
                            if dictionary.get("bindings", {}).get(binding) != target:
                                raise ValueError("undocumented_z_meaning")
                    expected_scope = "patient" if target.startswith("patient.") else "order" if target.startswith("report.") else "observation"
                    if _scope(ref["group_id"]) != expected_scope:
                        raise ValueError("unbound_target_group")
                    compatible = {
                        "decimal_with_comparator": {"observation.value"},
                        "timestamp_preserve_precision": {"observation.time"},
                        "unit_from_dictionary": {"observation.unit"},
                        "repeated_value": {"observation.value", "observation.note"},
                    }
                    if transform in compatible and target not in compatible[transform]:
                        raise ValueError("incompatible_target_transform")
                    components = [atoms[_canonical(r)]["text"] for r in siblings] if transform == "join_components" else None
                    value = _transform(rule, text, dictionary, components)
                    rep = ref["repetition"] if transform == "repeated_value" else 0
                    slot = (ref["group_id"], target, rep)
                    if slot in assigned:
                        raise ValueError("conflicting_target")
                    assigned[slot] = value
                    disposition.update(disposition="mapped", reason_code="dsl_rule",
                                       _target=target, _group=ref["group_id"], _rep=rep)
                result["dispositions"].append(disposition)
                for sibling in siblings[1:]:
                    result["dispositions"].append({**disposition, "source_ref": sibling,
                                                   "target_refs": [], "evidence_refs": list(disposition["evidence_refs"])})
        resources = _resources(assigned, dictionary)
        for disposition in result["dispositions"]:
            if disposition["disposition"] != "mapped":
                continue
            target = disposition.pop("_target")
            group = disposition.pop("_group")
            repetition = disposition.pop("_rep")
            kind = "Patient" if target.startswith("patient.") else "DiagnosticReport" if target.startswith("report.") else "Observation"
            repetitions = sorted({rep for (g, slot, rep) in assigned if g == group and slot == "observation.value" and rep > 0}) or [0]
            if kind != "Observation":
                repetitions = [0]
            elif target == "observation.value" and repetition:
                repetitions = [repetition]
            for rep in repetitions:
                resource_id = _resource_id(group, kind, rep)
                resource = next(r for r in resources if r["resourceType"] == kind and r["id"] == resource_id)
                path = {
                    "patient.id": "identifier/0/value", "report.status": "status",
                    "observation.code": "code/coding/0/code", "observation.system": "code/coding/0/system",
                    "observation.status": "status", "observation.time": "effectiveDateTime",
                    "observation.unit": "valueQuantity/unit", "observation.comparator": "valueQuantity/comparator",
                    "observation.flag": "interpretation/0/text",
                }.get(target)
                if target == "observation.value":
                    path = "valueQuantity/value" if "valueQuantity" in resource else "valueString"
                if target == "observation.note":
                    note_slots = [slot for slot in assigned if slot[0] == group and slot[1] == target]
                    path = f"note/{note_slots.index((group, target, repetition))}/text"
                if path is None:
                    raise ValueError("unsupported_target_pointer")
                disposition["target_refs"].append(f"{kind}/{resource_id}/{path}")
                if target == "observation.value" and resource.get("valueQuantity", {}).get("comparator"):
                    disposition["target_refs"].append(f"{kind}/{resource_id}/valueQuantity/comparator")
        # Every untouched lexical atom is explicitly abstained. No silent omissions.
        for key, ref in available.items():
            if key not in used:
                result["dispositions"].append({"source_ref": ref, "disposition": "abstain",
                                               "reason_code": "no_bound_rule", "target_refs": [], "evidence_refs": []})
        result.update(outcome="ok", bundle={"resourceType": "Bundle", "type": "collection",
                                           "entry": [{"resource": r} for r in resources]},
                      mapping_sha256=compiled["sha256"])
    except (ValueError, TypeError, KeyError, UnicodeError, ImportError, RecursionError) as exc:
        # Partial mappings cannot survive an error as apparently mapped evidence.
        result.update(error=str(exc), bundle=None, dispositions=[])
    return result
