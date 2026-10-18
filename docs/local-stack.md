# Local stack

The self-hosted way to run AutoResilience: the engine API, PostgreSQL and the console run
as containers (`compose.yaml`), next to a dedicated kind cluster. `tools/ar` (the `ar` CLI)
installs and manages both. The host-process setup in the README (§2) stays the
development workflow. Both can exist side by side: they use different databases, and the
dev API/console ports are the stack's defaults, so stop one before starting the other or
pick other stack ports.

| | |
|---|---|
| **Type** | Runbook, plus the contract and decisions behind it |
| **Code** | `compose.yaml`, `apps/api/Dockerfile`, `apps/web/Dockerfile`, `tools/ar/`, `infra/rbac/`, `infra/versions.env` |

## Requirements

| | Minimum | Checked by `ar doctor` |
|---|---|---|
| Docker Desktop / Engine, running | 24.0, Compose v2.20 | version, daemon reachable |
| Memory available to Docker | 4 GiB (6 GiB recommended) | `INSUFFICIENT` below 4 GiB |
| CPUs available to Docker | 2 | `INSUFFICIENT` below 2 |
| Free disk (images, cluster, backups) | 10 GiB | `INSUFFICIENT` below |
| kind / kubectl / Helm | 0.20 / 1.28 / 3.12 | `MISSING` or `INSUFFICIENT` with an install link |
| Python | 3.11 (standard library only) | — |
| Free loopback ports | 3000 console, 8000 API, 9090 Prometheus (only before the cluster exists) | `CONFLICT` |

Measured on the reference machine (Apple silicon, Docker Desktop with 10 CPUs / 7.7 GiB,
`docker stats` at idle after `ar install`): the kind node with Prometheus, Litmus and the
sample apps used 2.1 GiB; the compose stack 0.2 GiB (api 121 MiB, web 52 MiB, postgres
37 MiB). The 4 GiB minimum leaves headroom for image builds and an experiment's Litmus
runner and replacement pods; 6 GiB is recommended.

Statuses use the safety-check vocabulary (`OK`, `MISSING`, `INSUFFICIENT`, `ERROR`) plus
`CONFLICT` for a port another program uses. A port the stack or the kind node already
publishes counts as `OK`.

## Install

```bash
python3 tools/ar/ar.py doctor     # read-only; fix anything that is not OK
python3 tools/ar/ar.py install    # prints the plan and asks before changing anything
```

On Windows, use `py tools\ar\ar.py …`. Below, `ar` means `python3 tools/ar/ar.py`.

`install` prints exactly what it will do and waits for `y`. `--yes` answers that question
for scripts. Then it:

1. **Creates the kind cluster `autoresilience`** from `infra/kind/cluster.yaml`. If a cluster
   with that name already exists and `ar` did not create it (for example from
   `scripts/dev-cluster.sh`), `install` asks a second question before using it. Such a
   cluster is recorded as *adopted* and is never deleted by `ar`.
2. **Provisions it** with the `scripts/dev-cluster.sh` steps. It uses the same manifests and
   values, and the pinned versions in `infra/versions.env`, which the script also sources.
   The steps are: the sample apps, the Prometheus and litmus-core Helm releases, the
   pre-pulled chaos images, and the vetted pod-delete ChaosExperiment with its namespaced
   ServiceAccount in each chaos namespace.
