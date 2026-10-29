"""Bounded lexical v2 parser. Offsets always refer to original bytes."""

import hashlib
import re

MAX_MESSAGE_BYTES = 1024 * 1024
MAX_SEGMENTS = 4096
MAX_ATOMS = 65536


def _pieces(raw: bytes, sep: bytes, start: int):
    offset = start
    for piece in raw.split(sep):
        yield piece, offset, offset + len(piece)
        offset += len(piece) + len(sep)


def decode_escape(value: bytes, delimiters: dict) -> dict:
    """Decode supported lexical escapes without guessing charset/formatting."""
    escape = delimiters["escape"].encode("ascii")
    replacements = {key: delimiters[name].encode("ascii") for key, name in
                    ((b"F", "field"), (b"S", "component"), (b"T", "subcomponent"),
                     (b"R", "repetition"), (b"E", "escape"))}
    parts = value.split(escape)
    unsupported = []
    decoded = bytearray()
    if len(parts) % 2 == 0:
        return {"text": None, "unsupported": ["unterminated_escape"]}
    for i, part in enumerate(parts):
        if i % 2 == 0:
            decoded.extend(part)
        elif part in replacements:
            decoded.extend(replacements[part])
        elif part == b".br":
            decoded.extend(b"\n")
        elif part.startswith(b"X") and len(part) > 1 and len(part[1:]) % 2 == 0:
            try:
                decoded.extend(bytes.fromhex(part[1:].decode("ascii")))
            except (ValueError, UnicodeError):
                unsupported.append("invalid_hex_escape")
        else:
            unsupported.append("unsupported_escape")
    try:
        text = decoded.decode("ascii")
    except UnicodeError:
        text = None
        unsupported.append("unsupported_charset")
    return {"text": text if not unsupported else None, "unsupported": unsupported}


