"""Original builder-authored lexical regressions, not independent/gold data."""

import hashlib

import pytest

import h7loss.v2 as v2
from h7loss.gen import generate_case


HEADER = b"MSH|^~\\&|DEV|DEV|LOCAL|LOCAL|20260102120000+0000||ORU^R01|case|P|2.8\r"
DELIMITERS = {"field": "|", "component": "^", "repetition": "~", "escape": "\\", "subcomponent": "&"}


def _atoms(parsed, segment_index, field):
    return [atom for atom in parsed["atoms"]
            if atom["source_ref"]["segment_index"] == segment_index
            and atom["source_ref"]["field"] == field]


@pytest.mark.parametrize("index", range(50))
def test_developer_messages_keep_original_bytes_hash_and_leaf_spans(index):
    # Alternating original sites exercises CR and CRLF without a hidden corpus.
    case = generate_case("dev-01" if index % 2 == 0 else "dev-02", index)
    raw = case["raw"]
    parsed = v2.parse_message(raw)
    assert parsed["errors"] == []
    assert parsed["unsupported"] == []
    assert v2.serialize_message(parsed) == raw
    assert parsed["raw_sha256"] == hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
    assert len(parsed["source_refs"]) == len(parsed["atoms"])
    for atom in parsed["atoms"]:
        ref = atom["source_ref"]
        assert ref["raw_sha256"] == parsed["raw_sha256"]
        assert 0 <= ref["byte_start"] <= ref["byte_end"] <= len(raw)
        assert raw[ref["byte_start"]:ref["byte_end"]] == bytes.fromhex(atom["raw_hex"])
    # Resolve a few exact coordinates rather than reparsing for every leaf.
    for ref in (parsed["source_refs"][0], parsed["source_refs"][-1]):
        assert v2.resolve_source_ref(raw, ref) == raw[ref["byte_start"]:ref["byte_end"]]


def test_msh_separator_and_encoding_fields_are_opaque_original_spans():
    parsed = v2.parse_message(HEADER)
    separator = _atoms(parsed, 0, 1)
    encoding = _atoms(parsed, 0, 2)
    assert len(separator) == len(encoding) == 1
    assert separator[0]["text"] == "|"
    assert separator[0]["source_ref"]["byte_start"] == 3
    assert separator[0]["source_ref"]["byte_end"] == 4
    assert encoding[0]["text"] == "^~\\&"
    assert encoding[0]["source_ref"]["byte_start"] == 4
    assert encoding[0]["source_ref"]["byte_end"] == 8
    assert _atoms(parsed, 0, 9)[0]["text"] == "ORU"
    assert _atoms(parsed, 0, 9)[1]["text"] == "R01"
    assert _atoms(parsed, 0, 12)[0]["text"] == "2.8"


@pytest.mark.parametrize(("raw", "text"), [
    (b"plain", "plain"), (b"\\F\\", "|"), (b"\\S\\", "^"),
    (b"\\T\\", "&"), (b"\\R\\", "~"), (b"\\E\\", "\\"),
    (b"a\\.br\\b", "a\nb"), (b"\\X3C3e\\", "<>"),
])
def test_supported_escapes_decode_without_losing_original_leaf(raw, text):
    assert v2.decode_escape(raw, DELIMITERS) == {"text": text, "unsupported": []}
    message = HEADER + b"PID|1\rOBR|1\rOBX|1|ST|CODE||" + raw + b"\r"
    atom = _atoms(v2.parse_message(message), 3, 5)[0]
    assert atom["text"] == text
    assert bytes.fromhex(atom["raw_hex"]) == raw


@pytest.mark.parametrize(("raw", "reason"), [
    (b"trailing\\", "unterminated_escape"),
    (b"\\H\\", "unsupported_escape"),
    (b"\\X0\\", "unsupported_escape"),
    (b"\\XGG\\", "invalid_hex_escape"),
    (b"\\XFF\\", "unsupported_charset"),
    (b"\xff", "unsupported_charset"),
])
def test_unsupported_escape_or_charset_never_guesses_text(raw, reason):
    decoded = v2.decode_escape(raw, DELIMITERS)
    assert decoded["text"] is None
    assert reason in decoded["unsupported"]


