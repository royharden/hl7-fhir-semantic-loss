"""Public construction contracts; no oracle or held-out truth."""

from typing import Literal, NotRequired, TypedDict


class SourceRef(TypedDict):
    raw_sha256: str
    segment_index: int
    group_id: str
    field: int
    repetition: int
    component: int
    subcomponent: int
    byte_start: int
    byte_end: int


class Disposition(TypedDict):
    source_ref: SourceRef
    disposition: Literal["mapped", "declared_drop", "abstain"]
    reason_code: str
    target_refs: list[str]
    evidence_refs: list[str]


class InputCase(TypedDict):
    case_id: str
    raw_sha256: str
    site_id: str
    dictionary_sha256: str
    message_path: str


class ArmResult(TypedDict):
    case_id: str
    arm_id: str
    outcome: Literal["mapped", "partial", "refused", "error"]
    bundle: dict | None
    dispositions: list[Disposition]
    error: str | None
    raw_sha256: NotRequired[str]
    dictionary_sha256: NotRequired[str]
    provenance: NotRequired[dict]


class ValidationReceipt(TypedDict):
    status: Literal["pass", "fail", "error", "not_run"]
    tool_sha256: str | None
    package_sha256: str | None
    config_sha256: str | None
    input_sha256: str
    warnings: list[str]


class RunSeal(TypedDict):
    input_sha256: str
    truth_sha256: str | None
    oracle_sha256: str | None
    tool_sha256: str | None
    prompt_sha256: str | None
    protocol_sha256: str
    author_identities: list[str]
    opened_at: str | None
    attempts: list[str]
