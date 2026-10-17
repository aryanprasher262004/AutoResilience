"""Export one COMPLETED experiment as a recording (`autoresilience-recording/1`).

Read-only: one read-only transaction, by explicit experiment id, then rollback. No
HTTP endpoint, no chaos, no cluster access. Fields are copied by allowlist into the
contract in app/schemas/recording.py; identifiers outside the shipped sample apps
are pseudonymised, pod names always are. Incomplete or inconsistent records
(including a stored score that its own version cannot reproduce) are refused.

    uv run python -m app.tools.export_recording export <id> \\
        --evidence-category development_run --environment "kind, single node" \\
        --engine-commit <40-hex sha> [--out ../../recordings/<file>.json]
    uv run python -m app.tools.export_recording verify [paths or directories...]
    uv run python -m app.tools.export_recording schema [--check]
"""

import argparse
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.state_machine import ExperimentState
from app.schemas.recording import (
    CANONICALIZATION,
    EXPORTER_VERSION,
    LIFECYCLE_ORDER,
    SCHEMA_ID,
    RecordedExperiment,
    RecordingFormatError,
    content_hash,
    json_schema,
    parse_recording,
    render,
)
from app.services.scoring.resilience_score import SUPPORTED_VERSIONS, score_experiment

EvidenceCategory = Literal["controlled_research", "development_run"]

# Shipped sample workloads (infra/sample-app); their names are public already.
SAMPLE_WORKLOADS = frozenset(
    {
        ("shop", "frontend"),
        ("shop", "checkout"),
        ("shop", "cart-redis"),
        ("resilience-sandbox", "fragile"),
    }
)
REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = REPO_ROOT / "packages/contracts/recorded-experiment.schema.json"
RECORDINGS_DIR = REPO_ROOT / "recordings"
_TRANSITION = re.compile(r"^([A-Z_]+) -> ([A-Z_]+)\b")


