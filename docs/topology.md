# Topology and application onboarding

How the engine turns one read-only cluster snapshot into a graph, which clusters it may
read, and what an onboarded application is.

| | |
|---|---|
| **Type** | Contract and decisions |
| **Code** | `apps/api/app/services/topology/` (`graph.py` builder, `clusters.py` access), `apps/api/app/api/routes/topology.py`, `KubernetesAdapter.snapshot()`; console `apps/web/src/lib/topology.ts`, `src/components/{topology,applications}/` |
| **Runbook** | [onboarding.md](onboarding.md) |
| **Views** | [§ Views: 2D now, 3D later](#views-2d-now-3d-later) |

## Clusters the engine may read

Exactly two sources, both operator configuration outside the API:

| Role | Source | Namespaces | Chaos |
|---|---|---|---|
| `execution` | `KUBE_CONTEXT` | every namespace outside `SYSTEM_NAMESPACES` | yes, after safety validation (unchanged) |
| `discovery` | `DISCOVERY_CLUSTERS` (JSON list of `{context, namespaces}`) | only the listed ones | **never** |

`check_runtime()` refuses a discovery entry that repeats a context, equals `KUBE_CONTEXT`,
or lists a system or malformed namespace. The API can only choose among configured
contexts; it cannot add a context or widen a namespace list. In the local stack,
`ar cluster import` writes both the kubeconfig entry (a read-only ServiceAccount token)
and `DISCOVERY_CLUSTERS`; see [onboarding.md](onboarding.md).

## Contract: endpoints

| Endpoint | Returns | Errors |
|---|---|---|
| `GET /clusters` | `{items: [ClusterRef]}`; contacts no cluster | — |
| `GET /clusters/namespaces?context=` | `NamespaceList`: namespaces offered for onboarding with `workloads` and `access` (`readable`/`forbidden`/`error`); `source` is `namespaces` (listed), `workloads` (the engine may not list namespaces: fallback to those with workloads) or `configured` (discovery) | 404 unknown context, 503 unreachable |
| `GET /topology?context=&namespace=…` | `Topology` for the given namespaces, or all permitted ones | 404, 422 system/ungranted namespace, 503 |
| `POST /applications` | `ApplicationRead`, 201. Body `{name, context, namespaces}`; namespaces must be readable now | 422 with `loc` `body.context`/`body.namespaces`/`body.name`, 409 duplicate name, 503 |
| `GET /applications`, `GET /applications/{id}` | `cluster` is `null` when the context or a namespace is no longer authorized | 404 |
| `GET /applications/{id}/topology` | the application's `Topology` with `application_id` | 404, 409 no longer authorized, 503 |
| `DELETE /applications/{id}` | 204; removes the record only | 404 |

An omitted `context` means the execution cluster. An application is a database record
(`applications` table: name, context, namespaces). Creating or deleting one never writes
to a cluster, and experiments still target individual workloads.

## Contract: `autoresilience-topology/1`

```json
{
  "schema": "autoresilience-topology/1",
  "observed_at": "2026-10-18T17:54:53Z",
  "cluster": {"context": "kind-autoresilience", "role": "execution", "chaos_permitted": true, "namespaces": null},
  "scope": {"namespaces": ["shop"], "excluded_namespaces": ["kube-system", "…"]},
  "nodes": [{"id": "Deployment:shop/checkout", "kind": "Deployment", "namespace": "shop", "name": "checkout",
             "uid": "…", "labels": {}, "created_at": "…", "health": "DEGRADED",
             "health_reason": "1/2 ready (controller status)", "replicas": {…}, "pod": null,
             "service": null, "endpoint_slice": null, "node": null,
             "experiment_target": {"supported": true, "reason": "…"}, "events": [{…}]}],
  "edges": [{"id": "owns:Deployment:shop/checkout->ReplicaSet:shop/checkout-7d9", "type": "owns",
             "source": "…", "target": "…",
             "provenance": {"source": "metadata.ownerReferences", "detail": "… (UID verified)"},
             "attributes": {}}],
  "unknowns": [{"type": "owner_not_observed", "subject": "Pod:shop/migrate-x1", "resource": null,
                "namespace": null, "detail": "Owned by Job migrate; Job is not part of the topology"}],
  "counts": {"Deployment": 1, "Pod": 2},
  "traffic": {"observed": false, "detail": "…not traffic that was measured."},
  "application_id": null
}
```

- **Node kinds:** Deployment, ReplicaSet, StatefulSet, Pod, Service, EndpointSlice, Node.
  Cluster Nodes appear only when an in-scope Pod runs on them.
- **IDs** are `Kind:namespace/name` (`Node:name`): stable across snapshots; the UID is an
  attribute, so a recreated object keeps its ID.
- **Health** is read, not estimated: controller replicas for workloads (the Services rule),
  phase + Ready for Pods (`COMPLETED` for Succeeded), the Ready condition for Nodes, ready
  endpoints for Services and EndpointSlices. `UNKNOWN` when it cannot be read.
- **`experiment_target`** (Deployments and StatefulSets only): `supported` is true only on
  the execution cluster. It decides whether the console offers the builder; safety
  validation stays authoritative.
- **Events:** newest 10 per node, matched by involved object and UID, messages truncated
  to 500 characters.
- **Field allowlist:** no annotations (except the ReplicaSet revision), environment
  variables, commands or Secrets ever leave the builder; the engine cannot read Secrets or
  ConfigMaps at all.
- **Ordering** is deterministic (nodes by kind/namespace/name, edges by id, unknowns by
  type/subject).
- **Versioning:** additive fields stay `/1`; changing a field's meaning is `/2`.

### Edges: only what the API states

| Type | From → to | Read from | Verified by |
|---|---|---|---|
| `owns` | Deployment → ReplicaSet → Pod, StatefulSet → Pod, Service → EndpointSlice | `metadata.ownerReferences` with `controller: true` | owner UID matches the observed owner |
| `selects` | Service → Pod | `spec.selector` | all selector labels equal the Pod's, same namespace |
| `endpoint` | EndpointSlice → Pod | `endpoints[].targetRef` (`attributes`: ready/serving/terminating) | Pod UID |
| `slice_for` | EndpointSlice → Service | label `kubernetes.io/service-name`, only without an owner reference | Service observed |
| `scheduled_on` | Pod → Node | `spec.nodeName` | Node observed |

There is no "calls" or traffic edge: Kubernetes objects do not record runtime traffic,
and the engine never infers it (`traffic.observed` is always `false`).

### Unknowns: reported, never guessed

| Type | Meaning |
|---|---|
| `listing_forbidden` / `listing_failed` | a resource could not be listed (401/403, or another error), per namespace |
| `listing_truncated` | more than 2000 objects (500 events) in one listing |
| `owner_not_observed` | controller owner of an unlisted kind (Job, DaemonSet, CRD…) or not found |
| `owner_uid_mismatch` | the named owner exists but with another UID (recreated) |
| `node_not_observed` | `spec.nodeName` names a Node that is absent or not readable |
| `service_without_selector` | selector-less or ExternalName Service: no Pods linked by selector |
| `endpoint_target_not_observed` | an endpoint targets a Pod that is gone or out of scope, or a non-Pod |
| `malformed_object` | an object without name/namespace was skipped |

A refused listing never fails the whole snapshot; an unreachable API server does (503).

## Imported applications (P7, additive)

Applications created by an import ([imports.md](imports.md)) use the same contract; two
optional fields were added, so P6 clients that ignore unknown fields are unaffected and
`schema` stays `autoresilience-topology/1`:

- `nodes[].origin`: `{import_id, import_name, role: "application" | "load-generator",
  workload}` on objects whose ownership label `autoresilience.io/import-id` matches an
  import recorded in the database for that namespace (labels alone are never trusted).
- `imported` (application views only): `{import_id, name, status, source, namespace,
  declared, planned}`. `declared` lists relationships the source file states (Compose
  `depends_on`) as node-id pairs with `verified: false`; they are **not** in `edges` and
  never evidence of traffic. `planned` lists the plan's Deployments, StatefulSets and
  Services with `observed` (present in this snapshot or not).

Three sources stay distinct: **observed** (`edges`, from the Kubernetes API),
**declared** (`imported.declared`, from the file) and **planned** (`imported.planned`,
from the reviewed plan). `experiment_target` in an `ar-imp-*` namespace follows the
import's state (only a `READY` import's own workloads; never the load generator).

