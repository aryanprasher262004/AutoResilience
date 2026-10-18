import base64
import json
import tempfile
import unittest
from pathlib import Path

from ar_cli import cluster
from ar_cli.paths import OWNER_SELECTOR, load_versions

from .fakes import ROOT, FakeRunner, fail, ok, paths

VERSIONS = load_versions(paths(ROOT))
CONTEXT = ["kubectl", "--context", "kind-autoresilience"]


def owned_runner() -> FakeRunner:
    runner = FakeRunner()
    runner.on("kubectl", "--context", "kind-autoresilience", "get", "nodes", answer=ok("autoresilience-control-plane"))
    return runner


class OwnershipTests(unittest.TestCase):
    def test_refuses_a_context_that_points_elsewhere(self) -> None:
        for nodes in ("minikube", "autoresilience-control-plane other-node", ""):
            runner = FakeRunner()
            runner.on(*CONTEXT, "get", "nodes", answer=ok(nodes))
            with self.subTest(nodes=nodes), self.assertRaises(cluster.OwnershipError):
                cluster.verify_owned(runner, VERSIONS)

    def test_unreachable_context_says_how_to_recover(self) -> None:
        runner = FakeRunner()
        runner.on(*CONTEXT, "get", "nodes", answer=fail("connection refused"))
        with self.assertRaisesRegex(cluster.OwnershipError, "ar start"):
            cluster.verify_owned(runner, VERSIONS)

    def test_provision_stops_before_any_write_when_not_owned(self) -> None:
        runner = FakeRunner()
        runner.on(*CONTEXT, "get", "nodes", answer=ok("someone-elses-node"))
        with self.assertRaises(cluster.OwnershipError):
            cluster.provision(runner, paths(ROOT), VERSIONS, lambda _: None)
        self.assertEqual(runner.writes(), [])

    def test_start_node_only_restarts_the_labelled_kind_node(self) -> None:
        runner = FakeRunner()
        runner.on("docker", "inspect", answer=ok("other\n"))
        with self.assertRaises(cluster.OwnershipError):
            cluster.start_node(runner, VERSIONS)
        runner.on("docker", "inspect", answer=ok("autoresilience\n"))
        cluster.start_node(runner, VERSIONS)
        self.assertEqual(runner.calls[-1], ["docker", "start", "autoresilience-control-plane"])


class ProvisionTests(unittest.TestCase):
    def test_every_cluster_write_uses_the_explicit_context(self) -> None:
        runner = owned_runner()
        cluster.provision(runner, paths(ROOT), VERSIONS, lambda _: None)
        cluster.grant_engine_access(runner, paths(ROOT), VERSIONS)

        for argv in runner.calls:
            if argv[0] == "kubectl":
                self.assertEqual(argv[:3], CONTEXT, argv)
            if argv[0] == "helm" and argv[1] == "upgrade":
                self.assertIn("--kube-context", argv)
                self.assertEqual(argv[argv.index("--kube-context") + 1], "kind-autoresilience")
            self.assertIn(argv[0], {"kubectl", "helm", "docker"}, argv)

    def test_uses_pinned_versions_and_repository_manifests(self) -> None:
        runner = owned_runner()
        cluster.provision(runner, paths(ROOT), VERSIONS, lambda _: None)

        helm = [c for c in runner.calls if c[:2] == ["helm", "upgrade"]]
        self.assertEqual([c[c.index("--version") + 1] for c in helm], ["29.35.0", "3.31.1"])
        applied = [Path(c[c.index("-f") + 1]) for c in runner.calls if "apply" in c and c[c.index("-f") + 1] != "-"]
        for manifest in applied:
            self.assertTrue(manifest.is_relative_to(ROOT) and manifest.exists(), manifest)

    def test_chaos_rbac_is_retargeted_per_namespace(self) -> None:
        runner = owned_runner()
        cluster.provision(runner, paths(ROOT), VERSIONS, lambda _: None)
        piped = [i.decode() for c, i in zip(runner.calls, runner.inputs) if i and "kind: Role" in i.decode()]
        self.assertEqual(len(piped), 2)
        self.assertIn("namespace: resilience-sandbox", piped[1])
        self.assertNotIn("namespace: shop\n", piped[1])

    def test_for_namespace_only_rewrites_whole_namespace_lines(self) -> None:
        text = "metadata:\n  namespace: shop\n  name: shopkeeper\n    namespace: shop-x\n"
        self.assertEqual(
            cluster.for_namespace(text, "sandbox"),
            "metadata:\n  namespace: sandbox\n  name: shopkeeper\n    namespace: shop-x\n",
        )