def test_repeat_component_subcomponent_and_empty_null_are_distinct():
    raw = HEADER + b'PID|1||""|\rOBR|1\rOBX|1|ST|CODE||alpha&part^other~second\r'
    parsed = v2.parse_message(raw)
    assert parsed["errors"] == []
    leaves = _atoms(parsed, 3, 5)
    assert [(a["source_ref"]["repetition"], a["source_ref"]["component"],
             a["source_ref"]["subcomponent"], a["text"]) for a in leaves] == [
        (1, 1, 1, "alpha"), (1, 1, 2, "part"),
        (1, 2, 1, "other"), (2, 1, 1, "second"),
    ]
    empty = _atoms(parsed, 1, 2)[0]
    null = _atoms(parsed, 1, 3)[0]
    trailing_empty = _atoms(parsed, 1, 4)[0]
    assert empty["empty"] and not empty["null"]
    assert empty["source_ref"]["byte_start"] == empty["source_ref"]["byte_end"]
    assert null["null"] and not null["empty"] and null["text"] == '""'
    assert trailing_empty["empty"] and not trailing_empty["null"]


def test_custom_delimiters_control_lexical_structure_and_escape_decode():
    raw = b"MSH*$%!@*DEV\rPID*1\rOBR*1\rOBX*1*ST*CODE**one!F!literal%two$part@sub\r"
    parsed = v2.parse_message(raw)
    assert parsed["errors"] == []
    assert parsed["delimiters"] == {
        "field": "*", "component": "$", "repetition": "%", "escape": "!", "subcomponent": "@",
    }
    assert [a["text"] for a in _atoms(parsed, 3, 5)] == ["one*literal", "two", "part", "sub"]
    assert v2.serialize_message(parsed) == raw


def test_order_observation_and_note_scopes_do_not_bleed_between_orders():
    raw = (HEADER + b"PID|1\rORC|RE\rOBR|1\rNTE|1||order-a\r"
           b"OBX|1|ST|CODE||a\rNTE|1||obs-a\r"
           b"ORC|RE\rOBR|2\rNTE|1||order-b\rOBX|1|ST|CODE||b\rNTE|1||obs-b\r")
    parsed = v2.parse_message(raw)
    assert parsed["errors"] == []
    assert parsed["unsupported"] == []
    assert [s["group_id"] for s in parsed["segments"] if s["tag"] == "NTE"] == [
        "patient:0/order:0", "patient:0/order:0/observation:0",
        "patient:0/order:1", "patient:0/order:1/observation:0",
    ]


@pytest.mark.parametrize(("raw", "reason"), [
    (b"", "missing_msh"), (b"MSH|", "missing_msh"),
    (b"MSH|^~\\&", "unsupported_encoding_characters"),
    (b"MSH|^^\\&|DEV\r", "invalid_delimiters"),
    (b"MSH|^~\\&XDEV\r", "unsupported_encoding_characters"),
    (HEADER + b"\rPID|1\r", "empty_or_invalid_segment_framing"),
    (HEADER + b"OB\r", "invalid_segment:1"),
    (HEADER + b"PID|1\r\r", "invalid_trailing_framing"),
])
def test_malformed_or_truncated_framing_has_explicit_error(raw, reason):
    assert reason in v2.parse_message(raw)["errors"]


@pytest.mark.parametrize(("raw", "reason"), [
    (HEADER.replace(b"\r", b"\n"), "lf_only_segment_terminator"),
    (HEADER + b"PID|1\rPID|2\r", "multiple_patient_groups"),
    (HEADER + b"PID|1\rOBX|1|ST|CODE||value\r", "observation_without_order"),
    (HEADER + HEADER, "repeated_msh"),
    (HEADER + b"ABC|opaque\r", "segment:ABC"),
])
def test_unsupported_framing_and_groups_are_reported_not_normalized(raw, reason):
    parsed = v2.parse_message(raw)
    assert reason in parsed["unsupported"]
    assert v2.serialize_message(parsed) == raw


