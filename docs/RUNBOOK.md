# Experiment Runbook

Step-by-step instructions for running the real experiment end to end on
AWS EC2. Every step lists a verification command and the expected
output; if anything mismatches, stop and debug before moving on.

## Prerequisites

On your laptop:

* DockerHub account with push rights
* `docker` v24+, `kubectl`, `ssh`, `git`, Python 3.10+
* `.env` populated (copy from `.env.example`): `DOCKERHUB_USER`,
  `EC2_PUBLIC_IP`, `EC2_SSH_KEY`

On your AWS account:

* An EC2 `t3.medium` (or bigger) in any region you have latency to
* Security group opens TCP **22** (ssh), **6443** (kube-api, your IP
  only), **30567** (RabbitMQ AMQP), **31672** (RabbitMQ management)
* An Ubuntu 22.04 LTS AMI

## Step 1 — Build and push the consumer image (on your laptop)

```bash
source .env
docker build -t "$CONSUMER_IMAGE" consumer/
docker push "$CONSUMER_IMAGE"
```

**Verify:**

```bash
docker run --rm "$CONSUMER_IMAGE" java -jar /app/consumer.jar --help >/dev/null
```

Exit code 0 — image runs, no `ClassNotFoundException`.

## Step 2 — Provision the EC2 host

1. Launch `t3.medium` Ubuntu 22.04 with 20 GiB root disk.
2. Attach an SSH key; update `EC2_SSH_KEY` in `.env`.
3. Copy your IP into `.env` as `EC2_PUBLIC_IP`.

**Verify:**

```bash
ssh -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP" 'uname -a && free -h'
```

You should see `Linux ... aarch64` or `x86_64`, and at least 3 GiB free.

## Step 3 — Install K3s + RabbitMQ + KEDA (on the EC2 host)

On the host:

```bash
sudo apt-get update -y && sudo apt-get install -y git curl jq
git clone https://github.com/<YOUR_ORG>/CS5296-Group5-Autoscaling.git
cd CS5296-Group5-Autoscaling
./scripts/setup.sh
```

**Verify (~3–5 minutes):**

```bash
kubectl get nodes
# NAME      STATUS   ROLES                  AGE   VERSION
# ip-...    Ready    control-plane,master   ...   v1.28.x

kubectl get ns
# rabbitmq, baseline, keda, keda (operator), kube-system all Active

kubectl -n rabbitmq get pod
# rabbitmq-0  1/1  Running

kubectl -n keda get deploy keda-operator
# READY 1/1
```

Expected output for queues:

```bash
kubectl -n rabbitmq exec statefulset/rabbitmq -- rabbitmqctl list_queues
# baseline-queue  0
# keda-queue      0
```

## Step 4 — Deploy both experiment groups

```bash
export CONSUMER_IMAGE=<your-dockerhub>/cs5296-consumer:v1.0
./scripts/deploy-baseline.sh
./scripts/deploy-keda.sh
```

**Verify:**

```bash
kubectl -n baseline get deploy,hpa,pod
# deployment.apps/consumer  1/1
# horizontalpodautoscaler.autoscaling/consumer-hpa  Deployment/consumer  cpu: 0%/50%

kubectl -n keda get deploy,scaledobject,hpa,pod
# deployment.apps/consumer 1/1
# scaledobject.keda.sh/consumer-scaledobject  baseline  READY=True  ACTIVE=False
# horizontalpodautoscaler.autoscaling/keda-hpa-consumer-scaledobject   <-- created by KEDA
```

**Common failure modes:**

* *HPA shows `TARGETS: <unknown>/50%`* — metrics-server not healthy. Run
  `kubectl -n kube-system logs deploy/metrics-server` and check for TLS
  errors; `scripts/setup.sh` adds `--kubelet-insecure-tls` but if you
  installed metrics-server manually you must repeat that patch.
* *ScaledObject `READY=False`* — KEDA cannot reach RabbitMQ. Check
  `kubectl -n keda logs deploy/keda-operator | tail`; usually the host in
  `k8s/keda/triggerauth.yaml` is wrong.
* *Consumer pod in `CrashLoopBackOff`* — wrong credentials. Ensure the
  RabbitMQ Secret exists in both namespaces (`deploy-baseline.sh` and
  `deploy-keda.sh` create it automatically).

