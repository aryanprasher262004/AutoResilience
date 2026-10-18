"""`ar`: install and manage the AutoResilience local stack.

    python3 tools/ar/ar.py doctor | install | start | stop | status | diagnostics
                           backup | restore FILE | upgrade | uninstall
                           cluster contexts | cluster import | cluster remove
                           manager

Anything that provisions or deletes resources prints exactly what it will do and asks
first (`--yes` answers the plan's question, never the opt-in deletions of data or the
cluster, which need their own flags). See docs/local-stack.md.
"""

import argparse
import dataclasses
import io
import json
import platform
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from . import checks, cluster, imports, stack
from .checks import Finding
from .manager import MANAGER_PORT, OPERATIONS, Manager, serve
from .paths import (
    DATA_VOLUME,
    DEFAULT_API_PORT,
    DEFAULT_WEB_PORT,
    ENGINE_NAMESPACE,
    OWNER_SELECTOR,
    PROMETHEUS_HOST_PORT,
    Paths,
    Versions,
    default_paths,
    load_versions,
)
from .runner import CommandError, Runner
from .state import State, load, save

EXIT_OK, EXIT_FAILED, EXIT_DECLINED = 0, 1, 3


class Declined(Exception):
    """The user said no (or could not be asked)."""


class Abort(Exception):
    """A precondition failed; the message says what to do."""


