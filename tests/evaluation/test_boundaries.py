"""Original builder-only developer regressions, never independent gold/custody data."""
import copy
import json
import stat
import zipfile
from pathlib import Path

import pytest

from evaluation.archive import member_path, read_phase1_zip, validate_phase1_metadata
from evaluation.common import Refusal, digest, sha256
from evaluation.custody import freeze, open_once
from evaluation.denominators import summarize, validate_schedule
from evaluation.prereg import REQUIRED_HASHES, freeze_prereg, prereg_hash
from evaluation.producer_ports import denominator_records, normalize_producer
from evaluation.runner import create_campaign
from evaluation.stats import paired_site_bootstrap, ratio


def replay_port(raw, phase1, config):
    """Authored developer port, source pinned by campaign_fixture."""
    return {"outcome": "completed", "bundle": {"resourceType": "Bundle", "entry": []},
            "authored_fixture": True}


def invalid_output_port(raw, phase1, config):
    return {"outcome": "completed", "bundle_path": "outside.json"}


def developer_prereg():
    return {"schema_version": 1, "run_id": "developer-run", "frozen_at": "developer-test",
            "actor": "builder-unit-test", "heldout_started": False,
            "hashes": {key: sha256(key.encode()) for key in REQUIRED_HASHES},
            "statistics": {"resampling_unit": "site", "resamples": 10000, "seed": 7,
                           "quantile": "linear-(n-1)*p", "interval": .95},
            "design_disposition": {"descriptive_only": True}, "evidence_kind": "authored_fixture"}


def schedule_row(case_id="developer-case", purpose="scored", arm="B0"):
    return {"case_id": case_id, "site_id": "developer-site", "arm_id": arm,
            "config_id": "developer-config", "raw_sha256": sha256(case_id.encode()),
            "namespace": "authored_fixture", "purpose": purpose}


def phase1_metadata(raw_hash, dictionary_hash):
    return {"schema_version": 1, "cases": [{"case_id": "developer-case", "site_id": "developer-site",
            "raw_sha256": raw_hash, "dictionary_sha256": dictionary_hash,
            "message_path": "raw/developer.hl7", "dictionary_path": "dictionary/public.json",
            "usage": "scored", "namespace": "authored_fixture"}]}


def campaign_fixture(tmp_path, *, port=replay_port, repair=False):
    raw = b"original developer-only opaque runner bytes\r"
    raw_path = tmp_path / "developer.hl7"
    raw_path.write_bytes(raw)
    schedule = [schedule_row()]
    schedule[0]["raw_sha256"] = sha256(raw)
    phase1 = phase1_metadata(sha256(raw), sha256(b"developer dictionary"))
    configs = {"developer-config": {"evidence_class": "authored_fixture"}}
    source = Path(__file__).resolve()
    arm_files = {"B0": {"developer-port": str(source)}}
    artifacts = {"B0": {"developer-port": sha256(source.read_bytes())}}
    entrypoints = {"B0": port.__module__ + "." + port.__qualname__}
    prereg = developer_prereg()
    prereg["hashes"]["input_manifest"] = digest({"developer-case": sha256(raw)})
    prereg["hashes"]["arms"] = digest({"schedule": [("B0", "developer-config")],
        "artifacts": artifacts, "entrypoints": entrypoints, "configs_sha256": digest(configs)})
    attempts = [{"attempt_id": "initial", "case_id": "developer-case", "arm_id": "B0"}]
    if repair:
        attempts.append({"attempt_id": "repair", "case_id": "developer-case", "arm_id": "B0"})
    manifest = {"run_id": "developer-run", "prereg_sha256": prereg_hash(prereg),
        "schedule_sha256": digest(schedule), "configs_sha256": digest(configs),
        "phase1_sha256": digest(phase1), "protocol_sha256": prereg["hashes"]["protocol"],
        "input_manifest_sha256": prereg["hashes"]["input_manifest"], "arm_artifacts": artifacts,
        "arm_entrypoints": entrypoints, "attempts": attempts, "final_attempts": [attempts[-1]]}
    campaign = create_campaign(tmp_path / "campaign", manifest, prereg, schedule, configs,
                               {"developer-case": raw_path}, phase1, arm_files)
    return campaign, raw_path


def test_runner_refuses_live_without_calling_port(tmp_path):
    campaign, _ = campaign_fixture(tmp_path)
    with pytest.raises(Refusal, match="live dispatch refused"):
        campaign.execute_replay("initial", replay_port, authorized_replay=True, mode="live")
    assert list((campaign.root / "reservations").iterdir()) == []


