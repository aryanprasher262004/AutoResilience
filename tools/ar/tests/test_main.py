import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ar_cli import main as cli
from ar_cli.state import State, load, save

from .fakes import TTY, FakeRunner, NoTTY, fail, ok, paths

DOCKER_INFO = json.dumps({"ServerVersion": "29.3.1", "NCPU": 8, "MemTotal": 8 * 1024**3})


def healthy_runner(cluster_exists: bool = True) -> FakeRunner:
    runner = FakeRunner()
    runner.on("docker", "info", answer=ok(DOCKER_INFO))
    runner.on("docker", "compose", "version", answer=ok("2.40.0"))
    runner.on("kind", "version", answer=ok("kind v0.33.0"))
    runner.on("kubectl", "version", answer=ok("Client Version: v1.35.3"))
    runner.on("helm", "version", answer=ok("v3.19.0"))
    runner.on("kind", "get", "clusters", answer=ok("autoresilience\n" if cluster_exists else ""))
    runner.on("docker", "inspect", answer=ok("true"))
    return runner


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = paths(Path(self.tmp.name))
        patcher = mock.patch("ar_cli.checks.port_in_use", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, runner: FakeRunner, *argv: str, stdin: io.StringIO | None = None) -> tuple[int, str]:
        out = io.StringIO()
        code = cli.main(list(argv), runner=runner, paths=self.paths, out=out, stdin=stdin or NoTTY())
        return code, out.getvalue()


class InstallTests(Harness):
    def test_without_confirmation_nothing_is_changed(self) -> None:
        runner = healthy_runner(cluster_exists=False)
        code, out = self.run_cli(runner, "install")

        self.assertEqual(code, cli.EXIT_DECLINED)
        self.assertIn("create the kind cluster 'autoresilience'", out)
        self.assertIn("rerun with --yes", out)
        self.assertEqual(runner.writes(), [])
        self.assertIsNone(load(self.paths.state))

    def test_interactive_no_changes_nothing(self) -> None:
        runner = healthy_runner(cluster_exists=False)
        code, _ = self.run_cli(runner, "install", stdin=TTY("n\n"))
        self.assertEqual(code, cli.EXIT_DECLINED)
        self.assertEqual(runner.writes(), [])

    def test_blocking_findings_abort_before_the_plan(self) -> None:
        runner = healthy_runner()
        runner.tools.discard("helm")
        code, out = self.run_cli(runner, "--yes", "install")
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("nothing was changed", out)
        self.assertEqual(runner.writes(), [])

    def test_existing_cluster_needs_its_own_confirmation_and_is_recorded_as_adopted(self) -> None:
        runner = healthy_runner(cluster_exists=True)
        code, out = self.run_cli(runner, "install", stdin=TTY("y\nn\n"))
        self.assertEqual(code, cli.EXIT_DECLINED)
        self.assertIn("not created by this tool", out)
        self.assertEqual(runner.writes(), [])

    def test_port_flags_are_validated(self) -> None:
        code, out = self.run_cli(healthy_runner(), "install", "--web-port", "80")
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("between 1024 and 65535", out)


