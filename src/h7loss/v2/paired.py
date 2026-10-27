"""Original B0 paired source projection; neither raw replay nor independent truth."""

import hashlib
import json
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

_REF_KEYS = ("raw_sha256", "segment_index", "group_id", "field", "repetition",
             "component", "subcomponent", "byte_start", "byte_end")
_TABLES = frozenset({"identifier_systems", "codes", "value_codes", "units",
                     "observation_statuses", "report_statuses", "flags"})
_MAX_ITEMS = 65536


def _ref_key(ref: dict, raw_hash: str) -> tuple:
    if not isinstance(ref, dict) or set(ref) != set(_REF_KEYS):
        raise ValueError("invalid_source_ref")
    if ref["raw_sha256"] != raw_hash or not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
        raise ValueError("source_hash_mismatch")
    if not isinstance(ref["group_id"], str) or not ref["group_id"] or len(ref["group_id"]) > 256:
        raise ValueError("invalid_source_group")
    for name in ("segment_index", "field", "repetition", "component", "subcomponent", "byte_start", "byte_end"):
        if type(ref[name]) is not int or ref[name] < (1 if name in {"field", "repetition", "component", "subcomponent"} else 0):
            raise ValueError("invalid_source_coordinate")
    if ref["byte_end"] < ref["byte_start"] or ref["byte_end"] > 1024 * 1024:
        raise ValueError("invalid_source_span")
    return tuple(ref[name] for name in _REF_KEYS)


def _pointer(bundle: dict, pointer: str):
    if not isinstance(pointer, str) or len(pointer) > 512 or not pointer.startswith("/entry/"):
        raise ValueError("invalid_bundle_pointer")
    tokens = pointer.split("/")[1:]
    if len(tokens) < 3 or tokens[2] != "resource" or not re.fullmatch(r"0|[1-9][0-9]*", tokens[1]):
        raise ValueError("invalid_resource_pointer")
    value = bundle
    for token in tokens:
        if not token or re.search(r"~(?![01])", token):
            raise ValueError("invalid_pointer_token")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("invalid_array_pointer")
            index = int(token)
            if index >= len(value):
                raise ValueError("missing_target")
            value = value[index]
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise ValueError("missing_target")
    return value


def _dictionary_key(dictionary: dict, table_name: str, value) -> str:
    if table_name not in _TABLES or not isinstance(dictionary.get(table_name), dict):
        raise ValueError("unsupported_inverse_table")
    matches = []
    for key, entry in dictionary[table_name].items():
        if not isinstance(key, str) or not key:
            raise ValueError("invalid_inverse_dictionary_key")
        if isinstance(entry, str) and isinstance(value, str) and entry == value:
            matches.append(key)
        elif isinstance(entry, dict) and isinstance(value, dict):
            if all(isinstance(entry.get(k), str) and entry[k] and entry[k] == value.get(k)
                   for k in ("system", "code")):
                matches.append(key)
    if len(matches) != 1:
        raise ValueError("inverse_dictionary_missing_or_ambiguous")
    return matches[0]