def test_runner_requires_all_planned_repair_outputs_before_freeze(tmp_path):
    campaign, _ = campaign_fixture(tmp_path, repair=True)
    campaign.execute_replay("initial", replay_port, authorized_replay=True)
    with pytest.raises(Refusal, match="incomplete"):
        campaign.freeze("builder-test")
    assert not (campaign.root / "freeze.json").exists()


def test_runner_freeze_precedes_truth_access_and_score_callback(tmp_path):
    campaign, _ = campaign_fixture(tmp_path)
    calls = []
    with pytest.raises((FileNotFoundError, Refusal)):
        campaign.open_and_score_once(tmp_path / "not-created.bin", lambda *args: calls.append(args),
            actor="builder-test", expected_truth_sha256=sha256(b"developer assertions"),
            expected_freeze_sha256=sha256(b"unmade freeze"))
    assert calls == []
    assert not (campaign.root / "opened.json").exists()


def test_runner_freeze_open_once_and_no_post_open_replay(tmp_path):
    campaign, _ = campaign_fixture(tmp_path)
    campaign.execute_replay("initial", replay_port, authorized_replay=True)
    sealed = campaign.freeze("builder-test")
    developer_assertions = tmp_path / "developer-assertions.json"
    developer_assertions.write_bytes(b"builder unit assertions only")
    calls = []
    def scorer(raw, records):
        calls.append((raw, records))
        return {"builder_case_count": len(records), "complete_semantic_score": False}
    kwargs = {"actor": "builder-test", "expected_truth_sha256": sha256(developer_assertions.read_bytes()),
              "expected_freeze_sha256": sealed["freeze_sha256"]}
    result = campaign.open_and_score_once(developer_assertions, scorer, **kwargs)
    assert len(calls) == 1
    assert result["independent_semantic_acceptance"] is False
    with pytest.raises(FileExistsError):
        campaign.open_and_score_once(developer_assertions, scorer, **kwargs)
    assert len(calls) == 1
    with pytest.raises(Refusal, match="frozen/opened"):
        campaign.execute_replay("initial", replay_port, authorized_replay=True)


def test_runner_changed_output_after_freeze_refuses_before_open(tmp_path):
    campaign, _ = campaign_fixture(tmp_path)
    campaign.execute_replay("initial", replay_port, authorized_replay=True)
    sealed = campaign.freeze("builder-test")
    path = campaign.root / "attempts" / "initial.json"
    record = json.loads(path.read_text())
    record["result"]["bundle"]["extra"] = "tampered developer output"
    record["result_sha256"] = digest(record["result"])
    path.write_text(json.dumps(record))
    with pytest.raises(Refusal, match="outputs changed"):
        campaign.open_and_score_once(tmp_path / "unopened.bin", lambda *args: None,
            actor="builder-test", expected_truth_sha256=sha256(b"developer assertions"),
            expected_freeze_sha256=sealed["freeze_sha256"])
    assert not (campaign.root / "opened.json").exists()


def test_runner_failed_score_consumes_open_marker(tmp_path):
    campaign, _ = campaign_fixture(tmp_path)
    campaign.execute_replay("initial", replay_port, authorized_replay=True)
    sealed = campaign.freeze("builder-test")
    assertions = tmp_path / "developer-assertions.bin"
    assertions.write_bytes(b"developer-only")
    def fail_score(*args):
        raise RuntimeError("authored developer callback failure")
    kwargs = {"actor": "builder-test", "expected_truth_sha256": sha256(assertions.read_bytes()),
              "expected_freeze_sha256": sealed["freeze_sha256"]}
    with pytest.raises(RuntimeError):
        campaign.open_and_score_once(assertions, fail_score, **kwargs)
    assert (campaign.root / "opened.json").is_file()
    with pytest.raises(FileExistsError):
        campaign.open_and_score_once(assertions, fail_score, **kwargs)


def test_runner_input_drift_cannot_dispatch_or_reserve(tmp_path):
    campaign, raw_path = campaign_fixture(tmp_path)
    raw_path.write_bytes(b"changed developer raw")
    with pytest.raises(Refusal, match="input bytes drifted"):
        campaign.execute_replay("initial", replay_port, authorized_replay=True)
    assert list((campaign.root / "reservations").iterdir()) == []


def test_runner_external_output_reference_becomes_retained_error(tmp_path):
    campaign, _ = campaign_fixture(tmp_path, port=invalid_output_port)
    record = campaign.execute_replay("initial", invalid_output_port, authorized_replay=True)
    assert record["result"] == {"outcome": "error", "error_type": "Refusal"}
    assert (campaign.root / "attempts" / "initial.json").is_file()