def test_unterminated_final_segment_is_archived_without_inventing_terminator():
    raw = HEADER + b"PID|1"
    parsed = v2.parse_message(raw)
    assert parsed["errors"] == []
    assert parsed["segments"][-1]["terminator_hex"] == ""
    assert v2.serialize_message(parsed) == raw


def test_message_limit_refuses_before_retaining_large_original(monkeypatch):
    monkeypatch.setattr(v2, "MAX_MESSAGE_BYTES", len(HEADER) - 1)
    parsed = v2.parse_message(HEADER)
    assert parsed["errors"] == ["message_too_large"]
    assert parsed["raw_hex"] is None and parsed["atoms"] == []
    with pytest.raises(ValueError, match="original_bytes_not_retained"):
        v2.serialize_message(parsed)


def test_segment_limit_refuses_explicitly(monkeypatch):
    monkeypatch.setattr(v2, "MAX_SEGMENTS", 2)
    parsed = v2.parse_message(HEADER + b"PID|1\rOBR|1\r")
    assert parsed["errors"] == ["too_many_segments"]
    assert parsed["atoms"] == []


def test_exact_atom_limit_is_accepted_and_next_atom_is_refused(monkeypatch):
    # MSH-1 separator, opaque MSH-2 and MSH-3 comprise exactly three atoms.
    monkeypatch.setattr(v2, "MAX_ATOMS", 3)
    exact = v2.parse_message(b"MSH|^~\\&|A\r")
    assert len(exact["atoms"]) == 3
    assert exact["errors"] == []
    over = v2.parse_message(b"MSH|^~\\&|A|B\r")
    assert "too_many_atoms" in over["errors"]


def test_serialization_rejects_tampered_original_bytes():
    parsed = v2.parse_message(HEADER)
    parsed["raw_hex"] = (HEADER + b"PID|tampered\r").hex()
    with pytest.raises(ValueError, match="raw_hash_mismatch"):
        v2.serialize_message(parsed)


@pytest.mark.parametrize(("key", "replacement"), [
    ("raw_sha256", "0" * 64), ("segment_index", 99),
    ("group_id", "patient:0/order:99"), ("byte_start", 0),
    ("byte_end", 99), ("field", 99),
])
def test_forged_source_coordinates_do_not_resolve(key, replacement):
    raw = HEADER + b"PID|value\r"
    parsed = v2.parse_message(raw)
    ref = dict(_atoms(parsed, 1, 1)[0]["source_ref"])
    ref[key] = replacement
    with pytest.raises(ValueError, match="invalid_source_ref"):
        v2.resolve_source_ref(raw, ref)


@pytest.mark.parametrize(("key", "replacement"), [
    ("field", True), ("component", 1.0), ("subcomponent", True),
])
def test_bool_and_float_coordinate_aliases_are_not_exact_source_refs(key, replacement):
    # Python considers True == 1 and 1.0 == 1; source coordinates require ints.
    raw = HEADER + b"PID|value\r"
    ref = dict(_atoms(v2.parse_message(raw), 1, 1)[0]["source_ref"])
    ref[key] = replacement
    with pytest.raises(ValueError, match="invalid_source_ref"):
        v2.resolve_source_ref(raw, ref)


def test_hostile_text_remains_inert_literal_bytes_and_text():
    payload = b"<script>alert('developer fixture')</script> file:///hidden $(never-run)"
    raw = HEADER + b"PID|1\rOBR|1\rOBX|1|ST|CODE||" + payload + b"\r"
    parsed = v2.parse_message(raw)
    assert _atoms(parsed, 3, 5)[0]["text"] == payload.decode("ascii")
    assert v2.serialize_message(parsed) == raw


@pytest.mark.parametrize("raw", [None, "MSH|text", bytearray(b"MSH|text")])
def test_nonbytes_input_is_explicitly_rejected(raw):
    with pytest.raises(TypeError, match="raw must be bytes"):
        v2.parse_message(raw)
