"""LitmusChaos pod-delete provider.

The only code in AutoResilience that writes to the cluster, and it only ever
creates or stops its own ChaosEngine objects. The ChaosEngine is built from typed,
already-validated fields; no user-supplied YAML is accepted.

Litmus concepts: a ChaosExperiment (vetted template, chaos/templates/pod-delete.yaml)
must exist in the target namespace; a ChaosEngine binds it to the target and
overrides its env; the Litmus operator then runs it as the chaosServiceAccount and
reports progress in the engine's status (and a <engine>-pod-delete ChaosResult).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from urllib3.exceptions import HTTPError

from app.domain.experiment import ExperimentTarget
from app.domain.safety_policy import SYSTEM_NAMESPACES

LITMUS_GROUP = "litmuschaos.io"
LITMUS_VERSION = "v1alpha1"
EXPERIMENT_NAME = "pod-delete"
SERVICE_ACCOUNT = "autoresilience-chaos"
MANAGED_BY_LABEL = {"app.kubernetes.io/managed-by": "autoresilience"}
EXPERIMENT_ID_LABEL = "autoresilience.io/experiment-id"


class ChaosProviderError(Exception):
    """The fault could not be created, inspected or stopped."""


class FaultPhase(StrEnum):
    PENDING = "PENDING"  # engine accepted, experiment pod not running yet
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PodDeleteRequest:
    experiment_id: str
    target: ExperimentTarget
    label_selector: str
    target_pods: tuple[str, ...]
    duration_seconds: int


@dataclass(frozen=True)
class FaultStatus:
    phase: FaultPhase
    engine_status: str | None
    experiment_status: str | None
    verdict: str | None
    experiment_pod: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "phase": self.phase,
            "engine_status": self.engine_status,
            "experiment_status": self.experiment_status,
            "verdict": self.verdict,
            "experiment_pod": self.experiment_pod,
        }


def engine_name(experiment_id: str) -> str:
    # One injection per experiment (state machine), so the id makes it unique.
    return f"ar-{experiment_id}"


def build_pod_delete_engine(request: PodDeleteRequest) -> dict[str, Any]:
    """ChaosEngine for exactly one deletion round of exactly the given pods.

    CHAOS_INTERVAL == TOTAL_CHAOS_DURATION makes pod-delete kill once and then wait
    out the duration, so the blast radius is the validated affected_replicas.
    """
    target = request.target
    if target.namespace in SYSTEM_NAMESPACES:
        raise ChaosProviderError(
            f"Refusing to inject into namespace '{target.namespace}'"
        )
    if not request.target_pods:
        raise ChaosProviderError("No target pods selected")
    if request.duration_seconds <= 0:
        raise ChaosProviderError("Duration must be positive")
    duration = str(request.duration_seconds)
    return {
        "apiVersion": f"{LITMUS_GROUP}/{LITMUS_VERSION}",
        "kind": "ChaosEngine",
        "metadata": {
            "name": engine_name(request.experiment_id),
            "namespace": target.namespace,
            "labels": {**MANAGED_BY_LABEL, EXPERIMENT_ID_LABEL: request.experiment_id},
        },
        "spec": {
            "engineState": "active",
            # Litmus' opt-in annotation check is replaced by AutoResilience validation.
            "annotationCheck": "false",
            "appinfo": {
                "appns": target.namespace,
                "applabel": request.label_selector,
                "appkind": target.kind.lower(),
            },
            "chaosServiceAccount": SERVICE_ACCOUNT,
            "jobCleanUpPolicy": "delete",
            "experiments": [
                {
                    "name": EXPERIMENT_NAME,
                    "spec": {
                        "components": {
                            "env": [
                                {"name": "TOTAL_CHAOS_DURATION", "value": duration},
                                {"name": "CHAOS_INTERVAL", "value": duration},
                                {"name": "FORCE", "value": "false"},
                                {
                                    "name": "TARGET_PODS",
                                    "value": ",".join(request.target_pods),
                                },
                                {"name": "PODS_AFFECTED_PERC", "value": ""},
                                {"name": "SEQUENCE", "value": "parallel"},
                            ]
                        }
                    },
                }
            ],
        },
    }


def parse_engine_status(engine: dict[str, Any]) -> FaultStatus:
    status = engine.get("status") or {}
    experiments = status.get("experiments") or []
    first = experiments[0] if experiments else {}
    engine_status = status.get("engineStatus")
    exp_status = first.get("status")
    verdict = first.get("verdict")
    exp_pod = first.get("experimentPod")
    if exp_pod == "Yet to be launched":
        exp_pod = None

    if engine_status == "stopped" or verdict in ("Fail", "Error", "Stopped"):
        phase = FaultPhase.FAILED
    elif exp_status == "Completed":
        phase = FaultPhase.COMPLETED
    elif exp_status == "Running":
        phase = FaultPhase.RUNNING
    else:
        phase = FaultPhase.PENDING
    return FaultStatus(phase, engine_status, exp_status, verdict, exp_pod)


class LitmusChaosProvider:
    def __init__(self, context: str | None, request_timeout: float) -> None:
        self._context = context
        self._timeout = request_timeout
        self._api_client: Any = None

    def start_pod_delete(self, request: PodDeleteRequest) -> str:
        """Create the ChaosEngine; returns its name."""
        engine = build_pod_delete_engine(request)
        namespace = request.target.namespace
        with _translate_errors("create ChaosEngine"):
            self._require_chaos_setup(namespace)
            self._custom().create_namespaced_custom_object(
                LITMUS_GROUP,
                LITMUS_VERSION,
                namespace,
                "chaosengines",
                engine,
                _request_timeout=self._timeout,
            )
        name: str = engine["metadata"]["name"]
        return name

    def get_status(self, namespace: str, name: str) -> FaultStatus:
        with _translate_errors("read ChaosEngine"):
            engine = self._custom().get_namespaced_custom_object(
                LITMUS_GROUP,
                LITMUS_VERSION,
                namespace,
                "chaosengines",
                name,
                _request_timeout=self._timeout,
            )
        return parse_engine_status(engine)

    def stop(self, namespace: str, name: str) -> None:
        """Ask Litmus to abort the run (engineState: stop)."""
        with _translate_errors("stop ChaosEngine"):
            self._custom().patch_namespaced_custom_object(
                LITMUS_GROUP,
                LITMUS_VERSION,
                namespace,
                "chaosengines",
                name,
                {"spec": {"engineState": "stop"}},
                _request_timeout=self._timeout,
            )

    def _require_chaos_setup(self, namespace: str) -> None:
        try:
            self._custom().get_namespaced_custom_object(
                LITMUS_GROUP,
                LITMUS_VERSION,
                namespace,
                "chaosexperiments",
                EXPERIMENT_NAME,
                _request_timeout=self._timeout,
            )
            client.CoreV1Api(self._client()).read_namespaced_service_account(
                SERVICE_ACCOUNT, namespace, _request_timeout=self._timeout
            )
        except ApiException as exc:
            if exc.status == 404:
                raise ChaosProviderError(
                    f"Namespace '{namespace}' is not prepared for chaos: needs the "
                    f"'{EXPERIMENT_NAME}' ChaosExperiment and '{SERVICE_ACCOUNT}' "
                    "ServiceAccount (see scripts/dev-cluster.sh)"
                ) from exc
            raise

    def _custom(self) -> Any:
        return client.CustomObjectsApi(self._client())

    def _client(self) -> Any:
        if self._api_client is None:
            self._api_client = config.new_client_from_config(context=self._context)
        return self._api_client


@contextmanager
def _translate_errors(action: str) -> Iterator[None]:
    try:
        yield
    except ApiException as exc:
        raise ChaosProviderError(
            f"Failed to {action}: Kubernetes API error {exc.status}: {exc.reason}"
        ) from exc
    except (ConfigException, HTTPError, OSError) as exc:
        raise ChaosProviderError(
            f"Failed to {action}: Kubernetes API unreachable: {exc}"
        ) from exc
