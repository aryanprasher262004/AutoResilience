"""Recorded experiment contract and read-only exporter (synthetic data only)."""

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.schemas.recording import (
    RecordedExperiment,
    RecordingFormatError,
    content_hash,
    json_schema,
    parse_recording,
    render,
)
from app.tools import export_recording
from app.tools.export_recording import (
    RecordingError,
    build_document,
    export_experiment,
    seal,
)
from tests.api.test_orchestration import DONE, new_reconciler, start, tick_until
from tests.conftest import Clock, FakeChaos, FakeKubernetes, FakePrometheus

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
EXPORTED_AT = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
COMMIT = "0123456789abcdef0123456789abcdef01234567"
OPTIONS: dict[str, Any] = {
    "evidence_category": "development_run",
    "environment": "kind, single node, sample apps (synthetic test)",
    "engine_commit": COMMIT,
    "exported_at": EXPORTED_AT,
    "synthetic": True,
}


@pytest.fixture
def completed(
    client: TestClient,
    db_session: Session,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
    clock: Clock,
) -> Experiment:
    """A COMPLETED auto run driven through the real lifecycle with fakes."""
    clock.now = T0
    reconciler = new_reconciler(db_session, kubernetes, prometheus, chaos, clock)
    experiment_id = start(client, description="internal note: db at 10.0.0.7")
    body = tick_until(reconciler, client, experiment_id, "OBSERVING", clock)
    fault_start = datetime.fromisoformat(body["chaos"]["created_at"]).timestamp()
    prometheus.healthy_recovery(fault_start)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)
    reconciler.tick()
    experiment = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert experiment is not None and experiment.state == "COMPLETED"
    return experiment


def export(experiment: Experiment, **overrides: Any) -> RecordedExperiment:
    return seal(build_document(experiment, **{**OPTIONS, **overrides}))


def refusal(experiment: Experiment) -> str:
    with pytest.raises(RecordingError) as exc:
        export(experiment)
    return exc.value.code


# --- valid exports -------------------------------------------------------------------


def test_completed_experiment_exports_a_valid_recording(
    completed: Experiment,
) -> None:
    recording = export(completed)
    doc = recording.to_document()

    assert doc["schema"] == "autoresilience-recording/1"
    assert doc["provenance"]["evidence_level"] == "unclassified"
    assert doc["provenance"]["evidence_category"] == "development_run"
    assert doc["provenance"]["synthetic"] is True
    assert doc["provenance"]["score_version"] == completed.score["version"]  # type: ignore[index]
    run = doc["experiment"]
    assert run["target"] == {
        "namespace": "shop",
        "kind": "Deployment",
        "name": "checkout",
        "pseudonymised": False,
    }
    assert run["score"]["score"] == completed.score["score"]  # type: ignore[index]
    assert run["injection"]["target_pods"] == ["pod-1"]
    assert run["lifecycle"]["state_since"]["COMPLETED"]
    assert any(t["to_state"] == "COMPLETED" for t in run["lifecycle"]["transitions"])
    # Round trip through the file form.
    assert parse_recording(render(recording)) == recording


def test_export_is_read_only(completed: Experiment, db_session: Session) -> None:
    before = copy.deepcopy(
        {c.name: getattr(completed, c.name) for c in Experiment.__table__.columns}
    )
    export_experiment(db_session, completed.id, **OPTIONS)
    db_session.expire_all()
    after = db_session.get(Experiment, completed.id)
    assert {c: getattr(after, c) for c in before} == before
    assert not db_session.dirty and not db_session.new


def test_unknown_experiment_is_not_found(db_session: Session) -> None:
    with pytest.raises(RecordingError) as exc:
        export_experiment(db_session, uuid.uuid4(), **OPTIONS)
    assert exc.value.code == "NOT_FOUND"


# --- deterministic hashes ------------------------------------------------------------


def test_hash_is_deterministic_and_covers_the_content(completed: Experiment) -> None:
    first, second = export(completed), export(completed)
    assert render(first) == render(second)
    assert first.integrity.content_sha256 == second.integrity.content_sha256
    assert first.integrity.content_sha256 == content_hash(first.to_document())

    later = export(completed, exported_at=EXPORTED_AT + timedelta(days=1))
    assert later.integrity.content_sha256 != first.integrity.content_sha256


def test_hash_ignores_key_order_and_whitespace(completed: Experiment) -> None:
    doc = export(completed).to_document()
    shuffled = json.dumps(dict(reversed(list(doc.items()))))
    assert content_hash(json.loads(shuffled)) == doc["integrity"]["content_sha256"]


def test_tampered_recording_is_rejected(completed: Experiment) -> None:
    doc = export(completed).to_document()
    doc["experiment"]["score"]["score"] = 99.9
    with pytest.raises(ValueError, match="content_sha256"):
        parse_recording(json.dumps(doc, sort_keys=True))


# --- incomplete and inconsistent records ---------------------------------------------


def test_only_completed_experiments_are_exported(completed: Experiment) -> None:
    completed.state = "UNKNOWN"  # type: ignore[assignment]
    assert refusal(completed) == "NOT_COMPLETED"


@pytest.mark.parametrize(
    "field", ["baseline", "chaos", "observation", "score", "orchestration"]
)
def test_missing_evidence_is_refused(completed: Experiment, field: str) -> None:
    setattr(completed, field, None)
    assert refusal(completed) == "MISSING_EVIDENCE"


def test_missing_nested_evidence_is_refused(completed: Experiment) -> None:
    observation = copy.deepcopy(completed.observation)
    assert observation is not None
    del observation["recovery"]["confirmed_at"]
    completed.observation = observation
    assert refusal(completed) == "MISSING_EVIDENCE"


