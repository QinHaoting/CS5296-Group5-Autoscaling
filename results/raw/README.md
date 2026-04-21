# Raw Experiment Data — Baseline HPA vs KEDA

This directory contains the **raw artefacts** of the autoscaling comparison
experiment executed on 2026-04-20. All numbers in the final report and all
figures in `results/figures/` are derived from the CSVs committed here.

## 1. Experiment design at a glance

| Item | Value |
|---|---|
| Date (UTC) | 2026-04-20 19:58:40 → 20:47:51 |
| Wall time | 49 min 11 s |
| Node | 1× AWS EC2 `m5.large` (2 vCPU, 8 GiB, us-west-2) |
| Kubernetes | K3s v1.30 (single-node, embedded etcd) |
| RabbitMQ | Bitnami `3.13`, `limits.cpu=1000m`, `limits.memory=1Gi`, `tcpSocket:5672` probes |
| Consumer | Spring Boot 3 CPU-bound worker, `200 ms` processing delay per message |
| Consumer resources | `requests 100m/128Mi`, `limits 300m/256Mi`, image `htasteqin/cs5296-consumer:v1.0` |
| Baseline scaler | HPA on `cpu`, `min=1`, `max=6`, `target=50%`, scale-down `stabilizationWindowSeconds=60` |
| KEDA scaler | RabbitMQ `queueLength=10`, `min=1`, `max=6`, cooldown `60s`, polling `30s` |
| Load pattern | `load-test/patterns/burst.yaml` |
| Trials per group | 3 |
| Inter-trial cooldown | 120 s |

### `burst.yaml` (the pattern every trial uses)

| Phase | Duration | Rate (msg/s) | Purpose |
|---|---|---|---|
| warm-up | 10 s | 5 | let the collector capture the steady state at `replicas=1` |
| burst | 10 s | 1000 (target) | flash-crowd; HPA/KEDA must react |
| silence | 180 s | 0 | drain window + scale-down observation |

Each trial therefore runs for `10 (pre-collector) + 10 + 10 + 180 = 210 s`
of load injection, followed by `180 s` of post-burst observation window
— a nominal trial length of **~390 s** (measured 391–393 s).

## 2. File manifest

Per trial two CSVs are produced:

1. `{group}-run{N}.csv` — time series from `scripts/collect-metrics.sh` (1 Hz,
   written to disk every second; effective cadence ~2 s due to `kubectl`+`curl`+`jq`
   round-trip on a 2 vCPU node).
2. `{group}-run{N}-sendlog.csv` — every message emission timestamped by the
   Python producer.

Plus:

