"""Original conservative B0 construction rules, not an admitted mapping IG."""

import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation

from h7loss.v2 import parse_message
from h7loss.v2.time import timestamp_to_fhir

RULESET_ID = "original-b0-construction-v1"


def _digest(value: dict) -> str:
    # JSON encoder recursion behavior varies across supported interpreters.
    # Bound public dictionary metadata explicitly before hashing it.
    pending = [(value, 0)]
    visited_nodes = 0
    while pending:
        node, depth = pending.pop()
        visited_nodes += 1
        if depth > 64 or visited_nodes > 65536:
            raise ValueError("dictionary_nesting_or_node_limit")
        if isinstance(node, (dict, list, tuple)) and visited_nodes + len(pending) + len(node) > 65536:
            raise ValueError("dictionary_nesting_or_node_limit")
        if isinstance(node, dict):
            pending.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, (list, tuple)):
            pending.extend((child, depth + 1) for child in node)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _number(text: str):
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text) or len(text) > 128:
        raise ValueError("unsupported_numeric_lexeme")
    try:
        decimal = Decimal(text)
        number = int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError("nonfinite_number")
        if Decimal(str(number)) != decimal:
            raise ValueError("numeric_precision_loss")
        return number
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("unsupported_numeric_lexeme") from exc


def _coding(entry):
    if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k]
                                             for k in ("system", "code")):
        raise ValueError("dictionary_entry_missing")
    return {k: entry[k] for k in ("system", "code", "display") if isinstance(entry.get(k), str)}


