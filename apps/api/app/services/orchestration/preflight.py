from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.safety_policy import SafetyPolicy
from app.domain.state_machine import ExperimentState, transition
from app.integrations.kubernetes_adapter import (
    ClusterUnavailableError,
    KubernetesAdapter,
)
from app.services.safety.policy_evaluator import (
    ValidationResult,
    errored_cluster_checks,
    evaluate_cluster,
    evaluate_static,
    skipped_cluster_checks,
)


def run_validation(
    db: Session,
    experiment: Experiment,
    policy: SafetyPolicy,
    kubernetes: KubernetesAdapter,
) -> None:
    """CREATED -> VALIDATING -> BASELINING | VALIDATION_FAILED, committing each step.

    Static checks run first; the cluster is only queried if they all pass.
    Raises InvalidTransitionError (before any change) if the experiment is not CREATED.
    """
    experiment.state = transition(experiment.state, ExperimentState.VALIDATING)
    db.commit()

    spec = experiment.spec
    static_checks = evaluate_static(spec, policy)
    if not all(c.passed for c in static_checks):
        cluster_checks = skipped_cluster_checks(
            "Skipped: static policy checks failed; cluster not queried"
        )
    else:
        try:
            status = kubernetes.get_workload_status(spec.target)
        except ClusterUnavailableError as exc:
            cluster_checks = errored_cluster_checks(str(exc))
        else:
            cluster_checks = evaluate_cluster(spec, policy, status)

    result = ValidationResult(static_checks, cluster_checks, policy)
    outcome = (
        ExperimentState.BASELINING
        if result.passed
        else ExperimentState.VALIDATION_FAILED
    )
    experiment.validation_result = result.to_dict()
    experiment.state = transition(experiment.state, outcome)
    db.commit()
