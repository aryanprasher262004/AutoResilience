# Application imports (P7)

Import lets a Community user bring an application that is **not** running in a cluster yet
(a Docker Compose file, Kubernetes manifests, or a single image), review it, and deploy
it as an **isolated test deployment** on the execution cluster, where the existing
pod-delete experiments can then run against it. Onboarding (`docs/onboarding.md`)
remains the read-only path for applications that already run.

```
Import → Parse → Validate → Security review → Preview (plan) → Save
       → Explicit approval (plan digest) → Isolated deployment → Health verification
       → Topology (onboarded application) → Experiments (safety validation as always)
       → Removal (typed confirmation, ownership-checked)
```

Nothing runs on file selection; nothing deploys on save; nothing retries or deletes by
itself. The console is one client of this API; every rule below is enforced by the API,
the provisioner identity or the cluster, never only by the UI.

## Concepts

| Term | Meaning |
|---|---|
| Import | A record (`app_imports`) holding the **normalized spec**, the findings and the **plan** rendered from that spec. Never the file text, environment values or credentials. |
| Normalized spec | What the supported subset of the file says, through an allowlist (`app/schemas/imports.py` `ImportSpec`): workloads, images, replicas, ports, probes, resources, emptyDir volumes, declared relations, environment variable *names*. |
| Plan | The complete list of Kubernetes objects a deployment creates, all in `ar-imp-<name>`, rendered deterministically from the spec. Its `digest` (sha256 of the canonical JSON) is what the user approves. |
| Finding | `blocking` (must be fixed in the file), `warning` (deploys, behaves differently from Docker), `info` (how something is translated or ignored). Each has a stable `code`, the input `path` and a `hint`. |
| Declared relation | A relationship the file states (Compose `depends_on`). Recorded and shown, never verified, never drawn as a Kubernetes edge, never evidence of traffic. |
| Provisioner | The dedicated identity that deploys and removes imports. Separate from the engine's experiment identity. |

## Supported inputs (compatibility matrix)

Limits for every input: 256 KiB, 50 YAML documents, nesting depth 32, 20 workloads,
5 replicas per workload, 10 ports, 1 container per workload, CPU ≤ 1 core and memory
≤ 1 GiB per container (defaults 50m/64Mi requested, 500m/256Mi limit), namespace quota
30 Pods / 8 CPU / 8 GiB. YAML is loaded as plain data only: aliases, merge keys,
duplicate keys, non-string keys and custom tags are refused (`safe_yaml.py`).

### Docker Compose

| Compose | Handling |
|---|---|
| `image` | Required; must be a valid reference. Variables (`${TAG}`) are refused (no `.env` is read). No tag / `latest` → warning; digest → noted as reproducible. |
| `command`, `entrypoint` | Become container `args` / `command`. A string is split like Compose does (shell-like quoting, no shell). Variables refused; credential-looking arguments warned. |
| `working_dir` | Absolute paths only. |
| `ports`, `expose` | Container ports become a ClusterIP Service named after the service. Host ports are **not** published (info). Ranges and host-mode ports refused. |
| `deploy.replicas`, `scale` | 1–5 replicas. `deploy.mode: global` refused. |
| `deploy.resources` | `limits` / `reservations` (cpus, memory) within the caps; anything else defaulted. |
| `healthcheck` | `CMD` / `CMD-SHELL` → exec **readiness** probe with the same timing. No healthcheck but a TCP port → a TCP readiness check (marked "added"). |
| `depends_on`, `networks` | Recorded as declared relations / names. Start order is not enforced (info); all services share the namespace network. |
| `volumes` (named, anonymous, tmpfs) | An `emptyDir` per Pod (warning: not persisted, not shared). |
| `read_only` | `readOnlyRootFilesystem`. |
| `environment`, `env_file` | **Names only** (warning). Values are never read, stored, returned, logged or copied; `env_file` is never opened. |
| `container_name`, `hostname`, `restart`, `labels`, `logging`, `links`, `init`, `platform`, `pull_policy`, `stop_*`, `tty`, `stdin_open`, `x-*` | Ignored with the reason (info). Services with `profiles` are skipped, like `docker compose up`. |
| `dns`, `extra_hosts`, `ulimits`, `user`, `tmpfs`, `shm_size`, … | Ignored with a warning. |
| `build` | Refused when there is no `image`; with an `image`, ignored (nothing is ever built). |
| `privileged`, `cap_add`, `devices`, `network_mode`, `pid`, `ipc`, `uts`, `userns_mode`, `cgroup*`, `security_opt`, `sysctls`, `group_add`, `runtime`, `gpus`, `volumes_from`, `oom_*` | Refused. |
| Bind mounts, host paths, `~`, `./`, the Docker socket | Refused (`host_path_volume`, `docker_socket`). The path is never opened. |
| `secrets`, `configs`, `extends`, `include` (any level) | Refused: they read other files or carry credentials. |
| Any other key | Refused as unsupported, with a pointer to this page. |

