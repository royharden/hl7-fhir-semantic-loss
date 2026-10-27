"""Bounded original value decoding for the existing closed proposal transforms.

Inputs are parser-issued leaves from one OBX-5 repetition. These helpers do not
read source files, discover dictionaries, evaluate code, or validate clinical
meaning. Dictionary meanings are explicit mapping inputs, not independent truth.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(text: str) -> str:
    if not isinstance(text, str) or len(text) > 128 or not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text
    ):
        raise ValueError("unsupported_numeric_lexeme")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("unsupported_numeric_lexeme") from exc
    if not number.is_finite():
        raise ValueError("nonfinite_number")
    # Prove the later JSON numeric representation will retain numeric value.
    _number(text)
    return text


def _number(text: str) -> int | float:
    if not isinstance(text, str) or len(text) > 128 or not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text
    ):
        raise ValueError("unsupported_numeric_lexeme")
    try:
        exact = Decimal(text)
        number = int(exact) if exact == exact.to_integral_value() else float(exact)
        if not exact.is_finite() or (isinstance(number, float) and not math.isfinite(number)):
            raise ValueError("nonfinite_number")
        if Decimal(str(number)) != exact:
            raise ValueError("numeric_precision_loss")
        return number
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("unsupported_numeric_lexeme") from exc


def coding_entry(entry: Any, authority: Any, dictionary: dict) -> dict:
    """Copy one released coding after checking the source authority namespace."""
    if not isinstance(entry, dict) or not all(
        isinstance(entry.get(key), str) and entry[key] for key in ("system", "code")
    ):
        raise ValueError("dictionary_coding_missing")
    authorities = dictionary.get("coding_authorities") if isinstance(dictionary, dict) else None
    if not isinstance(authority, str) or not authority or not isinstance(authorities, dict):
        raise ValueError("coding_authority_required")
    permitted = authorities.get(authority)
    if not isinstance(permitted, list) or not all(isinstance(v, str) and v for v in permitted):
        raise ValueError("coding_authority_unknown")
    if entry["system"] not in permitted:
        raise ValueError("coding_authority_conflict")
    result = {"system": entry["system"], "code": entry["code"]}
    if "display" in entry:
        if not isinstance(entry["display"], str):
            raise ValueError("invalid_dictionary_display")
        result["display"] = entry["display"]
    return result


def _components(atoms: list[dict], maximum: int) -> dict[int, dict]:
    if not isinstance(atoms, list) or not atoms or len(atoms) > maximum:
        raise ValueError("unsupported_value_shape")
    parts: dict[int, dict] = {}
    identity = None
    for atom in atoms:
        if not isinstance(atom, dict) or not isinstance(atom.get("source_ref"), dict):
            raise ValueError("value_atom_required")
        ref = atom["source_ref"]
        if not all(type(ref.get(k)) is int and ref[k] >= 0 for k in (
            "segment_index", "field", "repetition", "component", "subcomponent", "byte_start", "byte_end"
        )) or ref["field"] != 5 or ref["repetition"] < 1 or ref["subcomponent"] != 1:
            raise ValueError("unsupported_value_coordinates")
        if not 1 <= ref["component"] <= maximum or ref["component"] in parts:
            raise ValueError("unsupported_value_components")
        if not isinstance(ref.get("raw_sha256"), str) or not isinstance(ref.get("group_id"), str):
            raise ValueError("value_provenance_required")
        current = tuple(ref[k] for k in ("raw_sha256", "segment_index", "group_id", "field", "repetition"))
        if identity is not None and current != identity:
            raise ValueError("mixed_value_repetitions")
        identity = current
        if atom.get("unsupported") or atom.get("null") or not isinstance(atom.get("text"), str):
            raise ValueError("unusable_value_atom")
        parts[ref["component"]] = atom
    if set(parts) != set(range(1, max(parts) + 1)):
        raise ValueError("incomplete_value_components")
    return parts


def _text(parts: dict[int, dict], number: int, *, empty: bool = False) -> str:
    atom = parts.get(number)
    if atom is None:
        if empty:
            return ""
        raise ValueError("missing_value_component")
    text = atom["text"]
    if not text and not empty:
        raise ValueError("empty_value_component")
    return text


def decode_value(datatype: str, atoms: list[dict], dictionary: dict, transform: str) -> dict:
    """Return ``value`` and ``consumed`` exact refs; unsupported content refuses.

    SN comparator/ratio/range separators are consumed because their meanings are
    represented in output structure. Empty placeholders remain unconsumed. CWE
    display is consumed only when identical to the explicit dictionary display.
    No datatype ref is accepted here; the caller owns its separate provenance.
    """
    if not isinstance(dictionary, dict) or not isinstance(datatype, str) or not isinstance(transform, str):
        raise ValueError("invalid_value_arguments")
    allowed = {"NM": {"decimal_with_comparator", "repeated_value"},
               "SN": {"decimal_with_comparator", "repeated_value"},
               "ST": {"copy_text", "repeated_value"},
               "CWE": {"dictionary_lookup", "repeated_value"}}
    if datatype not in allowed or transform not in allowed[datatype]:
        raise ValueError("unsupported_value_transform")
    parts = _components(atoms, {"NM": 1, "SN": 4, "ST": 1, "CWE": 3}[datatype])
    consumed: list[dict] = []

    def consume(number: int) -> None:
        if number in parts and parts[number]["text"]:
            consumed.append(dict(parts[number]["source_ref"]))

    if datatype == "ST":
        value: Any = _text(parts, 1)
        consume(1)
    elif datatype == "NM":
        value = {"kind": "quantity", "value": _decimal(_text(parts, 1)), "comparator": None}
        consume(1)
    elif datatype == "SN":
        comparator = _text(parts, 1, empty=True)
        first = _decimal(_text(parts, 2))
        separator = _text(parts, 3, empty=True)
        second = _text(parts, 4, empty=True)
        if comparator not in {"", "<", "<=", ">", ">="}:
            raise ValueError("unsupported_sn_comparator")
        if separator:
            if comparator or separator not in {":", "-"} or not second:
                raise ValueError("unsupported_sn_combination")
            second = _decimal(second)
            if separator == ":":
                if Decimal(second) == 0:
                    raise ValueError("zero_ratio_denominator")
                value = {"kind": "ratio", "numerator": first, "denominator": second}
            else:
                if Decimal(first) > Decimal(second):
                    raise ValueError("reversed_range")
                value = {"kind": "range", "low": first, "high": second}
            consume(3)
            consume(4)
        else:
            if second:
                raise ValueError("orphan_sn_second_number")
            value = {"kind": "quantity", "value": first, "comparator": comparator or None}
            consume(1)
        consume(2)
    else:
        code = _text(parts, 1)
        authority = _text(parts, 3)
        table = dictionary.get("value_codes")
        if not isinstance(table, dict):
            raise ValueError("value_code_dictionary_required")
        coding = coding_entry(table.get(code), authority, dictionary)
        # A renamed output code is permitted only by this exact released entry.
        value = {"kind": "code", "coding": coding}
        consume(1)
        consume(3)
        display = _text(parts, 2, empty=True)
        if display and display == coding.get("display"):
            consume(2)
    return {"value": value, "consumed": consumed}


def _unit(unit: dict | str | None) -> dict:
    if unit is None:
        return {}
    if isinstance(unit, str) and unit:
        return {"unit": unit}
    if not isinstance(unit, dict) or not all(
        isinstance(unit.get(key), str) and unit[key] for key in ("system", "code")
    ):
        raise ValueError("unsupported_unit")
    if "display" in unit and not isinstance(unit["display"], str):
        raise ValueError("invalid_unit_display")
    return {"system": unit["system"], "code": unit["code"],
            "unit": unit.get("display") or unit["code"]}


def render_value(value: Any, unit: dict | str | None = None) -> dict:
    """Produce a bounded FHIR value[x] object, without claiming FHIR validation."""
    if isinstance(value, str):
        if not value or unit is not None:
            raise ValueError("text_value_with_unit_or_empty")
        return {"valueString": value}
    if not isinstance(value, dict):
        raise ValueError("unsupported_value")
    kind = value.get("kind")
    if kind == "code":
        if unit is not None or set(value) != {"kind", "coding"}:
            raise ValueError("coded_value_with_unit_or_keys")
        coding = value["coding"]
        if not isinstance(coding, dict) or set(coding) - {"system", "code", "display"} or not all(
            isinstance(coding.get(k), str) and coding[k] for k in ("system", "code")
        ) or ("display" in coding and not isinstance(coding["display"], str)):
            raise ValueError("invalid_coded_value")
        return {"valueCodeableConcept": {"coding": [dict(coding)]}}
    unit_fields = _unit(unit)
    if kind == "quantity":
        if set(value) != {"kind", "value", "comparator"}:
            raise ValueError("unsupported_quantity_keys")
        comparator = value["comparator"]
        if comparator is not None and (not isinstance(comparator, str) or comparator not in {"<", "<=", ">", ">="}):
            raise ValueError("unsupported_comparator")
        quantity = {"value": _number(value["value"]), **unit_fields}
        if comparator:
            quantity["comparator"] = comparator
        return {"valueQuantity": quantity}
    if kind == "ratio":
        if set(value) != {"kind", "numerator", "denominator"}:
            raise ValueError("unsupported_ratio_keys")
        # A single v2 unit field does not release which side of a ratio owns it.
        # Keep that source abstained unless a future explicit role contract exists.
        if unit is not None:
            raise ValueError("ratio_unit_roles_not_released")
        numerator, denominator = _number(value["numerator"]), _number(value["denominator"])
        if denominator == 0:
            raise ValueError("zero_ratio_denominator")
        return {"valueRatio": {"numerator": {"value": numerator},
                               "denominator": {"value": denominator}}}
    if kind == "range":
        if set(value) != {"kind", "low", "high"}:
            raise ValueError("unsupported_range_keys")
        low, high = _number(value["low"]), _number(value["high"])
        if Decimal(value["low"]) > Decimal(value["high"]):
            raise ValueError("reversed_range")
        return {"valueRange": {"low": {"value": low, **unit_fields},
                               "high": {"value": high, **unit_fields}}}
    raise ValueError("unsupported_value_kind")
