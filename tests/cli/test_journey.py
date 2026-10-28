"""Developer command journeys; these assertions are not independent gold."""

import json

import pytest
from typer.testing import CliRunner

from h7loss.cli import app
from .helpers import call, digest, write_json


def test_help_and_authored_demo():
    help_result = CliRunner().invoke(app, ["--help"])
    assert help_result.exit_code == 0, help_result.output
    for command in ("demo", "mock-map", "mock-propose", "rule-replay", "report"):
        assert command in help_result.output
    result = call("demo", "--mock")
    assert result["raw_sha256"] == digest(result["raw_message"].encode("ascii"))
    assert result["parsed"]["raw_sha256"] == result["result"]["raw_sha256"] == result["raw_sha256"]
    assert result["status"] == "illustrative_only" and result["metrics"] is None
    assert result["validation"]["status"] == result["roundtrip"]["status"] == "not_run"
    assert result["cost"] == {"live_calls": 0, "spend_usd": "0"}
    assert result["runtime_verified"] is False


@pytest.mark.parametrize("command", ["admit", "validate", "roundtrip", "score", "eval", "live", "demo"])
def test_unapproved_commands_refuse(command):
    result = call(command, expected=2)
    assert result["status"] == "refused" and result["reason"]
    assert result["runtime_verified"] is False


def test_exports_parse_and_map(tmp_path):
    source, dictionary, case_path = (tmp_path / name for name in ("raw.hl7", "dict.json", "case.json"))
    generated = call("gen", "--output", source)
    call("dev-dictionary", dictionary)
    call("dev-case", case_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert source.read_bytes() == case["raw_message"].encode("ascii")
    assert json.loads(dictionary.read_text(encoding="utf-8")) == case["dictionary"]
    assert generated["artifact"]["sha256"] == case["raw_sha256"] == digest(source.read_bytes())
    assert call("parse", source)["result"]["errors"] == []
    mapped = call("map", source, "--dictionary", dictionary, expected=2)
    assert mapped["result"]["outcome"] == "partial"
    assert mapped["result"]["bundle"]["resourceType"] == "Bundle"
    assert mapped["result"]["dispositions"]
    assert mapped["dictionary_file_sha256"] == digest(dictionary.read_bytes())
    original = source.read_bytes()
    assert call("gen", "--output", source, expected=1)["error_type"] == "FileExistsError"
    assert source.read_bytes() == original


def test_invalid_proposal_refuses_before_execution(developer_files, tmp_path):
    source, dictionary, _ = developer_files
    proposal = write_json(tmp_path / "bad-proposal.json", {"code": "arbitrary code is forbidden"})
    result = call("propose", source, "--dictionary", dictionary, "--proposal", proposal, expected=2)
    assert result["status"] == "refused" and not result["proposal_check"]["valid"]


def test_authored_proposal_execution_and_binding_refusal(developer_files, tmp_path):
    source, dictionary, case = developer_files
    proposal = {"version": 1, "site_id": case["site_id"], "dictionary_sha256": case["dictionary_sha256"],
                "rules": [{"source": {"segment": "PID", "scope": "patient", "field": 3,
                    "repetition": 1, "component": 1, "subcomponent": 1},
                    "transform": "copy_text", "target": "patient.id"}]}
    path = write_json(tmp_path / "authored-proposal.json", proposal)
    args = ["propose", source, "--dictionary", dictionary, "--proposal", path]
    executed = call(*args)
    assert executed["result"]["outcome"] == "ok"
    assert executed["result"]["bundle"]["entry"][0]["resource"]["resourceType"] == "Patient"
    assert executed["result"]["dispositions"]
    proposal["dictionary_sha256"] = "0" * 64
    write_json(path, proposal)
    refused = call(*args, expected=2)
    assert refused["result"]["outcome"] == "error" and refused["result"]["bundle"] is None
    assert refused["result"]["error"] == "stale_dictionary"


def test_mock_map_persistence_and_replay_refusal(mock_files):
    source, dictionary, fixtures, ledger, _ = mock_files
    args = ["mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures, "--ledger", ledger]
    first = call(*args)
    assert first["namespace"] == "authored-mock"
    assert first["result"]["evidence_class"] == "authored_mock"
    assert first["ledger"]["spent"] == 0
    assert len(first["ledger"]["attempts"]) == 1
    replay = call(*args, expected=2)
    assert replay["result"]["outcome"] == "refused"
    assert replay["result"]["attempts"][0]["previously_dispatched"] is True
    assert call("ledger-report", ledger)["ledger"]["attempts"] == replay["ledger"]["attempts"]


def test_mock_syntax_repair_and_unknown_usage(mock_files):
    source, dictionary, fixtures, ledger, config = mock_files
    config["responses"].insert(0, {"outcome": "malformed", "text": "{"})
    write_json(fixtures, config)
    repaired = call("mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures, "--ledger", ledger)
    assert len(repaired["result"]["attempts"]) == 2
    config["config_id"] = "builder-unknown-unit-case"
    config["responses"] = [{"outcome": "unknown_usage", "text": config["responses"][1]["text"]}]
    config["max_liability_micro_usd"] = 7
    write_json(fixtures, config)
    unknown = call("mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures, "--ledger", ledger)
    assert unknown["result"]["attempts"][0]["usage_micro_usd"] is None
    assert unknown["ledger"]["held"] == 7
    assert unknown["ledger"]["spent"] == 0


def test_capped_mock_output_retains_original_hash(mock_files):
    source, dictionary, fixtures, ledger, config = mock_files
    capped = "x" * 32769
    config["responses"] = [{"outcome": "success", "text": capped}]
    write_json(fixtures, config)
    result = call("mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures,
                  "--ledger", ledger, expected=2)
    attempt = result["result"]["attempts"][0]
    assert attempt["output_omitted"] is True and attempt["raw_output_chars"] == len(capped)
    assert attempt["raw_output_sha256"] == digest(capped.encode()) and attempt["text"] == ""
    assert result["result"]["outcome"] == "error"


def test_mock_site_proposal_preserves_released_dictionary(tmp_path, developer_files):
    _, dictionary, case = developer_files
    before = dictionary.read_bytes()
    proposal = {"version": 1, "site_id": case["site_id"], "dictionary_sha256": case["dictionary_sha256"],
                "rules": [{"source": {"segment": "PID", "scope": "patient", "field": 3,
                    "repetition": 1, "component": 1, "subcomponent": 1},
                    "transform": "copy_text", "target": "patient.id"}]}
    fixtures = write_json(tmp_path / "site-mock.json", {"config_id": "builder-site-unit",
        "model": "authored-mock-only", "responses": [{"outcome": "success", "text": json.dumps(proposal)}]})
    result = call("mock-propose", dictionary, "--fixtures", fixtures, "--ledger", tmp_path / "site.sqlite")
    assert result["result"]["proposal"] == proposal
    assert result["result"]["evidence_class"] == "authored_mock"
    assert dictionary.read_bytes() == before


def test_simulated_journal_then_read_only_replay(ruling_files):
    args, journal, _, key = ruling_files
    assert call(*args, expected=2)["status"] == "refused"
    assert not journal.exists()
    written = call(*args, "--simulate")
    record = written["result"]["record"]
    assert record["simulated"] is True and record["key"] == key
    original = journal.read_bytes()
    replay = call("rule-replay", journal)
    assert replay["records"] == [record] and journal.read_bytes() == original
    refused = call(*args, "--simulate", expected=1)
    assert "new simulation journal" in refused["reason"]
    assert journal.read_bytes() == original
