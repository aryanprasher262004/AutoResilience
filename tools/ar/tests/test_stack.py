import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from ar_cli import stack
from ar_cli.paths import load_versions, parse_env_file
from ar_cli.state import State, load, save

from .fakes import ROOT, FakeRunner, ok, paths


class EnvFileTests(unittest.TestCase):
    def test_password_is_generated_once_and_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            stack.write_stack_env(p, State(web_port=3100, api_port=8100))
            first = parse_env_file(p.stack_env.read_text())
            stack.write_stack_env(p, State())
            second = parse_env_file(p.stack_env.read_text())
            mode = p.stack_env.stat().st_mode & 0o777

        self.assertEqual(mode, 0o600)
        self.assertGreaterEqual(len(first["AUTORESILIENCE_DB_PASSWORD"]), 24)
        self.assertEqual(first["AUTORESILIENCE_DB_PASSWORD"], second["AUTORESILIENCE_DB_PASSWORD"])
        self.assertEqual((first["AUTORESILIENCE_WEB_PORT"], second["AUTORESILIENCE_WEB_PORT"]), ("3100", "3000"))
        self.assertEqual(first["AUTORESILIENCE_KUBECONFIG"], str(p.kubeconfig))


class ComposeTests(unittest.TestCase):
    def test_down_never_removes_volumes(self) -> None:
        runner = FakeRunner()
        stack.down(runner, paths(ROOT))
        argv = runner.calls[0]
        self.assertNotIn("-v", argv)
        self.assertNotIn("--volumes", argv)
        self.assertEqual(argv[:4], ["docker", "compose", "-p", "autoresilience"])

    def test_parse_ps_accepts_ndjson_and_arrays(self) -> None:
        rows = [
            {"Service": "api", "State": "running", "Health": "healthy", "ExitCode": 0},
            {"Service": "migrate", "State": "exited", "Health": "", "ExitCode": 0},
        ]
        for text in ("\n".join(json.dumps(r) for r in rows), json.dumps(rows)):
            parsed = stack.parse_ps(text)
            self.assertEqual(parsed["api"].health, "healthy")
            self.assertEqual(parsed["migrate"].exit_code, 0)
        self.assertEqual(stack.parse_ps(""), {})

    def test_compose_file_publishes_only_on_loopback_and_mounts_no_host_credentials(self) -> None:
        text = (ROOT / "compose.yaml").read_text()
        lines = text.splitlines()
        ports = [lines[i + 1].strip() for i, line in enumerate(lines) if line.strip() == "ports:"]
        self.assertTrue(ports)
        self.assertTrue(all(p.startswith('- "127.0.0.1:') for p in ports), ports)
        self.assertNotIn("docker.sock", text)
        self.assertNotIn(".kube", text)
        self.assertIn("KUBE_CONTEXT: kind-autoresilience", text)
        self.assertIn("read_only: true", text)

    def test_compose_matches_pinned_cluster_name(self) -> None:
        versions = load_versions(paths(ROOT))
        text = (ROOT / "compose.yaml").read_text()
        self.assertIn(f"http://{versions.node}:30090", text)
        self.assertIn(f"KUBE_CONTEXT: {versions.context}", text)


class BackupTests(unittest.TestCase):
    def test_backup_writes_a_private_custom_format_dump(self) -> None:
        runner = FakeRunner()
        runner.on("exec", "-T", "postgres", "pg_dump", answer=ok(b"PGDMP\x01\x0e data"))
        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            target = stack.backup(runner, p, now=lambda: datetime(2026, 10, 18, 9, 30, tzinfo=UTC))
            self.assertEqual(target.name, "autoresilience-20261018T093000Z.dump")
            self.assertEqual(target.read_bytes(), b"PGDMP\x01\x0e data")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_backups_in_the_same_second_never_overwrite(self) -> None:
        runner = FakeRunner()
        runner.on("exec", "-T", "postgres", "pg_dump", answer=ok(b"PGDMP x"))
        fixed = lambda: datetime(2026, 10, 18, 9, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            names = [stack.backup(runner, p, now=fixed).name for _ in range(3)]
        self.assertEqual(len(set(names)), 3)

    def test_backup_refuses_output_that_is_not_a_dump(self) -> None:
        runner = FakeRunner()
        runner.on("exec", "-T", "postgres", "pg_dump", answer=ok(b"error: something"))
        with tempfile.TemporaryDirectory() as tmp:
            p = paths(Path(tmp))
            with self.assertRaises(ValueError):
                stack.backup(runner, p)
            self.assertFalse(p.backups.exists() and any(p.backups.iterdir()))

    def test_restore_reads_only_pg_dump_files_and_stops_the_engine_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "x.sql"
            bogus.write_text("DROP TABLE experiments;")
            with self.assertRaises(ValueError):
                stack.read_dump(bogus)
        runner = FakeRunner()
        stack.restore(runner, paths(ROOT), b"PGDMP...")
        self.assertIn("stop", runner.calls[0])
        restore = runner.calls[1]
        self.assertIn("pg_restore", restore)
        self.assertEqual(runner.inputs[1], b"PGDMP...")
        self.assertIn("up", runner.calls[2])


class RedactionTests(unittest.TestCase):
    def test_redacts_urls_tokens_and_passwords(self) -> None:
        text = (
            "postgresql+psycopg://autoresilience:s3cr3t@postgres:5432/db password=hunter2 "
            '"token": "abc" eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig'
        )
        out = stack.redact(text)
        for secret in ("s3cr3t", "hunter2", "abc", "eyJhbGci"):
            self.assertNotIn(secret, out)
        self.assertIn("autoresilience:***@postgres", out)


class StateTests(unittest.TestCase):
    def test_round_trip_and_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "home" / "state.json"
            self.assertIsNone(load(path))
            save(path, State(cluster_name="autoresilience", cluster_created_by_ar=True))
            self.assertEqual(load(path), State(cluster_name="autoresilience", cluster_created_by_ar=True))
            path.write_text(json.dumps({"schema": 99}))
            with self.assertRaises(ValueError):
                load(path)