class UninstallTests(Harness):
    def installed(self, created_by_ar: bool) -> None:
        save(self.paths.state, State(cluster_name="autoresilience", cluster_created_by_ar=created_by_ar))
        self.paths.stack_env.write_text("AUTORESILIENCE_DB_PASSWORD=x\n")
        self.paths.kubeconfig.write_text("{}")

    def runner(self) -> FakeRunner:
        runner = healthy_runner()
        runner.on(
            "kubectl", "--context", "kind-autoresilience", "get", "nodes", answer=ok("autoresilience-control-plane")
        )
        runner.on(
            "ps",
            "-a",
            "--format",
            "json",
            answer=ok(json.dumps({"Service": "postgres", "State": "running", "Health": "healthy", "ExitCode": 0})),
        )
        runner.on("exec", "-T", "postgres", "pg_dump", answer=ok(b"PGDMP dump"))
        return runner

    def test_default_keeps_data_and_cluster_but_revokes_engine_access(self) -> None:
        self.installed(created_by_ar=True)
        runner = self.runner()
        code, out = self.run_cli(runner, "--yes", "uninstall")

        self.assertEqual(code, cli.EXIT_OK, out)
        flat = [" ".join(c) for c in runner.calls]
        self.assertFalse(any("volume rm" in c for c in flat))
        self.assertFalse(any(c.startswith("kind delete") for c in flat))
        self.assertTrue(any("delete namespace -l" in c for c in flat))
        self.assertTrue(self.paths.stack_env.exists())  # the kept volume's password
        self.assertFalse(self.paths.kubeconfig.exists())  # credential removed
        self.assertIn("Data kept in volume autoresilience-data", out)

    def test_adopted_cluster_is_never_deleted_even_when_asked(self) -> None:
        self.installed(created_by_ar=False)
        runner = self.runner()
        code, out = self.run_cli(runner, "--yes", "uninstall", "--delete-cluster")

        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertFalse(any(c[:2] == ["kind", "delete"] for c in runner.calls))
        self.assertIn("it was not created by this tool", out)

    def test_deleting_data_and_owned_cluster_requires_flags_and_backs_up_first(self) -> None:
        self.installed(created_by_ar=True)
        runner = self.runner()
        code, out = self.run_cli(runner, "--yes", "uninstall", "--delete-data", "--delete-cluster")

        self.assertEqual(code, cli.EXIT_OK, out)
        flat = [" ".join(c) for c in runner.calls]
        dump = next(i for i, c in enumerate(flat) if "pg_dump" in c)
        down = next(i for i, c in enumerate(flat) if " down " in f" {c} ")
        volume = flat.index("docker volume rm autoresilience-data")
        self.assertLess(dump, down)
        self.assertLess(down, volume)
        self.assertIn("kind delete cluster --name autoresilience", flat)
        self.assertEqual(len(list(self.paths.backups.iterdir())), 1)

    def test_yes_alone_never_opts_into_deletions(self) -> None:
        self.installed(created_by_ar=True)
        runner = self.runner()
        self.run_cli(runner, "--yes", "uninstall", stdin=TTY("y\ny\ny\n"))
        self.assertFalse(any(c[:3] == ["docker", "volume", "rm"] or c[:2] == ["kind", "delete"] for c in runner.calls))


class StatusTests(Harness):
    def test_not_installed(self) -> None:
        code, out = self.run_cli(healthy_runner(), "status")
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("ar install", out)

    def test_json_reports_unreachable_engine(self) -> None:
        save(self.paths.state, State(cluster_name="autoresilience", api_port=1, web_port=2))
        code, out = self.run_cli(healthy_runner(), "status", "--json")
        report = json.loads(out)
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIsNone(report["api"]["ready_http"])
        self.assertFalse(report["console"]["reachable"])


class DoctorTests(Harness):
    def test_doctor_is_read_only(self) -> None:
        runner = healthy_runner(cluster_exists=False)
        code, out = self.run_cli(runner, "doctor", "--json")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertEqual(runner.writes(), [])
        names = [f["name"] for f in json.loads(out)]
        self.assertIn("port 9090", names)  # no cluster yet: its mapping must be free