- `experiment.log` — full stdout/stderr from `runner.sh` (tee'd out of tmux).
  This file is covered by `*.log` in `.gitignore`; use `git add -f
  results/raw/experiment.log` if you want it tracked as evidence.

### Schema: `{group}-run{N}.csv`

| Column | Unit | Source |
|---|---|---|
| `ts_ms` | ms since epoch | `date +%s%3N` |
| `pod_total` | count | `kubectl get pods -l app=consumer` |
| `pod_ready` | count | `kubectl get pods -o json | jq '...Ready...'` |
| `queue_depth` | messages | RabbitMQ `/api/queues/.../messages` |
| `rate_in` | msg/s | `.message_stats.publish_details.rate` |
| `rate_out` | msg/s | `.message_stats.deliver_details.rate` |
| `deliver_total` | cumulative msgs | `.message_stats.deliver` |
| `publish_total` | cumulative msgs | `.message_stats.publish` |

### Schema: `{group}-run{N}-sendlog.csv`

| Column | Meaning |
|---|---|
| `seq` | 0-based index of the message |
| `phase_idx` | which pattern phase (0=warm-up, 1=burst, 2=silence) |
| `send_ts_ms` | epoch ms the producer called `basic_publish` |

## 3. Trial manifest

| Trial | Group | Run | Start (UTC) | End (UTC) | Elapsed | Msgs sent | Metrics rows |
|-------|----------|-----|-------------|-----------|---------|-----------|--------------|
| 1 | baseline | 1 | 19:58:40 | 20:05:13 | 393 s | 7 446 | 193 |
| 2 | baseline | 2 | 20:07:13 | 20:13:45 | 392 s | 7 398 | 195 |
| 3 | baseline | 3 | 20:15:45 | 20:22:16 | 391 s | 7 510 | 190 |
| 4 | keda | 1 | 20:24:16 | 20:30:48 | 392 s | 7 257 | 203 |
| 5 | keda | 2 | 20:32:48 | 20:39:19 | 391 s | 7 274 | 184 |
| 6 | keda | 3 | 20:41:19 | 20:47:51 | 392 s | 7 105 | 185 |

Inter-trial gap in every pair is 120 s (`runner.sh` cooldown).

## 4. Headline results (mean of 3 runs)

Computed by `analysis/plot.py`; full per-trial breakdown is in
`../summary.csv`.

| Metric | Baseline HPA | KEDA | Delta |
|---|---|---|---|
| Reaction latency | **73.83 s** | **63.38 s** | −14% |
| Scale-up time (→6 pods) | **90.22 s** | **80.22 s** | −11% |
| Drain time (queue → 0) | **309.74 s** | **297.59 s** | −4% |
| Peak pods | 6 | 6 | = |
| Avg throughput (drain window) | 22.75 msg/s | 23.35 msg/s | +3% |

## 5. Known deviations from nominal design

1. **Burst intensity** — pattern designs for 1 000 msg/s but `pika`'s
   `BlockingConnection.basic_publish` ceilings at ~740 msg/s on the
   `m5.large` node. The `rate_in` column peaks at 714–742 msg/s across all
   six trials (consistent across both groups, so the comparison is still
   valid); total messages per trial therefore settles at ~7 100–7 500
   rather than 10 000.
2. **Producer exit code** — the Python `pika` client returns exit=1 during
   its normal-shutdown teardown on some pika/Python combinations. This
   previously caused `run-experiment.sh` to abort *before* the 180 s
   observation window, producing metrics CSVs of only ~105 rows. The script
   now wraps the producer call in `set +e` / captures `PRODUCER_RC` and
   continues on to the observation window regardless. See the commit
   touching `scripts/run-experiment.sh` for the fix.
3. **Collector cadence** — `collect-metrics.sh` loops `sleep 1` but the
   body of the loop (`kubectl` + `curl` + four `jq` invocations) takes ~1 s
   on a 2 vCPU node under load, yielding an effective 2 s cadence
   (184–203 rows per 390 s trial). Adequate for scaling-event granularity
   but worth keeping in mind when looking at instantaneous rates.
4. **`rabbitmq-diagnostics` replaced** — the original manifest used
   `exec: rabbitmq-diagnostics status` probes; these kept tripping under
   the 1 s default timeout on the constrained node and the pod went into
   `CrashLoopBackOff`. The deployed manifest now uses `tcpSocket: 5672`
   for both readiness and liveness.

## 6. Reproducing the figures

From the repo root:

```bash
python3 -m venv .venv-analysis
.venv-analysis/bin/pip install 'pandas>=2.2' 'matplotlib>=3.9' 'numpy>=1.26'
.venv-analysis/bin/python analysis/plot.py
```

Output:

- `results/summary.csv` — per-trial metrics
- `results/figures/fig1-pod-scaling-timeline.png`
- `results/figures/fig2-queue-depth-timeline.png`
- `results/figures/fig3-reaction-latency-bar.png`
- `results/figures/fig4-throughput-comparison.png`

> `analysis/requirements.txt` pins `matplotlib==3.8.4`, which has no Python
> 3.13 wheel (it tries to build FreeType via `make`). Loosen the pins to
> `>=` or bump to `matplotlib>=3.9` before re-running on Python 3.13.

## 7. Full step-by-step execution flow

The authoritative runbook is `plan/10-执行手册.md` (附录 F + G). The
condensed command-level flow that produced the CSVs in this directory is:

```text
PHASE 0  — Prerequisites on laptop
    - Colima (or any Docker engine) running
    - AWS Learner Lab credits available, us-west-2
    - SSH keypair + m5.large AMI Ubuntu 22.04 launched
    - Security group opened for 22, 6443, 31672, 30567, 30000-32767

PHASE 1  — Bootstrap EC2
    ssh ubuntu@$EC2_IP
    git clone https://github.com/QinHaoting/CS5296-Group5-Autoscaling.git
    cd CS5296-Group5-Autoscaling
    bash scripts/setup.sh                # installs K3s + Helm + metrics-server + KEDA + RabbitMQ

PHASE 2  — Build and publish consumer image (on laptop)
    docker buildx build --platform linux/amd64 \
        -t htasteqin/cs5296-consumer:v1.0 --push consumer/

PHASE 3  — Deploy both groups (on EC2)
    kubectl apply -f k8s/baseline/
    kubectl apply -f k8s/keda/

PHASE 4  — Local Python env (on EC2)
    python3 -m venv .venv-loadtest
    .venv-loadtest/bin/pip install -r load-test/requirements.txt

PHASE 5  — Smoke rehearsal (1 short run per group)
    # see results/smoke/ for the archived rehearsal artefacts

PHASE 6  — Formal batch (6 trials via runner.sh)
    # runner.sh is uploaded to ~/runner.sh on EC2 and launched in tmux:
    tmux new-session -d -s exp 'bash ~/runner.sh 2>&1 | tee -a ~/experiment.log'
    # Each trial:
    #   1. scale deploy/consumer --replicas=1 (under HPA / KEDA)
    #   2. rabbitmqctl purge_queue <group>-queue
    #   3. collect-metrics.sh in background
    #   4. python producer.py --pattern burst.yaml (200 s)
    #   5. sleep 180 s observation window
    #   6. kill collector, write {group}-run{N}.csv
    # After 6 trials + 5× 120 s cooldowns: 49 min total.

PHASE 7  — Harvest and analyse (on laptop)
    rsync -avz -e "ssh -i $EC2_KEY" \
        ubuntu@$EC2_IP:~/CS5296-Group5-Autoscaling/results/raw/ results/raw/
    python analysis/plot.py
```

## 8. Companion artefacts

- `../smoke/` — pre-flight rehearsal with a shorter pattern (500 msgs at 20 msg/s). Not used in the headline numbers but documents how we tuned the manifest before the formal batch.
- `../summary.csv` — the table behind section 4.
- `../figures/` — the four publication figures.