## Step 5 — Run one baseline trial

From your **laptop** (so the producer load is not on the same machine as
the cluster):

```bash
cd load-test
pip install -r requirements.txt
cd ..
export RABBITMQ_URL="amqp://admin:cs5296-demo@${EC2_PUBLIC_IP}:30567"
ssh -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP" \
    "cd CS5296-Group5-Autoscaling && ./scripts/run-experiment.sh baseline 1"
```

(Alternative: run `run-experiment.sh` on the EC2 host and have the
producer inside the cluster via `kubectl run`. The `run-experiment.sh`
script starts both and kills the collector on exit.)

**Verify:**

```bash
scp -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP":~/CS5296-Group5-Autoscaling/results/raw/baseline-run1.csv ./results/raw/
wc -l results/raw/baseline-run1.csv
# >= 300 lines (5 min @ 1 Hz)

head -1 results/raw/baseline-run1.csv
# ts_ms,pod_total,pod_ready,queue_depth,rate_in,rate_out,deliver_total,publish_total,cpu_avg_m
```

Inspect the data for obvious problems:

```bash
awk -F, 'NR>1 && $4>5000 {found=1} END {print "queue peaked above 5000:", found}' \
    results/raw/baseline-run1.csv
awk -F, 'NR>1 {m=($3>m?$3:m)} END {print "peak pods:", m}' \
    results/raw/baseline-run1.csv
```

Expected: peak queue > 5 000, peak pods ≥ 3.

## Step 6 — Repeat for the other three trials

```bash
ssh -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP" \
    "cd CS5296-Group5-Autoscaling && ./scripts/run-experiment.sh baseline 2"
ssh -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP" \
    "cd CS5296-Group5-Autoscaling && ./scripts/run-experiment.sh keda 1"
ssh -i "$EC2_SSH_KEY" ubuntu@"$EC2_PUBLIC_IP" \
    "cd CS5296-Group5-Autoscaling && ./scripts/run-experiment.sh keda 2"
scp -i "$EC2_SSH_KEY" "ubuntu@$EC2_PUBLIC_IP:~/CS5296-Group5-Autoscaling/results/raw/*.csv" ./results/raw/
```

## Step 7 — Generate figures

```bash
# First DELETE the placeholder synthetic data:
rm -f results/raw/PLACEHOLDER.md      # real data now lives here
cd analysis
pip install -r requirements.txt
python plot.py
```

Inspect `results/summary.csv`:

```bash
column -ts, results/summary.csv
```

Sanity checks on the real numbers:

| Column | Expected range |
|---|---|
| `reaction_latency_s` (baseline) | 15–35 |
| `reaction_latency_s` (keda) | 3–12 |
| `peak_pods` (both) | 5–10 |
| `drain_time_s` | 150–300 (both) |
| `avg_throughput` | 30–50 (both) |

If baseline reaction is *faster* than KEDA, something is wrong — most
commonly the HPA's `stabilizationWindowSeconds: 0` was overridden, or
the KEDA poll interval was bumped. Re-check
`k8s/baseline/hpa.yaml` and `k8s/keda/scaledobject.yaml`.

## Step 8 — Teardown

On the EC2 host:

```bash
./scripts/teardown.sh
```

From the AWS Console: **terminate the instance**. Forgetting this costs
~$0.04/h of credit.

## Troubleshooting cheat-sheet

| Symptom | Likely cause | Fix |
|---|---|---|
| `kubectl top pods` prints `error: Metrics API not available` | metrics-server not ready | `kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s` and re-patch with `--kubelet-insecure-tls`. |
| Producer `pika.exceptions.AMQPConnectionError` | Security group blocks 30567 | Open TCP 30567 from your laptop IP. |
| Queue depth never drops | Consumer crashed between messages | `kubectl -n baseline logs deploy/consumer --previous`. Common cause: wrong RabbitMQ password in the Secret. |
| Only 1 pod ever appears in baseline | Message processing too cheap to raise CPU | Increase `CONSUMER_PROCESS_MS` to e.g. `400`. |
| Only 1 pod ever appears in KEDA | Queue never crosses threshold | Lower `value: "100"` in `scaledobject.yaml` to e.g. `20`. |