def public_dictionary():
    return {"dictionary_id": "developer-public", "provenance": {"kind": "original",
        "admission": "not_admitted", "rights_review": "pending", "independent_semantic_review": "pending",
        "purpose": "developer-only"}, "codes": {}, "identifier_systems": {}, "observation_statuses": {},
        "report_statuses": {}, "coding_authorities": {}, "units": {}, "value_codes": {}, "z_segments": {}}


def archive_fixture(tmp_path, *, extra_member=None, metadata_change=None, special=False):
    raw = b"original developer-only opaque archive bytes\r"
    dictionary = json.dumps(public_dictionary()).encode()
    metadata = phase1_metadata(sha256(raw), sha256(dictionary))
    if metadata_change:
        metadata_change(metadata)
    members = {"raw/developer.hl7": raw, "dictionary/public.json": dictionary,
               "metadata/cases.json": json.dumps(metadata).encode()}
    manifest = [{"path": name, "kind": name.split("/")[0], "sha256": sha256(data)}
                for name, data in members.items()]
    path = tmp_path / "developer-archive.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            if special and name == "raw/developer.hl7":
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, data)
            else:
                archive.writestr(name, data)
        if extra_member:
            archive.writestr(extra_member, b"original developer extra")
    return path, manifest, members


@pytest.mark.parametrize("name", ["../raw/x.hl7", "/raw/x.hl7", "C:/raw/x.hl7", "raw/../x.hl7",
    "raw/x:stream.hl7", "raw/CON.hl7", "raw/.hidden.hl7", "raw/truth.hl7", "raw\\x.hl7"])
def test_archive_unsafe_paths_are_refused_without_normalization(name):
    with pytest.raises(Refusal):
        member_path(name, "raw")


def test_archive_valid_roundtrip_reads_bytes_without_extracting(tmp_path):
    path, manifest, original = archive_fixture(tmp_path)
    members = read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))
    assert members == original
    assert not (tmp_path / "raw").exists()


def test_archive_unexpected_member_refused(tmp_path):
    path, manifest, _ = archive_fixture(tmp_path, extra_member="raw/extra.hl7")
    with pytest.raises(Refusal, match="unexpected or missing"):
        read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))


def test_archive_special_member_refused(tmp_path):
    path, manifest, _ = archive_fixture(tmp_path, special=True)
    with pytest.raises(Refusal, match="symlink"):
        read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))


def test_archive_member_hash_drift_refused(tmp_path):
    path, manifest, _ = archive_fixture(tmp_path)
    manifest[0]["sha256"] = sha256(b"different developer bytes")
    with pytest.raises(Refusal, match="member size/hash mismatch"):
        read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))


def test_archive_reconstructive_metadata_refused():
    metadata = phase1_metadata(sha256(b"raw"), sha256(b"dictionary"))
    metadata["cases"][0]["hidden_seed"] = "developer forbidden field"
    with pytest.raises(Refusal):
        validate_phase1_metadata(metadata)


def test_archive_metadata_cannot_point_to_different_raw(tmp_path):
    path, manifest, _ = archive_fixture(tmp_path,
        metadata_change=lambda data: data["cases"][0].update(raw_sha256=sha256(b"other developer raw")))
    with pytest.raises(Refusal, match="metadata member/hash binding"):
        read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))


def test_archive_case_alias_and_size_cap_refused(tmp_path):
    path, manifest, _ = archive_fixture(tmp_path)
    manifest.append({**manifest[0], "path": "raw/DEVELOPER.hl7"})
    with pytest.raises(Refusal, match="case-alias"):
        read_phase1_zip(path, manifest, archive_sha256=sha256(path.read_bytes()))
    with pytest.raises(Refusal, match="member size cap"):
        read_phase1_zip(path, manifest[:-1], archive_sha256=sha256(path.read_bytes()), max_member_bytes=1)


def normalizer_fixture(producer="B0"):
    config = {"model": "developer-authored-fixture"}
    sources = {"developer-adapter": b"original builder developer artifact"}
    binding = {"producer": producer, "config_id": "developer-config", "site_id": "developer-site",
        "dictionary_sha256": sha256(b"dictionary"), "config_sha256": digest(config),
        "source_hashes": {name: sha256(value) for name, value in sources.items()},
        "case_id": "scheduled-developer", "raw_sha256": sha256(b"developer raw")}
    kwargs = {"producer": producer, "binding": binding, "expected_binding_sha256": digest(binding),
              "source_files": sources, "config": config}
    bundle = {"resourceType": "Bundle", "entry": []}
    return binding, kwargs, bundle


