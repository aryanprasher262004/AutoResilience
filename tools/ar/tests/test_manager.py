"""The loopback service manager: host/origin/token checks, allowlist, confirmations."""

import io
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from typing import Any
from unittest import mock

from ar_cli import manager as m
from ar_cli.runner import Runner

ORIGIN = "http://127.0.0.1:3000"


class FakeApp:
    def __init__(self, runner: Runner, out: io.StringIO) -> None:
        self.runner, self.out = runner, out
        self.ran: list[str] = []

    def start(self) -> int:
        self.out.write("started\npassword=hunter2\n")
        return 0

    def stop(self, include_cluster: bool) -> int:
        assert include_cluster is False  # the console never stops the cluster
        return 0

    def backup(self) -> int:
        raise ValueError("pg_dump did not return a custom-format dump")


class ManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1000.0
        self.manager = m.Manager(
            lambda runner, out: FakeApp(runner, out),  # type: ignore[arg-type,return-value]
            lambda: {"installed": True, "api": {"url": "postgresql://u:secret@db"}},
            {ORIGIN},
            8765,
            token="tok",
            clock=lambda: self.now,
        )

    def wait(self, job_id: str) -> dict[str, Any]:
        for _ in range(200):
            job = self.manager.jobs[job_id]
            if job.state != "running":
                return job.to_dict()
            time.sleep(0.01)
        raise AssertionError("job did not finish")

    def test_checks(self) -> None:
        self.assertTrue(self.manager.authorized("Bearer tok"))
        for header in (None, "", "tok", "Bearer tok2", "Basic tok"):
            self.assertFalse(self.manager.authorized(header))
        self.assertTrue(self.manager.origin_allowed(ORIGIN))
        for origin in (None, "null", "http://evil.test", "http://127.0.0.1:3001"):
            self.assertFalse(self.manager.origin_allowed(origin))
        self.assertTrue(self.manager.host_allowed("localhost:8765"))
        for host in (None, "evil.test:8765", "127.0.0.1:9999", "0.0.0.0:8765"):
            self.assertFalse(self.manager.host_allowed(host))

    def test_confirmation_is_single_use_and_bound_to_its_operation(self) -> None:
        plan = self.manager.plan("start")
        self.assertIn("docker compose up", " ".join(plan["plan"]))
        self.assertEqual(self.manager.run("stop", plan["confirmation"])[0], 409)  # wrong operation, consumed
        self.assertEqual(self.manager.run("start", plan["confirmation"])[0], 409)
        status, job = self.manager.run("start", self.manager.plan("start")["confirmation"])
        self.assertEqual(status, 202)
        done = self.wait(job["id"])
        self.assertEqual(done["state"], "succeeded")
        self.assertIn("password=***", done["output"])
        self.assertNotIn("hunter2", json.dumps(done))

    def test_confirmation_expires(self) -> None:
        plan = self.manager.plan("backup")
        self.now += m.CONFIRMATION_TTL + 1
        self.assertEqual(self.manager.run("backup", plan["confirmation"])[0], 409)

    def test_failures_are_reported_not_raised(self) -> None:
        _, job = self.manager.run("backup", self.manager.plan("backup")["confirmation"])
        done = self.wait(job["id"])
        self.assertEqual(done["state"], "failed")
        self.assertIn("error: pg_dump", "\n".join(done["output"]))

    def test_one_operation_at_a_time(self) -> None:
        release = threading.Event()

        class Slow(FakeApp):
            def start(self) -> int:
                release.wait(2)
                return 0

        self.manager.app_factory = lambda runner, out: Slow(runner, out)  # type: ignore[assignment,return-value]
        self.assertEqual(self.manager.run("start", self.manager.plan("start")["confirmation"])[0], 202)
        status, body = self.manager.run("stop", self.manager.plan("stop")["confirmation"])
        self.assertEqual((status, "still running" in body["detail"]), (409, True))
        release.set()

    def test_only_allowlisted_operations_exist(self) -> None:
        self.assertEqual(set(m.OPERATIONS), {"start", "stop", "backup"})


class HttpTests(unittest.TestCase):
    """The real handler on an ephemeral loopback port."""

    def setUp(self) -> None:
        self.manager = m.Manager(
            lambda runner, out: FakeApp(runner, out),  # type: ignore[arg-type,return-value]
            lambda: {"installed": True, "detail": "token=abc123"},
            {ORIGIN},
            0,
            token="tok",
        )
        self.server = m.serve(self.manager, 0)
        port = self.server.server_address[1]
        self.manager.hosts = {f"127.0.0.1:{port}"}
        self.base = f"http://127.0.0.1:{port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(
        self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], Any]:
        default = {"Origin": ORIGIN, "Authorization": "Bearer tok"}
        if body is not None:
            default["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={**default, **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, dict(response.headers), json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            with exc:
                raw = exc.read()
                return exc.code, dict(exc.headers), json.loads(raw) if raw else None

    def test_binds_loopback_only(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_status_requires_origin_and_token_and_is_redacted(self) -> None:
        status, headers, body = self.call("GET", "/v1/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(body["detail"], "token=***")
        self.assertEqual(self.call("GET", "/v1/status", headers={"Authorization": "Bearer nope"})[0], 401)
        status, headers, _ = self.call("GET", "/v1/status", headers={"Origin": "http://evil.test"})
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_dns_rebinding_host_is_refused(self) -> None:
        self.assertEqual(self.call("GET", "/v1/status", headers={"Host": "evil.test"})[0], 421)

    def test_preflight_only_for_the_console_origin(self) -> None:
        status, headers, _ = self.call("OPTIONS", "/v1/operations/start", headers={"Authorization": ""})
        self.assertEqual(status, 204)
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])
        self.assertEqual(self.call("OPTIONS", "/v1/status", headers={"Origin": "http://evil.test"})[0], 403)

    def test_mutations_need_json_an_allowlisted_name_and_a_confirmation(self) -> None:
        self.assertEqual(self.call("POST", "/v1/operations/start", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.call("POST", "/v1/operations/uninstall/plan", {})[0], 404)
        self.assertEqual(self.call("POST", "/v1/operations/start", {"confirmation": "guess"})[0], 409)
        status, _, plan = self.call("POST", "/v1/operations/start/plan", {})
        self.assertEqual(status, 200)
        status, _, job = self.call("POST", "/v1/operations/start", {"confirmation": plan["confirmation"]})
        self.assertEqual(status, 202)
        for _ in range(200):
            status, _, polled = self.call("GET", f"/v1/jobs/{job['id']}")
            if polled["state"] != "running":
                break
            time.sleep(0.01)
        self.assertEqual(polled["state"], "succeeded")

    def test_request_logs_never_contain_the_token(self) -> None:  # also keeps test output quiet
        with mock.patch("builtins.print") as printed:
            self.call("GET", "/v1/status?x=1")
        logged = " ".join(str(c) for c in printed.call_args_list)
        self.assertNotIn("tok", logged.replace("/v1/status", ""))
