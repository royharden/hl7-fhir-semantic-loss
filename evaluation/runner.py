"""Two-phase local campaign source. Live dispatch always refuses.

Only caller-provided replay ports execute. Nothing discovers arms, truth, files,
credentials or environment variables. Builder-authored receipts are unverified.
"""
import inspect
import json
import re
from pathlib import Path
from .common import Refusal, digest, require_hash, sha256
from .custody import snapshot, write_once
from .denominators import validate_schedule, OUTCOMES
from .prereg import prereg_hash, validate_prereg


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise Refusal("unsafe identifier")
    return value


def _file(path):
    p = Path(path).absolute()
    if any(part.is_symlink() for part in (p, *p.parents)) or not p.is_file():
        raise Refusal("ordinary explicit file without symlink ancestors required")
    return p


def _read(path):
    return json.loads(_file(path).read_text(encoding="utf-8"))


def create_campaign(root, manifest, prereg, schedule, configs, inputs, phase1, arm_files):
    """Construct an exclusive campaign directory, never overwriting old bytes.

    manifest pins prereg/schedule/input manifest/configs/phase1/protocol plus every
    planned attempt and an explicit final attempt for every case/arm. Optional
    repairs must be listed up front and recorded as skipped if unused.
    inputs maps case IDs to explicit raw file paths. phase1 is released public
    metadata/dictionary only, checked by the archive contract.
    """
    from .archive import validate_phase1_metadata
    validate_phase1_metadata(phase1)
    problems = validate_prereg(prereg)
    if problems:
        raise Refusal("preregistration invalid: " + ", ".join(problems))
    validate_schedule(schedule)
    _id(manifest.get("run_id"))
    if prereg["run_id"] != manifest["run_id"]:
        raise Refusal("run identity mismatch")
    bindings = {"prereg_sha256": prereg_hash(prereg), "schedule_sha256": digest(schedule),
                "configs_sha256": digest(configs), "phase1_sha256": digest(phase1)}
    for key, value in bindings.items():
        if manifest.get(key) != value:
            raise Refusal("manifest binding mismatch: " + key)
    arm_configs = sorted({(s["arm_id"], s["config_id"]) for s in schedule})
    arms = {s["arm_id"] for s in schedule}
    if not isinstance(arm_files, dict) or set(arm_files) != arms:
        raise Refusal("explicit source/artifact closure for every arm required")
    artifact_paths = {arm: {name: str(_file(path)) for name, path in arm_files[arm].items()} for arm in sorted(arms)}
    artifacts = {arm: snapshot(paths) for arm, paths in artifact_paths.items()}
    if artifacts != manifest.get("arm_artifacts"):
        raise Refusal("arm artifact hash mismatch")
    entrypoints = manifest.get("arm_entrypoints")
    if not isinstance(entrypoints, dict) or set(entrypoints) != arms or any(not isinstance(v, str) or not v for v in entrypoints.values()):
        raise Refusal("explicit arm module/qualified entrypoint names required")
    arm_pin = {"schedule": arm_configs, "artifacts": artifacts, "entrypoints": entrypoints, "configs_sha256": digest(configs)}
    if prereg["hashes"]["arms"] != digest(arm_pin):
        raise Refusal("preregistered arm/source/config mismatch")
    if prereg["hashes"]["protocol"] != manifest.get("protocol_sha256"):
        raise Refusal("protocol pin mismatch")
    if prereg["hashes"]["input_manifest"] != manifest.get("input_manifest_sha256"):
        raise Refusal("input manifest preregistration mismatch")
    cases = {s["case_id"] for s in schedule}
    released = {c["case_id"]: c for c in phase1["cases"]}
    if set(released) != cases:
        raise Refusal("released metadata must exactly cover schedule")
    for scheduled in schedule:
        public = released[scheduled["case_id"]]
        if any(public[k] != scheduled[k] for k in ("raw_sha256", "site_id", "namespace")) or public["usage"] != scheduled["purpose"]:
            raise Refusal("released metadata/schedule identity mismatch")
    if set(inputs) != cases:
        raise Refusal("input inventory must exactly cover scheduled cases")
    paths = {case: str(_file(inputs[case])) for case in sorted(cases)}
    hashes = snapshot(paths)
    if digest(hashes) != manifest.get("input_manifest_sha256"):
        raise Refusal("input manifest mismatch")
    for row in schedule:
        if hashes[row["case_id"]] != row["raw_sha256"]:
            raise Refusal("scheduled raw hash mismatch")
        if row["config_id"] not in configs:
            raise Refusal("scheduled config missing")
    keys = {(s["case_id"], s["arm_id"]) for s in schedule}
    attempts = manifest.get("attempts")
    finals = manifest.get("final_attempts")
    if not isinstance(attempts, list) or not isinstance(finals, list):
        raise Refusal("explicit planned/final attempt identities required")
    ids, covered = {}, set()
    for a in attempts:
        identity = _id(a.get("attempt_id"))
        key = (a.get("case_id"), a.get("arm_id"))
        if identity in ids or key not in keys:
            raise Refusal("duplicate attempt or unscheduled case/arm")
        ids[identity] = key
        covered.add(key)
    if covered != keys:
        raise Refusal("planned attempts incomplete")
    final_keys = set()
    for a in finals:
        key = (a.get("case_id"), a.get("arm_id"))
        if key in final_keys or key not in keys or ids.get(a.get("attempt_id")) != key:
            raise Refusal("invalid final attempt binding")
        final_keys.add(key)
    if final_keys != keys:
        raise Refusal("final attempt inventory incomplete")
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise Refusal("campaign root may not traverse symlinks")
    state = {"manifest": manifest, "prereg": prereg, "schedule": schedule,
             "configs": configs, "inputs": paths, "input_hashes": hashes, "phase1": phase1,
             "arm_files": artifact_paths, "arm_artifacts": artifacts}
    # Serialize before creating any state; arbitrary objects and NaN fail closed.
    expected = digest(state)
    root.mkdir()  # Already-existing or partial campaigns refuse; no auto cleanup.
    (root / "attempts").mkdir()
    (root / "reservations").mkdir()
    write_once(root / "campaign.json", state)
    return Campaign(root, expected)