def b2_attempt(binding, *, producer="B2", outcome="unknown_usage"):
    provenance = {"arm_id": "B2" if producer == "B2" else "A", "config_id": binding["config_id"],
        "dictionary_sha256": binding["dictionary_sha256"], "model": "developer-authored-fixture",
        "attempt_number": 0, "authored_fixture": True,
        "request_identity_sha256": sha256(b"request"), "messages_sha256": sha256(b"messages"),
        "initial_messages_sha256": sha256(b"initial")}
    if producer == "B2":
        provenance.update(case_id=binding["case_id"], raw_sha256=binding["raw_sha256"])
    else:
        provenance["site_id"] = binding["site_id"]
    return {"attempt_id": sha256(b"developer attempt"), "attempt_number": 0,
        "max_liability_micro_usd": 100, "provenance": provenance, "dispatch_state": "dispatched",
        "previously_dispatched": False, "reservation_state": "reserved", "outcome": outcome,
        "usage_micro_usd": None, "usage_state": "unknown", "authored_fixture": True,
        "raw_output_sha256": sha256(b"authored output"), "raw_output_chars": 15, "output_omitted": False}


def test_b0_native_case_alias_is_retained_and_never_becomes_semantic_pass():
    binding, kwargs, bundle = normalizer_fixture()
    payload = {"case_id": binding["raw_sha256"][:16], "arm_id": "B0", "outcome": "partial",
        "raw_sha256": binding["raw_sha256"], "dictionary_sha256": binding["dictionary_sha256"],
        "bundle": bundle, "dispositions": [], "error": None}
    result = normalize_producer(payload, **kwargs)
    assert result["case_id"] == "scheduled-developer"
    assert result["producer_case_id"] == payload["case_id"]
    assert result["producer_result"] == payload
    assert result["outcome"] == "completed"
    assert result["unreported_critical_error"] is None
    assert result["java_status"] == "not_run"
    assert denominator_records(result, final_attempt_id="campaign-attempt")["assessment"]["generic_rt_status"] == "not_run"


def test_normalizer_wrong_native_id_retains_original_as_unsupported():
    binding, kwargs, bundle = normalizer_fixture()
    payload = {"case_id": "invented-alias", "arm_id": "B0", "outcome": "mapped",
        "dictionary_sha256": binding["dictionary_sha256"], "bundle": bundle, "dispositions": [], "error": None}
    result = normalize_producer(payload, **kwargs)
    assert result["outcome"] == "unsupported"
    assert result["producer_result"] == payload
    assert result["binding_verified"] is False
    with pytest.raises(Refusal):
        denominator_records(result, final_attempt_id="campaign-attempt")


def test_b2_unknown_usage_and_refusal_history_remain_unknown():
    binding, kwargs, _ = normalizer_fixture("B2")
    attempt = b2_attempt(binding)
    payload = {"case_id": binding["case_id"], "arm_id": "B2", "config_id": binding["config_id"],
        "raw_sha256": binding["raw_sha256"], "outcome": "error", "bundle": None, "dispositions": [],
        "error": "developer unknown usage", "attempts": [attempt], "evidence_class": "authored_mock", "runtime_verified": False}
    result = normalize_producer(payload, **kwargs)
    assert result["outcome"] == "error"
    assert result["attempts"] == [attempt]
    assert result["usage"][0]["usage_micro_usd"] is None
    assert result["usage"][0]["usage_state"] == "unknown"
    assert result["evidence_class"] == "authored_mock"


def test_site_setup_is_never_a_scored_message():
    binding, kwargs, _ = normalizer_fixture("SITE")
    payload = {"outcome": "produced", "proposal": {"site_id": binding["site_id"],
        "dictionary_sha256": binding["dictionary_sha256"]}, "attempts": [b2_attempt(binding, producer="SITE")],
        "evidence_class": "authored_mock", "runtime_verified": False, "error": None}
    result = normalize_producer(payload, **kwargs)
    assert result["record_kind"] == "site_setup"
    assert result["outcome"] == "setup_produced"
    assert result["eligible_for_scored_denominator"] is False
    with pytest.raises(Refusal, match="site setup"):
        denominator_records(result, final_attempt_id="not-a-message")


def test_normalizer_source_drift_refuses_without_erasing_attempts():
    binding, kwargs, _ = normalizer_fixture("B2")
    payload = {"attempts": [b2_attempt(binding)], "outcome": "refused", "error": "developer refusal"}
    kwargs["source_files"] = {"developer-adapter": b"changed bytes"}
    result = normalize_producer(payload, **kwargs)
    assert result["outcome"] == "unsupported"
    assert result["attempts"] == payload["attempts"]
    assert result["producer_result"] == payload


