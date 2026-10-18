"""`ar manager`: the loopback service manager the console's stack controls talk to (D-4).

A foreground HTTP server on 127.0.0.1 only, run by the operator in a terminal. It is
the only way a browser can ask for a stack operation, and it allows very little:

  - operations: an allowlist of `start`, `stop` and `backup` (no install, uninstall,
    restore, upgrade, cluster import or anything that provisions or deletes);
  - authentication: a random pairing token printed in the terminal at start (never
    written to disk), sent as `Authorization: Bearer`; compared in constant time;
  - origin protection: requests must come from the console's own origin
    (`Origin` header), to this server's loopback `Host` (no DNS rebinding); CORS is
    answered for that origin only; bodies must be JSON (no form posts);
  - explicit confirmation: each operation first returns a plan with a single-use
    confirmation id (valid 2 minutes), which the run request must echo;
  - one operation at a time; output is captured, secret-redacted, and polled.

No Docker socket, kubeconfig or shell is reachable through it: operations call the
same App methods as the CLI, which run fixed argv lists.
"""

import hmac
import io
import json
import re
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

from .runner import CommandError, Result, Runner
from .stack import redact

if TYPE_CHECKING:
    from .main import App

MANAGER_PORT = 8765
CONFIRMATION_TTL = 120.0
MAX_BODY = 4096
OUTPUT_LIMIT = 200  # lines kept per job


@dataclass(frozen=True)
class Operation:
    name: str
    title: str
    plan: tuple[str, ...]


OPERATIONS: dict[str, Operation] = {
    "start": Operation(
        "start",
        "Start the stack",
        (
            "Start the kind node if it is stopped (only the container labelled for this cluster)",
            "docker compose up --wait: database, migrations, engine and console",
        ),
    ),
    "stop": Operation(
        "stop",
        "Stop the stack",
        (
            "docker compose stop: containers and data are kept; the kind cluster keeps running",
            (
                "This console stops responding until the stack is started again "
                "(from a terminal: `ar start`, or this manager's start operation from a reloaded console)"
            ),
        ),
    ),
    "backup": Operation(
        "backup",
        "Back up experiment data",
        ("pg_dump of the stack database to ~/.autoresilience/backups (0600); existing backups are kept",),
    ),
}


class CapturingRunner(Runner):
    """Like Runner, but long steps' output goes to the job log instead of the terminal."""

    def __init__(self, log: Callable[[str], None]) -> None:
        self._log = log

    def stream(self, argv: Any, *, timeout: float | None = 1800, env: Any = None) -> None:
        result: Result = self.run(argv, check=False, timeout=timeout, env=env)
        for line in (result.stdout + result.stderr).splitlines()[-40:]:
            self._log(line)
        if not result.ok:
            raise CommandError(argv, result)


