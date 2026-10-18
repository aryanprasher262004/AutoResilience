"""P7 imports: safe YAML, Compose and manifest parsing, security review, plans, health."""

import builtins
import json
import pathlib
from datetime import timedelta
from typing import Any

import pytest

from app.integrations.app_provisioner import (
    ImportProvisioner,
    OwnershipError,
    ProvisionerError,
    ProvisionerUnavailableError,
    check_objects,
)
from app.schemas.imports import ImportRequest
from app.services.imports.health import assess, verdict
from app.services.imports.plan import (
    IMPORT_ID_LABEL,
    LOADGEN_NAME,
    WORKLOAD_LABEL,
    preview,
)
from app.services.imports.safe_yaml import MAX_BYTES, YamlInputError, load_documents
from app.services.topology.graph import build_topology
from tests.import_fixtures import (
    COMPOSE,
    ENV_SECRET,
    REPO,
    RESILIENCEMART_COMPOSE,
    RESILIENCEMART_MANIFESTS,
    UNSAFE_COMPOSE,
    deployed,
)
from tests.topology_fixtures import OBSERVED_AT

IMAGE = "python:3.12.11-alpine3.22"
IMPORT_ID = "0e4c5f0e-0000-4000-8000-000000000001"


def run(content: str, kind: str = "compose", **extra: Any) -> Any:
    req = ImportRequest.model_validate(
        {
            "name": extra.pop("name", "shop"),
            "source": {"kind": kind, "content": content},
            **extra,
        }
    )
    return preview(req, import_id=extra.get("import_id"), loadgen_image=IMAGE)


def codes(result: Any, severity: str = "blocking") -> set[str]:
    return {f.code for f in result.findings if f.severity == severity}


def compose(service: str) -> str:
    return "services:\n  app:\n    image: nginx:1.27-alpine\n" + "".join(
        f"    {line}\n" for line in service.strip().splitlines()
    )


# --- safe YAML -------------------------------------------------------------------------


def test_aliases_are_refused_so_exponential_expansion_is_impossible() -> None:
    bomb = "a: &a [x, x]\nb: &b [*a, *a]\nc: [*b, *b]\n"
    with pytest.raises(YamlInputError, match="aliases"):
        load_documents(bomb)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("a: 1\na: 2\n", "Duplicate key"),
        ("<<: {a: 1}\n", "merge keys"),
        ("!!python/object/apply:os.system ['id']\n", "Unsupported YAML tag"),
        ("x: !reset []\n", "Unsupported YAML tag"),
        ("{1: a}\n", "Non-string"),
        ("a: [" * 40 + "]" * 40 + "\n", "Nesting"),
        ("a: b\0", "NUL"),
        ("a: [b\n", "Not valid YAML"),
    ],
)
def test_unsafe_or_ambiguous_yaml_is_refused(text: str, match: str) -> None:
    with pytest.raises(YamlInputError, match=match):
        load_documents(text)


def test_size_and_document_limits() -> None:
    with pytest.raises(YamlInputError, match="limited to"):
        load_documents("a: " + "x" * MAX_BYTES)
    with pytest.raises(YamlInputError, match="More than 2"):
        load_documents("a: 1\n---\nb: 2\n---\nc: 3\n", max_documents=2)


# --- Compose --------------------------------------------------------------------------


def test_supported_compose_becomes_workloads_services_and_declared_relations() -> None:
    result = run(COMPOSE)
    assert result.deployable, result.findings
    spec = result.spec
    web = next(w for w in spec.workloads if w.name == "web")
    assert (web.replicas, [p.container_port for p in web.ports]) == (2, [80])
    assert web.readiness.type == "tcp" and web.readiness.generated
    api = next(w for w in spec.workloads if w.name == "api")
    assert api.readiness.command == ["podcli", "check", "http", "localhost:9898/readyz"]
    assert api.args == ["./podinfo", "--port=9898"]
    assert [(s.name, s.ports[0].port) for s in spec.services] == [
        ("api", 9898),
        ("web", 80),
    ]
    # depends_on is recorded as declared, never as an observed or traffic relation.
    assert [(d.source, d.target, d.type) for d in spec.declared] == [
        ("web", "api", "depends_on")
    ]
    assert "host_port_not_published" in codes(result, "info")