class EngineAccessTests(unittest.TestCase):
    def test_kubeconfig_has_only_the_service_account_token(self) -> None:
        runner = owned_runner()
        secret = {"data": {"token": base64.b64encode(b"tok-123").decode(), "ca.crt": "Q0EK"}}
        runner.on(*CONTEXT, "-n", "autoresilience-system", "get", "secret", answer=ok(json.dumps(secret)))

        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            cluster.write_engine_kubeconfig(runner, p, VERSIONS)
            config = json.loads(p.kubeconfig.read_text())
            mode = p.kubeconfig.stat().st_mode & 0o777

        self.assertEqual(mode, 0o600)
        self.assertEqual(config["current-context"], "kind-autoresilience")
        self.assertEqual(
            config["clusters"][0]["cluster"],
            {"server": "https://autoresilience-control-plane:6443", "certificate-authority-data": "Q0EK"},
        )
        self.assertEqual(config["users"], [{"name": "autoresilience-engine", "user": {"token": "tok-123"}}])

    def test_waits_for_the_token_controller(self) -> None:
        runner = FakeRunner()
        answers = [ok(json.dumps({"data": {}})), ok(json.dumps({"data": {"token": "dA==", "ca.crt": "Yw=="}}))]
        runner.on(*CONTEXT, "-n", "autoresilience-system", "get", "secret", answer=lambda argv, _: answers.pop(0))
        self.assertEqual(cluster.read_token(runner, VERSIONS, sleep=lambda _: None), ("t", "Yw=="))

    def test_permission_check_impersonates_the_engine(self) -> None:
        runner = FakeRunner()
        allowed = {p.verb + p.resource + str(p.namespace) for p in cluster.expected_permissions(VERSIONS) if p.expected}

        def can_i(argv: list[str], _: bytes | None) -> object:
            ns = None if "--all-namespaces" in argv else argv[argv.index("-n") + 1]
            return ok("yes" if argv[5] + argv[6] + str(ns) in allowed else "no")

        runner.on(*CONTEXT, "auth", "can-i", answer=can_i)  # type: ignore[arg-type]
        results = cluster.check_engine_permissions(runner, VERSIONS)

        self.assertTrue(all(actual == p.expected for p, actual in results))
        self.assertTrue(any(not p.expected and p.resource == "secrets" for p, _ in results))
        for argv in runner.calls:
            self.assertEqual(argv[-2:], ["--as", "system:serviceaccount:autoresilience-system:autoresilience-engine"])

    def test_revoke_deletes_only_label_selected_objects(self) -> None:
        runner = owned_runner()
        cluster.revoke_engine_access(runner, VERSIONS)
        deletes = [c for c in runner.calls if "delete" in c]
        self.assertEqual(len(deletes), 4)
        for argv in deletes:
            self.assertEqual(argv[argv.index("-l") + 1], OWNER_SELECTOR)
            self.assertIn("--ignore-not-found", argv)


class NamespaceWaitTests(unittest.TestCase):
    def test_grant_waits_while_the_engine_namespace_terminates(self) -> None:
        runner = owned_runner()
        phases = [ok("Terminating"), ok("Terminating"), ok("")]
        runner.on(*CONTEXT, "get", "namespace", answer=lambda argv, _: phases.pop(0))
        cluster.wait_namespace_gone_or_active(runner, VERSIONS, sleep=lambda _: None)
        self.assertEqual(phases, [])