def test_malformed_evidence_is_refused_not_crashed(completed: Experiment) -> None:
    baseline = copy.deepcopy(completed.baseline)
    assert baseline is not None
    del baseline["availability"]
    completed.baseline = baseline
    assert refusal(completed) == "MISSING_EVIDENCE"


def test_manual_run_without_timeline_is_refused(completed: Experiment) -> None:
    completed.orchestration = {"mode": "manual"}
    assert refusal(completed) == "MISSING_EVIDENCE"


def test_score_that_does_not_match_its_evidence_is_refused(
    completed: Experiment,
) -> None:
    score = copy.deepcopy(completed.score)
    assert score is not None
    score["score"] = score["score"] - 12.5
    completed.score = score
    assert refusal(completed) == "INCONSISTENT"


def test_failed_litmus_verdict_is_inconsistent(completed: Experiment) -> None:
    observation = copy.deepcopy(completed.observation)
    assert observation is not None
    observation["litmus"]["verdict"] = "Fail"
    completed.observation = observation
    assert refusal(completed) == "INCONSISTENT"


def test_unsupported_score_version_is_refused(completed: Experiment) -> None:
    score = copy.deepcopy(completed.score)
    assert score is not None
    score["version"] = "v9"
    completed.score = score
    assert refusal(completed) == "UNSUPPORTED_SCORE_VERSION"


# --- sanitization and unsafe data ----------------------------------------------------


def test_identifiers_and_free_text_are_not_exported(completed: Experiment) -> None:
    blob = render(export(completed))
    assert str(completed.id) not in blob
    assert completed.name not in blob
    assert "10.0.0.7" not in blob and "internal note" not in blob
    for pod in (completed.chaos or {})["target_pods"]:
        assert pod not in blob
    assert "ar-" not in blob  # engine names


def test_non_sample_targets_are_pseudonymised(completed: Experiment) -> None:
    completed.target_namespace = "payments-prod"
    completed.target_name = "ledger"
    run = export(completed).to_document()["experiment"]
    assert run["target"]["namespace"] == "namespace-1"
    assert run["target"]["name"] == "workload-1"
    assert run["target"]["pseudonymised"] is True
    blob = render(export(completed))
    assert "payments-prod" not in blob and "ledger" not in blob


def test_unknown_fields_are_rejected(completed: Experiment) -> None:
    doc = export(completed).to_document()
    doc["experiment"]["kube_context"] = "kind-autoresilience"
    with pytest.raises(ValueError, match="Extra inputs"):
        RecordedExperiment.model_validate_json(json.dumps(doc))


@pytest.mark.parametrize(
    "value",
    [
        "http://prometheus.monitoring.svc:9090",
        "10.244.0.12",
        "1d6c2f2e-9a4e-4a7a-9c71-0d9c1f6f6a10",
    ],
)
def test_sensitive_strings_are_rejected(completed: Experiment, value: str) -> None:
    doc = build_document(completed, **OPTIONS)
    doc["experiment"]["score"]["explanation"] = f"see {value}"
    with pytest.raises(RecordingError) as exc:
        seal(doc)
    assert exc.value.code == "INVALID"


def test_exporter_never_assigns_level_a(completed: Experiment) -> None:
    recording = export(completed, evidence_category="controlled_research")
    assert recording.provenance.evidence_level == "unclassified"


@pytest.mark.parametrize(
    ("category", "synthetic", "review", "message"),
    [
        ("development_run", False, True, "controlled_research"),
        ("controlled_research", True, True, "synthetic"),
        ("controlled_research", False, False, "level_a_review"),
    ],
)
def test_level_a_rules(
    completed: Experiment,
    category: str,
    synthetic: bool,
    review: bool,
    message: str,
) -> None:
    doc = build_document(completed, **{**OPTIONS, "synthetic": synthetic})
    doc["provenance"].update(
        evidence_category=category,
        evidence_level="A",
        level_a_review={
            "reviewed_by": "maintainer",
            "reviewed_at": EXPORTED_AT.isoformat(),
        }
        if review
        else None,
    )
    with pytest.raises(RecordingError, match=message):
        seal(doc)


# --- file format, versions and CLI ---------------------------------------------------


def test_unsupported_schema_version_is_rejected(completed: Experiment) -> None:
    doc = export(completed).to_document()
    doc["schema"] = "autoresilience-recording/2"
    with pytest.raises(RecordingFormatError, match="unsupported recording schema"):
        parse_recording(json.dumps(doc))


def test_non_canonical_file_is_rejected(completed: Experiment) -> None:
    doc = export(completed).to_document()
    doc["experiment"]["created_at"] = doc["experiment"]["created_at"].replace(
        "Z", "+00:00"
    )
    with pytest.raises(RecordingFormatError, match="canonical"):
        parse_recording(json.dumps(doc))


def test_verify_cli(completed: Experiment, tmp_path: Path) -> None:
    recording = export(completed)
    good = tmp_path / f"{recording.recording_id}.json"
    good.write_text(render(recording))
    lines: list[str] = []
    assert export_recording._verify([str(tmp_path)], lines.append) == 0

    misnamed = tmp_path / "other.json"
    misnamed.write_text(render(recording))
    assert export_recording._verify([str(misnamed)], lines.append) == 1
    assert lines[-1] == "1 recording(s) checked, 1 failed"


def test_committed_schema_matches_the_model() -> None:
    committed = json.loads(export_recording.SCHEMA_PATH.read_text())
    assert committed == json_schema()


def test_committed_recordings_are_valid() -> None:
    assert export_recording._verify([], lambda _: None) == 0
