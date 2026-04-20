#!/usr/bin/env bash
# Tear down all experiment resources. Kubernetes itself stays installed.
#
# Does NOT stop the EC2 instance; remember to do that from the AWS Console
# to avoid further billing.
set -euo pipefail

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
ignore() { "$@" >/dev/null 2>&1 || true; }

say "Removing experiment namespaces (this also deletes pods, services, HPA, ScaledObjects, Secrets)..."
ignore kubectl delete ns baseline
ignore kubectl delete ns keda

say "Removing RabbitMQ..."
ignore kubectl delete ns rabbitmq

say "Uninstalling KEDA..."
ignore helm uninstall keda --namespace keda
ignore kubectl delete ns keda

say "Done. To also remove K3s itself:"
echo "    /usr/local/bin/k3s-uninstall.sh"
echo ""
echo "Remember: stop / terminate the EC2 instance via the AWS Console."
