import base64
import json
import tempfile
import unittest
from pathlib import Path

from ar_cli import cluster, imports
from ar_cli.paths import load_versions

from .fakes import ROOT, FakeRunner, fail, ok, paths

VERSIONS = load_versions(paths(ROOT))
CTX = "kind-staging"
K = ["kubectl", "--context", CTX]
CA = base64.b64encode(b"ca").decode()


def kubeconfig_view(server: str = "https://127.0.0.1:52011", ca: str | None = CA) -> str:
    cluster_entry: dict[str, object] = {"server": server}
    if ca:
        cluster_entry["certificate-authority-data"] = ca
    return json.dumps(
        {
            "clusters": [{"name": CTX, "cluster": cluster_entry}],
            # The operator's credentials: read by kubectl, never kept.
            "users": [{"name": CTX, "user": {"client-key-data": "operator-secret-key"}}],
        }
    )


def staging_runner(namespace_json: str = "") -> FakeRunner:
    runner = FakeRunner()
    runner.on("kubectl", "config", "get-contexts", answer=ok(f"kind-autoresilience\n{CTX}\nminikube\n"))
    runner.on(*K, "get", "namespace", "kube-system", answer=ok("uid-staging"))
    runner.on(*K, "get", "namespace", "shop", answer=ok("namespace/shop"))
    runner.on(*K, "get", "namespace", "autoresilience-system", answer=ok(namespace_json))
    runner.on("kubectl", "config", "view", answer=ok(kubeconfig_view()))
    token = base64.b64encode(b"viewer-token").decode()
    runner.on(*K, "-n", "autoresilience-system", "get", "secret", answer=ok(json.dumps({"data": {"token": token}})))
    return runner


class ValidationTests(unittest.TestCase):
    def test_refuses_the_stack_cluster_system_namespaces_and_bad_names(self) -> None:
        cases = [
            ("kind-autoresilience", ["shop"], "stack's own cluster"),
            (CTX, [], "at least one namespace"),
            (CTX, ["kube-system"], "system namespace"),
            (CTX, ["autoresilience-system"], "system namespace"),
            (CTX, ["Not_OK"], "not a namespace name"),
            ("bad context", ["shop"], "not a valid context name"),
        ]
        for context, namespaces, message in cases:
            with (
                self.subTest(context=context, namespaces=namespaces),
                self.assertRaisesRegex(imports.ImportRefused, message),
            ):
                imports.validate(VERSIONS, context, namespaces)

    def test_unknown_context_is_refused_before_any_cluster_call(self) -> None:
        runner = staging_runner()
        with self.assertRaisesRegex(imports.ImportRefused, "No context"):
            imports.plan(runner, VERSIONS, "kind-prod", ["shop"], False)
        self.assertFalse([c for c in runner.calls if "--context" in c])

    def test_missing_namespace_is_refused(self) -> None:
        runner = staging_runner()
        runner.on(*K, "get", "namespace", "shop", answer=fail("NotFound"))
        with self.assertRaisesRegex(imports.ImportRefused, "does not exist"):
            imports.plan(runner, VERSIONS, CTX, ["shop"], False)

    def test_foreign_identity_namespace_is_refused(self) -> None:
        foreign = json.dumps({"metadata": {"labels": {"team": "payments"}}})
        with self.assertRaisesRegex(imports.ImportRefused, "not created by AutoResilience"):
            imports.plan(staging_runner(foreign), VERSIONS, CTX, ["shop"], False)

    def test_clusters_without_a_ca_are_refused(self) -> None:
        runner = staging_runner()
        runner.on("kubectl", "config", "view", answer=ok(kubeconfig_view(ca=None)))
        with self.assertRaisesRegex(imports.ImportRefused, "CA certificate"):
            imports.plan(runner, VERSIONS, CTX, ["shop"], False)


class ServerTests(unittest.TestCase):
    def test_engine_reaches_kind_through_the_docker_network(self) -> None:
        self.assertEqual(imports.engine_server(CTX, "https://127.0.0.1:52011"), "https://staging-control-plane:6443")
        self.assertEqual(imports.engine_server("eks", "https://abc.eks.amazonaws.com"), "https://abc.eks.amazonaws.com")

    def test_other_loopback_servers_are_unreachable_from_the_container(self) -> None:
        for server in ("https://127.0.0.1:8443", "https://localhost:6443", "https://[::1]:6443"):
            with self.subTest(server=server), self.assertRaisesRegex(imports.ImportRefused, "cannot reach"):
                imports.engine_server("minikube", server)