def test_environment_values_are_never_kept_or_returned() -> None:
    result = run(COMPOSE)
    body = result.model_dump_json()
    assert ENV_SECRET not in body
    web = next(w for w in result.spec.workloads if w.name == "web")
    assert web.env_names == ["DB_PASSWORD", "MODE"]
    finding = next(f for f in result.findings if f.code == "environment_not_copied")
    assert "look like credentials" in (finding.hint or "")
    manifest = json.dumps(
        [o.manifest for o in result.plan.objects if o.group == "application"]
    )
    assert "DB_PASSWORD" not in manifest and '"env"' not in manifest


@pytest.mark.parametrize(
    ("service", "code"),
    [
        ("privileged: true", "unsupported_privileged"),
        ("cap_add: [SYS_ADMIN]", "unsupported_cap_add"),
        ("network_mode: host", "unsupported_network_mode"),
        ("pid: host", "unsupported_pid"),
        ("devices: ['/dev/sda:/dev/sda']", "unsupported_devices"),
        ("security_opt: ['seccomp:unconfined']", "unsupported_security_opt"),
        ("volumes: ['/etc:/host-etc']", "host_path_volume"),
        ("volumes: ['../../etc/passwd:/x']", "host_path_volume"),
        ("volumes: ['~/.ssh:/root/.ssh']", "host_path_volume"),
        ("volumes: ['/var/run/docker.sock:/var/run/docker.sock']", "docker_socket"),
        ("volumes: [{type: bind, source: ., target: /src}]", "host_path_volume"),
        ("secrets: [token]", "unsupported_secrets"),
        ("extends: {file: base.yaml, service: x}", "unsupported_extends"),
        ("ports: ['8000-8010:8000-8010']", "port_range"),
        ("ports: ['9000:8000-8010']", "port_range"),
        ("deploy: {replicas: 50}", "too_many_replicas"),
        ("deploy: {mode: global}", "unsupported_deploy_mode"),
        ("deploy: {resources: {limits: {memory: 8G}}}", "resource_out_of_bounds"),
        ("command: ['run', '${TOKEN}']", "unresolved_variable"),
        ("foo: bar", "unsupported_key"),
    ],
)
def test_dangerous_or_unsupported_compose_settings_block_deployment(
    service: str, code: str
) -> None:
    result = run(compose(service))
    assert code in codes(result)
    assert not result.deployable and result.plan is None


def test_referenced_files_are_never_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Any] = []
    real_open = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(
        pathlib.Path, "read_text", lambda *a, **k: pytest.fail("read_text")
    )
    result = run(
        compose(
            "env_file: [../../.env, /etc/shadow]\nvolumes: ['./secrets:/run/secrets']"
        )
        + "  other:\n    build: {context: ../.., dockerfile: Dockerfile}\n"
    )
    assert not result.deployable
    assert {"env_file_not_read"} <= codes(result, "warning")
    assert {"host_path_volume", "unsupported_build"} <= codes(result)
    assert not [
        f for f in opened if "env" in str(f) or "secret" in str(f) or "shadow" in str(f)
    ]


def test_build_with_an_image_uses_the_image_and_builds_nothing() -> None:
    result = run(compose("build: .\n"))
    assert result.deployable
    assert "build_ignored" in codes(result, "warning")


def test_named_volumes_become_empty_directories_with_a_warning() -> None:
    result = run(compose("volumes: ['data:/var/lib/data']") + "volumes:\n  data: {}\n")
    assert result.deployable
    assert "ephemeral_volume" in codes(result, "warning")
    workload = next(
        o for o in result.plan.objects if o.name == "app" and o.kind == "Deployment"
    )
    assert workload.manifest["spec"]["template"]["spec"]["volumes"] == [
        {"name": "vol-0", "emptyDir": {}}
    ]


