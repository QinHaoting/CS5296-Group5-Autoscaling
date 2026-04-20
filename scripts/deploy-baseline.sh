#!/usr/bin/env bash
# Deploy the HPA baseline group.
#
# Usage:
#   export CONSUMER_IMAGE=yourname/cs5296-consumer:v1.0
#   ./scripts/deploy-baseline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_DIR="$REPO_ROOT/k8s/baseline"

: "${CONSUMER_IMAGE:?Set CONSUMER_IMAGE=<dockerhub>/cs5296-consumer:v1.0 before running.}"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }

say "Applying HPA manifests with image: $CONSUMER_IMAGE"
# Use sed instead of kustomize to keep dependencies minimal.
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

for f in "$MANIFEST_DIR"/*.yaml; do
  out="$TMP_DIR/$(basename "$f")"
  sed "s#CHANGEME/cs5296-consumer:v1.0#${CONSUMER_IMAGE}#g" "$f" > "$out"
done
kubectl apply -f "$TMP_DIR"

say "Waiting for deployment to become ready..."
kubectl -n baseline rollout status deployment/consumer --timeout=180s

say "Current state:"
kubectl -n baseline get deploy,hpa,pod

say "HPA baseline ready. Scaling target: CPU > 50% -> up to 10 replicas."
