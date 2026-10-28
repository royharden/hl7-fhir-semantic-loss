"""Builder malicious-input, artifact integrity and filesystem refusal regressions."""

import json
import os
from html.parser import HTMLParser

import pytest

from .helpers import call, digest, write_json


def test_report_roundtrip_escaping_and_failure_provenance(tmp_path):
    attack = '</pre><script src="https://invalid.example/x">alert(1)</script><img src=x onerror=alert(2)>'
    record = {"record_kind": "site_setup", "semantic_error": None, "validation": {"status": "not_run"},
              "result": {"outcome": "unsupported", "error": attack,
                         "attempts": [{"output_omitted": True, "raw_output_sha256": "a" * 64}]},
              "failures": [{"reason": attack}, {"reason": "second authored failure"}]}
    source = write_json(tmp_path / "supplied.json", record)
    html_output, json_output = tmp_path / "report.html", tmp_path / "report.json"
    receipt = call("report", source, "--output", html_output)
    assert receipt["artifact"]["sha256"] == digest(html_output.read_bytes())
    markup = html_output.read_text(encoding="utf-8")
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
    tags = Tags()
    tags.feed(markup)
    assert not {"script", "img", "iframe", "a", "link"} & set(tags.tags)
    assert "&lt;script" in markup and "output_omitted" in markup
    assert "default-src 'none'" in markup and "unverified" in markup
    call("report", source, "--output", json_output, "--format", "json")
    exported = json.loads(json_output.read_text(encoding="utf-8"))
    assert exported["record"] == record and exported["source_sha256"] == digest(source.read_bytes())
    failures = tmp_path / "failures.jsonl"
    receipt = call("failures", source, "--output", failures)
    rows = [json.loads(line) for line in failures.read_text(encoding="utf-8").splitlines()]
    assert [row["failure"] for row in rows] == record["failures"]
    assert all(row["source_sha256"] == receipt["source_sha256"] for row in rows)


def test_empty_failure_export_keeps_source_receipt(tmp_path):
    source = write_json(tmp_path / "empty.json", {"failures": []})
    output = tmp_path / "empty.jsonl"
    receipt = call("failures", source, "--output", output)
    assert output.read_bytes() == b"" and receipt["count"] == 0
    assert receipt["source_sha256"] == digest(source.read_bytes())
    assert receipt["source_bytes"] == len(source.read_bytes())


def test_report_cannot_overwrite_its_source(tmp_path):
    source = write_json(tmp_path / "supplied.json", {"unverified": True})
    original = source.read_bytes()
    assert call("report", source, "--output", source, expected=1)["error_type"] == "FileExistsError"
    assert source.read_bytes() == original


@pytest.mark.parametrize("content", [b"{", b"[]", b'{"bad": NaN}', b'{"bad": 1e999}',
    b'{"a":' * 100 + b"0" + b"}" * 100, b'\xff'])
def test_malformed_or_nested_json_has_structured_error(tmp_path, content):
    source, output = tmp_path / "bad.json", tmp_path / "report.html"
    source.write_bytes(content)
    result = call("report", source, "--output", output, expected=1)
    assert result["status"] == "error" and result["reason"]
    assert not output.exists()


@pytest.mark.parametrize("message", [b"not a message", b"MSH|^~\\&|A\nPID|1\n", b"MSH|^~\\&|A\rPID|1||bad\\UNKNOWN\\\r"])
def test_unsupported_raw_parse_keeps_provenance(tmp_path, message):
    source = tmp_path / "bad.hl7"
    source.write_bytes(message)
    result = call("parse", source, expected=2)
    assert result["raw_sha256"] == result["result"]["raw_sha256"] == digest(message)
    assert result["runtime_verified"] is False


def test_raw_size_limit_is_structured(tmp_path):
    source = tmp_path / "large.hl7"
    source.write_bytes(b"x" * (1024 * 1024 + 1))
    result = call("parse", source, expected=1)
    assert "exceeds" in result["reason"]


@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
def test_ledger_mutation_paths_cannot_alias_fixtures(mock_files, suffix):
    source, dictionary, fixtures, ledger, _ = mock_files
    alias = ledger.parent / (ledger.name + suffix)
    # A hardlink reproduces inode aliasing even where symlink creation is restricted.
    os.link(fixtures, alias)
    original = fixtures.read_bytes()
    result = call("mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures,
                  "--ledger", ledger, expected=1)
    assert "alias" in result["reason"] and fixtures.read_bytes() == original


def test_memory_accounting_refuses_before_creating_state(mock_files):
    source, dictionary, fixtures, _, _ = mock_files
    result = call("mock-map", source, "--dictionary", dictionary, "--fixtures", fixtures,
                  "--ledger", ":memory:", expected=1)
    assert "persistent ledger" in result["reason"]


def test_existing_lock_preserved_before_ruling(ruling_files):
    args, journal, _, _ = ruling_files
    lock = journal.with_suffix(journal.suffix + ".lock")
    lock.write_bytes(b"existing lock evidence")
    result = call(*args, "--simulate", expected=1)
    assert "new simulation journal" in result["reason"] and not journal.exists()
    assert lock.read_bytes() == b"existing lock evidence"


def test_stale_ruling_hash_refuses_without_journal(ruling_files):
    args, journal, request, _ = ruling_files
    value = json.loads(request.read_text(encoding="utf-8"))
    value["key"]["source_hash"] = "0" * 64
    write_json(request, value)
    result = call(*args, "--simulate", expected=1)
    assert "stale ruling key" in result["reason"] and not journal.exists()


def test_dangling_journal_symlink_is_preserved(ruling_files, tmp_path):
    args, journal, _, _ = ruling_files
    try:
        journal.symlink_to(tmp_path / "missing-target")
    except OSError as exc:
        pytest.skip(f"local symlink capability unavailable: {exc}")
    result = call(*args, "--simulate", expected=1)
    assert "new simulation journal" in result["reason"]
    assert journal.is_symlink() and not journal.exists()
