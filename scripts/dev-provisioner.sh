#!/usr/bin/env bash
# Development: the dedicated identity that deploys imported applications (P7).
# Applies infra/rbac/provisioner.yaml to the kind cluster and writes a kubeconfig
# holding only that ServiceAccount's token. Run the API with
#   PROVISIONER_KUBECONFIG=<printed path>
# Idempotent. The local stack (`ar install`) does the same for the engine container.
# Revoke: kubectl --context kind-autoresilience delete -f infra/rbac/provisioner.yaml
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CONTEXT=kind-autoresilience
NAMESPACE=autoresilience-system
HOME_DIR=${AUTORESILIENCE_HOME:-$HOME/.autoresilience}
OUT="$HOME_DIR/dev-provisioner.kubeconfig"
k() { kubectl --context "$CONTEXT" "$@"; }

# Only the kind cluster this repository creates (scripts/dev-cluster.sh).
nodes=$(k get nodes -o jsonpath='{.items[*].metadata.name}')
for node in $nodes; do
  case "$node" in autoresilience-*) ;; *) echo "$CONTEXT points at node $node; refusing" >&2; exit 1 ;; esac
done

if ! k get namespace "$NAMESPACE" >/dev/null 2>&1; then
  k create namespace "$NAMESPACE"
  k label namespace "$NAMESPACE" app.kubernetes.io/managed-by=autoresilience autoresilience.io/owner=local-manager
fi
k apply -f "$ROOT/infra/rbac/provisioner.yaml"

token=""
for _ in $(seq 30); do
  token=$(k -n "$NAMESPACE" get secret autoresilience-provisioner-token -o jsonpath='{.data.token}' 2>/dev/null || true)
  [ -n "$token" ] && break
  sleep 1
done
[ -n "$token" ] || { echo "the provisioner token was not issued" >&2; exit 1; }
ca=$(k -n "$NAMESPACE" get secret autoresilience-provisioner-token -o jsonpath='{.data.ca\.crt}')
server=$(kubectl config view --raw --minify --context "$CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')

mkdir -p "$HOME_DIR"
umask 077
cat >"$OUT" <<YAML
apiVersion: v1
kind: Config
clusters:
  - name: $CONTEXT
    cluster: {server: "$server", certificate-authority-data: "$ca"}
users:
  - name: autoresilience-provisioner
    user: {token: "$(printf %s "$token" | base64 --decode)"}
contexts:
  - name: $CONTEXT
    context: {cluster: $CONTEXT, user: autoresilience-provisioner}
current-context: $CONTEXT
YAML
chmod 600 "$OUT"
echo "Provisioner kubeconfig: $OUT"
echo "Start the API with: PROVISIONER_KUBECONFIG=$OUT"
