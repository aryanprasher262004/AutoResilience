"""Environment status: can this API reach everything an experiment needs?

Unlike readiness (database only), this also probes the cluster and Prometheus, with
the same read-only calls normal operations use. It is informational: experiment
endpoints still report their own errors per request.
"""

from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.kubernetes_adapter import (
    ClusterUnavailableError,
    WorkloadSummary,
)
from app.integrations.prometheus_client import PrometheusError
from app.services.readiness import check_database


class Workloads(Protocol):
    def list_workloads(self) -> list[WorkloadSummary]: ...


class PrometheusStatus(Protocol):
    def build_info(self) -> str: ...


def public_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return f"{parts.scheme}://{host}{f':{parts.port}' if parts.port else ''}"


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def check_kubernetes(kubernetes: Workloads, context: str | None) -> dict[str, Any]:
    where = f"context {context}" if context else "the kubeconfig's current context"
    try:
        count = len(kubernetes.list_workloads())
    except ClusterUnavailableError as exc:
        return _check("kubernetes", False, f"Cannot list workloads via {where}: {exc}")
    return _check("kubernetes", True, f"{count} workloads visible via {where}")


def check_prometheus(prometheus: PrometheusStatus, url: str) -> dict[str, Any]:
    try:
        version = prometheus.build_info()
    except PrometheusError as exc:
        return _check("prometheus", False, f"{url}: {exc}")
    return _check("prometheus", True, f"{url}: Prometheus {version}")


def environment(
    db: Session,
    kubernetes: Workloads,
    prometheus: PrometheusStatus,
    settings: Settings,
) -> dict[str, Any]:
    url = public_url(settings.prometheus_url)
    database = check_database(db)
    return {
        "runtime_mode": settings.runtime_mode,
        "kube_context": settings.kube_context,
        "prometheus_url": url,
        "checks": [
            _check("database", database["status"] == "pass", database["detail"]),
            check_kubernetes(kubernetes, settings.kube_context),
            check_prometheus(prometheus, url),
        ],
    }