### Kubernetes manifests

| Kind | Handling |
|---|---|
| `apps/v1` Deployment, StatefulSet | One container; `selector.matchLabels` only and matching the template labels; replicas ≤ 5. StatefulSets need their `serviceName` Service in the file and no `volumeClaimTemplates`. |
| `v1` Service | Must select exactly one imported workload. `NodePort`/`LoadBalancer` become ClusterIP (warning); `ExternalName`, `externalIPs`, selector-less Services refused. |
| `List` | Flattened. |
| `Namespace` | Ignored: the import has its own namespace; `metadata.namespace` is replaced (info). |
| Secret, ConfigMap, CRD, any custom resource, RBAC, ServiceAccount, Pod, Job, CronJob, DaemonSet, PV/PVC, Ingress, NetworkPolicy, webhooks, Helm/Argo hooks | Refused with the reason. |

Pod and container fields are read through an allowlist and rendered again; nothing is
applied as written. Refused: `hostNetwork`, `hostPID`, `hostIPC`, `hostUsers`, `nodeName`,
`initContainers`, `ephemeralContainers`, `shareProcessNamespace`, `hostAliases`, privileged
containers, `allowPrivilegeEscalation: true`, added capabilities, `hostPort`, probe
`host`, non-emptyDir volumes (hostPath, secret, configMap, PVC, projected), mount
propagation, unknown fields. Dropped with a warning: scheduling (`nodeSelector`,
affinity, tolerations, priority), `serviceAccountName` (imported Pods get no token),
`imagePullSecrets`, `envFrom`, env values (names kept), Secret references, lifecycle
hooks, annotations (so Pods cannot opt into metric scraping or sidecar injection).

### Single image

`image`, optional `port` (→ Service + TCP readiness check), `replicas` (1–5, default 2).

### Not supported (future extensions)

Building images from a Dockerfile, private registries and pull secrets, configuration
and secret values (an explicit, reviewed opt-in per variable), ConfigMaps, persistent
volumes, Helm charts and kustomize, multi-container Pods and init containers, Compose
`profiles` selection, Ingress/exposure to the host, importing into a namespace that
already exists, import onto read-only discovery clusters.

## Security model

Layered, so that no single check is the only protection:

1. **Parsing.** Text only, in the request body: the API never opens a path, reads `.env`,
   fetches a URL or runs a command. Safe YAML loader with byte/document/depth limits.
   Filenames are reduced to a sanitized base name, for display only.
2. **Normalization.** Only allowlisted fields reach the spec; the plan is rendered from
   the spec, never from the input, with conservative defaults: no ServiceAccount token,
   no service-link environment, RuntimeDefault seccomp, `allowPrivilegeEscalation:
   false`, resource requests and limits on every container, no annotations on imported
   Pods. Ownership labels (`app.kubernetes.io/managed-by=autoresilience`,
   `autoresilience.io/owner=import`, `autoresilience.io/import=<name>`,
   `autoresilience.io/import-id=<uuid>`) on every object; user labels under
   `autoresilience.io/` are refused.
3. **Isolation in the cluster.** Namespace `ar-imp-<name>` with Pod Security Admission
   `baseline` enforced (`restricted` warned/audited), a ResourceQuota (no NodePorts,
   LoadBalancers or PVCs) and LimitRange, and a NetworkPolicy: imported Pods accept
   traffic only from the namespace and from `monitoring` (Prometheus), and may connect
   only within the namespace and to cluster DNS. Verified on kind (kindnet enforces
   NetworkPolicy): other namespaces and the internet are unreachable from imported Pods.
