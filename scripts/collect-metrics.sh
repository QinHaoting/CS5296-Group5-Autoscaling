#!/usr/bin/env bash
# Poll kubernetes + RabbitMQ every second and write a CSV row per sample.
#
# Usage:
#   ./scripts/collect-metrics.sh <namespace> <queue> <output.csv>
#
# Example:
#   ./scripts/collect-metrics.sh baseline baseline-queue results/raw/hpa-run1.csv
#
# Run in the background, kill with SIGTERM when the experiment ends:
#   ./scripts/collect-metrics.sh baseline baseline-queue out.csv &
#   PID=$!
#   ...  # run your load
#   kill "$PID"
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
PYTHON_BIN="${PYTHON_BIN:-python3}"

timestamp_ms() {
  local ts
  ts=$(date +%s%3N 2>/dev/null || true)
  if [[ "$ts" == *N ]]; then
    "$PYTHON_BIN" -c 'import time; print(int(time.time() * 1000))'
  else
    printf '%s\n' "$ts"
  fi
}

mkdir -p "$(dirname "$OUT")"
echo "ts_ms,pod_total,pod_ready,queue_depth,rate_in,rate_out,deliver_total,publish_total" > "$OUT"

trap 'echo "collector stopped"; exit 0' TERM INT

while true; do
  ts_ms=$(timestamp_ms)

  pods_json=$(kubectl -n "$NS" get pods -l app=consumer -o json --request-timeout=5s 2>/dev/null \
    || echo '{"items":[]}')
  pod_total=$(echo "$pods_json" | jq '.items | length')
  pod_ready=$(echo "$pods_json" \
    | jq '[.items[] | select(any(.status.conditions[]?; .type=="Ready" and .status=="True"))] | length')

  q_json=$(curl --max-time 5 -fsS -u "${RMQ_USER}:${RMQ_PASS}" \
    "${RMQ_MGMT_URL}/api/queues/%2F/${QUEUE}" 2>/dev/null || echo '{}')
  q_depth=$(echo "$q_json"    | jq 'if .messages == null then 0 else .messages end')
  rate_in=$(echo "$q_json"    | jq 'if .message_stats.publish_details.rate == null then 0 else .message_stats.publish_details.rate end')
  rate_out=$(echo "$q_json"   | jq 'if .message_stats.deliver_details.rate == null then 0 else .message_stats.deliver_details.rate end')
  deliver_total=$(echo "$q_json" | jq 'if .message_stats.deliver == null then 0 else .message_stats.deliver end')
  publish_total=$(echo "$q_json" | jq 'if .message_stats.publish == null then 0 else .message_stats.publish end')

  echo "${ts_ms},${pod_total},${pod_ready},${q_depth},${rate_in},${rate_out},${deliver_total},${publish_total}" >> "$OUT"
  sleep 1
done
