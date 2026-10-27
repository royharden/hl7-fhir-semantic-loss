"""Phase-one ZIP allowlist reader. No extraction, truth discovery or admission GO."""
from __future__ import annotations

import json
import re
import stat
import zipfile
from pathlib import Path

from .common import Refusal, require_hash, sha256

_FORBIDDEN = {"truth", "oracle", "expected", "expectations", "assertions", "atoms",
              "latent", "profiles", "profile", "seeds", "seed", "generator", "calibration",
              "gold", "hidden", "reconstruct", "reconstruction", "outcomes", "answers"}
_PREFIX = {"metadata": "metadata", "raw": "raw", "dictionary": "dictionary", "onboarding": "onboarding"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _token(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise Refusal(f"invalid {name}")
    return value


def _forbidden_key(value):
    # CamelCase, punctuation and snake-case variants are all inspected.
    expanded = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    words = set(re.findall(r"[a-z]+", expanded.lower()))
    return bool(words & _FORBIDDEN)


def member_path(name, kind=None):
    """Accept canonical portable paths only; never normalize a dangerous path."""
    if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name:
        raise Refusal("invalid archive path")
    parts = name.split("/")
    if len(parts) < 2 or any(not p or p in {".", ".."} for p in parts):
        raise Refusal("absolute, traversal or empty path component")
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) or part.endswith((".", " ")):
            raise Refusal("nonportable, drive, hidden or stream path")
        if part.split(".", 1)[0].upper() in _RESERVED or _forbidden_key(part):
            raise Refusal("reserved or forbidden archive member")
    if kind is not None:
        if kind not in _PREFIX or parts[0] != _PREFIX[kind]:
            raise Refusal("archive kind/prefix mismatch")
        extension = ".json" if kind in {"metadata", "dictionary"} else ".hl7"
        if not name.endswith(extension):
            raise Refusal("archive kind/extension mismatch")
    return name


def _object(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - (set(required) | set(optional)) or not set(required) <= set(value):
        raise Refusal("unknown, missing or reconstructive JSON fields")
    if any(not isinstance(k, str) or _forbidden_key(k) for k in value):
        raise Refusal("forbidden JSON field")
    return value


def validate_phase1_metadata(value):
    """Validate a released metadata document: schema_version=1 and cases list.

    The only per-case fields are public source identities, explicit paths,
    usage and namespace. No seed, latent record, expected outcome or profile.
    """
    _object(value, {"schema_version", "cases"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise Refusal("unsupported phase-one metadata version")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases or len(cases) > 10_000:
        raise Refusal("bounded nonempty cases list required")
    seen = set()
    for row in cases:
        _object(row, {"case_id", "site_id", "raw_sha256", "dictionary_sha256", "message_path", "dictionary_path", "usage", "namespace"})
        case = _token(row["case_id"], "case_id")
        _token(row["site_id"], "site_id")
        if case in seen:
            raise Refusal("duplicate metadata case")
        seen.add(case)
        require_hash(row["raw_sha256"])
        require_hash(row["dictionary_sha256"])
        if row["usage"] not in {"scored", "onboarding"} or row["namespace"] not in {"authored_fixture", "offline_dev", "heldout"}:
            raise Refusal("explicit permitted usage/namespace required")
        member_path(row["message_path"], "onboarding" if row["usage"] == "onboarding" else "raw")
        member_path(row["dictionary_path"], "dictionary")
    return value


def _public_string(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise Refusal("bounded public dictionary string required")


def _string_map(value):
    if not isinstance(value, dict) or len(value) > 10_000:
        raise Refusal("bounded public dictionary map required")
    for key, item in value.items():
        _token(key, "dictionary key")
        if _forbidden_key(key):
            raise Refusal("reconstructive dictionary key")
        _public_string(item)


def validate_dictionary(value):
    """Only the declared public developer dictionary shape is supported.

    Arbitrary Z conventions and schema extensions require a later released
    contract. This structural check never establishes rights or blindness.
    """
    required = {"dictionary_id", "provenance", "codes", "identifier_systems", "observation_statuses", "report_statuses", "coding_authorities", "units", "value_codes", "z_segments"}
    _object(value, required)
    _token(value["dictionary_id"], "dictionary_id")
    _object(value["provenance"], {"kind", "admission", "rights_review", "independent_semantic_review", "purpose"})
    for item in value["provenance"].values():
        _public_string(item)
    for name in ("codes", "units", "value_codes"):
        mapping = value[name]
        if not isinstance(mapping, dict) or len(mapping) > 10_000:
            raise Refusal("bounded code map required")
        for key, coding in mapping.items():
            _token(key, "code key")
            if _forbidden_key(key):
                raise Refusal("reconstructive code key")
            _object(coding, {"system", "code", "display"})
            for item in coding.values():
                _public_string(item)
    for name in ("identifier_systems", "observation_statuses", "report_statuses"):
        _string_map(value[name])
    authorities = value["coding_authorities"]
    if not isinstance(authorities, dict) or len(authorities) > 10_000:
        raise Refusal("bounded coding authorities required")
    for key, systems in authorities.items():
        _token(key, "authority key")
        if _forbidden_key(key) or not isinstance(systems, list) or not systems or len(systems) > 100:
            raise Refusal("unsupported authority")
        for system in systems:
            _public_string(system)
    if value["z_segments"] != {}:
        raise Refusal("released Z dictionary contract unavailable")
    return value


def _json_document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal("duplicate JSON object key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(Refusal("nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise Refusal("malformed JSON member") from error


def read_phase1_zip(archive_path, manifest, *, archive_sha256, max_member_bytes=2_000_000, max_total_bytes=20_000_000):
    """Read caller-selected archive only. Manifest is a list of path/kind/sha256.

    Returns a bytes mapping; it never writes/extracts members. Expected archive
    and member hashes must come from an independently admitted release.
    """
    require_hash(archive_sha256)
    for cap in (max_member_bytes, max_total_bytes):
        if type(cap) is not int or cap < 1:
            raise Refusal("positive size caps required")
    if not isinstance(manifest, list) or not manifest or len(manifest) > 10_000:
        raise Refusal("bounded explicit manifest required")
    expected, folded = {}, set()
    for row in manifest:
        _object(row, {"path", "kind", "sha256"})
        name = member_path(row["path"], row["kind"])
        require_hash(row["sha256"])
        if name.casefold() in folded:
            raise Refusal("duplicate or case-alias manifest member")
        folded.add(name.casefold())
        expected[name] = row
    path = Path(archive_path)
    chain = (path, *path.parents)
    if any(part.is_symlink() or getattr(part.lstat(), "st_file_attributes", 0) & 0x400 for part in chain) or not path.is_file():
        raise Refusal("archive must be an explicit ordinary file without symlink parents")
    if path.stat().st_size > max_total_bytes:
        raise Refusal("compressed archive exceeds cap")
    raw_archive = path.read_bytes()
    if len(raw_archive) > max_total_bytes or sha256(raw_archive) != archive_sha256:
        raise Refusal("archive size/hash mismatch")
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(raw_archive)) as archive:
            infos = archive.infolist()
            if len(infos) != len(expected):
                raise Refusal("unexpected or missing archive members")
            seen, total = set(), 0
            for info in infos:
                name = info.filename
                if info.orig_filename != name or name not in expected or name.casefold() in seen:
                    raise Refusal("unexpected, truncated or duplicate member")
                member_path(name, expected[name]["kind"])
                seen.add(name.casefold())
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if info.is_dir() or info.external_attr & 0x10 or file_type not in {0, stat.S_IFREG} or info.flag_bits & 1:
                    raise Refusal("directory, symlink, special or encrypted member")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise Refusal("unsupported compression")
                if info.file_size < 0 or info.file_size > max_member_bytes:
                    raise Refusal("member size cap exceeded")
                total += info.file_size
                if total > max_total_bytes:
                    raise Refusal("uncompressed total cap exceeded")
            members = {}
            for info in infos:
                with archive.open(info) as stream:
                    data = stream.read(max_member_bytes + 1)
                if len(data) != info.file_size or len(data) > max_member_bytes or sha256(data) != expected[info.filename]["sha256"]:
                    raise Refusal("member size/hash mismatch")
                members[info.filename] = data
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise Refusal("unreadable phase-one ZIP") from error
    referenced, case_ids = set(), set()
    for name, row in expected.items():
        if row["kind"] == "dictionary":
            validate_dictionary(_json_document(members[name]))
        elif row["kind"] == "metadata":
            metadata = validate_phase1_metadata(_json_document(members[name]))
            for case in metadata["cases"]:
                if case["case_id"] in case_ids:
                    raise Refusal("duplicate case across metadata documents")
                case_ids.add(case["case_id"])
                for field, hash_field, kind in (("message_path", "raw_sha256", "onboarding" if case["usage"] == "onboarding" else "raw"), ("dictionary_path", "dictionary_sha256", "dictionary")):
                    target = case[field]
                    if target not in expected or expected[target]["kind"] != kind or expected[target]["sha256"] != case[hash_field]:
                        raise Refusal("metadata member/hash binding mismatch")
                    referenced.add(target)
    if not any(row["kind"] == "metadata" for row in manifest):
        raise Refusal("metadata document required")
    if any(row["kind"] != "metadata" and name not in referenced for name, row in expected.items()):
        raise Refusal("unreferenced archive member")
    return members