class ApplyTests(unittest.TestCase):
    def test_plan_is_read_only_and_keeps_no_operator_credentials(self) -> None:
        runner = staging_runner()
        p = imports.plan(runner, VERSIONS, CTX, ["shop", "shop"], include_nodes=False)
        self.assertEqual(runner.writes(), [])
        self.assertEqual((p.namespaces, p.cluster_uid, p.create_namespace), (["shop"], "uid-staging", True))
        self.assertEqual(p.server, "https://staging-control-plane:6443")
        self.assertNotIn("operator-secret-key", repr(p))

    def test_apply_writes_only_repository_manifests_with_the_explicit_context(self) -> None:
        runner = staging_runner()
        p = imports.plan(runner, VERSIONS, CTX, ["shop"], include_nodes=True)
        runner.calls.clear()
        runner.inputs.clear()
        imports.apply(runner, paths(ROOT), p)
        writes = [c for c in runner.calls if "apply" in c]
        self.assertEqual(len(writes), 4)  # namespace, identity, role in shop, nodes
        for argv, data in zip(runner.calls, runner.inputs, strict=True):
            if argv[0] == "kubectl":
                self.assertEqual(argv[:3], K)
            if "apply" in argv and argv[-1] != "-":
                self.assertTrue(Path(argv[-1]).is_relative_to(ROOT / "infra" / "rbac"))
            if data:
                self.assertIn("namespace: shop", data.decode())
                self.assertNotIn("secrets", data.decode())

    def test_existing_owned_namespace_is_not_reapplied(self) -> None:
        owned = json.dumps(
            {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/managed-by": "autoresilience",
                        "autoresilience.io/owner": "local-manager",
                    }
                }
            }
        )
        runner = staging_runner(owned)
        p = imports.plan(runner, VERSIONS, CTX, ["shop"], include_nodes=False)
        self.assertFalse(p.create_namespace)
        imports.apply(runner, paths(ROOT), p)
        self.assertFalse(any("viewer-namespace.yaml" in a for c in runner.calls for a in c))

    def test_apply_refuses_when_the_context_changed_clusters(self) -> None:
        runner = staging_runner()
        p = imports.plan(runner, VERSIONS, CTX, ["shop"], include_nodes=False)
        runner.on(*K, "get", "namespace", "kube-system", answer=ok("uid-other"))
        runner.calls.clear()
        with self.assertRaises(cluster.OwnershipError):
            imports.apply(runner, paths(ROOT), p)
        self.assertEqual(runner.writes(), [])

    def test_permission_check_expects_reads_only_in_shared_namespaces(self) -> None:
        runner = staging_runner()
        p = imports.plan(runner, VERSIONS, CTX, ["shop"], include_nodes=False)
        expected = imports.expected_permissions(p)
        denied = {(e.verb, e.resource, e.namespace) for e in expected if not e.expected}
        self.assertIn(("get", "secrets", "shop"), denied)
        self.assertIn(("create", "chaosengines.litmuschaos.io", "shop"), denied)
        self.assertIn(("list", "pods", None), denied)
        self.assertIn(("list", "nodes", None), denied)
        imports.check_permissions(runner, p)
        for argv in runner.calls[-len(expected) :]:
            self.assertEqual(argv[-2:], ["--as", imports.VIEWER_USER])


class RevokeTests(unittest.TestCase):
    def record(self, created: bool = True) -> imports.ImportRecord:
        return imports.ImportRecord(CTX, ["shop", "web"], True, "uid-staging", "https://x:6443", created, "t")

    def test_revoke_deletes_only_labelled_viewer_objects(self) -> None:
        runner = staging_runner()
        imports.revoke(runner, self.record())
        deletes = [c for c in runner.calls if "delete" in c]
        self.assertEqual(len(deletes), 5)  # 2 namespaces' roles, cluster role, identity, namespace
        for argv in deletes:
            self.assertEqual(argv[:3], K)
            self.assertEqual(argv[argv.index("-l") + 1], imports.VIEWER_SELECTOR)
            self.assertIn("--ignore-not-found", argv)

    def test_revoke_keeps_a_namespace_it_did_not_create(self) -> None:
        runner = staging_runner()
        imports.revoke(runner, self.record(created=False))
        self.assertFalse([c for c in runner.calls if c[3:5] == ["delete", "namespace"]])

    def test_revoke_refuses_when_the_context_points_elsewhere(self) -> None:
        runner = staging_runner()
        runner.on(*K, "get", "namespace", "kube-system", answer=ok("uid-other"))
        with self.assertRaisesRegex(cluster.OwnershipError, "different cluster"):
            imports.revoke(runner, self.record())
        self.assertEqual(runner.writes(), [])


class KubeconfigTests(unittest.TestCase):
    def test_imported_entries_are_kept_and_carry_only_the_viewer_token(self) -> None:
        runner = FakeRunner()
        secret = {"data": {"token": base64.b64encode(b"engine").decode(), "ca.crt": "Q0EK"}}
        runner.on(
            "kubectl",
            "--context",
            "kind-autoresilience",
            "-n",
            "autoresilience-system",
            "get",
            "secret",
            answer=ok(json.dumps(secret)),
        )
        entry = cluster.KubeconfigEntry(
            CTX, f"autoresilience-viewer@{CTX}", "https://staging-control-plane:6443", CA, "v"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            self.assertTrue(cluster.write_engine_kubeconfig(runner, p, VERSIONS, add=[entry]))
            self.assertFalse(cluster.write_engine_kubeconfig(runner, p, VERSIONS, imported=[CTX]))
            kept = cluster.kubeconfig_entries(p.kubeconfig)
            self.assertEqual(set(kept), {"kind-autoresilience", CTX})
            self.assertEqual(kept[CTX], entry)
            # Dropping the import from the list removes it.
            self.assertTrue(cluster.write_engine_kubeconfig(runner, p, VERSIONS))
            self.assertEqual(set(cluster.kubeconfig_entries(p.kubeconfig)), {"kind-autoresilience"})
            config = json.loads(p.kubeconfig.read_text())
        self.assertEqual(config["current-context"], "kind-autoresilience")

    def test_discovery_setting_is_compact_json(self) -> None:
        r = imports.ImportRecord(CTX, ["shop"], False, "u", "s", True, "t")
        self.assertEqual(imports.discovery_setting([r]), '[{"context":"kind-staging","namespaces":["shop"]}]')
        self.assertEqual(imports.discovery_setting([]), "[]")
