# Onboarding a Kubernetes application

| | |
|---|---|
| **Type** | Runbook |
| **Contract** | [topology.md](topology.md) |

Onboarding is read-only: it picks a cluster the engine is already authorized to read, the
namespaces the application runs in, and shows its workloads, readiness and topology.
Experiments are then started from the existing builder and pass the same safety checks.

## In the console

**Applications → Onboard application**:

1. **Cluster.** Lists `GET /clusters`. *Execution cluster* (`KUBE_CONTEXT`): experiments
   may run there. *Read-only discovery*: topology only.
2. **Namespaces.** Each with its workload count; namespaces the engine may not read are
   shown disabled with the API's error. System namespaces are never offered.
3. **Workloads & save.** Deployments and StatefulSets with controller readiness, their
   Pods, the Services selecting them and Warning events. On the execution cluster each
   row links to `/experiments/new?namespace=&kind=&name=`. Saving stores a named
   application (nothing is written to the cluster) and opens its topology.

The application page shows the graph (drag to pan, scroll/pinch to zoom, click or focus +
Enter to select), kind and edge filters, a namespace filter, search, an equivalent List
view, the inspector (status, containers, relationships with provenance, unknowns, events,
labels) and the *Not verified* list. **Forget application** removes only the record.

## Granting read-only access to another cluster (local stack)

```bash
ar cluster contexts                                     # your kubeconfig's context names
ar cluster import --context kind-staging --namespace shop [--namespace web] [--include-nodes]
ar cluster remove --context kind-staging [--forget]
```

`import` is checked first, read-only, with your credentials and the explicit context:
the context exists, its API answers (the kube-system namespace UID is recorded as the
cluster's fingerprint), the namespaces exist, and `autoresilience-system` either does not
exist or was created by AutoResilience. It then prints its plan and asks. On yes it
applies `infra/rbac/viewer-*.yaml`:

- namespace `autoresilience-system` (only if absent), ServiceAccount `autoresilience-viewer`
  and its token Secret;
- per shared namespace a Role + RoleBinding: get/list Deployments, ReplicaSets,
  StatefulSets, Pods, Services, EndpointSlices, Events;
- with `--include-nodes`, get/list Nodes (cluster-scoped). Without it, Node placement is
  reported as unknown.

It verifies with `kubectl auth can-i --as` that the viewer can read exactly that and cannot
read Secrets or ConfigMaps, list Pods cluster-wide, delete Pods, patch workloads, create
ChaosEngines or RoleBindings. On any difference the engine gets no access (the objects stay
recorded so `ar cluster remove` can delete them). Otherwise the engine's kubeconfig gains
a context with **only the viewer token** (your credentials are never copied),
`DISCOVERY_CLUSTERS` is set in `stack.env`, and the engine container is recreated.

Reachability: the engine runs in a container on kind's Docker network. kind clusters are
reached by their control-plane container name; other clusters need a routable API server
address. Loopback servers of other tools (e.g. minikube's `127.0.0.1:port`) are refused.

`remove` re-checks the fingerprint, then deletes only objects carrying
`app.kubernetes.io/managed-by=autoresilience`, `autoresilience.io/owner=local-manager` and
`autoresilience.io/access=read-only-discovery`, and the namespace only if `import` created
it. If the cluster is unreachable it changes nothing unless you pass `--forget` (which
drops the local access and prints what remains in the cluster). `ar uninstall` revokes
every import as well. Applications onboarded from a removed context stay listed as *no
longer authorized* and are not read.

Re-running `import` for the same context adds namespaces. To reduce access, `remove` and
import again.

## Development (host processes)

The API uses your kubeconfig. To authorize a further context for read-only discovery,
set in `apps/api/.env`:

```bash
DISCOVERY_CLUSTERS=[{"context":"kind-staging","namespaces":["shop"]}]
```

The engine then lists only those namespaces there, with your credentials, read-only calls
only, and never offers chaos on it. Use a read-only identity if the context can do more.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Namespaces step: "derived from workloads" | The engine was granted before topology reads existed. `ar install` re-grants (adds ReplicaSets, Services, EndpointSlices, Events, Nodes, Namespaces). |
| Topology: `listing_forbidden` for a kind | Same as above, or the imported viewer lacks it (`--include-nodes` for Nodes). |
| Imported cluster: 503 "Failed to resolve" | The cluster's node is stopped or unreachable from the `kind` network. Start it; the engine retries on the next read. |
| `import`: "uses https://127.0.0.1:…" | Only kind clusters and routable API servers can be imported into the containerised engine. |
| `import`: "viewer's permissions … differ" | Existing RBAC in that cluster grants the viewer more (e.g. a wide binding to all ServiceAccounts). Review it, then `ar cluster remove`. |
| Application "no longer authorized" | Its context was removed or a namespace is no longer granted. Import again, or onboard a new application. |
