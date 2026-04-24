#!/usr/bin/env bash
# Poll Kubernetes + RabbitMQ every second and write a CSV row per sample.
#
# Usage:
#   ./scripts/collect-metrics.sh <namespace> <queue> <output.csv>
#
# Example:
#   ./scripts/collect-metrics.sh baseline baseline-queue results/raw/baseline-run1.csv
#
# Environment overrides:
#   RMQ_MGMT_URL  default http://localhost:31672 (NodePort from k8s/infra/02-rabbitmq.yaml)
#   RMQ_USER      default admin
#   RMQ_PASS      default cs5296-demo
#   SAMPLE_INTERVAL  seconds between samples (default 1)
#
# Run in the background, kill with SIGTERM when the experiment ends:
#   ./scripts/collect-metrics.sh baseline baseline-queue out.csv &
#   PID=$!
#   ...                               # run your load
#   kill "$PID"                       # writes final row, then exits cleanly.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <namespace> <queue> <output.csv>" >&2
  exit 1
fi

NS="$1"
QUEUE="$2"
OUT="$3"

RMQ_MGMT_URL="${RMQ_MGMT_URL:-http://localhost:31672}"
RMQ_USER="${RMQ_USER:-admin}"
RMQ_PASS="${RMQ_PASS:-cs5296-demo}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-1}"

for bin in kubectl curl jq; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: '$bin' not found in PATH" >&2
    exit 2
  fi
done

mkdir -p "$(dirname "$OUT")"
echo "ts_ms,pod_total,pod_ready,queue_depth,rate_in,rate_out,deliver_total,publish_total,cpu_avg_m" > "$OUT"

trap 'echo "collector stopped"; exit 0' TERM INT

# Extract average CPU millicores across all consumer pods. kubectl top returns
# lines like "consumer-xxx   37m   120Mi" and we only want the numeric CPU.
cpu_avg_millicores() {
  local raw
  raw=$(kubectl -n "$NS" top pods -l app=consumer --no-headers 2>/dev/null || true)
  if [[ -z "$raw" ]]; then
    echo 0
    return
  fi
  awk '{
    v = $2
    gsub(/m$/, "", v)
    # Some clusters return CPU in cores (e.g. "0.05"). Convert to millicores.
    if (index($2, "m") == 0) { v = v * 1000 }
    sum += v; n += 1
  } END {
    if (n > 0) printf "%.0f", sum / n; else print 0
  }' <<<"$raw"
}

while true; do
  ts_ms=$(date +%s%3N)

  pod_total=$(kubectl -n "$NS" get pods -l app=consumer --no-headers 2>/dev/null | wc -l | tr -d ' ')
  pod_ready=$(kubectl -n "$NS" get pods -l app=consumer -o json 2>/dev/null \
    | jq '[.items[] | select(.status.conditions[]? | .type=="Ready" and .status=="True")] | length')

  q_json=$(curl -fsS -u "${RMQ_USER}:${RMQ_PASS}" \
    "${RMQ_MGMT_URL}/api/queues/%2F/${QUEUE}" 2>/dev/null || echo '{}')
  q_depth=$(echo "$q_json"       | jq 'if .messages == null then 0 else .messages end')
  rate_in=$(echo "$q_json"       | jq 'if .message_stats.publish_details.rate == null then 0 else .message_stats.publish_details.rate end')
  rate_out=$(echo "$q_json"      | jq 'if .message_stats.deliver_details.rate == null then 0 else .message_stats.deliver_details.rate end')
  deliver_total=$(echo "$q_json" | jq 'if .message_stats.deliver == null then 0 else .message_stats.deliver end')
  publish_total=$(echo "$q_json" | jq 'if .message_stats.publish == null then 0 else .message_stats.publish end')

  cpu_avg=$(cpu_avg_millicores)

  echo "${ts_ms},${pod_total},${pod_ready},${q_depth},${rate_in},${rate_out},${deliver_total},${publish_total},${cpu_avg}" >> "$OUT"
  sleep "$SAMPLE_INTERVAL"
done