4. **A separate, confined identity.** `infra/rbac/provisioner.yaml`: the
   `autoresilience-provisioner` ServiceAccount may, cluster-wide, only get/create/patch/delete
   namespaces, create RoleBindings and `bind` three named ClusterRoles. Inside an import
   namespace it binds itself to `autoresilience-import-writer` (namespaced writes of the
   kinds a plan contains). A **ValidatingAdmissionPolicy** rejects any write by this
   identity outside namespaces named `ar-imp-*` and labelled `autoresilience.io/owner=import`,
   any namespace without Pod Security `baseline`, any RoleBinding other than the three
   vetted role/subject pairs, and any non-ClusterIP Service. It cannot read Secrets or
   ConfigMaps elsewhere, cannot touch Pods, and cannot run chaos. The engine's own identity
   (`engine-rbac.yaml`) still cannot deploy anything.
5. **The provisioner client** (`app/integrations/app_provisioner.py`) refuses a kubeconfig
   that is not that ServiceAccount (SelfSubjectReview), one that reaches a different
   cluster than the engine's execution context (kube-system UID), any object of a kind
   outside its allowlist, outside the import namespace, without the import's id label,
   binding another role, or exposing a Service; and it never updates an existing
   object that lacks the import's id.
6. **Approval.** `POST /imports/{id}/deploy` needs `confirm: true` and the digest of the
   reviewed plan; a changed plan is refused (409). Removal needs the typed name.
7. **Ownership-safe cleanup.** Removal deletes the namespace only if it carries this
   import's labels **and** every Deployment, StatefulSet, Service, ConfigMap,
   ServiceAccount and RoleBinding in it does (except the ones Kubernetes creates);
   otherwise it refuses and changes nothing. Cluster-scoped objects are never created.

What is **not** protected: images are pulled by the node from public registries and run
as the user wrote them (inside the constraints above); a malicious image can still use
its CPU/memory quota and talk to its own namespace. Treat imports as test deployments
of software you would run on your own machine.

## Load generator and evidence

Optionally, the user selects HTTP endpoints (`{service, port, path}`) of the import's own
Services. The plan then adds `autoresilience-loadgen` (the same stdlib
`infra/sample-app/loadgen/loadgen.py`, vendored and checked identical by a test) with
`TARGETS` built server-side as
`<ns>/<workload>=http://<service>.<ns>.svc.cluster.local:<port><path>`, plus
`ALLOWED_HOST_SUFFIX=.<ns>.svc.cluster.local`: the process exits before sending anything
if a target is not plain HTTP to that namespace. Paths are absolute, without host,
query, fragment, credentials or `..`; ports must be TCP ports of the chosen Service.
The NetworkPolicy confines it as well, so there is no route to other workloads, the node,
the cloud metadata address or the internet (SSRF). It exports the existing
`loadgen_*{target_namespace,target_workload}` series, so baselines, recovery and scoring
v1/v2/v3 use it unchanged. Without it, client evidence is `UNAVAILABLE`, never a
success. Imported Pods carry no annotations, so they cannot be scraped and cannot pose as
the load generator.

## Experiments on imported workloads

`POST /experiments` refuses (422, `target.namespace`) any target in an `ar-imp-*`
namespace unless that import is `READY` and the target is one of its workloads (not the
load generator). The topology reports the same through `experiment_target`. Every
experiment then goes through the unchanged safety validation and pod-delete
implementation (GRACEFUL/FORCE): for example a single-replica workload fails
`min_healthy_replicas_after_fault` under the default policy. Import namespaces always
get the default policy; the sandbox policy stays limited to `resilience-sandbox`.

## API (contract)

| Endpoint | Effect |
|---|---|
| `GET /imports/capabilities` | Whether deployment is available (provisioner identity verified on the execution cluster), limits, supported keys/kinds. |
| `POST /imports/preview` | Parse, review and plan. Stores nothing, contacts no cluster. |
| `POST /imports` | Save a deployable import (`PLANNED`). 409 if the name exists (a `REMOVED` one is replaced), 422 with blocking findings. |
| `GET /imports`, `GET /imports/{id}` | Read. |
| `POST /imports/{id}/deploy` `{plan_digest, confirm: true}` | Apply the plan (`PLANNED`/`FAILED` → `DEPLOYING`). 503 without a usable provisioner. |
| `POST /imports/{id}/refresh` | One read-only health check with the engine's access: `DEPLOYING` → `READY` (links an Application) or `FAILED`; `REMOVING` → `REMOVED`. |
| `POST /imports/{id}/remove` `{confirm_name}` | Ownership-checked namespace deletion (`REMOVING`), or discard a never-deployed plan. |
| `DELETE /imports/{id}` | Forget a `REMOVED` (or never-deployed) record. |

