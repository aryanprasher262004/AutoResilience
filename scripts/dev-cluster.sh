#!/usr/bin/env bash
# Create (idempotently) the local kind cluster and deploy the sample shop workload.
# Requires: docker (running), kind, kubectl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER=autoresilience
CONTEXT="kind-${CLUSTER}"

if ! kind get clusters | grep -qx "${CLUSTER}"; then
  kind create cluster --config "${ROOT}/infra/kind/cluster.yaml" --wait 120s
fi

kubectl --context "${CONTEXT}" apply -f "${ROOT}/infra/sample-app/shop.yaml"
kubectl --context "${CONTEXT}" -n shop rollout status deployment/frontend --timeout=180s
kubectl --context "${CONTEXT}" -n shop rollout status deployment/checkout --timeout=180s
kubectl --context "${CONTEXT}" -n shop rollout status statefulset/cart-redis --timeout=180s
kubectl --context "${CONTEXT}" -n shop get deploy,sts,pods

echo "Cluster ready. Point the API at it with KUBE_CONTEXT=${CONTEXT}"