class Console:
    def __init__(self, out: TextIO, stdin: TextIO, assume_yes: bool) -> None:
        self.out, self.stdin, self.assume_yes = out, stdin, assume_yes

    def say(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    def step(self, text: str) -> None:
        self.say(f"==> {text}")

    def finding(self, f: Finding) -> None:
        self.say(f"  [{f.status:^12}] {f.name:<16} {f.detail}")
        if f.fix and not f.ok:
            self.say(f"  {'':14} fix: {f.fix}")

    @property
    def interactive(self) -> bool:
        return self.stdin.isatty()

    def confirm(self, question: str) -> bool:
        """The main plan question: --yes answers it; otherwise the user must type y."""
        if self.assume_yes:
            self.say(f"{question} [y/N] y (--yes)")
            return True
        if not self.interactive:
            raise Declined(f"{question} — not a terminal; rerun with --yes to confirm")
        self.out.write(f"{question} [y/N] ")
        self.out.flush()
        return self.stdin.readline().strip().lower() in {"y", "yes"}

    def opt_in(self, question: str, flag: bool) -> bool:
        """Destructive extras: only an explicit flag, or an interactive yes."""
        if flag:
            return True
        if not self.interactive or self.assume_yes:
            return False
        self.out.write(f"{question} [y/N] ")
        self.out.flush()
        return self.stdin.readline().strip().lower() in {"y", "yes"}


class App:
    def __init__(self, runner: Runner, paths: Paths, console: Console) -> None:
        self.runner, self.paths, self.console = runner, paths, console
        self.versions: Versions = load_versions(paths)

    # --- helpers -------------------------------------------------------------------

    def state(self) -> State | None:
        return load(self.paths.state)

    def require_state(self) -> State:
        state = self.state()
        if state is None:
            raise Abort("AutoResilience is not installed here; run `ar install` first")
        return state

    def api_url(self, state: State) -> str:
        return f"http://127.0.0.1:{state.api_port}"

    def web_url(self, state: State) -> str:
        return f"http://127.0.0.1:{state.web_port}"

    def doctor_findings(self, web_port: int, api_port: int) -> list[Finding]:
        findings, _ = checks.check_docker(self.runner)
        findings += [checks.check_tool(self.runner, name) for name in ("kind", "kubectl", "helm")]
        findings.append(checks.check_disk(self.paths.home))
        docker_up = any(f.name == "docker" and f.ok for f in findings)
        owned = checks.owned_ports(self.runner, self.versions) if docker_up else set()
        cluster_exists = docker_up and cluster.cluster_status(self.runner, self.versions).exists
        ports = [
            ("console", web_port, "choose another with `ar install --web-port N`"),
            ("engine API", api_port, "choose another with `ar install --api-port N`"),
        ]
        if not cluster_exists:  # an existing cluster already owns its mapping
            ports.append(
                ("Prometheus (kind mapping)", PROMETHEUS_HOST_PORT, "free port 9090 (fixed in infra/kind/cluster.yaml)")
            )
        findings += checks.check_ports(ports, owned)
        return findings

    def ensure_engine_kubeconfig(self, provisioner: bool = False) -> None:
        paths = [self.paths.kubeconfig] + ([self.paths.provisioner_kubeconfig] if provisioner else [])
        for path in paths:
            if not path.exists():
                raise Abort(f"{path} is missing; run `ar install` to regenerate the engine's access")

    @staticmethod
    def imported(state: State) -> list[imports.ImportRecord]:
        return [imports.ImportRecord.from_dict(raw) for raw in state.imported_clusters]

    def write_stack_env(self, state: State) -> None:
        """stack.env, with DISCOVERY_CLUSTERS for imports the engine has a kubeconfig entry for."""
        granted = cluster.kubeconfig_entries(self.paths.kubeconfig)
        records = [r for r in self.imported(state) if r.context in granted]
        stack.write_stack_env(self.paths, state, imports.discovery_setting(records))

    def refresh_engine(self, state: State, add: Sequence[cluster.KubeconfigEntry] = ()) -> None:
        """Rewrite the engine's kubeconfig and env for the recorded imports; restart it if running."""
        changed = cluster.write_engine_kubeconfig(
            self.runner, self.paths, self.versions, [r.context for r in self.imported(state)], add
        )
        self.write_stack_env(state)
        api = stack.services(self.runner, self.paths).get("api")
        if api is not None and api.state == "running":
            self.console.step(
                "Restarting the engine with its new cluster access" if changed else "Restarting the engine"
            )
            stack.recreate_engine(self.runner, self.paths)
            stack.wait_ready(self.api_url(state))

    # --- commands ------------------------------------------------------------------

    def doctor(self, as_json: bool) -> int:
        state = self.state()
        findings = self.doctor_findings(
            state.web_port if state else DEFAULT_WEB_PORT, state.api_port if state else DEFAULT_API_PORT
        )
        if as_json:
            self.console.say(json.dumps([asdict(f) for f in findings], indent=2))
        else:
            self.console.step("Environment (read-only checks)")
            for f in findings:
                self.console.finding(f)
        return EXIT_OK if all(f.ok for f in findings) else EXIT_FAILED

    def install(self, web_port: int, api_port: int) -> int:
        c = self.console
        previous = self.state()
        c.step("Checking the environment")
        findings = self.doctor_findings(web_port, api_port)
        for f in findings:
            c.finding(f)
        blocking = [f for f in findings if not f.ok]
        if blocking:
            raise Abort("Fix the findings above, then rerun `ar install` (nothing was changed)")

        status = cluster.cluster_status(self.runner, self.versions)
        recorded = previous is not None and previous.cluster_name == self.versions.cluster_name
        created_by_ar = bool(previous and previous.cluster_created_by_ar)
        adopt = status.exists and not recorded
        v = self.versions
        c.say()
        c.say("This will:")
        if not status.exists:
            c.say(
                f"  - create the kind cluster '{v.cluster_name}' (Docker container {v.node}; localhost:{PROMETHEUS_HOST_PORT} → Prometheus)"
            )
        elif adopt:
            c.say(
                f"  - use the existing kind cluster '{v.cluster_name}' (not created by this tool: it will never be deleted by it)"
            )
        else:
            c.say(
                f"  - update the kind cluster '{v.cluster_name}' ({'created' if created_by_ar else 'adopted'} earlier)"
            )
        c.say(
            f"  - in context {v.context} only: apply the sample apps (shop, resilience-sandbox), Helm releases prometheus"
        )
        c.say(f"    ({v.prometheus_chart}) and litmus ({v.litmus_core_chart}), pod-delete templates and chaos RBAC")
        c.say(f"    (Helm repositories are added to {self.paths.helm}, not to your own Helm configuration)")
        c.say(
            f"  - create the engine's ServiceAccount ({ENGINE_NAMESPACE}/autoresilience-engine, read-only + own ChaosEngines)"
        )
        c.say(
            "    (read: workloads, ReplicaSets, Pods, Services, EndpointSlices, Events, Nodes, Namespaces; no Secrets)"
        )
        c.say(f"    and write its kubeconfig to {self.paths.kubeconfig} (0600)")
        c.say("  - create the separate import provisioner (autoresilience-provisioner: may only write inside")
        c.say(
            f"    ar-imp-* namespaces, enforced by an admission policy), kubeconfig {self.paths.provisioner_kubeconfig}"
        )
        c.say(
            f"  - build images autoresilience/api:local and autoresilience/web:local, create the Docker volume {DATA_VOLUME}"
        )
        c.say(
            f"  - start the stack: console {self.web_url(State(web_port=web_port))}, API {self.api_url(State(api_port=api_port))} (loopback only)"
        )
        c.say(f"  - record what it created in {self.paths.state}")
        if not c.confirm("Proceed?"):
            raise Declined("Nothing was changed")
        if adopt and not c.confirm(
            f"Cluster '{v.cluster_name}' already exists. Use it (it is never deleted by `ar uninstall`)?"
        ):
            raise Declined("Nothing was changed")

        state = previous or State()
        state.web_port, state.api_port = web_port, api_port
        if not status.exists:
            c.step(f"Creating kind cluster {v.cluster_name}")
            cluster.create_cluster(self.runner, self.paths)
            state.cluster_created_by_ar = True
        elif adopt:
            state.cluster_created_by_ar = False
        elif not status.running:
            cluster.start_node(self.runner, v)
        state.cluster_name = v.cluster_name
        state.installed_at = state.installed_at or datetime.now(UTC).isoformat(timespec="seconds")
        save(self.paths.state, state)  # recorded before provisioning, so cleanup knows it

        cluster.wait_api_server(self.runner, v)
        c.step("Provisioning cluster components")
        cluster.provision(self.runner, self.paths, v, c.step)
        c.step("Granting the engine its runtime access")
        changed = self._grant_and_verify(state)
        c.step("Building and starting the stack")
        api_before = stack.services(self.runner, self.paths).get("api")
        self.write_stack_env(state)
        stack.build(self.runner, self.paths)
        stack.up(self.runner, self.paths)
        if changed and api_before is not None:
            # An existing engine container keeps its old kubeconfig (and token) until recreated.
            stack.recreate_engine(self.runner, self.paths)
        stack.wait_ready(self.api_url(state))
        return self.status(as_json=False)

    def _grant_and_verify(self, state: State) -> bool:
        cluster.grant_engine_access(self.runner, self.paths, self.versions)
        changed = cluster.write_engine_kubeconfig(
            self.runner, self.paths, self.versions, [r.context for r in self.imported(state)]
        )
        changed = cluster.write_provisioner_kubeconfig(self.runner, self.paths, self.versions) or changed
        wrong = []
        for who, provisioner in (("engine", False), ("provisioner", True)):
            for p, actual in cluster.check_engine_permissions(self.runner, self.versions, provisioner=provisioner):
                if actual != p.expected:
                    wrong.append(p)
                    self.console.say(
                        f"  unexpected: {who} {'can' if actual else 'cannot'} {p.verb} {p.resource}"
                        f" in {p.namespace or 'all namespaces'}"
                    )
        if wrong:
            raise Abort("The engine's permissions differ from infra/rbac/; not starting the stack")
        self.console.say("  engine permissions verified (read-only + own ChaosEngines; no secrets, no workload writes)")
        self.console.say(
            "  provisioner permissions verified (namespaces and bindings only; writes confined to imports)"
        )
        return changed

    def start(self) -> int:
        state = self.require_state()
        self.ensure_engine_kubeconfig(provisioner=True)
        status = cluster.cluster_status(self.runner, self.versions)
        if not status.exists:
            raise Abort(
                f"The kind cluster '{self.versions.cluster_name}' does not exist; run `ar install` to create it"
            )
        if not status.running:
            self.console.step(f"Starting the kind node {self.versions.node}")
            cluster.start_node(self.runner, self.versions)
        cluster.wait_api_server(self.runner, self.versions)
        self.console.step("Starting the stack")
        self.write_stack_env(state)
        stack.up(self.runner, self.paths)
        stack.wait_ready(self.api_url(state))
        return self.status(as_json=False)

    def stop(self, include_cluster: bool) -> int:
        self.require_state()
        self.console.step("Stopping the stack (containers and data are kept)")
        stack.stop(self.runner, self.paths)
        if include_cluster:
            self.console.step(f"Stopping the kind node {self.versions.node}")
            cluster.stop_node(self.runner, self.versions)
        return EXIT_OK

    def collect_status(self) -> dict[str, Any]:
        state = self.state()
        report: dict[str, Any] = {"installed": state is not None, "state": asdict(state) if state else None}
        docker_ok = self.runner.run(["docker", "info", "--format", "{{.ServerVersion}}"], check=False, timeout=20).ok
        report["docker"] = "running" if docker_ok else "unreachable"
        if docker_ok:
            cs = cluster.cluster_status(self.runner, self.versions)
            report["cluster"] = {
                "name": self.versions.cluster_name,
                "exists": cs.exists,
                "running": cs.running,
                "created_by_ar": bool(state and state.cluster_created_by_ar),
            }
            report["services"] = {k: asdict(v) for k, v in stack.services(self.runner, self.paths).items()}
        report["engine_kubeconfig"] = self.paths.kubeconfig.exists()
        if state:
            ready_status, ready = stack.get_json(f"{self.api_url(state)}/ready")
            env_status, environment = stack.get_json(f"{self.api_url(state)}/environment", timeout=15)
            web_status, _ = stack.get_json(f"{self.web_url(state)}/api/backend/health")
            report["api"] = {"url": self.api_url(state), "ready_http": ready_status, "ready": ready}
            report["environment"] = environment if env_status == 200 else None
            report["console"] = {"url": self.web_url(state), "reachable": web_status == 200}
        return report

    def status(self, as_json: bool) -> int:
        r = self.collect_status()
        if as_json:
            self.console.say(json.dumps(r, indent=2, default=str))
            return EXIT_OK if self._healthy(r) else EXIT_FAILED
        c = self.console
        if not r["installed"]:
            c.say("Not installed. Run `ar doctor`, then `ar install`.")
            return EXIT_FAILED
        c.step("Status")
        c.finding(Finding("docker", checks.OK if r["docker"] == "running" else checks.ERROR, r["docker"]))
        if "cluster" in r:
            cl = r["cluster"]
            detail = f"{cl['name']}: {'running' if cl['running'] else 'stopped' if cl['exists'] else 'missing'}" + (
                " (created by ar)" if cl["created_by_ar"] else " (adopted; never deleted by ar)"
            )
            c.finding(
                Finding(
                    "cluster",
                    checks.OK if cl["running"] else checks.ERROR,
                    detail,
                    "ar start" if cl["exists"] else "ar install",
                )
            )
            for name in stack.SERVICES:
                svc = r["services"].get(name)
                if svc is None:
                    c.finding(Finding(name, checks.MISSING, "no container", "ar start"))
                elif name == "migrate":
                    done = svc["state"] == "exited" and svc["exit_code"] == 0
                    c.finding(
                        Finding(
                            name,
                            checks.OK if done else checks.ERROR,
                            f"{svc['state']} (exit {svc['exit_code']})",
                            "ar diagnostics --logs",
                        )
                    )
                else:
                    healthy = svc["state"] == "running" and svc["health"] in ("healthy", "")
                    c.finding(
                        Finding(
                            name,
                            checks.OK if healthy else checks.ERROR,
                            f"{svc['state']} {svc['health']}".strip(),
                            "ar start",
                        )
                    )
        if "api" in r:
            api = r["api"]
            ready = api["ready"] if isinstance(api["ready"], dict) else {}
            failed = [ch["detail"] for ch in ready.get("checks", []) if ch.get("status") == "fail"]
            c.finding(
                Finding(
                    "engine /ready",
                    checks.OK if api["ready_http"] == 200 else checks.ERROR,
                    f"{api['url']}: "
                    + (ready.get("status") or str(api["ready"]))
                    + (f" — {failed[0]}" if failed else ""),
                    "ar start, then ar diagnostics --logs",
                )
            )
            for ch in (r.get("environment") or {}).get("checks", []):
                if ch["name"] != "database":
                    c.finding(
                        Finding(
                            f"engine→{ch['name']}", checks.OK if ch["status"] == "pass" else checks.ERROR, ch["detail"]
                        )
                    )
            c.finding(
                Finding(
                    "console", checks.OK if r["console"]["reachable"] else checks.ERROR, r["console"]["url"], "ar start"
                )
            )
        return EXIT_OK if self._healthy(r) else EXIT_FAILED

    @staticmethod
    def _healthy(r: dict[str, Any]) -> bool:
        env_checks = (r.get("environment") or {}).get("checks", [])
        return bool(
            r.get("installed")
            and r.get("docker") == "running"
            and (r.get("cluster") or {}).get("running")
            and (r.get("api") or {}).get("ready_http") == 200
            and env_checks
            and all(ch["status"] == "pass" for ch in env_checks)
            and (r.get("console") or {}).get("reachable")
        )

    def diagnostics(self, include_logs: bool) -> int:
        """Secret-free report to paste into an issue."""
        c = self.console
        c.say("AutoResilience local stack diagnostics")
        c.say(f"generated: {datetime.now(UTC).isoformat(timespec='seconds')}")
        c.say(
            f"host: {platform.system()} {platform.release()} {platform.machine()}; python {platform.python_version()}"
        )
        c.say(f"repository: {self.paths.root}; state home: {self.paths.home}")
        self.doctor(as_json=False)
        report = self.collect_status()
        c.say(stack.redact(json.dumps(report, indent=2, default=str)))
        if include_logs and self.paths.stack_env.exists():
            c.step("Last 50 log lines per service (secrets redacted)")
            c.say(stack.logs(self.runner, self.paths, 50))
        return EXIT_OK

    def backup(self) -> int:
        self.require_state()
        path = stack.backup(self.runner, self.paths)
        self.console.say(f"Backup written: {path} ({path.stat().st_size} bytes)")
        return EXIT_OK

    def restore(self, file: Path) -> int:
        state = self.require_state()
        dump = stack.read_dump(file)
        c = self.console
        c.say(f"This replaces ALL experiment data in the stack database with {file}.")
        c.say("A backup of the current data is taken first. The engine is stopped while restoring.")
        if not c.confirm("Restore?"):
            raise Declined("Nothing was changed")
        safety = stack.backup(self.runner, self.paths)
        c.say(f"Current data backed up to {safety}")
        stack.restore(self.runner, self.paths, dump)
        stack.wait_ready(self.api_url(state))
        c.say("Restored.")
        return EXIT_OK

    def upgrade(self) -> int:
        state = self.require_state()
        self.ensure_engine_kubeconfig()
        c = self.console
        c.say("This will back up the database, rebuild the images from this checkout, and restart the stack;")
        c.say("the migrate service applies any new database migrations before the API starts.")
        if not c.confirm("Upgrade?"):
            raise Declined("Nothing was changed")
        if stack.services(self.runner, self.paths).get("postgres", None) is not None:
            c.say(f"Backup written: {stack.backup(self.runner, self.paths)}")
        self.write_stack_env(state)
        stack.build(self.runner, self.paths)
        stack.up(self.runner, self.paths)
        stack.wait_ready(self.api_url(state))
        c.say("Cluster components are not changed by upgrade; rerun `ar install` to update them.")
        return self.status(as_json=False)

    # --- imported clusters (read-only discovery) ---------------------------------------

    def cluster_contexts(self) -> int:
        state = self.state()
        recorded = {r.context: r for r in self.imported(state)} if state else {}
        contexts = imports.list_contexts(self.runner)
        if not contexts:
            self.console.say("No contexts in your kubeconfig (kubectl config get-contexts).")
            return EXIT_FAILED
        for name in contexts:
            if name == self.versions.context:
                note = "the stack's cluster (experiments run here)"
            elif name in recorded:
                note = f"imported, read-only: {', '.join(recorded[name].namespaces)}"
            else:
                note = ""
            self.console.say(f"  {name:<40} {note}".rstrip())
        return EXIT_OK

    def cluster_import(self, context: str, namespaces: list[str], include_nodes: bool) -> int:
        c = self.console
        state = self.require_state()
        self.ensure_engine_kubeconfig()
        c.step(f"Checking context {context} (read-only)")
        try:
            plan = imports.plan(self.runner, self.versions, context, namespaces, include_nodes)
        except imports.ImportRefused as exc:
            raise Abort(str(exc)) from exc
        c.say("This will:")
        for line in imports.describe(plan):
            c.say(f"  {line}")
        c.say("  The engine can then show this cluster's topology. It cannot run experiments there.")
        if not c.confirm("Grant read-only access?"):
            raise Declined("Nothing was changed")
        c.step(f"Creating the read-only identity in {context}")
        imports.apply(self.runner, self.paths, plan)
        record = imports.record(plan)
        others = [r for r in self.imported(state) if r.context != context]
        previous = next((r for r in self.imported(state) if r.context == context), None)
        if previous is not None:  # keep cleanup information about earlier grants
            record = dataclasses.replace(
                record,
                namespaces=sorted({*record.namespaces, *previous.namespaces}),
                created_namespace=previous.created_namespace or record.created_namespace,
            )
        state.imported_clusters = [r.to_dict() for r in [*others, record]]
        save(self.paths.state, state)  # recorded first, so `ar cluster remove` can clean up
        wrong = [(p, a) for p, a in imports.check_permissions(self.runner, plan) if a != p.expected]
        for p, actual in wrong:
            c.say(
                f"  unexpected: viewer {'can' if actual else 'cannot'} {p.verb} {p.resource} in {p.namespace or 'all namespaces'}"
            )
        if wrong:
            raise Abort(
                f"The viewer's permissions in {context} differ from infra/rbac/viewer-*.yaml (existing RBAC there?); "
                f"the engine was not given access. Review, then `ar cluster remove --context {context}`."
            )
        c.say("  viewer permissions verified (get/list in the shared namespaces only; no secrets, no writes)")
        entry = imports.kubeconfig_entry(plan, imports.read_token(self.runner, context))
        self.refresh_engine(state, [entry])
        c.say(f"Imported {context}. In the console: Applications → Onboard application → {context}.")
        return EXIT_OK

    def cluster_remove(self, context: str, forget: bool) -> int:
        c = self.console
        state = self.require_state()
        record = next((r for r in self.imported(state) if r.context == context), None)
        if record is None:
            raise Abort(f"{context} is not an imported cluster (see `ar cluster contexts`)")
        c.say("This will:")
        c.say(f"  - in {context}: delete the objects labelled {imports.VIEWER_SELECTOR}")
        c.say(
            f"    (Roles in {', '.join(record.namespaces)}, the viewer ServiceAccount and token"
            + (f", namespace {imports.VIEWER_NAMESPACE}" if record.created_namespace else "")
            + ")"
        )
        c.say("  - remove the context from the engine's kubeconfig and restart the engine")
        c.say("  Applications onboarded from it stay listed as no longer authorized; experiment history is unchanged.")
        if not c.confirm("Remove?"):
            raise Declined("Nothing was changed")
        try:
            imports.revoke(self.runner, record)
        except (cluster.OwnershipError, CommandError) as exc:
            if not forget:
                raise Abort(
                    f"{exc}. Nothing was changed locally; rerun with --forget to drop the engine's access "
                    "anyway and leave the objects in that cluster"
                ) from exc
            c.say(f"  not revoked ({exc}); objects labelled {imports.VIEWER_SELECTOR} remain in {context}")
        state.imported_clusters = [r.to_dict() for r in self.imported(state) if r.context != context]
        save(self.paths.state, state)
        if self.paths.kubeconfig.exists():
            self.refresh_engine(state)
        c.say(f"Removed {context}.")
        return EXIT_OK

    def uninstall(self, delete_data: bool, delete_cluster: bool) -> int:
        c = self.console
        state = self.require_state()
        v = self.versions
        c.say("This will:")
        c.say("  - stop and remove the stack's containers, network and locally built images")
        c.say(
            f"  - revoke the engine's cluster access (objects labelled {OWNER_SELECTOR}) and delete {self.paths.kubeconfig}"
        )
        c.say(
            f"Kept unless you opt in below: the Docker volume {DATA_VOLUME} (experiment history; backed up first if deleted),"
        )
        for r in self.imported(state):
            c.say(f"  - revoke read-only discovery access in imported context {r.context} ({', '.join(r.namespaces)})")
        c.say(f"backups in {self.paths.backups} (always kept), imported applications (namespaces ar-imp-*;")
        c.say("remove them in the console first, or they stay without a way to remove them from it),")
        c.say(
            f"and the kind cluster '{v.cluster_name}'"
            + ("" if state.cluster_created_by_ar else " (adopted: never deleted by this tool)")
        )
        if not c.confirm("Uninstall?"):
            raise Declined("Nothing was changed")
        drop_data = c.opt_in(f"Also DELETE all experiment data (volume {DATA_VOLUME})?", delete_data)
        drop_cluster = state.cluster_created_by_ar and c.opt_in(
            f"Also DELETE the kind cluster '{v.cluster_name}' created by this tool?", delete_cluster
        )
        if delete_cluster and not state.cluster_created_by_ar:
            c.say(f"Not deleting cluster '{v.cluster_name}': it was not created by this tool.")

        services = stack.services(self.runner, self.paths) if self.paths.stack_env.exists() else {}
        if drop_data:  # always keep a way back before deleting data
            if services.get("postgres") is None or services["postgres"].state != "running":
                raise Abort("The database is not running, so it cannot be backed up first; run `ar start` and retry")
            c.say(f"Backup written: {stack.backup(self.runner, self.paths)}")
        if self.paths.stack_env.exists():
            c.step("Removing the stack (volumes kept)")
            stack.down(self.runner, self.paths)
        status = cluster.cluster_status(self.runner, v)
        if status.running and not drop_cluster:
            c.step("Revoking the engine's cluster access")
            cluster.revoke_engine_access(self.runner, v)
        elif not drop_cluster:
            c.say(
                f"The kind node is not running, so the engine's ServiceAccount in '{v.cluster_name}' was not revoked;"
                f" start the node and delete objects labelled {OWNER_SELECTOR} (or run `ar install` then `ar uninstall`)."
            )
        for r in self.imported(state):
            c.step(f"Revoking discovery access in {r.context}")
            try:
                imports.revoke(self.runner, r)
            except (cluster.OwnershipError, CommandError) as exc:
                c.say(f"  not revoked ({exc}); objects labelled {imports.VIEWER_SELECTOR} remain in {r.context}")
        self.paths.kubeconfig.unlink(missing_ok=True)
        self.paths.provisioner_kubeconfig.unlink(missing_ok=True)
        shutil.rmtree(self.paths.helm, ignore_errors=True)  # this tool's Helm repo cache
        if drop_data:
            c.step(f"Deleting volume {DATA_VOLUME}")
            self.runner.run(["docker", "volume", "rm", DATA_VOLUME], check=False)
            self.paths.stack_env.unlink(missing_ok=True)  # its password only opened that volume
        if drop_cluster:
            c.step(f"Deleting kind cluster {v.cluster_name}")
            cluster.delete_cluster(self.runner, v)
        self.paths.state.unlink(missing_ok=True)
        c.say("Uninstalled." + ("" if drop_data else f" Data kept in volume {DATA_VOLUME}; `ar install` reuses it."))
        return EXIT_OK


def run_manager(app: App, port: int) -> int:
    """Serve the loopback service manager until Ctrl-C (see manager.py)."""
    state = app.require_state()
    origins = {f"http://127.0.0.1:{state.web_port}", f"http://localhost:{state.web_port}"}

    def factory(runner: Runner, out: io.StringIO) -> App:
        return App(runner, app.paths, Console(out, io.StringIO(), assume_yes=True))

    manager = Manager(factory, app.collect_status, origins, port)
    try:
        server = serve(manager, port)
    except OSError as exc:
        raise Abort(f"Cannot listen on 127.0.0.1:{port} ({exc}); choose another with --port") from exc
    c = app.console
    c.say(f"AutoResilience service manager on http://127.0.0.1:{port} (loopback only)")
    c.say(f"Accepts requests from the console at {', '.join(sorted(origins))}")
    c.say("Operations: " + ", ".join(OPERATIONS) + " (each needs a confirmation in the console)")
    c.say("")
    c.say(f"Pairing token (paste into Settings → Stack controls): {manager.token}")
    c.say("It is valid until this process stops. Press Ctrl-C to stop the manager.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        c.say("Manager stopped.")
    finally:
        server.server_close()
    return EXIT_OK


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ar", description="Install and manage the AutoResilience local stack.")
    p.add_argument("-y", "--yes", action="store_true", help="confirm the printed plan without asking")
    sub = p.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check tools, Docker resources and ports (read-only)")
    doctor.add_argument("--json", action="store_true")
    install = sub.add_parser(
        "install", help="create/verify the cluster, grant engine access, build and start the stack"
    )
    install.add_argument("--web-port", type=int, default=None)
    install.add_argument("--api-port", type=int, default=None)
    sub.add_parser("start", help="start the cluster node (if stopped) and the stack")
    stop = sub.add_parser("stop", help="stop the stack; containers and data are kept")
    stop.add_argument("--cluster", action="store_true", help="also stop the kind node container")
    status = sub.add_parser("status", help="health of the cluster, containers, engine and console")
    status.add_argument("--json", action="store_true")
    diagnostics = sub.add_parser("diagnostics", help="secret-free report for bug reports")
    diagnostics.add_argument("--logs", action="store_true", help="include the last 50 log lines per service")
    sub.add_parser("backup", help="pg_dump the stack database to ~/.autoresilience/backups")
    restore = sub.add_parser("restore", help="replace the database with a backup (takes a backup first)")
    restore.add_argument("file", type=Path)
    sub.add_parser("upgrade", help="back up, rebuild images from this checkout, migrate, restart")
    uninstall = sub.add_parser("uninstall", help="remove the stack; keeps data and the cluster unless asked")
    uninstall.add_argument("--delete-data", action="store_true", help="also delete the data volume")
    uninstall.add_argument(
        "--delete-cluster", action="store_true", help="also delete the cluster, if this tool created it"
    )
    clusters = sub.add_parser("cluster", help="read-only discovery access to further clusters")
    csub = clusters.add_subparsers(dest="cluster_command", required=True)
    csub.add_parser("contexts", help="list your kubeconfig contexts and what was imported (read-only)")
    imp = csub.add_parser("import", help="grant the engine read-only access to namespaces of a context")
    imp.add_argument("--context", required=True, help="kubeconfig context (never the current one implicitly)")
    imp.add_argument("--namespace", action="append", required=True, help="namespace to share; repeat for more")
    imp.add_argument("--include-nodes", action="store_true", help="also allow reading Nodes (cluster-scoped)")
    rm = csub.add_parser("remove", help="revoke an import and remove it from the engine")
    rm.add_argument("--context", required=True)
    rm.add_argument("--forget", action="store_true", help="drop it locally even if the cluster is unreachable")
    manager = sub.add_parser("manager", help="loopback service manager for the console's stack controls")
    manager.add_argument("--port", type=int, default=None, help=f"loopback port (default {MANAGER_PORT})")
    return p


def _port(value: int | None, fallback: int) -> int:
    port = fallback if value is None else value
    if not 1024 <= port <= 65535:
        raise Abort(f"port {port} must be between 1024 and 65535")
    return port


def main(
    argv: Sequence[str] | None = None,
    runner: Runner | None = None,
    paths: Paths | None = None,
    out: TextIO = sys.stdout,
    stdin: TextIO = sys.stdin,
) -> int:
    args = parser().parse_args(argv)
    console = Console(out, stdin, args.yes)
    try:
        app = App(runner or Runner(), paths or default_paths(), console)
        previous = app.state()
        commands: dict[str, Callable[[], int]] = {
            "doctor": lambda: app.doctor(args.json),
            "install": lambda: app.install(
                _port(getattr(args, "web_port", None), previous.web_port if previous else DEFAULT_WEB_PORT),
                _port(getattr(args, "api_port", None), previous.api_port if previous else DEFAULT_API_PORT),
            ),
            "start": app.start,
            "stop": lambda: app.stop(args.cluster),
            "status": lambda: app.status(args.json),
            "diagnostics": lambda: app.diagnostics(args.logs),
            "backup": app.backup,
            "restore": lambda: app.restore(args.file),
            "upgrade": app.upgrade,
            "uninstall": lambda: app.uninstall(args.delete_data, args.delete_cluster),
            "manager": lambda: run_manager(app, _port(args.port, MANAGER_PORT)),
        }
        if args.command == "cluster":
            cluster_commands: dict[str, Callable[[], int]] = {
                "contexts": app.cluster_contexts,
                "import": lambda: app.cluster_import(args.context, list(args.namespace or []), args.include_nodes),
                "remove": lambda: app.cluster_remove(args.context, args.forget),
            }
            return cluster_commands[args.cluster_command]()
        return commands[args.command]()
    except Declined as exc:
        console.say(f"Cancelled: {exc}")
        return EXIT_DECLINED
    except (Abort, cluster.OwnershipError, CommandError, TimeoutError, ValueError, OSError) as exc:
        console.say(f"error: {exc}")
        return EXIT_FAILED