States: `PLANNED → DEPLOYING → READY | FAILED`, `FAILED → DEPLOYING` (retry, explicit),
any deployed state `→ REMOVING → REMOVED`. A failure state (image pull, crash loop,
configuration error) must persist 45 s before it is a verdict; the deployment times out
after `IMPORT_DEPLOY_TIMEOUT_SECONDS` (300). Each failure carries `error` and
`recovery` text. The imported Application cannot be deleted on its own (409): remove the
import.

Topology (`autoresilience-topology/1`, additive): nodes may carry `origin`
(`{import_id, import_name, role, workload}`); an application's topology may carry
`imported` with `declared` relations (`verified: false`) and `planned` resources with
`observed`. See `docs/topology.md`.

## Runbook

Development (host processes):

```bash
./scripts/dev-cluster.sh          # once: kind cluster with Prometheus and Litmus
./scripts/dev-db.sh               # database at the current migration head
./scripts/dev-provisioner.sh      # the provisioner identity + its kubeconfig (prints the path)
cd apps/api && KUBE_CONTEXT=kind-autoresilience \
  PROVISIONER_KUBECONFIG=~/.autoresilience/dev-provisioner.kubeconfig uv run fastapi dev app/main.py
cd apps/web && npm run dev        # http://localhost:3000/applications/import
```

Local stack: `python3 tools/ar/ar.py install` creates the identity, writes
`~/.autoresilience/provisioner.kubeconfig` and mounts it into the engine container
(`docs/local-stack.md`). Without a provisioner, imports can be reviewed and saved but
not deployed; Settings → Kubernetes access → Application imports says why.

Revoke the identity (development): `kubectl --context kind-autoresilience delete -f
infra/rbac/provisioner.yaml`. Remove imports first: without the identity they can only be
deleted by hand (`kubectl delete namespace -l autoresilience.io/owner=import`).

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Deployment is not available on this engine" | No `PROVISIONER_KUBECONFIG`, or it is not the provisioner ServiceAccount, or it reaches another cluster. Run `scripts/dev-provisioner.sh` (or `ar install`) and restart the API. |
| `FAILED: Image pull failed` | The image or tag does not exist, is private, or the registry was unreachable. Fix the reference and import again, or retry. |
| `FAILED: Crash loop` | The container needs configuration that was not copied (environment values, files) or more memory. `kubectl -n ar-imp-<name> logs deploy/<workload>`. |
| Pods never created, `Cannot start` | Pod Security baseline or the quota rejected them; the event message says which. |
| Removal refused: "contains objects this import did not create" | Something else was created in the namespace. Delete those objects yourself, then remove again. |
| Experiment refused for an imported workload | The import is not `READY`, or the target is the load generator, or safety validation refused it (see its validation result). |
| Client evidence `UNAVAILABLE` | No load target was chosen for that workload's Service. Import again with one. |

## Verification (P7)

Automated: API unit and HTTP tests (`tests/unit/test_imports.py`,
`tests/api/test_imports.py`), CLI tests for the provisioner identity, web tests for the
wizard, the import page, topology overlay and tooltip placement. Real environment (kind,
2026-10-19): ResilienceMart (`examples/resiliencemart`) imported from Compose through the
console, deployed under the admission policy, Pod Security and NetworkPolicy (cross-
namespace and internet egress blocked), health verified, topology onboarded, pod-delete
run on storefront (GRACEFUL, 100) and checkout (FORCE, 96.2, slower recovery), the
single-replica cache refused by validation, the load generator refused as a target,
removal refused while a foreign ConfigMap was present, then completed.

Manual acceptance (user-run, ResilienceMart guide): Compose import, deployment,
topology discovery, storefront and checkout experiments, rejection of
`unsafe-compose.yaml` and the single-replica safety refusal confirmed. The manual
cleanup steps (guide §6: removal, ownership refusal, forget) are **not yet confirmed**
in that run.