def map_message(raw: bytes, dictionary: dict) -> dict:
    """Map a narrow released-dictionary subset; every lexical atom gets a ledger row.

    No terminology/IG rights or Java validity is inferred. Dictionary entries are
    public mapping inputs, never hidden truth. Unsupported critical slots abstain.
    """
    parsed = parse_message(raw)
    result = {"case_id": parsed["raw_sha256"][:16], "arm_id": "B0", "outcome": "refused",
              "bundle": None, "dispositions": [], "error": None,
              "raw_sha256": parsed["raw_sha256"], "dictionary_sha256": "",
              "provenance": {"ruleset": RULESET_ID, "admission": "unadmitted",
                             "validation": "not_run", "ig_rule_lock": "PENDING"},
              "paired_projection": [], "paired_relations": []}
    try:
        if not isinstance(dictionary, dict):
            raise ValueError("dictionary_must_be_object")
        for name in ("codes", "units", "value_codes", "identifier_systems", "observation_statuses", "report_statuses", "coding_authorities", "flags", "time_fields", "note_scopes"):
            mapping = dictionary.get(name, {})
            if not isinstance(mapping, dict) or not all(isinstance(k, str) for k in mapping):
                raise ValueError("invalid_dictionary_map:" + name)
        for name in ("identifier_systems", "observation_statuses", "report_statuses"):
            if not all(isinstance(v, str) for v in dictionary.get(name, {}).values()):
                raise ValueError("invalid_dictionary_values:" + name)
        for permitted in dictionary.get("coding_authorities", {}).values():
            if not isinstance(permitted, list) or not all(isinstance(v, str) for v in permitted):
                raise ValueError("invalid_coding_authorities")
        result["dictionary_sha256"] = _digest(dictionary)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        result["error"] = "invalid_dictionary:" + str(exc)
        # Still supply all parsed leaves as explicit abstentions below.
    rows = {}
    for atom in parsed["atoms"]:
        ref = atom["source_ref"]
        key = (ref["segment_index"], ref["field"], ref["repetition"], ref["component"], ref["subcomponent"])
        row = {"source_ref": ref, "disposition": "abstain", "reason_code": "unsupported_slot",
               "target_refs": [], "evidence_refs": [parsed["raw_sha256"], result["dictionary_sha256"], RULESET_ID]}
        if atom["empty"]:
            row.update(disposition="declared_drop", reason_code="empty_lexical_slot")
        elif atom["null"]:
            row["reason_code"] = "explicit_null_not_asserted"
        elif atom["unsupported"]:
            row["reason_code"] = atom["unsupported"][0]
        rows[key] = (atom, row)
        result["dispositions"].append(row)

    def atom_at(index, field, rep=1, comp=1):
        found = rows.get((index, field, rep, comp, 1))
        if found is None:
            raise ValueError("missing_source_slot")
        atom = found[0]
        if atom["unsupported"] or atom["null"] or atom["empty"]:
            raise ValueError("unusable_source_slot")
        return atom["text"]

    def mark(index, field, target, rep=1, comp=1, transform="copy", table=None, precision=None):
        row = rows[(index, field, rep, comp, 1)][1]
        row.update(disposition="mapped", reason_code="original_dictionary_rule")
        if target not in row["target_refs"]:
            row["target_refs"].append(target)
        projection = {"source_ref": dict(row["source_ref"]), "target_ref": target, "transform": transform}
        if table is not None:
            projection["table"] = table
        if precision is not None:
            projection["precision"] = precision
        result["paired_projection"].append(projection)

    def coding(index, field, table, rep=1):
        coded = _coding(dictionary.get(table, {}).get(atom_at(index, field, rep)))
        authority_row = rows.get((index, field, rep, 3, 1))
        if authority_row and not authority_row[0]["empty"]:
            authority = atom_at(index, field, rep, 3)
            if coded["system"] not in dictionary.get("coding_authorities", {}).get(authority, []):
                raise ValueError("source_coding_authority_unknown_or_conflicting")
        return coded

    if result["error"]:
        return result
    if parsed["errors"] or parsed["unsupported"]:
        result["error"] = ";".join(parsed["errors"] + parsed["unsupported"])
        return result
    tags = [s["tag"] for s in parsed["segments"]]
    if tags.count("PID") != 1 or not 1 <= tags.count("OBR") <= 2 or tags.count("OBX") > 6:
        result["error"] = "unsupported_message_shape"
        return result
    if tags.index("PID") > tags.index("OBR"):
        result["error"] = "order_before_patient"
        return result
    order_observations = 0
    order_seen = False
    for tag in tags:
        if tag == "OBR":
            if order_seen and not 1 <= order_observations <= 3:
                result["error"] = "unsupported_order_observation_count"
                return result
            order_seen, order_observations = True, 0
        elif tag == "OBX":
            order_observations += 1
    if not 1 <= order_observations <= 3:
        result["error"] = "unsupported_order_observation_count"
        return result
    try:
        msh = parsed["segments"][0]["index"]
        if (atom_at(msh, 9), atom_at(msh, 9, comp=2), atom_at(msh, 12)) != ("ORU", "R01", "2.8"):
            raise ValueError("unsupported_message_type_or_version")
        # Extra subcomponents need an explicit rule, never silently flatten them.
        if any(a["source_ref"]["subcomponent"] > 1 and not a["empty"] for a in parsed["atoms"]):
            raise ValueError("subcomponent_mapping_unsupported")
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    entries = []
    patient_segment = next(s for s in parsed["segments"] if s["tag"] == "PID")
    pi = patient_segment["index"]
    try:
        patient_id = atom_at(pi, 3)
        authority = atom_at(pi, 3, comp=4)
        system = dictionary.get("identifier_systems", {}).get(authority)
        if not isinstance(system, str) or not system:
            raise ValueError("identifier_authority_unknown")
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    patient_ref = "Patient/patient-0"
    entries.append({"resource": {"resourceType": "Patient", "id": "patient-0",
                                  "identifier": [{"system": system, "value": patient_id}]}})
    mark(pi, 3, "/entry/0/resource/identifier/0/value")
    mark(pi, 3, "/entry/0/resource/identifier/0/system", comp=4, transform="dictionary_key", table="identifier_systems")
    reports = {}
    group_targets = {}

    def add_time(index, field, resource, target, meaning):
        if dictionary.get("time_fields", {}).get(f"{parsed['segments'][index]['tag']}.{field}") != meaning:
            return
        try:
            timestamp, precision = timestamp_to_fhir(atom_at(index, field))
        except ValueError:
            return
        resource["effectiveDateTime"] = timestamp
        resource.setdefault("extension", []).append({"url": "urn:h7loss:time-precision-digits", "valueInteger": precision})
        mark(index, field, target + "/effectiveDateTime", transform="timestamp", precision=precision)
    for segment in parsed["segments"]:
        if segment["tag"] != "OBR":
            continue
        index = segment["index"]
        # Report is emitted only with dictionary-bound code and explicit status.
        try:
            code = coding(index, 4, "codes")
            status = dictionary.get("report_statuses", {}).get(atom_at(index, 25))
            if status not in {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended", "cancelled", "entered-in-error", "unknown"}:
                raise ValueError("report_status_unknown")
        except ValueError:
            continue
        pos = len(entries)
        rid = f"report-{len(reports)}"
        resource = {"resourceType": "DiagnosticReport", "id": rid, "status": status,
                    "code": {"coding": [code]}, "subject": {"reference": patient_ref}, "result": []}
        entries.append({"resource": resource})
        reports[segment["group_id"]] = resource
        target = f"/entry/{pos}/resource"
        group_targets[segment["group_id"]] = [(resource, target)]
        mark(index, 4, target + "/code/coding/0", transform="dictionary_key", table="codes")
        mark(index, 25, target + "/status", transform="dictionary_key", table="report_statuses")
        result["paired_relations"].append({"source_group": segment["group_id"], "target_ref": target + "/subject/reference"})
        add_time(index, 7, resource, target, "report_effective")
    for segment in parsed["segments"]:
        if segment["tag"] != "OBX":
            continue
        index = segment["index"]
        order_group = segment["group_id"].rsplit("/observation:", 1)[0]
        report = reports.get(order_group)
        if report is None:
            continue
        reps = sorted({a["source_ref"]["repetition"] for a in parsed["atoms"]
                       if a["source_ref"]["segment_index"] == index and a["source_ref"]["field"] == 5})
        for rep in reps:
            try:
                datatype = atom_at(index, 2)
                code = coding(index, 3, "codes")
                status = dictionary.get("observation_statuses", {}).get(atom_at(index, 11))
                if status not in {"registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error", "unknown"}:
                    raise ValueError("observation_status_unknown")
                source = atom_at(index, 5, rep)
                if datatype == "ST":
                    value = {"valueString": source}
                elif datatype in {"NM", "SN"}:
                    comparator = None
                    if datatype == "SN":
                        comparator = source
                        if comparator not in {"<", "<=", ">", ">="}:
                            raise ValueError("unsupported_sn_comparator")
                        source = atom_at(index, 5, rep, 2)
                        if any(a["source_ref"]["segment_index"] == index and a["source_ref"]["field"] == 5
                               and a["source_ref"]["repetition"] == rep and a["source_ref"]["component"] > 2
                               and not a["empty"] for a in parsed["atoms"]):
                            raise ValueError("unsupported_sn_range")
                    unit = coding(index, 6, "units")
                    quantity = {"value": _number(source), "system": unit["system"], "code": unit["code"],
                                "unit": unit.get("display", unit["code"])}
                    if comparator:
                        quantity["comparator"] = comparator
                    value = {"valueQuantity": quantity,
                             "extension": [{"url": "urn:h7loss:original-numeric-lexeme", "valueString": source}]}
                elif datatype == "CWE":
                    coded = coding(index, 5, "value_codes", rep)
                    value = {"valueCodeableConcept": {"coding": [coded]}}
                else:
                    raise ValueError("unsupported_datatype")
            except (ValueError, TypeError):
                continue
            pos = len(entries)
            oid = f"observation-{index}-{rep}"
            resource = {"resourceType": "Observation", "id": oid, "status": status,
                        "code": {"coding": [code]}, "subject": {"reference": patient_ref}, **value}
            entries.append({"resource": resource})
            report["result"].append({"reference": f"Observation/{oid}"})
            target = f"/entry/{pos}/resource"
            group_targets.setdefault(segment["group_id"], []).append((resource, target))
            mark(index, 2, target, transform="datatype")
            mark(index, 3, target + "/code/coding/0", transform="dictionary_key", table="codes")
            mark(index, 11, target + "/status", transform="dictionary_key", table="observation_statuses")
            if datatype == "ST":
                mark(index, 5, target + "/valueString", rep)
            elif datatype == "CWE":
                mark(index, 5, target + "/valueCodeableConcept/coding/0", rep, transform="dictionary_key", table="value_codes")
            else:
                mark(index, 5, target, rep, 2 if datatype == "SN" else 1, transform="numeric_lexeme")
                numeric_row = rows[(index, 5, rep, 2 if datatype == "SN" else 1, 1)][1]
                numeric_row["target_refs"].extend([target + "/valueQuantity/value", target + "/extension/0/valueString"])
                if datatype == "SN":
                    mark(index, 5, target + "/valueQuantity/comparator", rep)
                mark(index, 6, target + "/valueQuantity", transform="dictionary_key", table="units")
            add_time(index, 14, resource, target, "observation_effective")
            for flag_rep in sorted({a["source_ref"]["repetition"] for a in parsed["atoms"] if a["source_ref"]["segment_index"] == index and a["source_ref"]["field"] == 8}):
                try:
                    flag = _coding(dictionary.get("flags", {}).get(atom_at(index, 8, flag_rep)))
                except ValueError:
                    continue
                flag_pos = len(resource.setdefault("interpretation", []))
                resource["interpretation"].append({"coding": [flag]})
                mark(index, 8, target + f"/interpretation/{flag_pos}/coding/0", flag_rep, transform="dictionary_key", table="flags")
            result["paired_relations"].append({"source_group": segment["group_id"], "target_ref": target + "/subject/reference"})
            report_target = group_targets[order_group][0][1]
            result["paired_relations"].append({"source_group": segment["group_id"], "target_ref": report_target + f"/result/{len(report['result']) - 1}/reference"})
    for segment in parsed["segments"]:
        if segment["tag"] != "NTE":
            continue
        scope = "observation" if "/observation:" in segment["group_id"] else "order" if "/order:" in segment["group_id"] else "patient"
        allowed = dictionary.get("note_scopes", {}).get("NTE.3", [])
        if not isinstance(allowed, list) or scope not in allowed:
            continue
        index = segment["index"]
        repetitions = sorted({a["source_ref"]["repetition"] for a in parsed["atoms"] if a["source_ref"]["segment_index"] == index and a["source_ref"]["field"] == 3})
        for rep in repetitions:
            try:
                text = atom_at(index, 3, rep)
            except ValueError:
                continue
            for resource, target in group_targets.get(segment["group_id"], []):
                if scope == "observation":
                    note_pos = len(resource.setdefault("note", []))
                    resource["note"].append({"text": text})
                    pointer = target + f"/note/{note_pos}/text"
                else:
                    note_pos = len(resource.setdefault("extension", []))
                    resource["extension"].append({"url": "urn:h7loss:order-note", "valueString": text})
                    pointer = target + f"/extension/{note_pos}/valueString"
                mark(index, 3, pointer, rep)
    result["bundle"] = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    result["outcome"] = "partial" if any(r["disposition"] == "abstain" for r in result["dispositions"]) else "mapped"
    return result


def paired_inverse(result: dict, dictionary: dict) -> dict:
    """Reconstruct only declared mapped semantic source leaves, never raw replay."""
    from h7loss.v2.paired import paired_inverse as reconstruct
    return reconstruct(result, dictionary)