def parse_message(raw: bytes) -> dict:
    """Preserve all bytes, including CR/CRLF and empty/null atom spans.

    Segment indices are zero based, field/repetition/component/subcomponent one
    based. MSH-1 is its literal separator; MSH-2 is one opaque lexical atom.
    """
    if not isinstance(raw, bytes):
        raise TypeError("raw must be bytes")
    digest = hashlib.sha256(raw).hexdigest()
    result = {"raw_sha256": digest, "raw_hex": None, "segments": [],
              "source_refs": [], "atoms": [], "unsupported": [], "errors": []}
    if len(raw) > MAX_MESSAGE_BYTES:
        result["errors"].append("message_too_large")
        return result
    result["raw_hex"] = raw.hex()
    if len(raw) < 8 or raw[:3] != b"MSH":
        result["errors"].append("missing_msh")
        return result
    field, component, repetition, escape, subcomponent = raw[3:8]
    values = (field, component, repetition, escape, subcomponent)
    if len(set(values)) != 5 or any(v < 33 or v > 126 for v in values):
        result["errors"].append("invalid_delimiters")
        return result
    if len(raw) < 9 or raw[8] != field:
        result["errors"].append("unsupported_encoding_characters")
        return result
    delimiters = dict(zip(("field", "component", "repetition", "escape", "subcomponent"),
                          (chr(v) for v in values)))
    result["delimiters"] = delimiters
    order = -1
    observation = -1
    patient_seen = False
    group = "message"
    cursor = 0
    # Match framing only; escaped line breaks remain literal backslash text.
    chunks = list(re.finditer(rb"([^\r\n]+)(\r\n|\r|\n|$)", raw))
    if len(chunks) > MAX_SEGMENTS:
        result["errors"].append("too_many_segments")
        return result
    for index, match in enumerate(chunks):
        if match.start() != cursor:
            result["errors"].append("empty_or_invalid_segment_framing")
        cursor = match.end()
        segment = match.group(1)
        if match.group(2) == b"\n":
            result["unsupported"].append("lf_only_segment_terminator")
        tag = segment[:3].decode("ascii", errors="replace")
        if len(segment) < 4 or segment[3] != field or not re.fullmatch(r"[A-Z0-9]{3}", tag):
            result["errors"].append(f"invalid_segment:{index}")
            continue
        if tag == "PID":
            if patient_seen:
                result["unsupported"].append("multiple_patient_groups")
            patient_seen = True
            group = "patient:0"
        elif tag == "OBR":
            order += 1
            observation = -1
            group = f"patient:0/order:{order}"
        elif tag == "OBX":
            observation += 1
            group = f"patient:0/order:{order}/observation:{observation}"
            if order < 0:
                result["unsupported"].append("observation_without_order")
        elif tag == "ORC":
            group = f"patient:0/order:{order + 1}"
        elif tag not in {"MSH", "NTE"} and not tag.startswith("Z"):
            result["unsupported"].append(f"segment:{tag}")
        fields = []
        if tag == "MSH":
            if index != 0:
                result["unsupported"].append("repeated_msh")
            spans = [(1, segment[3:4], match.start() + 3)]
            spans += [(n + 2, piece, start) for n, (piece, start, _end) in
                      enumerate(_pieces(segment[4:], bytes([field]), match.start() + 4))]
        else:
            spans = [(n + 1, piece, start) for n, (piece, start, _end) in
                     enumerate(_pieces(segment[4:], bytes([field]), match.start() + 4))]
        for number, value, field_start in spans:
            fields.append({"field": number, "raw_hex": value.hex(), "byte_start": field_start,
                           "byte_end": field_start + len(value)})
            opaque = tag == "MSH" and number in (1, 2)
            reps = [(value, field_start, field_start + len(value))] if opaque else _pieces(value, bytes([repetition]), field_start)
            for rep, (rep_value, rep_start, _rep_end) in enumerate(reps, 1):
                comps = [(rep_value, rep_start, rep_start + len(rep_value))] if opaque else _pieces(rep_value, bytes([component]), rep_start)
                for comp, (comp_value, comp_start, _comp_end) in enumerate(comps, 1):
                    subs = [(comp_value, comp_start, comp_start + len(comp_value))] if opaque else _pieces(comp_value, bytes([subcomponent]), comp_start)
                    for sub, (leaf, start, end) in enumerate(subs, 1):
                        if len(result["atoms"]) >= MAX_ATOMS:
                            result["errors"].append("too_many_atoms")
                            return result
                        ref = {"raw_sha256": digest, "segment_index": index, "group_id": group,
                               "field": number, "repetition": rep, "component": comp,
                               "subcomponent": sub, "byte_start": start, "byte_end": end}
                        decoded = {"text": leaf.decode("ascii"), "unsupported": []} if opaque else decode_escape(leaf, delimiters)
                        result["source_refs"].append(ref)
                        result["atoms"].append({"source_ref": ref, "raw_hex": leaf.hex(),
                                                "text": decoded["text"], "empty": leaf == b"",
                                                "null": leaf == b'""', "unsupported": decoded["unsupported"]})
        result["segments"].append({"index": index, "tag": tag, "group_id": group,
                                    "fields": fields, "byte_start": match.start(),
                                    "byte_end": match.end(), "terminator_hex": match.group(2).hex()})
    if cursor != len(raw):
        result["errors"].append("invalid_trailing_framing")
    return result


def serialize_message(parsed: dict) -> bytes:
    """Reopen the preserved original, refusing changed provenance.

    This is lossless lexical serialization, not an editable message builder.
    """
    if not isinstance(parsed.get("raw_hex"), str):
        raise ValueError("original_bytes_not_retained")
    raw = bytes.fromhex(parsed["raw_hex"])
    if hashlib.sha256(raw).hexdigest() != parsed["raw_sha256"]:
        raise ValueError("raw_hash_mismatch")
    return raw


def resolve_source_ref(raw: bytes, source_ref: dict) -> bytes:
    """Reject forged coordinates, hashes and offsets before reopening a raw leaf."""
    coordinates = ("segment_index", "field", "repetition", "component", "subcomponent", "byte_start", "byte_end")
    if not isinstance(source_ref, dict) or any(type(source_ref.get(name)) is not int for name in coordinates):
        raise ValueError("invalid_source_ref")
    parsed = parse_message(raw)
    if parsed["errors"] or source_ref not in parsed["source_refs"]:
        raise ValueError("invalid_source_ref")
    return raw[source_ref["byte_start"]:source_ref["byte_end"]]