## Decisions

- **Snapshot on request, no cache.** Each request lists live state with bounded timeouts;
  the console re-reads every 15 s and, if a refresh fails, keeps showing the last snapshot
  labelled with its `observed_at` age instead of an empty graph.
- **Raw JSON lists** (`_preload_content=False`) instead of client models: the builder sees
  exactly what `kubectl get -o json` shows, tolerates unknown fields, and malformed data
  becomes an unknown rather than an exception.
- **Read-only remains structural.** New adapter calls are `list_*` only (tests assert it).
  The engine's ClusterRole gained get/list on ReplicaSets, Services, EndpointSlices,
  Events, Nodes and Namespaces (`infra/rbac/engine-rbac.yaml`, verified by `ar install`).
  An engine granted before P6 still works: those listings become `listing_forbidden`
  unknowns and namespaces fall back to `source: workloads` until `ar install` re-grants.
- **Imported clusters are discovery-only** (revises D-5). Attaching another cluster is
  read-only, namespace-scoped and explicit; experiments stay on the owned execution
  cluster. Granting chaos on an imported cluster would need its own reviewed path
  (namespaced ChaosEngine Role, prepared ChaosExperiment, policy review) and is not offered.
- **Console graph: React Flow** (`@xyflow/react` 12, MIT, maintained) for pan, zoom,
  selection and keyboard focus; the layout is a small deterministic layered layout in
  `src/lib/topology.ts` (namespace groups, kinds as columns, cluster Nodes on the right),
  so no layout library is needed. A List view offers the same nodes as a table.