def test_denominator_missing_and_failed_cases_never_become_clean():
    first, missing, onboarding = schedule_row("first"), schedule_row("missing"), schedule_row("onboard", "onboarding")
    attempt = {**{k: first[k] for k in ("case_id", "arm_id", "config_id", "raw_sha256")},
               "attempt_id": "failed", "outcome": "timeout", "output_sha256": None}
    assessment = {**{k: attempt[k] for k in ("case_id", "arm_id", "config_id", "raw_sha256", "output_sha256")},
        "final_attempt_id": "failed", "java_status": "not_run", "generic_rt_status": "not_run", "paired_rt_status": "not_run",
        "unreported_critical_error": None, "any_critical_loss": None}
    result = summarize([first, missing, onboarding], [attempt], [assessment])
    group = result["groups"][0]
    assert group["scheduled"] == 2
    assert group["assessment_missing"] == 1
    assert group["outcomes"]["timeout"] == 1
    assert group["wrong_all_scheduled"]["value"] is None
    assert group["wrong_all_scheduled"]["unmeasured"] == 2
    assert result["onboarding_rows"] == 1


def test_denominator_requires_every_arm_for_every_case():
    with pytest.raises(Refusal, match="all scheduled arms"):
        validate_schedule([schedule_row("one", arm="B0"), schedule_row("one", arm="B2"), schedule_row("two", arm="B0")])


def test_denominator_failed_attempt_cannot_claim_java_pass():
    row = schedule_row()
    attempt = {**{k: row[k] for k in ("case_id", "arm_id", "config_id", "raw_sha256")}, "attempt_id": "failed", "outcome": "error"}
    assessment = {**{k: row[k] for k in ("case_id", "arm_id", "config_id", "raw_sha256")},
        "final_attempt_id": "failed", "java_status": "pass", "generic_rt_status": "not_run", "paired_rt_status": "not_run"}
    with pytest.raises(Refusal, match="cannot pass"):
        summarize([row], [attempt], [assessment])


def test_paired_bootstrap_resamples_sites_together_not_messages():
    sites = {"site-a": {"A": {"numerator": 1, "denominator": 2}, "B": {"numerator": 1, "denominator": 2}},
             "site-b": {"A": {"numerator": 8, "denominator": 10}, "B": {"numerator": 8, "denominator": 10}}}
    result = paired_site_bootstrap(sites, seed=12, resamples=25, contrast=("A", "B"))
    assert result["resampling_unit"] == "site"
    assert result["contrast"]["intervals"]["pooled"]["interval_95"] == [0.0, 0.0]
    assert result["point"]["A"]["macro"] == .65
    assert result["point"]["A"]["pooled"] == .75


def test_bootstrap_empty_denominators_remain_undefined():
    assert ratio(0, 0) is None
    result = paired_site_bootstrap({"empty": {"A": {"numerator": 0, "denominator": 0}}}, seed=1, resamples=5)
    assert result["point"]["A"]["macro"] is None
    assert result["intervals"]["A"]["pooled"] == {"interval_95": None, "defined_resamples": 0, "undefined_resamples": 5}


def test_custody_composes_freeze_envelope_and_consumes_open_once(tmp_path):
    source = tmp_path / "developer-output.json"
    source.write_bytes(b"developer output")
    files = {"developer-output": source}
    frozen = freeze(tmp_path / "frozen.json", files, run_id="developer", actor="builder", protocol_sha256=sha256(b"protocol"), attempt_ids=["one"])
    kwargs = {"actor": "builder", "truth_sha256": sha256(b"developer assertions"), "expected_freeze_sha256": frozen["freeze_sha256"]}
    first = open_once(tmp_path / "opened.json", frozen["record"], files, **kwargs)
    assert first["state"] == "opened_once"
    with pytest.raises(FileExistsError):
        open_once(tmp_path / "opened.json", frozen["record"], files, **kwargs)


def test_preregistration_exclusive_freeze_rejects_started_or_replacement(tmp_path):
    prereg = developer_prereg()
    prereg["heldout_started"] = True
    with pytest.raises(ValueError, match="heldout_already_started"):
        freeze_prereg(prereg, tmp_path / "bad.json")
    prereg["heldout_started"] = False
    receipt = freeze_prereg(prereg, tmp_path / "freeze.json")
    assert receipt["dispatch_authorized"] is False
    with pytest.raises(FileExistsError):
        freeze_prereg(prereg, tmp_path / "freeze.json")
