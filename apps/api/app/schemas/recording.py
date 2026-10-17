"""Recorded experiment contract: `autoresilience-recording/1` (docs/recordings.md).

A recording is a sanitized, self-verifying copy of one COMPLETED experiment. Every
model forbids unknown fields, so anything not listed here can never be published.
Parsing is strict JSON (`parse_recording`); building one from the database is
`app/tools/export_recording.py`. A breaking change means a new schema version;
older files stay valid against their own version (same rule as score versions).
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, get_args

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    ValidationInfo,
    model_validator,
)

SCHEMA_ID = "autoresilience-recording/1"
# Safety-rejected experiments: validation evidence only, recorded separately.
VALIDATION_SCHEMA_ID = "autoresilience-validation/1"
SUPPORTED_SCHEMAS = (SCHEMA_ID, VALIDATION_SCHEMA_ID)
EXPORTER_VERSION = "1.0.0"
CANONICALIZATION = "json-sorted-compact/1"

_SENSITIVE = {
    "uuid": re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
    ),
    "ip address": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    "url": re.compile(r"[a-z][a-z0-9+.-]*://", re.IGNORECASE),
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "cluster hostname": re.compile(
        r"\.svc\b|\.cluster\.local\b|\.internal\b", re.IGNORECASE
    ),
    "secret material": re.compile(
        r"BEGIN [A-Z ]*PRIVATE KEY|\bbearer\s|\btoken\s*[:=]|\bpassword\s*[:=]",
        re.IGNORECASE,
    ),
}


def sensitive_findings(text: str) -> list[str]:
    return [name for name, pattern in _SENSITIVE.items() if pattern.search(text)]


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
Token = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
DnsLabel = Annotated[
    str, StringConstraints(max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
]
PodAlias = Annotated[str, StringConstraints(pattern=r"^pod-[0-9]{1,3}$")]
# Engine-generated sentences (recovery rule, score explanation); never user input.
EngineText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Scalar = bool | int | float | Token | None
State = Literal[
    "CREATED",
    "VALIDATING",
    "BASELINING",
    "INJECTING",
    "OBSERVING",
    "RECOVERING",
    "COMPLETED",
]
LIFECYCLE_ORDER: tuple[str, ...] = get_args(State)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# --- experiment evidence -----------------------------------------------------------


class Target(_Model):
    namespace: DnsLabel
    kind: Literal["Deployment", "StatefulSet"]
    name: DnsLabel
    # True when namespace/name are aliases (anything outside the shipped sample apps).
    pseudonymised: bool


class Fault(_Model):
    type: Literal["pod-delete"]
    pod_delete_mode: Literal["GRACEFUL", "FORCE"]
    duration_seconds: PositiveInt
    affected_replicas: PositiveInt


class PolicySnapshot(_Model):
    name: Token
    max_duration_seconds: PositiveInt
    max_affected_replicas: PositiveInt
    min_healthy_replicas: NonNegativeInt
    forbidden_namespaces: list[DnsLabel]
    allowed_namespaces: list[DnsLabel] | None


class Check(_Model):
    phase: Literal["static", "cluster"]
    name: Token
    status: Literal["PASSED"]


class Validation(_Model):
    passed: Literal[True]
    policy: PolicySnapshot
    checks: list[Check] = Field(min_length=1)


class MetricGroup(_Model):
    status: Literal["OK", "UNAVAILABLE", "ERROR"]
    values: dict[Token, int | float | None]


class Baseline(_Model):
    status: Literal["CAPTURED"]
    captured_at: UtcDatetime
    window_seconds: PositiveInt
    availability: MetricGroup
    restarts: MetricGroup
    requests: MetricGroup
    client: MetricGroup | None


class Injection(_Model):
    provider: Token
    experiment: Literal["pod-delete"]
    safety_policy: Token
    created_at: UtcDatetime
    injected_at: UtcDatetime
    target_pods: list[PodAlias] = Field(min_length=1)


class ChaosResult(_Model):
    phase: Token | None
    verdict: Token | None
    fail_step: Token | None
    probe_success_percentage: int | float | Token | None


class Litmus(_Model):
    verdict: Literal["Pass"]
    phase: Token | None
    engine_status: Token | None
    experiment_status: Token | None
    finished_at: UtcDatetime
    chaos_result: ChaosResult | None


class ErrorCheck(_Model):
    applicable: bool
    ok: bool | None
    error_ratio: float | None
    window_seconds: int | None


class StreakSample(_Model):
    at: UtcDatetime
    available_replicas: float


class Recovery(_Model):
    rule: EngineText
    status: Literal["RECOVERED"]
    evaluations: PositiveInt
    fault_observed_at: UtcDatetime
    recovered_at: UtcDatetime
    confirmed_at: UtcDatetime
    time_to_recovery_seconds: NonNegativeFloat
    stable_streak: list[StreakSample]
    max_sample_gap_seconds: float | None
    error_check: ErrorCheck | None


class FailureInterval(_Model):
    start: UtcDatetime
    end: UtcDatetime
    failed: NonNegativeInt
    by_outcome: dict[Literal["http_error", "connection_error", "timeout"], int]


class OutageWindow(_Model):
    start: UtcDatetime
    end: UtcDatetime | None
    seconds: float | None


class ClientOutage(_Model):
    status: Literal["OK", "INSUFFICIENT_DATA"]
    pattern: Literal["NONE", "CONTINUOUS", "INTERMITTENT", "INSUFFICIENT_DATA"]
    outage_seconds: float | None
    outages: int | None
    reset_detected: bool | None
    starts_before_fault: bool | None
    counted_from: UtcDatetime | None
    counted_to: UtcDatetime | None
    outage_windows: list[OutageWindow]


class ClientImpact(_Model):
    status: Literal["OK", "UNAVAILABLE"]
    requests: int | None
    success: int | None
    http_error: int | None
    connection_error: int | None
    timeout: int | None
    failed: int | None
    failure_ratio: float | None
    latency_p95_seconds: float | None
    counted_from: UtcDatetime | None
    counted_to: UtcDatetime | None
    starts_before_fault: bool | None
    failure_intervals: list[FailureInterval]
    outage: ClientOutage | None


class ReplacementPod(_Model):
    pod: PodAlias
    created_at: UtcDatetime
    ready_at: UtcDatetime | None


class Impact(_Model):
    window_seconds: PositiveInt
    availability_samples: NonNegativeInt
    min_available_replicas: int | None
    availability_dip_observed: bool
    restarts_in_window: int | None
    requests_in_window: float | None
    errors_in_window: float | None
    client: ClientImpact | None
    replacement_pods: list[ReplacementPod]


class TargetAfter(_Model):
    """Kubernetes' own view at recovery time (evidence only; never decides)."""

    deleted_pods_still_present: list[PodAlias]
    ready_pods: list[PodAlias]
    desired_replicas: int | None