## Views: 2D now, 3D later

The console separates three layers, so another renderer can be added without touching the
contract, filtering, selection or the inspector:

| Layer | Owns | Code |
|---|---|---|
| Contract | `autoresilience-topology/1` as returned by the API | `schemas/topology.py`, generated `src/lib/api/schema.ts` |
| View state (pure) | filters, search matches, selection, the selection's neighbourhood (direct relations + owner chain), presentation metadata (kind, health, edge and unknown meanings, line styles) | `src/lib/topology.ts`, `TopologyView` |
| Renderer | drawing, layout for its own space, camera, pointer and keyboard picking | `TopologyGraph` (2D, React Flow) |

A renderer receives only `TopologyRendererProps` (`nodes`, `edges`, `selected`, `matches`,
`onSelect`): filtered contract objects, never raw cluster data, and it reports selection by
node id. It must not add nodes, edges or attributes (no inferred traffic, no decorative
telemetry); the legend reads the same `EDGE_META`/`NODE_HEALTH_META`, so meaning stays
identical across views. The List view is the accessible equivalent of every renderer.

**Proposed 3D renderer** (not built; needs D-10 in `docs/product/v0.2-architecture.md`):
React Three Fiber, lazy-loaded as its own chunk only when the 3D view is chosen, 2D stays
the default. Requirements:

- **Layout:** deterministic from the snapshot (namespaces as planes or bands, kinds along one
  axis like the 2D columns); the same snapshot always renders the same scene.
- **Camera:** orbit, pan and zoom with mouse, touch (one-finger orbit, two-finger pan/pinch)
  and keyboard (arrow keys orbit, +/− zoom, a "reset view" control); bounded zoom and no
  camera roll; "fit to selection" and "fit all", like the 2D fit-view.
- **Selection:** click/tap picking and keyboard traversal of nodes in the List order, with
  the same `onSelect` contract; the selected node and its neighbourhood stay highlighted,
  others are dimmed, matching 2D.
- **Motion and access:** respect `prefers-reduced-motion` (no auto-rotation or animated
  transitions), canvas `aria-hidden` with the List view and inspector as the accessible
  path, a WebGL-unavailable fallback to 2D.
- **Budget:** the 3D chunk never loads for users who stay in 2D; no Three.js in the default
  console bundle (it stays small for the desktop shell).
