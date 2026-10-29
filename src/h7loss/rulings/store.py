"""JSONL is authoritative. SQLite is a disposable replay projection only.

No implicit paths, environment reads, truth discovery, or automatic source edits.
Callers supply current input hashes and evidence; these checks do not appoint a
custodian or certify evidence. A ruling is a separate after-study intervention.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator


KEY_FIELDS = {"site_id", "dictionary_hash", "mapping_hash", "source_hash", "item_id"}
HASH_FIELDS = {"dictionary_hash", "mapping_hash", "source_hash"}
ACTIONS = {"abstain", "declare_drop", "map_with_supplement", "reject"}
ZERO_HASH = "0" * 64
MAX_RECORD_BYTES = 64 * 1024
RECORD_FIELDS = {
    "schema", "sequence", "previous_sha256", "key", "revision", "decision",
    "actor", "basis", "simulated", "phase", "original_obligation", "supplement",
    "created_at", "record_sha256", "study_freeze_sha256",
}


class RulingError(ValueError):
    """Malformed, stale, incomplete, or tampered authoritative evidence."""


class RulingConflict(RulingError):
    """Another writer already changed the item revision."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise RulingError("ruling must contain finite JSON values") from exc


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise RulingError(f"{name} must be nonempty text of at most 4096 characters")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise RulingError(f"{name} must be a lowercase SHA256")
    return value


