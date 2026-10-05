#!/usr/bin/env bash
# Create (idempotently) the local kind cluster, deploy the sample shop workload and
# install Prometheus. Requires: docker (running), kind, kubectl, helm.
# After changing infra/kind/cluster.yaml port mappings, delete the cluster first:
#   kind delete cluster --name autoresilience
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER=autoresilience
CONTEXT="kind-${CLUSTER}"
PROMETHEUS_CHART_VERSION=29.35.0

if ! kind get clusters | grep -qx "${CLUSTER}"; then
  kind create cluster --config "${ROOT}/infra/kind/cluster.yaml" --wait 120s
fi

kubectl --context "${CONTEXT}" apply -f "${ROOT}/infra/sample-app/shop.yaml"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null
helm upgrade --install prometheus prometheus-community/prometheus \
  --kube-context "${CONTEXT}" \
  --namespace monitoring --create-namespace \
  --version "${PROMETHEUS_CHART_VERSION}" \
  --values "${ROOT}/monitoring/prometheus/values.yaml" \
  --wait --timeout 5m

for workload in deployment/frontend deployment/checkout deployment/loadgen statefulset/cart-redis; do
  kubectl --context "${CONTEXT}" -n shop rollout status "${workload}" --timeout=180s
done
kubectl --context "${CONTEXT}" -n shop get deploy,sts,pods
kubectl --context "${CONTEXT}" -n monitoring get pods

for _ in $(seq 30); do
  curl -sf http://localhost:9090/-/ready >/dev/null && break
  sleep 2
done
curl -sf http://localhost:9090/-/ready >/dev/null || { echo "Prometheus not reachable on localhost:9090" >&2; exit 1; }

echo "Cluster ready. API settings: KUBE_CONTEXT=${CONTEXT} PROMETHEUS_URL=http://localhost:9090"