class Campaign:
    def __init__(self, root, expected_campaign_sha256):
        self.root = Path(root).absolute()
        self.expected = require_hash(expected_campaign_sha256)

    def verify(self):
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise Refusal("campaign root symlink")
        state = _read(self.root / "campaign.json")
        if digest(state) != self.expected:
            raise Refusal("campaign/prereg/run/config/schedule drift")
        for arm, files in state["arm_files"].items():
            if snapshot(files) != state["arm_artifacts"][arm]:
                raise Refusal("arm source/artifact drift")
        if snapshot(state["inputs"]) != state["input_hashes"]:
            raise Refusal("input bytes drifted")
        return state

    def execute_replay(self, attempt_id, port, *, authorized_replay=False, mode="offline_replay"):
        """Source for later authorized execution only. No dispatch occurs in Dirty Mode.

        A caller must separately establish process/network isolation and rights.
        The boolean is an explicit invocation gate, not identity attestation.
        Exceptions are recorded as error attempts; raw exception text is excluded.
        """
        if mode != "offline_replay" or authorized_replay is not True:
            raise Refusal("live dispatch refused; separate offline replay authorization required")
        state = self.verify()
        if (self.root / "freeze.json").exists() or (self.root / "opened.json").exists():
            raise Refusal("campaign already frozen/opened")
        attempt_id = _id(attempt_id)
        attempt = next((a for a in state["manifest"]["attempts"] if a["attempt_id"] == attempt_id), None)
        if attempt is None:
            raise Refusal("attempt not preregistered")
        scheduled = next(s for s in state["schedule"] if (s["case_id"], s["arm_id"]) == (attempt["case_id"], attempt["arm_id"]))
        if not inspect.isfunction(port) or port.__closure__:
            raise Refusal("only explicit source-backed functions without closures supported")
        entrypoint = port.__module__ + "." + port.__qualname__
        if entrypoint != state["manifest"]["arm_entrypoints"][attempt["arm_id"]]:
            raise Refusal("arm entrypoint mismatch")
        source = inspect.getsourcefile(port)
        if source is None:
            raise Refusal("arm source unavailable")
        source_path = str(_file(source))
        if source_path not in state["arm_files"][attempt["arm_id"]].values():
            raise Refusal("callback source not in pinned arm closure")
        # Durable reservation precedes callback: crashes cannot silently retry.
        reservation = {"attempt_id": attempt_id, "campaign_sha256": self.expected}
        write_once(self.root / "reservations" / (attempt_id + ".json"), reservation)
        raw = _file(state["inputs"][attempt["case_id"]]).read_bytes()
        if sha256(raw) != scheduled["raw_sha256"]:
            raise Refusal("input changed before dispatch")
        try:
            # JSON copies stop a callback mutating pinned state passed by reference.
            result = port(raw, json.loads(json.dumps(state["phase1"])), json.loads(json.dumps(state["configs"][scheduled["config_id"]])))
            if not isinstance(result, dict) or result.get("outcome") not in OUTCOMES:
                raise Refusal("arm port must return explicit supported outcome")
            if "bundle_path" in result or "output_path" in result:
                raise Refusal("external output references cannot substitute for frozen bytes")
            if result["outcome"] == "completed" and (not isinstance(result.get("bundle"), dict) or result["bundle"].get("resourceType") != "Bundle"):
                raise Refusal("completed output must embed its FHIR Bundle bytes as JSON")
            digest(result)
        except Exception as error:
            result = {"outcome": "error", "error_type": type(error).__name__}
        record = {**attempt, "config_id": scheduled["config_id"], "raw_sha256": scheduled["raw_sha256"],
                  "campaign_sha256": self.expected, "result": result,
                  "result_sha256": digest(result), "runtime_verified": False}
        self.verify()
        write_once(self.root / "attempts" / (attempt_id + ".json"), record)
        return record

    def _attempts(self, state):
        expected = {a["attempt_id"] + ".json" for a in state["manifest"]["attempts"]}
        for directory in ("attempts", "reservations"):
            folder = self.root / directory
            if folder.is_symlink() or {p.name for p in folder.iterdir()} != expected:
                raise Refusal("incomplete/unexpected attempt or reservation inventory")
        records = []
        for planned in state["manifest"]["attempts"]:
            name = planned["attempt_id"] + ".json"
            reservation = _read(self.root / "reservations" / name)
            if reservation != {"attempt_id": planned["attempt_id"], "campaign_sha256": self.expected}:
                raise Refusal("reservation drift")
            record = _read(self.root / "attempts" / name)
            if record.get("campaign_sha256") != self.expected or any(record.get(k) != v for k, v in planned.items()):
                raise Refusal("attempt identity drift")
            scheduled = next(s for s in state["schedule"] if (s["case_id"], s["arm_id"]) == (planned["case_id"], planned["arm_id"]))
            if any(record.get(k) != scheduled[k] for k in ("raw_sha256", "config_id")):
                raise Refusal("attempt raw/config drift")
            if not isinstance(record.get("result"), dict) or record["result"].get("outcome") not in OUTCOMES:
                raise Refusal("attempt outcome malformed")
            if record.get("result_sha256") != digest(record.get("result")):
                raise Refusal("attempt result drift")
            records.append(record)
        return records

    def freeze(self, actor):
        state = self.verify()
        if not isinstance(actor, str) or not actor:
            raise Refusal("actor required")
        if (self.root / "opened.json").exists():
            raise Refusal("truth already opened")
        records = self._attempts(state)
        record = {"campaign_sha256": self.expected, "actor": actor,
                  "attempts_sha256": digest(records), "state": "outputs_frozen"}
        write_once(self.root / "freeze.json", record)
        return {"record": record, "freeze_sha256": digest(record)}

    def open_and_score_once(self, truth_path, scorer, *, actor, expected_truth_sha256, expected_freeze_sha256):
        """Freeze verifies before reading truth or invoking the external scorer.

        This is B orchestration, never O/Q admission. A failed score consumes
        the open marker; no same-set retry/tuning. No semantic success default.
        """
        state = self.verify()
        frozen = _read(self.root / "freeze.json")
        if digest(frozen) != require_hash(expected_freeze_sha256) or frozen.get("campaign_sha256") != self.expected:
            raise Refusal("freeze identity drift")
        records = self._attempts(state)
        if digest(records) != frozen.get("attempts_sha256"):
            raise Refusal("outputs changed after freeze")
        if not isinstance(actor, str) or not actor:
            raise Refusal("actor required")
        require_hash(expected_truth_sha256)
        # Marker is exclusive and precedes any truth byte access, even on failure.
        write_once(self.root / "opened.json", {"campaign_sha256": self.expected,
            "freeze_sha256": expected_freeze_sha256, "truth_sha256": expected_truth_sha256, "actor": actor})
        raw = _file(truth_path).read_bytes()
        if sha256(raw) != expected_truth_sha256:
            raise Refusal("truth bytes do not match external seal")
        result = scorer(raw, records)
        scored = {"result": result, "campaign_sha256": self.expected,
                  "independent_semantic_acceptance": False, "runtime_verified": False}
        digest(scored)
        write_once(self.root / "score.json", scored)
        return scored
