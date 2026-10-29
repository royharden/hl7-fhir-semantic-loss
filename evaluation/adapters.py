"""No subprocesses: ingest separately authorized execution receipts only."""
from .common import Refusal, require_hash, sha256

TOOLS = {"java", "b1", "generic_roundtrip", "paired_roundtrip", "structural"}

def validation_receipt(tool, input_bytes, execution=None):
    if tool not in TOOLS:
        raise Refusal("unsupported tool")
    base = {"tool": tool, "input_sha256": sha256(input_bytes), "status": "not_run",
            "warnings": [], "runtime_verified": False}
    if execution is None:
        return {**base, "reason": "no admitted execution evidence supplied"}
    # This only binds serialized external evidence; it does not attest execution.
    for name in ("tool_sha256", "config_sha256", "input_sha256", "stdout_sha256", "stderr_sha256"):
        require_hash(execution.get(name))
    if execution["input_sha256"] != base["input_sha256"] or execution.get("tool") != tool:
        raise Refusal("execution target mismatch")
    if execution.get("status") not in {"pass", "fail", "error", "not_run", "unsupported"}:
        raise Refusal("invalid execution status")
    if not execution.get("command") or not execution.get("actor") or not execution.get("package_pin"):
        raise Refusal("execution provenance incomplete")
    return {**base, "external_execution": dict(execution), "reason": "external evidence requires independent admission/verification"}
