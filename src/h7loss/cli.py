"""Local, keyless construction CLI. Evaluation is deliberately external."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(no_args_is_help=True, help="Semantic Loss Lab: runtime-unverified construction tools.")
MAX_INPUT_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 4 * MAX_INPUT_BYTES
DEMO_RAW = (
    b"MSH|^~\\&|AUTHORED-DEV|LAB|DEMO|LAB|202610271200||ORU^R01|DEV-ONLY-001|P|2.8\r"
    b"PID|1||SYN-MRN-DEV-001^^^LOCAL-DEV^MR||TESTPATIENT^DEV\r"
    b"OBR|1|DEV-ORDER-001||LOCAL-TEST^Original developer test^LOCAL-DEV\r"
    b"OBX|1|ST|LOCAL-TEST^Original developer test^LOCAL-DEV||Illustrative value||||||F\r"
)


def _emit(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True))


def _refuse(command: str, reason: str) -> None:
    _emit({"command": command, "status": "refused", "reason": reason,
           "runtime_verified": False})
    raise typer.Exit(2)


def _read(path: Path, limit: int = MAX_INPUT_BYTES) -> bytes:
    # Bounded read, even if a file grows between checking and opening it.
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"input exceeds {limit} bytes")
    return raw


def _object(path: Path) -> dict:
    return _decode_object(_read(path, MAX_RECORD_BYTES))


def _decode_object(raw: bytes) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON numeric constant: {value}")

    value = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def _write(path: Path, raw: bytes) -> dict:
    # Exclusive creation preserves earlier evidence; no implicit directory scans.
    with path.open("xb") as stream:
        stream.write(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _failure(command: str, exc: Exception) -> None:
    _emit({"command": command, "status": "error", "error_type": type(exc).__name__,
           "reason": str(exc), "runtime_verified": False})
    raise typer.Exit(1)


@app.command()
def demo(mock: Annotated[bool, typer.Option(help="Required: authored fixtures only.")] = False) -> None:
    """Show an original developer source record; no simulated validator pass."""
    if not mock:
        _refuse("demo", "Only demo --mock is available; no live transport is authorized.")
    _emit({"namespace": "authored-developer-demo", "status": "illustrative_only",
           "case_id": "DEV-ONLY-001", "raw_sha256": hashlib.sha256(DEMO_RAW).hexdigest(),
           "raw_message": DEMO_RAW.decode("ascii"), "runtime_verified": False,
           "validation": {"status": "not_run", "tool": "Java validator"},
           "roundtrip": {"status": "not_run"}, "metrics": None,
           "cost": {"live_calls": 0, "spend_usd": "0"},
           "note": "Authored developer fixture; no oracle, held-out truth or measured result."})


@app.command()
def gen(output: Annotated[Path, typer.Option(help="New file for one authored developer message.")]) -> None:
    """Write one original illustrative message, never a study corpus."""
    try:
        artifact = _write(output, DEMO_RAW)
        _emit({"namespace": "authored-developer-demo", "status": "illustrative_only", "artifact": artifact})
    except (OSError, ValueError) as exc:
        _failure("gen", exc)


@app.command("parse")
def parse_command(source: Path) -> None:
    """Parse explicitly named raw bytes through the public lexical interface."""
    try:
        from h7loss.v2 import parse_message

        raw = _read(source)
        _emit({"raw_sha256": hashlib.sha256(raw).hexdigest(), "result": parse_message(raw),
               "runtime_verified": False})
    except (ImportError, OSError, ValueError, TypeError) as exc:
        _failure("parse", exc)


@app.command("map")
def map_command(source: Path, dictionary: Annotated[Path, typer.Option()]) -> None:
    """Apply B0 using only explicitly supplied source and dictionary."""
    try:
        from h7loss.arms.b0 import map_message

        raw = _read(source)
        _emit({"raw_sha256": hashlib.sha256(raw).hexdigest(),
               "result": map_message(raw, _object(dictionary)), "runtime_verified": False})
    except (ImportError, OSError, ValueError, TypeError) as exc:
        _failure("map", exc)


@app.command()
def propose(source: Path, dictionary: Annotated[Path, typer.Option()],
            proposal: Annotated[Path, typer.Option()]) -> None:
    """Execute an explicitly authored proposal; never generate via a live model."""
    try:
        from h7loss.proposal import execute_proposal, validate_proposal

        supplied = _object(proposal)
        validation = validate_proposal(supplied)
        # The executor must enforce its own schema too; this record is diagnostic.
        raw = _read(source)
        _emit({"raw_sha256": hashlib.sha256(raw).hexdigest(), "proposal_check": validation,
               "result": execute_proposal(raw, _object(dictionary), supplied),
               "runtime_verified": False})
    except (ImportError, OSError, ValueError, TypeError) as exc:
        _failure("propose", exc)


@app.command()
def report(source: Path, output: Annotated[Path, typer.Option()],
           format: Annotated[str, typer.Option(help="html or json")] = "html") -> None:
    """Render supplied records with provenance; all supplied claims unverified."""
    try:
        from h7loss.report import render_report

        raw = _read(source, MAX_RECORD_BYTES)
        record = _decode_object(raw)
        envelope = {"status": "construction_unverified", "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "record": record, "runtime_verified": False}
        if format == "html":
            content = render_report(envelope).encode("utf-8")
        elif format == "json":
            content = (json.dumps(envelope, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
        else:
            raise ValueError("format must be html or json")
        _emit({"status": "construction_unverified", "artifact": _write(output, content)})
    except (ImportError, OSError, ValueError, TypeError) as exc:
        _failure("report", exc)


@app.command()
def failures(source: Path, output: Annotated[Path, typer.Option()]) -> None:
    """Export all supplied failure objects, with no metric or truth inference."""
    try:
        raw = _read(source, MAX_RECORD_BYTES)
        record = _decode_object(raw)
        items = record.get("failures")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("failures must be an explicit list of JSON objects")
        digest = hashlib.sha256(raw).hexdigest()
        lines = [json.dumps({"status": "supplied_unverified", "source_sha256": digest,
                             "failure": item}, ensure_ascii=True, allow_nan=False) for item in items]
        content = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        _emit({"status": "supplied_unverified", "count": len(items),
               "source_sha256": digest, "source_bytes": len(raw),
               "artifact": _write(output, content)})
    except (OSError, ValueError, TypeError) as exc:
        _failure("failures", exc)


@app.command()
def admit() -> None:
    _refuse("admit", "NOT_ADMITTED: actual-use rights and Roy-appointed H/Q signatures pending.")


@app.command()
def validate() -> None:
    _refuse("validate", "not_run: admitted pinned Java execution unavailable during Dirty construction.")


@app.command()
def roundtrip() -> None:
    _refuse("roundtrip", "Independent renderer, controls and runtime validation pending.")


@app.command()
def rule() -> None:
    _refuse("rule", "Hash-bound actor/evidence journal CLI integration pending; no ruling recorded.")


@app.command()
def score() -> None:
    _refuse("score", "Separate evaluation distribution and independent expectations required.")


@app.command("eval")
def eval_command() -> None:
    _refuse("eval", "No campaign: admission, independent roles, seals and dispatch approvals pending.")


@app.command()
def live() -> None:
    _refuse("live", "Live dispatch is disabled; no keys, accounts, model calls or spend authorized.")
