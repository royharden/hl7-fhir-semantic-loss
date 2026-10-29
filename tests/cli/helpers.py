"""Test command helpers; no provider transport or external accounts."""

import hashlib
import json

from typer.testing import CliRunner

from h7loss.cli import app


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
    return path


def call(*args, expected=0):
    result = CliRunner().invoke(app, [str(arg) for arg in args])
    assert result.exit_code == expected, (result.output, repr(result.exception))
    return json.loads(result.stdout)