def _timestamp(value: str, precision: int) -> str:
    if not isinstance(value, str) or type(precision) is not int:
        raise ValueError("invalid_timestamp_projection")
    if precision in {4, 6, 8}:
        patterns = {4: r"\d{4}", 6: r"\d{4}-\d{2}", 8: r"\d{4}-\d{2}-\d{2}"}
        if not re.fullmatch(patterns[precision], value):
            raise ValueError("timestamp_precision_changed")
        parts = [int(part) for part in value.split("-")]
        datetime(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        return value.replace("-", "")
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?([+-])(\d{2}):(\d{2})", value)
    if not match or not 14 <= precision <= 23:
        raise ValueError("unsupported_timestamp_target")
    year, month, day, hour, minute, second, fraction, sign, zone_hour, zone_minute = match.groups()
    if precision != 14 + len(fraction or ""):
        raise ValueError("timestamp_precision_changed")
    datetime(*map(int, (year, month, day, hour, minute, second)))
    zh, zm = int(zone_hour), int(zone_minute)
    if zh > 14 or zm > 59 or (zh == 14 and zm != 0):
        raise ValueError("invalid_timestamp_offset")
    return year + month + day + hour + minute + second + ("." + fraction if fraction else "") + sign + zone_hour + zone_minute


def _datatype(resource: dict) -> str:
    if not isinstance(resource, dict) or resource.get("resourceType") != "Observation":
        raise ValueError("datatype_target_not_observation")
    keys = [key for key in resource if key.startswith("value")]
    if len(keys) != 1:
        raise ValueError("datatype_missing_or_conflicting")
    key = keys[0]
    if key == "valueString" and isinstance(resource[key], str):
        return "ST"
    if key == "valueCodeableConcept" and isinstance(resource[key], dict):
        return "CWE"
    if key == "valueQuantity" and isinstance(resource[key], dict):
        comparator = resource[key].get("comparator")
        if comparator is None:
            return "NM"
        if comparator in {"<", "<=", ">", ">="}:
            return "SN"
    raise ValueError("unsupported_datatype_target")


def _numeric_lexeme(resource: dict) -> str:
    if not isinstance(resource, dict) or resource.get("resourceType") != "Observation":
        raise ValueError("numeric_target_not_observation")
    quantity = resource.get("valueQuantity")
    extensions = resource.get("extension", [])
    if not isinstance(quantity, dict) or not isinstance(extensions, list):
        raise ValueError("missing_numeric_target")
    values = [entry.get("valueString") for entry in extensions if isinstance(entry, dict)
              and entry.get("url") == "urn:h7loss:original-numeric-lexeme"]
    number = quantity.get("value")
    if len(values) != 1 or not isinstance(values[0], str) or len(values[0]) > 128:
        raise ValueError("numeric_lexeme_missing_or_ambiguous")
    if type(number) not in {int, float} or (isinstance(number, float) and not math.isfinite(number)):
        raise ValueError("invalid_numeric_target")
    lexeme = values[0]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", lexeme):
        raise ValueError("unsupported_numeric_lexeme")
    if Decimal(str(number)) != Decimal(lexeme):
        raise ValueError("numeric_target_changed")
    return lexeme


def paired_inverse(result: dict, dictionary: dict) -> dict:
    """Reconstruct the declared supported source projection, never original bytes.

    Coordinate metadata is attributed to B0, not independently verified. The
    status reports projection availability, never a round-trip pass or fidelity.
    """
    output = {"status": "unsupported", "projection": [], "unsupported": [], "relations": [],
              "error": None, "evidence_class": "original_b0_paired_projection", "runtime_verified": False}
    dispositions = {}
    try:
        if not isinstance(result, dict) or result.get("arm_id") != "B0" or not isinstance(dictionary, dict):
            raise ValueError("invalid_paired_input")
        raw_hash = result.get("raw_sha256")
        if not isinstance(raw_hash, str):
            raise ValueError("missing_source_hash")
        digest = hashlib.sha256(json.dumps(dictionary, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=True, allow_nan=False).encode()).hexdigest()
        if digest != result.get("dictionary_sha256"):
            raise ValueError("dictionary_hash_mismatch")
        bundle = result.get("bundle")
        if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
            raise ValueError("missing_bundle")
        rows = result.get("dispositions")
        records = result.get("paired_projection")
        relations = result.get("paired_relations", [])
        if not all(isinstance(items, list) and len(items) <= _MAX_ITEMS for items in (rows, records, relations)):
            raise ValueError("invalid_or_oversize_projection_metadata")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid_disposition")
            key = _ref_key(row.get("source_ref"), raw_hash)
            if key in dispositions or row.get("disposition") not in {"mapped", "declared_drop", "abstain"}:
                raise ValueError("duplicate_or_invalid_disposition")
            if not isinstance(row.get("target_refs"), list) or not all(isinstance(p, str) for p in row["target_refs"]):
                raise ValueError("invalid_disposition_targets")
            dispositions[key] = row
        projected = {}
        failed = {}
        for record in records:
            ref = record.get("source_ref") if isinstance(record, dict) else None
            try:
                if not isinstance(record, dict) or set(record) - {"source_ref", "target_ref", "transform", "table", "precision"}:
                    raise ValueError("invalid_projection_record")
                key = _ref_key(ref, raw_hash)
                disposition = dispositions.get(key)
                pointer = record.get("target_ref")
                if disposition is None or disposition["disposition"] != "mapped" or pointer not in disposition["target_refs"]:
                    raise ValueError("projection_not_bound_to_mapped_disposition")
                value = _pointer(bundle, pointer)
                transform = record.get("transform")
                if transform == "copy":
                    if not isinstance(value, str):
                        raise ValueError("copy_target_not_text")
                    text = value
                elif transform == "dictionary_key":
                    text = _dictionary_key(dictionary, record.get("table"), value)
                elif transform == "timestamp":
                    text = _timestamp(value, record.get("precision"))
                elif transform == "datatype":
                    text = _datatype(value)
                elif transform == "numeric_lexeme":
                    text = _numeric_lexeme(value)
                else:
                    raise ValueError("unsupported_inverse_transform")
                if key in projected and projected[key]["text"] != text:
                    raise ValueError("conflicting_repeated_target_values")
                if key not in failed:
                    projected.setdefault(key, {"source_ref": ref, "text": text, "target_ref": pointer,
                                               "target_refs": []})["target_refs"].append(pointer)
            except (TypeError, ValueError, KeyError, IndexError, InvalidOperation, OverflowError, RecursionError) as exc:
                try:
                    key = _ref_key(ref, raw_hash)
                except (TypeError, ValueError):
                    raise ValueError("invalid_projection_source_ref") from exc
                if key not in dispositions:
                    raise ValueError("projection_source_not_in_dispositions") from exc
                failed[key] = str(exc)
                projected.pop(key, None)
        for key, row in dispositions.items():
            if key in failed:
                reason = failed[key]
            elif key not in projected:
                reason = "missing_inverse_rule" if row["disposition"] == "mapped" else row["disposition"] + ":" + str(row.get("reason_code", "unspecified"))
            else:
                continue
            output["unsupported"].append({"source_ref": row["source_ref"], "reason_code": reason})
        output["projection"] = list(projected.values())
        source_groups = {row["source_ref"]["group_id"] for row in dispositions.values()}
        for relation in relations:
            if not isinstance(relation, dict) or set(relation) != {"source_group", "target_ref"}:
                raise ValueError("invalid_relation_metadata")
            group, pointer = relation["source_group"], relation["target_ref"]
            if (not isinstance(group, str) or not group or len(group) > 256
                    or group not in source_groups):
                raise ValueError("invalid_relation_group")
            if not isinstance(pointer, str) or not re.fullmatch(r"/entry/(?:0|[1-9][0-9]*)/resource/(?:subject/reference|result/(?:0|[1-9][0-9]*)/reference)", pointer):
                raise ValueError("unsupported_relation_pointer")
            reference = _pointer(bundle, pointer)
            if not isinstance(reference, str):
                raise ValueError("relation_target_not_text")
            output["relations"].append({"source_group": group, "target_ref": pointer, "reference": reference})
        output["status"] = "partial" if output["unsupported"] else "projected"
        if not projected:
            output["status"] = "unsupported"
    except (TypeError, ValueError, KeyError, IndexError, InvalidOperation, OverflowError, RecursionError) as exc:
        output.update(status="unsupported", error=str(exc), projection=[], relations=[])
        output["unsupported"] = [{"source_ref": row["source_ref"], "reason_code": "paired_projection_refused"}
                                 for row in dispositions.values()]
    return output
