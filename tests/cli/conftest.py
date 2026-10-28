"""Builder-authored CLI checks; no independent semantic truth or live access."""

import json

import pytest
from h7loss.gen import generate_case
from .helpers import digest, write_json


@pytest.fixture
def developer_files(tmp_path):
    case = generate_case("dev-01", 1)
    source = tmp_path / "developer.hl7"
    source.write_bytes(case["raw"])
    dictionary = write_json(tmp_path / "dictionary.json", case["dictionary"])
    return source, dictionary, case


@pytest.fixture
def mock_files(tmp_path, developer_files):
    source, dictionary, case = developer_files
    config = {"case_id": case["case_id"], "config_id": "builder-unit-v1",
              "model": "authored-mock-only", "responses": [{"outcome": "success", "text": json.dumps({
                  "bundle": {"resourceType": "Bundle", "type": "collection", "entry": []},
                  "dispositions": []})}]}
    fixtures = write_json(tmp_path / "mock.json", config)
    return source, dictionary, fixtures, tmp_path / "mock.sqlite", config


@pytest.fixture
def ruling_files(tmp_path, developer_files):
    source, dictionary, _ = developer_files
    mapping = write_json(tmp_path / "mapping.json", {"builder_fixture": "not a semantic oracle"})
    key = {"site_id": "dev-01", "item_id": "builder-item-1",
           "source_hash": digest(source.read_bytes()), "dictionary_hash": digest(dictionary.read_bytes()),
           "mapping_hash": digest(mapping.read_bytes())}
    request = write_json(tmp_path / "ruling.json", {
        "key": key, "decision": {"action": "abstain", "reason": "Builder-only journal regression"},
        "actor": "builder-unit-test-not-independent", "basis": [{"sha256": key["source_hash"],
            "description": "Original developer input, not admitted evidence"}],
        "expected_revision": 0, "original_obligation": "abstain",
        "study_freeze_sha256": digest(b"authored simulated freeze, not actual study custody")})
    journal = tmp_path / "simulated.jsonl"
    args = ["rule", request, "--source", source, "--dictionary", dictionary,
            "--mapping", mapping, "--journal", journal]
    return args, journal, request, key