def _key(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != KEY_FIELDS:
        raise RulingError("key must contain exactly site_id/dictionary_hash/mapping_hash/source_hash/item_id")
    return {name: (_hash(value[name], name) if name in HASH_FIELDS
                   else _text(value[name], name)) for name in sorted(KEY_FIELDS)}


def _identity(key: dict[str, str]) -> tuple[str, str]:
    return key["site_id"], key["item_id"]


def _validate_payload(record: dict[str, Any]) -> None:
    _key(record["key"])
    _text(record["actor"], "actor")
    _hash(record["study_freeze_sha256"], "study freeze receipt")
    if type(record["simulated"]) is not bool:
        raise RulingError("simulated must be an explicit boolean")
    if record["phase"] != "after_study_expanded_information":
        raise RulingError("rulings are after-study interventions only")
    if not isinstance(record["original_obligation"], str) or record["original_obligation"] not in {"preserve", "declare_drop", "abstain"}:
        raise RulingError("original obligation must be retained explicitly")
    decision = record["decision"]
    if not isinstance(decision, dict) or set(decision) != {"action", "reason"}:
        raise RulingError("decision requires exactly action and reason")
    if not isinstance(decision["action"], str) or decision["action"] not in ACTIONS:
        raise RulingError("unsupported ruling action")
    _text(decision["reason"], "decision reason")
    basis = record["basis"]
    if not isinstance(basis, list) or not 1 <= len(basis) <= 32:
        raise RulingError("one to 32 evidence references required")
    for evidence in basis:
        if not isinstance(evidence, dict) or set(evidence) != {"sha256", "description"}:
            raise RulingError("evidence requires exactly sha256 and description")
        _hash(evidence["sha256"], "evidence sha256")
        _text(evidence["description"], "evidence description")
    supplement = record["supplement"]
    if supplement is not None:
        if not isinstance(supplement, dict) or set(supplement) != {
            "sha256", "fictional", "custodian_authorization_sha256",
            "expanded_obligations_sha256",
        }:
            raise RulingError("supplement requires hash, fictional declaration, custodian receipt and expanded obligations hash")
        if supplement["fictional"] is not True:
            raise RulingError("only an original fictional dictionary supplement is eligible")
        for field in ("sha256", "custodian_authorization_sha256", "expanded_obligations_sha256"):
            _hash(supplement[field], field)
    if decision["action"] == "map_with_supplement" and supplement is None:
        raise RulingError("mapping requires a separate hash-bound dictionary supplement")
    if record["original_obligation"] == "abstain" and decision["action"] == "declare_drop":
        raise RulingError("unknown obligation cannot be relabeled as known loss")


class RulingStore:
    """Serialized local append journal; no authority is inferred from actor strings.

    The persistent sibling lock is shared by all operations. Journal durability
    is fsync-before-return; partial final lines are fatal and require operator
    recovery that preserves the damaged original. Never use this on an unlocked
    distributed filesystem without validating its locking semantics.
    """

    def __init__(self, journal: str | Path, index: str | Path | None = None):
        self.journal = Path(journal).absolute()
        self.index = Path(index).absolute() if index is not None else None
        if self.index == self.journal or self.index == self.journal.with_suffix(self.journal.suffix + ".lock"):
            raise RulingError("index must not alias journal or lock")
        self.lock = self.journal.with_suffix(self.journal.suffix + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.lock.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> list[dict[str, Any]]:
        if not self.journal.exists():
            return []
        records: list[dict[str, Any]] = []
        revisions: dict[tuple[str, str], int] = {}
        previous = ZERO_HASH
        with self.journal.open("rb") as handle:
            for sequence, line in enumerate(iter(lambda: handle.readline(MAX_RECORD_BYTES + 1), b""), 1):
                if len(line) > MAX_RECORD_BYTES or not line.endswith(b"\n"):
                    raise RulingError(f"incomplete/oversized journal record {sequence}; preserve original")
                try:
                    record = json.loads(line)
                except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                    raise RulingError(f"malformed journal record {sequence}") from exc
                if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
                    raise RulingError(f"unexpected fields at record {sequence}")
                _validate_payload(record)
                _text(record["created_at"], "created_at")
                if type(record["schema"]) is not int or record["schema"] != 1:
                    raise RulingError("unsupported journal schema")
                if type(record["sequence"]) is not int or record["sequence"] != sequence:
                    raise RulingError("journal sequence discontinuity")
                if record["previous_sha256"] != previous:
                    raise RulingError("journal hash chain mismatch")
                item = _identity(record["key"])
                revision = revisions.get(item, 0) + 1
                if type(record["revision"]) is not int or record["revision"] != revision:
                    raise RulingError("journal revision discontinuity")
                claimed = _hash(record["record_sha256"], "record hash")
                body = {name: value for name, value in record.items() if name != "record_sha256"}
                if hashlib.sha256(_canonical(body)).hexdigest() != claimed:
                    raise RulingError("journal record hash mismatch")
                # Reject duplicate keys/noncanonical encodings rather than parse a different truth.
                if _canonical(record) + b"\n" != line:
                    raise RulingError("journal record is not canonical JSONL")
                previous = claimed
                revisions[item] = revision
                records.append(record)
        return records

    def replay(self) -> list[dict[str, Any]]:
        """Verify and return the journal; never consult SQLite for truth."""
        with self._locked():
            return self._read()

    def append(
        self, key: dict[str, str], decision: dict[str, str], actor: str,
        basis: list[dict[str, str]], *, current_key: dict[str, str],
        expected_revision: int, original_obligation: str, simulated: bool,
        study_freeze_sha256: str,
        supplement: dict[str, Any] | None = None,
        supplement_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Append using item-wide revision CAS and exact current hash binding.

        Supplement authorization hashes are recorded evidence, not verified role
        appointments. Caller must independently admit them before applying a
        ruling. This store never edits mappings, expectations or original data.
        """
        normalized = _key(key)
        if normalized != _key(current_key):
            raise RulingError("stale ruling key: current input hashes differ")
        if type(expected_revision) is not int or expected_revision < 0:
            raise RulingError("expected_revision must be a nonnegative integer")
        if supplement is not None:
            if not isinstance(supplement, dict) or not isinstance(supplement_bytes, bytes) or hashlib.sha256(supplement_bytes).hexdigest() != supplement.get("sha256"):
                raise RulingError("supplement bytes must match the recorded dictionary hash")
        elif supplement_bytes is not None:
            raise RulingError("unexpected supplement bytes")
        # Snapshot inputs before acquiring the lock; caller mutations cannot alter stored bytes.
        payload = json.loads(_canonical({
            "key": normalized, "decision": decision, "actor": actor, "basis": basis,
            "original_obligation": original_obligation, "simulated": simulated,
            "supplement": supplement, "phase": "after_study_expanded_information",
            "study_freeze_sha256": study_freeze_sha256,
        }))
        _validate_payload(payload)
        with self._locked():
            records = self._read()
            prior = [record for record in records if _identity(record["key"]) == _identity(normalized)]
            revision = prior[-1]["revision"] if prior else 0
            if revision != expected_revision:
                raise RulingConflict(f"revision conflict: expected {expected_revision}, current {revision}")
            record = {
                **payload, "schema": 1, "sequence": len(records) + 1,
                "revision": revision + 1,
                "previous_sha256": records[-1]["record_sha256"] if records else ZERO_HASH,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            record["record_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
            line = _canonical(record) + b"\n"
            if len(line) > MAX_RECORD_BYTES:
                raise RulingError("ruling exceeds journal record limit")
            with self.journal.open("ab") as handle:
                if handle.write(line) != len(line):
                    raise RulingError("short journal write; preserve journal and recover before use")
                handle.flush()
                os.fsync(handle.fileno())
            # Projection is explicitly separate: its failure must never encourage retrying a committed append.
            return {"record": record, "durable_journal": True, "projection": "rebuild_required"}

    def current(self, key: dict[str, str]) -> dict[str, Any] | None:
        """Return an exact current binding, or refuse a stale last ruling."""
        normalized = _key(key)
        with self._locked():
            matches = [record for record in self._read()
                       if _identity(record["key"]) == _identity(normalized)]
            if not matches:
                return None
            if matches[-1]["key"] != normalized:
                raise RulingError("latest ruling belongs to stale input hashes")
            return matches[-1]

    def conflicts(self, key: dict[str, str], expected_revision: int) -> dict[str, Any]:
        normalized = _key(key)
        with self._locked():
            matches = [record for record in self._read()
                       if _identity(record["key"]) == _identity(normalized)]
            latest = matches[-1] if matches else None
            revision = latest["revision"] if latest else 0
            return {"conflict": revision != expected_revision,
                    "stale": latest is not None and latest["key"] != normalized,
                    "current_revision": revision}

    def rebuild_index(self) -> dict[str, Any]:
        """Replace projection rows transactionally from a verified journal."""
        if self.index is None:
            raise RulingError("no index path configured")
        with self._locked():
            records = self._read()
            # Protect authoritative files even when two configured names alias one inode.
            for protected in (self.journal, self.lock):
                if self.index.resolve() == protected.resolve() or (
                    self.index.exists() and protected.exists() and self.index.samefile(protected)
                ):
                    raise RulingError("index aliases an authoritative journal/lock file")
            self.index.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.index)) as connection, connection:
                connection.execute("CREATE TABLE IF NOT EXISTS ruling_projection (sequence INTEGER PRIMARY KEY, site_id TEXT NOT NULL, item_id TEXT NOT NULL, revision INTEGER NOT NULL, record_sha256 TEXT NOT NULL, record_json TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS projection_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), journal_head TEXT NOT NULL, record_count INTEGER NOT NULL)")
                connection.execute("DELETE FROM ruling_projection")
                connection.executemany("INSERT INTO ruling_projection VALUES (?, ?, ?, ?, ?, ?)", [
                    (record["sequence"], record["key"]["site_id"], record["key"]["item_id"],
                     record["revision"], record["record_sha256"], _canonical(record).decode("utf-8"))
                    for record in records
                ])
                head = records[-1]["record_sha256"] if records else ZERO_HASH
                connection.execute("INSERT OR REPLACE INTO projection_metadata VALUES (1, ?, ?)", (head, len(records)))
            return {"projection": "rebuilt", "record_count": len(records), "journal_head": head}
