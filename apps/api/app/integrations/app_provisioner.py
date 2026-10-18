"""Deploys and removes imported applications (P7), and nothing else.

The second cluster writer next to LitmusChaosProvider, deliberately separate from it:
it uses its own kubeconfig (PROVISIONER_KUBECONFIG), which must authenticate as the
dedicated `autoresilience-provisioner` ServiceAccount (checked with a
SelfSubjectReview; an operator or admin credential is refused). That identity
(infra/rbac/provisioner.yaml) can only create namespaces and a few RoleBindings
cluster-wide, and a ValidatingAdmissionPolicy confines every write it makes to
namespaces labelled as import namespaces. Inside one, it binds itself to a
namespaced writer role; it has no access anywhere else.

On top of that, this module only writes objects of the allowlisted kinds, only in
the import's own namespace, only carrying the import's id label, and never touches
an existing object that lacks that label. Removal deletes the namespace only after
checking that it, and everything managed in it, belongs to the import.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from kubernetes import config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from urllib3.exceptions import HTTPError

from app.services.imports.plan import (
    CHAOS_RUNNER_ROLE,
    ENGINE_CHAOS_ROLE,
    IMPORT_ID_LABEL,
    NAMESPACE_PREFIX,
    OWNER_LABEL,
    OWNER_VALUE,
)

PROVISIONER_USER = (
    "system:serviceaccount:autoresilience-system:autoresilience-provisioner"
)
FIELD_MANAGER = "autoresilience-import"
WRITER_ROLE = "autoresilience-import-writer"
WRITER_BINDING = "autoresilience-provisioner"
# (apiVersion, kind) -> (API prefix, plural, namespaced). Nothing else is ever written.
RESOURCES: dict[tuple[str, str], tuple[str, str, bool]] = {
    ("v1", "Namespace"): ("/api/v1", "namespaces", False),
    ("v1", "ResourceQuota"): ("/api/v1", "resourcequotas", True),
    ("v1", "LimitRange"): ("/api/v1", "limitranges", True),
    ("v1", "ServiceAccount"): ("/api/v1", "serviceaccounts", True),
    ("v1", "ConfigMap"): ("/api/v1", "configmaps", True),
    ("v1", "Service"): ("/api/v1", "services", True),
    ("apps/v1", "Deployment"): ("/apis/apps/v1", "deployments", True),
    ("apps/v1", "StatefulSet"): ("/apis/apps/v1", "statefulsets", True),
    ("networking.k8s.io/v1", "NetworkPolicy"): (
        "/apis/networking.k8s.io/v1",
        "networkpolicies",
        True,
    ),
    ("rbac.authorization.k8s.io/v1", "RoleBinding"): (
        "/apis/rbac.authorization.k8s.io/v1",
        "rolebindings",
        True,
    ),
    ("litmuschaos.io/v1alpha1", "ChaosExperiment"): (
        "/apis/litmuschaos.io/v1alpha1",
        "chaosexperiments",
        True,
    ),
}
BINDABLE_ROLES = {CHAOS_RUNNER_ROLE, ENGINE_CHAOS_ROLE}
# Checked before removal: anything of these kinds without the import's label blocks it.
MANAGED_PLURALS = [
    ("/apis/apps/v1", "deployments"),
    ("/apis/apps/v1", "statefulsets"),
    ("/api/v1", "services"),
    ("/api/v1", "configmaps"),
    ("/api/v1", "serviceaccounts"),
    ("/apis/rbac.authorization.k8s.io/v1", "rolebindings"),
]
# Created by Kubernetes itself in every namespace.
BUILTIN = {("configmaps", "kube-root-ca.crt"), ("serviceaccounts", "default")}


class ProvisionerUnavailableError(Exception):
    """No provisioner identity is configured, or it is not the dedicated one."""


class ProvisionerError(Exception):
    """A write failed or was refused; the message is safe to show."""


class OwnershipError(ProvisionerError):
    """An object exists that this import did not create; nothing was changed."""


def _labels(obj: dict[str, Any]) -> dict[str, str]:
    return (obj.get("metadata") or {}).get("labels") or {}


def owned(obj: dict[str, Any], import_id: str) -> bool:
    labels = _labels(obj)
    return (
        labels.get(OWNER_LABEL) == OWNER_VALUE
        and labels.get(IMPORT_ID_LABEL) == import_id
    )


def check_objects(
    namespace: str, import_id: str, objects: list[dict[str, Any]]
) -> None:
    """Refuse anything a plan from services/imports/plan.py would never contain."""
    if not namespace.startswith(NAMESPACE_PREFIX):
        raise ProvisionerError(f"{namespace!r} is not an import namespace")
    for obj in objects:
        key = (obj.get("apiVersion"), obj.get("kind"))
        meta = obj.get("metadata") or {}
        what = f"{key[1]} {meta.get('name')}"
        if key not in RESOURCES:
            raise ProvisionerError(f"{what}: kind is not allowed")
        if not owned(obj, import_id):
            raise ProvisionerError(f"{what}: missing the import's ownership labels")
        if key[1] == "Namespace":
            if meta.get("name") != namespace:
                raise ProvisionerError(f"{what}: not the import's namespace")
        elif meta.get("namespace") != namespace:
            raise ProvisionerError(f"{what}: outside the import's namespace")
        if key[1] == "RoleBinding":
            role = obj.get("roleRef") or {}
            if (
                role.get("kind") != "ClusterRole"
                or role.get("name") not in BINDABLE_ROLES
            ):
                raise ProvisionerError(f"{what}: binds a role that is not allowed")
        if key[1] == "Service" and (obj.get("spec") or {}).get("type") != "ClusterIP":
            raise ProvisionerError(f"{what}: only ClusterIP Services are allowed")


class ImportProvisioner:
    def __init__(
        self, kubeconfig: str | None, context: str | None, request_timeout: float
    ) -> None:
        self._kubeconfig = kubeconfig
        self._context = context
        self._timeout = request_timeout
        self._api_client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._kubeconfig)

    # --- identity -------------------------------------------------------------------

    def identity(self) -> str:
        """The authenticated user name (SelfSubjectReview). Raises if unusable."""
        body = self._call(
            "POST",
            "/apis/authentication.k8s.io/v1/selfsubjectreviews",
            body={
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "SelfSubjectReview",
            },
        )
        return str(
            ((body.get("status") or {}).get("userInfo") or {}).get("username", "")
        )

    def verify(self) -> None:
        user = self.identity()
        if user != PROVISIONER_USER:
            raise ProvisionerUnavailableError(
                f"The provisioner kubeconfig authenticates as {user!r}, not the dedicated "
                f"{PROVISIONER_USER!r}; refusing to deploy with it "
                "(scripts/dev-provisioner.sh or `ar install` creates the right one)"
            )

    def cluster_fingerprint(self) -> str | None:
        """kube-system's UID: identifies the cluster the credential reaches."""
        body = self._get("/api/v1/namespaces/kube-system")
        return (body or {}).get("metadata", {}).get("uid")

    # --- deploy ---------------------------------------------------------------------

    def namespace_phase(self, namespace: str) -> str:
        """ "absent" | "Active" | "Terminating"."""
        body = self._get(f"/api/v1/namespaces/{namespace}")
        if body is None:
            return "absent"
        return str((body.get("status") or {}).get("phase") or "Active")

    def apply(
        self, namespace: str, import_id: str, objects: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Create or update every object; refuse anything not owned by this import."""
        check_objects(namespace, import_id, objects)
        self.verify()
        results: list[dict[str, str]] = []
        ns_obj = next(o for o in objects if o["kind"] == "Namespace")
        existing = self._get(f"/api/v1/namespaces/{namespace}")
        if existing is not None:
            if not owned(existing, import_id):
                raise OwnershipError(
                    f"Namespace {namespace} exists and was not created by this import; "
                    "nothing was changed"
                )
            if (existing.get("status") or {}).get("phase") == "Terminating":
                raise ProvisionerError(
                    f"Namespace {namespace} is still being removed; retry in a minute"
                )
        self._apply_one(ns_obj)
        results.append(
            {
                "kind": "Namespace",
                "name": namespace,
                "result": "updated" if existing else "created",
            }
        )
        self._bind_writer(namespace, import_id)
        for obj in objects:
            if obj["kind"] == "Namespace":
                continue
            prefix, plural, _ = RESOURCES[(obj["apiVersion"], obj["kind"])]
            name = obj["metadata"]["name"]
            path = f"{prefix}/namespaces/{namespace}/{plural}/{name}"
            current = self._get(path)
            if current is not None and not owned(current, import_id):
                raise OwnershipError(
                    f"{obj['kind']} {namespace}/{name} exists and was not created by this "
                    "import; stopped before changing it"
                )
            self._apply_one(obj)
            results.append(
                {
                    "kind": obj["kind"],
                    "name": name,
                    "result": "updated" if current else "created",
                }
            )
        return results

    def _bind_writer(self, namespace: str, import_id: str) -> None:
        """Give the provisioner write access inside this namespace only (create-only:
        it has no cluster-wide read of RoleBindings)."""
        labels = {
            "app.kubernetes.io/managed-by": "autoresilience",
            OWNER_LABEL: OWNER_VALUE,
            IMPORT_ID_LABEL: import_id,
        }
        body = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": WRITER_BINDING,
                "namespace": namespace,
                "labels": labels,
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": WRITER_ROLE,
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "autoresilience-provisioner",
                    "namespace": "autoresilience-system",
                }
            ],
        }
        try:
            self._call(
                "POST",
                f"/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/rolebindings",
                body=body,
            )
        except ProvisionerError as exc:
            if "409" not in str(exc):
                raise

    def _apply_one(self, obj: dict[str, Any]) -> None:
        prefix, plural, namespaced = RESOURCES[(obj["apiVersion"], obj["kind"])]
        meta = obj["metadata"]
        base = f"{prefix}/namespaces/{meta['namespace']}" if namespaced else prefix
        self._call(
            "PATCH",
            f"{base}/{plural}/{meta['name']}",
            body=obj,
            query=[("fieldManager", FIELD_MANAGER), ("force", "true")],
            content_type="application/apply-patch+yaml",
        )

    # --- remove ---------------------------------------------------------------------

    def remove(self, namespace: str, import_id: str) -> dict[str, Any]:
        """Delete the import's namespace (and so everything in it), if provably owned."""
        if not namespace.startswith(NAMESPACE_PREFIX):
            raise ProvisionerError(f"{namespace!r} is not an import namespace")
        self.verify()
        existing = self._get(f"/api/v1/namespaces/{namespace}")
        if existing is None:
            return {"namespace": "absent", "foreign": []}
        if not owned(existing, import_id):
            raise OwnershipError(
                f"Namespace {namespace} is not labelled as this import's; not deleting it"
            )
        foreign: list[str] = []
        for prefix, plural in MANAGED_PLURALS:
            body = self._get(f"{prefix}/namespaces/{namespace}/{plural}") or {}
            for item in body.get("items") or []:
                name = (item.get("metadata") or {}).get("name")
                if (plural, name) in BUILTIN or owned(item, import_id):
                    continue
                foreign.append(f"{plural}/{name}")
        if foreign:
            raise OwnershipError(
                f"Namespace {namespace} contains objects this import did not create ("
                + ", ".join(sorted(foreign)[:10])
                + "); remove them yourself, then retry"
            )
        self._call(
            "DELETE",
            f"/api/v1/namespaces/{namespace}",
            body={"propagationPolicy": "Background"},
        )
        return {"namespace": "deleting", "foreign": []}

    # --- HTTP ------------------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any] | None:
        try:
            return self._call("GET", path)
        except ProvisionerError as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise

    def _call(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: list[tuple[str, str]] | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        with _translate(method, path):
            api = self._client()
            response = api.call_api(
                path,
                method,
                query_params=query or [],
                header_params={
                    "Content-Type": content_type,
                    "Accept": "application/json",
                },
                body=body,
                auth_settings=["BearerToken"],
                _preload_content=False,
                _request_timeout=self._timeout,
            )
            data = response[0].data if isinstance(response, tuple) else response.data
            return json.loads(data) if data else {}

    def _client(self) -> Any:
        if not self._kubeconfig:
            raise ProvisionerUnavailableError(
                "No provisioner identity is configured (PROVISIONER_KUBECONFIG); "
                "imports can be reviewed but not deployed"
            )
        if self._api_client is None:
            self._api_client = config.new_client_from_config(
                config_file=self._kubeconfig, context=self._context
            )
        return self._api_client


class _StatusError(ProvisionerError):
    def __init__(self, message: str, status: int | None) -> None:
        super().__init__(message)
        self.status = status


@contextmanager
def _translate(method: str, path: str) -> Iterator[None]:
    try:
        yield
    except ApiException as exc:
        detail = ""
        try:
            detail = json.loads(exc.body or "{}").get("message", "")
        except (ValueError, AttributeError):
            pass
        raise _StatusError(
            f"Kubernetes refused {method} {path} ({exc.status}): {detail or exc.reason}"[
                :600
            ],
            exc.status,
        ) from exc
    except (ConfigException, FileNotFoundError) as exc:
        raise ProvisionerUnavailableError(
            f"The provisioner kubeconfig cannot be used: {exc}"
        ) from exc
    except (HTTPError, OSError) as exc:
        raise ProvisionerError(f"Kubernetes API unreachable: {exc}") from exc