def test_a_published_host_range_is_fine_since_nothing_is_published() -> None:
    result = run(compose("ports: ['127.0.0.1:8080-8082:80']"))
    assert result.deployable
    assert [p.container_port for p in result.spec.workloads[0].ports] == [80]
    assert "host_port_not_published" in codes(result, "info")


def test_string_commands_are_split_without_a_shell() -> None:
    result = run(compose("command: nginx -g 'daemon off;'"))
    assert result.spec.workloads[0].args == ["nginx", "-g", "daemon off;"]


def test_invalid_service_names_and_reserved_prefixes_are_refused() -> None:
    assert "invalid_name" in codes(
        run("services:\n  Web_App:\n    image: nginx:1.27\n")
    )
    assert "reserved_name" in codes(
        run("services:\n  autoresilience-x:\n    image: nginx:1.27\n")
    )


def test_unpinned_images_warn() -> None:
    assert "image_not_pinned" in codes(
        run("services:\n  a:\n    image: nginx\n"), "warning"
    )
    assert "image_not_pinned" in codes(
        run("services:\n  a:\n    image: nginx:latest\n"), "warning"
    )


def test_the_unsafe_example_is_refused_for_every_reason_it_shows() -> None:
    result = run(UNSAFE_COMPOSE)
    assert not result.deployable
    assert {
        "unsupported_privileged",
        "docker_socket",
        "host_path_volume",
        "unsupported_network_mode",
        "unsupported_build",
        "unsupported_cap_add",
        "unresolved_variable",
        "unsupported_secrets",
    } <= codes(result)


# --- manifests --------------------------------------------------------------------------

DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: api, namespace: production}
spec:
  replicas: 2
  selector: {matchLabels: {app: api}}
  template:
    metadata: {labels: {app: api}, annotations: {prometheus.io/scrape: "true"}}
    spec:
      containers:
        - name: api
          image: ghcr.io/stefanprodan/podinfo:6.7.1
          ports: [{containerPort: 9898}]
          env:
            - {name: TOKEN, valueFrom: {secretKeyRef: {name: s, key: k}}}
          %s
---
apiVersion: v1
kind: Service
metadata: {name: api}
spec:
  type: NodePort
  selector: {app: api}
  ports: [{port: 80, targetPort: 9898, nodePort: 30001}]