3. **Grants the engine its runtime identity** (see [Permissions](#permissions)). It writes a
   ServiceAccount kubeconfig to `~/.autoresilience/engine.kubeconfig` (0600). It then checks
   the actual permissions with `kubectl auth can-i --as`, and refuses to start if they differ.
4. **Builds and starts the stack.** It generates a database password into
   `~/.autoresilience/stack.env` (0600) and runs `docker compose up --wait`. It then waits
   until `/ready` answers 200.

Before every cluster write, `ar` checks that the context `kind-autoresilience` points at
exactly the nodes of kind cluster `autoresilience`. Otherwise it stops. It never uses the
kubeconfig's current context.

`install` is idempotent: rerun it to repair a partial install, re-grant revoked access or
update cluster components. Options: `--web-port N`, `--api-port N` (remembered).

Open the console at <http://127.0.0.1:3000>. **Settings → Local environment** shows whether
the engine reaches its database, the cluster and Prometheus, with the fix for each failure.

## Everyday commands

| Command | What it does |
|---|---|
| `ar status [--json]` | Docker, cluster node, each container's state and health, engine `/ready` and `/environment`, console. Exit code 0 only when everything is healthy. |
| `ar start` | Starts a stopped kind node (only the container labelled for this cluster), waits for the Kubernetes API, then `compose up --wait`. |
| `ar stop [--cluster]` | `compose stop`: containers and data are kept. `--cluster` also stops the kind node. |
| `ar diagnostics [--logs]` | Host, doctor, status and (optionally) the last 50 log lines per service, with URLs, passwords and tokens redacted. Paste it into an issue. |
| `ar backup` | `pg_dump -Fc` of the stack database to `~/.autoresilience/backups/autoresilience-<UTC time>.dump` (0600). |
| `ar restore FILE` | Asks first. Backs up the current data, stops the engine and console, runs `pg_restore --clean --single-transaction`, then starts them again. Only files with the pg_dump custom-format header are accepted. |
| `ar upgrade` | Asks first. Backs up, rebuilds the images from this checkout, restarts. The `migrate` service applies new migrations before the API starts. |
| `ar uninstall` | See [Uninstall](#uninstall). |

Exit codes: 0 success, 1 failure (the message says what to do), 3 declined or not confirmed.

## Startup order and recovery

`compose.yaml` encodes the order:

1. `postgres`, healthy when `pg_isready` passes.
2. `migrate`, a one-shot `alembic upgrade head`. It must exit 0.
3. `api`, healthy when `/ready` returns 200, i.e. the database is reachable and at the
   expected head.
4. `web`, healthy when its proxy reaches the API.

`up --wait` returns only when all of them are healthy. A failing step is reported by
`ar status` (for example `migrate exited (exit 1)`). `ar diagnostics --logs` shows why.

`postgres`, `api` and `web` use `restart: unless-stopped`, so they return after a Docker or
host restart. Docker does not enforce `depends_on` on such restarts. That is harmless:
`/ready` stays 503 until PostgreSQL is back, and the console shows "Database unavailable"
meanwhile. Experiments resume from the database (`docs/orchestration.md`). If the kind node
did not come back, `ar start` starts it. Prometheus keeps no data across restarts, so
baselines need about a minute of new samples.

## Permissions

Provisioning and runtime are separate identities.

| | Who | Credentials | Can |
|---|---|---|---|
| Provisioning | `ar`, on the host | the operator's kubeconfig, always `--context kind-autoresilience` after the ownership check | create the cluster, Helm releases, sample apps, RBAC |
| Runtime | the `api` container | ServiceAccount `autoresilience-system/autoresilience-engine` (`infra/rbac/`), mounted read-only | cluster-wide get/list of Deployments, StatefulSets and Pods; in `shop` and `resilience-sandbox` only: create/get/patch/delete ChaosEngines, get/delete ChaosResults, read the `pod-delete` ChaosExperiment and the `autoresilience-chaos` ServiceAccount |

The engine **cannot** read Secrets, change or delete workloads or pods (Litmus' runner
deletes pods under its own namespaced `autoresilience-chaos` account), create chaos in other
namespaces, or change RBAC. `install` verifies this list on every run.

The containers never get the host kubeconfig or the Docker socket. They reach the cluster
over kind's `kind` Docker network (`https://autoresilience-control-plane:6443`, Prometheus
at `:30090`). The API runs with `RUNTIME_MODE=local-stack`, and refuses to start without an
explicit `KUBE_CONTEXT` (`check_runtime` in `apps/api/app/core/config.py`). Ports are
published on `127.0.0.1` only. PostgreSQL is not published. Containers run as non-root
users with a read-only root filesystem, all capabilities dropped and `no-new-privileges`.

To revoke the engine's access, run `ar uninstall`, or delete the token Secret
`autoresilience-system/autoresilience-engine-token`. `ar install` grants it again.

## Data, backup and upgrade

- Experiment history lives in the Docker volume `autoresilience-data`. It survives `stop`,
  `upgrade`, `docker compose down` and, by default, `uninstall`. It is separate from the
  development database (`autoresilience-pgdata`, `scripts/dev-db.sh`).
- `~/.autoresilience/` (override with `AUTORESILIENCE_HOME`) holds:
  - `state.json`: what `ar` created, which is the source of truth for cleanup;
  - `stack.env`: ports, and the database password the volume was initialised with;
  - `engine.kubeconfig`;
  - `backups/`.
  Do not delete `stack.env` while you keep the volume.
- **Upgrade:** `git pull`, then `ar upgrade` (backup → build → migrate → restart). If the
  new version misbehaves, check out the previous commit, run `ar upgrade` again, then
  `ar restore` the backup it took. A newer schema cannot be opened by older code. Then run
  `ar install` to update cluster components when `infra/versions.env` changed.
- **Copy elsewhere:** the `.dump` files are standard `pg_restore` input.

## Uninstall

```bash
ar uninstall                                   # keeps data and the cluster
ar uninstall --delete-data --delete-cluster    # opt in to each deletion
```

By default `uninstall`:
- removes the stack's containers, network and locally built images;
- revokes the engine's access: it deletes only objects carrying both
  `app.kubernetes.io/managed-by=autoresilience` and `autoresilience.io/owner=local-manager`;
- deletes `engine.kubeconfig` and `state.json`.

It keeps the data volume, `stack.env`, backups and the cluster. A later `install` reuses
the data.

Deletions are opt-in. `--yes` alone never deletes data or the cluster.
- **Data:** with `--delete-data` (or an interactive yes), `uninstall` first takes a backup,
  and refuses if the database is not running.
- **Cluster:** `--delete-cluster` deletes the cluster only if `ar` created it. An adopted
  cluster is never deleted.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `doctor`: docker `ERROR` | Start Docker Desktop (`sudo systemctl start docker` on Linux). |
| `doctor`: port `CONFLICT` on 3000/8000 | Another program, often the dev console or API, uses it. Stop it or run `ar install --web-port 3100 --api-port 8100`. |
| `doctor`: port `CONFLICT` on 9090 | Something else uses it, and the cluster's Prometheus mapping is fixed at creation. Free it before the first `install`. |
| `install`: "points at nodes …, not kind cluster" | The context `kind-autoresilience` was redefined. Fix the kubeconfig. `ar` will not write elsewhere. |
| `install`: "The engine's permissions differ" | Someone changed `infra/rbac/` or the cluster's RBAC. Review the printed lines. |
| `status`: `migrate exited (exit 1)` | `ar diagnostics --logs`. Usually the database is not ready yet, or a migration failed. Fix it, then run `ar start`. |
| Console: Cluster (Kubernetes API) **Failing**, 401/403 | The engine's token was revoked. Run `ar install`. |
| Console: Cluster **Failing**, unreachable | The kind node is stopped. Run `ar start`. |
| Console: Prometheus **Failing** | Prometheus is restarting inside the cluster. Wait, then run `ar status`. |
| `compose.yaml`: "run `ar install` to create …" | `docker compose` was run without `--env-file ~/.autoresilience/stack.env`. Use `ar`. |

## Decisions

- **Containers, not bundled runtimes** (D-3). Docker is already required for kind, so
  containers add no new prerequisite. The future desktop shell supervises the same stack.
- **A stdlib-only Python CLI in the repository** (`tools/ar`, D-9 for now). It needs no new
  dependency and no virtualenv, and runs on macOS, Linux and Windows. It runs only fixed
  argv lists, never a shell, and applies only manifests from this repository. It needs a
  checkout, because `compose.yaml` and the manifests live there. Packaging (pipx, single
  binary, published images) is the distribution follow-up.
- **Images built locally from lockfiles.** Base images are pinned by digest, and
  dependencies are installed exactly from `uv.lock` (`--frozen`) and `package-lock.json`
  (`npm ci`). No registry is involved yet, so there are no published digests to verify.
- **Long-lived ServiceAccount token** in a Secret. The stack must recover after restarts
  without the operator. Revocation is a single Secret deletion.
- **No console controls for the stack yet.** The console only shows what the engine
  observes (`GET /environment`). Starting, stopping, backups and cleanup need a local
  service-manager endpoint (D-4), and fake buttons are not acceptable.

## Contract: `GET /environment`

Always 200 when the API answers.

```json
{
  "runtime_mode": "local-stack",
  "kube_context": "kind-autoresilience",
  "prometheus_url": "http://autoresilience-control-plane:30090",
  "checks": [{"name": "database|kubernetes|prometheus", "status": "pass|fail", "detail": "…"}]
}
```

- **Probes:**
  - `database`: the `/ready` check;
  - `kubernetes`: listing workloads, i.e. the engine's real permissions;
  - `prometheus`: `GET /api/v1/status/buildinfo`.
- **Bounded:** each probe is limited by the configured timeouts.
- **No secrets:** credentials never appear (the Prometheus URL drops userinfo).
- **Not readiness:** `/ready` stays database-only (`docs/readiness.md`).
