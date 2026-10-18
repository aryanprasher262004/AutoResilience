import json
import socket
import unittest

from ar_cli import checks
from ar_cli.checks import CONFLICT, ERROR, INSUFFICIENT, MISSING, OK, DockerInfo
from ar_cli.paths import load_versions

from .fakes import ROOT, FakeRunner, fail, ok, paths

GiB = 1024**3


class VersionTests(unittest.TestCase):
    def test_parses_common_version_outputs(self) -> None:
        self.assertEqual(checks.parse_version("kind v0.33.0 go1.27.0 darwin/arm64"), (0, 33, 0))
        self.assertEqual(checks.parse_version("Client Version: v1.35.3\nKustomize Version: v5"), (1, 35, 3))
        self.assertEqual(checks.parse_version("v4.3.0+gbec5b06"), (4, 3, 0))
        self.assertEqual(checks.parse_version("2.29"), (2, 29, 0))
        self.assertIsNone(checks.parse_version("unknown"))

    def test_missing_old_and_current_tools(self) -> None:
        runner = FakeRunner(tools=("kind", "helm"))
        runner.on("kind", "version", answer=ok("kind v0.19.0 go1.20"))
        runner.on("helm", "version", answer=ok("v3.15.0+g1"))

        missing = checks.check_tool(runner, "kubectl")
        old = checks.check_tool(runner, "kind")
        current = checks.check_tool(runner, "helm")

        self.assertEqual((missing.status, old.status, current.status), (MISSING, INSUFFICIENT, OK))
        self.assertIn("kubernetes.io", missing.fix or "")
        self.assertEqual(old.detail, "0.19.0 < required 0.20")


class DockerTests(unittest.TestCase):
    def test_daemon_not_running_is_an_actionable_error(self) -> None:
        runner = FakeRunner()
        runner.on("docker", "info", answer=fail("Cannot connect to the Docker daemon"))

        findings, info = checks.check_docker(runner)

        self.assertIsNone(info)
        self.assertEqual([(f.name, f.status) for f in findings], [("docker", ERROR)])
        self.assertIn("Start Docker", findings[0].fix or "")

    def test_reports_versions_and_resources(self) -> None:
        runner = FakeRunner()
        runner.on("docker", "info", answer=ok(json.dumps({"ServerVersion": "29.3.1", "NCPU": 1, "MemTotal": 3 * GiB})))
        runner.on("docker", "compose", "version", answer=ok("2.40.0\n"))

        findings, info = checks.check_docker(runner)

        self.assertEqual(info, DockerInfo(cpus=1, memory_bytes=3 * GiB))
        self.assertEqual(
            {f.name: f.status for f in findings},
            {"docker": OK, "compose": OK, "docker memory": INSUFFICIENT, "docker cpus": INSUFFICIENT},
        )

    def test_below_recommended_memory_passes_with_a_note(self) -> None:
        memory, cpus = checks.check_resources(DockerInfo(cpus=4, memory_bytes=5 * GiB))
        self.assertEqual((memory.status, cpus.status), (OK, OK))
        self.assertIn("recommended", memory.detail)


class PortTests(unittest.TestCase):
    def test_conflict_unless_published_by_autoresilience(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            busy = listener.getsockname()[1]
            with socket.socket() as spare:
                spare.bind(("127.0.0.1", 0))
                free = spare.getsockname()[1]
            findings = checks.check_ports([("console", busy, "pick another"), ("api", free, "")], owned=set())
            owned = checks.check_ports([("console", busy, "pick another")], owned={busy})

        self.assertEqual([f.status for f in findings], [CONFLICT, OK])
        self.assertEqual(findings[0].fix, "pick another")
        self.assertEqual(owned[0].status, OK)
        self.assertIn("in use by AutoResilience", owned[0].detail)

    def test_owned_ports_come_from_project_and_cluster_labels(self) -> None:
        runner = FakeRunner()
        runner.on(
            "docker",
            "ps",
            answer=lambda argv, _: ok(
                "127.0.0.1:3000->3000/tcp\n127.0.0.1:9090->30090/tcp, 127.0.0.1:51234->6443/tcp\n"
            ),
        )
        ports = checks.owned_ports(runner, load_versions(paths(ROOT)))

        self.assertEqual(ports, {3000, 9090, 51234})
        labels = [c[c.index("--filter") + 1] for c in runner.calls]
        self.assertEqual(
            labels, ["label=com.docker.compose.project=autoresilience", "label=io.x-k8s.kind.cluster=autoresilience"]
        )