"""


def manifest(extra: str = "") -> str:
    return DEPLOYMENT % extra


def test_supported_manifests_are_normalized_not_applied_as_written() -> None:
    result = run(manifest(), kind="manifests")
    assert result.deployable, result.findings
    assert {"service_exposure_removed", "secret_reference_dropped"} <= codes(
        result, "warning"
    )
    assert {"namespace_replaced", "annotations_dropped"} <= codes(result, "info")
    objects = {(o.kind, o.name): o.manifest for o in result.plan.objects}
    svc = objects[("Service", "api")]
    assert svc["spec"]["type"] == "ClusterIP" and "nodePort" not in json.dumps(svc)
    pod = objects[("Deployment", "api")]["spec"]["template"]
    assert "annotations" not in pod["metadata"]  # cannot opt into scraping
    assert pod["spec"]["automountServiceAccountToken"] is False
    assert objects[("Deployment", "api")]["metadata"]["namespace"] == "ar-imp-shop"


@pytest.mark.parametrize(
    ("doc", "code"),
    [
        ("apiVersion: v1\nkind: Secret\nmetadata: {name: s}\n", "unsupported_kind"),
        ("apiVersion: v1\nkind: ConfigMap\nmetadata: {name: c}\n", "unsupported_kind"),
        (
            "apiVersion: apiextensions.k8s.io/v1\nkind: CustomResourceDefinition\nmetadata: {name: x}\n",
            "unsupported_kind",
        ),
        (
            "apiVersion: example.com/v1\nkind: Widget\nmetadata: {name: w}\n",
            "unsupported_kind",
        ),
        (
            "apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRoleBinding\nmetadata: {name: x}\n",
            "unsupported_kind",
        ),
        (
            "apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: j\n  annotations: {helm.sh/hook: pre-install}\n",
            "hook_annotation",
        ),
    ],
)
def test_unsupported_and_dangerous_kinds_are_refused(doc: str, code: str) -> None:
    result = run(manifest() + "---\n" + doc, kind="manifests")
    assert code in codes(result)
    assert not result.deployable


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ("securityContext: {privileged: true}", "unsafe_security_context"),
        ("securityContext: {allowPrivilegeEscalation: true}", "privilege_escalation"),
        ("securityContext: {capabilities: {add: [NET_ADMIN]}}", "added_capabilities"),
        (
            "readinessProbe: {httpGet: {host: 169.254.169.254, path: /, port: 80}}",
            "probe_host",
        ),
        ("lifecycleX: {}", "unsupported_field"),
    ],
)
def test_container_level_privileges_are_refused(extra: str, code: str) -> None:
    assert code in codes(run(manifest(extra), kind="manifests"))


@pytest.mark.parametrize(
    ("pod_extra", "code"),
    [
        ("hostNetwork: true", "unsafe_hostNetwork"),
        ("hostPID: true", "unsafe_hostPID"),
        ("nodeName: worker-1", "unsafe_nodeName"),
        ("volumes: [{name: h, hostPath: {path: /}}]", "unsafe_volume"),
        ("volumes: [{name: s, secret: {secretName: x}}]", "unsupported_volume"),
        ("initContainers: [{name: i, image: busybox:1.36}]", "unsafe_initContainers"),
    ],
)
def test_pod_level_host_access_is_refused(pod_extra: str, code: str) -> None:
    text = manifest().replace(
        "      containers:\n", f"      {pod_extra}\n      containers:\n", 1
    )
    assert code in codes(run(text, kind="manifests"))


def test_services_must_select_exactly_one_imported_workload() -> None:
    text = manifest().replace("selector: {app: api}", "selector: {app: other}")
    assert "service_selector_unmatched" in codes(run(text, kind="manifests"))


def test_selector_expressions_and_mismatches_are_refused() -> None:
    text = manifest().replace(
        "selector: {matchLabels: {app: api}}", "selector: {matchLabels: {app: x}}"
    )
    assert "selector_mismatch" in codes(run(text, kind="manifests"))


def test_persistent_volume_claim_templates_are_refused() -> None:
    sts = (
        manifest()
        .replace("kind: Deployment", "kind: StatefulSet")
        .replace(
            "  replicas: 2\n",
            "  replicas: 2\n  serviceName: api\n  volumeClaimTemplates: []\n",
            1,
        )
    )
    assert "persistent_storage" in codes(run(sts, kind="manifests"))


def test_resiliencemart_fixture_imports_in_both_formats() -> None:
    for kind, text in (
        ("compose", RESILIENCEMART_COMPOSE),
        ("manifests", RESILIENCEMART_MANIFESTS),
    ):
        result = run(text, kind=kind, name="resiliencemart")
        assert result.deployable, (
            kind,
            [f for f in result.findings if f.severity == "blocking"],
        )
        names = {w.name: w.replicas for w in result.spec.workloads}
        assert names == {"storefront": 3, "catalog": 2, "checkout": 2, "cache": 1}


# --- plans ------------------------------------------------------------------------------


def test_plans_are_deterministic_and_change_with_the_input() -> None:
    a, b = run(COMPOSE), run(COMPOSE)
    assert a.plan.digest == b.plan.digest
    assert a.plan.model_dump() == b.plan.model_dump()
    assert (
        run(COMPOSE.replace("replicas: 2", "replicas: 3")).plan.digest != a.plan.digest
    )


def test_every_object_is_owned_isolated_and_inside_the_import_namespace() -> None:
    result = run(
        COMPOSE,
        import_id=IMPORT_ID,
        traffic=[{"service": "api", "port": 9898, "path": "/version"}],
    )
    plan = result.plan
    assert plan.namespace == "ar-imp-shop"
    check_objects(plan.namespace, IMPORT_ID, [o.manifest for o in plan.objects])
    namespace = plan.objects[0].manifest
    assert (
        namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"]
        == "baseline"
    )
    kinds = {o.kind for o in plan.objects}
    assert {"ResourceQuota", "LimitRange", "NetworkPolicy", "ChaosExperiment"} <= kinds
    assert not kinds & {
        "Secret",
        "ClusterRole",
        "ClusterRoleBinding",
        "Role",
        "Ingress",
    }
    for o in plan.objects:
        if o.kind in ("Deployment", "StatefulSet"):
            pod = o.manifest["spec"]["template"]
            assert pod["metadata"]["labels"][IMPORT_ID_LABEL] == IMPORT_ID
            assert pod["metadata"]["labels"][WORKLOAD_LABEL] == o.name
            container = pod["spec"]["containers"][0]
            assert container["securityContext"]["allowPrivilegeEscalation"] is False
            assert container["resources"]["limits"]["memory"]
            if o.name != LOADGEN_NAME:
                assert "annotations" not in pod["metadata"]
    quota = next(o for o in plan.objects if o.kind == "ResourceQuota").manifest
    assert quota["spec"]["hard"]["services.nodeports"] == "0"


def test_the_load_generator_only_targets_approved_endpoints_in_the_namespace() -> None:
    result = run(
        COMPOSE, traffic=[{"service": "api", "port": 9898, "path": "/version"}]
    )
    loadgen = next(o for o in result.plan.objects if o.name == LOADGEN_NAME).manifest
    env = {
        e["name"]: e["value"]
        for e in loadgen["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert (
        env["TARGETS"]
        == "ar-imp-shop/api=http://api.ar-imp-shop.svc.cluster.local:9898/version"
    )
    assert env["ALLOWED_HOST_SUFFIX"] == ".ar-imp-shop.svc.cluster.local"


@pytest.mark.parametrize(
    "target",
    [
        {"service": "kubernetes", "port": 443, "path": "/"},
        {"service": "api", "port": 22, "path": "/"},
        {"service": "web", "port": 80, "path": "/"},  # web exposes 80, ok
    ],
)
def test_traffic_targets_outside_the_import_are_refused(target: dict[str, Any]) -> None:
    result = run(COMPOSE, traffic=[target])
    if target["service"] == "web":
        assert result.deployable
    else:
        assert "invalid_traffic_target" in codes(result)


@pytest.mark.parametrize(
    "path",
    [
        "http://169.254.169.254/",
        "/../../x",
        "/a?b=c",
        "/a#x",
        "//evil.example/",
        "/@x:y",
        "x",
    ],
)
def test_traffic_paths_cannot_carry_a_host_or_traversal(path: str) -> None:
    with pytest.raises(ValueError):
        ImportRequest.model_validate(
            {
                "name": "shop",
                "source": {"kind": "image", "image": {"image": "nginx:1.27"}},
                "traffic": [{"service": "x", "port": 80, "path": path}],
            }
        )


def test_import_names_and_filenames_are_sanitized() -> None:
    with pytest.raises(ValueError):
        ImportRequest.model_validate(
            {"name": "../etc", "source": {"kind": "compose", "content": "a: 1"}}
        )
    req = ImportRequest.model_validate(
        {
            "name": "shop",
            "source": {
                "kind": "compose",
                "content": "a: 1",
                "filename": "../../etc/passwd",
            },
        }
    )
    assert req.source.filename == "passwd"


def test_single_image_import() -> None:
    req = ImportRequest.model_validate(
        {
            "name": "hello",
            "source": {
                "kind": "image",
                "image": {"image": "nginx:1.27-alpine", "port": 80},
            },
        }
    )
    result = preview(req, import_id=None, loadgen_image=IMAGE)
    assert result.deployable and result.plan is not None
    assert [
        (o.kind, o.name) for o in result.plan.objects if o.group == "application"
    ] == [
        ("Deployment", "hello"),
        ("Service", "hello"),
    ]


def test_vendored_assets_match_their_sources() -> None:
    assets = REPO / "apps/api/app/services/imports/assets"
    assert (assets / "pod-delete.yaml").read_text() == (
        REPO / "chaos/templates/pod-delete.yaml"
    ).read_text()
    assert (assets / "loadgen.py").read_text() == (
        REPO / "infra/sample-app/loadgen/loadgen.py"
    ).read_text()


def test_loadgen_image_matches_versions_env() -> None:
    env = (REPO / "infra/versions.env").read_text()
    assert f"LOADGEN_IMAGE={IMAGE}" in env


# --- provisioner allowlist ----------------------------------------------------------------


def plan_objects(**extra: Any) -> list[dict[str, Any]]:
    result = run(COMPOSE, import_id=IMPORT_ID, **extra)
    return [o.manifest for o in result.plan.objects]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda o: o.append(
                {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "x"}}
            ),
            "not allowed",
        ),
        (lambda o: o[-1]["metadata"].update(namespace="shop"), "outside"),
        (
            lambda o: o[-1]["metadata"]["labels"].update({IMPORT_ID_LABEL: "other"}),
            "ownership",
        ),
        (
            lambda o: next(x for x in o if x["kind"] == "RoleBinding")[
                "roleRef"
            ].update(name="cluster-admin"),
            "role that is not allowed",
        ),
        (
            lambda o: next(x for x in o if x["kind"] == "Service")["spec"].update(
                type="NodePort"
            ),
            "ClusterIP",
        ),
    ],
)
def test_the_provisioner_refuses_anything_a_plan_would_never_contain(
    mutate: Any, match: str
) -> None:
    objects = plan_objects()
    mutate(objects)
    with pytest.raises(ProvisionerError, match=match):
        check_objects("ar-imp-shop", IMPORT_ID, objects)
    with pytest.raises(ProvisionerError, match="not an import namespace"):
        check_objects("shop", IMPORT_ID, plan_objects())


class FakeHTTP(ImportProvisioner):
    """ImportProvisioner with its HTTP layer replaced: GET answers from `objects`."""

    def __init__(self, objects: dict[str, dict[str, Any]], user: str) -> None:
        super().__init__("kubeconfig", None, 1.0)
        self.objects = objects
        self.user = user
        self.calls: list[tuple[str, str]] = []

    def _call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:  # type: ignore[override]
        self.calls.append((method, path))
        if path.endswith("selfsubjectreviews"):
            return {"status": {"userInfo": {"username": self.user}}}
        if method == "GET":
            if path in self.objects:
                return self.objects[path]
            from app.integrations.app_provisioner import _StatusError

            raise _StatusError("not found", 404)
        return {}


PROVISIONER = "system:serviceaccount:autoresilience-system:autoresilience-provisioner"


def test_an_admin_credential_is_refused_as_provisioner() -> None:
    fake = FakeHTTP({}, "kubernetes-admin")
    with pytest.raises(ProvisionerUnavailableError, match="not the dedicated"):
        fake.apply("ar-imp-shop", IMPORT_ID, plan_objects())
    assert not [c for c in fake.calls if c[0] in ("PATCH", "DELETE")]


def test_apply_never_touches_a_namespace_or_object_it_does_not_own() -> None:
    foreign_ns: dict[str, dict[str, Any]] = {
        "/api/v1/namespaces/ar-imp-shop": {"metadata": {"labels": {}}}
    }
    fake = FakeHTTP(foreign_ns, PROVISIONER)
    with pytest.raises(OwnershipError):
        fake.apply("ar-imp-shop", IMPORT_ID, plan_objects())
    assert not [c for c in fake.calls if c[0] != "GET" and "selfsubject" not in c[1]]

    ours = {
        "metadata": {
            "labels": {"autoresilience.io/owner": "import", IMPORT_ID_LABEL: IMPORT_ID}
        }
    }
    existing = {
        "/api/v1/namespaces/ar-imp-shop": ours,
        "/apis/apps/v1/namespaces/ar-imp-shop/deployments/web": {
            "metadata": {"labels": {"app": "web"}}
        },
    }
    fake = FakeHTTP(existing, PROVISIONER)
    with pytest.raises(OwnershipError, match="Deployment ar-imp-shop/web"):
        fake.apply("ar-imp-shop", IMPORT_ID, plan_objects())
    patched = [p for m, p in fake.calls if m == "PATCH"]
    assert not any(p.endswith("/deployments/web") for p in patched)


def test_removal_requires_ownership_and_no_foreign_objects() -> None:
    ours = {
        "metadata": {
            "labels": {"autoresilience.io/owner": "import", IMPORT_ID_LABEL: IMPORT_ID}
        }
    }
    base: dict[str, dict[str, Any]] = {"/api/v1/namespaces/ar-imp-shop": ours}
    foreign: dict[str, dict[str, Any]] = {
        **base,
        "/apis/apps/v1/namespaces/ar-imp-shop/deployments": {
            "items": [
                ours | {"metadata": {**ours["metadata"], "name": "web"}},
                {"metadata": {"name": "intruder"}},
            ]
        },
    }
    fake = FakeHTTP(foreign, PROVISIONER)
    with pytest.raises(OwnershipError, match="deployments/intruder"):
        fake.remove("ar-imp-shop", IMPORT_ID)
    assert not [c for c in fake.calls if c[0] == "DELETE"]

    fake = FakeHTTP(base, PROVISIONER)
    assert fake.remove("ar-imp-shop", IMPORT_ID)["namespace"] == "deleting"
    assert ("DELETE", "/api/v1/namespaces/ar-imp-shop") in fake.calls
    with pytest.raises(ProvisionerError, match="not an import namespace"):
        fake.remove("shop", IMPORT_ID)
    assert (
        FakeHTTP({}, PROVISIONER).remove("ar-imp-shop", IMPORT_ID)["namespace"]
        == "absent"
    )


# --- health ---------------------------------------------------------------------------------


def topology_of(snapshot: Any, namespace: str) -> dict[str, Any]:
    return build_topology(
        snapshot,
        namespaces=[namespace],
        excluded=frozenset(),
        cluster={
            "context": "kind",
            "role": "execution",
            "chaos_permitted": True,
            "namespaces": None,
        },
    )


@pytest.mark.parametrize(
    ("kwargs", "state"),
    [
        ({}, "READY"),
        ({"ready": False}, "PROGRESSING"),
        ({"reason": "ImagePullBackOff"}, "IMAGE_PULL_FAILED"),
        ({"reason": "CrashLoopBackOff"}, "CRASH_LOOP"),
        ({"reason": "CreateContainerConfigError"}, "CONFIG_ERROR"),
        ({"only": {"api"}}, "MISSING"),
    ],
)
def test_health_comes_from_controller_and_pod_status(
    kwargs: dict[str, Any], state: str
) -> None:
    plan = run(COMPOSE).plan
    assessment = assess(plan, topology_of(deployed(plan, **kwargs), plan.namespace))
    web = next(w for w in assessment.workloads if w.name == "web")
    assert web.state == state
    assert assessment.ready is (state == "READY")


def test_a_failure_must_persist_before_it_is_a_verdict() -> None:
    plan = run(COMPOSE).plan
    failing = assess(
        plan, topology_of(deployed(plan, reason="ErrImagePull"), plan.namespace)
    )
    start = OBSERVED_AT
    assert verdict(failing, start, start, start + timedelta(seconds=10), 300) == (
        "DEPLOYING",
        None,
    )
    assert verdict(failing, start, start, start + timedelta(seconds=60), 300) == (
        "FAILED",
        "IMAGE_PULL_FAILED",
    )
    slow = assess(plan, topology_of(deployed(plan, ready=False), plan.namespace))
    assert verdict(slow, start, None, start + timedelta(seconds=301), 300) == (
        "FAILED",
        "PROGRESSING",
    )