@dataclass
class Job:
    id: str
    operation: str
    state: str = "running"  # running | succeeded | failed
    output: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def log(self, text: str) -> None:
        for line in redact(text).splitlines() or [""]:
            self.output.append(line)
        del self.output[:-OUTPUT_LIMIT]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation": self.operation,
            "state": self.state,
            "output": self.output,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class Manager:
    """Authorization, confirmations and jobs; independent of HTTP for testing."""

    def __init__(
        self,
        app_factory: Callable[[Runner, io.StringIO], "App"],
        status: Callable[[], dict[str, Any]],
        origins: set[str],
        port: int,
        token: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app_factory = app_factory
        self.status = status
        self.origins = origins
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.token = token or secrets.token_urlsafe(32)
        self.clock = clock
        self.confirmations: dict[str, tuple[str, float]] = {}
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.active: Job | None = None

    # --- checks ---------------------------------------------------------------------

    def origin_allowed(self, origin: str | None) -> bool:
        return origin is not None and origin in self.origins

    def host_allowed(self, host: str | None) -> bool:
        return host is not None and host in self.hosts

    def authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header.removeprefix("Bearer ").encode(), self.token.encode())

    # --- operations -----------------------------------------------------------------

    def plan(self, name: str) -> dict[str, Any]:
        op = OPERATIONS[name]
        confirmation = secrets.token_urlsafe(16)
        now = self.clock()
        with self.lock:
            self.confirmations = {k: v for k, v in self.confirmations.items() if v[1] > now}
            self.confirmations[confirmation] = (name, now + CONFIRMATION_TTL)
        return {
            "operation": name,
            "title": op.title,
            "plan": list(op.plan),
            "confirmation": confirmation,
            "expires_in_seconds": int(CONFIRMATION_TTL),
        }

    def run(self, name: str, confirmation: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            entry = self.confirmations.pop(confirmation, None)  # single use
            if entry is None or entry[0] != name or entry[1] <= self.clock():
                return 409, {"detail": "Confirmation missing, expired or for another operation; plan again"}
            if self.active is not None and self.active.state == "running":
                return 409, {"detail": f"Operation {self.active.operation} is still running"}
            job = Job(uuid.uuid4().hex, name)
            self.jobs[job.id] = self.active = job
        threading.Thread(target=self._execute, args=(job,), daemon=True, name=f"ar-{name}").start()
        return 202, job.to_dict()

    def _execute(self, job: Job) -> None:
        out = io.StringIO()
        try:
            app = self.app_factory(CapturingRunner(job.log), out)
            method = {"start": app.start, "stop": lambda: app.stop(False), "backup": app.backup}[job.operation]
            code = method()
            job.state = "succeeded" if code == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 (reported to the console, never raised into the server)
            job.log(f"error: {exc}")
            job.state = "failed"
        finally:
            job.log(out.getvalue())
            job.finished_at = time.time()


_JOB = re.compile(r"^/v1/jobs/([0-9a-f]{32})$")
_OPERATION = re.compile(r"^/v1/operations/([a-z]+)(/plan)?$")


def handler_for(manager: Manager) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "autoresilience-manager"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            # Request lines only; headers (with the token) are never logged.
            print(f"manager: {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

        def _send(self, status: int, body: Any = None, cors: bool = True) -> None:
            payload = b"" if body is None else json.dumps(body, default=str).encode()
            self.send_response(status)
            origin = self.headers.get("Origin")
            if cors and manager.origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", str(origin))
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _guard(self) -> bool:
            """Host, Origin and token checks shared by every method. False: already answered."""
            if not manager.host_allowed(self.headers.get("Host")):
                self._send(421, {"detail": "Wrong Host; the manager answers only on loopback"}, cors=False)
                return False
            if not manager.origin_allowed(self.headers.get("Origin")):
                self._send(403, {"detail": "Origin not allowed"}, cors=False)
                return False
            if self.command != "OPTIONS" and not manager.authorized(self.headers.get("Authorization")):
                self._send(401, {"detail": "Pairing token missing or wrong; copy it from the `ar manager` terminal"})
                return False
            return True

        def do_OPTIONS(self) -> None:
            if not self._guard():
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", str(self.headers.get("Origin")))
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            if not self._guard():
                return
            path = self.path.split("?")[0]
            if path == "/v1/status":
                self._send(200, json.loads(redact(json.dumps(manager.status(), default=str))))
            elif path == "/v1/operations":
                self._send(
                    200,
                    {"items": [{"name": o.name, "title": o.title, "plan": list(o.plan)} for o in OPERATIONS.values()]},
                )
            elif (match := _JOB.match(path)) and match.group(1) in manager.jobs:
                self._send(200, manager.jobs[match.group(1)].to_dict())
            else:
                self._send(404, {"detail": "Not found"})

        def do_POST(self) -> None:
            if not self._guard():
                return
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._send(415, {"detail": "Content-Type must be application/json"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413, {"detail": "Body too large"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"detail": "Body must be JSON"})
                return
            match = _OPERATION.match(self.path.split("?")[0])
            if not match or match.group(1) not in OPERATIONS:
                self._send(404, {"detail": f"Not an allowed operation; allowed: {', '.join(OPERATIONS)}"})
                return
            name = match.group(1)
            if match.group(2):
                self._send(200, manager.plan(name))
                return
            confirmation = body.get("confirmation") if isinstance(body, dict) else None
            status, payload = manager.run(name, str(confirmation or ""))
            self._send(status, payload)

    return Handler


def serve(manager: Manager, port: int) -> ThreadingHTTPServer:
    """Bound to 127.0.0.1 only; there is deliberately no option to bind elsewhere."""
    return ThreadingHTTPServer(("127.0.0.1", port), handler_for(manager))