class RecordingError(Exception):
    """Refusal to export; `code` is stable for scripts and tests."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _require(value: Any, path: str) -> Any:
    if value is None or value == {} or value == []:
        raise RecordingError("MISSING_EVIDENCE", f"{path} is missing")
    return value


def _get(record: dict[str, Any] | None, path: str) -> Any:
    value: Any = record
    for part in path.split(".")[1:]:
        value = value.get(part) if isinstance(value, dict) else None
    return _require(value, path)


def _inconsistent(message: str) -> RecordingError:
    return RecordingError("INCONSISTENT", message)


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value))


class _Aliases:
    """Stable per-recording pod aliases (pod-1, pod-2, ... in sorted name order)."""

    def __init__(self, names: set[str]) -> None:
        self._map = {name: f"pod-{i}" for i, name in enumerate(sorted(names), 1)}

    def __call__(self, name: str) -> str:
        return self._map[name]


def _check_score(experiment: Experiment, stored: dict[str, Any]) -> str:
    version = stored.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise RecordingError(
            "UNSUPPORTED_SCORE_VERSION", f"score version {version!r} is not known"
        )
    if stored.get("status") != "SCORED":
        raise _inconsistent(f"COMPLETED run has score status {stored.get('status')}")
    recomputed = score_experiment(
        experiment.state.value,
        experiment.baseline,
        experiment.observation,
        version=version,
        chaos=experiment.chaos,
    )
    if _json(recomputed) != _json(stored):
        raise _inconsistent(
            f"stored {version} score is not reproducible from the stored evidence"
        )
    return str(version)


def _lifecycle(orch: dict[str, Any]) -> dict[str, Any]:
    if orch.get("mode") != "auto":
        raise RecordingError(
            "MISSING_EVIDENCE",
            "orchestration timeline missing (only auto runs started with /run "
            "have one)",
        )
    since = _get(orch, "orchestration.state_since")
    transitions = []
    for event in orch.get("events") or []:
        match = _TRANSITION.match(str(event.get("event", "")))
        if match and {match[1], match[2]} <= set(LIFECYCLE_ORDER):
            transitions.append(
                {"at": event["at"], "from_state": match[1], "to_state": match[2]}
            )
    return {
        "mode": "auto",
        "requested_at": _get(orch, "orchestration.requested_at"),
        "state_since": {k: v for k, v in since.items() if k in LIFECYCLE_ORDER},
        "transitions": transitions,
    }


def _client(client: dict[str, Any] | None) -> dict[str, Any] | None:
    if not client:
        return None
    outage = client.get("outage")
    return {
        "status": client["status"],
        **{
            k: client.get(k)
            for k in (
                "requests",
                "success",
                "http_error",
                "connection_error",
                "timeout",
                "failed",
                "failure_ratio",
                "latency_p95_seconds",
                "counted_from",
                "counted_to",
                "starts_before_fault",
            )
        },
        "failure_intervals": [
            {
                "start": i["from"],
                "end": i["to"],
                "failed": i["failed"],
                "by_outcome": i["by_outcome"],
            }
            for i in client.get("failure_intervals") or []
        ],
        "outage": None
        if not outage
        else {
            "status": outage["status"],
            "pattern": outage["pattern"],
            **{
                k: outage.get(k)
                for k in (
                    "outage_seconds",
                    "outages",
                    "reset_detected",
                    "starts_before_fault",
                    "counted_from",
                    "counted_to",
                )
            },
            "outage_windows": [
                {"start": w["start"], "end": w.get("end"), "seconds": w.get("seconds")}
                for w in outage.get("outage_windows") or []
            ],
        },
    }


def _metric_group(group: dict[str, Any] | None) -> dict[str, Any] | None:
    if group is None:
        return None
    return {"status": group["status"], "values": group.get("values") or {}}


def _score(stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": stored["version"],
        "status": stored["status"],
        "score": stored["score"],
        "rating": stored["rating"],
        "explanation": stored["explanation"],
        "components": [
            {
                k: c[k]
                for k in (
                    "name",
                    "status",
                    "raw",
                    "normalized",
                    "weight",
                    "effective_weight",
                    "contribution",
                    "reason",
                )
            }
            for c in stored["components"]
        ],
        "weights": stored.get("weights"),
        "thresholds": stored.get("thresholds"),
    }


def _ordered(*stamps: tuple[str, str]) -> None:
    times = [(name, datetime.fromisoformat(value)) for name, value in stamps]
    for (a, ta), (b, tb) in pairwise(times):
        if tb < ta:
            raise _inconsistent(f"{b} ({tb.isoformat()}) is before {a}")


def build_document(experiment: Experiment, **options: Any) -> dict[str, Any]:
    """Allowlisted, sanitized recording body (no integrity block yet)."""
    try:
        return _build(experiment, **options)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        # Stored JSON that does not have the shape the engine writes.
        raise RecordingError(
            "MISSING_EVIDENCE", f"malformed stored evidence ({exc!r})"
        ) from exc


def _build(
    experiment: Experiment,
    *,
    evidence_category: EvidenceCategory,
    environment: str,
    engine_commit: str,
    exported_at: datetime,
    synthetic: bool = False,
) -> dict[str, Any]:
    if experiment.state is not ExperimentState.COMPLETED:
        raise RecordingError(
            "NOT_COMPLETED", f"experiment is {experiment.state}, not COMPLETED"
        )
    validation = _require(experiment.validation_result, "validation_result")
    baseline = _require(experiment.baseline, "baseline")
    chaos = _require(experiment.chaos, "chaos")
    observation = _require(experiment.observation, "observation")
    stored_score = _require(experiment.score, "score")
    orch = _require(experiment.orchestration, "orchestration")
    litmus = _get(observation, "observation.litmus")
    recovery = _get(observation, "observation.recovery")
    impact = _get(observation, "observation.impact")
    result = _get(observation, "observation.result")

    # Cross-checks between the stored records.
    checks = [
        {"phase": phase, "name": c["name"], "status": c["status"]}
        for phase in ("static", "cluster")
        for c in validation.get(f"{phase}_checks") or []
    ]
    if not validation.get("passed") or any(c["status"] != "PASSED" for c in checks):
        raise _inconsistent("COMPLETED run without an all-PASSED validation")
    policy = _get(validation, "validation_result.policy")
    if chaos.get("safety_policy") != policy.get("name"):
        raise _inconsistent("injection policy differs from the validated policy")
    if baseline.get("status") != "CAPTURED":
        raise _inconsistent(f"baseline is {baseline.get('status')}, not CAPTURED")
    if result.get("status") != "COMPLETED" or result.get("reason_code") != "RECOVERED":
        raise _inconsistent(f"observation result is {result.get('status')}")
    if recovery.get("status") != "RECOVERED":
        raise _inconsistent(f"recovery finding is {recovery.get('status')}")
    if litmus.get("verdict") != "Pass":
        raise _inconsistent(
            f"Litmus verdict {litmus.get('verdict')} on a COMPLETED run"
        )
    if chaos.get("experiment") != experiment.fault_type.value:
        raise _inconsistent("injected fault differs from the experiment's fault type")
    target_pods = _get(chaos, "chaos.target_pods")
    if len(target_pods) != experiment.affected_replicas:
        raise _inconsistent("number of target pods differs from affected_replicas")
    for path in (
        "chaos.created_at",
        "chaos.injected_at",
        "recovery.fault_observed_at",
        "recovery.recovered_at",
        "recovery.confirmed_at",
        "recovery.time_to_recovery_seconds",
    ):
        _get(chaos if path.startswith("chaos") else recovery, path)
    _get(litmus, "litmus.finished_at")
    lifecycle = _lifecycle(orch)
    if "COMPLETED" not in lifecycle["state_since"]:
        raise RecordingError("MISSING_EVIDENCE", "no COMPLETED time in the timeline")
    _ordered(
        ("requested_at", lifecycle["requested_at"]),
        ("baseline.captured_at", baseline["captured_at"]),
        ("chaos.created_at", chaos["created_at"]),
        ("chaos.injected_at", chaos["injected_at"]),
        ("litmus.finished_at", litmus["finished_at"]),
    )
    # Recovery is measured independently of Litmus, which waits out the duration.
    _ordered(
        ("chaos.created_at", chaos["created_at"]),
        ("recovery.recovered_at", recovery["recovered_at"]),
        ("recovery.confirmed_at", recovery["confirmed_at"]),
    )
    score_version = _check_score(experiment, stored_score)

    # Identifiers: sample workloads keep their names, everything else is aliased.
    sample = (experiment.target_namespace, experiment.target_name) in SAMPLE_WORKLOADS
    target_after = observation.get("target")
    replacement = impact.get("replacement_pods") or []
    pod_names = {*target_pods, *(p["pod"] for p in replacement)}
    if target_after and "error" not in target_after:
        pod_names |= {
            *target_after.get("deleted_pods_still_present", []),
            *target_after.get("ready_pods_now", []),
        }
    pod = _Aliases(pod_names)

    chaos_result = litmus.get("chaos_result")
    if not chaos_result or "error" in chaos_result:
        chaos_result = None
    run = {
        "state": "COMPLETED",
        # Stored as UTC; SQLite returns it without tzinfo.
        "created_at": experiment.created_at.replace(
            tzinfo=experiment.created_at.tzinfo or UTC
        ).isoformat(),
        "target": {
            "namespace": experiment.target_namespace if sample else "namespace-1",
            "kind": experiment.target_kind.value,
            "name": experiment.target_name if sample else "workload-1",
            "pseudonymised": not sample,
        },
        "fault": {
            "type": experiment.fault_type.value,
            "pod_delete_mode": experiment.pod_delete_mode.value,
            "duration_seconds": experiment.duration_seconds,
            "affected_replicas": experiment.affected_replicas,
        },
        "validation": {
            "passed": True,
            "policy": {
                k: policy.get(k)
                for k in (
                    "name",
                    "max_duration_seconds",
                    "max_affected_replicas",
                    "min_healthy_replicas",
                    "forbidden_namespaces",
                    "allowed_namespaces",
                )
            },
            "checks": checks,
        },
        "baseline": {
            "status": "CAPTURED",
            "captured_at": baseline["captured_at"],
            "window_seconds": baseline["window_seconds"],
            "availability": _metric_group(baseline["availability"]),
            "restarts": _metric_group(baseline["restarts"]),
            "requests": _metric_group(baseline["requests"]),
            "client": _metric_group(baseline.get("client")),
        },
        "injection": {
            "provider": chaos["provider"],
            "experiment": chaos["experiment"],
            "safety_policy": chaos["safety_policy"],
            "created_at": chaos["created_at"],
            "injected_at": chaos["injected_at"],
            "target_pods": sorted(pod(p) for p in target_pods),
        },
        "litmus": {
            "verdict": litmus["verdict"],
            "phase": litmus.get("phase"),
            "engine_status": litmus.get("engine_status"),
            "experiment_status": litmus.get("experiment_status"),
            "finished_at": litmus["finished_at"],
            "chaos_result": None
            if chaos_result is None
            else {
                k: chaos_result.get(k)
                for k in ("phase", "verdict", "fail_step", "probe_success_percentage")
            },
        },
        "recovery": {
            "rule": observation["rule"],
            "status": "RECOVERED",
            "evaluations": observation["evaluations"],
            **{
                k: recovery[k]
                for k in (
                    "fault_observed_at",
                    "recovered_at",
                    "confirmed_at",
                    "time_to_recovery_seconds",
                )
            },
            "stable_streak": [
                {"at": at, "available_replicas": v}
                for at, v in recovery.get("stable_streak") or []
            ],
            "max_sample_gap_seconds": recovery.get("max_sample_gap_seconds"),
            "error_check": None
            if recovery.get("error_check") is None
            else {
                k: recovery["error_check"].get(k)
                for k in ("applicable", "ok", "error_ratio", "window_seconds")
            },
        },
        "impact": {
            **{
                k: impact.get(k)
                for k in (
                    "window_seconds",
                    "availability_samples",
                    "min_available_replicas",
                    "availability_dip_observed",
                    "restarts_in_window",
                    "requests_in_window",
                    "errors_in_window",
                )
            },
            "client": _client(impact.get("client")),
            "replacement_pods": [
                {
                    "pod": pod(p["pod"]),
                    "created_at": p["created_at"],
                    "ready_at": p.get("ready_at"),
                }
                for p in replacement
            ],
        },
        "target_after": None
        if not target_after or "error" in target_after
        else {
            "deleted_pods_still_present": sorted(
                pod(p) for p in target_after.get("deleted_pods_still_present", [])
            ),
            "ready_pods": sorted(
                pod(p) for p in target_after.get("ready_pods_now", [])
            ),
            "desired_replicas": target_after.get("desired_replicas_now"),
        },
        "outcome": {"status": "COMPLETED", "reason_code": "RECOVERED"},
        "lifecycle": lifecycle,
        "score": _score(stored_score),
    }
    document = {
        "schema": SCHEMA_ID,
        "recording_id": "rec-"
        + hashlib.sha256(f"{SCHEMA_ID}:{experiment.id}".encode()).hexdigest()[:16],
        "provenance": {
            "evidence_category": evidence_category,
            "evidence_level": "unclassified",  # never assigned automatically
            "level_a_review": None,
            "synthetic": synthetic,
            "captured_at": lifecycle["state_since"]["COMPLETED"],
            "exported_at": exported_at.isoformat(),
            "engine_commit": engine_commit,
            "exporter_version": EXPORTER_VERSION,
            "score_version": score_version,
            "environment": environment,
        },
        "experiment": run,
    }
    _assert_no_leaks(_json(document), experiment, pod_names, sample)
    return document


def _assert_no_leaks(
    document: Any, experiment: Experiment, pods: set[str], sample: bool
) -> None:
    """Defence in depth: no original identifier may survive sanitization."""
    secret = {
        "experiment id": {str(experiment.id)},
        "experiment name": {experiment.name},
        "description": {experiment.description or ""},
        "pod name": pods,
        "engine name": {str((experiment.chaos or {}).get("engine_name") or "")},
        "target": set()
        if sample
        else {experiment.target_namespace, experiment.target_name},
    }
    blob = json.dumps(document)
    for kind, values in secret.items():
        for value in values:
            if len(value) >= 3 and re.search(
                rf"(?<![A-Za-z0-9-]){re.escape(value)}(?![A-Za-z0-9-])", blob
            ):
                raise RecordingError("UNSAFE", f"original {kind} survived export")


def seal(document: dict[str, Any]) -> RecordedExperiment:
    """Normalise through the contract, hash the canonical form, verify."""
    try:
        draft = RecordedExperiment.model_validate_json(
            json.dumps({**document, "integrity": _integrity("0" * 64)}),
            context={"draft": True},
        ).to_document()
        draft["integrity"] = _integrity(content_hash(draft))
        return RecordedExperiment.model_validate_json(json.dumps(draft))
    except ValidationError as exc:
        raise RecordingError("INVALID", _first_error(exc)) from exc


def _integrity(digest: str) -> dict[str, str]:
    return {
        "algorithm": "sha256",
        "canonicalization": CANONICALIZATION,
        "content_sha256": digest,
    }


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    loc = ".".join(str(p) for p in error["loc"])
    return f"{loc}: {error['msg']}" if loc else error["msg"]


def export_experiment(
    session: Session, experiment_id: uuid.UUID, **options: Any
) -> RecordedExperiment:
    """Read-only: the transaction is marked READ ONLY (PostgreSQL) and rolled back."""
    try:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise RecordingError("NOT_FOUND", f"experiment {experiment_id} not found")
        return seal(build_document(experiment, **options))
    finally:
        session.rollback()


# --- CLI ---------------------------------------------------------------------------


def _recording_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths or [str(RECORDINGS_DIR)]:
        path = Path(raw)
        if path.is_dir():
            files += sorted(path.glob("*.json"))
        elif path.exists():
            files.append(path)
        else:
            raise SystemExit(f"error: {path} does not exist")
    return files


def _verify(paths: list[str], out: Callable[[str], None]) -> int:
    failures = 0
    files = _recording_files(paths)
    for path in files:
        try:
            recording = parse_recording(path.read_bytes())
        except (RecordingFormatError, ValidationError) as exc:
            failures += 1
            detail = _first_error(exc) if isinstance(exc, ValidationError) else exc
            out(f"FAIL {path}: {detail}")
            continue
        if path.name != f"{recording.recording_id}.json":
            failures += 1
            out(f"FAIL {path}: file must be named {recording.recording_id}.json")
            continue
        out(f"ok   {path} ({recording.integrity.content_sha256[:12]})")
    out(f"{len(files)} recording(s) checked, {failures} failed")
    return 1 if failures else 0


def _schema(check: bool, out: Callable[[str], None]) -> int:
    expected = json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"
    if not check:
        SCHEMA_PATH.write_text(expected)
        out(f"wrote {SCHEMA_PATH}")
        return 0
    if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text() != expected:
        out(f"FAIL {SCHEMA_PATH} is stale; run: export_recording schema")
        return 1
    out(f"ok   {SCHEMA_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export_recording", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="export one COMPLETED experiment")
    exp.add_argument("experiment_id", type=uuid.UUID)
    exp.add_argument(
        "--evidence-category",
        required=True,
        choices=["controlled_research", "development_run"],
    )
    exp.add_argument("--environment", required=True)
    exp.add_argument(
        "--engine-commit", required=True, help="commit the API ran when captured"
    )
    exp.add_argument("--exported-at", type=datetime.fromisoformat)
    exp.add_argument("--out", type=Path, help="file to write (default: stdout)")
    ver = sub.add_parser("verify", help="validate recordings (default: recordings/)")
    ver.add_argument("paths", nargs="*")
    sch = sub.add_parser("schema", help="write the generated JSON Schema")
    sch.add_argument("--check", action="store_true", help="fail if it is stale")
    args = parser.parse_args(argv)

    if args.command == "verify":
        return _verify(args.paths, print)
    if args.command == "schema":
        return _schema(args.check, print)

    from app.db.session import SessionLocal

    exported_at = args.exported_at or datetime.now(UTC)
    if exported_at.tzinfo is None:
        parser.error("--exported-at needs a timezone")
    try:
        with SessionLocal() as session:
            recording = export_experiment(
                session,
                args.experiment_id,
                evidence_category=args.evidence_category,
                environment=args.environment,
                engine_commit=args.engine_commit,
                exported_at=exported_at,
            )
    except RecordingError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"error: database unavailable ({type(exc).__name__})", file=sys.stderr)
        return 3
    if args.out:
        args.out.write_text(render(recording))
        print(f"wrote {args.out} ({recording.integrity.content_sha256})")
    else:
        sys.stdout.write(render(recording))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
