"""Explicit local freeze/open-once records. No archive extraction or truth loading.
The caller supplies paths; held-out custodians must enforce isolation outside this process.
"""
import json
import os
from pathlib import Path
from .common import Refusal, digest, require_hash, sha256

def snapshot(files):
    if not files:
        raise Refusal("empty freeze")
    result = {}
    for name, path in sorted(files.items()):
        if not name or name in result:
            raise Refusal("invalid logical file id")
        p = Path(path)
        if p.is_symlink() or not p.is_file():
            raise Refusal("freeze requires ordinary explicit files")
        result[name] = sha256(p.read_bytes())
    return result

def write_once(path, record):
    data = json.dumps(record, sort_keys=True, allow_nan=False).encode()
    # O_EXCL is the single-host concurrency boundary; partial files fail closed.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())

def freeze(path, files, *, run_id, actor, protocol_sha256, attempt_ids):
    require_hash(protocol_sha256)
    if not run_id or not actor or not attempt_ids or len(set(attempt_ids)) != len(attempt_ids):
        raise Refusal("run/actor/complete unique attempt ids required")
    record = {"version": 1, "run_id": run_id, "actor": actor, "protocol_sha256": protocol_sha256,
              "attempt_ids": sorted(attempt_ids), "files": snapshot(files)}
    write_once(path, record)
    return {"record": record, "freeze_sha256": digest(record)}

def open_once(marker_path, frozen_record, files, *, actor, truth_sha256, expected_freeze_sha256):
    require_hash(truth_sha256)
    require_hash(expected_freeze_sha256)
    if not actor or digest(frozen_record) != expected_freeze_sha256:
        raise Refusal("freeze identity mismatch")
    if snapshot(files) != frozen_record.get("files"):
        raise Refusal("frozen outputs drifted")
    record = {"freeze_sha256": expected_freeze_sha256, "truth_sha256": truth_sha256,
              "actor": actor, "state": "opened_once", "run_id": frozen_record["run_id"]}
    write_once(marker_path, record)
    return record
