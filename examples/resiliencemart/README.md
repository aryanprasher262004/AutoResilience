# ResilienceMart: import acceptance fixture

A small, functional storefront for testing application imports (P7) by hand. It is a
**compatibility fixture**: passing with it shows that this supported subset works end to
end, not that arbitrary third-party applications import. No credentials, no host mounts,
no privileges; images pinned by tag and digest.

| Service | Image | Replicas | Role |
|---|---|---|---|
| `storefront` | podinfo 6.7.1 | 3 | UI and API; `POST /api/echo` calls catalog and checkout and shows each answer or failure. **Healthy, replicated.** |
| `catalog` | podinfo 6.7.1 | 2 | API using the cache (`/cache/<key>`). |
| `checkout` | podinfo 6.7.1 | 2 | API, **deliberately slow**: a replacement Pod is not ready for 20 s, so recovery is visibly slower. |
| `cache` | Redis 7.4.1 | 1 | **Single point of failure**: safety validation refuses pod-delete on it. |

Files: `compose.yaml` (Docker Compose), `k8s/resiliencemart.yaml` (the same as
Kubernetes manifests), `unsafe-compose.yaml` (what an import refuses; never run it).

## 1. Run it with Docker (optional)

```bash
docker compose -f examples/resiliencemart/compose.yaml up -d --wait
curl -s http://127.0.0.1:8080/version                       # {"version":"6.7.1",...}
curl -s -XPOST http://127.0.0.1:8080/api/echo -d order      # ["order","order"]: both backends answered
docker compose -f examples/resiliencemart/compose.yaml stop checkout
curl -s -XPOST http://127.0.0.1:8080/api/echo -d order      # second entry: "backend ... call failed"
docker compose -f examples/resiliencemart/compose.yaml down
```

Open http://127.0.0.1:8080 for the UI ("ResilienceMart storefront"). Ports 8080-8082
(one per replica, loopback only) must be free.

## 2. Import it

Prerequisites: the dev cluster, database and provisioner identity, the API with
`PROVISIONER_KUBECONFIG`, the console (commands in `docs/imports.md` → Runbook).

1. **Applications → Import application → Docker Compose file**, choose
   `examples/resiliencemart/compose.yaml`, name it `resiliencemart`, **Check it**.
2. **Security review**, expected: 0 blocking, 1 warning (`/data` of `cache` becomes an
   empty per-Pod directory), notes for pinned images, host ports not published, start
   order not enforced. Nothing has been stored or deployed.
3. **Review the plan**: 4 Deployments, 4 Services, isolation (quota, limits, network
   policy), chaos preparation, all in `ar-imp-resiliencemart`. Under *Load generator*,
   tick `storefront` and `checkout`, path `/version`, **Update the plan**, then
   **Save reviewed import**. Still nothing is deployed.
4. Optional security check: import `unsafe-compose.yaml` instead. Expected: blocking
   findings for privileged, the Docker socket, host paths, `network_mode: host`, `build`,
   `cap_add`, an unresolved `${WORKER_TAG}` and `secrets`; it cannot be saved.

## 3. Deploy and verify

5. On the import's page, **Deploy** → the dialog lists exactly what will happen and the
   plan digest → **Deploy this plan**. Status: *Deploying*, each workload's readiness
   updates every few seconds; *Ready* typically within a minute (images are pulled first).
6. Storefront check from your terminal (your own credentials, read-only port-forward):

   ```bash
   kubectl --context kind-autoresilience -n ar-imp-resiliencemart port-forward svc/storefront 8080:9898
   curl -s -XPOST http://127.0.0.1:8080/api/echo -d order   # ["order","order"]
   ```

7. Isolation check (optional): `kubectl --context kind-autoresilience -n ar-imp-resiliencemart
   exec deploy/autoresilience-loadgen -- python -c "import urllib.request as u;
   u.urlopen('http://frontend.shop.svc.cluster.local/', timeout=3)"` fails (no route to
   other namespaces); the same for `http://catalog:9898/version` succeeds.

## 4. Topology

8. **Open topology**. Expected: Services → EndpointSlices → Pods, Deployments → ReplicaSets
   → Pods, all tagged *imported*; the load generator tagged *load gen*. The *Imported
   application* card lists planned vs observed resources and the declared `depends_on`
   relations, which are **not** drawn as lines. Selecting `storefront` shows *Imported*
   and *Declared in the source file* in the inspector.
9. Tooltip check: hover or Tab to the relationship toggles (`slice for` is the last);
   each tooltip stays fully on screen, also at phone width.

## 5. Experiments

10. Inspector on **storefront** → *New experiment* → pod-delete, 1 affected replica,
    30 s, GRACEFUL → validate and run. Expected: COMPLETED, recovery within seconds,
    no client-observed outage (load generator evidence), score ≈ 100.
11. Same on **checkout** with FORCE. Expected: COMPLETED, recovery around 20–25 s (the
    slow readiness), score slightly lower (≈ 96 in our run).
12. **cache**: validation fails `min_healthy_replicas_after_fault` (one replica; nothing
    would be left serving). Nothing is injected.
13. The load generator is never offered as a target.

## 6. Clean up

14. Import page → **Remove deployment** → type `resiliencemart` → **Remove**. Status
    *Removing*, then *Removed* when the namespace is gone. Only `ar-imp-resiliencemart`
    is deleted; experiment history stays.
15. Ownership check (optional, before step 14): `kubectl --context kind-autoresilience -n
    ar-imp-resiliencemart create configmap intruder --from-literal=a=b`. Removal is then
    refused (“contains objects this import did not create (configmaps/intruder)”) and the
    namespace stays. Delete the ConfigMap and remove again.
16. **Forget record** removes the saved import.

## Troubleshooting

| Problem | What to do |
|---|---|
| Deploy is disabled | Settings → Kubernetes access → Application imports explains why; usually `PROVISIONER_KUBECONFIG` is not set (`./scripts/dev-provisioner.sh`). |
| `Image pull failed` | The node needs internet access to `ghcr.io` and Docker Hub. Retry once online. |
| Deploying for minutes | First pulls can be slow; it fails after 5 minutes with the reason. Retry or remove. |
| Client evidence unavailable | You did not tick a load target for that Service; import again with one. |
| Baseline fails right after deploying | Prometheus needs about a minute of samples; start the experiment a little later. |
| `ar-imp-resiliencemart` left behind after revoking the provisioner | `kubectl --context kind-autoresilience delete namespace ar-imp-resiliencemart` (it is labelled `autoresilience.io/owner=import`). |
