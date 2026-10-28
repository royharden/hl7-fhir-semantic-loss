"""Builder journal expectations only; fake hashes never authenticate outside roles."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from h7loss.rulings import RulingConflict, RulingError, RulingStore


@pytest.fixture
def ruling(tmp_path):
    store = RulingStore(tmp_path / "builder-journal.jsonl", tmp_path / "builder-index.sqlite")
    key = {"site_id": "builder-unit-site", "dictionary_hash": "a" * 64,
           "mapping_hash": "b" * 64, "source_hash": "c" * 64, "item_id": "unit-item"}

    def append(*, revision=0, decision=None, key_override=None, current_key=None,
               actor="builder-unit-test", basis=None, original_obligation="abstain",
               simulated=True, supplement=None, supplement_bytes=None):
        bound = key if key_override is None else key_override
        return store.append(bound, decision or {"action": "abstain", "reason": "builder fixture unknown"},
            actor, [{"sha256": "d" * 64, "description": "synthetic builder evidence fixture"}] if basis is None else basis,
            current_key=bound if current_key is None else current_key, expected_revision=revision,
            original_obligation=original_obligation, simulated=simulated,
            study_freeze_sha256="e" * 64, supplement=supplement, supplement_bytes=supplement_bytes)

    return store, key, append


def test_append_replay_and_revision_cas_preserve_authoritative_history(ruling):
    store, key, append = ruling
    first = append()["record"]
    assert first["revision"] == 1 and first["simulated"] is True
    assert first["original_obligation"] == "abstain"
    with pytest.raises(RulingConflict):
        append(revision=0)
    second = append(revision=1, decision={"action": "reject", "reason": "builder fixture rejects intervention"})["record"]
    assert second["revision"] == 2 and second["previous_sha256"] == first["record_sha256"]
    assert store.replay() == [first, second]
    assert store.current(key) == second
    assert store.conflicts(key, 1) == {"conflict": True, "stale": False, "current_revision": 2}


def test_stale_hash_binding_never_silently_reuses_old_ruling(ruling):
    store, key, append = ruling
    append()
    changed = {**key, "dictionary_hash": "f" * 64}
    with pytest.raises(RulingError, match="stale ruling key"):
        append(revision=1, current_key=changed)
    with pytest.raises(RulingError, match="stale input hashes"):
        store.current(changed)
    assert store.conflicts(changed, 1) == {"conflict": False, "stale": True, "current_revision": 1}
    assert len(store.replay()) == 1


def test_new_input_binding_uses_item_wide_revision_and_preserves_prior_record(ruling):
    store, key, append = ruling
    first = append()["record"]
    changed = {**key, "source_hash": "f" * 64}
    with pytest.raises(RulingConflict):
        append(key_override=changed, revision=0)
    second = append(key_override=changed, revision=1)["record"]
    assert second["revision"] == 2
    assert store.current(changed) == second
    with pytest.raises(RulingError, match="stale input hashes"):
        store.current(key)
    assert store.replay()[0] == first


@pytest.mark.parametrize("changes", [
    {"actor": ""}, {"basis": []}, {"simulated": "true"},
    {"basis": [{"sha256": "not-a-hash", "description": "builder fixture"}]},
    {"decision": {"action": "declare_drop", "reason": "must not relabel unknown"}},
    {"decision": {"action": "map_with_supplement", "reason": "no released supplement"}},
])
def test_invalid_or_unknown_relabeling_payload_does_not_append(ruling, changes):
    store, _key, append = ruling
    with pytest.raises(RulingError):
        append(**changes)
    assert store.replay() == []


def test_mapping_supplement_requires_matching_bytes_and_separate_evidence(ruling):
    store, _key, append = ruling
    raw = b'{"kind":"original fictional builder dictionary supplement"}'
    metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "fictional": True,
                "custodian_authorization_sha256": "1" * 64, "expanded_obligations_sha256": "2" * 64}
    decision = {"action": "map_with_supplement", "reason": "builder simulated expanded information"}
    with pytest.raises(RulingError, match="supplement bytes"):
        append(decision=decision, supplement=metadata, supplement_bytes=raw + b"tamper")
    record = append(decision=decision, supplement=metadata, supplement_bytes=raw)["record"]
    assert record["supplement"] == metadata
    assert record["original_obligation"] == "abstain" and record["simulated"] is True
    assert record["phase"] == "after_study_expanded_information"
    assert store.replay() == [record]


def test_truncated_crash_tail_is_refused_without_mutating_original(ruling):
    store, _key, append = ruling
    append()
    with store.journal.open("ab") as handle:
        handle.write(b'{"partial_crash_tail":')
    damaged = store.journal.read_bytes()
    with pytest.raises(RulingError, match="incomplete/oversized"):
        store.replay()
    with pytest.raises(RulingError):
        append(revision=1)
    assert store.journal.read_bytes() == damaged


def test_tampered_record_and_noncanonical_encoding_are_refused(ruling):
    store, _key, append = ruling
    append()
    original = store.journal.read_bytes()
    record = json.loads(original)
    record["actor"] = "tampered-builder-fixture"
    store.journal.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    with pytest.raises(RulingError, match="hash mismatch"):
        store.replay()
    store.journal.write_bytes(original.replace(b'{"actor":', b'{ "actor":', 1))
    with pytest.raises(RulingError, match="not canonical"):
        store.replay()


def test_projection_rebuild_uses_journal_instead_of_corrupted_sqlite_truth(ruling):
    store, _key, append = ruling
    first = append()["record"]
    result = store.rebuild_index()
    assert result == {"projection": "rebuilt", "record_count": 1, "journal_head": first["record_sha256"]}
    with sqlite3.connect(store.index) as connection:
        connection.execute("UPDATE ruling_projection SET record_json='corrupt-projection'")
        connection.execute("UPDATE projection_metadata SET record_count=99")
    assert store.replay() == [first]
    assert store.rebuild_index()["record_count"] == 1
    with sqlite3.connect(store.index) as connection:
        assert json.loads(connection.execute("SELECT record_json FROM ruling_projection").fetchone()[0]) == first
        assert connection.execute("SELECT record_count FROM projection_metadata").fetchone()[0] == 1


def test_projection_alias_cannot_replace_authoritative_journal(tmp_path):
    journal = tmp_path / "journal.jsonl"
    with pytest.raises(RulingError, match="alias"):
        RulingStore(journal, journal)
    with pytest.raises(RulingError, match="alias"):
        RulingStore(journal, journal.with_suffix(".jsonl.lock"))


def test_concurrent_journal_writers_cannot_both_claim_revision_zero(ruling):
    store, key, _append = ruling
    start = Barrier(2)

    def write(number):
        writer = RulingStore(store.journal, store.index)
        start.wait(timeout=10)
        try:
            writer.append(key, {"action": "abstain", "reason": "builder concurrent fixture"},
                "builder-unit-test", [{"sha256": "d" * 64, "description": f"builder writer {number}"}],
                current_key=key, expected_revision=0, original_obligation="abstain",
                simulated=True, study_freeze_sha256="e" * 64)
            return "appended"
        except RulingConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, (1, 2)))
    assert sorted(outcomes) == ["appended", "conflict"]
    assert len(store.replay()) == 1


def test_record_size_bound_refuses_before_journal_append(ruling):
    store, _key, append = ruling
    evidence = [{"sha256": "d" * 64, "description": "x" * 4096} for _ in range(32)]
    with pytest.raises(RulingError, match="record limit"):
        append(basis=evidence)
    assert store.replay() == []


def test_recursive_payload_is_a_typed_refusal(ruling):
    store, _key, append = ruling
    recursive = {}
    recursive["self"] = recursive
    with pytest.raises(RulingError, match="finite JSON"):
        append(decision=recursive)
    assert store.replay() == []