class Outcome(_Model):
    status: Literal["COMPLETED"]
    reason_code: Literal["RECOVERED"]


class Transition(_Model):
    at: UtcDatetime
    from_state: State
    to_state: State


class Lifecycle(_Model):
    mode: Literal["auto"]
    requested_at: UtcDatetime
    state_since: dict[State, UtcDatetime]
    transitions: list[Transition]


class ScoreComponent(_Model):
    name: Token
    status: Literal["SCORED", "NOT_APPLICABLE"]
    # Engine-computed inputs: numbers, flags, enum tokens, timestamps (e.g. counted_from).
    raw: dict[Token, UtcDatetime | Scalar | list[OutageWindow]]
    normalized: float | None
    weight: float
    effective_weight: float
    contribution: float
    reason: EngineText


class Score(_Model):
    version: Literal["v1", "v2", "v3"]
    status: Literal["SCORED"]
    score: float = Field(ge=0, le=100)
    rating: Literal["Excellent", "Good", "Fair", "Poor"]
    explanation: EngineText
    components: list[ScoreComponent] = Field(min_length=1)
    weights: dict[Token, float] | None
    thresholds: dict[Token, float] | None


class RecordedRun(_Model):
    state: Literal["COMPLETED"]
    created_at: UtcDatetime
    target: Target
    fault: Fault
    validation: Validation
    baseline: Baseline
    injection: Injection
    litmus: Litmus
    recovery: Recovery
    impact: Impact
    target_after: TargetAfter | None
    outcome: Outcome
    lifecycle: Lifecycle
    score: Score


# --- provenance and integrity ------------------------------------------------------


class LevelAReview(_Model):
    reviewed_by: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
    reviewed_at: UtcDatetime


class _ProvenanceBase(_Model):
    # Declared by the maintainer at export time; never inferred.
    evidence_category: Literal["controlled_research", "development_run"]
    # The exporter always writes "unclassified"; "A" is a manual review decision.
    evidence_level: Literal["unclassified", "A"]
    level_a_review: LevelAReview | None
    synthetic: bool
    captured_at: UtcDatetime
    exported_at: UtcDatetime
    engine_commit: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    exporter_version: Literal["1.0.0"]
    environment: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z0-9 ,.()/+_-]{3,120}$")
    ]

    @model_validator(mode="after")
    def _level_a_rules(self) -> "_ProvenanceBase":
        if self.evidence_level == "A":
            if self.evidence_category != "controlled_research":
                raise ValueError(
                    "Level A requires evidence_category controlled_research"
                )
            if self.synthetic:
                raise ValueError("synthetic recordings can never be Level A")
            if self.level_a_review is None:
                raise ValueError("Level A requires a level_a_review record")
        elif self.level_a_review is not None:
            raise ValueError("level_a_review is only allowed with evidence_level A")
        return self


class Provenance(_ProvenanceBase):
    score_version: Literal["v1", "v2", "v3"]


class ValidationProvenance(_ProvenanceBase):
    """A rejected experiment never ran, so there is no score."""


