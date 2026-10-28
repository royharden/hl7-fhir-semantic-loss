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

from .values import coding_entry, decode_value, render_value

TRANSFORMS = frozenset({
    "copy_text", "decimal_with_comparator", "timestamp_preserve_precision",
    "dictionary_lookup", "unit_from_dictionary", "repeated_value", "join_components",
    "constant_from_dictionary", "declare_drop", "abstain",
})
TARGETS = frozenset({
    "patient.id", "patient.system", "observation.code", "observation.system", "observation.value",
    "observation.comparator", "observation.unit", "observation.status", "observation.flag",
    "observation.time", "observation.precision", "observation.note", "report.status", "report.code", "report.system",
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
                 "then": {"properties": {"transform": {"enum": ["join_components", "decimal_with_comparator", "dictionary_lookup", "repeated_value", "unit_from_dictionary"]}}}}
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
                if key == "component" and source[key] == "all" and transform in {"join_components", "decimal_with_comparator", "dictionary_lookup", "repeated_value", "unit_from_dictionary"}:
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
        table = dictionary.get(rule.get("dictionary"), tables.get(rule.get("dictionary")))
        if not isinstance(table, dict):
            raise ValueError("missing_dictionary_table")
        key = "constant" if name == "constant_from_dictionary" else text
        if name=="dictionary_lookup" and rule.get("target")=="observation.flag" and isinstance(table.get(key),dict):
            entry=table[key]
            if not all(isinstance(entry.get(k),str) and entry[k] for k in ("system","code")) or ("display" in entry and not isinstance(entry["display"],str)):
                raise ValueError("invalid_flag_dictionary_entry")
            return {k:v for k,v in entry.items() if k in {"system","code","display"}}
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
        return {"kind": "quantity", "value": str(value), "comparator": comparator}
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


def _resources(slots: dict, dictionary: dict) -> list[dict]:
    """Build only explicit supplied fields; resource relationships follow parser groups."""
    groups = sorted({group for group, _target, _rep in slots})
    resources: list[dict] = []
    patient_id = _resource_id("patient:0", "Patient")
    identity = slots.get(("patient:0", "patient.id", 0))
    if slots and (not isinstance(identity, str) or not identity):
        raise ValueError("missing_patient_identifier")
    if identity:
        identifier = {"value": identity}
        system = slots.get(("patient:0", "patient.system", 0))
        if system is not None:
            if system not in dictionary.get("identifier_systems", {}).values():
                raise ValueError("identifier_namespace_not_released")
            identifier["system"] = system
        resources.append({"resourceType": "Patient", "id": patient_id, "identifier": [identifier]})
    reports = {}
    for group in groups:
        if _scope(group) != "order":
            continue
        status = slots.get((group, "report.status", 0))
        code = slots.get((group, "report.code", 0), dictionary.get("report_code"))
        if status not in {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended", "cancelled", "entered-in-error", "unknown"} or not code:
            raise ValueError("report_required_fields_missing_or_invalid")
        # The accepted producer publishes report_code as an original panel display,
        # not a coding object or coding system. Preserve that exact representation.
        if (group,"report.code",0) not in slots and (group,"report.system",0) not in slots and isinstance(code,str) and code.strip():
            concept = {"text":code}
        else:
            concept = _concept(code, slots.get((group, "report.system", 0)), dictionary)
        report = {"resourceType": "DiagnosticReport", "id": _resource_id(group, "DiagnosticReport"),
                  "status": status, "code": concept, "subject": {"reference": "Patient/"+patient_id}, "result": []}
        reports[group] = report
        resources.append(report)
    for group in groups:
        if _scope(group) != "observation":
            continue
        common = {target: value for (g,target,rep),value in slots.items() if g == group and rep == 0}
        variants = {rep: value for (g,target,rep),value in slots.items() if g == group and target == "observation.value"}
        if not variants:
            raise ValueError("observation_value_not_supplied")
        if common.get("observation.status") not in {"registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error", "unknown"}:
            raise ValueError("observation_status_unknown")
        concept = _concept(common.get("observation.code"), common.get("observation.system"), dictionary)
        for repetition,value in sorted(variants.items()):
            observation = {"resourceType":"Observation", "id":_resource_id(group,"Observation",repetition),
                           "status":common["observation.status"], "code":concept,
                           "subject":{"reference":"Patient/"+patient_id}}
            if "observation.comparator" in common:
                if not isinstance(value,dict) or value.get("kind") != "quantity":
                    raise ValueError("comparator_requires_quantity")
                value = dict(value)
                comparator = common["observation.comparator"]
                if comparator not in {"<","<=",">",">="} or value.get("comparator") not in (None,comparator):
                    raise ValueError("conflicting_comparator")
                value["comparator"] = comparator
            observation.update(render_value(value, common.get("observation.unit")))
            if "observation.time" in common:
                observation["effectiveDateTime"] = common["observation.time"]
            if "observation.precision" in common:
                raise ValueError("precision_target_requires_released_extension")
            if "observation.flag" in common:
                flag=common["observation.flag"]
                observation["interpretation"]=[{"coding":[flag]}] if isinstance(flag,dict) else [{"text":flag}]
            notes=[v for (g,target,_rep),v in slots.items() if g == group and target == "observation.note"]
            if notes:
                observation["note"]=[{"text":v} for v in notes]
            resources.append(observation)
            order_group=group.split("/observation:",1)[0]
            if order_group in reports:
                reports[order_group]["result"].append({"reference":"Observation/"+observation["id"]})
    return resources


def _concept(code: Any, system: Any, dictionary: dict) -> dict:
    if isinstance(code, dict):
        if system is not None and system != code.get("system"):
            raise ValueError("conflicting_coding_namespace")
        if not all(isinstance(code.get(k),str) and code[k] for k in ("code","system")):
            raise ValueError("coding_dictionary_entry_required")
        return {"coding":[code]}
    if isinstance(code,str) and isinstance(system,str):
        for entry in dictionary.get("codes",{}).values():
            if isinstance(entry,dict) and entry.get("code") == code and entry.get("system") == system:
                return {"coding":[{k:v for k,v in entry.items() if k in {"code","system","display"}}]}
    raise ValueError("released_coding_namespace_required")


def _row(ref: dict, reason: str = "no_bound_rule") -> dict:
    return {"source_ref":ref,"disposition":"abstain","reason_code":reason,"target_refs":[],"evidence_refs":[]}


def _paths(bundle: dict, group: str, target: str, rep: int, slots: dict) -> list[str]:
    kind="Patient" if target.startswith("patient.") else "DiagnosticReport" if target.startswith("report.") else "Observation"
    repetitions=sorted({r for g,t,r in slots if g == group and t == "observation.value"}) if kind == "Observation" else [0]
    if target == "observation.value":
        repetitions=[rep]
    paths=[]
    for repetition in repetitions:
        identity=_resource_id(group,kind,repetition)
        position=next((i for i,e in enumerate(bundle["entry"]) if e["resource"]["resourceType"] == kind and e["resource"]["id"] == identity),None)
        if position is None:
            raise ValueError("emitted_target_resource_missing")
        resource=bundle["entry"][position]["resource"]
        suffix={"patient.id":"identifier/0/value","patient.system":"identifier/0/system",
                "report.status":"status","report.code":"code/coding/0","report.system":"code/coding/0/system",
                "observation.code":"code/coding/0","observation.system":"code/coding/0/system",
                "observation.status":"status","observation.unit":"valueQuantity",
                "observation.comparator":"valueQuantity/comparator","observation.flag":"interpretation/0",
                "observation.time":"effectiveDateTime"}.get(target)
        if target == "observation.value":
            suffix=next((key for key in resource if key.startswith("value")),None)
        if target == "observation.unit" and "valueRange" in resource:
            paths.extend([f"/entry/{position}/resource/valueRange/{bound}" for bound in ("low","high")])
            continue
        if target == "observation.note":
            note_slots=[slot for slot in slots if slot[0] == group and slot[1] == target]
            suffix=f"note/{note_slots.index((group,target,rep))}/text"
        if suffix is None:
            raise ValueError("unsupported_target_pointer")
        paths.append(f"/entry/{position}/resource/{suffix}")
    for path in paths:
        current=bundle
        for token in path.split("/")[1:]:
            current=current[int(token)] if isinstance(current,list) else current[token]
    return paths


def execute_proposal(raw: bytes, dictionary: dict, proposal: dict) -> dict:
    """Bind every mapped row to an actually emitted, resolvable JSON pointer."""
    result={"case_id":hashlib.sha256(raw).hexdigest(),"arm_id":"A","outcome":"error",
            "bundle":None,"dispositions":[],"error":None}
    refs=[]
    try:
        compiled=compile_proposal(proposal)
        if len(raw)>1048576:
            raise ValueError("message_too_large")
        if not isinstance(dictionary,dict):
            raise ValueError("dictionary_mapping_required")
        for name in ("tables","bindings","codes","units","value_codes","flags","identifier_systems","observation_statuses","report_statuses","coding_authorities"):
            if not isinstance(dictionary.get(name,{}),dict):
                raise ValueError("dictionary_mapping_required:"+name)
        if hashlib.sha256(_canonical(dictionary)).hexdigest()!=proposal["dictionary_sha256"]:
            raise ValueError("stale_dictionary")
        site=dictionary.get("site_id")
        if site is not None and site!=proposal["site_id"]:
            raise ValueError("site_mismatch")
        result.update(raw_sha256=result["case_id"],dictionary_sha256=proposal["dictionary_sha256"],
                      site_id=proposal["site_id"],site_label_verified=site is not None)
        from h7loss.v2 import parse_message
        parsed=parse_message(raw)
        refs=parsed["source_refs"]
        if parsed["errors"] or parsed["unsupported"]:
            raise ValueError("unsupported_parser_input")
        if not refs:
            raise ValueError("parser_source_refs_unavailable")
        tags={s["index"]:s["tag"] for s in parsed["segments"]}
        atoms={_canonical(a["source_ref"]):a for a in parsed["atoms"]}
        fields={}
        for atom in parsed["atoms"]:
            source=atom["source_ref"]
            fields.setdefault((source["segment_index"],source["field"],source["repetition"]),[]).append(atom)
        rows={key:_row(a["source_ref"],"explicit_null_not_asserted" if a["null"] else "empty_lexical_slot" if a["empty"] else "unsupported_atom" if a["unsupported"] else "no_bound_rule") for key,a in atoms.items()}
        assigned={}
        contributions=[]
        type_support=[]
        used=set()
        mapped_sources=set()
        for rule in compiled["proposal"]["rules"]:
            matching=[ref for ref in refs if _matches(rule["source"],ref,tags)]
            if set(rule["source"])==REF_KEYS and not matching:
                raise ValueError("fake_source_pointer")
            grouped=set()
            for ref in matching:
                transform=rule["transform"]
                target=rule.get("target")
                index=ref["segment_index"]
                field_atoms=fields[(index,ref["field"],ref["repetition"])]
                whole=(target=="observation.value" and tags[index]=="OBX" and ref["field"]==5) or target in {"observation.code","report.code","observation.unit"} or transform=="join_components"
                group_key=(index,ref["field"],ref["repetition"])
                if whole and group_key in grouped:
                    continue
                grouped.add(group_key)
                selected=[atoms[_canonical(ref)]]
                if whole:
                    selected=([atoms[_canonical(r)] for r in matching if all(r[k]==ref[k] for k in ("segment_index","field","repetition"))]
                              if transform=="join_components" else field_atoms)
                atom=atoms[_canonical(ref)]
                if (atom["empty"] or atom["null"] or atom["unsupported"]) and not (whole and target=="observation.value"):
                    continue
                text=atom["text"]
                if "guard" in rule and text!=rule["guard"]:
                    continue
                consumed=[ref]
                if transform in {"declare_drop","abstain"}:
                    value=None
                else:
                    expected="patient" if target.startswith("patient.") else "order" if target.startswith("report.") else "observation"
                    if _scope(ref["group_id"])!=expected:
                        raise ValueError("unbound_target_group")
                    if (target=="observation.time") != (transform=="timestamp_preserve_precision"):
                        raise ValueError("timestamp_target_transform_required")
                    if transform=="decimal_with_comparator" and target!="observation.value":
                        raise ValueError("decimal_value_target_required")
                    if transform=="unit_from_dictionary" and target!="observation.unit":
                        raise ValueError("unit_target_required")
                    if tags[index].startswith("Z"):
                        binding=f"{tags[index]}.{ref['field']}.{ref['component']}.{ref['subcomponent']}"
                        if dictionary.get("bindings",{}).get(binding)!=target:
                            raise ValueError("undocumented_z_meaning")
                    if target=="observation.value" and tags[index]=="OBX" and ref["field"]==5:
                        dtype=next((a for a in fields.get((index,2,1),[]) if a["source_ref"]["component"]==1 and a["source_ref"]["subcomponent"]==1),None)
                        if not dtype or dtype["unsupported"] or dtype["null"] or dtype["empty"]:
                            raise ValueError("datatype_unavailable")
                        decoded=decode_value(dtype["text"],selected,dictionary,transform)
                        value=decoded["value"]
                        consumed=decoded["consumed"]
                        # Datatype is structural evidence, allowed to support each repeat.
                    elif target in {"observation.code","report.code","observation.unit"} and transform in {"dictionary_lookup","unit_from_dictionary"}:
                        table_name=rule.get("dictionary") or ("units" if target=="observation.unit" else "codes")
                        table=dictionary.get(table_name,dictionary.get("tables",{}).get(table_name))
                        components={a["source_ref"]["component"]:a for a in selected if a["source_ref"]["subcomponent"]==1}
                        code_atom=components.get(1)
                        authority=components.get(3)
                        if not isinstance(table,dict) or not code_atom or not authority or authority["empty"] or authority["unsupported"] or authority["null"]:
                            raise ValueError("coded_source_namespace_required")
                        entry=table.get(code_atom["text"])
                        if isinstance(entry,str):
                            # Scalar code views are part of the same hashed release;
                            # verify them against its canonical code entry, retaining
                            # source authority checks and the original namespace.
                            canonical=dictionary.get("units" if target=="observation.unit" else "codes",{}).get(code_atom["text"])
                            value=coding_entry(canonical,authority["text"],dictionary)
                            expected=value["code"]
                            if entry!=expected:
                                raise ValueError("scalar_coding_view_conflict")
                        else:
                            value=coding_entry(entry,authority["text"],dictionary)
                        consumed=[code_atom["source_ref"],authority["source_ref"]]
                        display=components.get(2)
                        if display and display["text"]==value.get("display") and not display["unsupported"] and not display["null"]:
                            consumed.append(display["source_ref"])
                        if any(a["source_ref"]["component"]>3 or a["source_ref"]["subcomponent"]>1 for a in selected if not a["empty"]):
                            raise ValueError("extra_coding_components_unsupported")
                    else:
                        if transform=="join_components":
                            if any(a["unsupported"] or a["null"] or a["source_ref"]["subcomponent"]!=1 for a in selected):
                                raise ValueError("join_unsupported_atom")
                            # Preserve empty component positions in the joined output;
                            # they do not themselves assert a scalar source value.
                            consumed=[a["source_ref"] for a in selected if not a["empty"]]
                        value=_transform(rule,text,dictionary,[a["text"] for a in selected] if transform=="join_components" else None)
                    for bound in consumed:
                        if tags[bound["segment_index"]].startswith("Z"):
                            binding=f"{tags[bound['segment_index']]}.{bound['field']}.{bound['component']}.{bound['subcomponent']}"
                            if dictionary.get("bindings",{}).get(binding)!=target:
                                raise ValueError("undocumented_z_meaning")
                if any(_canonical(r) in used and (transform in {"declare_drop","abstain"} or _canonical(r) not in mapped_sources) for r in consumed):
                    raise ValueError("conflicting_source_dispositions")
                used.update(_canonical(r) for r in consumed)
                if transform in {"declare_drop","abstain"}:
                    for source in consumed:
                        rows[_canonical(source)].update(disposition="declared_drop" if transform=="declare_drop" else "abstain",reason_code=rule["reason"])
                    continue
                rep=ref["repetition"] if target=="observation.value" else index*65536+ref["repetition"] if target=="observation.note" else 0
                slot=(ref["group_id"],target,rep)
                if slot in assigned:
                    raise ValueError("conflicting_target")
                assigned[slot]=value
                contributions.append((consumed,slot))
                mapped_sources.update(_canonical(r) for r in consumed)
                if target=="observation.value" and tags[index]=="OBX" and ref["field"]==5:
                    type_support.append((dtype["source_ref"],slot))
        resources=_resources(assigned,dictionary)
        bundle={"resourceType":"Bundle","type":"collection","entry":[{"resource":r} for r in resources]}
        for consumed,(group,target,rep) in contributions:
            paths=_paths(bundle,group,target,rep,assigned)
            if not paths:
                raise ValueError("mapped_target_missing")
            for source in consumed:
                row=rows[_canonical(source)]
                row.update(disposition="mapped",reason_code="dsl_dictionary_rule",target_refs=list(dict.fromkeys(row["target_refs"]+paths)),
                           evidence_refs=[proposal["dictionary_sha256"],compiled["sha256"]])
        for source,(group,target,rep) in type_support:
            key=_canonical(source)
            if key in used:
                raise ValueError("datatype_disposition_conflict")
            row=rows[key]
            paths=_paths(bundle,group,target,rep,assigned)
            row.update(disposition="mapped",reason_code="dsl_value_datatype",
                       target_refs=list(dict.fromkeys(row["target_refs"]+paths)),
                       evidence_refs=[proposal["dictionary_sha256"],compiled["sha256"]])
        result.update(outcome="ok",bundle=bundle,dispositions=list(rows.values()),mapping_sha256=compiled["sha256"])
    except (ValueError,TypeError,KeyError,UnicodeError,ImportError,RecursionError,StopIteration,OverflowError) as exc:
        result.update(error=str(exc),bundle=None,dispositions=[_row(ref,"execution_refused") for ref in refs])
    return result