class ClusterImportTests(Harness):
    CTX = "kind-staging"

    def setUp(self) -> None:
        super().setUp()
        save(self.paths.state, State(cluster_name="autoresilience"))
        self.paths.stack_env.write_text("AUTORESILIENCE_DB_PASSWORD=x\n")
        self.paths.kubeconfig.write_text('{"clusters": [], "users": [], "contexts": []}')

    def runner(self) -> FakeRunner:
        from .test_imports import staging_runner

        runner = staging_runner()
        engine = {"data": {"token": "ZQ==", "ca.crt": "Q0EK"}}
        runner.on(
            "kubectl",
            "--context",
            "kind-autoresilience",
            "-n",
            "autoresilience-system",
            "get",
            "secret",
            answer=ok(json.dumps(engine)),
        )
        allowed = {
            ("list", "pods", "shop"),
            ("list", "deployments.apps", "shop"),
            ("list", "endpointslices.discovery.k8s.io", "shop"),
            ("list", "events", "shop"),
        }

        def can_i(argv: list[str], _: bytes | None) -> object:
            ns = None if "--all-namespaces" in argv else argv[argv.index("-n") + 1]
            return ok("yes" if (argv[5], argv[6], ns) in allowed else "no")

        runner.on("kubectl", "--context", self.CTX, "auth", "can-i", answer=can_i)  # type: ignore[arg-type]
        return runner

    def test_import_needs_confirmation_and_changes_nothing_without_it(self) -> None:
        runner = self.runner()
        code, out = self.run_cli(runner, "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        self.assertEqual(code, cli.EXIT_DECLINED, out)
        self.assertIn("not granted: Secrets, ConfigMaps, any write, chaos execution", out)
        self.assertEqual(runner.writes(), [])
        self.assertEqual(load(self.paths.state).imported_clusters, [])  # type: ignore[union-attr]

    def test_import_grants_verifies_and_configures_the_engine(self) -> None:
        runner = self.runner()
        code, out = self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        self.assertEqual(code, cli.EXIT_OK, out)
        [record] = load(self.paths.state).imported_clusters  # type: ignore[union-attr]
        self.assertEqual(
            (record["context"], record["namespaces"], record["cluster_uid"]), (self.CTX, ["shop"], "uid-staging")
        )
        config = json.loads(self.paths.kubeconfig.read_text())
        self.assertEqual({c["name"] for c in config["contexts"]}, {"kind-autoresilience", self.CTX})
        self.assertIn(
            'AUTORESILIENCE_DISCOVERY_CLUSTERS=[{"context":"kind-staging","namespaces":["shop"]}]',
            self.paths.stack_env.read_text(),
        )
        self.assertNotIn("operator-secret-key", self.paths.kubeconfig.read_text())

    def test_unexpected_permissions_keep_the_engine_without_access(self) -> None:
        runner = self.runner()
        runner.on("kubectl", "--context", self.CTX, "auth", "can-i", answer=ok("yes"))  # e.g. cluster-admin binding
        code, out = self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("unexpected: viewer can get secrets", out)
        self.assertNotIn(self.CTX, self.paths.kubeconfig.read_text())
        self.assertEqual(len(load(self.paths.state).imported_clusters), 1)  # type: ignore[union-attr]  # for cleanup

    def test_remove_revokes_then_forgets(self) -> None:
        runner = self.runner()
        self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        code, out = self.run_cli(runner, "--yes", "cluster", "remove", "--context", self.CTX)
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertEqual(load(self.paths.state).imported_clusters, [])  # type: ignore[union-attr]
        self.assertNotIn(self.CTX, self.paths.kubeconfig.read_text())
        self.assertTrue(any("delete" in c and self.CTX in c for c in runner.calls))

    def test_remove_of_an_unreachable_cluster_needs_forget(self) -> None:
        runner = self.runner()
        self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        runner.on("kubectl", "--context", self.CTX, "get", "namespace", "kube-system", answer=fail("refused"))
        code, out = self.run_cli(runner, "--yes", "cluster", "remove", "--context", self.CTX)
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("--forget", out)
        self.assertEqual(len(load(self.paths.state).imported_clusters), 1)  # type: ignore[union-attr]
        code, out = self.run_cli(runner, "--yes", "cluster", "remove", "--context", self.CTX, "--forget")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("remain in kind-staging", out)

    def test_contexts_marks_the_stack_and_imports(self) -> None:
        runner = self.runner()
        self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        code, out = self.run_cli(runner, "cluster", "contexts")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("the stack's cluster", out)
        self.assertIn("imported, read-only: shop", out)

    def test_uninstall_also_revokes_imports(self) -> None:
        runner = self.runner()
        runner.on("docker", "info", answer=ok(DOCKER_INFO))
        runner.on("kind", "get", "clusters", answer=ok("autoresilience\n"))
        runner.on("docker", "inspect", answer=ok("true"))
        runner.on(
            "kubectl", "--context", "kind-autoresilience", "get", "nodes", answer=ok("autoresilience-control-plane")
        )
        self.run_cli(runner, "--yes", "cluster", "import", "--context", self.CTX, "--namespace", "shop")
        code, out = self.run_cli(runner, "--yes", "uninstall")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("revoke read-only discovery access in imported context kind-staging", out)
        self.assertTrue(any(c[:3] == ["kubectl", "--context", self.CTX] and "delete" in c for c in runner.calls))
        self.assertFalse(self.paths.helm.exists())