class Integrity(_Model):
    algorithm: Literal["sha256"]
    canonicalization: Literal["json-sorted-compact/1"]
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def canonical_bytes(content: Any) -> bytes:
    """Sorted keys, no whitespace, UTF-8, no NaN/Infinity."""
    return json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def content_hash(document: dict[str, Any]) -> str:
    """sha256 over the canonical document without its `integrity` block."""
    body = {k: v for k, v in document.items() if k != "integrity"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


class RecordedExperiment(_Model):
    schema_: Literal["autoresilience-recording/1"] = Field(alias="schema")
    recording_id: Annotated[str, StringConstraints(pattern=r"^rec-[0-9a-f]{16}$")]
    provenance: Provenance
    experiment: RecordedRun
    integrity: Integrity

    @model_validator(mode="after")
    def _consistent(self, info: ValidationInfo) -> "RecordedExperiment":
        run = self.experiment
        if self.provenance.score_version != run.score.version:
            raise ValueError("provenance.score_version differs from experiment.score")
        times = [
            run.lifecycle.state_since[s]
            for s in LIFECYCLE_ORDER
            if s in run.lifecycle.state_since
        ]
        if times != sorted(times) or "COMPLETED" not in run.lifecycle.state_since:
            raise ValueError("lifecycle.state_since is incomplete or out of order")
        _check_sealed(self.to_document(), self.integrity, info)
        return self

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def _check_sealed(
    document: dict[str, Any], integrity: Integrity, info: ValidationInfo
) -> None:
    for text in _strings(document):
        if found := sensitive_findings(text):
            raise ValueError(f"unsafe content ({', '.join(found)}) in recording")
    draft = bool(info.context and info.context.get("draft"))
    if not draft and content_hash(document) != integrity.content_sha256:
        raise ValueError("integrity.content_sha256 does not match the content")


# --- safety-rejected experiments (autoresilience-validation/1) -----------------------


class RejectedFault(_Model):
    # Any requested fault: an unsupported type is itself a reason for rejection.
    type: Token
    pod_delete_mode: Literal["GRACEFUL", "FORCE"]
    duration_seconds: PositiveInt
    affected_replicas: PositiveInt


class RejectedCheck(_Model):
    phase: Literal["static", "cluster"]
    name: Token
    status: Literal["PASSED", "FAILED", "ERROR", "SKIPPED"]
    # Engine-generated; kept only for shipped sample workloads (it names the target).
    message: EngineText | None


class RejectedValidation(_Model):
    passed: Literal[False]
    policy: PolicySnapshot
    checks: list[RejectedCheck] = Field(min_length=1)

    @model_validator(mode="after")
    def _has_failure(self) -> "RejectedValidation":
        if all(c.status == "PASSED" for c in self.checks):
            raise ValueError("a rejected validation needs a check that did not pass")
        return self


class RejectedRun(_Model):
    state: Literal["VALIDATION_FAILED"]
    created_at: UtcDatetime
    target: Target
    fault: RejectedFault
    validation: RejectedValidation


class RecordedValidation(_Model):
    """Evidence that the safety model refused an experiment before any injection."""

    schema_: Literal["autoresilience-validation/1"] = Field(alias="schema")
    recording_id: Annotated[str, StringConstraints(pattern=r"^val-[0-9a-f]{16}$")]
    provenance: ValidationProvenance
    experiment: RejectedRun
    integrity: Integrity

    @model_validator(mode="after")
    def _consistent(self, info: ValidationInfo) -> "RecordedValidation":
        _check_sealed(self.to_document(), self.integrity, info)
        return self

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


AnyRecording = RecordedExperiment | RecordedValidation
MODELS: dict[str, type[RecordedExperiment] | type[RecordedValidation]] = {
    SCHEMA_ID: RecordedExperiment,
    VALIDATION_SCHEMA_ID: RecordedValidation,
}


class RecordingFormatError(ValueError):
    pass


def parse_recording(raw: str | bytes) -> AnyRecording:
    """Strictly parse and verify one recording file (schema, safety, hash, form)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecordingFormatError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RecordingFormatError("a recording must be a JSON object")
    if data.get("schema") not in SUPPORTED_SCHEMAS:
        raise RecordingFormatError(
            f"unsupported recording schema {data.get('schema')!r} "
            f"(supported: {', '.join(SUPPORTED_SCHEMAS)})"
        )
    recording = MODELS[data["schema"]].model_validate_json(raw)
    # Exactly what the model emits: no hidden normalisation differences.
    if recording.to_document() != data:
        raise RecordingFormatError("file is not in canonical form; re-export it")
    return recording


def render(recording: AnyRecording) -> str:
    return json.dumps(recording.to_document(), indent=2, sort_keys=True) + "\n"


def json_schema(schema_id: str = SCHEMA_ID) -> dict[str, Any]:
    schema = MODELS[schema_id].model_json_schema(by_alias=True)
    schema["$id"] = schema_id
    return schema
