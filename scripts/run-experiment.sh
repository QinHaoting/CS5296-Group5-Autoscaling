#!/usr/bin/env bash
# Run one end-to-end experiment trial.
#
# Usage:
#   ./scripts/run-experiment.sh <baseline|keda> <run_number>
#
# Example:
#   ./scripts/run-experiment.sh baseline 1
#
# What happens:
#   1. Reset the target deployment to 1 replica and purge the queue.
#   2. Start the metrics collector in the background.
#   3. Launch the Python producer.
#   4. Wait out the observation window (default 180 s).
#   5. Stop the collector. The CSV in results/raw/ is the artefact.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <baseline|keda> <run_number>" >&2
  exit 1
fi

GROUP="$1"
RUN="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

case "$GROUP" in
  baseline)
    NS=baseline
    QUEUE=baseline-queue
    ;;
  keda)
    NS=keda
    QUEUE=keda-queue
    ;;
  *)
    echo "First arg must be 'baseline' or 'keda'." >&2
    exit 2
    ;;
esac

RABBITMQ_URL="${RABBITMQ_URL:-amqp://admin:cs5296-demo@localhost:30567}"
PATTERN="${PATTERN:-$REPO_ROOT/load-test/patterns/burst.yaml}"
OBS_DURATION="${OBS_DURATION:-180}"

METRICS_CSV="$REPO_ROOT/results/raw/${GROUP}-run${RUN}.csv"
SENDLOG_CSV="$REPO_ROOT/results/raw/${GROUP}-run${RUN}-sendlog.csv"
mkdir -p "$(dirname "$METRICS_CSV")"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }

say "Experiment: group=$GROUP run=$RUN queue=$QUEUE"

say "Resetting deployment to 1 replica..."
kubectl -n "$NS" scale deploy/consumer --replicas=1 >/dev/null
kubectl -n "$NS" rollout status deploy/consumer --timeout=120s >/dev/null

say "Purging queue $QUEUE..."
kubectl -n rabbitmq exec statefulset/rabbitmq -- \
  rabbitmqctl purge_queue "$QUEUE" >/dev/null 2>&1 || true

say "Starting metrics collector -> $METRICS_CSV"
"$SCRIPT_DIR/collect-metrics.sh" "$NS" "$QUEUE" "$METRICS_CSV" &
COLLECT_PID=$!
cleanup() {
  if kill -0 "$COLLECT_PID" 2>/dev/null; then
    kill -TERM "$COLLECT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Let the collector capture a baseline before producing load.
sleep 10

say "Launching producer..."
(cd "$REPO_ROOT/load-test" && \
  python producer.py \
    --rabbitmq "$RABBITMQ_URL" \
    --queue "$QUEUE" \
    --pattern "$PATTERN" \
    --output "$SENDLOG_CSV")

say "Observing post-burst behaviour for ${OBS_DURATION}s..."
sleep "$OBS_DURATION"

say "Stopping collector."
cleanup

say "Trial done."
echo "  metrics: $METRICS_CSV"
echo "  sendlog: $SENDLOG_CSV"
