#!/usr/bin/env bash
# One-shot bootstrap for the CS5296 experiment on a fresh Ubuntu 22.04 host.
#
# What it does:
#   1. Install K3s (single-node Kubernetes).
#   2. Install Helm 3.
#   3. Install metrics-server (required for HPA).
#   4. Install KEDA via Helm.
#   5. Deploy the common RabbitMQ + namespaces.
#
# Re-running this script is safe: each step checks whether the target is
# already present and skips if so.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\n\033[1;33m[!]\033[0m %s\n" "$*"; }

need_root() {
  if [[ $EUID -ne 0 ]] && ! sudo -n true 2>/dev/null; then
    warn "This script needs sudo. Please enter your password when prompted."
  fi
}

install_k3s() {
  if command -v k3s >/dev/null 2>&1; then
    say "K3s already installed, skipping."
    return
  fi
  say "Installing K3s..."
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 644" sh -

  mkdir -p "$HOME/.kube"
  sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
  sudo chown "$USER":"$USER" "$HOME/.kube/config"
  export KUBECONFIG="$HOME/.kube/config"
}

wait_for_nodes() {
  say "Waiting for node to become Ready..."
  for _ in {1..30}; do
    if kubectl get nodes 2>/dev/null | grep -q " Ready "; then
      kubectl get nodes
      return
    fi
    sleep 2
  done
  warn "Node never became Ready. Inspect 'kubectl get nodes'."
  exit 1
}

install_helm() {
  if command -v helm >/dev/null 2>&1; then
    say "Helm already installed ($(helm version --short))."
    return
  fi
  say "Installing Helm..."
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
}

install_metrics_server() {
  if kubectl -n kube-system get deploy metrics-server >/dev/null 2>&1; then
    say "metrics-server already present."
    return
  fi
  say "Installing metrics-server..."
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  # K3s uses self-signed certs for kubelet, so we must allow insecure TLS.
  kubectl -n kube-system patch deploy metrics-server --type=json -p='[
    {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}
  ]'
  kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
}

install_keda() {
  if kubectl get ns keda >/dev/null 2>&1; then
    say "KEDA namespace already exists, skipping install."
    return
  fi
  say "Installing KEDA via Helm..."
  helm repo add kedacore https://kedacore.github.io/charts
  helm repo update
  helm install keda kedacore/keda --namespace keda --create-namespace --wait
}

deploy_common() {
  say "Applying namespaces + RabbitMQ..."
  kubectl apply -f "$REPO_ROOT/k8s/infra/"
  kubectl -n rabbitmq rollout status statefulset/rabbitmq --timeout=180s
}

main() {
  need_root
  install_k3s
  wait_for_nodes
  install_helm
  install_metrics_server
  install_keda
  deploy_common
  say "Setup complete! Next: ./scripts/deploy-baseline.sh and ./scripts/deploy-keda.sh"
}

main "$@"
